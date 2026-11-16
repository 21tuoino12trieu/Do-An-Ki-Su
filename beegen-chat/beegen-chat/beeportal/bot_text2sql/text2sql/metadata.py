from typing import Dict, List, Any, Union, Tuple

import yaml
from beegenerate.const import BEEGEN_ROOT

def _load_metadata_config() -> Dict[str, Any]:
    config_path = BEEGEN_ROOT / "config" / "metadata_query.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

METADATA_CONFIG = _load_metadata_config()
def build_table_overview_query(role_ids, metadata=None):
    """Build SQL query to get table overview based on role IDs and metadata."""
    table_domain = (metadata or {}).get("TableDomain", [])
    
    schema = METADATA_CONFIG["database"]["schema"]
    table_name = METADATA_CONFIG["tables"]["tables_with_columns"]

    base_query = f"""
        SELECT db_dialect, schema_name, table_name, description
        FROM {schema}.{table_name}
        WHERE is_active = TRUE
    """

    if not role_ids:
        base_query += " AND FALSE"
        return {"sql_table": base_query.strip()}

    role_str = ", ".join([f"'{r}'" for r in role_ids])
    base_query += f" AND channel IN ({role_str})"

    if table_domain:
        pairs = [
            f"('{t['schemaName']}','{t['tableName']}')"
            for t in table_domain
        ]

        base_query += f"""
        AND (schema_name, table_name) IN (
            {", ".join(pairs)}
        )
        """

    return {"sql_table": base_query.strip()}


def get_metadata_filter(tables: Union[str, List]) -> Dict[str, List[str]]:
    """
    Build a SELECT query using tuple IN on (schema_name, table_name)
    from a list of strings like ["schema.table", ...].

    Args:
        tables : Union[str, List]. Items in the form "schema.table" or ["schema.table_1", "schema.table_2"].

    Returns:
        query (str)  : The parametrized SQL.
        params (list) : Flat list of params in the order [schema1, table1, schema2, table2, ...].
    """
    if isinstance(tables, str):
        tables = [tables]

    schema = METADATA_CONFIG["database"]["schema"]
    table_name = METADATA_CONFIG["tables"]["tables_with_columns"]

    schema_table_pairs: List[Tuple[str, str]] = []
    for p in tables:
        if "." not in p:
            raise ValueError(f"Invalid item (expect 'schema.table'): {p!r}")
        s, t = p.split(".", 1)
        schema_table_pairs.append((s, t))

    # Build "(%s, %s), (%s, %s), ..."
    placeholders = ", ".join(["(%s, %s)"] * len(schema_table_pairs))
    params: List[str] = [x for st in schema_table_pairs for x in st]

    query = f"""
        SELECT db_dialect, schema_name, table_name, description,
            is_active, columns
        FROM {schema}.{table_name}
        WHERE is_active = TRUE
        AND (schema_name, table_name) IN ({placeholders})
    """.strip()

    return {"query": query, "params": params}


def get_authorized_metadata_filter(
    tables: Union[str, List],
    role_ids: List[str],
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, List[str]]:
    """Build one metadata query scoped by requested tables, roles and TableDomain."""
    if isinstance(tables, str):
        tables = [tables]

    schema_table_pairs: List[Tuple[str, str]] = []
    for table in tables or []:
        if "." not in table:
            raise ValueError(f"Invalid item (expect 'schema.table'): {table!r}")
        schema_name, table_name = table.split(".", 1)
        schema_table_pairs.append((schema_name, table_name))

    schema = METADATA_CONFIG["database"]["schema"]
    metadata_table = METADATA_CONFIG["tables"]["tables_with_columns"]
    table_placeholders = ", ".join(["(%s, %s)"] * len(schema_table_pairs))
    params: List[str] = [value for pair in schema_table_pairs for value in pair]
    query = f"""
        SELECT db_dialect, schema_name, table_name, description, is_active, columns
        FROM {schema}.{metadata_table}
        WHERE is_active = TRUE
        AND (schema_name, table_name) IN ({table_placeholders})
    """

    if role_ids:
        role_placeholders = ", ".join(["%s"] * len(role_ids))
        query += f" AND channel IN ({role_placeholders})"
        params.extend(role_ids)
    else:
        query += " AND FALSE"

    table_domain = (metadata or {}).get("TableDomain", [])
    if table_domain:
        domain_pairs = [
            (item["schemaName"], item["tableName"])
            for item in table_domain
        ]
        domain_placeholders = ", ".join(["(%s, %s)"] * len(domain_pairs))
        query += f" AND (schema_name, table_name) IN ({domain_placeholders})"
        params.extend(value for pair in domain_pairs for value in pair)

    return {"query": query.strip(), "params": params}


