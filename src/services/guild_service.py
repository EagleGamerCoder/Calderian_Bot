"""Business rules for configuring a Discord server's verification features."""

"""It validates and saves server setup settings, nickname templates, Roblox group configuration, and rank-to-role rules. Every staff change is saved to the audit log."""

from __future__ import annotations

import logging
from dataclasses import replace
from string import Formatter
from typing import TYPE_CHECKING

from ..core.types import DiscordGuildID, DiscordUserID, RobloxGroupID
from ..database.models import GroupRankRule, GuildConfig
from ..database.repositories.audit_repository import AuditRepository
from ..database.repositories.guild_repository import GuildRepository

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


NICKNAME_PLACEHOLDERS = {
    "roblox_username",
    "roblox_display_name",
    "roblox_user_id",
    "group_rank",
    "group_role_name",
}


class GuildService:
    """Validate and save one guild's verification and rank-sync configuration."""

    def __init__(
        self,
        guild_repository: GuildRepository,
        audit_repository: AuditRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self._guilds = guild_repository
        self._audit = audit_repository
        self._log = logger or logging.getLogger("verification_bot.guilds")

    @classmethod
    async def create(cls, _: Config, services: ServiceContainer) -> GuildService:
        """Factory used by ``ServiceManager`` after repositories are available."""
        return cls(
            guild_repository=services.require("guild_repository"),
            audit_repository=services.require("audit_repository"),
        )

    async def get_or_create_config(self, guild_id: DiscordGuildID) -> GuildConfig:
        """Return a server's current settings, creating safe defaults if needed."""
        return await self._guilds.get_or_create_config(guild_id)

    async def save_config(
        self,
        config: GuildConfig,
        *,
        actor_discord_user_id: DiscordUserID,
    ) -> GuildConfig:
        """Validate and save full guild settings from a staff configuration flow."""
        self._validate_config(config)
        saved = await self._guilds.save_config(config)
        await self._audit.record(
            guild_id=saved.guild_id,
            action="guild_config_updated",
            actor_discord_user_id=actor_discord_user_id,
            details=(
                f"group_id={saved.roblox_group_id}; "
                f"rank_sync_enabled={saved.rank_sync_enabled}; "
                f"verified_role_id={saved.verified_role_id}; "
                f"unverified_role_id={saved.unverified_role_id}"
            ),
        )
        self._log.info("Updated verification configuration for guild %s.", saved.guild_id)
        return saved

    async def update_config(
        self,
        guild_id: DiscordGuildID,
        *,
        actor_discord_user_id: DiscordUserID,
        **changes: object,
    ) -> GuildConfig:
        """Apply selected setting changes without commands rebuilding the model."""
        current = await self.get_or_create_config(guild_id)
        allowed_fields = {
            "verified_role_id",
            "unverified_role_id",
            "log_channel_id",
            "roblox_group_id",
            "nickname_template",
            "rank_sync_enabled",
        }
        unknown_fields = changes.keys() - allowed_fields
        if unknown_fields:
            raise ValueError(f"Unsupported guild settings: {', '.join(sorted(unknown_fields))}")
        return await self.save_config(
            replace(current, **changes),
            actor_discord_user_id=actor_discord_user_id,
        )

    async def replace_rank_rules(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rules: list[GroupRankRule],
        *,
        actor_discord_user_id: DiscordUserID,
    ) -> None:
        """Validate and atomically replace rank-to-role mappings for one group."""
        self._validate_rank_rules(guild_id, roblox_group_id, rules)
        await self._guilds.replace_rank_rules(guild_id, roblox_group_id, rules)
        await self._audit.record(
            guild_id=guild_id,
            action="group_rank_rules_replaced",
            actor_discord_user_id=actor_discord_user_id,
            details=f"group_id={roblox_group_id}; rule_count={len(rules)}",
        )
        self._log.info("Replaced %d rank rules in guild %s.", len(rules), guild_id)

    @staticmethod
    def _validate_config(config: GuildConfig) -> None:
        if config.verified_role_id is not None and config.verified_role_id == config.unverified_role_id:
            raise ValueError("Verified and unverified roles must be different.")
        if config.rank_sync_enabled and config.roblox_group_id is None:
            raise ValueError("Choose a Roblox group before enabling rank synchronisation.")
        GuildService._validate_nickname_template(config.nickname_template)

    @staticmethod
    def _validate_nickname_template(template: str) -> None:
        if not template or len(template) > 200:
            raise ValueError("Nickname templates must contain between 1 and 200 characters.")
        for _, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if field_name not in NICKNAME_PLACEHOLDERS or format_spec or conversion:
                raise ValueError("Nickname template contains an unsupported placeholder.")

    @staticmethod
    def _validate_rank_rules(
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rules: list[GroupRankRule],
    ) -> None:
        for rule in rules:
            if rule.guild_id != guild_id or rule.roblox_group_id != roblox_group_id:
                raise ValueError("Every rank rule must belong to the selected guild and Roblox group.")
            if not 0 <= rule.minimum_rank <= rule.maximum_rank <= 255:
                raise ValueError("Roblox group ranks must be between 0 and 255.")