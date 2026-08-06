"""Business logic and API access for Roblox users and groups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from ..core.types import RobloxGroupID, RobloxRank, RobloxUserID


ROBLOX_API_BASE = "https://users.roblox.com"
ROBLOX_GROUPS_API_BASE = "https://groups.roblox.com"


@dataclass(frozen=True, slots=True)
class RobloxUser:
    """Basic Roblox account information."""

    user_id: RobloxUserID
    username: str
    display_name: str


@dataclass(frozen=True, slots=True)
class RobloxGroupMembership:
    """A Roblox user's membership and rank within a group."""

    group_id: RobloxGroupID
    user_id: RobloxUserID
    rank: RobloxRank
    role_name: str


class RobloxAPIError(RuntimeError):
    """Raised when a Roblox API request fails."""


class RobloxNotFoundError(RobloxAPIError):
    """Raised when a requested Roblox resource does not exist."""


class RobloxService:
    """Access Roblox users and group membership information."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._session = session
        self._owns_session = session is None

    async def start(self) -> None:
        """Create the HTTP session if this service owns it."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "CalderiaVerificationBot/1.0",
                    "Accept": "application/json",
                }
            )

    async def close(self) -> None:
        """Close the HTTP session if this service owns it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def get_user(
        self,
        user_id: RobloxUserID,
    ) -> RobloxUser:
        """Retrieve a Roblox user by their user ID."""
        data = await self._request(
            f"{ROBLOX_API_BASE}/v1/users/{int(user_id)}",
        )

        return RobloxUser(
            user_id=RobloxUserID(data["id"]),
            username=data["name"],
            display_name=data["displayName"],
        )

    async def get_user_by_username(
        self,
        username: str,
    ) -> RobloxUser | None:
        """Find a Roblox user by their username."""
        username = username.strip()

        if not username:
            raise ValueError("username cannot be empty.")

        data = await self._request(
            f"{ROBLOX_API_BASE}/v1/usernames/users",
            method="POST",
            json={
                "usernames": [username],
                "excludeBannedUsers": False,
            },
        )

        users = data.get("data", [])

        if not users:
            return None

        user = users[0]

        return RobloxUser(
            user_id=RobloxUserID(user["id"]),
            username=user["name"],
            display_name=user["displayName"],
        )

    async def get_group_membership(
        self,
        user_id: RobloxUserID,
        group_id: RobloxGroupID,
    ) -> RobloxGroupMembership | None:
        """
        Return a user's membership in a Roblox group.

        Returns None when the user is not a member of the group.
        """
        data = await self._request(
            f"{ROBLOX_GROUPS_API_BASE}/v2/users/{int(user_id)}/groups/roles",
        )

        for membership in data.get("data", []):
            group = membership.get("group", {})
            role = membership.get("role", {})

            if int(group.get("id", 0)) != int(group_id):
                continue

            return RobloxGroupMembership(
                group_id=RobloxGroupID(group["id"]),
                user_id=user_id,
                rank=RobloxRank(role["rank"]),
                role_name=role["name"],
            )

        return None

    async def get_user_rank(
        self,
        user_id: RobloxUserID,
        group_id: RobloxGroupID,
    ) -> RobloxRank | None:
        """Return a user's rank within a Roblox group."""
        membership = await self.get_group_membership(
            user_id,
            group_id,
        )

        return membership.rank if membership else None

    async def verify_group_membership(
        self,
        user_id: RobloxUserID,
        group_id: RobloxGroupID,
    ) -> bool:
        """Return whether a Roblox user belongs to a group."""
        return (
            await self.get_group_membership(
                user_id,
                group_id,
            )
        ) is not None

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a Roblox API request and validate the response."""
        if self._session is None:
            await self.start()

        assert self._session is not None

        try:
            async with self._session.request(
                method,
                url,
                json=json,
            ) as response:
                if response.status == 404:
                    raise RobloxNotFoundError(
                        f"Roblox resource was not found: {url}"
                    )

                if response.status == 429:
                    raise RobloxAPIError(
                        "Roblox API rate limit reached."
                    )

                if response.status >= 500:
                    raise RobloxAPIError(
                        f"Roblox API server error: HTTP {response.status}."
                    )

                if response.status >= 400:
                    body = await response.text()

                    raise RobloxAPIError(
                        f"Roblox API request failed: "
                        f"HTTP {response.status}: {body}"
                    )

                data = await response.json()

                if not isinstance(data, dict):
                    raise RobloxAPIError(
                        "Roblox API returned an unexpected response."
                    )

                return data

        except aiohttp.ClientError as exc:
            raise RobloxAPIError(
                "Failed to communicate with the Roblox API."
            ) from exc