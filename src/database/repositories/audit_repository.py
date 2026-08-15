"""PostgreSQL persistence for staff-facing audit records."""

"""It records and retrieves staff audit history for verification, rank syncing, nickname changes, and admin settings."""

from __future__ import annotations

from datetime import datetime

from ..database import Database
from ..models import AuditEntry
from ...core.types import DiscordGuildID, DiscordUserID, RobloxUserID


class AuditRepository:
    """Create and retrieve concise, server-scoped bot audit records."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def record(
        self,
        *,
        guild_id: DiscordGuildID,
        action: str,
        actor_discord_user_id: DiscordUserID | None = None,
        target_discord_user_id: DiscordUserID | None = None,
        target_roblox_user_id: RobloxUserID | None = None,
        details: str | None = None,
    ) -> AuditEntry:
        """Store an action that staff may need to investigate later."""
        if not action or len(action) > 100:
            raise ValueError("Audit actions must contain between 1 and 100 characters.")
        if details is not None and len(details) > 2_000:
            raise ValueError("Audit details cannot exceed 2,000 characters.")

        row = await self._database.fetchrow(
            """
            INSERT INTO audit_entries (
                guild_id, action, actor_discord_user_id, target_discord_user_id,
                target_roblox_user_id, details
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            guild_id,
            action,
            actor_discord_user_id,
            target_discord_user_id,
            target_roblox_user_id,
            details,
        )
        assert row is not None
        return _to_audit_entry(row)

    async def recent_for_guild(
        self,
        guild_id: DiscordGuildID,
        *,
        limit: int = 25,
    ) -> list[AuditEntry]:
        """Return the newest audit records for a server, capped safely."""
        if not 1 <= limit <= 100:
            raise ValueError("Audit history limit must be between 1 and 100.")
        rows = await self._database.fetch(
            """
            SELECT guild_id, action, actor_discord_user_id, target_discord_user_id,
                   target_roblox_user_id, details, occurred_at
            FROM audit_entries
            WHERE guild_id = $1
            ORDER BY occurred_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [_to_audit_entry(row) for row in rows]


def _to_audit_entry(row: object) -> AuditEntry:
    return AuditEntry(
        guild_id=DiscordGuildID(row["guild_id"]),  # type: ignore[index]
        action=row["action"],  # type: ignore[index]
        occurred_at=_as_datetime(row["occurred_at"]),  # type: ignore[index]
        actor_discord_user_id=(
            DiscordUserID(row["actor_discord_user_id"])  # type: ignore[index]
            if row["actor_discord_user_id"] is not None  # type: ignore[index]
            else None
        ),
        target_discord_user_id=(
            DiscordUserID(row["target_discord_user_id"])  # type: ignore[index]
            if row["target_discord_user_id"] is not None  # type: ignore[index]
            else None
        ),
        target_roblox_user_id=(
            RobloxUserID(row["target_roblox_user_id"])  # type: ignore[index]
            if row["target_roblox_user_id"] is not None  # type: ignore[index]
            else None
        ),
        details=row["details"],  # type: ignore[index]
    )


def _as_datetime(value: object) -> datetime:
    """Narrow a database timestamp for the dataclass constructor."""
    if not isinstance(value, datetime):
        raise TypeError("Database returned an invalid audit timestamp.")
    return value