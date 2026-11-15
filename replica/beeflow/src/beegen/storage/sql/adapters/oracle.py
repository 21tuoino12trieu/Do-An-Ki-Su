# -*- coding: utf-8 -*-
from __future__ import annotations

"""
AsyncOracle adapter for BaseSQLAdapter (python-oracledb asyncio backend).

Key features
------------
- Lazily creates an oracledb async Pool bound to the CURRENT event loop when
  `connect_pool()` is called (BaseSQLAdapter ensures correct loop via _ensure_pool()).
- Per-call acquire/release of connections; no global/shared connection reuse.
- Placeholder conversion to Oracle binds:
    * Named (:name or %(name)s)        -> :name (ordered args dict)
    * Positional (%s or ?)             -> :1, :2, ...
- Thin execution helpers that wrap oracledb calls and normalize outputs.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from beegen.storage.sql.base_adapter import BaseSQLAdapter

try:
    import oracledb  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("Install python-oracledb: pip install oracledb") from e


# Placeholder patterns (same semantics as your PG adapter)
_RE_NAMED = re.compile(r"%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s|:([a-zA-Z_][a-zA-Z0-9_]*)")
_RE_POS = re.compile(r"(%s|\?)")


def _normalize_dsn(uri: str) -> str:
    """
    Normalize DSN/URI to an oracledb-accepted form.

    Converts:
    - 'oracle+cx_oracle://user:pass@host:port/?service_name=...' -> 'oracle://...'
    - 'oracle+oracledb://...'                                   -> 'oracle://...'
    Leaves other 'oracle://', Easy Connect strings, or full DSNs intact.

    Notes
    -----
    oracledb.create_pool() can accept:
      - user=..., password=..., dsn=...
      - or a single DSN string that already contains credentials, e.g. 'user/pass@host/service'
    We pass self.uri through as DSN to keep parity with your PG adapter.
    """
    return uri.split("://", 1)[1]


class _Tx:
    """
    Simple transaction shim to mirror begin/commit/rollback API.

    Oracle autocommit is disabled by default; no explicit BEGIN is needed.
    """
    def __init__(self, conn):
        self._conn = conn

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()


class AsyncOracle(BaseSQLAdapter):
    """
    AsyncOracle implements BaseSQLAdapter against python-oracledb (asyncio).
    """

    def __init__(self, conf):
        super().__init__(conf)
        self._pool: Optional[oracledb.AsyncConnectionPool] = None  # created per-loop by connect_pool()

    # ---- dialect helpers ----
    def _wrap_sample_sql(self, inner_sql: str, limit: int) -> str:
        return f"SELECT * FROM ({inner_sql}) q WHERE ROWNUM <= {int(limit)}"

    def _wrap_count_sql(self, inner_sql: str) -> str:
        return f"SELECT COUNT(*) AS total FROM ({inner_sql}) q"

    # ---- lifecycle/pool ----
    async def connect_pool(self) -> None:
        """
        Create the oracledb async pool bound to the CURRENT event loop.
        """
        if self._pool is None:
            dsn = _normalize_dsn(self.uri)

            # If your conf provides explicit user/password, you can switch to:
            # self._pool = await oracledb.create_pool(user=self.user, password=self.password, dsn=dsn, ...)
            #
            # To keep parity with your PG adapter (which only passes a single URI),
            # we pass DSN only. The DSN may embed credentials ("user/pass@host/service").
            self._pool = oracledb.create_pool(
                user=self.user, 
                password=self.password,
                dsn=dsn,
                min= self.pool_min_size or 1,
                max= self.pool_max_size or 10,
                increment=1,
                timeout=self.connect_timeout or 0,  # seconds; 0 means default
                # session_callback=...,  # attach if you need ALTER SESSION, NLS, etc.
            )

    async def close_pool(self) -> None:
        """Close and discard the current oracledb pool."""
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
        oracledb.AsyncConnection
        """
        if self._pool is None:
            raise RuntimeError("Pool is not initialized. connect_pool() must be called first.")
        return self._pool.acquire()

    async def release(self, conn) -> None:
        """
        Release a connection back to the current pool.
        """
        if self._pool is None:
            # Pool vanished; best effort close
            try:
                await conn.close()
            except Exception:
                pass
            return
        await self._pool.release(conn)

    # ---- transactions ----
    async def begin(self, conn):
        """Return a transaction shim bound to `conn` (Oracle doesn't need explicit BEGIN)."""
        return _Tx(conn)

    async def commit(self, tx) -> None:
        await tx.commit()

    async def rollback(self, tx) -> None:
        await tx.rollback()

    # ---- SQL conversion ----
    def _convert_named(self, sql: str, params: Dict[str, Any]) -> Tuple[str, dict]:
        """
        Convert named placeholders (:name or %(name)s) to Oracle :name binds.

        Returns the SQL and a dict suitable for cursor.execute(sql, args).
        """
        used: List[str] = []
        def repl(m: re.Match) -> str:
            name = m.group(1) or m.group(2)
            used.append(name)
            return f":{name}"

        sql_d = _RE_NAMED.sub(repl, sql)
        try:
            args = {name: params[name] for name in used}
        except KeyError as e:
            raise KeyError(f"Missing named param: {e.args[0]}") from e
        return sql_d, args

    def _convert_pos(self, sql: str, params: Sequence[Any]) -> Tuple[str, tuple]:
        """
        Convert positional placeholders (%s or ?) to Oracle :1, :2, ...
        """
        idx = 0
        def repl(_: re.Match) -> str:
            nonlocal idx
            idx += 1
            return f":{idx}"

        sql_d, count = _RE_POS.subn(repl, sql)
        if count != len(params):
            raise ValueError(f"Expected {count} positional params, got {len(params)}")
        return sql_d, tuple(params)

    def convert_sql_and_args(self, sql: str, params) -> Tuple[str, Any]:
        """
        Convert user SQL + params to oracledb-ready `(sql, args)`.
        - None params: SQL must not contain placeholders.
        - dict params: SQL may use :name or %(name)s.
        - list/tuple params: SQL may use %s or ?.
        """

        if isinstance(params, dict):
            if _RE_NAMED.search(sql):
                return self._convert_named(sql, params)
            # If user already wrote ':name' only, we still need to filter to used names:
            used = [m.group(2) for m in _RE_NAMED.finditer(sql) if m.group(2)]
            if not used:
                # Assume the dict keys match any :name in sql (no %(name)s present)
                return sql, params
            return sql, {k: params[k] for k in used}

        if isinstance(params, (list, tuple)):
            if _RE_POS.search(sql):
                return self._convert_pos(sql, params)
            raise ValueError("Positional params require %s or ? placeholders.")

    def convert_many(
        self,
        sql: str,
        seq_of_params: Iterable[Dict[str, Any] | List[Any] | tuple],
    ) -> Tuple[str, List[Any]]:
        """
        Convert a sequence of param rows for executemany.

        For dict rows, keeps :name binds and materializes dicts per row (matching the first row's order).
        For positional rows, converts %s/? -> :1,:2,... and materializes tuples per row.
        """
        seq = list(seq_of_params)
        if not seq:
            return sql, []

        first = seq[0]
        if isinstance(first, dict):
            # Determine the placeholder order by scanning SQL once
            order: List[str] = []
            def repl(m: re.Match) -> str:
                name = m.group(1) or m.group(2)
                order.append(name)
                return f":{name}"

            sql_d = _RE_NAMED.sub(repl, sql)
            arglists: List[dict] = []
            for row in seq:  # type: ignore[assignment]
                if not isinstance(row, dict):
                    raise TypeError("All rows must be dict for named placeholders.")
                try:
                    arglists.append({name: row[name] for name in order})
                except KeyError as e:
                    raise KeyError(f"Missing named param in batch: {e.args[0]}") from e
            return sql_d, arglists

        if isinstance(first, (list, tuple)):
            idx = 0
            def repl(_: re.Match) -> str:
                nonlocal idx
                idx += 1
                return f":{idx}"

            sql_d, count = _RE_POS.subn(repl, sql)
            arglists: List[tuple] = []
            for row in seq:  # type: ignore[assignment]
                if not isinstance(row, (list, tuple)):
                    raise TypeError("All rows must be list/tuple for positional placeholders.")
                if len(row) != count:
                    raise ValueError(f"Expected {count} positional params, got {len(row)} in batch.")
                arglists.append(tuple(row))
            return sql_d, arglists

        raise TypeError("Each item in seq_of_params must be dict or list/tuple")

    # ---- execution helpers ----
    async def _fetch_all(self, cursor) -> List[Dict[str, Any]]:
        cols = [d[0].lower() for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(cols, r)) for r in rows]

    async def fetch(self, conn, sql: str, args) -> List[Dict[str, Any]]:
        """
        Execute a SELECT returning multiple rows.
        """
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return await self._fetch_all(cur)

    async def fetchrow(self, conn, sql: str, args) -> Optional[Dict[str, Any]]:
        """
        Execute a SELECT returning a single row (or None).
        """
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            row = await cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description] if cur.description else []
            return dict(zip(cols, row))

    async def execute(self, conn, sql: str, args) -> Dict[str, Any]:
        """
        Execute a DDL/DML statement and return affected row count.
        Note: For some DDLs Oracle may return -1; for DML, rowcount is accurate.
        """
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return {"rowcount": cur.rowcount}

    async def executemany(self, conn, sql: str, arglists: List[Any]) -> Dict[str, Any]:
        """
        Execute batch DML using cursor.executemany.
        """
        if not arglists:
            return {"rowcount": 0}
        async with conn.cursor() as cur:
            await cur.executemany(sql, arglists)
            # For executemany, oracledb doesn't always provide exact per-row rowcount; fallback to len(batch)
            return {"rowcount": len(arglists)}


