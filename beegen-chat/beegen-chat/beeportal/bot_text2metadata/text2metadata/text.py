from __future__ import annotations
from typing import Optional
from sqlglot import exp

_UNACCENT_MAP = str.maketrans(
    "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    "ùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄ"
    "ÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ",
    "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiioooooooooooooooo"
    "uuuuuuuuuuu-yyyyydAAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIII"
    "OOOOOOOOOOOOOOOOOUUUUUUUUUU-YYYYYĐ".replace("Đ", "D")
)

def normalize_text(s: str) -> str:
    return s.strip().lower().translate(_UNACCENT_MAP)

def literal_to_python(lit: exp.Expression) -> str:
    """Lấy giá trị text từ Literal; fallback trả về SQL nếu không phải literal."""
    if isinstance(lit, exp.Literal):
        return str(lit.this)
    return lit.sql()

def first_column(expr: exp.Expression) -> Optional[exp.Column]:
    """Tìm cột (exp.Column) trong biểu thức (hỗ trợ wrap như LOWER/CAST)."""
    if isinstance(expr, exp.Column):
        return expr
    return expr.find(exp.Column)