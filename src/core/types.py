"""Shared type aliases for identifiers used across the application."""

from __future__ import annotations

from typing import NewType, TypeAlias


# ``NewType`` has no runtime cost, but type checkers can distinguish IDs that
# are all represented as integers in Discord and Roblox APIs.
DiscordUserID = NewType("DiscordUserID", int)
DiscordGuildID = NewType("DiscordGuildID", int)
DiscordRoleID = NewType("DiscordRoleID", int)
DiscordChannelID = NewType("DiscordChannelID", int)
DiscordMessageID = NewType("DiscordMessageID", int)
RobloxUserID = NewType("RobloxUserID", int)
RobloxGroupID = NewType("RobloxGroupID", int)

VerificationCode = NewType("VerificationCode", str)
VerificationSessionID = NewType("VerificationSessionID", str)

# Helpful when a public method intentionally accepts any Discord snowflake.
SnowflakeID: TypeAlias = int
