"""Application composition root and executable startup entry point.

This is the only core module that wires concrete objects together.  All other
modules receive dependencies instead of creating global database clients, bots,
or services themselves.
"""

from __future__ import annotations

import asyncio
import logging

from .client import RuntimeComponents, CalderianBot
from .command_manager import CommandManager
from .config import Config, ConfigurationError
from .container import ServiceContainer
from .event_manager import EventManager
from .logger import setup_logging
from .service_manager import ServiceManager
from .view_manager import ViewManager


def build_bot(config: Config, logger: logging.Logger | None = None) -> CalderianBot:
    """Construct a fully configured, but not yet connected, Discord bot.

    This function is deliberately synchronous and side-effect free.  It makes
    integration tests possible without opening a Discord or database connection.
    """
    application_logger = logger or logging.getLogger("verification_bot")
    container = ServiceContainer()
    bot = CalderianBot(config, logger=application_logger)

    service_manager = ServiceManager(config, container, application_logger)
    command_manager = CommandManager(bot, logger=application_logger)
    event_manager = EventManager(bot, logger=application_logger)
    view_manager = ViewManager(bot, logger=application_logger)

    register_services(service_manager)
    register_views(view_manager)

    bot.configure_runtime(
        RuntimeComponents(
            services=container,
            service_manager=service_manager,
            command_manager=command_manager,
            event_manager=event_manager,
            view_manager=view_manager,
        )
    )
    return bot


def register_services(manager: ServiceManager) -> None:
    """Register concrete services as they are implemented.

    Keep all service construction here.  For example, after the database and
    Roblox modules exist, this function will contain registrations like::

        manager.register("database", DatabaseService.create)
        manager.register("roblox", RobloxService.create)
        manager.register(
            "verification",
            VerificationService.create,
            depends_on=("database", "roblox", "roles"),
        )

    The empty implementation is intentional: the core can be completed before
    the business-layer services are written.
    """


def register_views(manager: ViewManager) -> None:
    """Register persistent UI views as they are implemented.

    For example, once ``VerifyView`` exists::

        manager.register("verify", lambda bot: VerifyView(bot.services.verification))
    """


async def run() -> None:
    """Load settings, configure logs, and keep the Discord bot running."""
    try:
        config = Config.from_environment()
    except ConfigurationError as error:
        # Configuration failures occur before a configured application logger
        # exists.  The message identifies only the missing setting, never a secret.
        raise SystemExit(f"Configuration error: {error}") from error

    logger = setup_logging(config)
    logger.info("Starting verification bot with settings: %s", config.safe_summary())
    bot = build_bot(config, logger)

    try:
        async with bot:
            await bot.start(config.discord_token)
    except KeyboardInterrupt:
        logger.info("Shutdown requested from the keyboard.")
    except Exception:
        logger.exception("The bot stopped because of an unexpected error.")
        raise


def main() -> None:
    """Run the asynchronous application from a terminal."""
    asyncio.run(run())


if __name__ == "__main__":
    main()