import asyncio
import os
from pathlib import Path
from beegen.configs.memory.mem0_config import Mem0MemoryConfig
from beegen.memory.factory import MemoryFactory
from beegen.configs.memory.memory_config import MemoryConfig
from beegen.registry.resource_factory import ResourceFactory
from beegen.registry.resource_hub import ResourceHub

USER_ID = "hieuvt"
MESSAGES = [
    {"role": "user", "content": "Bạn lên lịch xem phim tối nay cho tôi"},
    {"role": "assistant", "content": "Ok. Bạn có thích phim kinh dị không ?"},
    {"role": "user", "content": "Tôi không phải fan phim kinh dị nhưng tôi thích phim khoa học viễn tưởng"},
    {"role": "assistant",
     "content": "Ok. Tôi sẽ tránh phim kinh dị và ưu tiên phim khoa học viễn tưởng"},
    {"role": "user", "content": "Nhưng lâu rôi tôi không xem phim kinh dị. Cho tôi vài gợi ý đi"},

    {"role": "assistant",
     "content": "Nếu bạn muốn làm quen lại thì tôi gợi ý vài phim nhẹ nhàng trước: A Quiet Place, The Others hoặc The Woman in Black. Bạn thích kiểu kinh dị tâm lý hay kinh dị siêu nhiên?"},
    {"role": "user",
     "content": "Chắc là kinh dị tâm lý, tôi không thích mấy cảnh máu me cho lắm."},
    {"role": "assistant",
     "content": "Vậy bạn có thể xem The Babadook hoặc The Invitation. Hai phim này tập trung vào cảm giác căng thẳng và tâm lý, hầu như không có cảnh gore."},
    {"role": "user",
     "content": "Nghe cũng ổn. Nhưng thôi, để tối nay xem sci-fi vẫn hay hơn. Có phim nào mới không?"},    
    {"role": "assistant",
     "content": "Dune Part Two, Rebel Moon và The Creator đều mới và được đánh giá khá cao. Bạn thích phim có tiết tấu nhanh hay thiên về triết lý?"},

    {"role": "user",
     "content": "Tôi đang hơi mệt, xem cái gì nhẹ nhàng thôi. Hoặc có thể chuyển sang xem series cũng được."},
    {"role": "assistant",
     "content": "Nếu bạn muốn nhẹ nhàng thì có series Upload (hài – sci-fi) hoặc Severance (sci-fi nhưng nhẹ về action). Bạn muốn xem bao nhiêu tập tối nay?"},

    {"role": "user",
     "content": "Chắc 1–2 tập là đủ. Nhưng mà trước khi xem, tôi muốn nấu gì đó. Có món nào đơn giản không?"},
    {"role": "assistant",
     "content": "Bạn có thể làm mì Ý sốt kem nấm, chỉ mất 15 phút. Hoặc sandwich trứng nếu thích nhanh gọn. Bạn có đủ nguyên liệu không?"},

    {"role": "user",
     "content": "Có đủ hết. À mà này… bạn có biết tối nay có mưa không? Tôi tính mở cửa sổ cho mát."},
    {"role": "assistant",
     "content": "Dự báo thời tiết nói tối nay có khả năng mưa nhẹ. Nếu mở cửa sổ bạn nên để rèm phòng khi gió tạt mưa vào."},

    {"role": "user",
     "content": "Ok. Sau khi xem phim chắc tôi sẽ đọc sách. Bạn có gợi ý sách khoa học hoặc tâm lý học không?"},
    {"role": "assistant",
     "content": "Bạn có thể đọc Sapiens của Yuval Noah Harari (khoa học – lịch sử) hoặc Thinking, Fast and Slow (tâm lý học hành vi). Cả hai đều rất dễ đọc trước khi ngủ."}
]

async def setup_memory():
    """
    Set up the memory instance for testing.
    """
    # os.environ["OPENAI_API_KEY"] = "sk-_FcF3ua4t3rRfFtmTJQgHQ"
    # os.environ["OPENAI_BASE_URL"] = "https://llm-gateway-dev.mbbank.com.vn/"
    # os.environ["NO_PROXY"] = "llm-gateway-dev.mbbank.com.vn"

    config = Mem0MemoryConfig.default()
    memory = ResourceFactory.create(config=config)
    
    return memory

if __name__ == "__main__":
    mem = asyncio.run(setup_memory())
    print(mem)