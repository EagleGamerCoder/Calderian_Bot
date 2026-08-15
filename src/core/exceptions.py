"""Application-specific exceptions for the Roblox verification bot.

Services raise these errors instead of generic ``Exception``.  Command and API
layers can then turn known failures into safe messages without exposing tokens,
database URLs, or internal stack traces to users.
"""

from __future__ import annotations


class CalderianBotError(Exception):
    """Base class for every expected application-level failure."""

    default_message = "Something went wrong while processing that request."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)

    @property
    def public_message(self) -> str:
        """A safe message that may be shown to a Discord user."""
        return self.default_message


class ConfigurationError(CalderianBotError):
    """Application configuration is missing or invalid."""

    default_message = "The application is not configured correctly."


class ServiceError(CalderianBotError):
    """A registered application service could not perform its task."""


class ServiceNotRegistered(ServiceError):
    """A requested dependency has not been placed in the service container."""

    default_message = "A required application service is unavailable."


class ServiceAlreadyRegistered(ServiceError):
    """A service key was registered more than once."""


class DatabaseError(ServiceError):
    """A database connection or query failed."""

    default_message = "The verification database is temporarily unavailable."


class DatabaseRecordNotFound(DatabaseError):
    """A requested database record does not exist."""

    default_message = "No matching record was found."


class RobloxError(ServiceError):
    """The Roblox integration could not complete its request."""

    default_message = "Roblox could not be reached right now. Please try again shortly."


class RobloxUserNotFound(RobloxError):
    """No Roblox account matched the supplied username or ID."""

    default_message = "That Roblox user could not be found."


class RobloxRequestFailed(RobloxError):
    """A Roblox API response was unsuccessful or invalid."""


class VerificationError(CalderianBotError):
    """A verification request cannot be completed."""

    default_message = "Your verification could not be completed."


class VerificationNotFound(VerificationError):
    """The user has no pending verification session."""

    default_message = "You do not have a verification in progress. Start a new one with /verify."


class VerificationExpired(VerificationError):
    """The verification code or session has expired."""

    default_message = "Your verification expired. Please start again with /verify."


class VerificationProofNotFound(VerificationError):
    """The expected one-time code is not present on the Roblox profile."""

    default_message = "That verification code is not on the Roblox profile yet."


class VerificationAlreadyLinked(VerificationError):
    """A Discord or Roblox account is already linked where it cannot be reused."""

    default_message = "That account is already linked to a verification record."


class GuildNotConfigured(CalderianBotError):
    """A command was used before a Discord server's settings were configured."""

    default_message = "This server has not been configured yet. Ask an administrator to set it up."


class PermissionDenied(CalderianBotError):
    """The caller is authenticated but lacks permission for the action."""

    default_message = "You do not have permission to use that action."


class ExternalAPIError(ServiceError):
    """The bot's own HTTP API received an invalid or unauthorised request."""

    default_message = "The API request could not be completed."


class APIAuthenticationError(ExternalAPIError):
    """An API caller did not provide the configured application secret."""

    default_message = "The API request was not authorised."