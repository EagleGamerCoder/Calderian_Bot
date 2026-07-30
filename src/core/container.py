"""A small dependency container for application-wide service instances."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any, TypeVar

from .exceptions import ServiceAlreadyRegistered, ServiceNotRegistered


T = TypeVar("T")


class ServiceContainer:
    """Stores the single shared instance of each application service.

    ``startup.py`` creates this container and ``ServiceManager`` populates it.
    A command can then use ``bot.services.require("verification")`` instead of
    constructing a new service with hidden dependencies.
    """

    __slots__ = ("_services", "_frozen")

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._frozen = False

    def register(self, name: str, service: T) -> T:
        """Register and return one service instance.

        Names must be simple public identifiers, for example ``"database"``,
        ``"roblox"``, or ``"verification"``.  Registering twice is rejected;
        replacing a live database or HTTP client silently is unsafe.
        """
        self._validate_name(name)
        if self._frozen:
            raise RuntimeError("The service container is frozen after startup.")
        if name in self._services:
            raise ServiceAlreadyRegistered(f"Service '{name}' is already registered.")
        self._services[name] = service
        return service

    def require(self, name: str, expected_type: type[T] | None = None) -> T:
        """Return a required service, optionally validating its runtime type."""
        try:
            service = self._services[name]
        except KeyError as error:
            raise ServiceNotRegistered(f"Service '{name}' is not registered.") from error

        if expected_type is not None and not isinstance(service, expected_type):
            raise TypeError(
                f"Service '{name}' is {type(service).__name__}, "
                f"not {expected_type.__name__}."
            )
        return service

    def get(self, name: str, default: T | None = None) -> Any | T | None:
        """Return a service if registered, otherwise return ``default``."""
        return self._services.get(name, default)

    def is_registered(self, name: str) -> bool:
        """Return whether a service has been registered under ``name``."""
        return name in self._services

    def freeze(self) -> None:
        """Prevent further registrations once startup has completed."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """Whether registrations are currently locked."""
        return self._frozen

    @property
    def registered(self) -> Mapping[str, Any]:
        """A read-only view of currently registered services."""
        return MappingProxyType(self._services)

    def __contains__(self, name: object) -> bool:
        return name in self._services

    def __iter__(self) -> Iterator[str]:
        return iter(self._services)

    def __len__(self) -> int:
        return len(self._services)

    def __getattr__(self, name: str) -> Any:
        """Allow concise access such as ``bot.services.verification``.

        ``require()`` remains preferable where a service is mandatory because it
        makes the failure message and optional type assertion explicit.
        """
        try:
            return self.require(name)
        except ServiceNotRegistered as error:
            raise AttributeError(str(error)) from error

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.isidentifier() or name.startswith("_"):
            raise ValueError(
                "Service names must be non-private Python identifiers, "
                "such as 'database' or 'verification'."
            )
