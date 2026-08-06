"""Business logic for per-guild configuration and rank synchronisation."""

from __future__ import annotations

from ..core.types import (
    DiscordGuildID,
    DiscordRoleID,
    RobloxGroupID,
    RobloxRank,
)
from ..database.models import GroupRankRule, GuildConfig
from ..database.repositories.guild_repository import GuildRepository


class GuildService:
    """Manage guild configuration and Roblox group rank rules."""

    def __init__(self, repository: GuildRepository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------
    # Guild configuration
    # ------------------------------------------------------------------

    async def get_config(
        self,
        guild_id: DiscordGuildID,
    ) -> GuildConfig | None:
        """Return a guild's configuration, if it exists."""
        return await self._repository.get_config(guild_id)

    async def get_or_create_config(
        self,
        guild_id: DiscordGuildID,
    ) -> GuildConfig:
        """Return a guild's configuration, creating safe defaults if needed."""
        return await self._repository.get_or_create_config(guild_id)

    async def save_config(
        self,
        config: GuildConfig,
    ) -> GuildConfig:
        """Validate and persist a complete guild configuration."""
        self._validate_config(config)

        return await self._repository.save_config(config)

    # ------------------------------------------------------------------
    # Rank rules
    # ------------------------------------------------------------------

    async def get_rank_rules(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
    ) -> list[GroupRankRule]:
        """Return rank rules for a guild and Roblox group."""
        return await self._repository.get_rank_rules(
            guild_id,
            roblox_group_id,
        )

    async def replace_rank_rules(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rules: list[GroupRankRule],
    ) -> None:
        """Validate and atomically replace a group's rank rules."""
        self._validate_rank_rules(
            guild_id,
            roblox_group_id,
            rules,
        )

        await self._repository.replace_rank_rules(
            guild_id,
            roblox_group_id,
            rules,
        )

    async def resolve_rank_rule(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rank: RobloxRank,
    ) -> GroupRankRule | None:
        """
        Find the highest-priority rule matching a Roblox rank.

        The repository already returns rules ordered by priority, so the
        first matching rule wins.
        """
        rules = await self.get_rank_rules(
            guild_id,
            roblox_group_id,
        )

        for rule in rules:
            if rule.matches(rank):
                return rule

        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_config(config: GuildConfig) -> None:
        """Validate values that must be safe before reaching the database."""
        if not config.nickname_template.strip():
            raise ValueError("nickname_template cannot be empty.")

        if "{roblox_username}" not in config.nickname_template:
            raise ValueError(
                "nickname_template must contain '{roblox_username}'."
            )

    @staticmethod
    def _validate_rank_rules(
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rules: list[GroupRankRule],
    ) -> None:
        """Validate a complete set of rank rules before persistence."""
        for rule in rules:
            if rule.guild_id != guild_id:
                raise ValueError(
                    "Every rank rule must belong to the selected guild."
                )

            if rule.roblox_group_id != roblox_group_id:
                raise ValueError(
                    "Every rank rule must belong to the selected Roblox group."
                )

            if rule.minimum_rank > rule.maximum_rank:
                raise ValueError(
                    "minimum_rank cannot be greater than maximum_rank."
                )

            if not 0 <= rule.minimum_rank <= 255:
                raise ValueError(
                    "minimum_rank must be between 0 and 255."
                )

            if not 0 <= rule.maximum_rank <= 255:
                raise ValueError(
                    "maximum_rank must be between 0 and 255."
                )

            if rule.priority < 0:
                raise ValueError(
                    "priority cannot be negative."
                )