"""Typed data models shared by repositories and business services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..core.types import (
    DiscordChannelID,
    DiscordGuildID,
    DiscordRoleID,
    DiscordUserID,
    RobloxGroupID,
    RobloxRank,
    RobloxUserID,
    VerificationCode,
)


class VerificationStatus(str, Enum):
    """The current state of a short-lived verification request."""

    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class VerifiedUser:
    """A permanent Discord-to-Roblox link created after successful verification."""

    discord_user_id: DiscordUserID
    roblox_user_id: RobloxUserID
    roblox_username: str
    roblox_display_name: str
    verified_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PendingVerification:
    """A one-time code awaiting proof on a Roblox profile."""

    code: VerificationCode
    discord_user_id: DiscordUserID
    guild_id: DiscordGuildID
    created_at: datetime
    expires_at: datetime
    roblox_user_id: RobloxUserID | None = None
    status: VerificationStatus = VerificationStatus.PENDING


@dataclass(frozen=True, slots=True)
class GuildConfig:
    """Per-server settings that control verification and synchronisation."""

    guild_id: DiscordGuildID
    verified_role_id: DiscordRoleID | None
    unverified_role_id: DiscordRoleID | None
    log_channel_id: DiscordChannelID | None
    roblox_group_id: RobloxGroupID | None
    nickname_template: str
    rank_sync_enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GroupRankRule:
    """Map a range of Roblox group ranks to one Discord role.

    Example: ranks 50–255 may map to an ``Officer`` Discord role.  Rules are
    evaluated by priority, which makes special exceptions possible later.
    """

    guild_id: DiscordGuildID
    roblox_group_id: RobloxGroupID
    discord_role_id: DiscordRoleID
    minimum_rank: RobloxRank
    maximum_rank: RobloxRank
    priority: int = 0

    def matches(self, rank: RobloxRank) -> bool:
        """Return whether this rule applies to a Roblox group rank."""
        return self.minimum_rank <= rank <= self.maximum_rank


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A server-scoped audit record for important bot actions."""

    guild_id: DiscordGuildID
    action: str
    occurred_at: datetime
    actor_discord_user_id: DiscordUserID | None = None
    target_discord_user_id: DiscordUserID | None = None
    target_roblox_user_id: RobloxUserID | None = None
    details: str | None = None
