"""Centralised authorisation rules for server and staff bot actions."""

"""It lets everyone verify and sync themselves, while restricting server configuration, Roblox-group role rules, and syncing other members to people with Manage Server or Administrator. It also rejects server-only commands used in DMs. Discord.py permissions guidance"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ..core.exceptions import PermissionDenied

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


class PermissionService:
    """Apply the bot's internal permission policy consistently.

    Discord's slash-command default permissions are only a client-side hint;
    every sensitive command must still call this service before changing config,
    rank rules, or another member's roles.
    """

    @classmethod
    async def create(cls, _: Config, __: ServiceContainer) -> PermissionService:
        """Factory used by ``ServiceManager`` during startup."""
        return cls()

    @staticmethod
    def can_configure(member: discord.Member) -> bool:
        """Whether a member can alter server-wide bot settings."""
        permissions = member.guild_permissions
        return permissions.administrator or permissions.manage_guild

    @staticmethod
    def can_manage_rank_rules(member: discord.Member) -> bool:
        """Whether a member can change Roblox group/rank role mappings."""
        return PermissionService.can_configure(member)

    @staticmethod
    def can_sync(member: discord.Member, target: discord.Member) -> bool:
        """Allow self-sync for everyone; staff may synchronise other members."""
        return member.id == target.id or PermissionService.can_configure(member)

    @staticmethod
    def require_configuration_access(member: discord.Member) -> None:
        """Raise a safe error if a member cannot modify server configuration."""
        if not PermissionService.can_configure(member):
            raise PermissionDenied(
                "Manage Server permission is required to configure this bot."
            )

    @staticmethod
    def require_rank_rule_access(member: discord.Member) -> None:
        """Raise a safe error if a member cannot edit group rank rules."""
        if not PermissionService.can_manage_rank_rules(member):
            raise PermissionDenied(
                "Manage Server permission is required to edit rank rules."
            )

    @staticmethod
    def require_sync_access(actor: discord.Member, target: discord.Member) -> None:
        """Raise a safe error if a member attempts to sync somebody else."""
        if not PermissionService.can_sync(actor, target):
            raise PermissionDenied("You can only synchronise your own account.")

    @staticmethod
    def require_guild_member(interaction: discord.Interaction[object]) -> discord.Member:
        """Return the invoking member or reject commands used outside a server."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            raise PermissionDenied("This command can only be used in a Discord server.")
        return interaction.user
