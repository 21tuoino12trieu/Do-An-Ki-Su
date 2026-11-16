
from datetime import datetime
import json
from typing import Any, Optional, Dict
from ag_ui.core import (
    Event,RunStartedEvent, RunFinishedEvent, RunErrorEvent,
    StepStartedEvent, StepFinishedEvent,
    TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent,
    CustomEvent
)

from beegenerate.loggings.loggers import LOGGER
from .manager import stream_manager
from .context import get_current_session, get_current_thread, get_current_run

def _with_raw(payload: Dict[str, Any], raw_event: Optional[Any]) -> Dict[str, Any]:
    """
    Thêm raw_event vào payload nếu nó không phải là None.
    """
    if raw_event is not None:
        payload["raw_event"] = raw_event
    return payload

class EventEmitter:
    """
    Bộ phát sự kiện cốt lõi - chỉ chịu trách nhiệm phát các sự kiện, không chứa logic nghiệp vụ.
    Tất cả các sự kiện đều được định tuyến đến `stream_manager` để xử lý và phân phối.
    """
    
    @staticmethod
    async def _emit_to_manager(session_id: str, event: Event) -> bool:
        """
        Phương thức nội bộ để gửi một sự kiện đến EventStreamManager.

        Args:
            session_id (str): ID của phiên mà sự kiện này thuộc về.
            event (Event): Đối tượng sự kiện AG-UI cần phát.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không (ví dụ: phiên không hoạt động hoặc hàng đợi đầy).
        """
        LOGGER.info(f"Phát sự kiện {event.type} cho phiên {session_id}\r\n")
        return await stream_manager.emit_event(session_id, event)

    @staticmethod
    async def emit_run_started(raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `RunStartedEvent` khi một quá trình chạy mới bắt đầu.
        Sự kiện này đánh dấu sự khởi đầu của một chuỗi các hoạt động.

        Args:
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện RunStartedEvent.")
            return False
        
        payload = {
            "thread_id": get_current_thread(),
            "run_id": get_current_run()
        }
        event = RunStartedEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_run_finished(result: Any = None, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `RunFinishedEvent` khi một quá trình chạy hoàn tất.
        Sự kiện này có thể bao gồm kết quả cuối cùng của quá trình.

        Args:
            result (Any, optional): Kết quả của quá trình chạy. Mặc định là None.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện RunFinishedEvent.")
            return False
        
        payload = {
            "thread_id": get_current_thread(),
            "run_id": get_current_run(),
            "result": result,
            "timestamp": int(datetime.now().timestamp())
        }
        event = RunFinishedEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_run_error(message: str, code: Optional[str] = None, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `RunErrorEvent` khi có lỗi xảy ra trong quá trình chạy.

        Args:
            message (str): Thông điệp lỗi.
            code (Optional[str], optional): Mã lỗi. Mặc định là None.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện RunErrorEvent.")
            return False
        
        payload = {
            "message": message,
            "code": code
        }
        event = RunErrorEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_step_started(step_name: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `StepStartedEvent` khi một bước cụ thể trong quá trình chạy bắt đầu.

        Args:
            step_name (str): Tên của bước bắt đầu.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện StepStartedEvent.")
            return False
        
        payload = {
            "step_name": step_name,
            "timestamp": int(datetime.now().timestamp())
        }
        event = StepStartedEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_step_finished(step_name: str,  raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `StepFinishedEvent` khi một bước cụ thể trong quá trình chạy hoàn tất.

        Args:
            step_name (str): Tên của bước đã hoàn thành.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện StepFinishedEvent.")
            return False
        
        payload = {
            "step_name": step_name,
            "timestamp": int(datetime.now().timestamp())
        }
        event = StepFinishedEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_text_message_start(message_id: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `TextMessageStartEvent` khi một tin nhắn văn bản mới bắt đầu.

        Args:
            message_id (str): ID duy nhất của tin nhắn văn bản.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện TextMessageStartEvent.")
            return False
        
        payload = {
            "message_id": message_id,
            "timestamp": int(datetime.now().timestamp())
        }
        event = TextMessageStartEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_text_message_content(message_id: str, delta: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `TextMessageContentEvent` chứa một phần nội dung của tin nhắn văn bản.
        Sự kiện này thường được sử dụng để truyền tải nội dung tin nhắn theo từng phần (streaming).

        Args:
            message_id (str): ID của tin nhắn văn bản mà nội dung này thuộc về.
            delta (str): Phần nội dung văn bản mới được thêm vào.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện TextMessageContentEvent.")
            return False
        
        payload = {
            "message_id": message_id,
            "delta": delta,
            "timestamp": int(datetime.now().timestamp())
        }
        event = TextMessageContentEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_text_message_end(message_id: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `TextMessageEndEvent` khi một tin nhắn văn bản hoàn tất.

        Args:
            message_id (str): ID của tin nhắn văn bản đã hoàn tất.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện TextMessageEndEvent.")
            return False
        
        payload = {
            "message_id": message_id,
            "timestamp": int(datetime.now().timestamp())
        }
        event = TextMessageEndEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_tool_call_start(tool_call_id: str, tool_name: str, parent_message_id: Optional[str] = None, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `ToolCallStartEvent` khi một lời gọi công cụ (tool call) bắt đầu.

        Args:
            tool_call_id (str): ID duy nhất của lời gọi công cụ.
            tool_name (str): Tên của công cụ được gọi.
            parent_message_id (Optional[str], optional): ID của tin nhắn cha đã kích hoạt lời gọi công cụ này. Mặc định là None.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện ToolCallStartEvent.")
            return False
        
        payload = {
            "tool_call_id": tool_call_id,
            "tool_call_name": tool_name,
            "parent_message_id": parent_message_id,
            "timestamp": int(datetime.now().timestamp())
        }
        event = ToolCallStartEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_tool_call_args(tool_call_id: str, delta: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `ToolCallArgsEvent` chứa một phần đối số của lời gọi công cụ.
        Sự kiện này được sử dụng để truyền tải đối số theo từng phần (streaming).

        Args:
            tool_call_id (str): ID của lời gọi công cụ mà đối số này thuộc về.
            delta (str): Phần đối số mới được thêm vào.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện ToolCallArgsEvent.")
            return False
        
        payload = {
            "tool_call_id": tool_call_id,
            "delta": delta,
            "timestamp": int(datetime.now().timestamp())
        }
        event = ToolCallArgsEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_tool_call_end(tool_call_id: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `ToolCallEndEvent` khi một lời gọi công cụ hoàn tất.

        Args:
            tool_call_id (str): ID của lời gọi công cụ đã hoàn tất.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện ToolCallEndEvent.")
            return False
        
        payload = {
            "tool_call_id": tool_call_id,
            "timestamp": int(datetime.now().timestamp())
        }
        event = ToolCallEndEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
    
    @staticmethod
    async def emit_tool_call_result(message_id: str, tool_call_id: str, content: str, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra sự kiện `ToolCallResultEvent` chứa kết quả của một lời gọi công cụ.

        Args:
            message_id (str): ID của tin nhắn mà kết quả này liên quan.
            tool_call_id (str): ID của lời gọi công cụ đã tạo ra kết quả này.
            content (str): Nội dung kết quả từ lời gọi công cụ.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện ToolCallResultEvent.")
            return False
        
        payload = {
            "message_id": message_id,
            "tool_call_id": tool_call_id,
            "content": content,
            "timestamp": int(datetime.now().timestamp())
        }
        event = ToolCallResultEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)

    @staticmethod
    async def emit_custom_event(name: str, value: Any, raw_event: Optional[Any] = None) -> bool:
        """
        Phát ra một sự kiện tùy chỉnh `CustomEvent`.
        Sự kiện này có thể được sử dụng để truyền tải bất kỳ thông tin tùy chỉnh nào không thuộc các loại sự kiện tiêu chuẩn.

        Args:
            name (str): Tên của sự kiện tùy chỉnh.
            value (Any): Giá trị hoặc payload của sự kiện tùy chỉnh.
            raw_event (Optional[Any], optional): Sự kiện thô (raw) đi kèm; chỉ được đưa vào event khi khác None. Mặc định None.

        Returns:
            bool: True nếu sự kiện được phát thành công, False nếu không tìm thấy session_id.
        """
        session_id = get_current_session()
        if not session_id:
            LOGGER.warning("Không tìm thấy session_id để phát sự kiện CustomEvent.")
            return False
        
        payload = {
            "name": name,
            "value": value,
            "timestamp": int(datetime.now().timestamp())
        }
        event = CustomEvent(**_with_raw(payload, raw_event))
        return await EventEmitter._emit_to_manager(session_id, event)
# Thể hiện (instance) toàn cục của EventEmitter để sử dụng dễ dàng
emitter = EventEmitter()
