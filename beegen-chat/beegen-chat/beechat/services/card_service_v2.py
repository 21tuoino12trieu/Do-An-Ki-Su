import asyncio
from typing import Dict, List, Any
from jsonpath_ng import parse

from beechat.services.document_service import core_search_banking_knowledge
from beechat.services.llm_service import LLMService
from beechat.utils.card_tree_init import CARD_HIERARCHY_NEW
from beechat.utils.prompt_loader import get_prompt
from beechat.utils.pyinstrument_profiler import profile_async_func
from beegenerate.configs import ParserType
from beegenerate.loggings import LOGGER
from beegen_v1.parser.parser_factory import OutputParserFactory
from langfuse.decorators import observe, langfuse_context


def find_card_path(card_name: str, tree: dict = None) -> List[Dict]:
    """
    Tìm path phân cấp của thẻ trong CARD_HIERARCHY_NEW từ gốc đến node khớp.
    Returns: List[Dict] e.g. [{"name": "Thẻ đa năng"}, {"name": "Hi LOL"}]
    """
    if tree is None:
        tree = CARD_HIERARCHY_NEW

    target_clean = card_name.lower().strip()

    def _search_node(node_dict: dict, current_path: list):
        for key, value in node_dict.items():
            if not isinstance(value, dict):
                continue

            node_name = value.get("name", key)
            keywords = [k.lower() for k in value.get("keywords", [])]
            node_clean = node_name.lower()

            new_path = current_path + [{"name": node_name, "key": key}]

            # Matches node name or keywords
            if (target_clean == node_clean or 
                target_clean in keywords or 
                any(target_clean in k for k in keywords) or
                any(k in target_clean for k in keywords if len(k) > 3)):
                return new_path

            if "children" in value and isinstance(value["children"], dict):
                sub_result = _search_node(value["children"], new_path)
                if sub_result:
                    return sub_result

        return None

    for category_key, category_dict in tree.items():
        if isinstance(category_dict, dict):
            res = _search_node(category_dict, [])
            if res:
                return res

    return []


@observe()
@profile_async_func("Card Hierarchy Search - search_card_info_hierarchy")
async def search_card_info_hierarchy(
        card_name: str,
        tool_context: Any = None
) -> str:
    """
    Tra cứu thông tin chi tiết về thẻ và các cấp cha của nó (phân loại thẻ).
    Dùng khi cần biết về một loại thẻ cụ thể (vd: Wukong, Visa Hybrid, Thẻ tín dụng...), 
    tính năng, ưu đãi và mối liên hệ của nó trong hệ thống thẻ MB.

    Args:
        card_name (str): Tên loại thẻ hoặc nhóm thẻ cần tra cứu.

    Returns:
        str: Thông tin chi tiết về thẻ và các cấp cha liên quan.
    """
    LOGGER.info(f"Card Agent searching hierarchy for: {card_name}")
    langfuse_context.update_current_observation(input={"card_name": card_name})

    path = find_card_path(card_name)
    if not path:
        LOGGER.info(f"No hierarchy path found for {card_name}, falling back to general search.")
        return await core_search_banking_knowledge(card_name)

    # path trả về list các node từ gốc đến node khớp. Ví dụ: [{"name": "Thẻ đa năng"}, {"name": "Hi LOL"}]
    node_names = [node["name"] for node in path if node.get("name")]
    target_node = node_names[-1]

    # Limit search targets to max 2 (card_name and parent_node) to reduce API calls & context size
    if len(node_names) > 1:
        parent_node = node_names[-2]
        hierarchy_str = ", ".join(node_names[::-1][1:])
        relationship_summary = f"Thẻ '{card_name}' (thuộc nhóm {target_node}) là một loại thẻ thuộc dòng thẻ {hierarchy_str}."
        search_targets = [card_name, parent_node]
    else:
        relationship_summary = f"Thông tin về thẻ {card_name} (thuộc nhóm {target_node})."
        search_targets = [card_name]

    # Loại bỏ các từ khóa trùng lặp để giảm thiểu số lần gọi API
    seen = set()
    unique_targets = []
    for t in search_targets:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_targets.append(t)

    LOGGER.info(f"Unique search targets for card hierarchy (max 2): {unique_targets}")

    # 2. Search thông tin cho thẻ và cấp cha với page_size=2 và threshold=0.7
    search_tasks = [core_search_banking_knowledge(name, page_size=2, threshold=0.7) for name in unique_targets]
    search_results = await asyncio.gather(*search_tasks)

    # 3. Tổng hợp kết quả
    parts = [f"=== MỐI QUAN HỆ THẺ ===\n{relationship_summary}\n(Lưu ý cho LLM: Thẻ này sẽ kế thừa các tính năng, đặc quyền và biểu phí của các dòng thẻ cha nêu trên)"]

    for name, content in zip(unique_targets, search_results):
        if "Không có tài liệu phù hợp" not in content and "dưới ngưỡng" not in content.lower():
            LOGGER.info(f"Retrieved card info for target '{name}' ({len(content)} chars)")
            parts.append(f"--- Thông tin về {name} ---\n{content}")
        else:
            LOGGER.info(f"No suitable card info found for target '{name}'")

    res_str = "\n\n".join(parts)
    if len(res_str) > 12000:
        res_str = res_str[:12000] + "\n\n[Dữ liệu tài liệu thẻ đã được tối ưu độ dài...]"

    langfuse_context.update_current_observation(output=res_str)
    return res_str


