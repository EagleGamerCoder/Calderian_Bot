"""Dependency-aware creation and shutdown of application services."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from .container import ServiceContainer
from .exceptions import ServiceError

if TYPE_CHECKING:
    from .config import Config


T = TypeVar("T")
ServiceFactory = Callable[[Config, ServiceContainer], T | Awaitable[T]]


@dataclass(frozen=True, slots=True)
class ServiceDefinition:
    """A service factory and the named services it needs first."""

    name: str
    factory: ServiceFactory[Any]
    depends_on: tuple[str, ...] = ()


class ServiceManager:
    """Creates every shared service exactly once in a known order.

    ``startup.py`` registers definitions before the Discord client starts::

        manager.register("database", DatabaseService.create)
        manager.register("roblox", RobloxService.create)
        manager.register(
            "verification",
            VerificationService.create,
            depends_on=("database", "roblox", "roles"),
        )

    A factory receives the validated config and the container, so it can obtain
    only its explicitly declared dependencies through ``container.require()``.
    A service may optionally expose asynchronous ``start()`` and ``close()``
    methods; the manager calls them at the appropriate lifecycle point.
    """

    def __init__(
        self,
        config: Config,
        container: ServiceContainer,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._container = container
        self._log = logger or logging.getLogger("verification_bot.services")
        self._definitions: dict[str, ServiceDefinition] = {}
        self._started_services: list[tuple[str, Any]] = []
        self._loaded = False
        self._closed = False

    def register(
        self,
        name: str,
        factory: ServiceFactory[T],
        *,
        depends_on: tuple[str, ...] = (),
    ) -> None:
        """Declare a service that will be built during :meth:`load`.

        Registration itself has no side effects.  This keeps startup predictable
        and allows a test to replace one factory with a fake before loading.
        """
        if self._loaded:
            raise RuntimeError("Services cannot be registered after startup.")
        self._container._validate_name(name)
        if name in self._definitions:
            raise ValueError(f"Service '{name}' has already been declared.")
        if not callable(factory):
            raise TypeError("A service factory must be callable.")

        dependencies = tuple(depends_on)
        for dependency in dependencies:
            self._container._validate_name(dependency)
        self._definitions[name] = ServiceDefinition(name, factory, dependencies)

    async def load(self) -> None:
        """Create and start declared services once, respecting dependencies."""
        if self._loaded:
            return
        if self._closed:
            raise RuntimeError("A closed service manager cannot be started again.")

        pending = dict(self._definitions)
        try:
            while pending:
                ready = [
                    definition
                    for definition in pending.values()
                    if all(self._container.is_registered(name) for name in definition.depends_on)
                ]
                if not ready:
                    self._raise_unresolvable_dependencies(pending)

                for definition in ready:
                    pending.pop(definition.name)
                    await self._create_and_start(definition)
        except Exception:
            self._log.exception("Service startup failed; closing started services.")
            await self._close_started_services()
            raise

        self._container.freeze()
        self._loaded = True
        self._log.info("Started %d application service(s).", len(self._started_services))

    async def close(self) -> None:
        """Close started services in reverse dependency order."""
        if self._closed:
            return
        self._closed = True
        await self._close_started_services()

    async def _create_and_start(self, definition: ServiceDefinition) -> None:
        self._log.debug("Creating service '%s'.", definition.name)
        service = definition.factory(self._config, self._container)
        if inspect.isawaitable(service):
            service = await service
        if service is None:
            raise ServiceError(f"Service factory '{definition.name}' returned None.")

        self._container.register(definition.name, service)
        self._started_services.append((definition.name, service))
        await _call_lifecycle_method(service, "start")
        self._log.debug("Started service '%s'.", definition.name)

    async def _close_started_services(self) -> None:
        while self._started_services:
            name, service = self._started_services.pop()
            try:
                await _call_lifecycle_method(service, "close")
                self._log.debug("Closed service '%s'.", name)
            except Exception:
                self._log.exception("Could not close service '%s'.", name)

    def _raise_unresolvable_dependencies(
        self,
        pending: dict[str, ServiceDefinition],
    ) -> None:
        details = "; ".join(
            f"{definition.name} needs {', '.join(definition.depends_on) or 'nothing'}"
            for definition in pending.values()
        )
        raise ServiceError(
            "Service dependencies cannot be resolved. Check for a missing "
            f"registration or circular dependency: {details}"
        )


async def _call_lifecycle_method(service: Any, method_name: str) -> None:
    """Call an optional sync or async service lifecycle method."""
    method = getattr(service, method_name, None)
    if method is None:
        return
    if not callable(method):
        raise TypeError(f"Service attribute '{method_name}' must be callable.")
    result = method()
    if inspect.isawaitable(result):
        await result