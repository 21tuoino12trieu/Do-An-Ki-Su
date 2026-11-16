"""
Unified Message-based Conversation Processor - Enhanced with Profile Integration

Xử lý conversation messages để tạo enhanced query và quyết định flow termination.
Enhanced version đảm bảo luôn load được account context từ user profile.
"""
from typing import List, Dict, Tuple, Optional
from beechat.services.llm_service import LLMService
from beegen_v1.parser.implementations.xml import XMLOutputParser
from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf


class ConversationProcessor:
    """
    Enhanced processor chuyên xử lý conversation messages với profile integration.

    Chức năng chính:
    - Phân tích messages để tạo enhanced query
    - Quyết định có nên terminate flow hiện tại hay không
    - Tích hợp account context từ user profile một cách nhất quán
    - Hỗ trợ context từ balance coordinator cho account information
    """

    def __init__(self, llm_service: LLMService) -> None:
        """Khởi tạo conversation processor với enhanced profile support."""
        self.llm_service = llm_service
        self.balance_coordinator = None
        self.user_profile_service = None

    def set_balance_coordinator(self, coordinator) -> None:
        """Set coordinator reference cho việc lấy account context."""
        self.balance_coordinator = coordinator

    def set_user_profile_service(self, user_profile_service) -> None:
        """Set user profile service reference."""
        self.user_profile_service = user_profile_service
        LOGGER.info("User profile service injected into ConversationProcessor")

    async def process_messages(
            self,
            messages: List[Dict],
            session_id: Optional[str] = None,
            session_manager=None,
            user_profile_service=None
    ) -> Tuple[str, str]:
        """MAIN METHOD: Xử lý messages và trả về enhanced query + flow decision."""
        if not messages:
            LOGGER.warning("Empty messages list provided to process_messages")
            return "", "continue"

        try:
            recent_messages = messages[-15:] if len(messages) > 15 else messages
            account_context = self._get_account_context_from_profile(session_id, user_profile_service)

            if len(messages) == 1:
                return messages[0]['content'].strip(), "continue"

            enhanced_query, flow_decision = await self._enhance_from_full_conversation(
                recent_messages, account_context, session_id, user_profile_service
            )

            # Handle account_selection result from prompt
            if enhanced_query == "account_selection" and session_id and session_manager:
                if hasattr(session_manager, 'reset_balance_context'):
                    session_manager.reset_balance_context(session_id)

            return enhanced_query, flow_decision

        except Exception as e:
            LOGGER.error(f"Critical error in process_messages - Session: {session_id}, Error: {str(e)}")
            last_message = messages[-1].get('content', 'Câu hỏi không rõ') if messages else 'Câu hỏi không rõ'
            return last_message, "continue"

    def _get_account_context_from_profile(
            self,
            session_id: Optional[str] = None,
            user_profile_service=None
    ) -> str:
        """Get account context from user profile service with consistent sorting."""
        effective_service = user_profile_service or self.user_profile_service

        if not effective_service:
            return ""

        accounts = effective_service.get_sorted_user_accounts(session_id)
        if not accounts:
            return ""

        return self._format_account_context_for_prompt(accounts)

    async def _enhance_from_full_conversation(
            self,
            messages: List[Dict],
            account_context: str = "",
            session_id: Optional[str] = None,
            user_profile_service=None
    ) -> Tuple[str, str]:
        """Enhanced processing với account context được cung cấp trực tiếp cho LLM."""
        full_conversation = self._format_conversation(messages)
        current_user_message = messages[-1]['content'].strip()

        if not account_context:
            account_context = self._get_account_context_from_profile(session_id, user_profile_service)

        LOGGER.info(f"Conversation:{full_conversation}")

        response = await self.llm_service.llm_task(
            inputs={
                'full_conversation': full_conversation,
                'account_context': account_context,
                'current_user_message': current_user_message,
            },
            prompt_template=lf.get_prompt("BEECHAT_KHCN_ENHANCED_CONVERSATION_WITH_FLOW_PROMPT"),
            use_primary=True,
            stream=False,
            tempature=0
        )

        return await self._parse_enhancement_response(response)

    def _format_account_context_for_prompt(self, account_list: List[str]) -> str:
        """Format account list for prompt context."""
        if not account_list:
            return "Không có tài khoản khả dụng"

        formatted_lines = [f"{i}. **{account}** (TK{i})"
                           for i, account in enumerate(account_list, 1)]

        return f"Danh sách tài khoản khả dụ:\n" + "\n".join(formatted_lines)

    async def _parse_enhancement_response(self, response: str) -> Tuple[str, str]:
        """Parse LLM XML response để lấy enhanced query và flow decision."""
        xml_parser = XMLOutputParser()

        parsed_result = await xml_parser.parse(text=response)

        enhanced_query = parsed_result.get('enhanced_query', '').strip()
        flow_decision = parsed_result.get('flow_decision', 'continue').strip()

        if not enhanced_query:
            lines = response.strip().split('\n')
            enhanced_query = lines[0].strip() if lines else ""

        if flow_decision not in ["continue", "new_flow"]:
            flow_decision = "continue"

        return enhanced_query, flow_decision

    def _format_conversation(self, messages: List[Dict]) -> str:
        """Format conversation messages cho LLM processing."""
        formatted = []
        for i, msg in enumerate(messages):
            role = "USER" if msg.get("role") == "user" else "BOT"
            content = msg.get("content", "").strip()
            if content:
                formatted.append(f"[{i + 1}] {role}: {content}")
        return "\n".join(formatted)