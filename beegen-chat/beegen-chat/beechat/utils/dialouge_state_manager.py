# Đặt lớp này ở đầu file beechat.py hoặc trong một file tiện ích riêng
from typing import Dict

from beegenerate.loggings import LOGGER


class DialogueStateManager:
    """
    Quản lý trạng thái hội thoại trong bộ nhớ.
    Đây là một triển khai đơn giản cho mục đích phát triển và gỡ lỗi.
    Trong production, nên thay thế bằng một giải pháp bền vững hơn như Redis.
    """
    def __init__(self):
        self._states: dict = {}
        LOGGER.info("In-memory DialogueStateManager initialized.")

    async def load_state(self, dialogue_id: str) -> dict:
        """Tải trạng thái từ bộ nhớ. Trả về một bản sao để tránh thay đổi ngoài ý muốn."""
        if dialogue_id in self._states:
            LOGGER.info(f"State found for dialogue_id: {dialogue_id}")
            # Trả về một bản sao (copy) để đảm bảo trạng thái gốc không bị thay đổi
            # cho đến khi được lưu lại một cách tường minh.
            return self._states[dialogue_id].copy()
        LOGGER.info(f"No state found for new dialogue_id: {dialogue_id}")
        return {}

    async def save_state(self, dialogue_id: str, state: dict):
        """Lưu trạng thái vào bộ nhớ."""
        LOGGER.info(f"Saving state for dialogue_id: {dialogue_id} with keys: {state.keys()}")
        self._states[dialogue_id] = state

    async def delete_state(self, dialogue_id: str):
        """Xóa trạng thái khỏi bộ nhớ."""
        if dialogue_id in self._states:
            del self._states[dialogue_id]
            LOGGER.info(f"Deleted state for dialogue_id: {dialogue_id}")

