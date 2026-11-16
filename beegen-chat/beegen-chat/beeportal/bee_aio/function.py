from typing import Any, Dict, List, Optional
from unidecode import unidecode
import re

# ── Pure functions ────────────────────────────────────────────────────────────

def collect_response(result: str, session_id: str) -> Dict[str, Any]:
    """
    Trích xuất bot_response từ BeegenExecutorNode output.

    BeegenExecutorNode output schema:
        result      : str   — nội dung full text sau stream
        success     : bool
        error       : str | None
        matched_bot : str
    """
    return {
        "bot_response": result,
        "redis_key": f"chat_history:{session_id}"
    }

def map_guardrail_category_response(category: str) -> Dict[str, str]:
    responses = {
        "0": "Xin lỗi, tôi không thể cung cấp thông tin nội bộ hoặc hỗ trợ các yêu cầu can thiệp vào hệ thống.",
        "1": "Xin lỗi, tôi không thể hỗ trợ các hoạt động vi phạm pháp luật hoặc gây ảnh hưởng đến người khác.",
        "2": "Tôi rất tiếc khi biết bạn đang gặp khó khăn. Nếu bạn đang gặp nguy hiểm hoặc có ý định làm hại bản thân, hãy liên hệ ngay với người thân hoặc cơ sở hỗ trợ gần nhất.",
        "3": "Xin lỗi, tôi không thể hỗ trợ nội dung tình dục hoặc khiêu dâm.",
        "4": "Xin lỗi, tôi không thể hỗ trợ các nội dung kích động bạo lực hoặc vi phạm pháp luật.",
        "5": "Tôi rất tiếc vì trải nghiệm chưa tốt. Bạn có thể cho biết mã lỗi hoặc thời điểm xảy ra sự cố để tôi hỗ trợ kiểm tra không?",
        "6": "Xin lỗi, tôi không thể hỗ trợ các hoạt động cá cược hoặc cờ bạc.",
        "7": "Tôi không thể hỗ trợ nội dung bói toán hoặc mê tín.",
    }
    return {"response": responses.get(str(category))}

def normalize(text: str) -> str:
    text = unidecode(text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w_]", "", text)
    return text.upper()

def init_query(
    messages: List[Dict[str, Any]],
    # metadata: Dict
) -> Dict[str, Any]:
    """
    Formats a list of message dictionaries into a structure with query and history.
    
    Takes the most recent message as the query and formats up to 20 previous messages
    as history with "USER:" or "BOT:" prefixes.
    
    Args:
        messages: List of message dictionaries with 'content' and 'role' keys
    
    Returns:
        origin_query (str): The content of the most recent message
        conversation (List[str]): Formatted list of previous messages
        agents (List[Dict]): List of agents
    """
    # query = messages[-1]['content']        
    history = [
        f"USER: {m['content']}" 
        if m['role']=='user' 
        else f"BOT: {m['content']}" 
        for m in messages[-7:-1]
    ]

    return {
        "conversation": history,
    }

def is_image_message(messages: List[Dict[str, Any]]) -> bool:
    """
    Kiểm tra xem messages có chứa ảnh hay không.
    
    Returns:
        True nếu có ít nhất 1 message chứa image_url, False nếu thuần text.
    """
    return any(
        isinstance(msg.get('content'), list) and
        any(
            isinstance(part, dict) and part.get('type') == 'image_url'
            for part in msg['content']
        )
        for msg in messages
    )

def extract_text_and_images(messages: List[Dict[str, Any]]) -> Dict[str, Any]:

    user_message = next(
        (msg for msg in reversed(messages)
         if isinstance(msg, dict)                              
         and msg.get('role') == 'user' 
         and isinstance(msg.get('content'), list)),
        None
    )

    if not user_message:
        return {"text": "", "images": []}

    text_parts = []
    images = []

    for part in user_message['content']:
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'text':
            text_parts.append(part.get('text', ''))
        elif part.get('type') == 'image_url':
            url = part.get('image_url', {}).get('url', '')
            if url:
                images.append(url)

    return {
        "text": ' '.join(text_parts).strip(),
        "images": images,
    }


