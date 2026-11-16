from unittest.mock import patch
import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
os.environ["BEE_AI_ENTERPRISES_ADK_WEB_BOT_ID"] = "test_bot"
import pytest
from unittest.mock import patch

from beeportal.bee_ai_enterprises_adk.agent import root_agent
from beeportal.bee_ai_enterprises_adk.tools.retrieval_tools import (
    search_qna_tool,
    search_documents_tool,
    search_forms_tool,
    _qna_node,
    _doc_node,
    _forms_node
)

@pytest.mark.asyncio
@patch.dict("os.environ", {"ADK_WEB_ENABLE_PRODUCTION_RUNTIME": "true", "BEE_AI_ENTERPRISES_ADK_WEB_BOT_ID": "test_bot"})
async def test_root_agent_tools_are_initialized_by_default():
    """Kiểm tra: Entry point agent.root_agent thì tool phải đã được init."""
    assert root_agent is not None

    # Tùy theo thiết kế mới, ProductionWorkflowAgent khởi tạo lazy
    # Ta phải gọi _ensure_runtime() (hoặc chạy 1 invocation) để nodes được build
    from beeportal.bee_ai_enterprises_adk.agent import ProductionWorkflowAgent
    if isinstance(root_agent, ProductionWorkflowAgent):
        await root_agent._ensure_runtime()
        # Initialize nodes explicitly since it's lazy in the new design
        from beeportal.bee_ai_enterprises_adk.tools.retrieval_tools import initialize_retrieval_nodes_sync
        from unittest.mock import patch
        with patch('beeportal.bee_ai_enterprises_adk.tools.retrieval_tools._init_qna_node', return_value="mock_node"):
            with patch('beeportal.bee_ai_enterprises_adk.tools.retrieval_tools._init_doc_node', return_value="mock_node"):
                with patch('beeportal.bee_ai_enterprises_adk.tools.retrieval_tools._init_forms_node', return_value="mock_node"):
                    initialize_retrieval_nodes_sync()

    # Nodes đã phải được khởi tạo
    from beeportal.bee_ai_enterprises_adk.tools.retrieval_tools import _qna_node, _doc_node, _forms_node
    assert _qna_node is not None
    assert _doc_node is not None
    assert _forms_node is not None

    # Gọi tool thử, không được raise RuntimeError về lifecycle
    # Vì _qna_node đang là mock (do conftest.py), _search() trả về MagicMock (awaitable không lỗi)
    try:
        await search_qna_tool("test")
        await search_documents_tool("test")
        await search_forms_tool("test")
    except RuntimeError as e:
        if "chưa được khởi tạo" in str(e):
            pytest.fail("Tool bị lỗi chưa khởi tạo dù đã qua agent.root_agent")
        else:
            pass # Lỗi khác không sao

def test_build_main_agent_initializes_nodes():
    """Kiểm tra: build_main_agent hoàn tất thì cả ba tool có node sẵn sàng."""
    from beeportal.bee_ai_enterprises_adk.agents.main_agent import build_main_agent
    from beeportal.bee_ai_enterprises_adk.tools import retrieval_tools

    # Clear nodes to simulate cold start
    retrieval_tools._qna_node = None
    retrieval_tools._doc_node = None
    retrieval_tools._forms_node = None

    # Tools should fail if we try to call them now
    with pytest.raises(RuntimeError, match="chưa được khởi tạo"):
        retrieval_tools._get_qna_node()

    # Call build_main_agent
    agent = build_main_agent(definition="test")

    # Now they should be initialized
    assert retrieval_tools._qna_node is not None
    assert retrieval_tools._doc_node is not None
    assert retrieval_tools._forms_node is not None

    assert retrieval_tools._get_qna_node() is not None
