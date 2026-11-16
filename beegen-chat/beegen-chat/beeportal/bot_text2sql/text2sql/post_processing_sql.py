# -*- coding: utf-8 -*-
from dataclasses import dataclass
import re
from typing import Optional, Iterable

import sqlglot
from sqlglot import exp
from sqlglot.dialects import Dialect
from sqlglot.errors import ErrorLevel, SqlglotError
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.tokens import Tokenizer, TokenType


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_UNSAFE_SQL_TOKENS = {
    TokenType.ALTER,
    TokenType.COMMAND,
    TokenType.COPY,
    TokenType.CREATE,
    TokenType.DELETE,
    TokenType.DROP,
    TokenType.EXECUTE,
    TokenType.GRANT,
    TokenType.INSERT,
    TokenType.MERGE,
    TokenType.REPLACE,
    TokenType.REVOKE,
    TokenType.SET,
    TokenType.TRUNCATE,
    TokenType.UPDATE,
    TokenType.USE,
}


def _inspect_tokens(sql: str, dialect: Optional[str]) -> tuple[int, bool]:
    """Count non-empty statements and flag obvious unsafe commands without regex."""
    try:
        tokenizer = (
            Dialect.get_or_raise(dialect).tokenizer()
            if dialect
            else Tokenizer()
        )
        tokens = tokenizer.tokenize(sql)
    except (SqlglotError, ValueError):
        return 0, False

    statement_count = 0
    has_content = False
    unsafe_token_detected = False
    for token in tokens:
        if token.token_type == TokenType.SEMICOLON:
            if has_content:
                statement_count += 1
                has_content = False
            continue
        if token.token_type in _UNSAFE_SQL_TOKENS:
            unsafe_token_detected = True
        has_content = True
    if has_content:
        statement_count += 1
    return statement_count, unsafe_token_detected


def _inspect_table_references(statement: exp.Expression) -> tuple[list[str], int]:
    """Extract physical tables while excluding CTE and derived aliases."""
    query = statement.unnest()
    table_sources = []
    if isinstance(query, exp.Query):
        for scope in traverse_scope(query):
            table_sources.extend(
                source
                for source in scope.sources.values()
                if isinstance(source, exp.Table)
            )
    else:
        table_sources.extend(statement.find_all(exp.Table))

    physical_tables = []
    seen = set()
    metadata_references_valid = True
    for source in table_sources:
        parts = list(source.parts)
        part_names = [
            part.sql() if part.args.get("quoted") else part.name.casefold()
            for part in parts
            if isinstance(part, exp.Identifier)
        ]
        metadata_safe = (
            len(part_names) == len(parts)
            and len(parts) in {1, 2}
            and not any("." in name for name in part_names)
        )
        metadata_references_valid &= metadata_safe
        table_name = ".".join(part_names)
        if table_name and table_name not in seen:
            seen.add(table_name)
            physical_tables.append(table_name)

    return (
        physical_tables,
        int(bool(physical_tables) and metadata_references_valid),
    )


def inspect_sql(sql: str, dialect: Optional[str] = None) -> dict:
    """Parse SQL and return syntax, safety, dialect and physical-table metadata."""
    raw_sql = sql.strip() if isinstance(sql, str) else ""
    db_dialect = dialect.strip().lower() if isinstance(dialect, str) else ""
    read_dialect = None

    if db_dialect:
        try:
            Dialect.get_or_raise(db_dialect)
            read_dialect = db_dialect
        except ValueError:
            pass

    result = {
        "syntax_valid": 0,
        "statement_count": 0,
        "is_read_only": 0,
        "physical_tables": [],
        "metadata_references_valid": 0,
        "parse_error": "",
    }

    try:
        statements = [
            statement
            for statement in sqlglot.parse(raw_sql, read=read_dialect)
            if statement is not None
        ]
    except SqlglotError as exc:
        tokenized_statement_count, unsafe_sql_token = _inspect_tokens(raw_sql, read_dialect)
        if tokenized_statement_count > 1:
            result["statement_count"] = tokenized_statement_count
        elif unsafe_sql_token:
            # Mark malformed DDL/DML so final execution guard can reject the source.
            result["statement_count"] = 1
        try:
            partial_statements = [
                statement
                for statement in sqlglot.parse(
                    raw_sql,
                    read=read_dialect,
                    error_level=ErrorLevel.IGNORE,
                )
                if statement is not None
            ]
            if len(partial_statements) == 1:
                (
                    result["physical_tables"],
                    result["metadata_references_valid"],
                ) = _inspect_table_references(partial_statements[0])
        except SqlglotError:
            pass
        result["parse_error"] = _ANSI_ESCAPE_RE.sub("", str(exc))
        return result

    result["statement_count"] = len(statements)
    if not statements:
        result["parse_error"] = "No SQL statement found."
        return result

    result["syntax_valid"] = 1
    physical_tables = []
    seen_tables = set()
    metadata_references_valid = True
    for statement in statements:
        tables, metadata_valid = _inspect_table_references(statement)
        metadata_references_valid &= bool(metadata_valid) or not tables
        for table in tables:
            if table not in seen_tables:
                seen_tables.add(table)
                physical_tables.append(table)
    result["physical_tables"] = physical_tables
    result["metadata_references_valid"] = int(
        bool(physical_tables) and metadata_references_valid
    )
    # Multi-statement SQL may be repaired, but is never executable.
    if len(statements) != 1:
        return result

    statement = statements[0]
    query = statement.unnest()
    unsafe_nodes = (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock)
    unsafe_function_nodes = (
        exp.Anonymous,
        exp.UserDefinedFunction,
        exp.NextValueFor,
        exp.ReadCSV,
        getattr(exp, "ReadParquet", exp.Anonymous),
    )
    has_unsafe_function = any(
        isinstance(node, unsafe_function_nodes)
        or (isinstance(node, exp.Column) and node.name.upper() == "NEXTVAL")
        for node in statement.walk()
    )
    has_dynamic_table_source = any(
        not isinstance(table.this, exp.Identifier)
        for table in statement.find_all(exp.Table)
    )
    result["is_read_only"] = int(
        isinstance(query, exp.Query)
        and not any(isinstance(node, unsafe_nodes) for node in statement.walk())
        and not has_unsafe_function
        and not has_dynamic_table_source
    )

    return result