class CardService:
    """Dịch vụ xử lý truy vấn thẻ ngân hàng với logic phân cấp và Vertex AI Search."""

    def __init__(self, bot_id: str, llm_service: LLMService):
        """Khởi tạo dịch vụ thẻ với các thành phần cần thiết."""
        self.bot_id = bot_id
        self.llm_service = llm_service
        self.xml_parser = OutputParserFactory.create(format=ParserType.XML)
        LOGGER.info(f"Initialized CardService for bot: {bot_id}")

    @observe()
    async def run(self, state: Dict) -> Dict:
        """Xử lý truy vấn thẻ với logic phân cấp Vertex AI Search."""
        query = state.get('enhanced_query', state['query'])
        LOGGER.info(f"Processing card query: {query}")
        langfuse_context.update_current_observation(input={"query": query})

        # Fast-path: Kiểm tra Python find_card_path trực tiếp trước để tránh gọi LLM Task phụ
        python_path = find_card_path(query)
        if python_path:
            node_names = [node["name"] for node in python_path if node.get("name")]
            card_name = node_names[-1]
            LOGGER.info(f"[CardService Fast-Path] Python matched card hierarchy: '{card_name}' (Bypassed LLM Keyword Extract Task).")
        else:
            # Fallback gọi LLM để xác định từ khóa thẻ nếu không tìm thấy trực tiếp
            response = await self.llm_service.llm_task(
                inputs={"query": query, "CARD_HIERARCHY": CARD_HIERARCHY_NEW},
                prompt_template=get_prompt("CARD_KEYWORD_EXTRACT_PROMPT_V2")
            )

            # Parse kết quả XML
            xml_result = await self.xml_parser.parse(text=response)
            extracted_keyword = xml_result.get('keyword', '').strip()
            node_key = xml_result.get('node', '').strip()

            LOGGER.info(f"Extracted card keyword: '{extracted_keyword}', node: '{node_key}'")

            if node_key == "unknown" or not extracted_keyword:
                card_name = query
            else:
                card_name = extracted_keyword

        search_result_text = await search_card_info_hierarchy(card_name)

        doc = {
            "id": f"card_hierarchy_{card_name}",
            "content": search_result_text,
            "score": 1.0
        }

        res = {
            "is_leaf": True,
            "value": [doc],
            "node_name": card_name
        }
        langfuse_context.update_current_observation(output=res)
        return res


async def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("==================================================")
    print(" CARD SERVICE HIERARCHY TEST (VERTEX AI SEARCH)")
    print("==================================================")

    llm_service = LLMService("test_bot")
    card_service = CardService("test_bot", llm_service)

    test_queries = [
        "Tôi muốn hỏi thông tin thẻ Wukong",
        "Ưu đãi thẻ Visa Hybrid MB"
    ]

    for q in test_queries:
        print(f"\n Testing query: '{q}'")
        res = await card_service.run({"query": q})
        docs = res.get('value', [])
        print(f"Node Name: {res.get('node_name')}")
        if docs:
            print(f"Content Preview:\n{docs[0]['content'][:300]}...\n")
        print("-" * 50)

    print("\n Card Service Test Complete!")


if __name__ == "__main__":
    asyncio.run(main())
