from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT
from beegen.tools.schema.param import ParamSet


class SQLOperation(str, Enum):
    QUERY = "query"
    QUERY_ONE = "query_one"
    EXECUTE = "execute"
    EXECUTE_MANY = "execute_many"
    BEGIN_TRANSACTION = "begin_transaction"
    COMMIT_TRANSACTION = "commit_transaction"
    ABORT_TRANSACTION = "abort_transaction"


SQL_OPERATION_INPUTS = {
    SQLOperation.QUERY: (
        ParamSet.new()
            .var("query: str", required=True)
            .var("params: Any = None", "Query parameters (tuple/list/dict), optional")
            .var("session_id: str = None", "Transaction session id, if inside a transaction")
            .var("limit: int = 10", "Maximum number of items to return, optional")
            .build()
    ),
    SQLOperation.QUERY_ONE: (
        ParamSet.new()
            .var("query: str", required=True)
            .var("params: Any = None", "Query parameters (tuple/list/dict), optional")
            .var("session_id: str = None", "Transaction session id, if inside a transaction")
            .build()
    ),
    SQLOperation.EXECUTE: (
        ParamSet.new()
            .var("query: str", required=True)
            .var("params: Any = None", "Statement parameters (tuple/list/dict), optional")
            .var("returning: bool = False", "If True, fetch and return rows (requires RETURNING in SQL)")
            .var("session_id: str = None", "Transaction session id, if inside a transaction")
            .build()
    ),
    SQLOperation.EXECUTE_MANY: (
        ParamSet.new()
            .var("query: str", required=True)
            .var("seq_of_params: List[Any]", required=True, description="Iterable of parameter sets for executemany")
            .var("session_id: str = None", "Transaction session id, if inside a transaction")
            .build()
    ),
    SQLOperation.BEGIN_TRANSACTION: ParamSet.new().build(),
    SQLOperation.COMMIT_TRANSACTION: (
        ParamSet.new()
            .var("session_id: str", required=True)
            .build()
    ),
    SQLOperation.ABORT_TRANSACTION: (
        ParamSet.new()
            .var("session_id: str", required=True)
            .build()
    ),
}

# --- Every output now has optional `error: Dict = None` ---
SQL_OPERATION_OUTPUTS = {
    SQLOperation.QUERY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: List[Dict]", "List of result rows (JSON-serializable)")
            .var("count: int", "Number of rows returned")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.QUERY_ONE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("data: Dict", "Single row as a dictionary, or None if no row found")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.EXECUTE: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("rowcount: int", "Number of rows affected")
            .var("data: List[Dict] = None", "Returned rows if 'returning=True' and SQL includes RETURNING")
            .var("count: int = None", "Number of returned rows when 'returning=True'")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.EXECUTE_MANY: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("rowcount: int", "Total number of rows affected")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.BEGIN_TRANSACTION: (
        ParamSet.new()
            .var("status: str", "Operation status ('success' or 'error')", required=True)
            .var("session_id: str = None", "Unique identifier for the created transaction session")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.COMMIT_TRANSACTION: (
        ParamSet.new()
            .var("status: str", required=True)
            .var("committed: bool = None", "Whether the transaction was committed successfully")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
    SQLOperation.ABORT_TRANSACTION: (
        ParamSet.new()
            .var("status: str", required=True)
            .var("aborted: bool = None", "Whether the transaction was aborted successfully")
            .var("message: str", "Optional message")
            .var("error: Dict = None", "Error details when status='error'")
            .build()
    ),
}


class SQLConfig(YamlModel):
    """
    Generic SQL connection configuration.
    """

    uri: str
    user: str = ""
    password: str = ""
    pool_min_size: int = 10
    pool_max_size: int = 10
    pool_timeout: int = 30
    connect_timeout: int = 10
    autocommit: bool = False

    @classmethod
    def default(cls) -> "SQLConfig":
        data = SQLConfig.read_yaml(BEEGEN_ROOT / "config/sql.yaml")
        return SQLConfig(**data)


if __name__ == "__main__":
    config = SQLConfig.default()
    print(config)
