"""Asynchronous PostgreSQL connection service for the verification bot."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

import asyncpg

from ..core.exceptions import DatabaseError

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


class Database:
    """Owns one reusable asyncpg connection pool.

    Repositories receive this service and use parameterised methods instead of
    making their own PostgreSQL connections.  No SQL for users, guilds, or
    verification records belongs in this class; those go in repositories.
    """

    def __init__(self, database_url: str, logger: logging.Logger | None = None) -> None:
        self._database_url = database_url
        self._log = logger or logging.getLogger("verification_bot.database")
        self._pool: asyncpg.Pool | None = None

    @classmethod
    async def create(cls, config: Config, _: ServiceContainer) -> Database:
        """Factory used by ``ServiceManager`` during application startup."""
        return cls(config.database_url)

    async def start(self) -> None:
        """Open the shared database pool once."""
        if self._pool is not None:
            return
        try:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                min_size=1,
                max_size=10,
                command_timeout=30,
            )
        except (OSError, asyncpg.PostgresError) as error:
            # Do not include the URL in this error: it may contain a password.
            raise DatabaseError("Unable to connect to PostgreSQL.") from error
        self._log.info("PostgreSQL connection pool opened.")

    async def close(self) -> None:
        """Close every connection in the pool during shutdown."""
        if self._pool is None:
            return
        pool, self._pool = self._pool, None
        await pool.close()
        self._log.info("PostgreSQL connection pool closed.")

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire one pooled connection for a short database operation."""
        pool = self._require_pool()
        try:
            async with pool.acquire() as connection:
                yield connection
        except asyncpg.PostgresError as error:
            raise DatabaseError("A PostgreSQL operation failed.") from error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """Provide a connection whose changes commit or roll back together."""
        async with self.connection() as connection:
            transaction = connection.transaction()
            try:
                await transaction.start()
                yield connection
            except Exception:
                await transaction.rollback()
                raise
            else:
                await transaction.commit()

    async def execute(self, query: str, *parameters: object) -> str:
        """Run a parameterised statement and return asyncpg's status string."""
        async with self.connection() as connection:
            return await connection.execute(query, *parameters)

    async def fetch(self, query: str, *parameters: object) -> list[asyncpg.Record]:
        """Run a parameterised query and return all resulting records."""
        async with self.connection() as connection:
            return await connection.fetch(query, *parameters)

    async def fetchrow(self, query: str, *parameters: object) -> asyncpg.Record | None:
        """Run a parameterised query and return one record, if present."""
        async with self.connection() as connection:
            return await connection.fetchrow(query, *parameters)

    async def fetchval(self, query: str, *parameters: object) -> object | None:
        """Run a parameterised query and return its first value, if present."""
        async with self.connection() as connection:
            return await connection.fetchval(query, *parameters)

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise DatabaseError("The PostgreSQL pool has not been started.")
        return self._pool