# ---------------------------------------------------------------------------
# Helper code functions
# ---------------------------------------------------------------------------

def check_agent_count(metadata: Dict) -> Dict:
    """Kiểm tra số lượng agent, trả về cờ cần retriever hay không."""
    
    filtered_agents = metadata["agents"]

    return {"need_retriever": len(filtered_agents) > 7,
            "agents": filtered_agents}

def get_agent_by_bot_id(agents: str, metadata: Dict) -> Dict:
    agent_info = next(
        (
            {
                "name": agent["name"],
                "agent_type": agent.get("agent_type", "beeflow")
            }
            for agent in metadata["agents"]
            if agent["bot_id"] == agents
        ),
        None
    )

    return {
        "extract_bot_id": {
            "bot_id":           agents,
            "status_response":  f"Đang điều hướng tới agent: {agent_info["name"]} và tìm kiếm câu trả lời..."
        },
        "executor_type": agent_info["agent_type"]
    }

def get_input_workflow(
    messages: List[Dict],
    session_id: str,
    role_ids: List[str] = [],
) -> Dict:

    return {"workflow_inputs": 
                {   "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids,
                    }
                }

# ---------------------------------------------------------------------------
# CodeNode function: chuẩn bị bot_id + bot_inputs cho BeegenExecutorNode
# ---------------------------------------------------------------------------

def get_input_beegen(
    messages: List[Dict],
    beegen_id: str,
    role_ids: List[str] = [],
    topic: str = "default",
) -> Dict[str, Any]:
    """
    Tương tự get_input_workflow nhưng cho beegen.
    Trả về bot_id và bot_inputs theo interface Bot.run().
    """
    return {
        "bot_id": beegen_id,
        "bot_inputs": {
            "messages": messages,
            "role_ids": role_ids,
            "topic": topic,
        },
    }


def convert_to_beegen_input(workflow_inputs: Dict[str, Any], role: List[str] = None, bot_id: str = None) -> Dict[str, Any]:
    """
    Chuyển đổi workflow_inputs sang format bot_inputs cho BeegenExecutorNode.
    """
    messages = workflow_inputs.get("messages", [])
    return {
        "bot_inputs": {
            "messages": messages,
            "role_ids": ["L1"],
            "topic": "default",
            "bot_id": bot_id,
        },
    }


def merge_executor_response(
    agent_result: Optional[Any] = None,
    beegen_result: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Merge response từ agent_executor và beegen_executor.
    Lấy kết quả đầu tiên khác None.
    """
    result = agent_result if agent_result is not None else beegen_result
    return {"result": result}

def prepare_bot_id(selected_bot_id: str):
    return {
        "bot_id": selected_bot_id
    } 

if __name__ == "__main__":
    messages_template=[
    {
        "content": "Chào bạn! Mình là Trợ lý bán hàng thông minh. Hãy chọn sản phẩm để mình gợi ý các kịch bản bán hàng hiệu quả nhé! <Button: Tín dụng> <Button: Huy động> <Button: CDs> <Button: Bancas><Button: Thẻ><Button: SP Đầu tư><Button: Kiều hối>",
        "role": "assistant"
    },
    {
        "content": "Thẻ",
        "role": "user"
    },
    {
        "content": """Để xây dựng kịch bản bán hàng bám sát đặc điểm và nhu cầu của Khách hàng, bạn vui lòng cung cấp bổ sung các thông tin sau:

Chân dung khách hàng: phân khúc, giới tính, độ tuổi, nghề nghiệp...
Điểm chạm khách hàng (nếu có): được anh Hiếu giới thiệu, gặp KH giao dịch tại quầy...
Tình huống bán: KH từ chối do đã có nhiều thẻ; phí cao; thủ tục phức tạp; chưa có nhu cầu...""",
        "role": "assistant"
    },
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Trích xuất toàn bộ thông tin có trong ảnh, chỉ trả thông tin đã bóc tách. Không giải thích hay yêu cầu gì thêm."},
            {
                "type": "image_url", 
                "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"}
            },
            {
                "type": "image_url", 
                "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"}
            }
        ]
    }     

]
    result = extract_text_and_images(messages_template)
    print(result)
