# NOT DONE

"""Calderian organisational structure and organisation lookup logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrganisationType(str, Enum):
    """The type of organisational node."""

    NATION = "nation"
    GOVERNMENT = "government"
    DEPARTMENT = "department"
    AGENCY = "agency"
    ARMED_FORCE = "armed_force"
    SERVICE = "service"
    CORPS = "corps"
    COMMAND = "command"
    FORMATION = "formation"
    UNIT = "unit"
    CIVILIAN = "civilian"


@dataclass(frozen=True, slots=True)
class OrganisationNode:
    """A node within the Calderian organisational hierarchy."""

    id: str
    name: str
    organisation_type: OrganisationType
    parent_id: str | None = None


class OrganisationNotFoundError(LookupError):
    """Raised when an organisation cannot be found."""


class OrganisationService:
    """
    Provide access to the Calderian organisational hierarchy.

    This service currently owns the organisational definition rather than
    persisting it in PostgreSQL. Personnel assignments can be built on top
    of this later without coupling the hierarchy to Discord roles.
    """

    def __init__(
        self,
        organisations: list[OrganisationNode] | None = None,
    ) -> None:
        nodes = organisations or self._default_organisations()

        self._organisations: dict[str, OrganisationNode] = {
            organisation.id: organisation
            for organisation in nodes
        }

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        organisation_id: str,
    ) -> OrganisationNode:
        """Return an organisation by its unique identifier."""
        try:
            return self._organisations[organisation_id]
        except KeyError as exc:
            raise OrganisationNotFoundError(
                f"Organisation '{organisation_id}' does not exist."
            ) from exc

    def get_optional(
        self,
        organisation_id: str,
    ) -> OrganisationNode | None:
        """Return an organisation if it exists."""
        return self._organisations.get(organisation_id)

    def exists(
        self,
        organisation_id: str,
    ) -> bool:
        """Return whether an organisation exists."""
        return organisation_id in self._organisations

    def all(self) -> list[OrganisationNode]:
        """Return every registered organisation."""
        return list(self._organisations.values())

    # ------------------------------------------------------------------
    # Hierarchy
    # ------------------------------------------------------------------

    def get_children(
        self,
        organisation_id: str,
    ) -> list[OrganisationNode]:
        """Return the direct children of an organisation."""
        self.get(organisation_id)

        return [
            organisation
            for organisation in self._organisations.values()
            if organisation.parent_id == organisation_id
        ]

    def get_parent(
        self,
        organisation_id: str,
    ) -> OrganisationNode | None:
        """Return an organisation's direct parent."""
        organisation = self.get(organisation_id)

        if organisation.parent_id is None:
            return None

        return self.get(organisation.parent_id)

    def get_ancestors(
        self,
        organisation_id: str,
    ) -> list[OrganisationNode]:
        """Return an organisation's ancestors from nearest to furthest."""
        current = self.get(organisation_id)
        ancestors: list[OrganisationNode] = []

        while current.parent_id is not None:
            current = self.get(current.parent_id)
            ancestors.append(current)

        return ancestors

    def get_descendants(
        self,
        organisation_id: str,
    ) -> list[OrganisationNode]:
        """Return all descendants beneath an organisation."""
        self.get(organisation_id)

        descendants: list[OrganisationNode] = []
        pending = self.get_children(organisation_id)

        while pending:
            current = pending.pop(0)
            descendants.append(current)
            pending.extend(self.get_children(current.id))

        return descendants

    def is_descendant_of(
        self,
        organisation_id: str,
        ancestor_id: str,
    ) -> bool:
        """Return whether an organisation exists beneath another."""
        current = self.get(organisation_id)

        while current.parent_id is not None:
            if current.parent_id == ancestor_id:
                return True

            current = self.get(current.parent_id)

        return False

    # ------------------------------------------------------------------
    # Calderian structure
    # ------------------------------------------------------------------

    @staticmethod
    def _default_organisations() -> list[OrganisationNode]:
        """Return the initial Calderian organisational structure."""
        return [
            OrganisationNode(
                id="calderia",
                name="Calderia",
                organisation_type=OrganisationType.NATION,
            ),

            OrganisationNode(
                id="federal_government",
                name="Federal Government",
                organisation_type=OrganisationType.GOVERNMENT,
                parent_id="calderia",
            ),

            OrganisationNode(
                id="department_of_defense",
                name="Department of Defense",
                organisation_type=OrganisationType.DEPARTMENT,
                parent_id="federal_government",
            ),

            OrganisationNode(
                id="calderian_armed_forces",
                name="Calderian Armed Forces",
                organisation_type=OrganisationType.ARMED_FORCE,
                parent_id="department_of_defense",
            ),

            OrganisationNode(
                id="calderian_army",
                name="Calderian Army",
                organisation_type=OrganisationType.SERVICE,
                parent_id="calderian_armed_forces",
            ),

            OrganisationNode(
                id="army_corps",
                name="Army Corps",
                organisation_type=OrganisationType.CORPS,
                parent_id="calderian_army",
            ),

            OrganisationNode(
                id="infantry_corps",
                name="Infantry Corps",
                organisation_type=OrganisationType.CORPS,
                parent_id="army_corps",
            ),

            OrganisationNode(
                id="medical_corps",
                name="Medical Corps",
                organisation_type=OrganisationType.CORPS,
                parent_id="army_corps",
            ),

            OrganisationNode(
                id="military_police_corps",
                name="Military Police Corps",
                organisation_type=OrganisationType.CORPS,
                parent_id="army_corps",
            ),

            OrganisationNode(
                id="logistics_corps",
                name="Logistics Corps",
                organisation_type=OrganisationType.CORPS,
                parent_id="army_corps",
            ),

            OrganisationNode(
                id="army_commands",
                name="Army Commands",
                organisation_type=OrganisationType.COMMAND,
                parent_id="calderian_army",
            ),

            OrganisationNode(
                id="army_training_command",
                name="Army Training Command",
                organisation_type=OrganisationType.COMMAND,
                parent_id="army_commands",
            ),

            OrganisationNode(
                id="infantry_force_command",
                name="Infantry Force Command",
                organisation_type=OrganisationType.COMMAND,
                parent_id="army_commands",
            ),

            OrganisationNode(
                id="special_operations_command",
                name="Special Operations Command",
                organisation_type=OrganisationType.COMMAND,
                parent_id="army_commands",
            ),

            OrganisationNode(
                id="army_forces_command",
                name="Army Forces Command",
                organisation_type=OrganisationType.COMMAND,
                parent_id="army_commands",
            ),

            OrganisationNode(
                id="civilian_population",
                name="Civilian Population",
                organisation_type=OrganisationType.CIVILIAN,
                parent_id="calderia",
            ),
        ]