# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Dict, Any, Optional

from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.tools.schema.param import ParamSet

from beegen.configs.storage.sql_config import (
    SQLOperation,
    SQL_OPERATION_INPUTS,
    SQL_OPERATION_OUTPUTS,
)


class SQLNode(BaseNode):
    """Class for SQL node in the Beeflow graph."""
    # Keep consistent with core style (RedisNode uses "data")
    type: NodeType = "data"

    __slots__ = [
        "resource_key",  # The SQL model/resource identifier (a.k.a. adapter key)
        "operation",     # The SQL operation (enum SQLOperation)
        "core",          # Callable resolved from adapter.operation_map[operation]
        "input_schema",
        "output_schema",
    ]

    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[SQLOperation] = None,
        **kwargs: Any,
    ):
        """
        Initialize SQLNode from either config or kwargs.

        Args:
            resource_key: SQL adapter key registered in ResourceHub (alias: 'model')
            operation: SQLOperation to execute (e.g., SQLOperation.QUERY)
            **kwargs: Additional NodeConfig-compatible args (name, inputs, outputs, etc.)
        """
        super().__init__(**kwargs)

        # When constructed via NodeConfig, BaseNode injects attributes from self.config.
        # Fallback to explicit kwargs if present.
        self.resource_key: Optional[str] = getattr(self, "model", None) or resource_key
        self.operation: Optional[SQLOperation] = getattr(self, "operation", None) or operation

        if self.resource_key is None or self.operation is None:
            raise ValueError("SQLNode requires both 'resource_key/model' and 'operation'.")

        # Bind IO schemas for the selected operation
        self.input_schema: Optional[ParamSet] = SQL_OPERATION_INPUTS.get(self.operation)
        self.output_schema: Optional[ParamSet] = SQL_OPERATION_OUTPUTS.get(self.operation)

        if self.input_schema is None or self.output_schema is None:
            raise ValueError(f"Unsupported or unregistered SQL operation: {self.operation}")

        # Resolve concrete callable from the SQL adapter
        adapter = RESOURCE_HUB.sql(self.resource_key)
        try:
            self.core = adapter.operation_map[self.operation]
        except Exception as e:
            raise ValueError(
                f"Operation {self.operation!r} not available for SQL adapter {self.resource_key!r}"
            ) from e

    def specific_metadata(self) -> Dict[str, Any]:
        """Return SQL-specific metadata dictionary for observability/tracing."""
        return {
            "model": self.resource_key,
            "operation": str(self.operation),
        }


# ---- Example usage (mirrors your Redis demo style) --------------------------

async def main():
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT

    # Example: simple SELECT
    query_node = SQLNode(
        name="sql_query",
        resource_key="anapp",                 # matches a SQL adapter key in ResourceHub
        operation=SQLOperation.QUERY,
        inputs={
            "query": INPUT,
            "limit": 1               # adapter expects "query" for QUERY op
        },
        outputs=OUTPUT
    )

    indexer = WorkflowIndexer(name="wf_sql_ops")\
        .add_node(query_node)\
        .build()

    state = WorkflowState(
        indexer=indexer,
        inputs={
            "query": "SELECT * FROM agent_ai.behavior_in_app"
        }
    )

    # Execute the node
    await query_node.run(state=state)
    print(query_node.get_outputs(state, None))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
