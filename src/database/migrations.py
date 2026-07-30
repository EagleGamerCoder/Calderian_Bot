"""Versioned PostgreSQL schema migrations for the verification bot."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered, irreversible database schema change."""

    version: int
    name: str
    statements: tuple[str, ...]


INITIAL_SCHEMA = Migration(
    version=1,
    name="initial_verification_schema",
    statements=(
        """
        CREATE TABLE verified_users (
            discord_user_id BIGINT PRIMARY KEY,
            roblox_user_id BIGINT UNIQUE NOT NULL,
            roblox_username TEXT NOT NULL,
            roblox_display_name TEXT NOT NULL,
            verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE pending_verifications (
            code TEXT PRIMARY KEY,
            discord_user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            roblox_user_id BIGINT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed', 'expired', 'cancelled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX pending_verifications_one_active_per_member
        ON pending_verifications (discord_user_id, guild_id)
        WHERE status = 'pending'
        """,
        """
        CREATE INDEX pending_verifications_expiry_index
        ON pending_verifications (expires_at)
        WHERE status = 'pending'
        """,
        """
        CREATE TABLE guild_configs (
            guild_id BIGINT PRIMARY KEY,
            verified_role_id BIGINT,
            unverified_role_id BIGINT,
            log_channel_id BIGINT,
            roblox_group_id BIGINT,
            nickname_template TEXT NOT NULL DEFAULT '{roblox_username}',
            rank_sync_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE group_rank_rules (
            id BIGSERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            roblox_group_id BIGINT NOT NULL,
            discord_role_id BIGINT NOT NULL,
            minimum_rank SMALLINT NOT NULL CHECK (minimum_rank BETWEEN 0 AND 255),
            maximum_rank SMALLINT NOT NULL CHECK (maximum_rank BETWEEN 0 AND 255),
            priority INTEGER NOT NULL DEFAULT 0,
            CHECK (minimum_rank <= maximum_rank)
        )
        """,
        """
        CREATE INDEX group_rank_rules_lookup_index
        ON group_rank_rules (guild_id, roblox_group_id, priority DESC)
        """,
        """
        CREATE TABLE audit_entries (
            id BIGSERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            action TEXT NOT NULL,
            actor_discord_user_id BIGINT,
            target_discord_user_id BIGINT,
            target_roblox_user_id BIGINT,
            details TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE INDEX audit_entries_guild_time_index
        ON audit_entries (guild_id, occurred_at DESC)
        """,
    ),
)

MIGRATIONS: tuple[Migration, ...] = (INITIAL_SCHEMA,)


class MigrationRunner:
    """Apply each schema migration once and record its version."""

    def __init__(self, database: Database, logger: logging.Logger | None = None) -> None:
        self._database = database
        self._log = logger or logging.getLogger("verification_bot.migrations")

    async def run(self) -> None:
        """Create migration tracking and apply every outstanding migration."""
        await self._create_tracking_table()
        applied_versions = await self._applied_versions()

        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue
            await self._apply(migration)

    async def _create_tracking_table(self) -> None:
        await self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    async def _applied_versions(self) -> set[int]:
        rows = await self._database.fetch("SELECT version FROM schema_migrations")
        return {int(row["version"]) for row in rows}

    async def _apply(self, migration: Migration) -> None:
        self._log.info("Applying migration %d: %s", migration.version, migration.name)
        async with self._database.transaction() as connection:
            for statement in migration.statements:
                await connection.execute(statement)
            await connection.execute(
                "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                migration.version,
                migration.name,
            )
        self._log.info("Applied migration %d.", migration.version)
