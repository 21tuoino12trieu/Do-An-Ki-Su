import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from beegenerate.const import BEEGEN_ROOT


@dataclass
class BeechatSettings:
    kb_vector_prj_number: str = "598796242609"
    kb_engine_id: str = "ai-khcn-beeapp_1785750796442"
    kb_vector_engine_id: str = "ai-khcn-beeapp_1785750796442"
    kb_qna_engine_id: str = "ai-khcn-beeapp_1785750796442"
    kb_api_version: str = "v1alpha"
    kb_atm_prj_number: str = "901045532135"
    kb_atm_engine_id: str = "dc-atm-pgd_1778856348641"
    kb_atm_api_version: str = "v1alpha"
    kb_qna_relevance_threshold: float = 0.8
    openai_base_url: str = "https://llm-gateway-dev.mbbank.com.vn/"
    openai_api_key: str = "REPLACE_WITH_LOCAL_SECRET"
    heavy_model: str = "gemini-3.6-flash"
    light_model: str = "gemini-3.5-flash-lite"
    scenario_model: str = "gemini-3.6-flash"


def load_settings() -> BeechatSettings:
    possible_paths = [
        Path("/deployment/config/beechat.yaml"),
        BEEGEN_ROOT / "config" / "beechat.yaml",
        Path("config/beechat.yaml")
    ]
    yaml_config = {}
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                break
            except Exception:
                pass

    return BeechatSettings(
        kb_vector_prj_number=os.getenv("KB_VECTOR_PRJ_NUMBER", str(yaml_config.get("kb_vector_prj_number", "598796242609"))),
        kb_engine_id=os.getenv("KB_ENGINE_ID", str(yaml_config.get("kb_engine_id", "ai-khcn-beeapp_1785750796442"))),
        kb_vector_engine_id=os.getenv("KB_VECTOR_ENGINE_ID", str(yaml_config.get("kb_vector_engine_id", "ai-khcn-beeapp_1785750796442"))),
        kb_qna_engine_id=os.getenv("KB_QNA_ENGINE_ID", str(yaml_config.get("kb_qna_engine_id", "ai-khcn-beeapp_1785750796442"))),
        kb_api_version=os.getenv("KB_API_VERSION", str(yaml_config.get("kb_api_version", "v1alpha"))),
        kb_atm_prj_number=os.getenv("KB_ATM_PRJ_NUMBER", str(yaml_config.get("kb_atm_prj_number", "901045532135"))),
        kb_atm_engine_id=os.getenv("KB_ATM_ENGINE_ID", str(yaml_config.get("kb_atm_engine_id", "dc-atm-pgd_1778856348641"))),
        kb_atm_api_version=os.getenv("KB_ATM_API_VERSION", str(yaml_config.get("kb_atm_api_version", "v1alpha"))),
        kb_qna_relevance_threshold=float(os.getenv("KB_QNA_RELEVANCE_THRESHOLD", yaml_config.get("kb_qna_relevance_threshold", 0.8))),
        openai_base_url=os.getenv("OPENAI_API_BASE", str(yaml_config.get("openai_base_url", "https://llm-gateway-dev.mbbank.com.vn/"))),
        openai_api_key=os.getenv("OPENAI_API_KEY", str(yaml_config.get("openai_api_key", "REPLACE_WITH_LOCAL_SECRET"))),
        heavy_model=os.getenv("HEAVY_MODEL", str(yaml_config.get("heavy_model", "gemini-3.6-flash"))),
        light_model=os.getenv("LIGHT_MODEL", str(yaml_config.get("light_model", "gemini-3.5-flash-lite"))),
        scenario_model=os.getenv("SCENARIO_MODEL", str(yaml_config.get("scenario_model", "gemini-3.6-flash")))
    )
