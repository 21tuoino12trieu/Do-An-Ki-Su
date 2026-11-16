from agents import Runner, gen_trace_id, trace, RunConfig, ModelSettings
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta
from openai.types.responses import ResponseTextDeltaEvent

from typing import AsyncGenerator
from beegenerate.loggings import LOGGER


from beemcp.services.manager import MCPManagerService
from beegen_v1.configs.mcp.mcp_config import RootMCPConfig
from beegen_v1.utils.common import fake_chunk_from
from beetools.system_aware import current_datetime
import time
from datetime import datetime

from ..base_agent import BaseAgent
from .beehai_intent_classify import beehai_intent_classify, UserIntent
from .beehai_hr import beehai_hr_agent
from .beehai_text2sql import text2sql_agent
from .context import UserInfo, botgresql_tool_filter
from ..crud.user import UserService
from uuid import uuid4


class BeeHaiHR(BaseAgent):
    """
    Agent to support query HR information for BeeHai
    """

    def __init__(self, bot_id: str, user_service: UserService) -> None:
        """
        Initialize the JiraAgent.

        Args:
            bot_id (str): The bot identifier.
            user_service (UserService): Service for user data access.
        """
        self.bot_id = bot_id
        self.tools = [current_datetime]
        self.user_service = user_service
        self.root_mcp_config = RootMCPConfig.default()
        self.token_store: str
        self.run_config = RunConfig(
            model_settings=ModelSettings(
                temperature=0,
                include_usage=True,
                parallel_tool_calls=True
            )
        )

    async def run(self, messages, role_ids, topic, username, bot_id, keycloak_token, token, mcp_manager: MCPManagerService) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Main entry point for handling BeeHai chat session.

        Args:
            messages: List of chat messages.
            role_ids: The role of the user or agent.
            topic: The chat topic.
            username: The user's username.
            bot_id: The bot identifier.
            mcp_manager (MCPManagerService): Service for managing MCP servers.

        Yields:
            ChatCompletionChunk: Streaming chat response chunks.
        """

        trace_id = gen_trace_id()
        current_timestamp = int(time.time())
        result_id = str(uuid4().hex)

        # Get/Init SQL MCP
        final_data = ""
        with trace(f"BeeHai Agent: {username}", trace_id=trace_id, group_id=bot_id, metadata={"username": username, "bot_id": bot_id}):
            # Get user info
            raw_user = await self.user_service.get_user(username=username)
            user = UserInfo(
                username=raw_user.get('username', None),
                email=raw_user.get('email', None),
                full_name=raw_user.get('full_name', None),
                current_time=str(datetime.now())
            )

            # Get MCP
            hr_mcp = await mcp_manager.get_mcp_of_user_for_agent(username=username, mcp_server_name="hr_info")
            if (hr_mcp is None) or (current_timestamp >= int(self.token_store.get("exp"))):
                await mcp_manager.remove_mcp_of_user(username, "hr_info")
                await mcp_manager.add_sse_server_user(
                    username=username,
                    name="hr_info",
                    url=self.root_mcp_config.mcp_config.hr_info.mcp_url,
                    headers={
                        "Authorization": f"{keycloak_token}",
                        "User": username
                    },
                    tool_filter=botgresql_tool_filter
                )
                self.token_store = token
                hr_mcp = await mcp_manager.get_mcp_of_user_for_agent(username=username, mcp_server_name="hr_info")

            result = await self._beehai_hr_executor(
                messages=messages,
                context=user,
                run_config=self.run_config,
                user_mcp=[hr_mcp]
            )

            try:
                async for event in result.stream_events():
                    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                        final_data += event.data.delta
                        yield fake_chunk_from(
                            content=str(event.data.delta),
                            model=str('gpt-4.1'),
                            chat_id=result_id,
                            current_time=current_timestamp
                        )
                    # -----------------------
                    # When the agent updates, print that
                    elif event.type == "agent_updated_stream_event":
                        LOGGER.info(
                            f"Agent updated: {event.new_agent.name}")
                        continue
                    # When items are generated, print them
                    elif event.type == "run_item_stream_event":
                        if event.item.type == "tool_call_item":
                            LOGGER.info("-- Tool was called")
                        elif event.item.type == "tool_call_output_item":
                            LOGGER.info(
                                f"-- Tool output: {event.item.output}")
            finally:
                LOGGER.info(f"-- Final output (str): {final_data}")

    @classmethod
    async def beehai_intent_classifier(cls, messages) -> UserIntent:
        run_config = RunConfig(
            model_settings=ModelSettings(
                temperature=0,
                include_usage=True,
                parallel_tool_calls=True
            )
        )
        intent_result = await Runner.run(
            starting_agent=beehai_intent_classify,
            input=messages,
            run_config=run_config
        )

        assert isinstance(intent_result.final_output, UserIntent)
        return intent_result.final_output

    async def _beehai_hr_executor(self, messages, context, run_config, user_mcp):
        """
        Execute the BeeHai agent for the given messages and context.

        Args:
            messages: List of chat messages.
            context: The user context.
            run_config: The run configuration.
            user_mcp: User's MCP server information.

        Returns:
            Streaming agent result.
        """
        beehai_hr = beehai_hr_agent.clone()
        beehai_hr.mcp_servers = user_mcp
        beehai_hr.tools = self.tools
        # tool_list = self.tools.copy()
        # beehai_hr.tools = tool_list.append(
        #     text2sql_agent.as_tool(
        #         tool_name="text_to_sql",
        #         tool_description="Convert text to SQL query for Postgresql"
        #     )
        # )
        result = Runner.run_streamed(
            starting_agent=beehai_hr,
            input=messages,
            context=context,
            run_config=run_config
        )
        return result
