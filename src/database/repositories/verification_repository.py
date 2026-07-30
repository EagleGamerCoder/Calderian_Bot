"""PostgreSQL persistence for Roblox-to-Discord verification records."""

from __future__ import annotations

from datetime import datetime

from ..database import Database
from ..models import PendingVerification, VerificationStatus, VerifiedUser
from ...core.types import DiscordGuildID, DiscordUserID, RobloxUserID, VerificationCode


class VerificationRepository:
    """Read and write verification links and short-lived pending codes only."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_verified_by_discord(self, user_id: DiscordUserID) -> VerifiedUser | None:
        row = await self._database.fetchrow(
            "SELECT * FROM verified_users WHERE discord_user_id = $1", user_id
        )
        return _to_verified_user(row) if row else None

    async def get_verified_by_roblox(self, user_id: RobloxUserID) -> VerifiedUser | None:
        row = await self._database.fetchrow(
            "SELECT * FROM verified_users WHERE roblox_user_id = $1", user_id
        )
        return _to_verified_user(row) if row else None

    async def save_verified(
        self,
        *,
        discord_user_id: DiscordUserID,
        roblox_user_id: RobloxUserID,
        roblox_username: str,
        roblox_display_name: str,
    ) -> VerifiedUser:
        """Create or refresh the Roblox link for one Discord user."""
        row = await self._database.fetchrow(
            """
            INSERT INTO verified_users (
                discord_user_id, roblox_user_id, roblox_username, roblox_display_name
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (discord_user_id) DO UPDATE SET
                roblox_user_id = EXCLUDED.roblox_user_id,
                roblox_username = EXCLUDED.roblox_username,
                roblox_display_name = EXCLUDED.roblox_display_name,
                updated_at = NOW()
            RETURNING *
            """,
            discord_user_id,
            roblox_user_id,
            roblox_username,
            roblox_display_name,
        )
        assert row is not None
        return _to_verified_user(row)

    async def unlink(self, user_id: DiscordUserID) -> bool:
        """Remove a Discord user's verification link, if one exists."""
        result = await self._database.execute(
            "DELETE FROM verified_users WHERE discord_user_id = $1", user_id
        )
        return result == "DELETE 1"

    async def create_pending(
        self,
        *,
        code: VerificationCode,
        discord_user_id: DiscordUserID,
        guild_id: DiscordGuildID,
        expires_at: datetime,
        roblox_user_id: RobloxUserID | None = None,
    ) -> PendingVerification:
        """Replace a member's old active code with one new pending code."""
        async with self._database.transaction() as connection:
            await connection.execute(
                """
                UPDATE pending_verifications
                SET status = 'cancelled'
                WHERE discord_user_id = $1 AND guild_id = $2 AND status = 'pending'
                """,
                discord_user_id,
                guild_id,
            )
            row = await connection.fetchrow(
                """
                INSERT INTO pending_verifications (
                    code, discord_user_id, guild_id, roblox_user_id, expires_at
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                code,
                discord_user_id,
                guild_id,
                roblox_user_id,
                expires_at,
            )
        assert row is not None
        return _to_pending_verification(row)

    async def get_pending(self, code: VerificationCode) -> PendingVerification | None:
        """Find a pending verification by its one-time code."""
        row = await self._database.fetchrow(
            "SELECT * FROM pending_verifications WHERE code = $1", code
        )
        return _to_pending_verification(row) if row else None

    async def complete_pending(self, code: VerificationCode) -> bool:
        """Mark a code completed exactly once, preventing reuse."""
        result = await self._database.execute(
            """
            UPDATE pending_verifications
            SET status = 'completed'
            WHERE code = $1 AND status = 'pending' AND expires_at > NOW()
            """,
            code,
        )
        return result == "UPDATE 1"

    async def expire_pending(self, code: VerificationCode) -> bool:
        """Mark an expired pending code so it cannot be completed later."""
        result = await self._database.execute(
            """
            UPDATE pending_verifications
            SET status = 'expired'
            WHERE code = $1 AND status = 'pending' AND expires_at <= NOW()
            """,
            code,
        )
        return result == "UPDATE 1"


def _to_verified_user(row: object) -> VerifiedUser:
    """Convert an asyncpg row into a typed verified-user model."""
    return VerifiedUser(
        discord_user_id=DiscordUserID(row["discord_user_id"]),  # type: ignore[index]
        roblox_user_id=RobloxUserID(row["roblox_user_id"]),  # type: ignore[index]
        roblox_username=row["roblox_username"],  # type: ignore[index]
        roblox_display_name=row["roblox_display_name"],  # type: ignore[index]
        verified_at=row["verified_at"],  # type: ignore[index]
        updated_at=row["updated_at"],  # type: ignore[index]
    )


def _to_pending_verification(row: object) -> PendingVerification:
    """Convert an asyncpg row into a typed pending-verification model."""
    return PendingVerification(
        code=VerificationCode(row["code"]),  # type: ignore[index]
        discord_user_id=DiscordUserID(row["discord_user_id"]),  # type: ignore[index]
        guild_id=DiscordGuildID(row["guild_id"]),  # type: ignore[index]
        roblox_user_id=(
            RobloxUserID(row["roblox_user_id"])  # type: ignore[index]
            if row["roblox_user_id"] is not None  # type: ignore[index]
            else None
        ),
        status=VerificationStatus(row["status"]),  # type: ignore[index]
        created_at=row["created_at"],  # type: ignore[index]
        expires_at=row["expires_at"],  # type: ignore[index]
    )
