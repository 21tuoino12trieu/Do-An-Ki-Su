# -*- coding: utf-8 -*-
from __future__ import annotations

"""
AsyncPostgres adapter for BaseSQLAdapter (asyncpg backend).

Key features
------------
- Lazily creates an asyncpg Pool bound to the CURRENT event loop when
  `connect_pool()` is called (BaseSQLAdapter ensures correct loop via _ensure_pool()).
- Per-call acquire/release of connections; no global/shared connection reuse.
- Placeholder conversion:
    * Named (:name or %(name)s)  -> $1, $2, ...
    * Positional (%s or ?)       -> $1, $2, ...
- Thin execution helpers that wrap asyncpg calls and normalize outputs.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from beegen.storage.sql.base_adapter import BaseSQLAdapter

try:
    import asyncpg  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("Install asyncpg: pip install asyncpg") from e


# Placeholder patterns
_RE_NAMED = re.compile(
    r"%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s|:([a-zA-Z_][a-zA-Z0-9_]*)")
_RE_POS = re.compile(r"(%s|\?)")


def _parse_rowcount(status: str) -> Optional[int]:
    """
    Extract an integer rowcount from asyncpg's command status string.

    Examples
    --------
    'INSERT 0 3' -> 3
    'UPDATE 12'  -> 12
    """
    toks = status.strip().split()
    for t in reversed(toks):
        if t.isdigit():
            try:
                return int(t)
            except Exception:
                return None
    return None


def _normalize_dsn(uri: str) -> str:
    """
    Normalize DSN/URI to asyncpg-accepted form.

    Converts:
    - 'postgresql+psycopg://...' -> 'postgresql://...'
    - 'postgres://...'           -> 'postgresql://...'
    Leaves other schemes intact.
    """
    if uri.startswith("postgresql+"):
        return "postgresql://" + uri.split("://", 1)[1]
    if uri.startswith("postgres://"):
        return "postgresql://" + uri.split("://", 1)[1]
    return uri


class AsyncPostgres(BaseSQLAdapter):
    """
    AsyncPostgres implements BaseSQLAdapter against asyncpg.

    Pool lifecycle
    --------------
    BaseSQLAdapter._ensure_pool() guarantees that connect_pool() is executed in
    the correct event loop. This class keeps its pool in `self._pool` and never
    exposes nor reuses connections across loops.
    """

    def __init__(self, conf):
        super().__init__(conf)
        # created per-loop by connect_pool()
        self._pool: Optional[asyncpg.pool.Pool] = None

    # ---- dialect helpers ----
    def _wrap_sample_sql(self, inner_sql: str, limit: int) -> str:
        return f"SELECT * FROM ({inner_sql}) AS _q LIMIT {int(limit)}"

    def _wrap_count_sql(self, inner_sql: str) -> str:
        return f"SELECT COUNT(*) AS total FROM ({inner_sql}) AS _q"

    # ---- lifecycle/pool ----
    async def connect_pool(self) -> None:
        """
        Create the asyncpg pool bound to the CURRENT event loop.

        Notes
        -----
        This method is called by BaseSQLAdapter._ensure_pool(). If a pool from a
        different loop exists, BaseSQLAdapter will first call close_pool() and then
        call connect_pool() again on the new loop.
        """
        if self._pool is None:
            dsn = _normalize_dsn(self.uri)
            self._pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
                timeout=self.connect_timeout or None,
                # Uncomment for edge cases with prepared statement cache:
                # statement_cache_size=1000,
            )

    async def close_pool(self) -> None:
        """Close and discard the current asyncpg pool."""
        if self._pool is not None:
            try:
                await self._pool.close()
            finally:
                self._pool = None

    async def acquire(self):
        """
        Acquire a connection from the current pool.

        Returns
        -------
        asyncpg.Connection
        """
        if self._pool is None:
            raise RuntimeError(
                "Pool is not initialized. connect_pool() must be called first.")
        return await self._pool.acquire()

    async def release(self, conn) -> None:
        """
        Release a connection back to the current pool.

        If the pool was unexpectedly gone, attempt to close the connection.
        """
        if self._pool is None:
            try:
                await conn.close()
            except Exception:
                pass
            return
        await self._pool.release(conn)

    # ---- transactions ----
    async def begin(self, conn):
        """Begin and return an asyncpg transaction handle bound to `conn`."""
        tx = conn.transaction()
        await tx.start()
        return tx

    async def commit(self, tx) -> None:
        """Commit the given asyncpg transaction handle."""
        await tx.commit()

    async def rollback(self, tx) -> None:
        """Rollback the given asyncpg transaction handle."""
        await tx.rollback()

    # ---- SQL conversion ----
    def _convert_named(self, sql: str, params: Dict[str, Any]) -> Tuple[str, tuple]:
        """
        Convert named placeholders (:name or %(name)s) to $1, $2, ... with ordered args.
        """
        order: List[str] = []
        idx = 0

        def repl(m: re.Match) -> str:
            nonlocal idx
            name = m.group(1) or m.group(2)
            order.append(name)
            idx += 1
            return f"${idx}"

        sql_d = _RE_NAMED.sub(repl, sql)
        try:
            args = tuple(params[name] for name in order)
        except KeyError as e:
            raise KeyError(f"Missing named param: {e.args[0]}") from e
        return sql_d, args

    def _convert_pos(self, sql: str, params: Sequence[Any]) -> Tuple[str, tuple]:
        """
        Convert positional placeholders (%s or ?) to $1, $2, ... with ordered args.
        """
        idx = 0

        def repl(_: re.Match) -> str:
            nonlocal idx
            idx += 1
            return f"${idx}"

        sql_d, count = _RE_POS.subn(repl, sql)
        if count != len(params):
            raise ValueError(
                f"Expected {count} positional params, got {len(params)}")
        return sql_d, tuple(params)

    def convert_sql_and_args(self, sql: str, params) -> Tuple[str, tuple]:
        """
        Convert user SQL + params to asyncpg-ready `(sql, args)`.

        Rules
        -----
        - None params: SQL must not contain placeholders.
        - dict params: SQL must use named placeholders (:name or %(name)s).
        - list/tuple params: SQL must use positional placeholders (%s or ?).
        """
        if params is None:
            if _RE_POS.search(sql) or _RE_NAMED.search(sql):
                raise ValueError("SQL has placeholders but 'params' is None")
            return sql, tuple()

        if isinstance(params, dict):
            if _RE_NAMED.search(sql):
                return self._convert_named(sql, params)
            raise ValueError(
                "Dict params require :name or %(name)s placeholders.")

        if isinstance(params, (list, tuple)):
            if _RE_POS.search(sql):
                return self._convert_pos(sql, params)
            raise ValueError("Positional params require %s or ? placeholders.")

        raise TypeError("params must be dict, list/tuple, or None")

    def convert_many(
        self,
        sql: str,
        seq_of_params: Iterable[Dict[str, Any] | List[Any] | tuple],
    ) -> Tuple[str, List[tuple]]:
        """
        Convert a sequence of param rows for executemany.

        Supports both named and positional placeholders; all rows must be
        homogeneous (all dicts or all list/tuples).
        """
        seq = list(seq_of_params)
        if not seq:
            return sql, []

        first = seq[0]
        if isinstance(first, dict):
            order: List[str] = []
            idx = 0

            def repl(m: re.Match) -> str:
                nonlocal idx
                name = m.group(1) or m.group(2)
                order.append(name)
                idx += 1
                return f"${idx}"

            sql_d = _RE_NAMED.sub(repl, sql)
            arglists: List[tuple] = []
            for row in seq:  # type: ignore[assignment]
                if not isinstance(row, dict):
                    raise TypeError(
                        "All rows must be dict for named placeholders.")
                try:
                    arglists.append(tuple(row[name] for name in order))
                except KeyError as e:
                    raise KeyError(
                        f"Missing named param in batch: {e.args[0]}") from e
            return sql_d, arglists

        if isinstance(first, (list, tuple)):
            idx = 0

            def repl(_: re.Match) -> str:
                nonlocal idx
                idx += 1
                return f"${idx}"

            sql_d, count = _RE_POS.subn(repl, sql)
            arglists = []
            for row in seq:  # type: ignore[assignment]
                if not isinstance(row, (list, tuple)):
                    raise TypeError(
                        "All rows must be list/tuple for positional placeholders.")
                if len(row) != count:
                    raise ValueError(
                        f"Expected {count} positional params, got {len(row)} in batch.")
                arglists.append(tuple(row))
            return sql_d, arglists

        raise TypeError(
            "Each item in seq_of_params must be dict or list/tuple")

    # ---- execution ----
    async def fetch(self, conn, sql: str, args: tuple) -> List[Dict[str, Any]]:
        """
        Execute a SELECT returning multiple rows.

        Returns
        -------
        List[Dict[str, Any]]
        """
        recs = await conn.fetch(sql, *args)
        return [dict(r) for r in recs]

    async def fetchrow(self, conn, sql: str, args: tuple) -> Optional[Dict[str, Any]]:
        """
        Execute a SELECT returning a single row (or None).
        """
        rec = await conn.fetchrow(sql, *args)
        return dict(rec) if rec is not None else None

    async def execute(self, conn, sql: str, args: tuple) -> Dict[str, Any]:
        """
        Execute a DDL/DML statement and parse affected row count from status.
        """
        status = await conn.execute(sql, *args)
        return {"rowcount": _parse_rowcount(status)}

    async def executemany(self, conn, sql: str, arglists: List[tuple]) -> Dict[str, Any]:
        """
        Execute a batch DML using asyncpg.executemany.
        """
        await conn.executemany(sql, arglists)
        return {"rowcount": len(arglists)}


# ---------- __main__ demo ----------
async def _demo_with_registry():
    import os
    from pprint import pprint
    from beegen.registry.resource_hub import RESOURCE_HUB
    from beegen.configs.storage.sql_config import SQLOperation

    adapter = RESOURCE_HUB.sql("anapp")

    print(f"[adapter] Type={type(adapter).__name__}")

    res = await adapter.run(
        SQLOperation.QUERY,
        {
            "query": "select * from agent_ai.behavior_in_app limit 20",
            "limit": 1,
            "params": None,
            "session_id": None
         },
    )
    pprint(res)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_demo_with_registry())
