"""Staff `/rankrule` commands for Roblox-rank-to-Discord-role mappings."""

"""
/rankrule list
/rankrule add
/rankrule remove
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ...core.client import VerificationBot
from ...core.exceptions import VerificationBotError
from ...core.types import DiscordRoleID, RobloxRank
from ...database.models import GroupRankRule
from ...services.guild_service import GuildService
from ...services.permission_service import PermissionService


class RankRuleCommands(commands.Cog):
    """Add, remove, and display group-rank role mappings for staff."""

    rankrule = app_commands.Group(
        name="rankrule",
        description="Manage Roblox rank-to-Discord-role rules.",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: VerificationBot) -> None:
        self._bot = bot
        self._permissions: PermissionService = bot.services.require("permissions")
        self._guilds: GuildService = bot.services.require("guilds")

    @rankrule.command(name="list", description="Show this server's Roblox rank rules.")
    async def list_rules(self, interaction: discord.Interaction[VerificationBot]) -> None:
        """Display mappings in the priority order used by member synchronisation."""
        member = self._permissions.require_guild_member(interaction)
        try:
            config = await self._guilds.get_or_create_config(member.guild.id)
            if config.roblox_group_id is None:
                raise ValueError("Configure a Roblox group first with `/setup configure`.")
            rules = await self._guilds.get_rank_rules(config.guild_id, config.roblox_group_id)
        except (VerificationBotError, ValueError) as error:
            message = error.public_message if isinstance(error, VerificationBotError) else str(error)
            await interaction.response.send_message(message, ephemeral=True)
            return

        if not rules:
            await interaction.response.send_message(
                "No rank rules are configured yet. Use `/rankrule add` to create one.",
                ephemeral=True,
            )
            return

        lines = [
            f"`{rule.minimum_rank}-{rule.maximum_rank}` → <@&{rule.discord_role_id}> "
            f"(priority `{rule.priority}`)"
            for rule in rules
        ]
        embed = discord.Embed(title="Roblox rank rules", colour=discord.Colour.blurple())
        embed.description = "\n".join(lines[:25])
        if len(lines) > 25:
            embed.set_footer(text=f"Showing 25 of {len(lines)} rules")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rankrule.command(name="add", description="Map a Roblox rank range to a Discord role.")
    @app_commands.describe(
        minimum_rank="Lowest Roblox group rank, from 0 to 255",
        maximum_rank="Highest Roblox group rank, from 0 to 255",
        role="Discord role the bot should apply",
        priority="Higher values win if ranges overlap",
    )
    async def add_rule(
        self,
        interaction: discord.Interaction[VerificationBot],
        minimum_rank: int,
        maximum_rank: int,
        role: discord.Role,
        priority: int = 0,
    ) -> None:
        """Append a rank mapping while preserving existing mappings."""
        member = self._permissions.require_guild_member(interaction)
        try:
            self._permissions.require_rank_rule_access(member)
            _validate_manageable_role(member.guild, role)
            config = await self._guilds.get_or_create_config(member.guild.id)
            if config.roblox_group_id is None:
                raise ValueError("Configure a Roblox group first with `/setup configure`.")
            existing = await self._guilds.get_rank_rules(config.guild_id, config.roblox_group_id)
            new_rule = GroupRankRule(
                guild_id=config.guild_id,
                roblox_group_id=config.roblox_group_id,
                discord_role_id=DiscordRoleID(role.id),
                minimum_rank=RobloxRank(minimum_rank),
                maximum_rank=RobloxRank(maximum_rank),
                priority=priority,
            )
            await self._guilds.replace_rank_rules(
                config.guild_id,
                config.roblox_group_id,
                [*existing, new_rule],
                actor_discord_user_id=member.id,
            )
        except (VerificationBotError, ValueError) as error:
            message = error.public_message if isinstance(error, VerificationBotError) else str(error)
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.send_message(
            f"Added rule: ranks `{minimum_rank}-{maximum_rank}` → {role.mention} "
            f"with priority `{priority}`.",
            ephemeral=True,
        )

    @rankrule.command(name="remove", description="Remove an exact Roblox rank-to-role mapping.")
    @app_commands.describe(
        minimum_rank="The rule's lowest rank",
        maximum_rank="The rule's highest rank",
        role="The role in the rule",
        priority="The rule's priority",
    )
    async def remove_rule(
        self,
        interaction: discord.Interaction[VerificationBot],
        minimum_rank: int,
        maximum_rank: int,
        role: discord.Role,
        priority: int = 0,
    ) -> None:
        """Remove one exact mapping so staff cannot delete a different rule by accident."""
        member = self._permissions.require_guild_member(interaction)
        try:
            self._permissions.require_rank_rule_access(member)
            config = await self._guilds.get_or_create_config(member.guild.id)
            if config.roblox_group_id is None:
                raise ValueError("Configure a Roblox group first with `/setup configure`.")
            existing = await self._guilds.get_rank_rules(config.guild_id, config.roblox_group_id)
            remaining = [
                rule
                for rule in existing
                if not (
                    rule.minimum_rank == minimum_rank
                    and rule.maximum_rank == maximum_rank
                    and rule.discord_role_id == role.id
                    and rule.priority == priority
                )
            ]
            if len(remaining) == len(existing):
                raise ValueError("No matching rank rule was found.")
            await self._guilds.replace_rank_rules(
                config.guild_id,
                config.roblox_group_id,
                remaining,
                actor_discord_user_id=member.id,
            )
        except (VerificationBotError, ValueError) as error:
            message = error.public_message if isinstance(error, VerificationBotError) else str(error)
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.send_message("Rank rule removed.", ephemeral=True)


def _validate_manageable_role(guild: discord.Guild, role: discord.Role) -> None:
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        raise ValueError("The bot needs the Manage Roles permission before rules can be added.")
    if role.is_default() or role.managed or role >= bot_member.top_role:
        raise ValueError("Choose a normal role positioned below the bot's role.")


async def setup(bot: VerificationBot) -> None:
    """Discord.py extension entry point used by CommandManager."""
    await bot.add_cog(RankRuleCommands(bot))
