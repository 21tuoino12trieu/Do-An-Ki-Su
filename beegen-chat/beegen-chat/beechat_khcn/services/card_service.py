import json
from typing import Dict, List
from jsonpath_ng import parse

from beechat.prompts import CARD_KEYWORD_EXTRACT_PROMPT_V2
from beechat.services.document_service import DocumentService
from beechat.services.llm_service import LLMService
from beechat.utils.card_tree_init import CARD_HIERARCHY_NEW
from beegenerate.configs import ParserType
from beegenerate.loggings import LOGGER
from beegen_v1.parser.parser_factory import OutputParserFactory


class CardService:
    """Dịch vụ xử lý truy vấn thẻ ngân hàng với logic phân cấp."""

    def __init__(self, bot_id: str, llm_service: LLMService):
        """Khởi tạo dịch vụ thẻ với các thành phần cần thiết."""
        self.bot_id = bot_id
        self.collection_card = f"bot_{bot_id.replace('-', '_')}_THE"
        self.collection_main = f"bot_{bot_id.replace('-', '_')}"
        self.llm_service = llm_service
        self._doc_service = DocumentService(
            llm_service=self.llm_service,
            bot_id=self.bot_id
        )
        self.xml_parser = OutputParserFactory.create(format=ParserType.XML)
        self.special_card_keywords = []

    async def run(self, state: Dict) -> Dict:
        """Xử lý truy vấn thẻ với logic đơn giản và rõ ràng."""
        query = state.get('enhanced_query', state['query'])
        LOGGER.info(f"Processing card query: {query}")

        # Gọi LLM để xác định từ khóa thẻ
        response = await self.llm_service.llm_task(
            inputs={"query": query, "CARD_HIERARCHY": CARD_HIERARCHY_NEW},
            prompt_template=CARD_KEYWORD_EXTRACT_PROMPT_V2
        )

        # Parse kết quả XML
        xml_result = await self.xml_parser.parse(text=response)
        extracted_keyword = xml_result.get('keyword', '').strip()
        node_key = xml_result.get('node', '').strip()
        description = xml_result.get('description', '').strip()

        LOGGER.info(f"Extracted keyword: '{extracted_keyword}', node: '{node_key}', description: '{description}'")

        # FIX ĐỌN GIẢN: Nếu là list hoặc multiple nodes → unknown
        if isinstance(node_key, list) or ',' in str(node_key):
            LOGGER.info(f"Multiple nodes detected: {node_key}, treating as unknown")
            return {"unknown": True}

        # Xử lý trường hợp từ khóa đặc biệt
        if node_key in self.special_card_keywords:
            LOGGER.info(f"Detected specific card keyword: {node_key}")
            return {"special_keyword": True, "keyword": node_key}

        # Xử lý trường hợp unknown
        if node_key == "unknown":
            LOGGER.info("Node key is unknown, switching to normal RAG flow")
            return {"unknown": True}

        # Tìm node trong cây
        node_info = self._find_node_in_tree(node_key)

        # Nếu không tìm thấy thông tin node
        if not node_info:
            LOGGER.info(f"No node found for node_key={node_key}")
            return {}

        # Xử lý node dựa vào thuộc tính is_leaf
        if node_info.get("is_leaf", False):
            # Lấy card_ids từ node
            card_ids = node_info["value"]
            if not isinstance(card_ids, list):
                card_ids = [card_ids]

            LOGGER.info(f"Found card IDs: {card_ids}")

            # Tạo aggregated documents cho mỗi card_id
            all_docs = []
            for card_id in card_ids:
                card_docs = await self._doc_service._fetch_and_rank(
                    query=query,
                    collection=self.collection_card,
                    retrieval_top_k=15,
                    rerank_top_k=7,
                    partition_names=[str(card_id)]
                )
                if card_docs:
                    # Tạo aggregated document cho card_id này
                    aggregated_doc = self._create_aggregated_document(card_id, card_docs)
                    all_docs.append(aggregated_doc)

            # Tạo classification document từ description
            if description:
                classification_doc = {
                    "content": description,
                    "id": "card_classification_info",
                    "score": 1.0
                }
                all_docs.insert(0, classification_doc)
                LOGGER.info(f"Added classification: {description}")

            return {
                "is_leaf": True,
                "value": all_docs,
                "node_name": self._get_node_display_name(node_key)
            }
        else:
            # Nếu không phải node lá và không có id
            LOGGER.info(f"Non-leaf node found with children: {node_info.get('children', [])}")
            return {
                "is_leaf": False,
                "children": node_info.get("children", [])
            }

    def _create_aggregated_document(self, card_id: str, card_docs: List[Dict]) -> Dict:
        """Gộp tất cả documents của một card_id thành một tài liệu hoàn chỉnh."""
        if not card_docs:
            return {}

        # Sắp xếp theo score
        sorted_docs = sorted(card_docs, key=lambda x: x.get('score', 0), reverse=True)

        # Gộp content
        content_sections = []
        max_score = 0

        for doc in sorted_docs:
            content = doc.get('content', '').strip()
            if content:
                content_sections.append(content)

            doc_score = doc.get('score', 0)
            if doc_score > max_score:
                max_score = doc_score

        # Tạo aggregated content
        aggregated_content = "\n\n--- --- ---\n\n".join(content_sections)

        return {
            "id": f"card_{card_id}_aggregated",
            "content": aggregated_content,
            "score": max_score,
            "card_id": card_id,
            "source_count": len(sorted_docs)
        }

    def _find_node_in_tree(self, target_key: str) -> Dict:
        """Tìm kiếm node trong cây phân cấp thẻ."""
        # Tìm node trong cây sử dụng jsonpath
        jsonpath_expr = parse(f'$..{target_key}')
        matches = jsonpath_expr.find(CARD_HIERARCHY_NEW)

        # Nếu không tìm thấy
        if not matches:
            return None

        # Lấy node từ kết quả đầu tiên
        node = matches[0].value

        # Kiểm tra node có phải là node lá không (có id)
        if "id" in node:
            return {"is_leaf": True, "value": node["id"]}

        # Kiểm tra node có special_ids không
        if "special_ids" in node:
            return {"is_leaf": True, "value": node["special_ids"]}

        # Kiểm tra node có card_ids không
        if "card_ids" in node:
            return {"is_leaf": True, "value": node["card_ids"]}

        # Kiểm tra node có children không
        if "children" in node:
            children = [child_node["name"] for _, child_node in node["children"].items()]
            return {"is_leaf": False, "children": children}

        # Nếu không có gì cả
        return {"is_leaf": False, "children": []}

    def _get_node_display_name(self, node_key: str) -> str:
        """Lấy tên hiển thị của node từ key."""
        try:
            jsonpath_expr = parse(f'$..{node_key}')
            matches = jsonpath_expr.find(CARD_HIERARCHY_NEW)

            if matches:
                node = matches[0].value
                if isinstance(node, dict) and "name" in node:
                    return node["name"]
        except Exception:
            pass

        return node_key.replace("_", " ").title()


