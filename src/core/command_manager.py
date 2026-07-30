"""Automatic loading and unloading of Discord command extensions."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from discord.ext import commands


class CommandManager:
    """Load every command extension underneath a Python package.

    With the default package, a future project can use this structure::

        src/commands/
            verification/verify.py
            moderation/sync.py
            admin/settings.py

    Every command module must provide the normal discord.py extension entry
    point: ``async def setup(bot): ...``.  The manager discovers those modules
    recursively, so adding a new command does not require editing startup code.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        package: str = "commands",
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._package_name = package
        self._log = logger or logging.getLogger("verification_bot.commands")
        self._loaded_extensions: list[str] = []
        self._loaded = False

    async def load(self) -> None:
        """Discover and load command modules once, in alphabetical order."""
        if self._loaded:
            return

        for extension_name in self._discover_extensions():
            try:
                await self._bot.load_extension(extension_name)
            except commands.ExtensionError:
                self._log.exception("Could not load command extension '%s'.", extension_name)
                await self.close()
                raise
            self._loaded_extensions.append(extension_name)
            self._log.debug("Loaded command extension '%s'.", extension_name)

        self._loaded = True
        self._log.info("Loaded %d command extension(s).", len(self._loaded_extensions))

    async def close(self) -> None:
        """Unload extensions created by this manager in reverse load order."""
        while self._loaded_extensions:
            extension_name = self._loaded_extensions.pop()
            try:
                await self._bot.unload_extension(extension_name)
                self._log.debug("Unloaded command extension '%s'.", extension_name)
            except commands.ExtensionError:
                # The Discord client is already closing; continue cleaning up
                # other extensions instead of allowing one bad teardown to stop it.
                self._log.exception("Could not unload command extension '%s'.", extension_name)
        self._loaded = False

    def _discover_extensions(self) -> list[str]:
        """Return importable command modules from the configured package."""
        try:
            package = importlib.import_module(self._package_name)
        except ModuleNotFoundError as error:
            if error.name == self._package_name:
                raise RuntimeError(
                    f"Command package '{self._package_name}' does not exist. "
                    "Create it with an __init__.py file before starting the bot."
                ) from error
            raise

        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            raise RuntimeError(f"Command package '{self._package_name}' is not a package.")

        names = [
            module.name
            for module in pkgutil.walk_packages(package_paths, f"{package.__name__}.")
            if not module.ispkg and not module.name.rsplit(".", maxsplit=1)[-1].startswith("_")
        ]
        return sorted(names)
