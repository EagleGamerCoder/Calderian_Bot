"""Synchronise verified members' Roblox group ranks to Discord roles."""

"""It performs the full Roblox-group sync: finds a verified user, gets their group rank, selects the highest-priority matching Discord role rules, removes outdated bot-managed roles, updates their nickname, and writes an audit entry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import discord

from ..core.types import DiscordUserID, RobloxRank
from ..database.models import GroupRankRule
from ..database.repositories.audit_repository import AuditRepository
from ..database.repositories.guild_repository import GuildRepository
from ..database.repositories.verification_repository import VerificationRepository
from .roblox_service import RobloxGroupMembership, RobloxService
from .role_service import RoleService, RoleSyncResult

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


class SyncStatus(str, Enum):
    """Why a requested member synchronisation did or did not run."""

    COMPLETED = "completed"
    NOT_VERIFIED = "not_verified"
    NOT_CONFIGURED = "not_configured"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class MemberSyncResult:
    """A concise outcome suitable for a `/sync` response or audit trail."""

    status: SyncStatus
    role_result: RoleSyncResult | None = None
    nickname_changed: bool = False
    group_rank: RobloxRank | None = None
    group_role_name: str | None = None


class RankSyncService:
    """Apply a guild's Roblox-group role rules to one verified Discord member."""

    def __init__(
        self,
        verification_repository: VerificationRepository,
        guild_repository: GuildRepository,
        audit_repository: AuditRepository,
        roblox_service: RobloxService,
        role_service: RoleService,
        logger: logging.Logger | None = None,
    ) -> None:
        self._verifications = verification_repository
        self._guilds = guild_repository
        self._audit = audit_repository
        self._roblox = roblox_service
        self._roles = role_service
        self._log = logger or logging.getLogger("verification_bot.rank_sync")

    @classmethod
    async def create(cls, _: Config, services: ServiceContainer) -> RankSyncService:
        """Factory used by ``ServiceManager`` after dependent services exist."""
        return cls(
            verification_repository=services.require("verification_repository"),
            guild_repository=services.require("guild_repository"),
            audit_repository=services.require("audit_repository"),
            roblox_service=services.require("roblox"),
            role_service=services.require("roles"),
        )

    async def sync_member(
        self,
        member: discord.Member,
        *,
        actor_discord_user_id: DiscordUserID | None = None,
        reason: str = "Roblox verification rank synchronisation",
    ) -> MemberSyncResult:
        """Synchronise verified and Roblox-group roles for one guild member."""
        guild_id = member.guild.id
        config = await self._guilds.get_config(guild_id)
        if config is None:
            return MemberSyncResult(SyncStatus.NOT_CONFIGURED)
        if not config.rank_sync_enabled:
            return MemberSyncResult(SyncStatus.DISABLED)

        verified_user = await self._verifications.get_verified_by_discord(member.id)
        if verified_user is None:
            return MemberSyncResult(SyncStatus.NOT_VERIFIED)

        group_membership: RobloxGroupMembership | None = None
        rules: list[GroupRankRule] = []
        if config.roblox_group_id is not None:
            group_membership = await self._roblox.get_group_membership(
                verified_user.roblox_user_id,
                config.roblox_group_id,
            )
            rules = await self._guilds.get_rank_rules(config.guild_id, config.roblox_group_id)

        managed_role_ids = {rule.discord_role_id for rule in rules}
        desired_role_ids: set[int] = set()
        if config.verified_role_id is not None:
            managed_role_ids.add(config.verified_role_id)
            desired_role_ids.add(config.verified_role_id)
        if config.unverified_role_id is not None:
            managed_role_ids.add(config.unverified_role_id)

        if group_membership is not None:
            desired_role_ids.update(_desired_roles(rules, group_membership.rank))

        role_result = await self._roles.sync_managed_roles(
            member,
            managed_role_ids=managed_role_ids,
            desired_role_ids=desired_role_ids,
            reason=reason,
        )

        nickname = self._roles.format_nickname(
            config.nickname_template,
            roblox_username=verified_user.roblox_username,
            roblox_display_name=verified_user.roblox_display_name,
            roblox_user_id=verified_user.roblox_user_id,
            group_rank=group_membership.rank if group_membership else None,
            group_role_name=group_membership.role_name if group_membership else None,
        )
        nickname_changed = await self._roles.update_nickname(member, nickname, reason=reason)

        await self._audit.record(
            guild_id=guild_id,
            action="member_rank_synced",
            actor_discord_user_id=actor_discord_user_id,
            target_discord_user_id=member.id,
            target_roblox_user_id=verified_user.roblox_user_id,
            details=(
                f"roles_added={list(role_result.added_role_ids)}; "
                f"roles_removed={list(role_result.removed_role_ids)}; "
                f"nickname_changed={nickname_changed}; "
                f"group_rank={group_membership.rank if group_membership else 'none'}"
            ),
        )
        self._log.info("Synced verified member %s in guild %s.", member.id, guild_id)
        return MemberSyncResult(
            status=SyncStatus.COMPLETED,
            role_result=role_result,
            nickname_changed=nickname_changed,
            group_rank=group_membership.rank if group_membership else None,
            group_role_name=group_membership.role_name if group_membership else None,
        )


def _desired_roles(rules: list[GroupRankRule], rank: RobloxRank) -> set[int]:
    """Return all matching roles at the highest configured priority only."""
    matching = [rule for rule in rules if rule.matches(rank)]
    if not matching:
        return set()
    highest_priority = max(rule.priority for rule in matching)
    return {rule.discord_role_id for rule in matching if rule.priority == highest_priority}