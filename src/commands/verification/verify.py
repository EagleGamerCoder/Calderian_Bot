"""The `/verify` slash-command group for Roblox profile verification."""

"""
/verify start <roblox_username>
/verify complete <code>
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...core.client import CalderianBot
from ...core.exceptions import CalderianBotError
from ...core.types import VerificationCode
from ...services.permission_service import PermissionService
from ...services.rank_sync_service import RankSyncService, SyncStatus
from ...services.verification_service import VerificationService


class VerificationCommands(commands.Cog):
    """Start and complete a member's Roblox account verification."""

    verify = app_commands.Group(
        name="verify",
        description="Link your Discord account to Roblox.",
        guild_only=True,
    )

    def __init__(self, bot: CalderianBot) -> None:
        self._bot = bot
        self._permissions: PermissionService = bot.services.require("permissions")
        self._verification: VerificationService = bot.services.require("verification")
        self._rank_sync: RankSyncService = bot.services.require("rank_sync")

    @verify.command(name="start", description="Start verification with your Roblox username.")
    @app_commands.describe(roblox_username="Your exact Roblox username, not display name")
    async def start(
        self,
        interaction: discord.Interaction[CalderianBot],
        roblox_username: str,
    ) -> None:
        """Issue a private profile-description code for the invoking member."""
        member = self._permissions.require_guild_member(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            started = await self._verification.start(
                discord_user_id=member.id,
                guild_id=member.guild.id,
                roblox_username=roblox_username,
            )
        except CalderianBotError as error:
            await interaction.followup.send(error.public_message, ephemeral=True)
            return
        except Exception:
            self._bot.log.exception("Unexpected error while starting verification.")
            await interaction.followup.send(
                "Verification could not be started right now. Please try again shortly.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Verification started", colour=discord.Colour.blurple())
        embed.add_field(name="Roblox account", value=started.roblox_user.username, inline=False)
        embed.add_field(name="Your code", value=f"`{started.pending.code}`", inline=False)
        embed.add_field(
            name="Next step",
            value=(
                "Put this code in the **About** section of your "
                f"[Roblox profile]({started.roblox_user.profile_url}), then run "
                "`/verify complete` with the same code."
            ),
            inline=False,
        )
        embed.set_footer(text="This code expires in 15 minutes and should not be shared.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @verify.command(name="complete", description="Complete verification after adding your code.")
    @app_commands.describe(code="The code shown by /verify start")
    async def complete(
        self,
        interaction: discord.Interaction[CalderianBot],
        code: str,
    ) -> None:
        """Check the profile proof, link the account, then synchronise roles."""
        member = self._permissions.require_guild_member(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            completed = await self._verification.complete(
                VerificationCode(code.strip().upper()),
                actor_discord_user_id=member.id,
            )
        except CalderianBotError as error:
            await interaction.followup.send(error.public_message, ephemeral=True)
            return
        except Exception:
            self._bot.log.exception("Unexpected error while completing verification.")
            await interaction.followup.send(
                "Verification could not be completed right now. Please try again shortly.",
                ephemeral=True,
            )
            return

        sync_note = ""
        try:
            sync_result = await self._rank_sync.sync_member(member, reason="Member completed Roblox verification")
            if sync_result.status is SyncStatus.COMPLETED:
                sync_note = " Your configured roles and nickname were synchronised."
            elif sync_result.status is SyncStatus.DISABLED:
                sync_note = " Verification succeeded; automatic rank sync is disabled here."
        except CalderianBotError:
            # The account is already safely linked. Configuration or hierarchy
            # mistakes must not make the member think verification failed.
            self._bot.log.exception("Verification succeeded but member sync failed.")
            sync_note = " Your account is linked, but staff need to check role or nickname setup."

        await interaction.followup.send(
            f"Verified as **{completed.verified_user.roblox_username}**.{sync_note}",
            ephemeral=True,
        )


async def setup(bot: CalderianBot) -> None:
    """Discord.py extension entry point used by CommandManager."""
    await bot.add_cog(VerificationCommands(bot))