async def main():
    # Khởi tạo LLMService
    llm_service = LLMService("da498399-56c2-479f-80c6-b79e605dcd66")

    # Khởi tạo CardService
    card_service = CardService("da498399-56c2-479f-80c6-b79e605dcd66", llm_service)

    print("🔍 CARD SERVICE DEBUG MODE - Kiểm tra nội dung từ database")
    print("=" * 80)
    print("Nhập 'thoát' hoặc 'exit' để kết thúc chương trình.")
    print("Nhập 'debug' để xem thông tin debug chi tiết")

    debug_mode = False

    while True:
        # Nhận input từ người dùng
        user_input = input("\n💬 Nhập câu hỏi của bạn: ")

        # Kiểm tra điều kiện thoát
        if user_input.lower() in ['thoát', 'exit', 'quit']:
            print("👋 Cảm ơn bạn đã sử dụng dịch vụ. Tạm biệt!")
            break

        # Toggle debug mode
        if user_input.lower() == 'debug':
            debug_mode = not debug_mode
            print(f"🔧 Debug mode: {'ON' if debug_mode else 'OFF'}")
            continue

        try:
            print(f"\n🔄 Đang xử lý: '{user_input}'...")

            # === BƯỚC 1: PHÂN TÍCH LLM ===
            print("\n" + "=" * 60)
            print("BƯỚC 1: PHÂN TÍCH LLM")
            print("=" * 60)

            response = await card_service.llm_service.llm_task(
                inputs={"query": user_input, "CARD_HIERARCHY": CARD_HIERARCHY_NEW},
                prompt_template=CARD_KEYWORD_EXTRACT_PROMPT_V2
            )

            print(f"🤖 Raw LLM Response:\n{response}")

            # Parse XML
            xml_result = await card_service.xml_parser.parse(text=response)
            extracted_keyword = xml_result.get('keyword', '').strip()
            node_key = xml_result.get('node', '').strip()
            description = xml_result.get('description', '').strip()

            print(f"\nParsed Results:")
            print(f"   Keyword: '{extracted_keyword}'")
            print(f"   Node: '{node_key}'")
            print(f"   Description: '{description}'")

            # === BƯỚC 2: TÌM NODE TRONG CÂY ===
            print("\n" + "=" * 60)
            print("🌳 BƯỚC 2: TÌM NODE TRONG CÂY")
            print("=" * 60)

            node_info = card_service._find_node_in_tree(node_key)
            print(f"🔍 Node info found: {node_info}")

            if not node_info or node_key == "unknown":
                print("Không tìm thấy node hoặc node = unknown")
                continue

            # === BƯỚC 3: XỬ LÝ LEAF NODE ===
            if node_info.get("is_leaf", False):
                print("\n" + "=" * 60)
                print("🍃 BƯỚC 3: XỬ LÝ LEAF NODE")
                print("=" * 60)

                card_ids = node_info["value"]
                if not isinstance(card_ids, list):
                    card_ids = [card_ids]

                print(f"Card IDs to search: {card_ids}")

                # Lấy documents cho từng card_id
                all_docs = []
                for card_id in card_ids:
                    print(f"\n🔎 Searching for card_id: {card_id}")
                    print(f"   Collection: {card_service.collection_card}")
                    print(f"   Partition: [{card_id}]")

                    try:
                        card_docs = await card_service._doc_service._fetch_and_rank(
                            query=user_input,
                            collection=card_service.collection_card,
                            retrieval_top_k=15,
                            rerank_top_k=7,
                            partition_names=[str(card_id)]
                        )

                        print(f"   Found {len(card_docs)} documents")

                        if debug_mode and card_docs:
                            print(f"\n   📝 RAW DOCUMENTS FOR CARD_ID {card_id}:")
                            for idx, doc in enumerate(card_docs, 1):
                                print(f"      Document {idx}:")
                                print(f"         ID: {doc.get('id', 'N/A')}")
                                print(f"         Score: {doc.get('score', 'N/A')}")
                                print(f"         Content Length: {len(doc.get('content', ''))}")
                                if debug_mode:
                                    content = doc.get('content', '')
                                    # Hiển thị 300 ký tự đầu
                                    preview = content[:300] + "..." if len(content) > 300 else content
                                    print(f"         Content Preview: {preview}")
                                print(f"         Full Content:\n{doc.get('content', '')}")
                                print("         " + "-" * 50)

                        if card_docs:
                            # Tạo aggregated document
                            aggregated_doc = card_service._create_aggregated_document(card_id, card_docs)
                            all_docs.append(aggregated_doc)

                            print(f"   Created aggregated document:")
                            print(f"      ID: {aggregated_doc.get('id', 'N/A')}")
                            print(f"      Score: {aggregated_doc.get('score', 'N/A')}")
                            print(f"      Source Count: {aggregated_doc.get('source_count', 'N/A')}")
                            print(f"      Content Length: {len(aggregated_doc.get('content', ''))}")

                            if debug_mode:
                                print(f"      AGGREGATED CONTENT:")
                                print(f"{aggregated_doc.get('content', '')}")
                                print("      " + "=" * 50)

                    except Exception as e:
                        print(f"   Error searching card_id {card_id}: {str(e)}")
                        import traceback
                        traceback.print_exc()

                # Thêm classification document nếu có
                if description:
                    classification_doc = {
                        "content": description,
                        "id": "card_classification_info",
                        "score": 1.0
                    }
                    all_docs.insert(0, classification_doc)
                    print(f"\nAdded classification document: {description}")

                # === HIỂN THỊ KẾT QUẢ CUỐI CÙNG ===
                print("\n" + "=" * 60)
                print("KẾT QUẢ CUỐI CÙNG")
                print("=" * 60)

                print(f"Total Documents: {len(all_docs)}")

                for i, doc in enumerate(all_docs, 1):
                    print(f"\nDOCUMENT {i}:")
                    print(f"   ID: {doc.get('id', 'N/A')}")
                    print(f"   Score: {doc.get('score', 'N/A')}")
                    print(f"   Card ID: {doc.get('card_id', 'N/A')}")
                    print(f"   Source Count: {doc.get('source_count', 'N/A')}")
                    print(f"   Content Length: {len(doc.get('content', ''))}")

                    content = doc.get('content', '')
                    if len(content) > 500:
                        print(f"   Content Preview (first 500 chars): {content[:500]}...")
                    else:
                        print(f"   Full Content: {content}")
                    print("   " + "-" * 50)

            else:
                print(f"\n📁 Non-leaf node with children: {node_info.get('children', [])}")

        except Exception as e:
            print(f"\nLỖI NGHIÊM TRỌNG: {str(e)}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 80)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())