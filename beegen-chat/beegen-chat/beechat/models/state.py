from typing import List, Dict, Any, Optional


class State:
    """
    Lightweight state container for conversation context.
    Designed to be created and used within a single request.
    """

    @staticmethod
    def create_from_messages(
            query: str,
            messages: List[Dict],
            correlation_id: str = None,
            metadata: Dict = None
    ) -> Dict[str, Any]:
        """
        Create a simple state dictionary from messages.

        Args:
            query: The current query (usually the last message)
            messages: List of all conversation messages
            correlation_id: Optional ID for tracing
            metadata: Optional additional metadata

        Returns:
            Dict containing state information
        """
        # Format conversation history
        conversation_history = []
        for i, message in enumerate(messages[:-1]):  # Skip current message
            role_name = "Người dùng" if message['role'] == 'user' else "BOT"
            conversation_history.append(f"{role_name} ({i + 1}): {message['content']}")

        # Create state dictionary
        return {
            'query': query,
            'messages': messages,
            'latest_message': messages[-1]['content'] if messages else "",
            'conversation_history': conversation_history,
            'metadata': metadata or {},
            'correlation_id': correlation_id,
            # Empty placeholders for analysis results
            'intent_analysis': {},
            'topic_analysis': {},
            'card_analysis': {},
            'cache_check': {},
            'document_results': {},
            'greeting':{},
            'card_clarity':{}
        }

    @staticmethod
    def add_intent_analysis(state: Dict, intent_data: Dict) -> Dict:
        """Add intent analysis results to state."""
        new_state = state.copy()
        new_state['intent_analysis'] = intent_data
        return new_state

    @staticmethod
    def add_topic_analysis(state: Dict, topic_data: Dict) -> Dict:
        """Add topic analysis results to state."""
        new_state = state.copy()
        new_state['topic_analysis'] = topic_data
        return new_state

    @staticmethod
    def add_card_analysis(state: Dict, card_data: Dict) -> Dict:
        """Add card analysis results to state."""
        new_state = state.copy()
        new_state['card_analysis'] = card_data
        return new_state

    @staticmethod
    def add_cache_check(state: Dict, cache_data: Dict) -> Dict:
        """Add cache check results to state."""
        new_state = state.copy()
        new_state['cache_check'] = cache_data
        return new_state

    @staticmethod
    def add_document_results(state: Dict, document_data: Dict) -> Dict:
        """Add document retrieval results to state."""
        new_state = state.copy()
        new_state['document_results'] = document_data
        return new_state

    @staticmethod
    def get_intent(state: Dict) -> str:
        """Get the intent from state."""
        return state.get('intent_analysis', {}).get('intent', 'require_document')

    @staticmethod
    def get_topic(state: Dict) -> str:
        """Get the topic from state."""
        return state.get('topic_analysis', {}).get('Topic', 'khác')

    @staticmethod
    def needs_clarification(state: Dict) -> bool:
        """Check if query needs clarification."""
        return state.get('intent_analysis', {}).get('needs_clarification', False)

    @staticmethod
    def has_cache_hit(state: Dict) -> bool:
        """Check if there's a cache hit."""
        return state.get('cache_check', {}).get('check', False)

    @staticmethod
    def get_cache_reference(state: Dict) -> Optional[Dict]:
        """Get the cache reference if available."""
        return state.get('cache_check', {}).get('ref')

    @staticmethod
    def needs_card_clarification(state: Dict) -> bool:
        """Check if card information needs clarification."""
        card_analysis = state.get('card_analysis', {})

        # Kiểm tra explicit needs_clarification flag
        if card_analysis.get('needs_clarification', False):
            return True

        # Kiểm tra tất cả các node có node con
        if card_analysis.get('matched_nodes') and card_analysis.get('children'):
            top_node = card_analysis.get('matched_nodes')[0]

            # Danh sách các danh mục cần hỏi lại thông tin khi có con
            clarification_categories = [
                'card_types',  # Loại thẻ (tín dụng, ghi nợ,...)
                'brands',  # Thương hiệu (Visa, Mastercard,...)
                'product_lines',  # Dòng sản phẩm (Hi, Priority,...)
                'specific_products'  # Sản phẩm cụ thể nếu có thêm biến thể
            ]

            if top_node.get('category') in clarification_categories and len(card_analysis.get('children', [])) > 0:
                return True

        return False

    @staticmethod
    def has_card_matches(state: Dict) -> bool:
        """Check if there are matching cards."""
        return bool(state.get('card_analysis', {}).get('matched_ids', []))

    @staticmethod
    def get_card_state(state: Dict) -> Dict:
        """Get card-specific state information."""
        return state.get('card_analysis', {})

    @staticmethod
    def update_card_state(state: Dict, updates: Dict) -> Dict:
        """Update card-specific state."""
        new_state = state.copy()
        card_state = new_state.get('card_analysis', {})
        card_state.update(updates)
        new_state['card_analysis'] = card_state
        return new_state

    @staticmethod
    def needs_card_clarification(state: Dict) -> bool:
        """Enhanced check for card clarification needs."""
        card_state = state.get('card_analysis', {})

        # Check explicit needs_clarification flag
        if card_state.get('needs_clarification', False):
            return True

        # Check for product lines needing clarification
        if card_state.get('matched_nodes'):
            top_node = card_state['matched_nodes'][0]
            if (top_node.get('category') == 'product_lines' and
                    top_node.get('id') in ['hi', 'priority', 'standard']):
                if card_state.get('children'):
                    return True

        return False