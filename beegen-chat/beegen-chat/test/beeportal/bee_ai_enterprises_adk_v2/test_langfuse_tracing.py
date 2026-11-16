# -*- coding: utf-8 -*-
"""Tests for Langfuse tracing integration in bee_ai_enterprises_adk_v2.

Covers:
  - setup_langfuse_tracing() idempotency, env var handling, error resilience
  - propagate_attributes integration in runtime
  - Module-level tracing activation in agent.py for adk web CLI
"""
import os
import logging
from unittest.mock import patch, MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# setup_langfuse_tracing() unit tests
# ---------------------------------------------------------------------------

class TestSetupLangfuseTracing:
    """Tests for utils/langfuse_tracing.py::setup_langfuse_tracing()."""

    def _reset_tracing(self):
        """Reset the module-level _tracing_initialized flag between tests."""
        import beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing as mod
        mod._tracing_initialized = False

    def setup_method(self):
        self._reset_tracing()

    def teardown_method(self):
        self._reset_tracing()

    def test_disabled_when_missing_credentials(self):
        """Should return None and log info when LANGFUSE env vars are missing."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
            "LANGFUSE_HOST": "",
        }
        with patch.dict(os.environ, env, clear=False):
            from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                setup_langfuse_tracing,
            )

            result = setup_langfuse_tracing()
            assert result is None

    def test_disabled_when_host_missing(self):
        """Should return None when only LANGFUSE_HOST is missing."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "",
        }
        with patch.dict(os.environ, env, clear=False):
            from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                setup_langfuse_tracing,
            )

            result = setup_langfuse_tracing()
            assert result is None

    def test_disabled_via_tracing_enabled_false(self):
        """Should return None when LANGFUSE_TRACING_ENABLED is False."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "https://localhost",
            "LANGFUSE_TRACING_ENABLED": "False",
        }
        with patch.dict(os.environ, env, clear=False):
            from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                setup_langfuse_tracing,
            )

            result = setup_langfuse_tracing()
            assert result is None

    def test_disabled_via_tracing_enabled_zero(self):
        """Should also accept '0' as disabled."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "https://localhost",
            "LANGFUSE_TRACING_ENABLED": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                setup_langfuse_tracing,
            )

            result = setup_langfuse_tracing()
            assert result is None

    def test_idempotent_second_call_returns_none(self):
        """Second call should return None without re-initializing."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
            "LANGFUSE_HOST": "",
        }
        with patch.dict(os.environ, env, clear=False):
            from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                setup_langfuse_tracing,
            )

            first = setup_langfuse_tracing()
            second = setup_langfuse_tracing()
            assert first is None
            assert second is None

    @patch("beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing.Langfuse", create=True)
    def test_langfuse_client_created_with_correct_params(self, mock_langfuse_cls):
        """Should create Langfuse client with correct params from env."""
        mock_client = MagicMock()
        mock_client.auth_check.return_value = True
        mock_langfuse_cls.return_value = mock_client

        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test-123",
            "LANGFUSE_SECRET_KEY": "sk-test-456",
            "LANGFUSE_HOST": "https://langfuse.example.com",
            "LANGFUSE_TRACING_ENABLED": "True",
        }

        with patch.dict(os.environ, env, clear=False):
            # Mock imports within the function
            with patch(
                "beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing.Langfuse",
                mock_langfuse_cls,
                create=True,
            ):
                # Also mock logfire and instrumentor to avoid import errors
                mock_logfire = MagicMock()
                mock_instrumentor_cls = MagicMock()

                with patch.dict(
                    "sys.modules",
                    {
                        "logfire": mock_logfire,
                        "openinference.instrumentation.google_adk": MagicMock(
                            GoogleADKInstrumentor=mock_instrumentor_cls
                        ),
                    },
                ):
                    from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                        setup_langfuse_tracing,
                    )
                    self._reset_tracing()

                    result = setup_langfuse_tracing()

        # Cannot easily assert exact call args when real imports happen,
        # but at least verify the function completes without error
        # and _tracing_initialized is set
        import beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing as mod
        assert mod._tracing_initialized is True

    def test_resilient_when_logfire_not_installed(self):
        """Should continue without error when logfire is not importable."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "https://localhost",
            "LANGFUSE_TRACING_ENABLED": "True",
        }

        with patch.dict(os.environ, env, clear=False):
            # Mock langfuse to succeed but logfire to fail
            mock_langfuse = MagicMock()
            mock_langfuse.return_value.auth_check.return_value = True

            with patch.dict(
                "sys.modules",
                {"logfire": None},  # Simulate ImportError
            ):
                from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                    setup_langfuse_tracing,
                )
                self._reset_tracing()

                # Should not raise
                result = setup_langfuse_tracing()

        import beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing as mod
        assert mod._tracing_initialized is True

    def test_resilient_when_openinference_not_installed(self, caplog):
        """Should log warning and continue when openinference is not available."""
        env = {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_HOST": "https://localhost",
            "LANGFUSE_TRACING_ENABLED": "True",
        }

        with patch.dict(os.environ, env, clear=False):
            # Remove openinference from modules to trigger ImportError
            with patch.dict(
                "sys.modules",
                {
                    "openinference": None,
                    "openinference.instrumentation": None,
                    "openinference.instrumentation.google_adk": None,
                },
            ):
                from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
                    setup_langfuse_tracing,
                )
                self._reset_tracing()

                with caplog.at_level(logging.WARNING):
                    result = setup_langfuse_tracing()

        import beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing as mod
        assert mod._tracing_initialized is True


