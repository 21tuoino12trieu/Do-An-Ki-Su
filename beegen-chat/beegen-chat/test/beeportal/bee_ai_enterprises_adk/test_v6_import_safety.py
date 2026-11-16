import pytest
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
from unittest.mock import patch

def test_import_safety_no_web_env():
    # Clear any ADK Web env variables before importing
    with patch.dict(os.environ, clear=True):
        # We need to make sure the module is not already loaded or we force reload it.
        # But for this test, simply importing it should not raise errors
        # if the web env vars are not set.
        import beeportal.bee_ai_enterprises_adk.agent as agent_module
        
        # Verify root_agent exists and is a ProductionWorkflowAgent
        assert hasattr(agent_module, "root_agent")
        
        from beeportal.bee_ai_enterprises_adk.agent import ProductionWorkflowAgent
        assert isinstance(agent_module.root_agent, ProductionWorkflowAgent)
        
        # Verify bot_id is empty string, meaning no env var was read at import time
        assert agent_module.root_agent.bot_id == ""

def test_import_bot_module_safety():
    with patch.dict(os.environ, clear=True):
        import beeportal.bee_ai_enterprises_adk.bot as bot_module
        assert hasattr(bot_module, "BeeAiEnterprisesADK")
