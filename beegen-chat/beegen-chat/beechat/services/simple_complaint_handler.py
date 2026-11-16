# services/simple_complaint_handler.py
import json
import os
from typing import AsyncGenerator, Dict, Tuple, Optional, List

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk


class SimpleComplaintHandler:
    """
    Xử lý đơn giản cho các khiếu nại giao dịch,
    sử dụng kịch bản có sẵn để trả lời người dùng.
    """

    def __init__(self, llm_service):
        """Khởi tạo với LLM service."""
        self.llm_service = llm_service

        # Mô tả cho các loại khiếu nại
        self.complaint_descriptions = {
            "transfer_failure": "giao dịch chuyển tiền không thành công",
            "topup_issue": "nạp tiền điện thoại không thành công",
            "wrong_transfer": "chuyển tiền nhầm tài khoản",
            "card_transaction_issue": "vấn đề giao dịch thẻ",
            "atm_withdrawal_issue": "rút tiền ATM không thành công",
            "staff_complaint": "thái độ nhân viên",
            "card_delivery_issue": "chưa nhận được thẻ",
            "app_transaction_issue": "lỗi giao dịch trên ứng dụng",
            "other_complaint": "khiếu nại khác"
        }

        # Tải kịch bản phản hồi
        self.scenarios = self._load_scenarios()
        self.complaint_to_scenario_mapping = self.scenarios.get("mapping", {})

    def _load_scenarios(self) -> Dict:
        """
        Tải kịch bản từ file JSON hoặc sử dụng kịch bản mặc định nếu không tìm thấy file.
        """
        scenarios_path = os.path.join(os.path.dirname(__file__), "complaint_scenarios.json")
        if os.path.exists(scenarios_path):
            with open(scenarios_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # Kịch bản mặc định nếu không tìm thấy file
        return {
            "scenarios": {
                "staff_attitude": {
                    "id": "staff_attitude",
                    "title": "Khiếu nại về thái độ nhân viên MB",
                    "response": "Bee chân thành xin lỗi vì sự việc đã xảy ra trong quá trình bạn sử dụng sản phẩm dịch vụ tại MB.  Bạn vui lòng chọn **\"Liên hệ tư vấn viên\"** để được xử lý nhanh chóng."
                },
                "transfer_failure": {
                    "id": "transfer_failure",
                    "title": "Chuyển tiền không thành công",
                    "response": "Bee rất xin lỗi vì sự bất tiện này!  Để được xử lý nhanh chóng về vấn đề chuyển tiền không thành công,  bạn vui lòng chọn **\"Liên hệ tư vấn viên\"** để được hỗ trợ ngay."
                },
                "general_complaint": {
                    "id": "general_complaint",
                    "title": "Khiếu nại chung",
                    "response": "Bee chân thành xin lỗi vì trải nghiệm chưa tốt của bạn khi sử dụng dịch vụ MB.  Bạn vui lòng chọn **\"Liên hệ tư vấn viên\"** để được hỗ trợ xử lý khiếu nại một cách nhanh chóng."
                }
            },
            "mapping": {
                "staff_complaint": "staff_attitude",
                "transfer_failure": "transfer_failure",
                "topup_issue": "general_complaint",
                "wrong_transfer": "transfer_failure",
                "card_transaction_issue": "general_complaint",
                "atm_withdrawal_issue": "general_complaint",
                "card_delivery_issue": "general_complaint",
                "app_transaction_issue": "general_complaint",
                "other_complaint": "general_complaint"
            }
        }

    def _get_scenario_for_complaint(self, complaint_type: str) -> Optional[Dict]:
        """
        Lấy kịch bản phù hợp cho loại khiếu nại.

        Args:
            complaint_type: Loại khiếu nại đã được phân loại

        Returns:
            Dict scenario hoặc None nếu không tìm thấy
        """
        # Map complaint type to scenario ID
        scenario_id = self.complaint_to_scenario_mapping.get(complaint_type)
        if not scenario_id:
            # Fallback to general complaint
            scenario_id = "general_complaint"

        # Get scenario details
        scenario = self.scenarios.get("scenarios", {}).get(scenario_id)
        return scenario

    def has_complaint_mapping(self, complaint_type: str) -> bool:
        """
        Kiểm tra xem complaint type có mapping với scenario không.

        Args:
            complaint_type: Loại khiếu nại cần kiểm tra

        Returns:
            True nếu có mapping, False nếu không
        """
        return complaint_type in self.complaint_to_scenario_mapping

    def _extract_xml_value(self, xml_text: str, tag: str) -> Optional[str]:
        """
        Extract value from XML tag (giữ lại cho compatibility nhưng không sử dụng).

        Args:
            xml_text: XML text to parse
            tag: XML tag name to extract

        Returns:
            Extracted value or None if not found
        """
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"

        if start_tag in xml_text and end_tag in xml_text:
            start_idx = xml_text.find(start_tag) + len(start_tag)
            end_idx = xml_text.find(end_tag)
            if start_idx < end_idx:
                value = xml_text[start_idx:end_idx].strip()
                return value if value and value.lower() != "none" else None

        return None

    async def extract_staff_complaint_info(self, messages: List[Dict]) -> Dict:
        """
        Giữ lại method cho compatibility nhưng trả về empty dict.

        Args:
            messages: Lịch sử tin nhắn

        Returns:
            Empty dict cho compatibility
        """
        return {
            'location': None,
            'time': None,
            'content': None
        }

    async def handle_staff_complaint_with_collection(
            self,
            messages: List[Dict],
            existing_info: Optional[Dict] = None
    ) -> Tuple[AsyncGenerator, Dict]:
        """
        Xử lý khiếu nại nhân viên - giờ chỉ sử dụng kịch bản có sẵn.

        Args:
            messages: Lịch sử tin nhắn
            existing_info: Thông tin đã thu thập từ trước (không sử dụng nữa)

        Returns:
            Tuple (generator cho response, empty dict)
        """
        # Luôn sử dụng kịch bản có sẵn cho staff_complaint
        return self.handle_complaint("staff_complaint"), {}

    async def handle_complaint(self, complaint_type: str, query: str = None) -> AsyncGenerator[
        ChatCompletionChunk, None]:
        """
        Handle complaint with direct mapping to predefined scenarios.

        Args:
            complaint_type: Complaint type from analysis_prompt
            query: Original query (optional, not used in simplified version)

        Yields:
            ChatCompletionChunk: Response chunks with status code 206

        Raises:
            ValueError: If no scenario found (e.g., for 'other_complaint')
        """
        # Get scenario directly by mapping
        scenario = self._get_scenario_for_complaint(complaint_type)

        if not scenario:
            # Fallback to general complaint
            scenario = self.scenarios.get("scenarios", {}).get("general_complaint")
            if not scenario:
                raise ValueError(f"No scenario found for complaint type: {complaint_type}")

        response = scenario.get("response")
        if not response:
            raise ValueError(f"No response found in scenario for complaint type: {complaint_type}")

        # Create simple prompt for exact response
        prompt = f"""
        Vai trò: Bee - trợ lý ảo ngân hàng MB

        Nhiệm vụ: Trả lời CHÍNH XÁC phản hồi được cung cấp mà không thay đổi nội dung.

        Phản hồi cần trả lại:
        "{response}"

        Lưu ý:
        - KHÔNG thay đổi nội dung
        - KHÔNG thêm lời chào hay câu kết
        - Trả về phản hồi CHÍNH XÁC như đã cung cấp
        """

        # Stream response with status code 206 (Meet Consultant)
        async for chunk in self.llm_service.llm_stream(
                prompt_template=prompt,
                sleep=0.01
        ):
            # Add status code 206 to each chunk
            chunk_dict = chunk.model_dump()
            chunk_dict["status_code"] = 206
            chunk_dict["status_message"] = "meet_consultant"
            modified_chunk = ChatCompletionChunk(**chunk_dict)

            yield modified_chunk


def extract_transaction_complaint_info(xml_text: str) -> Dict:
    """
    Extract complaint information from XML text.
    """
    result = {}
    start_tag = "<transaction_complaint>"
    end_tag = "</transaction_complaint>"
    if start_tag in xml_text and end_tag in xml_text:
        start_idx = xml_text.find(start_tag) + len(start_tag)
        end_idx = xml_text.find(end_tag)
        if start_idx < end_idx:
            complaint_type = xml_text[start_idx:end_idx].strip()
            if complaint_type:
                result['complaint_type'] = complaint_type
    return result