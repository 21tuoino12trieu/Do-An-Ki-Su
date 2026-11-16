from dataclasses import dataclass
import re

import merman


@dataclass
class MermaidValidation:
    valid: bool
    error: str | None = None


ENGINE = merman.MermanEngine()


def clean_mermaid_code(text: str) -> str:
    """Loại bỏ markdown fence do LLM thường sinh ra."""
    text = text.strip()
    match = re.fullmatch(
        r"```(?:mermaid)?\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else text


def validate_mermaid(code: str) -> MermaidValidation:
    code = clean_mermaid_code(code)

    if not code:
        return MermaidValidation(valid=False, error="Mermaid code is empty.")
    if len(code) > 50_000:
        return MermaidValidation(valid=False, error="Mermaid code is too large.")

    try:
        result = ENGINE.validate(code, None)
        if result.valid:
            return MermaidValidation(valid=True)
        return MermaidValidation(
            valid=False,
            error=result.error or "Invalid Mermaid syntax.",
        )
    except merman.MermanError as exc:
        return MermaidValidation(valid=False, error=str(exc))
    except Exception as exc:
        return MermaidValidation(valid=False, error=f"{type(exc).__name__}: {exc}")
