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

    Importing here keeps this composition root as the only place that knows
    about concrete services. Individual command modules remain testable and
    depend only on the interfaces placed in ``bot.services``.
    """
    from ..database.database import Database
    from ..database.migrations import MigrationRunner
    from ..database.repositories.audit_repository import AuditRepository
    from ..database.repositories.guild_repository import GuildRepository
    from ..database.repositories.verification_repository import VerificationRepository
    from ..services.cache_service import CacheService
    from ..services.guild_service import GuildService
    from ..services.permission_service import PermissionService
    from ..services.rank_sync_service import RankSyncService
    from ..services.roblox_service import RobloxService
    from ..services.role_service import RoleService
    from ..services.verification_service import VerificationService

    manager.register("database", Database.create)
    manager.register("migrations", MigrationRunner.create, depends_on=("database",))
    manager.register("verification_repository", VerificationRepository.create, depends_on=("migrations",))
    manager.register("guild_repository", GuildRepository.create, depends_on=("migrations",))
    manager.register("audit_repository", AuditRepository.create, depends_on=("migrations",))

    manager.register("cache", CacheService.create)
    manager.register("roblox", RobloxService.create)
    manager.register("roles", RoleService.create)
    manager.register("permissions", PermissionService.create)
    manager.register(
        "guilds",
        GuildService.create,
        depends_on=("guild_repository", "audit_repository"),
    )
    manager.register(
        "verification",
        VerificationService.create,
        depends_on=("verification_repository", "audit_repository", "roblox"),
    )
    manager.register(
        "rank_sync",
        RankSyncService.create,
        depends_on=(
            "verification_repository",
            "guild_repository",
            "audit_repository",
            "roblox",
            "roles",
        ),
    )


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