"""Staff `/setup` commands for configuring verification and rank synchronisation."""

"""
/setup show — shows the current server configuration.
/setup configure — staff set the Roblox group, verified/unverified roles, log channel, nickname format, and rank-sync setting.
"""

from __future__ import annotations

from dataclasses import replace

import discord
from discord import app_commands
from discord.ext import commands

from ...core.client import VerificationBot
from ...core.exceptions import VerificationBotError
from ...core.types import RobloxGroupID
from ...services.guild_service import GuildService
from ...services.permission_service import PermissionService


class SetupCommands(commands.Cog):
    """View and configure a server's Roblox verification settings."""

    setup_group = app_commands.Group(
        name="setup",
        description="Configure Roblox verification for this server.",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: VerificationBot) -> None:
        self._bot = bot
        self._permissions: PermissionService = bot.services.require("permissions")
        self._guilds: GuildService = bot.services.require("guilds")

    @setup_group.command(name="show", description="Show the current verification setup.")
    async def show(self, interaction: discord.Interaction[VerificationBot]) -> None:
        """Display non-secret server configuration to any server member."""
        member = self._permissions.require_guild_member(interaction)
        config = await self._guilds.get_or_create_config(member.guild.id)
        embed = discord.Embed(title="Verification setup", colour=discord.Colour.blurple())
        embed.add_field(
            name="Roblox group",
            value=str(config.roblox_group_id) if config.roblox_group_id else "Not configured",
        )
        embed.add_field(name="Rank sync", value="Enabled" if config.rank_sync_enabled else "Disabled")
        embed.add_field(
            name="Verified role",
            value=f"<@&{config.verified_role_id}>" if config.verified_role_id else "Not configured",
        )
        embed.add_field(
            name="Unverified role",
            value=f"<@&{config.unverified_role_id}>" if config.unverified_role_id else "Not configured",
        )
        embed.add_field(
            name="Log channel",
            value=f"<#{config.log_channel_id}>" if config.log_channel_id else "Not configured",
        )
        embed.add_field(name="Nickname format", value=f"`{config.nickname_template}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @setup_group.command(name="configure", description="Set the main verification and rank-sync settings.")
    @app_commands.describe(
        roblox_group_id="The numeric ID of the Roblox group to use",
        verified_role="Role granted to verified members",
        unverified_role="Optional role removed after verification",
        log_channel="Optional channel for future public audit messages",
        nickname_template="Example: {roblox_username} | {group_role_name}",
        enable_rank_sync="Whether /sync applies Roblox group-rank roles",
    )
    async def configure(
        self,
        interaction: discord.Interaction[VerificationBot],
        roblox_group_id: int,
        verified_role: discord.Role | None = None,
        unverified_role: discord.Role | None = None,
        log_channel: discord.TextChannel | None = None,
        nickname_template: str = "{roblox_username}",
        enable_rank_sync: bool = True,
    ) -> None:
        """Save the baseline settings needed before members can use `/sync`."""
        member = self._permissions.require_guild_member(interaction)
        try:
            self._permissions.require_configuration_access(member)
            if roblox_group_id <= 0:
                raise ValueError("Roblox group ID must be a positive number.")
            _validate_setup_roles(member.guild, verified_role, unverified_role)
            current = await self._guilds.get_or_create_config(member.guild.id)
            saved = await self._guilds.save_config(
                replace(
                    current,
                    verified_role_id=verified_role.id if verified_role else None,
                    unverified_role_id=unverified_role.id if unverified_role else None,
                    log_channel_id=log_channel.id if log_channel else None,
                    roblox_group_id=RobloxGroupID(roblox_group_id),
                    nickname_template=nickname_template,
                    rank_sync_enabled=enable_rank_sync,
                ),
                actor_discord_user_id=member.id,
            )
        except (VerificationBotError, ValueError) as error:
            message = error.public_message if isinstance(error, VerificationBotError) else str(error)
            await interaction.response.send_message(message, ephemeral=True)
            return
        except Exception:
            self._bot.log.exception("Unexpected error while saving server setup.")
            await interaction.response.send_message(
                "Setup could not be saved right now. Please try again shortly.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Setup saved for Roblox group `{saved.roblox_group_id}`. "
            f"Rank sync is {'enabled' if saved.rank_sync_enabled else 'disabled'}.",
            ephemeral=True,
        )


def _validate_setup_roles(
    guild: discord.Guild,
    verified_role: discord.Role | None,
    unverified_role: discord.Role | None,
) -> None:
    """Catch role hierarchy mistakes before they are saved into setup."""
    bot_member = guild.me
    if bot_member is None:
        raise ValueError("The bot is not ready in this server yet.")
    for role in (verified_role, unverified_role):
        if role is None:
            continue
        if role.is_default() or role.managed:
            raise ValueError("Choose a normal server role, not @everyone or an integration role.")
        if role >= bot_member.top_role:
            raise ValueError("The bot's role must be above every selected verification role.")


async def setup(bot: VerificationBot) -> None:
    """Discord.py extension entry point used by CommandManager."""
    await bot.add_cog(SetupCommands(bot))
