# -*- coding: utf-8 -*-
from __future__ import annotations

from beegen.configs.storage.sql_config import SQLConfig
from beegen.storage.sql.adapters.oracle import AsyncOracle

"""
SQLFactory
----------

Registry-driven factory for SQL adapter adapters and engines.

- `SQLFactory.create_adapter(uri, **opts)` -> BaseSQLAdapter
- `SQLFactory.create_engine(uri, **opts)` -> AsyncSqlEngine
- `SQLFactory.register(key, adapter_cls)`  -> register/override a adapter

Also exposes backward-compatible helpers:
- `make_adapter(uri, **opts)`
- `make_engine(uri, **opts)`
"""

from typing import Any, Dict, Type

from beegen.storage.sql.base_adapter import BaseSQLAdapter
from beegen.storage.sql.adapters.postgres import AsyncPostgres


class SQLFactory:
    """
    Build the right SQL adapter adapter/engine from a URI.

    A *adapter* is the concrete async adapter implementing BaseSQLAdapter
    for a specific database flavor (Postgres, MySQL, SQLite, Oracle, ...).

    Common `opts` supported by adapters (if implemented):
      - pool_min_size: int
      - pool_max_size: int
      - connect_timeout: int
    """

    # Keyed by normalized scheme/adapter key (lowercase).
    # You can add more mappings (e.g., "mysql", "sqlite", "oracle") later.
    _ADAPTERS: Dict[str, Type[BaseSQLAdapter]] = {
        "postgres": AsyncPostgres,
        "oracle": AsyncOracle
    }

    @classmethod
    def register(cls, key: str, adapter_cls: Type[BaseSQLAdapter]) -> None:
        """
        Register or override a adapter class.

        Args:
            key: adapter key (e.g., "postgres", "mysql"). Case-insensitive.
            adapter_cls: Class implementing BaseSQLAdapter.
        """
        if not issubclass(adapter_cls, BaseSQLAdapter):
            raise TypeError("adapter_cls must subclass BaseSQLAdapter")
        cls._ADAPTERS[key.lower()] = adapter_cls

    @staticmethod
    def _scheme(uri: str) -> str:
        """Return the URI scheme (substring before '://'), lowercased."""
        idx = uri.find("://")
        return uri[:idx].lower() if idx > 0 else ""

    @classmethod
    def _normalize_key(cls, scheme: str) -> str:
        """Map scheme variants to a canonical adapter key."""
        if scheme.startswith("postgres"):
            return "postgres"
        elif scheme.startswith("oracle"):
            return "oracle"
        else:
            return scheme

    @classmethod
    def create(cls, cfg: SQLConfig) -> BaseSQLAdapter:
        """
        Create a concrete async adapter adapter for the given connection URI.
        """
        scheme = cls._scheme(cfg.uri)
        key = cls._normalize_key(scheme)
        adapter_cls = cls._ADAPTERS.get(key)
        if adapter_cls is None:
            raise ValueError(f"Unsupported DB scheme: {scheme!r}")
        return adapter_cls(cfg)

    # @classmethod
    # def create_engine(cls, **opts: Any) -> AsyncSqlEngine:
    #     """
    #     Build an AsyncSqlEngine bound to an adapter created from `uri`.
    #     """
    #     adapter = cls.create(**opts)
    #     return AsyncSqlEngine(adapter)