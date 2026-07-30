"""Typed application configuration loaded from environment variables.

Only this module should read environment variables.  The rest of the
application receives a validated :class:`Config` instance through startup.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when the application cannot start with its current settings."""


@dataclass(frozen=True, slots=True)
class Config:
    """Validated runtime settings for the Discord verification application.

    Secrets stay in this object only; avoid logging or serialising the whole
    object because it contains the Discord token and database connection URL.
    """

    discord_token: str
    database_url: str
    roblox_cookie: str | None
    api_host: str
    api_port: int
    api_secret: str | None
    debug: bool
    sync_commands: bool
    development_guild_id: int | None
    log_level: str

    @classmethod
    def from_environment(cls, env_file: str | Path = ".env") -> Config:
        """Load, validate, and return settings from a local ``.env`` file.

        Values already present in the process environment take precedence over
        the file, which makes the same code safe to use in deployment services.
        """
        load_dotenv(dotenv_path=env_file, override=False)

        debug = _read_bool("DEBUG", default=False)
        return cls(
            discord_token=_require("DISCORD_TOKEN"),
            database_url=_require("DATABASE_URL"),
            roblox_cookie=_optional("ROBLOX_COOKIE"),
            api_host=_optional("API_HOST") or "127.0.0.1",
            api_port=_read_port("API_PORT", default=8080),
            api_secret=_optional("API_SECRET"),
            debug=debug,
            sync_commands=_read_bool("SYNC_COMMANDS", default=True),
            development_guild_id=_read_optional_snowflake("DEVELOPMENT_GUILD_ID"),
            log_level=(_optional("LOG_LEVEL") or ("DEBUG" if debug else "INFO")).upper(),
        )

    @property
    def is_development(self) -> bool:
        """Whether the application is running with development diagnostics."""
        return self.debug

    def safe_summary(self) -> dict[str, object]:
        """Return non-secret settings suitable for a startup log entry."""
        return {
            "api_host": self.api_host,
            "api_port": self.api_port,
            "debug": self.debug,
            "sync_commands": self.sync_commands,
            "development_guild_id": self.development_guild_id,
            "log_level": self.log_level,
            "roblox_cookie_configured": self.roblox_cookie is not None,
            "api_secret_configured": self.api_secret is not None,
        }


def _require(name: str) -> str:
    """Read a non-empty required setting without ever exposing its value."""
    value = _optional(name)
    if value is None:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    """Read an optional variable and normalise blank values to ``None``."""
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_bool(name: str, *, default: bool) -> bool:
    """Read a strict boolean setting (true/false, yes/no, or 1/0)."""
    value = _optional(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} must be true/false, yes/no, or 1/0; received an invalid value."
    )


def _read_port(name: str, *, default: int) -> int:
    """Read a valid TCP port."""
    value = _optional(name)
    if value is None:
        return default
    try:
        port = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a whole number.") from error
    if not 1 <= port <= 65_535:
        raise ConfigurationError(f"{name} must be between 1 and 65535.")
    return port


def _read_optional_snowflake(name: str) -> int | None:
    """Read an optional positive Discord snowflake ID."""
    value = _optional(name)
    if value is None:
        return None
    try:
        snowflake = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a Discord ID made of digits.") from error
    if snowflake <= 0:
        raise ConfigurationError(f"{name} must be a positive Discord ID.")
    return snowflake