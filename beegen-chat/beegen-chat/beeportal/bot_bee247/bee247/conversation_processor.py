import asyncio
from typing import List, Dict, Tuple

from beechat.services.llm_service import LLMService
from beegenerate.loggings import LOGGER
from beegenerate.prompts.bee247 import BEE247_ENHANCED_CONVERSATION_WITH_FLOW_PROMPT


class ConversationProcessor:
    def __init__(self, bot_id: str) -> None:
        self.llm_service = LLMService(bot_id=bot_id)

    def _format_conversation(self, messages: List[Dict]) -> str:
        """
        Định dạng danh sách hội thoại thành một chuỗi văn bản.

        Args:
            messages (List[Dict]): Danh sách các tin nhắn trong hội thoại,
                mỗi tin nhắn là một dict có ít nhất các khóa:
                - "role": Vai trò của người gửi ("user" hoặc "assistant").
                - "content": Nội dung tin nhắn (str).

        Returns:
            str: Chuỗi hội thoại đã được định dạng, mỗi dòng có dạng:
                 "USER: <nội dung>" hoặc "BOT: <nội dung>".
        """
        formatted = []
        for message in messages:
            role = "USER" if message.get("role") == "user" else 'BOT'
            content = message.get("content").strip()

            if content:
                formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    async def _enhance_from_full_conversation(
            self,
            recent_messages: List[Dict],
    ) -> Tuple[str, str]:
        full_conversation = self._format_conversation(messages=recent_messages)
        history = full_conversation.rsplit("\n", 1)[0]
        current_user_message = recent_messages[-1]['content'].strip()

        LOGGER.info(f"Conversation:{full_conversation}")

        response = await self.llm_service.llm_task(
            inputs={
                'full_conversation': full_conversation,
                'current_user_message': current_user_message
            },
            prompt_template=BEE247_ENHANCED_CONVERSATION_WITH_FLOW_PROMPT,
            use_primary=True,
            stream=False,
            tempature=0
        )
        LOGGER.info(f"response {response}")
        if response.startswith("**Enhanced Query:**"):
            enhanced_query = response.replace("**Enhanced Query:**", "").strip()
            return enhanced_query, history
        else:
            enhanced_query = (
                response.split(":**")[1] if ":**" in response else
                response.split(":")[1] if ":" in response else
                None
            ).strip()
        return enhanced_query, history

    async def process_messages(self,
                               messages: List[Dict]) -> Tuple[str, str]:
        if not messages:
            LOGGER.warning("✅ User profile service injected into ConversationProcessor")

        if len(messages) == 1:
            return messages[0]['content'].strip(), None

        try:
            recent_message = messages[-15:] if len(messages) > 15 else messages

            enhanced_query, history = await self._enhance_from_full_conversation(
                recent_messages=recent_message,
            )

            return enhanced_query, history

        except Exception as e:
            LOGGER.warning(f"Error in process_messages, Error: {e}")

            last_message = messages[-1].get('content', 'Câu hỏi không rõ') if messages else 'Câu hỏi không rõ'
            return last_message, None


async def main():
    obj0 = LLMService('cbc75713-2646-4331-84ad-645664ab86ef')
    obj1 = ConversationProcessor(obj0)
    last_message, _ = await obj1.process_messages(
        messages=[{"role": "user", "content": "chào bạn"},
                  {"role": "assistant",
                   "content": "Chào bạn! Tôi là Bee-247, trợ lý ảo của ngân hàng MB. Rất vui được hỗ trợ bạn hôm nay. Bạn đang cần tôi giúp gì? 😊"},
                  {"role": "user", "content": "CTUD thẻ JCB/ Visa"},
                  {"role": "assistant",
                   "content": """### **Ưu đãi dành cho thẻ JCB**
1. **Hoàn tiền 500.000 VNĐ khi chi tiêu bằng thẻ MB JCB**
   - **Nội dung:** Hoàn tiền 500.000 VNĐ khi khách hàng chi tiêu bằng thẻ MB JCB.
   - **Khám phá ưu đãi:**
     - **Ẩm thực:** GOGI, KICHI, MANWAH...
     - **Mua sắm:** AEON MALL, SHOPEE, FPT...
     - **Du lịch:** AGODA, PHÒNG CHỜ...
     - **Giải trí:** CGV, APPLE STORE...
     - **Sức khỏe y tế:** TRẢ GÓP BỆNH VIỆN, NHÀ THUỐC AN KHANG...
   - **Chi tiết chương trình:** [Xem tại đây](https://www.mbbank.com.vn/chi-tiet/tin-khuyen-mai-khcn/hoan-tien-500000-d-khi-chi-tieu-bang-the-mb-jcb-2025-6-3-15-0-12/5390).

2. **Gieo Tri Thức - Lời Tương Lai cùng thẻ MB JCB**
   - **Nội dung:** Hoàn 1.000.000 VNĐ cho mỗi giao dịch chi tiêu tích lũy từ 10 triệu đồng trong lĩnh vực giáo dục.
   - **Danh sách MCC giáo dục được ưu đãi:** 7295, 8211, 8220, 8241, 8244, 8299, 8352.
   - **Ví dụ:** Nếu bạn chi tiêu 10 triệu VNĐ tại các MCC giáo dục hợp lệ, bạn sẽ được hoàn 1 triệu VNĐ.

---

### **Ưu đãi dành cho thẻ Visa**
1. **Đặc quyền INFINITE dành cho chủ thẻ MB Visa hợp lệ**
   - **Nội dung:**
     - **Du lịch:**
       - Giảm đến 30% (tối đa 300 USD) khi đặt phòng tại các khách sạn 4 sao trở lên qua [Agoda.com/VisaInfiniteVN](https://www.agoda.com/VisaInfiniteVN).
       - Thời hạn đặt phòng: Đến 30/09/2025.
       - Thời gian lưu trú: Đến 30/06/2026.
     - **Nâng hạng khách sạn cao cấp:**
       - Tận hưởng ưu đãi nâng hạng phòng và các ưu tiên đặc biệt miễn phí tại hàng trăm khách sạn, resort hàng đầu thế giới như Six Senses Resorts, Mandarin Oriental, Park Hyatt, Aman Resorts...
       - Thời gian áp dụng: Đến 31/12/2025.
       - Đặt phòng tại: [VisaLuxuryHotels.com](https://www.visaluxuryhotels.com).
   - **Lưu ý:** Ưu đãi chỉ áp dụng cho thẻ Visa Infinite hợp lệ và thanh toán bằng thẻ.

---

Nếu bạn cần thêm thông tin chi tiết hoặc hỗ trợ về các chương trình ưu đãi, vui lòng cho tôi biết nhé! Cảm ơn bạn đã quan tâm. 😊"""},
                  {"role": "user", "content": "Chi tiết vể chương trình ưu đãi INFINITE của thẻ Visa mà bạn đề cập"}]
    )
    print("enhanced_query: ", last_message)


if __name__ == "__main__":
    asyncio.run(main())
