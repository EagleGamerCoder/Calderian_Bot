"""The `/sync` slash command for Roblox rank, role, and nickname refreshes."""

"""
/sync
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...core.client import VerificationBot
from ...core.exceptions import VerificationBotError
from ...services.permission_service import PermissionService
from ...services.rank_sync_service import MemberSyncResult, RankSyncService, SyncStatus


class SyncCommands(commands.Cog):
    """Let members refresh their own sync and staff refresh other members."""

    def __init__(self, bot: VerificationBot) -> None:
        self._bot = bot
        self._permissions: PermissionService = bot.services.require("permissions")
        self._rank_sync: RankSyncService = bot.services.require("rank_sync")

    @app_commands.command(name="sync", description="Refresh your Roblox rank, Discord roles, and nickname.")
    @app_commands.guild_only()
    @app_commands.describe(member="Optional: a member to sync (staff only)")
    async def sync(
        self,
        interaction: discord.Interaction[VerificationBot],
        member: discord.Member | None = None,
    ) -> None:
        """Run a safe, current Roblox-group synchronisation."""
        actor = self._permissions.require_guild_member(interaction)
        target = member or actor
        try:
            self._permissions.require_sync_access(actor, target)
        except VerificationBotError as error:
            await interaction.response.send_message(error.public_message, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self._rank_sync.sync_member(
                target,
                actor_discord_user_id=actor.id if actor.id != target.id else None,
                reason=f"Roblox sync requested by {actor}",
            )
        except VerificationBotError as error:
            await interaction.followup.send(error.public_message, ephemeral=True)
            return
        except Exception:
            self._bot.log.exception("Unexpected error while synchronising a member.")
            await interaction.followup.send(
                "The synchronisation could not be completed right now. Please try again shortly.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(_message_for(result, target), ephemeral=True)


def _message_for(result: MemberSyncResult, member: discord.Member) -> str:
    """Turn a service outcome into a concise, user-facing private response."""
    if result.status is SyncStatus.NOT_VERIFIED:
        return "You need to verify first with `/verify start`."
    if result.status is SyncStatus.NOT_CONFIGURED:
        return "This server has not configured Roblox verification yet."
    if result.status is SyncStatus.DISABLED:
        return "Rank synchronisation is disabled in this server."

    assert result.role_result is not None
    changes: list[str] = []
    if result.role_result.added_role_ids:
        changes.append(f"added {len(result.role_result.added_role_ids)} role(s)")
    if result.role_result.removed_role_ids:
        changes.append(f"removed {len(result.role_result.removed_role_ids)} role(s)")
    if result.nickname_changed:
        changes.append("updated nickname")
    change_text = ", ".join(changes) if changes else "no changes were needed"
    rank_text = str(result.group_rank) if result.group_rank is not None else "no configured group rank"
    return f"Synced **{member.display_name}** — {change_text}. Current rank: {rank_text}."


async def setup(bot: VerificationBot) -> None:
    """Discord.py extension entry point used by CommandManager."""
    await bot.add_cog(SyncCommands(bot))
