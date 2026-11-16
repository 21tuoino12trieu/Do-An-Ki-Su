# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Optional, Iterable

import sqlglot
from sqlglot import exp


# =============================
# Config
# =============================
@dataclass
class NormalizerConfig:
    input_dialect: str = "postgres"
    output_dialect: str = "postgres"
    # pg_unaccent | pg_translate | lower_only
    mode: str = "pg_unaccent"

    # Bảng ánh xạ mặc định (dùng khi mode = pg_translate)
    translate_src: str = (
        "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        "ùúụủũưừứựửữỳýỵỷỹđ"
        "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠ"
        "ỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
        "çÇñÑäëïöüÄËÏÖÜ"
    )
    translate_dst: str = (
        "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiOOOOOooooooooouuuuuuuuuuuyyyyyd"
        "AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOooooooooouuuuuuuuuuuYYYYYD"
        "cCnNaeiouAEIOU"
    )


# =============================
# Helpers xây expr chuẩn hoá
# =============================
def _lower(expr: exp.Expression) -> exp.Expression:
    return exp.Lower(this=expr)


def _unaccent(expr: exp.Expression) -> exp.Expression:
    # Postgres extension unaccent(text)
    return exp.Anonymous(this="unaccent", expressions=[expr])


def _translate(expr: exp.Expression, src: str, dst: str) -> exp.Expression:
    # translate(text, from, to)
    return exp.Anonymous(
        this="translate",
        expressions=[expr, exp.Literal.string(src), exp.Literal.string(dst)],
    )


def _build_normalize_expr(inner: exp.Expression, cfg: NormalizerConfig) -> exp.Expression:
    """
    Tạo biểu thức normalize theo mode.
    """
    if cfg.mode == "pg_unaccent":
        return _lower(_unaccent(inner))
    if cfg.mode == "pg_translate":
        return _lower(_translate(inner, cfg.translate_src, cfg.translate_dst))
    # lower_only
    return _lower(inner)


# =============================
# Kiểm tra & unwrap literal
# =============================
_STRINGY = (exp.Literal,)

def _is_string_literal(node: exp.Expression) -> bool:
    return isinstance(node, exp.Literal) and node.is_string


def _is_column(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column)


def _all_string_literals(items: Iterable[exp.Expression]) -> bool:
    return all(_is_string_literal(e) for e in items)


# =============================
# Core transform
# =============================
def refine_sql(sql: str, cfg: Optional[NormalizerConfig] = None) -> str:
    """
    Chuẩn hoá so khớp có dấu/hoa/thường cho các phép so sánh cột-với-chuỗi:
      - EQ (=), NEQ (<> hoặc !=)
      - IN / NOT IN (với danh sách literal chuỗi). Bỏ qua IN (subquery).
    Duyệt và thay thế trên TOÀN AST (CTE, subquery, JOIN/ON, HAVING, QUALIFY...).
    """
    cfg = cfg or NormalizerConfig()
    tree = sqlglot.parse_one(sql, read=cfg.input_dialect)

    def _normalize_binop(op_cls, node: exp.Expression) -> Optional[exp.Expression]:
        """
        Chuẩn hoá nhị thức (EQ/NEQ) khi 1 vế là cột & 1 vế là string literal.
        """
        if _is_column(node.left) and _is_string_literal(node.right):
            return op_cls(
                this=_build_normalize_expr(node.left, cfg),
                expression=_build_normalize_expr(node.right, cfg),
            )
        if _is_column(node.right) and _is_string_literal(node.left):
            return op_cls(
                this=_build_normalize_expr(node.right, cfg),
                expression=_build_normalize_expr(node.left, cfg),
            )
        return None

    def _transform(node: exp.Expression) -> exp.Expression:
        # = (EQ)
        if isinstance(node, exp.EQ):
            new_node = _normalize_binop(exp.EQ, node)
            if new_node:
                return new_node

        # != / <> (NEQ)
        if isinstance(node, exp.NEQ):
            new_node = _normalize_binop(exp.NEQ, node)
            if new_node:
                return new_node

        # IN / NOT IN (chỉ khi RHS là danh sách literal chuỗi)
        if isinstance(node, exp.In):
            # Bỏ qua IN (subquery), chỉ làm việc với IN (list)
            # Trong sqlglot, node.args.get("query") tồn tại khi là IN (SELECT ...)
            if node.args.get("query"):
                return node

            lhs = node.this
            exprs = list(node.expressions or [])
            if _is_column(lhs) and exprs and _all_string_literals(exprs):
                norm_lhs = _build_normalize_expr(lhs, cfg)
                norm_rhs = [_build_normalize_expr(e, cfg) for e in exprs]
                new_in = exp.In(this=norm_lhs, expressions=norm_rhs)
                if node.args.get("not"):
                    new_in.set("not", True)
                return new_in

        # Mặc định: không thay đổi
        return node

    # Duyệt & thay thế toàn bộ AST (bao gồm CTE/subquery/join/having/qualify…)
    refined = tree.transform(_transform)
    return refined.sql(dialect=cfg.output_dialect)


# =============================
# Demo & kiểm thử nhanh
# =============================
if __name__ == "__main__":
    tests = [
        # 1) CTE + IN(literals) trong CTE + NEQ ngoài
        """
        WITH cte AS (
            SELECT * 
            FROM city 
            WHERE name IN ('Hà Nội','Đà Nẵng')
        )
        SELECT * FROM cte WHERE city != 'HCM'
        """,
        # 2) Nested subqueries + IN (subquery) (phải được BỎ QUA), + IN (list) (được chuẩn hoá)
        """
        SELECT u.id
        FROM users u
        WHERE u.city IN (SELECT DISTINCT city FROM hot_cities WHERE score > 90)
          AND u.district IN ('Ba Đình', 'Tây Hồ', 'Hoàn Kiếm')
        """,
        # 3) JOIN/ON + OR/AND phức hợp
        """
        SELECT o.order_id
        FROM orders o
        JOIN customer c ON c.id = o.customer_id 
                       AND c.city = 'Hà Nội'
        WHERE (o.status = 'ĐÃ GIAO' OR o.status != 'HUỶ')
          AND o.province IN ('đà nẵng', 'Quảng Nam')
        """,
        # 4) Subquery trong SELECT list + HAVING
        """
        SELECT country,
               (SELECT COUNT(*) FROM users u WHERE u.country = countries.name) AS user_cnt
        FROM countries
        GROUP BY country
        HAVING country IN ('Việt Nam', 'Nhật Bản')
        """,
        # 5) NOT IN với list literal
        """
        SELECT *
        FROM shop s
        WHERE s.location NOT IN ('ĐN', 'Hà Nội')
        """,
    ]

    cfgs = [
        NormalizerConfig(mode="pg_unaccent"),
        NormalizerConfig(mode="pg_translate"),
        NormalizerConfig(mode="lower_only"),
    ]

    for i, sql in enumerate(tests, 1):
        print(f"\n--- Test #{i} (pg_unaccent) ---")
        print(refine_sql(sql, cfgs[0]))
