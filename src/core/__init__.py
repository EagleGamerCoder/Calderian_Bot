"""Core framework components for the Discord Roblox verification bot."""

from .client import RuntimeComponents, VerificationBot
from .command_manager import CommandManager
from .config import Config
from .container import ServiceContainer
from .event_manager import EventManager
from .exceptions import (
    APIAuthenticationError,
    ConfigurationError,
    DatabaseError,
    GuildNotConfigured,
    PermissionDenied,
    RobloxError,
    RobloxUserNotFound,
    ServiceError,
    ServiceNotRegistered,
    VerificationAlreadyLinked,
    VerificationBotError,
    VerificationError,
    VerificationExpired,
    VerificationNotFound,
)
from .logger import get_logger, setup_logging
from .service_manager import ServiceDefinition, ServiceManager
from .view_manager import ViewManager

__all__ = (
    "APIAuthenticationError",
    "CommandManager",
    "Config",
    "ConfigurationError",
    "DatabaseError",
    "EventManager",
    "GuildNotConfigured",
    "PermissionDenied",
    "RobloxError",
    "RobloxUserNotFound",
    "RuntimeComponents",
    "ServiceContainer",
    "ServiceDefinition",
    "ServiceError",
    "ServiceManager",
    "ServiceNotRegistered",
    "VerificationAlreadyLinked",
    "VerificationBot",
    "VerificationBotError",
    "VerificationError",
    "VerificationExpired",
    "VerificationNotFound",
    "ViewManager",
    "get_logger",
    "setup_logging",
)
