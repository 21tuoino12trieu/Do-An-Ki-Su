import os
os.environ["ADK_WEB_ENABLE_PRODUCTION_RUNTIME"] = "true"
from unittest.mock import mock_open
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from beeportal.bee_ai_enterprises_adk.agent import BeeAiEnterprisesADK
from beeportal.bee_ai_enterprises_adk.utils.lock_manager import SessionLockManager, AgentRequestState, HeartbeatFailedError

def mock_getenv_side_effect(pg_url="postgresql://localhost"):
    def _mock(key, def_val=None):
        if key == "POSTGRES_URL":
            return pg_url
        if key == "MONGO_CONFIG_PATH":
            return "config/mongo.yaml"
        if key == "AIE_LLM_API_TYPE":
            return "litellm_proxy"
        if key == "AIE_LLM_API_KEY":
            return "test-key"
        if key == "AIE_LLM_BASE_URL":
            return "https://example.test/v1"
        if key == "AIE_LLM_MODEL":
            return "test-model"
        return def_val
    return _mock

def get_valid_lock_mgr_mock():
    mgr = MagicMock()
    check_conn = AsyncMock()
    check_conn.fetch.side_effect = [
        [{"column_name": c} for c in ["bot_id", "namespace_version", "user_id", "request_hash", "conversation_id", "request_id", "status", "phase", "response", "final_event_id", "user_event_id", "error", "attempt", "draft_event_id", "reviewer_verdict", "reviewer_feedback", "iteration", "lease_expires_at", "created_at", "updated_at"]],
        [{"constraint_name": "uq1", "cols": ["bot_id", "namespace_version", "user_id", "conversation_id", "request_id"]}]
    ]
    mgr.pool.acquire.return_value.__aenter__.return_value = check_conn
    mgr.pool.acquire.return_value.__aexit__.return_value = None
    mgr.close = AsyncMock()
    return mgr

@pytest.fixture
def mock_bot():
    bot = BeeAiEnterprisesADK(bot_id="072fab09-7f7f-4682-9152-c142fa178444")
    runtime = bot._runtime
    runtime._ensure_initialized = AsyncMock()
    runtime._main_agent = MagicMock()
    runtime._main_agent.name = "ENTERPRISES_MAIN_AGENT"
    runtime._check_context_guard = AsyncMock(return_value=True)
    bot._runtime._app_name = "bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444"
    bot._runtime._reviewer_agent = MagicMock()
    bot._runtime._lock_manager = MagicMock(spec=SessionLockManager)
    
    # Mock AgentRequestState
    req_state = MagicMock(spec=AgentRequestState)
    req_state.phase = "main_running"
    req_state.iteration = 0
    req_state.status = "processing"
    req_state.user_event_id = None
    req_state.draft_event_id = None
    req_state.reviewer_feedback = None
    req_state.reviewer_verdict = None
    req_state.response = None
    
    async def mock_update_state(**kwargs):
        for k, v in kwargs.items():
            if v is not None:
                setattr(req_state, k, v)
    req_state.update_state = AsyncMock(side_effect=mock_update_state)
    req_state.mark_completed = AsyncMock()
    req_state.mark_failed = AsyncMock()
    req_state.raise_if_heartbeat_failed = MagicMock()

    lock_ctx = MagicMock()
    lock_ctx.__aenter__ = AsyncMock(return_value=req_state)
    lock_ctx.__aexit__ = AsyncMock(return_value=None)
    bot._runtime._lock_manager.lock.return_value = lock_ctx
    
    mock_session = MagicMock()
    mock_session.events = []
    bot._runtime._canonical_session_service = __import__('unittest.mock').mock.MagicMock()
    bot._runtime._canonical_session_service.get_session = AsyncMock(return_value=mock_session)
    bot._runtime._canonical_session_service.create_session = AsyncMock(return_value=mock_session)
    bot._runtime._canonical_session_service.append_event = AsyncMock()
    
    bot._runtime._runner = MagicMock()
    async def dummy_run(*args, **kwargs):
        from google.adk.sessions import Event
        from google.adk import types
        yield Event(
            id="dummy_evt",
            author="ENTERPRISES_MAIN_AGENT",
            content=types.Content(role="model", parts=[types.Part.from_text(text="Dummy answer")]),
            partial=False
        )
    bot._runtime._runner.run_async = dummy_run
    patcher = patch("beeportal.bee_ai_enterprises_adk.core.state_machine.recover_stale_request", new_callable=AsyncMock)
    mock_recover = patcher.start()
    mock_recover.return_value = (True, "Draft", "Reasoning", "evt-draft", "evt-user")
    bot._runtime.mock_recover_stale_request = mock_recover
    
    bot._run_reviewer_agent = AsyncMock(return_value=("PASS", "Looks good", "Final response", "evt-rev"))
    
    return bot, req_state


