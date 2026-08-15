"""Read-only Roblox profile and group-membership integration."""

"""It securely handles public Roblox profile lookups, username lookup, profile-code verification, group memberships, and group-rank checks—without requiring or storing a .ROBLOSECURITY cookie. Roblox documents the public profile, username, and group-role endpoints this uses. Roblox API reference"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from ..core.exceptions import RobloxRequestFailed, RobloxUserNotFound
from ..core.types import RobloxGroupID, RobloxRank, RobloxUserID

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


USERS_API = "https://users.roblox.com"
GROUPS_API = "https://groups.roblox.com"


@dataclass(frozen=True, slots=True)
class RobloxUser:
    """Public Roblox profile data used for verification and Discord display."""

    user_id: RobloxUserID
    username: str
    display_name: str
    description: str
    created_at: datetime | None
    is_banned: bool

    @property
    def profile_url(self) -> str:
        return f"https://www.roblox.com/users/{self.user_id}/profile"


@dataclass(frozen=True, slots=True)
class RobloxGroupMembership:
    """One Roblox group role held by a user."""

    group_id: RobloxGroupID
    group_name: str
    role_name: str
    rank: RobloxRank


class RobloxService:
    """Read public Roblox data without storing a dangerous account cookie.

    This service intentionally does not rank people in Roblox groups.  That is
    a privileged action that should later use Roblox Open Cloud/OAuth with a
    narrowly scoped credential, never a browser .ROBLOSECURITY cookie.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("verification_bot.roblox")
        self._client: httpx.AsyncClient | None = None

    @classmethod
    async def create(cls, _: Config, __: ServiceContainer) -> RobloxService:
        """Factory used by ``ServiceManager`` during application startup."""
        return cls()

    async def start(self) -> None:
        """Create the shared HTTP client once."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                follow_redirects=False,
                headers={"User-Agent": "RobloxVerificationBot/1.0"},
            )

    async def close(self) -> None:
        """Release persistent HTTP connections on bot shutdown."""
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def get_user(self, user_id: RobloxUserID) -> RobloxUser:
        """Fetch public profile data for a global Roblox user ID."""
        response = await self._request("GET", f"{USERS_API}/v1/users/{user_id}")
        if response.status_code == 404:
            raise RobloxUserNotFound()
        payload = self._decode_json(response)
        return _to_roblox_user(payload)

    async def get_user_by_username(self, username: str) -> RobloxUser:
        """Resolve an exact Roblox username, then fetch the user's profile."""
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("A Roblox username is required.")

        response = await self._request(
            "POST",
            f"{USERS_API}/v1/usernames/users",
            json={"usernames": [clean_username], "excludeBannedUsers": True},
        )
        payload = self._decode_json(response)
        users = payload.get("data")
        if not isinstance(users, list) or not users:
            raise RobloxUserNotFound()
        user_id = users[0].get("id")
        if not isinstance(user_id, int):
            raise RobloxRequestFailed("Roblox returned an invalid username response.")
        return await self.get_user(RobloxUserID(user_id))

    async def get_group_memberships(
        self,
        user_id: RobloxUserID,
    ) -> list[RobloxGroupMembership]:
        """Return the public Roblox group roles held by a user."""
        response = await self._request(
            "GET",
            f"{GROUPS_API}/v1/users/{user_id}/groups/roles",
        )
        if response.status_code == 404:
            raise RobloxUserNotFound()
        payload = self._decode_json(response)
        memberships = payload.get("data")
        if not isinstance(memberships, list):
            raise RobloxRequestFailed("Roblox returned invalid group-role data.")
        return [_to_group_membership(item) for item in memberships]

    async def get_group_membership(
        self,
        user_id: RobloxUserID,
        group_id: RobloxGroupID,
    ) -> RobloxGroupMembership | None:
        """Return one group's role for a user, or ``None`` if they are not in it."""
        memberships = await self.get_group_memberships(user_id)
        return next((item for item in memberships if item.group_id == group_id), None)

    async def get_group_rank(
        self,
        user_id: RobloxUserID,
        group_id: RobloxGroupID,
    ) -> RobloxRank | None:
        """Return the user's current rank in a group, if they are a member."""
        membership = await self.get_group_membership(user_id, group_id)
        return membership.rank if membership else None

    async def profile_contains_code(self, user_id: RobloxUserID, code: str) -> bool:
        """Check the Roblox profile description for one verification code."""
        if not code:
            raise ValueError("Verification code cannot be empty.")
        profile = await self.get_user(user_id)
        return code in profile.description

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._require_client()
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise RobloxRequestFailed("Roblox could not be reached.") from error

        if response.status_code >= 500 or response.status_code == 429:
            raise RobloxRequestFailed("Roblox is temporarily unavailable. Please try again.")
        if response.status_code >= 400 and response.status_code != 404:
            self._log.warning("Roblox returned HTTP %s for %s.", response.status_code, url)
            raise RobloxRequestFailed("Roblox rejected the request.")
        return response

    @staticmethod
    def _decode_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise RobloxRequestFailed("Roblox returned an invalid response.") from error
        if not isinstance(payload, dict):
            raise RobloxRequestFailed("Roblox returned an invalid response.")
        return payload

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("RobloxService has not been started.")
        return self._client


def _to_roblox_user(payload: dict[str, Any]) -> RobloxUser:
    user_id = payload.get("id")
    username = payload.get("name")
    display_name = payload.get("displayName")
    if not isinstance(user_id, int) or not isinstance(username, str) or not isinstance(display_name, str):
        raise RobloxRequestFailed("Roblox returned invalid profile data.")

    created_at = _parse_datetime(payload.get("created"))
    return RobloxUser(
        user_id=RobloxUserID(user_id),
        username=username,
        display_name=display_name,
        description=payload.get("description") if isinstance(payload.get("description"), str) else "",
        created_at=created_at,
        is_banned=bool(payload.get("isBanned", False)),
    )


def _to_group_membership(payload: object) -> RobloxGroupMembership:
    if not isinstance(payload, dict):
        raise RobloxRequestFailed("Roblox returned invalid group-role data.")
    group = payload.get("group")
    role = payload.get("role")
    if not isinstance(group, dict) or not isinstance(role, dict):
        raise RobloxRequestFailed("Roblox returned invalid group-role data.")

    group_id, group_name = group.get("id"), group.get("name")
    role_name, rank = role.get("name"), role.get("rank")
    if (
        not isinstance(group_id, int)
        or not isinstance(group_name, str)
        or not isinstance(role_name, str)
        or not isinstance(rank, int)
    ):
        raise RobloxRequestFailed("Roblox returned invalid group-role data.")
    return RobloxGroupMembership(
        group_id=RobloxGroupID(group_id),
        group_name=group_name,
        role_name=role_name,
        rank=RobloxRank(rank),
    )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