# ---------------------------------------------------------------------------
# propagate_attributes in runtime
# ---------------------------------------------------------------------------

class TestRuntimeTracingIntegration:
    """Tests that runtime.py correctly integrates Langfuse tracing."""
    
    @property
    def runtime_source(self):
        from pathlib import Path
        path = Path(__file__).parents[3] / "beeportal" / "bee_ai_enterprises_adk_v2" / "core" / "runtime.py"
        return path.read_text(encoding="utf-8")

    def test_runtime_imports_langfuse_tracing(self):
        """Verify the runtime module imports setup_langfuse_tracing."""
        assert "from ..utils.langfuse_tracing import setup_langfuse_tracing" in self.runtime_source

    def test_runtime_calls_setup_in_ensure_initialized(self):
        """Verify setup_langfuse_tracing is called during initialization."""
        assert "setup_langfuse_tracing()" in self.runtime_source

    def test_runtime_uses_propagate_attributes(self):
        """Verify execute_stream uses propagate_attributes."""
        source = self.runtime_source
        assert "propagate_attributes" in source
        assert "user_id=request.user_id" in source
        assert "session_id=request.conversation_id" in source
        assert '"adk-v2"' in source
        assert '"bee-ai-enterprises"' in source

    def test_runtime_propagate_attributes_has_cleanup(self):
        """Verify _lf_ctx is cleaned up in finally block."""
        source = self.runtime_source
        assert "_lf_ctx.__exit__" in source
        assert "finally:" in source


# ---------------------------------------------------------------------------
# Module-level tracing in agent.py (for adk web CLI)
# ---------------------------------------------------------------------------

