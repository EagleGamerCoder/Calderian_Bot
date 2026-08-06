"""The Discord client and lifecycle boundary for the verification bot.

This module deliberately owns Discord lifecycle concerns only.  Database,
Roblox, HTTP, and verification behaviour belong to services that are attached
by ``startup.py`` through :class:`RuntimeComponents`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from .config import Config
    from .container import ServiceContainer
    from .service_manager import ServiceManager
    from .command_manager import CommandManager
    from .event_manager import EventManager
    from .view_manager import ViewManager


class LifecycleManager(Protocol):
    """Minimum contract implemented by the future core managers."""

    async def load(self) -> None:
        """Initialise or register this manager's resources."""

    async def close(self) -> None:
        """Release resources owned by this manager."""


@dataclass(slots=True)
class RuntimeComponents:
    """Dependencies attached by ``startup.py`` before the bot is started.

    Keeping construction outside the Discord client avoids import cycles and
    makes the bot straightforward to test with fake managers.
    """

    services: ServiceContainer
    service_manager: LifecycleManager
    command_manager: LifecycleManager
    event_manager: LifecycleManager
    view_manager: LifecycleManager


class CalderianBot(commands.Bot):
    """Discord client for a Roblox-to-Discord verification application.

    The client coordinates startup in a fixed order:

    1. Create services (database, Roblox client, repositories, etc.).
    2. Load commands and event listeners.
    3. Register persistent Discord views.
    4. Optionally synchronise application commands.

    It intentionally does *not* contain verification rules, SQL, Roblox HTTP
    calls, or web routes.  Those all remain independently testable services.
    """

    def __init__(
        self,
        config: Config,
        *,
        intents: discord.Intents | None = None,
        command_prefix: str = "!",
        logger: logging.Logger | None = None,
    ) -> None:
        """Create an unstarted Discord bot.

        Args:
            config: Application settings created by ``core.config``.
            intents: Discord gateway intents.  Supplying explicit intents is
                preferred; a safe baseline is used when omitted.
            command_prefix: Temporary prefix for any legacy text commands.
                Slash commands remain the primary command interface.
            logger: Application logger supplied by ``core.logger``.
        """
        super().__init__(
            command_prefix=command_prefix,
            intents=intents or self.default_intents(),
            help_command=None,
        )
        self.config = config
        self.log = logger or logging.getLogger("verification_bot")

        # Assigned once by startup.py.  ``None`` keeps basic login tests and
        # incremental project setup possible before the other core files exist.
        self.services: ServiceContainer | None = None
        self._runtime: RuntimeComponents | None = None
        self._setup_lock = asyncio.Lock()
        self._started = asyncio.Event()
        self._closing = False

    @staticmethod
    def default_intents() -> discord.Intents:
        """Return the least-privileged intents normally needed by this bot."""
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True  # Required for role and nickname updates.
        return intents

    def configure_runtime(self, runtime: RuntimeComponents) -> None:
        """Attach core managers before calling :meth:`start`.

        Calling this after Discord startup would leave lifecycle ownership
        ambiguous, so it is intentionally rejected once setup has completed.
        """
        if self._started.is_set():
            raise RuntimeError("Runtime components cannot be changed after setup.")
        if self._runtime is not None:
            raise RuntimeError("Runtime components have already been configured.")

        self._runtime = runtime
        self.services = runtime.services

    async def setup_hook(self) -> None:
        """Initialise application dependencies before the gateway connects."""
        async with self._setup_lock:
            if self._started.is_set():
                return

            if self._runtime is None:
                self.log.warning(
                    "No runtime components configured; starting without services, "
                    "commands, events, or persistent views."
                )
            else:
                await self._runtime.service_manager.load()
                await self._runtime.command_manager.load()
                await self._runtime.event_manager.load()
                await self._runtime.view_manager.load()
                await self._sync_application_commands()

            self._started.set()
            self.log.info("Application setup completed.")

    async def _sync_application_commands(self) -> None:
        """Synchronise slash commands when enabled by the application config.

        ``development_guild_id`` makes command changes appear immediately in a
        single development guild; production falls back to global synchronising.
        """
        if not self._config_value("sync_commands", True):
            self.log.info("Application-command sync disabled by configuration.")
            return

        development_guild_id = self._config_value("development_guild_id", None)
        if development_guild_id is not None:
            guild = discord.Object(id=int(development_guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self.log.info("Synced %d command(s) to development guild %s.", synced, guild.id)
            return

        synced = await self.tree.sync()
        self.log.info("Synced %d global application command(s).", len(synced))

    def get_service(self, name: str) -> Any:
        """Return a named service from the container or raise a clear error."""
        if self.services is None:
            raise RuntimeError("Services are not configured; startup is incomplete.")
        try:
            return getattr(self.services, name)
        except AttributeError as error:
            raise LookupError(f"Service '{name}' is not registered.") from error

    async def wait_until_started(self) -> None:
        """Wait until managers have been loaded (useful in integration tests)."""
        await self._started.wait()

    async def on_ready(self) -> None:
        """Log gateway readiness without putting business logic in an event."""
        if self.user is not None:
            self.log.info("Connected to Discord as %s (%s).", self.user, self.user.id)

    async def close(self) -> None:
        """Close managed resources in reverse startup order, then Discord."""
        if self._closing:
            return
        self._closing = True

        try:
            if self._runtime is not None:
                for manager in (
                    self._runtime.view_manager,
                    self._runtime.event_manager,
                    self._runtime.command_manager,
                    self._runtime.service_manager,
                ):
                    try:
                        await manager.close()
                    except Exception:
                        # Continue shutdown so pooled DB and HTTP resources do
                        # not leak because one manager failed to close cleanly.
                        self.log.exception("Error while closing %s.", type(manager).__name__)
        finally:
            await super().close()

    def _config_value(self, name: str, default: Any) -> Any:
        """Read a config field while allowing this file to be built first."""
        return getattr(self.config, name, default)