@pytest.mark.asyncio
async def test_bot_heartbeat_fail_aborts(mock_bot):
    bot, req_state = mock_bot
    
    # Mô phỏng lỗi heartbeat ngay từ đầu
    req_state.raise_if_heartbeat_failed.side_effect = HeartbeatFailedError("Heartbeat died")
    
    # Run the generator
    chunks = []
    async for chunk in bot.run(
        messages=[{"role": "user", "content": "hello"}],
        session_id="session1",
        client_message_id="msg1",
        username="test"
    ):
        chunks.append(chunk)

    full_text = "".join(getattr(chunk.choices[0].delta, "content", "") for chunk in chunks if chunk.choices and chunk.choices[0].delta)
    assert "mất kết nối mạng cục bộ" in full_text
    req_state.mark_completed.assert_not_called()


def _get_mock_bot_uninitialized():
    bot = BeeAiEnterprisesADK(bot_id="072fab09-7f7f-4682-9152-c142fa178444")
    bot._runtime._initialized = False
    bot._runtime._app_name = "bee_ai_enterprises_adk:072fab09-7f7f-4682-9152-c142fa178444"
    return bot

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_yaml_missing_uri(mock_getenv, mock_path, mock_client, mock_init_nodes):
    bot = _get_mock_bot_uninitialized()
    mock_getenv.return_value = "config/mongo.yaml"
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "authen_source: admin\n"
    mock_path.return_value = mock_path_obj

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(ValueError, match=r"Thiếu.*uri.*"):
            await bot._runtime._ensure_initialized()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_yaml_missing_authen_source(mock_getenv, mock_path, mock_client, mock_init_nodes):
    bot = _get_mock_bot_uninitialized()
    mock_getenv.return_value = "config/mongo.yaml"
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\n"
    mock_path.return_value = mock_path_obj

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(ValueError, match=r"Thiếu.*authen_source.*"):
            await bot._runtime._ensure_initialized()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_bot_id_not_found(mock_getenv, mock_path, mock_client, mock_init_nodes):
    bot = _get_mock_bot_uninitialized()
    mock_getenv.return_value = "config/mongo.yaml"
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = None
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(LookupError, match="Không tìm thấy bot_id"):
            await bot._runtime._ensure_initialized()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.SessionLockManager")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.DatabaseSessionService")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.create_async_engine")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_bot_info_data_none(mock_getenv, mock_path, mock_client, mock_init_nodes, mock_engine, mock_dbsession, mock_lock_mgr):
    bot = _get_mock_bot_uninitialized()
    mock_conn = __import__("unittest.mock").mock.AsyncMock()
    mock_res = __import__("unittest.mock").mock.MagicMock()
    mock_res.fetchone.return_value = ["dummy"]
    # Provide all required columns for fetchall (columns check and unique constraints check)
    mock_res.fetchall.side_effect = [
        [["bot_id"], ["namespace_version"], ["user_id"], ["request_hash"], ["conversation_id"], ["request_id"], ["status"], ["phase"], ["response"], ["final_event_id"], ["user_event_id"], ["error"], ["attempt"], ["draft_event_id"], ["reviewer_verdict"], ["reviewer_feedback"], ["iteration"], ["lease_expires_at"], ["created_at"], ["updated_at"]],
        [["constraint1", "bot_id"], ["constraint1", "namespace_version"], ["constraint1", "user_id"], ["constraint1", "conversation_id"], ["constraint1", "request_id"]]
    ]
    mock_conn.execute.return_value = mock_res
    engine_mock = __import__("unittest.mock").mock.MagicMock()
    engine_mock.dispose = __import__("unittest.mock").mock.AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = mock_conn
    mock_engine.return_value = engine_mock
    mock_getenv.side_effect = mock_getenv_side_effect("postgresql://localhost")
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {"_id": "072fab09-7f7f-4682-9152-c142fa178444", "data": None}
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance
    
    mock_lock_mgr.create = AsyncMock(return_value=get_valid_lock_mgr_mock())

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        await bot._runtime._ensure_initialized()
    assert bot._runtime._initialized is True
    # definition is "" because data is None

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.SessionLockManager")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.DatabaseSessionService")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.create_async_engine")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_bot_info_metadata_none(mock_getenv, mock_path, mock_client, mock_init_nodes, mock_engine, mock_dbsession, mock_lock_mgr):
    bot = _get_mock_bot_uninitialized()
    mock_conn = __import__("unittest.mock").mock.AsyncMock()
    mock_res = __import__("unittest.mock").mock.MagicMock()
    mock_res.fetchone.return_value = ["dummy"]
    # Provide all required columns for fetchall (columns check and unique constraints check)
    mock_res.fetchall.side_effect = [
        [["bot_id"], ["namespace_version"], ["user_id"], ["request_hash"], ["conversation_id"], ["request_id"], ["status"], ["phase"], ["response"], ["final_event_id"], ["user_event_id"], ["error"], ["attempt"], ["draft_event_id"], ["reviewer_verdict"], ["reviewer_feedback"], ["iteration"], ["lease_expires_at"], ["created_at"], ["updated_at"]],
        [["constraint1", "bot_id"], ["constraint1", "namespace_version"], ["constraint1", "user_id"], ["constraint1", "conversation_id"], ["constraint1", "request_id"]]
    ]
    mock_conn.execute.return_value = mock_res
    engine_mock = __import__("unittest.mock").mock.MagicMock()
    engine_mock.dispose = __import__("unittest.mock").mock.AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = mock_conn
    mock_engine.return_value = engine_mock
    mock_getenv.side_effect = mock_getenv_side_effect("postgresql://localhost")
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {"_id": "072fab09-7f7f-4682-9152-c142fa178444", "data": {"metadata": None}}
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance
    
    mock_lock_mgr.create = AsyncMock(return_value=get_valid_lock_mgr_mock())

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        await bot._runtime._ensure_initialized()
    assert bot._runtime._initialized is True
    # definition is "" because metadata is None

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.SessionLockManager")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.DatabaseSessionService")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.create_async_engine")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_valid_system_prompt(mock_getenv, mock_path, mock_client, mock_init_nodes, mock_engine, mock_dbsession, mock_lock_mgr):
    bot = _get_mock_bot_uninitialized()
    mock_conn = __import__("unittest.mock").mock.AsyncMock()
    mock_res = __import__("unittest.mock").mock.MagicMock()
    mock_res.fetchone.return_value = ["dummy"]
    # Provide all required columns for fetchall (columns check and unique constraints check)
    mock_res.fetchall.side_effect = [
        [["bot_id"], ["namespace_version"], ["user_id"], ["request_hash"], ["conversation_id"], ["request_id"], ["status"], ["phase"], ["response"], ["final_event_id"], ["user_event_id"], ["error"], ["attempt"], ["draft_event_id"], ["reviewer_verdict"], ["reviewer_feedback"], ["iteration"], ["lease_expires_at"], ["created_at"], ["updated_at"]],
        [["constraint1", "bot_id"], ["constraint1", "namespace_version"], ["constraint1", "user_id"], ["constraint1", "conversation_id"], ["constraint1", "request_id"]]
    ]
    mock_conn.execute.return_value = mock_res
    engine_mock = __import__("unittest.mock").mock.MagicMock()
    engine_mock.dispose = __import__("unittest.mock").mock.AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = mock_conn
    mock_engine.return_value = engine_mock
    mock_getenv.side_effect = mock_getenv_side_effect("postgresql://localhost")
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {
        "_id": "072fab09-7f7f-4682-9152-c142fa178444", 
        "data": {
            "metadata": {"system_prompt": "You are a helpful assistant"}
        }
    }
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance
    
    mock_lock_mgr.create = AsyncMock(return_value=get_valid_lock_mgr_mock())

    with patch("beeportal.bee_ai_enterprises_adk.core.runtime.build_main_agent") as mock_build_agent:
        await bot._runtime._ensure_initialized()
        assert bot._runtime._initialized is True
        mock_build_agent.assert_called_once_with(definition="You are a helpful assistant")

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_mongo_client_closed_on_error(mock_getenv, mock_path, mock_client, mock_init_nodes):
    bot = _get_mock_bot_uninitialized()
    mock_getenv.return_value = "config/mongo.yaml"
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj

    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.side_effect = Exception("Mongo timeout")
    
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(Exception, match="Mongo timeout"):
            await bot._runtime._ensure_initialized()

    # Xác nhận context manager vẫn được gọi __exit__
    mock_client_instance.__exit__.assert_called_once()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.SessionLockManager")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.DatabaseSessionService")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.create_async_engine")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_postgres_url_formatting(mock_getenv, mock_path, mock_client, mock_init_nodes, mock_engine, mock_dbsession, mock_lock_mgr):
    bot = _get_mock_bot_uninitialized()
    mock_conn = __import__("unittest.mock").mock.AsyncMock()
    mock_res = __import__("unittest.mock").mock.MagicMock()
    mock_res.fetchone.return_value = ["dummy"]
    # Provide all required columns for fetchall (columns check and unique constraints check)
    mock_res.fetchall.side_effect = [
        [["bot_id"], ["namespace_version"], ["user_id"], ["request_hash"], ["conversation_id"], ["request_id"], ["status"], ["phase"], ["response"], ["final_event_id"], ["user_event_id"], ["error"], ["attempt"], ["draft_event_id"], ["reviewer_verdict"], ["reviewer_feedback"], ["iteration"], ["lease_expires_at"], ["created_at"], ["updated_at"]],
        [["constraint1", "bot_id"], ["constraint1", "namespace_version"], ["constraint1", "user_id"], ["constraint1", "conversation_id"], ["constraint1", "request_id"]]
    ]
    mock_conn.execute.return_value = mock_res
    engine_mock = __import__("unittest.mock").mock.MagicMock()
    engine_mock.dispose = __import__("unittest.mock").mock.AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = mock_conn
    mock_engine.return_value = engine_mock
    # Test 1: Input postgresql://...
    # Test 2: Input postgresql+psycopg2://...
    # Test password with special chars
    test_cases = [
        "postgresql://user:LOCAL_PASSWORD@localhost:5432/db",
        "postgresql+psycopg2://user:p%40ssw%3Ard@localhost:5432/db",
        "postgresql+asyncpg://user:p%40ssw%3Ard@localhost:5432/db"
    ]
    
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj
    
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {"_id": "072fab09-7f7f-4682-9152-c142fa178444", "data": {}}
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance
    
    for url in test_cases:
        bot._runtime._initialized = False
        mock_getenv.side_effect = mock_getenv_side_effect(url)
        mock_lock_mgr.create = AsyncMock(return_value=get_valid_lock_mgr_mock())
        
        with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
            await bot._runtime._ensure_initialized()
        
        # Native lock DSN luôn là postgresql://
        mock_lock_mgr.create.assert_called_once_with("postgresql://user:LOCAL_PASSWORD@localhost:5432/db")
        # ADK URL luôn là postgresql+asyncpg://
        mock_dbsession.assert_called_once_with(db_url="postgresql+asyncpg://user:p%40ssw%3Ard@localhost:5432/db")
        
        mock_lock_mgr.reset_mock()
        mock_dbsession.reset_mock()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_postgres_url_reject_invalid_dialect(mock_getenv, mock_path, mock_client, mock_init_nodes):
    bot = _get_mock_bot_uninitialized()
    mock_getenv.side_effect = mock_getenv_side_effect("mysql://localhost/db")
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj
    
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {"_id": "072fab09-7f7f-4682-9152-c142fa178444", "data": {}}
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(ValueError, match="POSTGRES_URL phải sử dụng PostgreSQL"):
            await bot._runtime._ensure_initialized()

