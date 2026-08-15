"""The business workflow for secure Roblox profile-code verification."""

"""It issues 15-minute secure codes, checks the Roblox profile description, prevents duplicate account links, atomically saves a verified link, and creates audit entries."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from ..core.exceptions import (
    VerificationAlreadyLinked,
    VerificationError,
    VerificationExpired,
    VerificationNotFound,
    VerificationProofNotFound,
)
from ..core.types import DiscordGuildID, DiscordUserID, VerificationCode
from ..database.models import PendingVerification, VerifiedUser, VerificationStatus
from ..database.repositories.audit_repository import AuditRepository
from ..database.repositories.verification_repository import VerificationRepository
from .roblox_service import RobloxService, RobloxUser

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


VERIFICATION_LIFETIME = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class VerificationStart:
    """Instructions a Discord command or button view can present to a member."""

    pending: PendingVerification
    roblox_user: RobloxUser

    @property
    def instructions(self) -> str:
        return (
            f"Add `{self.pending.code}` to the About section of your Roblox profile, "
            "then press Verify again before the code expires."
        )


@dataclass(frozen=True, slots=True)
class VerificationComplete:
    """The permanent link created by a successful verification."""

    verified_user: VerifiedUser
    guild_id: DiscordGuildID


class VerificationService:
    """Create, validate, and complete one-time Roblox profile verification codes."""

    def __init__(
        self,
        verification_repository: VerificationRepository,
        audit_repository: AuditRepository,
        roblox_service: RobloxService,
        logger: logging.Logger | None = None,
    ) -> None:
        self._verifications = verification_repository
        self._audit = audit_repository
        self._roblox = roblox_service
        self._log = logger or logging.getLogger("verification_bot.verification")

    @classmethod
    async def create(cls, _: Config, services: ServiceContainer) -> VerificationService:
        """Factory used by ``ServiceManager`` after its dependencies are ready."""
        return cls(
            verification_repository=services.require("verification_repository"),
            audit_repository=services.require("audit_repository"),
            roblox_service=services.require("roblox"),
        )

    async def start(
        self,
        *,
        discord_user_id: DiscordUserID,
        guild_id: DiscordGuildID,
        roblox_username: str,
    ) -> VerificationStart:
        """Resolve a Roblox account and issue a secure, expiring profile code."""
        roblox_user = await self._roblox.get_user_by_username(roblox_username)
        linked_user = await self._verifications.get_verified_by_roblox(roblox_user.user_id)
        if linked_user is not None and linked_user.discord_user_id != discord_user_id:
            raise VerificationAlreadyLinked(
                "This Roblox account is already linked to another Discord user."
            )

        pending = await self._verifications.create_pending(
            code=_new_code(),
            discord_user_id=discord_user_id,
            guild_id=guild_id,
            roblox_user_id=roblox_user.user_id,
            expires_at=datetime.now(UTC) + VERIFICATION_LIFETIME,
        )
        self._log.info(
            "Started verification for Discord user %s and Roblox user %s.",
            discord_user_id,
            roblox_user.user_id,
        )
        return VerificationStart(pending=pending, roblox_user=roblox_user)

    async def complete(
        self,
        code: VerificationCode,
        *,
        actor_discord_user_id: DiscordUserID,
    ) -> VerificationComplete:
        """Validate profile proof and atomically create the permanent account link."""
        pending = await self._verifications.get_pending(code)
        if pending is None or pending.status is not VerificationStatus.PENDING:
            raise VerificationNotFound()
        if pending.discord_user_id != actor_discord_user_id:
            # A code is a proof for one Discord account, never a transferable
            # token. Do not reveal who owns it to another member.
            raise VerificationNotFound()
        if pending.expires_at <= datetime.now(UTC):
            await self._verifications.expire_pending(code)
            raise VerificationExpired()
        if pending.roblox_user_id is None:
            raise VerificationError("The pending verification has no Roblox user.")

        roblox_user = await self._roblox.get_user(pending.roblox_user_id)
        if not await self._roblox.profile_contains_code(roblox_user.user_id, code):
            raise VerificationProofNotFound()

        linked_user = await self._verifications.get_verified_by_roblox(roblox_user.user_id)
        if linked_user is not None and linked_user.discord_user_id != pending.discord_user_id:
            raise VerificationAlreadyLinked(
                "This Roblox account is already linked to another Discord user."
            )

        verified_user = await self._verifications.complete_and_save_verified(
            code=code,
            discord_user_id=pending.discord_user_id,
            roblox_user_id=roblox_user.user_id,
            roblox_username=roblox_user.username,
            roblox_display_name=roblox_user.display_name,
        )
        if verified_user is None:
            # A simultaneous request consumed or expired the code after the proof check.
            raise VerificationNotFound()

        await self._audit.record(
            guild_id=pending.guild_id,
            action="member_verified",
            target_discord_user_id=pending.discord_user_id,
            target_roblox_user_id=roblox_user.user_id,
            details=f"Roblox username={roblox_user.username}",
        )
        self._log.info(
            "Completed verification for Discord user %s and Roblox user %s.",
            pending.discord_user_id,
            roblox_user.user_id,
        )
        return VerificationComplete(verified_user=verified_user, guild_id=pending.guild_id)

    async def cancel(self, code: VerificationCode, *, actor_discord_user_id: DiscordUserID) -> bool:
        """Cancel a still-pending verification code at the member's request."""
        pending = await self._verifications.get_pending(code)
        if pending is None or pending.discord_user_id != actor_discord_user_id:
            return False
        result = await self._verifications.cancel_pending(code)
        if result:
            await self._audit.record(
                guild_id=pending.guild_id,
                action="verification_cancelled",
                actor_discord_user_id=actor_discord_user_id,
                target_discord_user_id=pending.discord_user_id,
                target_roblox_user_id=pending.roblox_user_id,
            )
        return result


def _new_code() -> VerificationCode:
    """Create a short displayable code with 80 bits of unpredictable entropy."""
    return VerificationCode(f"VERIFY-{secrets.token_hex(10).upper()}")
