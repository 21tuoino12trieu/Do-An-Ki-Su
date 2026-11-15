# -*- coding: utf-8 -*-
from __future__ import annotations
import json

"""
BaseSqlAdapter: Abstract SQL adapter with operations & run()

This module defines an abstract, asyncio-friendly SQL adapter that:
  - Manages a connection pool lifecycle (delegated to concrete adapters).
  - Supports simple transaction sessions mapped by `session_id`.
  - Exposes a uniform operation map and a `run()` method that returns
    standardized envelopes suitable for higher-level nodes.

Concrete adapters (e.g., AsyncPostgres) MUST implement:
  connect_pool() / close_pool() / acquire() / release()
  begin() / commit() / rollback()
  convert_sql_and_args() / convert_many()
  fetch() / fetchrow() / execute() / executemany()
"""

import asyncio
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from beegen.configs.storage.sql_config import SQLConfig, SQLOperation


class BaseSQLAdapter(ABC):
    """
    Abstract SQL adapter exposing a uniform async interface and operation runner.

    Design highlights
    -----------------
    - Event-loop affinity: the underlying pool is tied to the *current* event loop.
      If the loop changes, the existing pool is closed and a new one is created
      to avoid "Future attached to a different loop" errors.
    - Per-call acquire/release: each operation acquires a connection from the pool
      and releases it in a `finally` block, preventing "operation in progress" races.
    - Transaction sessions: BEGIN returns a `session_id`; subsequent COMMIT/ABORT
      must be executed on the same loop where BEGIN occurred.

    Subclasses must be asyncio-compatible and implement the abstract methods below.
    """

    def __init__(self, conf: SQLConfig):
        # --- configuration (shared with concrete adapters via getters/setters) ---
        self.uri: str = conf.uri
        self.user: str = conf.user
        self.password: str = conf.password
        self.pool_max_size: int = int(conf.pool_max_size)
        self.pool_min_size: int = int(conf.pool_min_size)
        self.connect_timeout: int = int(conf.connect_timeout)

        # --- pool state ---
        self._pool_ready: bool = False
        self._pool_loop: Optional[int] = None  # id(current loop) that owns the pool

        # --- transaction sessions: sid -> {"conn": ..., "tx": ..., "loop_id": int}
        self._sessions: Dict[str, Dict[str, Any]] = {}

        # --- public operation map (SqlNode-compatible) ---
        self.operation_map = {
            SQLOperation.QUERY: self._op_query,
            SQLOperation.QUERY_ONE: self._op_query_one,
            SQLOperation.EXECUTE: self._op_execute,
            SQLOperation.EXECUTE_MANY: self._op_execute_many,
            SQLOperation.BEGIN_TRANSACTION: self._op_begin,
            SQLOperation.COMMIT_TRANSACTION: self._op_commit,
            SQLOperation.ABORT_TRANSACTION: self._op_abort,
        }

    # ===== Pool lifecycle (implemented by concrete adapters) ===================

    @abstractmethod
    async def connect_pool(self) -> None:
        """Create/connect the pool bound to the *current* event loop."""
        ...

    @abstractmethod
    async def close_pool(self) -> None:
        """Close/destroy the current pool."""
        ...

    @abstractmethod
    async def acquire(self):
        """Acquire a connection from the pool."""
        ...

    @abstractmethod
    async def release(self, conn) -> None:
        """Release a connection back to the pool."""
        ...

    # ===== Transactions API (implemented by concrete adapters) =================

    @abstractmethod
    async def begin(self, conn):
        """Begin/return a transaction handle bound to `conn`."""
        ...

    @abstractmethod
    async def commit(self, tx) -> None:
        """Commit a previously started transaction `tx`."""
        ...

    @abstractmethod
    async def rollback(self, tx) -> None:
        """Rollback a previously started transaction `tx`."""
        ...

    # ===== SQL conversion (implemented by concrete adapters) ===================

    @abstractmethod
    def convert_sql_and_args(self, sql: str, params) -> tuple[str, tuple]:
        """
        Convert `sql` and `params` to a database-driver-friendly `(sql_prepared, args_tuple)`.
        """
        ...

    @abstractmethod
    def convert_many(
        self,
        sql: str,
        seq_of_params: Iterable[Dict[str, Any] | List[Any] | Tuple[Any, ...]],
    ) -> tuple[str, List[tuple]]:
        """
        Convert batch params for executemany into `(sql_prepared, [args_tuple, ...])`.
        """
        ...

    # ===== Execution (implemented by concrete adapters) ========================

    @abstractmethod
    async def fetch(self, conn, sql: str, args: tuple) -> List[Dict[str, Any]]:
        """Execute a SELECT returning multiple rows."""
        ...

    @abstractmethod
    async def fetchrow(self, conn, sql: str, args: tuple) -> Optional[Dict[str, Any]]:
        """Execute a SELECT returning a single row (or None)."""
        ...

    @abstractmethod
    async def execute(self, conn, sql: str, args: tuple) -> Dict[str, Any]:
        """Execute a DDL/DML statement (optionally with driver-specific metrics)."""
        ...

    @abstractmethod
    async def executemany(self, conn, sql: str, arglists: List[tuple]) -> Dict[str, Any]:
        """Execute a batch DML via executemany (returns driver-specific metrics)."""
        ...

    # ===== Internal helpers ====================================================

    async def _ensure_pool(self) -> None:
        """
        Ensure a pool exists and is bound to the *current* event loop.

        If an existing pool was created in a different loop, it will be closed and
        a new pool will be created for the current loop to avoid loop affinity issues.
        """
        loop = asyncio.get_running_loop()
        loop_id = id(loop)

        if (not self._pool_ready) or (self._pool_loop != loop_id):
            # Close a previous pool if it was created on a different loop.
            if self._pool_ready:
                try:
                    await self.close_pool()
                except Exception:
                    # Swallow pool closing errors; we are recreating it anyway.
                    pass

            await self.connect_pool()
            self._pool_ready = True
            self._pool_loop = loop_id

    async def _acquire(self, session_id: Optional[str]):
        """
        Acquire a connection either from a transaction session or from the pool.

        Returns
        -------
        (conn, in_tx): (Any, bool)
            - conn: acquired connection object
            - in_tx: True if the connection belongs to an active transaction session
        """
        await self._ensure_pool()

        if session_id:
            bundle = self._sessions.get(session_id)
            if not bundle:
                raise ValueError("Invalid session_id")

            cur_loop_id = id(asyncio.get_running_loop())
            if bundle.get("loop_id") != cur_loop_id:
                raise RuntimeError(
                    "Transaction session is bound to a different event loop"
                )
            return bundle["conn"], True

        conn = await self.acquire()
        return conn, False

    async def _release(self, conn, in_tx: bool) -> None:
        """
        Release a connection if it does not belong to an active transaction.
        """
        if not in_tx:
            try:
                await self.release(conn)
            except Exception:
                # Avoid masking upstream exceptions with release/reset errors.
                pass

    # ===== Operations ==========================================================

    async def _op_begin(self, **_: Any) -> Dict[str, Any]:
        """
        Begin a transaction, returning a session_id to be used for subsequent
        COMMIT/ABORT calls. The session is tied to the current event loop.
        """
        await self._ensure_pool()
        conn = await self.acquire()
        try:
            tx = await self.begin(conn)
        except Exception:
            # If begin fails, release the connection before raising.
            try:
                await self.release(conn)
            finally:
                raise

        sid = uuid4().hex
        self._sessions[sid] = {
            "conn": conn,
            "tx": tx,
            "loop_id": id(asyncio.get_running_loop()),
        }
        return {
            "status": "success",
            "session_id": sid,
            "message": "Operation begin transaction completed successfully",
        }

    async def _op_commit(self, **params) -> Dict[str, Any]:
        """
        Commit a previously started transaction for the provided session_id.
        Must be invoked on the same loop as the BEGIN call.
        """
        await self._ensure_pool()

        sid = params.get("session_id")
        bundle = self._sessions.pop(sid, None)
        if not bundle:
            raise ValueError("Valid session_id must be provided")

        if bundle.get("loop_id") != id(asyncio.get_running_loop()):
            # restore session to avoid losing it on wrong-loop calls
            self._sessions[sid] = bundle
            raise RuntimeError("Commit must be called from the same event loop as begin")

        try:
            await self.commit(bundle["tx"])
            return {
                "status": "success",
                "committed": True,
                "message": "Operation commit transaction completed successfully",
            }
        finally:
            try:
                await self.release(bundle["conn"])
            except Exception:
                pass

    async def _op_abort(self, **params) -> Dict[str, Any]:
        """
        Rollback a previously started transaction for the provided session_id.
        Must be invoked on the same loop as the BEGIN call.
        """
        await self._ensure_pool()

        sid = params.get("session_id")
        bundle = self._sessions.pop(sid, None)
        if not bundle:
            raise ValueError("Valid session_id must be provided")

        if bundle.get("loop_id") != id(asyncio.get_running_loop()):
            self._sessions[sid] = bundle
            raise RuntimeError("Abort must be called from the same event loop as begin")

        try:
            await self.rollback(bundle["tx"])
            return {
                "status": "success",
                "aborted": True,
                "message": "Operation abort transaction completed successfully",
            }
        finally:
            try:
                await self.release(bundle["conn"])
            except Exception:
                pass

    async def _op_query(self, **params) -> Dict[str, Any]:
        """
        Execute a SELECT returning multiple rows.

        Notes
        -----
        - Limits the returned `data` payload to the first 10 rows for UI safety.
        - Returns the full `count` of fetched rows as a separate field.
        """
        sql: str = params["query"]
        bind = params.get("params")
        session_id = params.get("session_id")
        limit = int(params.get("limit", 10))

        if bind:
            sql, bind = self.convert_sql_and_args(sql, bind)

        conn, in_tx = await self._acquire(session_id)
        try:
            sample_data = await self.fetch(conn, self._wrap_sample_sql(sql, limit), bind)
            count_rows = await self.fetch(conn, self._wrap_count_sql(sql), bind)

            return {
                "status": "success",
                "data": sample_data,
                "count": count_rows[0]["total"] if count_rows else 0,
                "message": "Operation query completed successfully",
            }
        finally:
            await self._release(conn, in_tx)

    async def _op_query_one(self, **params) -> Dict[str, Any]:
        """
        Execute a SELECT returning a single row (or None).
        """
        sql: str = params["query"]
        bind = params.get("params")
        session_id = params.get("session_id")

        sql_d, args = self.convert_sql_and_args(sql, bind)
        conn, in_tx = await self._acquire(session_id)
        try:
            row = await self.fetchrow(conn, sql_d, args)
            return {
                "status": "success",
                "data": row,
                "message": "Operation query one completed successfully",
            }
        finally:
            await self._release(conn, in_tx)

    async def _op_execute(self, **params) -> Dict[str, Any]:
        """
        Execute a DDL/DML statement.

        If `returning=True` is provided, this method will perform a fetch instead
        (so adapters can return the affected rows).
        """
        sql: str = params["query"]
        bind = params.get("params")
        returning: bool = params.get("returning", False)
        session_id = params.get("session_id")

        sql_d, args = self.convert_sql_and_args(sql, bind)
        conn, in_tx = await self._acquire(session_id)
        try:
            if returning:
                rows = await self.fetch(conn, sql_d, args)
                return {
                    "status": "success",
                    "data": rows,
                    "count": len(rows),
                    "message": "Operation execute completed successfully",
                }
            res = await self.execute(conn, sql_d, args)
            res.update(
                {"status": "success", "message": "Operation execute completed successfully"}
            )
            return res
        finally:
            await self._release(conn, in_tx)

    async def _op_execute_many(self, **params) -> Dict[str, Any]:
        """
        Execute a batch DML via executemany for `seq_of_params`.
        """
        sql: str = params["query"]
        seq_of_params = params["seq_of_params"]
        session_id = params.get("session_id")

        sql_d, arglists = self.convert_many(sql, seq_of_params)
        conn, in_tx = await self._acquire(session_id)
        try:
            res = await self.executemany(conn, sql_d, arglists)
            res.update(
                {
                    "status": "success",
                    "message": "Operation execute many completed successfully",
                }
            )
            return res
        finally:
            await self._release(conn, in_tx)

    # ===== Public API ==========================================================

    async def run(self, operation: SQLOperation, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an operation using the standardized envelope.

        Parameters
        ----------
        operation : SQLOperation
            The operation to execute (QUERY/EXECUTE/etc.).
        params : Dict[str, Any]
            Operation-specific parameters.

        Returns
        -------
        Dict[str, Any]
            A standardized envelope:
            - On success: {"status": "success", ..., "message": "..."}
            - On error  : {"status": "error", "message": "<traceback>"}
        """
        try:
            fn = self.operation_map.get(operation)
            if not fn:
                raise ValueError(f"Unsupported operation: {operation}")
            result = await fn(**params)
            if "message" not in result:
                op_name = operation.name.lower().replace("_", " ")
                result["message"] = f"Operation {op_name} completed successfully"
            return result
        except Exception:
            return {"status": "error", "message": traceback.format_exc()}

    async def close(self) -> None:
        """
        Close all active sessions and shut down the pool.

        This method attempts to rollback any open transaction, releases
        associated connections, and closes the pool tied to the current loop.
        """
        # Close sessions (rollback if needed)
        for sid, bundle in list(self._sessions.items()):
            try:
                tx = bundle.get("tx")
                if tx:
                    try:
                        await self.rollback(tx)
                    except Exception:
                        pass
            finally:
                try:
                    await self.release(bundle["conn"])
                except Exception:
                    pass
                finally:
                    self._sessions.pop(sid, None)

        # Close the pool if present
        if self._pool_ready:
            try:
                await self.close_pool()
            finally:
                self._pool_ready = False
                self._pool_loop = None