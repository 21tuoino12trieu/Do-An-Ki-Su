
import asyncio
import logging
from typing import Dict, Optional, AsyncGenerator
from contextvars import ContextVar
from datetime import datetime

from ag_ui.core import Event,CustomEvent
from beegenerate.loggings import LOGGER

class EventStreamManager:
    """
    Quản lý luồng sự kiện cốt lõi - không chứa logic nghiệp vụ.
    Chỉ quản lý các phiên (sessions) và phát các sự kiện (events) đến các phiên đó.
    """
    
    def __init__(self):
        # Dictionary lưu trữ các hàng đợi sự kiện cho từng phiên.
        # Mỗi phiên có một asyncio.Queue riêng để chứa các sự kiện.
        self._sessions: Dict[str, asyncio.Queue] = {}
        # Dictionary theo dõi trạng thái hoạt động của từng phiên (True nếu đang hoạt động, False nếu đã đóng).
        self._active_sessions: Dict[str, bool] = {}
        # Dictionary lưu trữ siêu dữ liệu (metadata) của từng phiên, ví dụ: thời gian tạo, số lượng sự kiện.
        self._session_metadata: Dict[str, dict] = {}
    
    def create_session(self, session_id: str, metadata: dict = None) -> str:
        """
        Tạo một phiên streaming mới.

        Args:
            session_id (str): ID duy nhất cho phiên mới.
            metadata (dict, optional): Siêu dữ liệu bổ sung cho phiên. Mặc định là None.

        Returns:
            str: ID của phiên vừa được tạo.
        """
        # Khởi tạo một hàng đợi asyncio mới cho phiên, giới hạn kích thước để tránh tràn bộ nhớ.
        self._sessions[session_id] = asyncio.Queue(maxsize=1000)
        # Đặt trạng thái phiên là hoạt động.
        self._active_sessions[session_id] = True
        # Lưu trữ siêu dữ liệu của phiên.
        self._session_metadata[session_id] = {
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "event_count": 0
        }
        LOGGER.info(f"Đã tạo phiên streaming: {session_id}")
        return session_id
    
    async def emit_event(self, session_id: str, event: Event) -> bool:
        """
        Phát một sự kiện đến một phiên cụ thể.

        Args:
            session_id (str): ID của phiên nhận sự kiện.
            event (Event): Đối tượng sự kiện AG-UI cần phát.

        Returns:
            bool: True nếu sự kiện được thêm vào hàng đợi thành công, False nếu phiên không hoạt động
                  hoặc hàng đợi đã đầy.
        """
        if not self.is_session_active(session_id):
            LOGGER.warning(f"Phiên {session_id} không hoạt động, bỏ qua sự kiện: {event.type}")
            return False
        
        try:
            if not self._sessions[session_id].full():
                await self._sessions[session_id].put(event)
                self._session_metadata[session_id]["event_count"] += 1
                LOGGER.debug(f"Đã phát sự kiện {event.type} đến phiên {session_id}")
                return True
            else:
                LOGGER.warning(f"Hàng đợi đầy cho phiên {session_id}, bỏ qua sự kiện: {event.type}")
                return False
        except Exception as e:
            LOGGER.error(f"Lỗi khi phát sự kiện đến phiên {session_id}: {e}")
            return False
    
    async def stream_events(self, session_id: str, timeout: int = 5) -> AsyncGenerator[str, None]:
        """
        Tạo một luồng sự kiện (Server-Sent Events - SSE) cho một phiên.
        Generator này sẽ liên tục lấy các sự kiện từ hàng đợi của phiên và định dạng chúng thành chuỗi SSE.

        Args:
            session_id (str): ID của phiên cần tạo luồng sự kiện.
            timeout (int, optional): Thời gian chờ tối đa (giây) để lấy một sự kiện từ hàng đợi.
                                     Nếu hết thời gian chờ, một sự kiện heartbeat sẽ được gửi. Mặc định là 30.

        Yields:
            str: Chuỗi sự kiện đã được định dạng theo chuẩn SSE (ví dụ: "data: {json_event}\n\n").
        """
        if not self.session_exists(session_id):
            LOGGER.error(f"Không tìm thấy phiên {session_id}")
            return
        
        LOGGER.info(f"Bắt đầu luồng sự kiện cho phiên: {session_id}")
        
        while self.is_session_active(session_id):
            try:

                event = await asyncio.wait_for(
                    self._sessions[session_id].get(),
                    timeout=timeout
                )
                
                event_json = event.model_dump_json()
                LOGGER.debug(f"Nhận sự kiện cho session {session_id}: {event_json}")
                yield f"data: {event_json}\n\n"
                
            except asyncio.TimeoutError as ex:
                # Phát sự kiện heartbeat nếu không có sự kiện nào trong khoảng thời gian timeout
                LOGGER.error(f"Timeout trong luồng cho phiên {session_id}: {ex}")
                heartbeat = CustomEvent(
                    name="heartbeat",
                    value={"session_id": session_id, "timestamp": datetime.now().isoformat()}
                )
                yield f"data: {heartbeat.model_dump_json()}\n\n"
            except Exception as e:
                LOGGER.error(f"Lỗi trong luồng sự kiện cho phiên {session_id}: {e}")
                break # Thoát khỏi vòng lặp nếu có lỗi nghiêm trọng
        
        LOGGER.info(f"Luồng sự kiện đã kết thúc cho phiên: {session_id}")
    
    def close_session(self, session_id: str) -> bool:
        """
        Đóng một phiên streaming và dọn dẹp tài nguyên liên quan.

        Args:
            session_id (str): ID của phiên cần đóng.

        Returns:
            bool: True nếu phiên được đóng thành công, False nếu phiên không tồn tại.
        """
        if not self.session_exists(session_id):
            return False
        
        # Đặt trạng thái phiên là không hoạt động.
        self._active_sessions[session_id] = False
        
        # Xóa tất cả các sự kiện còn lại trong hàng đợi của phiên.
        if session_id in self._sessions:
            while not self._sessions[session_id].empty():
                try:
                    self._sessions[session_id].get_nowait()
                except asyncio.QueueEmpty:
                    break
            del self._sessions[session_id] # Xóa hàng đợi khỏi danh sách phiên
        
        # Xóa siêu dữ liệu của phiên.
        if session_id in self._session_metadata:
            del self._session_metadata[session_id]
        
        LOGGER.info(f"Đã đóng phiên: {session_id}")
        return True
    
    def session_exists(self, session_id: str) -> bool:
        """
        Kiểm tra xem một phiên có tồn tại hay không.

        Args:
            session_id (str): ID của phiên cần kiểm tra.

        Returns:
            bool: True nếu phiên tồn tại, False nếu không.
        """
        return session_id in self._sessions
    
    def is_session_active(self, session_id: str) -> bool:
        """
        Kiểm tra xem một phiên có đang hoạt động hay không.

        Args:
            session_id (str): ID của phiên cần kiểm tra.

        Returns:
            bool: True nếu phiên đang hoạt động, False nếu không hoặc không tồn tại.
        """
        return self._active_sessions.get(session_id, False)
    
    def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        Lấy thông tin chi tiết về một phiên cụ thể.

        Args:
            session_id (str): ID của phiên cần lấy thông tin.

        Returns:
            Optional[dict]: Một dictionary chứa thông tin phiên (ID, trạng thái hoạt động, kích thước hàng đợi, metadata)
                            hoặc None nếu phiên không tồn tại.
        """
        if not self.session_exists(session_id):
            return None
        
        return {
            "session_id": session_id,
            "active": self.is_session_active(session_id),
            "queue_size": self._sessions[session_id].qsize(),
            **self._session_metadata[session_id]
        }
    
    def get_all_sessions(self) -> list:
        """
        Lấy thông tin của tất cả các phiên đang được quản lý.

        Returns:
            list: Một danh sách các dictionary, mỗi dictionary chứa thông tin của một phiên.
        """
        return [
            self.get_session_info(session_id)
            for session_id in self._sessions.keys()
        ]

# Thể hiện (instance) toàn cục của EventStreamManager để sử dụng dễ dàng trong ứng dụng.
stream_manager = EventStreamManager()
