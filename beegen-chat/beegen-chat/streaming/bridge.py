import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import AsyncIterable, Optional, Union, Any

from .emitters import emitter
from .context import current_session_id, current_thread_id, current_run_id

# Định danh công khai cho các kiểu chunk từ nhà cung cấp mà bridge có thể tiêu thụ
Chunk = Union[str, dict]


class GeneratorEventBridge:
    """
    Kết nối một luồng chunk bất đồng bộ (ví dụ: token hoặc sự kiện có cấu trúc từ nhà cung cấp)
    thành các sự kiện tuân thủ AG-UI thông qua EventEmitter.

    Trách nhiệm
    - Bọc một tin nhắn văn bản duy nhất bằng `text_message_start` / `text_message_end`.
    - Chuyển đổi các chunk thành `text_message_content` (hoặc `custom_event` khi payload là dict).
    - Phát ra `run_finished` khi hoàn thành bình thường.
    - Tùy chọn phát tín hiệu heartbeat để giữ các trung gian hoạt động.
    - Hủy bỏ hợp tác và dọn dẹp tài nguyên.

    Cách sử dụng
    -------
        agen = await chat_service.process_message_stream(prompt)
        bridge = GeneratorEventBridge()
        await bridge.run(agen)
    """

    def __init__(
        self,
        *,
        message_id_factory=lambda: None,
        chunk_to_text=lambda c: c if isinstance(c, str) else c.get("text", ""),
        chunk_to_custom=lambda c: c if isinstance(c, dict) else None,
    ) -> None:
        self._message_id_factory = message_id_factory
        self._chunk_to_text = chunk_to_text
        self._chunk_to_custom = chunk_to_custom

    @asynccontextmanager
    async def _message_envelope(self):
        msg_id = self._message_id_factory() or "msg_1"
        await emitter.emit_text_message_start(msg_id)
        try:
            yield msg_id
        finally:
            # Đảm bảo chúng ta luôn đóng tin nhắn, ngay cả khi có lỗi/hủy bỏ
            await emitter.emit_text_message_end(msg_id)

    async def run(self, agen: AsyncIterable[Chunk]) -> None:
        """
        Tiêu thụ một iterable bất đồng bộ của các chunk và phát ra các sự kiện AG-UI.

        Hợp đồng
        --------
        - Giả định các bao bọc run/step có thể được xử lý bởi một decorator hoặc caller.
        - Đảm bảo `run_finished` khi hoàn thành bình thường.
        - Khi hủy bỏ, phát ra một sự kiện tùy chỉnh `generator_cancelled`.
        """
        try:
            async with self._message_envelope() as msg_id:
                async for chunk in agen:
                    # Lập lịch hợp tác để chuyển đổi tác vụ công bằng
                    await asyncio.sleep(0)

                    # Nếu chunk dạng dict mang thông tin có cấu trúc → custom_event; ngược lại là văn bản
                    custom_payload = self._chunk_to_custom(chunk)
                    if custom_payload is not None:
                        await emitter.emit_custom_event("generator_payload", custom_payload)
                        continue

                    text_part = self._chunk_to_text(chunk)
                    if text_part:
                        await emitter.emit_text_message_content(msg_id, text_part)

            # Hoàn thành bình thường
            await emitter.emit_run_finished({"reason": "completed"})

        except asyncio.CancelledError:
            # Hủy bỏ hợp tác: thông báo cho client/UI
            await emitter.emit_custom_event(
                "generator_cancelled",
                {
                    "session_id": current_session_id.get(),
                    "thread_id": current_thread_id.get(),
                    "run_id": current_run_id.get(),
                },
            )
            raise
        except Exception as e:  # Tùy chọn: hiển thị lỗi từ nhà cung cấp cho UI
            await emitter.emit_custom_event(
                "error",
                {
                    "code": "provider_stream_error",
                    "message": str(e),
                    "session_id": current_session_id.get(),
                },
            )
            # Bạn cũng có thể quyết định phát ra run_finished ở đây với reason=error
            await emitter.emit_run_finished({"reason": "error"})
            raise
