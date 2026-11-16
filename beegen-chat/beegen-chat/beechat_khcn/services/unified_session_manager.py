"""
Unified Session Manager - Centralized session management cho tất cả domains
Enhanced với domain-specific state management
"""

from typing import Dict, Optional, Any, List
from datetime import datetime
from beegenerate.loggings import LOGGER


class UnifiedSessionManager:
    """
    Centralized session management thay thế session logic rải rác
    Thống nhất session cho deposit, balance_retrieve, card domains
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict] = {}
        LOGGER.info("UnifiedSessionManager initialized")

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Get complete session state"""
        return self._sessions.get(session_id, {})

    def update_conversation_context_for_card(self, session_id: str, enhanced_query: str, messages: List[Dict[str, Any]]) -> None:
        """Update conversation context để card service có thể sử dụng conversation_summary_query"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }

        self._sessions[session_id].update({
            'enhanced_query': enhanced_query,
            'conversation_context': {
                'messages': messages[-5:] if len(messages) > 5 else messages,
                'summary': 'Cuộc hội thoại về dịch vụ ngân hàng'
            },
            'last_updated': datetime.now().isoformat()
        })

        LOGGER.info(f"📝 [SESSION_CARD] Updated context for card domain - session: {session_id}")

    def update_session_state(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Update session state with new data"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }

        self._sessions[session_id].update(updates)
        self._sessions[session_id]['last_updated'] = datetime.now().isoformat()

        LOGGER.debug(f"Session {session_id} updated with: {list(updates.keys())}")

    def get_collection_state(self, session_id: str) -> Dict[str, Any]:
        """Get current attribute collection state"""
        session = self.get_session_state(session_id)
        return session.get('collection_state', {})

    def save_collection_state(self, session_id: str, collection_state: Dict[str, Any]) -> None:
        """Save attribute collection state"""
        collection_state['saved_at'] = datetime.now().isoformat()
        self.update_session_state(session_id, {'collection_state': collection_state})
        LOGGER.info(f"Collection state saved for session {session_id}")

    def clear_collection_state(self, session_id: str) -> None:
        """Clear collection state when completed or cancelled"""
        session = self.get_session_state(session_id)
        if 'collection_state' in session:
            del session['collection_state']
            self.update_session_state(session_id, {'collection_cleared_at': datetime.now().isoformat()})
            LOGGER.info(f"Collection state cleared for session {session_id}")

    def is_collecting(self, session_id: str) -> bool:
        """Check if session is in collection mode"""
        collection_state = self.get_collection_state(session_id)
        return bool(collection_state.get('active_intent'))

    def get_domain_state(self, session_id: str, domain: str) -> Dict[str, Any]:
        """Get domain-specific state (balance, deposit, card)"""
        session = self.get_session_state(session_id)
        domain_states = session.get('domain_states', {})
        return domain_states.get(domain, {})

    def update_domain_state(self, session_id: str, domain: str, state_updates: Dict[str, Any]) -> None:
        """Update domain-specific state"""
        session = self.get_session_state(session_id)

        if 'domain_states' not in session:
            session['domain_states'] = {}

        if domain not in session['domain_states']:
            session['domain_states'][domain] = {}

        session['domain_states'][domain].update(state_updates)
        session['domain_states'][domain]['last_updated'] = datetime.now().isoformat()

        self.update_session_state(session_id, session)
        LOGGER.debug(f"Domain state '{domain}' updated for session {session_id}")

    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get conversation history with optional limit"""
        session = self.get_session_state(session_id)
        history = session.get('conversation_history', [])
        return history[-limit:] if limit else history

    def add_conversation_turn(self, session_id: str, user_message: str, bot_response: str) -> None:
        """Add conversation turn to history"""
        session = self.get_session_state(session_id)

        if 'conversation_history' not in session:
            session['conversation_history'] = []

        turn = {
            'timestamp': datetime.now().isoformat(),
            'user_message': user_message,
            'bot_response': bot_response[:500] + '...' if len(bot_response) > 500 else bot_response
        }

        session['conversation_history'].append(turn)

        if len(session['conversation_history']) > 20:
            session['conversation_history'] = session['conversation_history'][-20:]

        self.update_session_state(session_id, session)

    def get_user_context(self, session_id: str) -> Dict[str, Any]:
        """Get user context information - Enhanced with profile"""
        session = self.get_session_state(session_id)
        profile_info = session.get('user_profile', {})

        return {
            'user_name': session.get('user_name') or profile_info.get('xung_ho'),
            'user_profile': profile_info,
            'current_topic': session.get('current_topic'),
            'current_intent': session.get('current_intent'),
            'last_activity': session.get('last_updated'),
            'session_duration': self._calculate_session_duration(session),
            'total_interactions': len(session.get('conversation_history', []))
        }

    def save_user_profile(self, session_id: str, profile_data: Dict[str, Any]) -> None:
        """Save user profile data to session"""
        self.update_session_state(session_id, {'user_profile': profile_data})
        LOGGER.info(f"👤 User profile saved for session {session_id}")

    def get_user_profile(self, session_id: str) -> Dict[str, Any]:
        """Get user profile data from session"""
        session = self.get_session_state(session_id)
        return session.get('user_profile', {})

    def _calculate_session_duration(self, session: Dict[str, Any]) -> Optional[str]:
        """Calculate session duration in human-readable format"""
        created_at = session.get('created_at')
        if not created_at:
            return None

        try:
            created_time = datetime.fromisoformat(created_at)
            duration = datetime.now() - created_time

            if duration.days > 0:
                return f"{duration.days} ngày"
            elif duration.seconds > 3600:
                hours = duration.seconds // 3600
                return f"{hours} giờ"
            elif duration.seconds > 60:
                minutes = duration.seconds // 60
                return f"{minutes} phút"
            else:
                return f"{duration.seconds} giây"
        except Exception:
            return None

    def reset_balance_context(self, session_id: str) -> None:
        """
        Reset toàn bộ balance context khi user đổi tài khoản.
        Xóa collection_state và domain_state của balance_retrieve.
        """
        session = self.get_session_state(session_id)

        if 'collection_state' in session:
            del session['collection_state']

        if 'domain_states' in session and 'balance_retrieve' in session['domain_states']:
            del session['domain_states']['balance_retrieve']

        session['balance_context_reset_at'] = datetime.now().isoformat()
        self.update_session_state(session_id, session)

        LOGGER.info(f"Balance context reset for session {session_id}")