@pytest.mark.asyncio
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.SessionLockManager")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.DatabaseSessionService")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.create_async_engine")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.initialize_retrieval_nodes_sync")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.MongoClient")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.Path")
@patch("beeportal.bee_ai_enterprises_adk.core.runtime.os.getenv")
async def test_postgres_url_hides_password_in_exception(mock_getenv, mock_path, mock_client, mock_init_nodes, mock_engine, mock_dbsession, mock_lock_mgr):
    bot = _get_mock_bot_uninitialized()
    mock_conn = __import__("unittest.mock").mock.AsyncMock()
    mock_res = __import__("unittest.mock").mock.MagicMock()
    mock_res.fetchone.return_value = ["dummy"]
    # Provide all required columns for fetchall (columns check and unique constraints check)
    mock_res.fetchall.side_effect = [
        [["bot_id"], ["namespace_version"], ["user_id"], ["request_hash"], ["conversation_id"], ["request_id"], ["status"], ["phase"], ["response"], ["final_event_id"], ["user_event_id"], ["error"], ["attempt"], ["draft_event_id"], ["reviewer_verdict"], ["reviewer_feedback"], ["iteration"], ["lease_expires_at"], ["created_at"], ["updated_at"]],
        [["constraint1", "bot_id"], ["constraint1", "namespace_version"], ["constraint1", "user_id"], ["constraint1", "conversation_id"], ["constraint1", "request_id"]]
    ]
    mock_conn.execute.return_value = mock_res
    engine_mock = __import__("unittest.mock").mock.MagicMock()
    engine_mock.dispose = __import__("unittest.mock").mock.AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = mock_conn
    mock_engine.return_value = engine_mock
    mock_getenv.side_effect = mock_getenv_side_effect("postgresql://user:LOCAL_PASSWORD@localhost/db")
    mock_path_obj = MagicMock()
    mock_path_obj.exists.return_value = True
    mock_path_obj.read_text.return_value = "uri: mongodb://localhost\nauthen_source: admin\n"
    mock_path.return_value = mock_path_obj
    
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {"_id": "072fab09-7f7f-4682-9152-c142fa178444", "data": {}}
    mock_client_instance = MagicMock()
    mock_client_instance.__getitem__.return_value = mock_db
    mock_client.return_value = mock_client_instance
    
    mock_lock_mgr.create = AsyncMock(return_value=get_valid_lock_mgr_mock())
    # Gây exception trong DatabaseSessionService
    mock_dbsession.side_effect = Exception("Driver error")

    with patch('beeportal.bee_ai_enterprises_adk.core.runtime.open', mock_open(read_data=mock_path_obj.read_text.return_value), create=True):
        with pytest.raises(Exception) as exc_info:
            await bot._runtime._ensure_initialized()
        
    assert "secret" not in str(exc_info.value)
    assert "postgresql+asyncpg://user:***@localhost/db" in str(exc_info.value)