# ---------- __main__ demo ----------
async def _demo_with_registry():
    """
    Example using RESOURCE_HUB like your PG demo.
    Ensure your 'oracle' resource is configured with a DSN that oracledb accepts.
    Examples:
      - 'user/password@host:1521/service_name'
      - 'oracle://user:password@host:1521/?service_name=orclpdb1' (normalized)
    """
    from pprint import pprint
    from beegen.registry.resource_hub import RESOURCE_HUB
    from beegen.configs.storage.sql_config import SQLOperation

    adapter = RESOURCE_HUB.sql("tckt")  # e.g., points to this AsyncOracle

    print(f"[adapter] Type={type(adapter).__name__}")

    # Oracle's "fetch first N rows only" for limiting:
    res = await adapter.run(
        SQLOperation.QUERY,
        {
            "query": """
                SELECT TINH_THANH, COUNT(DISTINCT MAKH) AS SO_KHACH_HANG 
                FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC 
                WHERE TRANSACTION_DATE = TO_TIMESTAMP('2025-06-30 00:00:00.000', 'YYYY-MM-DD HH24:MI:SS.FF') 
                AND IS_APP_BIZ = 1
                AND APP_BIZ_STATUS = 'ACTIVE' GROUP BY TINH_THANH 
                ORDER BY SO_KHACH_HANG DESC 
                FETCH FIRST 6 ROWS ONLY""",
            "limit": 10,
        },
    )
    pprint(res)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_demo_with_registry())