def validate_db_dialect(table_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate that all tables share the same db_dialect.

    Expected input:
        {
            "table_metadata": [
                {"db_dialect": "oracle", ...},
                ...
            ]
        }

    Returns:
        {
            "db_dialect": str | None,
            "is_consistent": 1/0,
            "dialects_found": List[str],
            "table_count": int
        }
    """
    table_count = len(table_metadata)

    if table_count == 0:
        return {
            "db_dialect": None,
            "is_consistent": 0,
            "dialects_found": [],
            "table_count": 0
        }

    # Collect dialects (normalized), skip None/empty values
    dialects = {
        str(table["db_dialect"]).strip().lower()
        for table in table_metadata
        if table.get("db_dialect") is not None  # check None explicitly
        and str(table["db_dialect"]).strip()     # check empty string
    }

    # Check if some tables are missing dialect info
    tables_with_dialect = len([
        t for t in table_metadata
        if t.get("db_dialect") is not None and str(t["db_dialect"]).strip()
    ])

    # Not consistent if not all tables have dialect info
    if tables_with_dialect < table_count:
        dialects_list = sorted(dialects)
        return {
            "db_dialect": None,
            "is_consistent": 0,
            "dialects_found": dialects_list,
            "table_count": table_count,
        }

    dialects_list = sorted(dialects)
    is_consistent = 1 if len(dialects_list) == 1 else 0

    return {
        "db_dialect": dialects_list[0] if is_consistent == 1 else None,
        "is_consistent": is_consistent,
        "dialects_found": dialects_list,
        "table_count": table_count
    }


def get_dialect_specific_prompt(db_dialect: str, prompt_manager) -> Dict[str, str]:
    """
    Load dialect-specific prompt from Langfuse based on db_dialect.

    Args:
        db_dialect: Database dialect (oracle, postgres, mysql, etc.)
        prompt_manager: PromptManager instance

    Returns:
        Dict with key "dialect_instructions" containing specific rules
    """
    dialect = (db_dialect or "").lower().strip()

    prompt_key_map = {
        "oracle": "TEXT2QUERY:TEXT2SQL_ORACLE_RULES",
        "postgres": "TEXT2QUERY:TEXT2SQL_POSTGRES_RULES",
        "postgresql": "TEXT2QUERY:TEXT2SQL_POSTGRES_RULES",
        "mysql": "TEXT2QUERY:TEXT2SQL_MYSQL_RULES",
    }

    prompt_key = prompt_key_map.get(dialect, "TEXT2QUERY:TEXT2SQL_DEFAULT_RULES")

    try:
        # Load from Langfuse PromptManager
        dialect_instructions = prompt_manager.get(prompt_key)

        if prompt_key == "TEXT2SQL_DEFAULT_RULES":
            dialect_instructions = dialect_instructions.format(db_dialect=dialect)

    except Exception as e:
        dialect_instructions = f"""
            ## Không tìm thấy quy tắc cho database: {dialect}

            Vui lòng:
            1. Kiểm tra prompt key '{prompt_key}' đã được tạo trong Langfuse chưa
            2. Sử dụng SQL standard syntax
            3. Thông báo cho quản trị viên về database dialect này

            Error: {str(e)}
        """
    return {
        "dialect_instructions": dialect_instructions
    }
