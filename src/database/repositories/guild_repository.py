"""PostgreSQL persistence for per-guild configuration and group rank rules."""

from __future__ import annotations

from ..database import Database
from ..models import GroupRankRule, GuildConfig
from ...core.types import (
    DiscordChannelID,
    DiscordGuildID,
    DiscordRoleID,
    RobloxGroupID,
    RobloxRank,
)


class GuildRepository:
    """Read and write one Discord server's bot settings and role mappings."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_config(self, guild_id: DiscordGuildID) -> GuildConfig | None:
        row = await self._database.fetchrow(
            "SELECT * FROM guild_configs WHERE guild_id = $1", guild_id
        )
        return _to_guild_config(row) if row else None

    async def get_or_create_config(self, guild_id: DiscordGuildID) -> GuildConfig:
        """Return a guild's configuration, creating safe defaults if needed."""
        row = await self._database.fetchrow(
            """
            INSERT INTO guild_configs (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO UPDATE SET guild_id = EXCLUDED.guild_id
            RETURNING *
            """,
            guild_id,
        )
        assert row is not None
        return _to_guild_config(row)

    async def save_config(self, config: GuildConfig) -> GuildConfig:
        """Insert or replace all configurable settings for a guild."""
        row = await self._database.fetchrow(
            """
            INSERT INTO guild_configs (
                guild_id, verified_role_id, unverified_role_id, log_channel_id,
                roblox_group_id, nickname_template, rank_sync_enabled
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (guild_id) DO UPDATE SET
                verified_role_id = EXCLUDED.verified_role_id,
                unverified_role_id = EXCLUDED.unverified_role_id,
                log_channel_id = EXCLUDED.log_channel_id,
                roblox_group_id = EXCLUDED.roblox_group_id,
                nickname_template = EXCLUDED.nickname_template,
                rank_sync_enabled = EXCLUDED.rank_sync_enabled,
                updated_at = NOW()
            RETURNING *
            """,
            config.guild_id,
            config.verified_role_id,
            config.unverified_role_id,
            config.log_channel_id,
            config.roblox_group_id,
            config.nickname_template,
            config.rank_sync_enabled,
        )
        assert row is not None
        return _to_guild_config(row)

    async def get_rank_rules(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
    ) -> list[GroupRankRule]:
        """Return a group's rules ordered so higher priorities apply first."""
        rows = await self._database.fetch(
            """
            SELECT guild_id, roblox_group_id, discord_role_id, minimum_rank, maximum_rank, priority
            FROM group_rank_rules
            WHERE guild_id = $1 AND roblox_group_id = $2
            ORDER BY priority DESC, minimum_rank DESC
            """,
            guild_id,
            roblox_group_id,
        )
        return [_to_group_rank_rule(row) for row in rows]

    async def replace_rank_rules(
        self,
        guild_id: DiscordGuildID,
        roblox_group_id: RobloxGroupID,
        rules: list[GroupRankRule],
    ) -> None:
        """Atomically replace every rank rule for one server and Roblox group."""
        if any(
            rule.guild_id != guild_id or rule.roblox_group_id != roblox_group_id for rule in rules
        ):
            raise ValueError("Every rank rule must belong to the selected guild and Roblox group.")

        async with self._database.transaction() as connection:
            await connection.execute(
                "DELETE FROM group_rank_rules WHERE guild_id = $1 AND roblox_group_id = $2",
                guild_id,
                roblox_group_id,
            )
            if rules:
                await connection.executemany(
                    """
                    INSERT INTO group_rank_rules (
                        guild_id, roblox_group_id, discord_role_id,
                        minimum_rank, maximum_rank, priority
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    [
                        (
                            rule.guild_id,
                            rule.roblox_group_id,
                            rule.discord_role_id,
                            rule.minimum_rank,
                            rule.maximum_rank,
                            rule.priority,
                        )
                        for rule in rules
                    ],
                )


def _to_guild_config(row: object) -> GuildConfig:
    return GuildConfig(
        guild_id=DiscordGuildID(row["guild_id"]),  # type: ignore[index]
        verified_role_id=(
            DiscordRoleID(row["verified_role_id"])  # type: ignore[index]
            if row["verified_role_id"] is not None  # type: ignore[index]
            else None
        ),
        unverified_role_id=(
            DiscordRoleID(row["unverified_role_id"])  # type: ignore[index]
            if row["unverified_role_id"] is not None  # type: ignore[index]
            else None
        ),
        log_channel_id=(
            DiscordChannelID(row["log_channel_id"])  # type: ignore[index]
            if row["log_channel_id"] is not None  # type: ignore[index]
            else None
        ),
        roblox_group_id=(
            RobloxGroupID(row["roblox_group_id"])  # type: ignore[index]
            if row["roblox_group_id"] is not None  # type: ignore[index]
            else None
        ),
        nickname_template=row["nickname_template"],  # type: ignore[index]
        rank_sync_enabled=row["rank_sync_enabled"],  # type: ignore[index]
        created_at=row["created_at"],  # type: ignore[index]
        updated_at=row["updated_at"],  # type: ignore[index]
    )


def _to_group_rank_rule(row: object) -> GroupRankRule:
    return GroupRankRule(
        guild_id=DiscordGuildID(row["guild_id"]),  # type: ignore[index]
        roblox_group_id=RobloxGroupID(row["roblox_group_id"]),  # type: ignore[index]
        discord_role_id=DiscordRoleID(row["discord_role_id"]),  # type: ignore[index]
        minimum_rank=RobloxRank(row["minimum_rank"]),  # type: ignore[index]
        maximum_rank=RobloxRank(row["maximum_rank"]),  # type: ignore[index]
        priority=row["priority"],  # type: ignore[index]
    )
