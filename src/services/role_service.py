"""Discord role and nickname operations for verified members."""

"""It safely syncs only bot-managed roles, preserves unrelated member roles, checks Discord’s role hierarchy, and updates Roblox-based nicknames using templates such as {roblox_username}. Discord.py uses Member.add_roles(), remove_roles(), and edit(nick=...) for those actions. Discord.py reference"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from ..core.exceptions import ServiceError

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


@dataclass(frozen=True, slots=True)
class RoleSyncResult:
    """A summary of changes made during one member role synchronisation."""

    added_role_ids: tuple[int, ...]
    removed_role_ids: tuple[int, ...]

    @property
    def changed(self) -> bool:
        return bool(self.added_role_ids or self.removed_role_ids)


class RoleService:
    """Perform permission-safe Discord role and nickname changes only.

    It never decides a user's Roblox rank or which roles they deserve.  The
    future rank-sync service provides the desired role IDs; this class applies
    them while preserving every unrelated Discord role the member already has.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("verification_bot.roles")

    @classmethod
    async def create(cls, _: Config, __: ServiceContainer) -> RoleService:
        """Factory used by ``ServiceManager`` during startup."""
        return cls()

    async def sync_managed_roles(
        self,
        member: discord.Member,
        *,
        managed_role_ids: Iterable[int],
        desired_role_ids: Iterable[int],
        reason: str,
    ) -> RoleSyncResult:
        """Synchronise only roles the bot is configured to manage.

        Unmanaged roles—such as staff, booster, or game-night roles—are never
        touched.  The bot's highest role must be above every configured role.
        """
        managed_ids = set(managed_role_ids)
        desired_ids = set(desired_role_ids)
        unknown_desired = desired_ids - managed_ids
        if unknown_desired:
            raise ValueError("Desired roles must be included in the managed-role set.")

        role_by_id = {role.id: role for role in member.guild.roles}
        configured_roles = [role_by_id[role_id] for role_id in managed_ids if role_id in role_by_id]
        self._validate_role_permissions(member.guild, configured_roles)

        current_ids = {role.id for role in member.roles}
        roles_to_add = [
            role_by_id[role_id]
            for role_id in desired_ids - current_ids
            if role_id in role_by_id
        ]
        roles_to_remove = [
            role_by_id[role_id]
            for role_id in (managed_ids - desired_ids) & current_ids
            if role_id in role_by_id
        ]

        try:
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=reason, atomic=True)
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason, atomic=True)
        except (discord.Forbidden, discord.HTTPException) as error:
            raise ServiceError("Discord could not update the member's roles.") from error

        self._log.info(
            "Synced roles for member %s in guild %s: +%s, -%s.",
            member.id,
            member.guild.id,
            [role.id for role in roles_to_add],
            [role.id for role in roles_to_remove],
        )
        return RoleSyncResult(
            added_role_ids=tuple(role.id for role in roles_to_add),
            removed_role_ids=tuple(role.id for role in roles_to_remove),
        )

    async def update_nickname(
        self,
        member: discord.Member,
        nickname: str,
        *,
        reason: str,
    ) -> bool:
        """Set a member nickname if needed, respecting Discord's 32-char limit."""
        clean_nickname = nickname.strip()
        if not clean_nickname:
            raise ValueError("A nickname cannot be empty.")
        if len(clean_nickname) > 32:
            clean_nickname = clean_nickname[:32].rstrip()
        if member.nick == clean_nickname:
            return False

        bot_member = member.guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_nicknames:
            raise ServiceError("The bot lacks the Manage Nicknames permission.")
        if member.id != bot_member.id and member.top_role >= bot_member.top_role:
            raise ServiceError("The bot's role must be above this member's highest role.")

        try:
            await member.edit(nick=clean_nickname, reason=reason)
        except (discord.Forbidden, discord.HTTPException) as error:
            raise ServiceError("Discord could not update the member's nickname.") from error
        self._log.info("Updated nickname for member %s in guild %s.", member.id, member.guild.id)
        return True

    @staticmethod
    def format_nickname(
        template: str,
        *,
        roblox_username: str,
        roblox_display_name: str,
        roblox_user_id: int,
        group_rank: int | None = None,
        group_role_name: str | None = None,
    ) -> str:
        """Render a configured nickname using a small, predictable placeholder set.

        Supported placeholders: ``{roblox_username}``, ``{roblox_display_name}``,
        ``{roblox_user_id}``, ``{group_rank}``, and ``{group_role_name}``.
        """
        try:
            nickname = template.format(
                roblox_username=roblox_username,
                roblox_display_name=roblox_display_name,
                roblox_user_id=roblox_user_id,
                group_rank=group_rank if group_rank is not None else "",
                group_role_name=group_role_name or "",
            )
        except (KeyError, ValueError) as error:
            raise ValueError("Nickname template contains an unsupported placeholder.") from error
        if not nickname.strip():
            raise ValueError("Nickname template produced an empty nickname.")
        return nickname.strip()[:32].rstrip()

    @staticmethod
    def _validate_role_permissions(guild: discord.Guild, roles: list[discord.Role]) -> None:
        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            raise ServiceError("The bot lacks the Manage Roles permission.")
        blocked_roles = [
            role.name
            for role in roles
            if role.is_default() or role.managed or role >= bot_member.top_role
        ]
        if blocked_roles:
            raise ServiceError(
                "The bot cannot manage these configured roles: " + ", ".join(blocked_roles)
            )