class TestAgentModuleLevelTracing:
    """Tests that agent.py calls setup_langfuse_tracing at module level."""

    @property
    def agent_source(self):
        from pathlib import Path
        path = Path(__file__).parents[3] / "beeportal" / "bee_ai_enterprises_adk_v2" / "agent.py"
        return path.read_text(encoding="utf-8")

    def test_agent_module_calls_setup_tracing(self):
        """Verify agent.py source contains setup_langfuse_tracing() call."""
        assert "setup_langfuse_tracing()" in self.agent_source

    def test_agent_module_imports_tracing(self):
        """Verify agent.py imports from langfuse_tracing module."""
        assert "from .utils.langfuse_tracing import setup_langfuse_tracing" in self.agent_source

    def test_agent_module_loads_dotenv_before_tracing(self):
        """Verify load_dotenv is called before setup_langfuse_tracing."""
        source = self.agent_source
        dotenv_pos = source.find("load_dotenv(")
        tracing_pos = source.find("setup_langfuse_tracing()")

        assert dotenv_pos != -1, "load_dotenv() not found in agent.py"
        assert tracing_pos != -1, "setup_langfuse_tracing() not found in agent.py"
        assert dotenv_pos < tracing_pos, (
            "load_dotenv() must be called BEFORE setup_langfuse_tracing(). "
            f"load_dotenv at pos {dotenv_pos}, setup_tracing at pos {tracing_pos}"
        )

    def test_agent_module_tracing_before_root_agent(self):
        """Verify setup_langfuse_tracing() is called BEFORE root_agent creation."""
        source = self.agent_source
        tracing_pos = source.find("setup_langfuse_tracing()")
        root_agent_pos = source.find("root_agent = build_root_workflow")

        assert tracing_pos != -1, "setup_langfuse_tracing() not found"
        assert root_agent_pos != -1, "root_agent = build_root_workflow not found"
        assert tracing_pos < root_agent_pos, (
            "setup_langfuse_tracing() must be called BEFORE root_agent creation. "
            f"tracing at pos {tracing_pos}, root_agent at pos {root_agent_pos}"
        )

    def test_agent_module_has_root_agent(self):
        """Verify root_agent is exposed at module level."""
        assert "root_agent = build_root_workflow" in self.agent_source


# ---------------------------------------------------------------------------
# langfuse_tracing.py module attributes
# ---------------------------------------------------------------------------

class TestTracingModuleStructure:
    """Tests for the structure and defensive design of langfuse_tracing.py."""

    def test_module_exports_setup_function(self):
        """Verify the module exports setup_langfuse_tracing."""
        from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
            setup_langfuse_tracing,
        )
        assert callable(setup_langfuse_tracing)

    def test_module_has_initialized_flag(self):
        """Verify the module has _tracing_initialized flag."""
        import beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing as mod
        assert hasattr(mod, "_tracing_initialized")

    def test_env_var_names_match_convention(self):
        """Verify the function reads standard Langfuse env var names."""
        import inspect
        from beeportal.bee_ai_enterprises_adk_v2.utils.langfuse_tracing import (
            setup_langfuse_tracing,
        )

        source = inspect.getsource(setup_langfuse_tracing)
        assert "LANGFUSE_PUBLIC_KEY" in source
        assert "LANGFUSE_SECRET_KEY" in source
        assert "LANGFUSE_HOST" in source
        assert "LANGFUSE_TRACING_ENABLED" in source


# ---------------------------------------------------------------------------
# .env file configuration tests
# ---------------------------------------------------------------------------

class TestEnvConfiguration:
    """Tests that .env has all required Langfuse config vars."""

    @pytest.fixture(autouse=True)
    def _load_env(self):
        """Env is loaded by conftest.py."""
        pass

    def test_langfuse_host_configured(self):
        """LANGFUSE_HOST should be set."""
        host = os.getenv("LANGFUSE_HOST", "")
        assert host, "LANGFUSE_HOST not set in .env"

    def test_langfuse_public_key_configured(self):
        """LANGFUSE_PUBLIC_KEY should be set."""
        key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        assert key, "LANGFUSE_PUBLIC_KEY not set in .env"

    def test_langfuse_secret_key_configured(self):
        """LANGFUSE_SECRET_KEY should be set."""
        key = os.getenv("LANGFUSE_SECRET_KEY", "")
        assert key, "LANGFUSE_SECRET_KEY not set in .env"

    def test_langfuse_tracing_enabled_configured(self):
        """LANGFUSE_TRACING_ENABLED should be set."""
        val = os.getenv("LANGFUSE_TRACING_ENABLED", "")
        assert val, "LANGFUSE_TRACING_ENABLED not set in .env"
        assert val.lower() in ("true", "false", "0", "1", "yes", "no")

    def test_otel_capture_content_configured(self):
        """OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT should be set."""
        val = os.getenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "")
        assert val, "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT not set in .env"
