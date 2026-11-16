import pytest
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
from beeportal.bee_ai_enterprises_adk.utils.llm_utils import build_litellm_model


@pytest.fixture
def aie_llm_env(monkeypatch):
    """Fixture to set up valid AIE_LLM environment variables."""
    monkeypatch.delenv("LITELLM_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("AIE_LLM_API_TYPE", "litellm_proxy")
    monkeypatch.setenv("AIE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AIE_LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AIE_LLM_MODEL", "test-model")


def test_build_litellm_model_success(aie_llm_env):
    """Test successful creation of LiteLlm model with valid environment."""
    model = build_litellm_model()
    
    assert model.model == "litellm_proxy/test-model"
    assert os.environ.get("LITELLM_PROXY_API_KEY") == "test-key"


def test_build_litellm_model_missing_api_type(aie_llm_env, monkeypatch):
    """Test validation fails if api_type is not litellm_proxy."""
    monkeypatch.setenv("AIE_LLM_API_TYPE", "openai")
    
    with pytest.raises(ValueError, match="AIE_LLM_API_TYPE must be 'litellm_proxy'"):
        build_litellm_model()


@pytest.mark.parametrize("missing_var", [
    "AIE_LLM_API_KEY",
    "AIE_LLM_BASE_URL",
    "AIE_LLM_MODEL"
])
def test_build_litellm_model_missing_required_vars(aie_llm_env, monkeypatch, missing_var):
    """Test validation fails if any required variable is missing."""
    monkeypatch.delenv(missing_var)
    
    with pytest.raises(ValueError, match=f"Missing required environment variables:.*{missing_var}"):
        build_litellm_model()


def test_build_litellm_model_ignores_old_llm_config(monkeypatch):
    """Test that LLM_CONFIG is no longer read or parsed."""
    monkeypatch.setenv("LLM_CONFIG", '{"api_key": "old-key", "api_type": "litellm_proxy", "base_url": "old-url", "model": "old-model"}')
    monkeypatch.delenv("AIE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("AIE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("AIE_LLM_MODEL", raising=False)
    
    # Missing new flat vars should fail immediately
    with pytest.raises(ValueError, match="Missing required environment variables:"):
        build_litellm_model()
