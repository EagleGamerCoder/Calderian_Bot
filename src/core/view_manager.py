"""Registration and lifecycle management for persistent Discord UI views."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import discord
from discord.ext import commands


ViewFactory = Callable[[commands.Bot], discord.ui.View | Awaitable[discord.ui.View]]


@dataclass(frozen=True, slots=True)
class ViewDefinition:
    """A named factory for one persistent Discord view."""

    name: str
    factory: ViewFactory


class ViewManager:
    """Create and register persistent views during Discord startup.

    A view is registered once here rather than when a command sends its embed.
    That allows Discord to route button interactions to it after a process
    restart.  Persistent views must have ``timeout=None`` and stable custom IDs
    on every interactive item.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._log = logger or logging.getLogger("verification_bot.views")
        self._definitions: dict[str, ViewDefinition] = {}
        self._active_views: list[discord.ui.View] = []
        self._loaded = False

    def register(self, name: str, factory: ViewFactory) -> None:
        """Declare a view factory before startup.

        Example::

            manager.register("verify", lambda bot: VerifyView(bot.services.verification))
        """
        if self._loaded:
            raise RuntimeError("Views cannot be registered after startup.")
        if not name or not name.isidentifier() or name.startswith("_"):
            raise ValueError("View names must be public Python identifiers.")
        if name in self._definitions:
            raise ValueError(f"View '{name}' has already been declared.")
        if not callable(factory):
            raise TypeError("A view factory must be callable.")
        self._definitions[name] = ViewDefinition(name, factory)

    async def load(self) -> None:
        """Create and register all persistent views exactly once."""
        if self._loaded:
            return

        try:
            for definition in self._definitions.values():
                view = definition.factory(self._bot)
                if inspect.isawaitable(view):
                    view = await view
                self._validate_persistent_view(definition.name, view)
                self._bot.add_view(view)
                self._active_views.append(view)
                self._log.debug("Registered persistent view '%s'.", definition.name)
        except Exception:
            await self.close()
            raise

        self._loaded = True
        self._log.info("Registered %d persistent view(s).", len(self._active_views))

    async def close(self) -> None:
        """Stop views owned by this manager during application shutdown."""
        while self._active_views:
            view = self._active_views.pop()
            view.stop()
        self._loaded = False

    @staticmethod
    def _validate_persistent_view(name: str, view: Any) -> None:
        if not isinstance(view, discord.ui.View):
            raise TypeError(f"View factory '{name}' did not return discord.ui.View.")
        if not view.is_persistent():
            raise ValueError(
                f"View '{name}' is not persistent. Set timeout=None and give every "
                "button, select menu, or other interactive item a custom_id."
            )