"""Automatic loading and unloading of Discord event-listener extensions."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from discord.ext import commands


class EventManager:
    """Load event-listener extensions from the project's ``events`` package.

    Event modules are discovered recursively and must expose discord.py's
    standard ``async def setup(bot)`` entry point.  They should contain only
    gateway event handling and delegate real work to ``bot.services``.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        package: str = "events",
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._package_name = package
        self._log = logger or logging.getLogger("verification_bot.events")
        self._loaded_extensions: list[str] = []
        self._loaded = False

    async def load(self) -> None:
        """Discover and load listener extensions in stable alphabetical order."""
        if self._loaded:
            return

        for extension_name in self._discover_extensions():
            try:
                await self._bot.load_extension(extension_name)
            except commands.ExtensionError:
                self._log.exception("Could not load event extension '%s'.", extension_name)
                await self.close()
                raise
            self._loaded_extensions.append(extension_name)
            self._log.debug("Loaded event extension '%s'.", extension_name)

        self._loaded = True
        self._log.info("Loaded %d event extension(s).", len(self._loaded_extensions))

    async def close(self) -> None:
        """Unload event extensions created by this manager in reverse order."""
        while self._loaded_extensions:
            extension_name = self._loaded_extensions.pop()
            try:
                await self._bot.unload_extension(extension_name)
                self._log.debug("Unloaded event extension '%s'.", extension_name)
            except commands.ExtensionError:
                self._log.exception("Could not unload event extension '%s'.", extension_name)
        self._loaded = False

    def _discover_extensions(self) -> list[str]:
        """Find non-private Python modules beneath the configured package."""
        try:
            package = importlib.import_module(self._package_name)
        except ModuleNotFoundError as error:
            if error.name == self._package_name:
                raise RuntimeError(
                    f"Event package '{self._package_name}' does not exist. "
                    "Create it with an __init__.py file before starting the bot."
                ) from error
            raise

        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            raise RuntimeError(f"Event package '{self._package_name}' is not a package.")

        names = [
            module.name
            for module in pkgutil.walk_packages(package_paths, f"{package.__name__}.")
            if not module.ispkg and not module.name.rsplit(".", maxsplit=1)[-1].startswith("_")
        ]
        return sorted(names)
