from agents import Runner, gen_trace_id, trace, RunConfig, ModelSettings
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta
from openai.types.responses import ResponseTextDeltaEvent

from typing import AsyncGenerator
from beegenerate.loggings import LOGGER


from beemcp.services.manager import MCPManagerService
from beegen_v1.configs.mcp.mcp_config import RootMCPConfig
from beetools.system_aware import current_datetime
import time

from ..base_agent import BaseAgent
from ..general_executor import normal_agent
from .context import UserInfo, LOGIN_MESSAGE, INCORRECT_LOGIN_MESSAGE, SUCCESS_LOGIN_MESSAGE, TOKEN_EXPIRE_MESSAGE, jira_tool_filter
from .jira_executor import jira_executor_agent
from .jira_info_gather import jira_info_gather
from .jira_rewrite_instruct import jira_rewrite_instruct
from .jira_intent_classify import jira_intent_classify, UserIntent
from ..crud.user import UserService
from uuid import uuid4
import base64
import re
import requests
import json


class JiraAgent(BaseAgent):
    """
    Agent for managing Jira authentication, intent classification, and chat flows.

    Handles user login, token management, intent classification, and orchestrates
    the execution of different agents based on user intent for Jira-related tasks.
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

    async def run(self, messages, role, topic, username, bot_id, mcp_manager: MCPManagerService) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Main entry point for handling a Jira chat session.

        Handles user authentication, intent classification, and orchestrates
        the flow of messages and tool usage for Jira-related and general queries.

        Args:
            messages: List of chat messages.
            role: The role of the user or agent.
            topic: The chat topic.
            username: The user's username.
            bot_id: The bot identifier.
            mcp_manager (MCPManagerService): Service for managing MCP servers.

        Yields:
            ChatCompletionChunk: Streaming chat response chunks.
        """
        run_config = RunConfig(
            model_settings=ModelSettings(
                temperature=0,
                include_usage=True,
                parallel_tool_calls=True
            )
        )
        trace_id = gen_trace_id()
        current_timestampt = int(time.time())
        # Generate result id from uuid4
        result_id = str(uuid4().hex)
        # Check login
        if not await self._check_jira_login(username=username, mcp_manager=mcp_manager):
            LOGGER.info(
                f"{username} trying to login with username: {messages[-1].get('content').split(':')[0]}")
            # Try restoring jira session
            if await self._restore_jira_session(username=username, mcp_manager=mcp_manager):
                LOGGER.info(f"Restore Jira session success for `{username}`")
            elif self.is_valid_username_password_format(messages[-1].get('content')):
                if messages[-1].get('content').split(':')[0] != username:
                    yield ChatCompletionChunk(
                        id=result_id,
                        created=current_timestampt,
                        model=str('gpt-4.1'),
                        choices=[Choice(
                            delta=ChoiceDelta(
                                content=str(INCORRECT_LOGIN_MESSAGE)
                            ),
                            index=0
                        )],
                        object="chat.completion.chunk"
                    )
                    return
                if not await self._jira_login_flow(messages[-1].get('content'), mcp_manager):
                    yield ChatCompletionChunk(
                        id=result_id,
                        created=current_timestampt,
                        model=str('gpt-4.1'),
                        choices=[Choice(
                            delta=ChoiceDelta(
                                content=str(INCORRECT_LOGIN_MESSAGE)
                            ),
                            index=0
                        )],
                        object="chat.completion.chunk"
                    )
                    return
                else:
                    yield ChatCompletionChunk(
                        id=result_id,
                        created=current_timestampt,
                        model=str('gpt-4.1'),
                        choices=[Choice(
                            delta=ChoiceDelta(
                                content=str(SUCCESS_LOGIN_MESSAGE.format(
                                    username=username))
                            ),
                            index=0
                        )],
                        object="chat.completion.chunk"
                    )
                    return
            else:
                yield ChatCompletionChunk(
                    id=result_id,
                    created=current_timestampt,
                    model=str('gpt-4.1'),
                    choices=[Choice(
                        delta=ChoiceDelta(
                            content=str(LOGIN_MESSAGE)
                        ),
                        index=0
                    )],
                    object="chat.completion.chunk"
                )
                return
        else:
            if not await self._check_token_alive(username=username, mcp_manager=mcp_manager):
                yield ChatCompletionChunk(
                    id=result_id,
                    created=current_timestampt,
                    model=str('gpt-4.1'),
                    choices=[Choice(
                        delta=ChoiceDelta(
                            content=str(TOKEN_EXPIRE_MESSAGE)
                        ),
                        index=0
                    )],
                    object="chat.completion.chunk"
                )
                return

        final_data = ""
        with trace(f"Jira assistant trace: {username}", trace_id=trace_id, group_id=bot_id, metadata={"username": username, "bot_id": bot_id}):
            # Get user info
            raw_user = await self.user_service.get_user(username=username)
            user = UserInfo(
                username=raw_user.get('username', None),
                email=raw_user.get('email', None),
                full_name=raw_user.get('full_name', None),
            )

            # User intent classify
            intent_result = await Runner.run(
                starting_agent=jira_intent_classify,
                input=messages,
                run_config=run_config,
                context=user
            )

            # Branching by intent
            rewrite_query_agent = None
            gather_info_agent = None
            jira_agent = None
            result = None
            assert isinstance(intent_result.final_output, UserIntent)
            if not intent_result.final_output.is_jira_relate:
                normal_agent_exec = normal_agent.clone()
                normal_agent_exec.tools = self.tools
                result = Runner.run_streamed(
                    starting_agent=normal_agent_exec,
                    input=messages,
                    run_config=run_config,
                    context=user
                )
            else:
                # Get user MCP and init agent for request
                user_mcp = await mcp_manager.get_list_server_of_user_for_agent(username)
                LOGGER.info(f"User MCPs: {len(user_mcp)}")
                rewrite_query_result = await self._rewrite_query(messages=messages, context=user, run_config=run_config)
                # gather_info_result = await self._gather_info(messages=rewrite_query_result, context=user, run_config=run_config, user_mcp=user_mcp)
                result = await self._jira_executor(messages=rewrite_query_result, context=user, run_config=run_config, user_mcp=user_mcp)
            try:
                async for event in result.stream_events():
                    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                        # print(event.data.delta, end="", flush=True)
                        final_data += event.data.delta
                        # yield "data: " + StreamResponse(content=str(event.data.delta)).model_dump_json() + "\n"
                        yield ChatCompletionChunk(
                            id=result_id,
                            created=current_timestampt,
                            model=str('gpt-4.1'),
                            choices=[Choice(
                                delta=ChoiceDelta(
                                    content=str(event.data.delta)
                                ),
                                index=0
                            )],
                            object="chat.completion.chunk"
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

    async def _rewrite_query(self, messages, context, run_config):
        """
        Rewrite the user's query using the Jira rewrite instruction agent.

        Args:
            messages: List of chat messages.
            context: The user context.
            run_config: The run configuration.

        Returns:
            list: The rewritten query as a list of input messages.
        """
        rewrite_query_agent = jira_rewrite_instruct.clone()
        rewrite_query_agent.tools = self.tools
        rewrite_query_result = await Runner.run(
            starting_agent=rewrite_query_agent,
            input=messages,
            run_config=run_config,
            context=context
        )
        LOGGER.info(rewrite_query_result.__str__())
        return rewrite_query_result.to_input_list()

    async def _gather_info(self, messages, context, run_config, user_mcp):
        """
        Gather additional information using the Jira info gather agent.

        Args:
            messages: List of chat messages.
            context: The user context.
            run_config: The run configuration.
            user_mcp: User's MCP server information.

        Returns:
            list: The gathered information as a list of input messages.
        """
        gather_info_agent = jira_info_gather.clone()
        gather_info_agent.mcp_servers = user_mcp
        gather_info_result = await Runner.run(
            starting_agent=gather_info_agent,
            input=messages,
            run_config=run_config,
            context=context
        )
        LOGGER.info(gather_info_result.__str__())
        return gather_info_result.to_input_list()

    async def _jira_executor(self, messages, context, run_config, user_mcp):
        """
        Execute the Jira agent for the given messages and context.

        Args:
            messages: List of chat messages.
            context: The user context.
            run_config: The run configuration.
            user_mcp: User's MCP server information.

        Returns:
            Streaming agent result.
        """
        jira_agent = jira_executor_agent.clone()
        jira_agent.mcp_servers = user_mcp
        result = Runner.run_streamed(
            starting_agent=jira_agent,
            input=messages,
            context=context,
            run_config=run_config,
        )
        return result

    async def _check_jira_login(self, username, mcp_manager: MCPManagerService) -> bool:
        """
        Check if the user is logged in to Jira.

        Args:
            username: The user's username.
            mcp_manager (MCPManagerService): Service for managing MCP servers.

        Returns:
            bool: True if the user is logged in, False otherwise.
        """
        user_mcp = mcp_manager.mcp_server_list_users.get(username)
        if user_mcp is None or user_mcp.get('jira') is None or user_mcp.get('jira') == {}:
            return False
        return True

    async def _check_token_alive(self, username, mcp_manager: MCPManagerService):
        """
        Check if the user's Jira token is still valid.

        Args:
            username: The user's username.
            mcp_manager (MCPManagerService): Service for managing MCP servers.

        Returns:
            bool: True if the token is valid, False otherwise.
        """
        user_mcp = mcp_manager.mcp_server_list_users.get(username)
        jira_token = "Bearer " + user_mcp.get('jira').params.get(
            'headers').get('Authorization').split(' ')[-1]
        url = f"{self.root_mcp_config.mcp_config.jira.jira_base_url}/rest/pat/latest/tokens"

        payload = {}
        headers = {
            'Content-Type': 'application/json',
            'Authorization': jira_token
        }

        try:
            response = requests.request(
                "GET", url, headers=headers, data=payload)
            if response.status_code != 200:
                await mcp_manager.remove_mcp_of_user(username, 'jira')
                return False
            return True
        except Exception as e:
            LOGGER.debug(f"Check token failed for `{username}`")
            return False

    async def _revoke_unuse_token(self, userpass: str):
        """
        Revoke unused Jira personal access tokens for the user.

        Args:
            userpass (str): The "username:password" string for authentication.
        """
        username, password = userpass.split(':')
        # Generate PAT with 1d expire
        basic_auth_token = self._generate_basic_auth_token(username, password)
        url_list_token = f"{self.root_mcp_config.mcp_config.jira.jira_base_url}/rest/pat/latest/tokens"

        payload = {}
        headers = {
            'Content-Type': 'application/json',
            'Authorization': basic_auth_token
        }
        list_token_response = requests.request(
            "GET", url_list_token, headers=headers, data=payload)
        for tok in list_token_response.json():
            if tok.get('name') == 'BeeChatJirassistant_1d':
                url = f"{self.root_mcp_config.mcp_config.jira.jira_base_url}/rest/pat/latest/tokens/{str(tok.get('id'))}"
                response = requests.request(
                    "DELETE", url, headers=headers, data=payload)

    async def _jira_login_flow(self, message: str, mcp_manager: MCPManagerService):
        """
        Handle the Jira login flow for a user.

        Args:
            message (str): The "username:password" string from the user.
            mcp_manager (MCPManagerService): Service for managing MCP servers.

        Returns:
            bool: True if login is successful, False otherwise.
        """
        # TODO: This flow is shit, we need to convert to OAuth2.0 or LDAP to authenticate for jira
        # Parse username/password
        username, password = message.split(':')

        # Generate PAT with 1d expire
        basic_auth_token = self._generate_basic_auth_token(username, password)

        # Revoke unused token
        await self._revoke_unuse_token(userpass=message)

        url = f"{self.root_mcp_config.mcp_config.jira.jira_base_url}/rest/pat/latest/tokens"

        payload = json.dumps({
            "name": "BeeChatJirassistant_1d",
            "expirationDuration": 90
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': basic_auth_token,
        }

        response = requests.request(
            "POST", url, headers=headers, data=payload, verify=False)
        if response.status_code != 201:
            return False
        auth_header = f"Token {response.json()['rawToken']}"

        # Store encrypted token to db
        await self.user_service.set_token(
            username=username, jira_pat_plain=auth_header)

        # Add jira mcp with token
        result = await mcp_manager.add_sse_server_user(
            username=username,
            name='jira',
            url=self.root_mcp_config.mcp_config.jira.jira_mcp_url,
            headers={
                "Authorization": auth_header
            },
            tool_filter=jira_tool_filter
        )
        return result

    async def _restore_jira_session(self, username: str, mcp_manager: MCPManagerService):
        user_jira_pat = await self.user_service.get_token(username)

        # Add jira mcp with token
        try:
            result = await mcp_manager.add_sse_server_user(
                username=username,
                name='jira',
                url=self.root_mcp_config.mcp_config.jira.jira_mcp_url,
                headers={
                    "Authorization": user_jira_pat.get("jira_pat", "")
                },
                tool_filter=jira_tool_filter
            )
            if await self._check_token_alive(username=username, mcp_manager=mcp_manager):
                return True
            else:
                remove_res = await mcp_manager.remove_mcp_of_user(username, 'jira')
                return False
        # This exception is not a bug, exception throw is acceptable for this checking case
        except Exception as e:
            LOGGER.debug(f"Restore Jira session of `{username}` failed: {e}")
            return False

    def is_valid_username_password_format(self, s: str) -> bool:
        """
        Check if a string is in the exact format "username:password".

        - Username must have at least one character and cannot contain a colon.
        - Password must have at least one character.
        - There must be exactly one colon separating username and password.

        Args:
            s (str): The string to check.

        Returns:
            bool: True if the string matches the format, False otherwise.
        """
        if not isinstance(s, str):  # Optional: handle non-string inputs gracefully
            return False

        pattern = r"^[^:]+:.+$"
        # re.fullmatch() checks if the entire string matches the pattern
        if re.match(pattern, s):
            return True
        else:
            return False

    def _generate_basic_auth_token(self, username, password):
        """
        Generate a Basic Authentication token for HTTP headers.

        Args:
            username (str): The username.
            password (str): The password.

        Returns:
            str: The Basic Authentication token.
        """
        token = f"{username}:{password}"
        token_bytes = token.encode('ascii')
        base64_bytes = base64.b64encode(token_bytes)
        base64_token = base64_bytes.decode('ascii')
        return f"Basic {base64_token}"
