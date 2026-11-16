import re
from datetime import datetime

from beegenerate.configs.db.mongo_config import MongoConfig
from beegenerate.configs import LLMConfig
from typing import Dict, List, Optional
import json
from beegenerate.loggings import LOGGER
from .mongodb import MongoStorage


class DocumentStore(MongoStorage):

    def __init__(
            self,
            config: Optional[MongoConfig] = None
    ) -> None:
        super().__init__(config)

    def find_document_chunks(
            self,
            chunk_ids: List[str],
            allowed_roles: List[str],
            collection_name: str = "chunk_data"
    ) -> List[Dict]:
        r"""Retrieves document chunks and their metadata from MongoDB based on Milvus chunk IDs.

        Args:
            chunk_ids: List of chunk identifiers from Milvus.
            allowed_roles: A list of roles permitted to access the documents.
            collection_name: Name of the MongoDB collection containing chunk data.

        Returns:
            A dictionary mapping chunk IDs to their corresponding content and metadata.
        """

        def replace_question(text, new_question):
            # Tìm vị trí bắt đầu của "Câu hỏi:" và "Câu trả lời:"
            question_start = text.find("Câu hỏi:")
            answer_start = text.find("Câu trả lời:")

            if question_start != -1 and answer_start != -1:
                # Tạo văn bản mới với câu hỏi đã được thay thế
                new_text = text[:question_start + len("Câu hỏi: ")] + new_question + text[answer_start - 1:]
                return new_text
            else:
                # Nếu không tìm thấy cả "Câu hỏi:" và "Câu trả lời:", sử dụng regex ban đầu
                return re.sub(r'(Câu hỏi:\s*).*?(?=\n)', r'\1' + new_question, text, flags=re.DOTALL)

        def build_pipeline(chunks, roles, collection):
            return [
                {
                    "$match": {
                        "chunk_id": {"$in": chunks}
                    }
                },
                {
                    "$lookup": {
                        "from": collection,
                        "localField": "doc_id",
                        "foreignField": "_id",
                        "as": "docs"
                    }
                },
                {
                    "$unwind": "$docs"
                },
                {
                    "$match": {
                        "docs.role_ids": {"$in": roles}
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "chunk_id": 1,
                        "doc_id": 1,
                        "raw_text": 1,
                        "llm_text": 1,
                        "questions": "$docs.questions",
                        "valid_from": "$docs.valid_from",
                        "valid_to": "$docs.valid_to",
                    }
                }
            ]

        # 1. find the chunks by input ids list
        document_chunks = self.aggregate(
            collection_name=collection_name,
            pipeline=build_pipeline(chunk_ids, allowed_roles, "documents")
        )

        dialogue_chunks = self.aggregate(
            collection_name=collection_name,
            pipeline=build_pipeline(chunk_ids, allowed_roles, "dialogue")
        )

        chunk_map = {chunk['chunk_id']: chunk for chunk in document_chunks + dialogue_chunks}

        # 2. Mongo result did not keep the ids ordering, reorder them
        # Create a mapping of chunk_id to document
        # Append documents in original order
        result = []
        for _id in chunk_ids:
            if _id in chunk_map:
                chunk = chunk_map[_id]
                if "questions" in chunk:
                    for question in chunk['questions']:
                        content = chunk['llm_text']
                        content = replace_question(content, question['text'])
                        
                        result.append({
                            'id': chunk['chunk_id'],
                            'doc': chunk['doc_id'],
                            'content': content,
                            "valid_from": None,
                            "valid_to": None
                        })
                else:
                    result.append({
                        'id': chunk['chunk_id'],
                        'doc': chunk['doc_id'],
                        'content': chunk['llm_text'],
                        "valid_from": chunk["valid_from"] if "valid_from" in chunk else None,
                        "valid_to": chunk["valid_to"] if "valid_to" in chunk else None,
                    })
        return result
    
    
        # Trong file document_store.py
    # THAY THẾ TOÀN BỘ HÀM NÀY

    # THÊM HÀM MỚI NÀY VÀO TRONG CLASS DocumentStore

    def find_document_chunks_v2(
            self,
            chunk_ids: List[str],
            allowed_roles: List[str],
            bot_id: str,
            collection_name: str = "chunk_data"
    ) -> List[Dict]:
        """
        [PHIÊN BẢN HOÀN CHỈNH CHO QHLD]
        Hàm này là nơi duy nhất thực hiện:
        1. Dịch Role Name sang Role ID, có lọc theo bot_id.
        2. Đảm bảo trả về 'raw_text' trong kết quả cuối cùng.
        """
        # === BƯỚC 1: DỊCH ROLE NAME SANG ROLE ID (LOGIC QUAN TRỌNG NHẤT) ===
        allowed_role_ids = []
        if allowed_roles:
            try:
                # Truy vấn collection 'roles' để tìm ID dựa trên tên và bot_id
                roles_from_db = self.find(
                    collection_name="roles",
                    query={"role_name": {"$in": allowed_roles}, "bot_id": bot_id}
                )
                if roles_from_db:
                    # Lấy ra danh sách các ID (dưới dạng string)
                    allowed_role_ids = [str(r['_id']) for r in roles_from_db]
                
                LOGGER.info(f"Translated role names {allowed_roles} for bot {bot_id} to IDs: {allowed_role_ids}")

            except Exception as e:
                LOGGER.error(f"An error occurred while translating role names: {e}")
                return [] # Dừng lại nếu có lỗi

        # Nếu có yêu cầu role nhưng không tìm thấy ID nào, trả về rỗng để tránh truy vấn sai
        if not allowed_role_ids and allowed_roles:
            LOGGER.warning(f"Could not find any matching role IDs for names {allowed_roles} and bot {bot_id}. Returning empty list.")
            return []

        # === BƯỚC 2: XÂY DỰNG PIPELINE VÀ TRUY VẤN DỮ LIỆU CHUNK ===
        def build_pipeline(chunks, roles_to_check, collection):
            # Pipeline này sẽ được sử dụng cho cả 'documents' và 'dialogue'
            pipeline = [
                {"$match": {"chunk_id": {"$in": chunks}}},
                {"$lookup": {"from": collection, "localField": "doc_id", "foreignField": "_id", "as": "docs"}},
                {"$unwind": "$docs"},
                # Sử dụng ID đã được dịch để lọc chính xác document theo role
                {"$match": {"docs.role_ids": {"$in": roles_to_check}}},
                {"$project": {
                    "_id": 0, "chunk_id": 1, "doc_id": 1, "raw_text": 1, "llm_text": 1,
                    "questions": "$docs.questions", "valid_from": "$docs.valid_from", "valid_to": "$docs.valid_to",
                }}
            ]
            return pipeline

        # Thực hiện aggregate trên cả hai collection có thể chứa document
        document_chunks = self.aggregate(
            collection_name=collection_name,
            pipeline=build_pipeline(chunk_ids, allowed_role_ids, "documents")
        )
        dialogue_chunks = self.aggregate(
            collection_name=collection_name,
            pipeline=build_pipeline(chunk_ids, allowed_role_ids, "dialogue")
        )
        
        # Gộp kết quả và tạo map để dễ tra cứu
        chunk_map = {chunk['chunk_id']: chunk for chunk in document_chunks + dialogue_chunks}

        # === BƯỚC 3: TRẢ VỀ KẾT QUẢ, ĐẢM BẢO CÓ 'raw_text' ===
        result = []
        # Duyệt qua danh sách chunk_ids ban đầu để giữ đúng thứ tự
        for _id in chunk_ids:
            if _id in chunk_map:
                chunk = chunk_map[_id]
                # Tạo dictionary kết quả với đầy đủ các trường cần thiết
                result.append({
                    'id': chunk['chunk_id'],
                    'doc': chunk.get('doc_id'),
                    'content': chunk.get('llm_text', ''), # Dành cho các flow khác có thể cần
                    'raw_text': chunk.get('raw_text', ''), # <-- TRƯỜNG QUAN TRỌNG CHO QHLD
                    "valid_from": chunk.get("valid_from"),
                    "valid_to": chunk.get("valid_to"),
                })
                
        return result


    
    def _find_docs_with_botid(
        self,
        _id : str,
        bot_id: str,
        collection_name: str = "documents"    
    ) ->List[Dict]:
        docs=self.find(
            collection_name= collection_name,
            query={
                "bot_id": bot_id,
                "_id":_id
            }
        )
        return docs
    
    def find_llm_configurations(self, model: str, type: str = "LLM") -> LLMConfig:
        config = self.find(
            collection_name="beegen_configurations",
            query={
                "type": type,
                "config.model": model
            }
        )
        if config:
            config = config[0]['config']
            
            config["completion"] = {
                "model": config.get("model"),
                "temprature": config.get("temprature", 0),
                "top_p": config.get("top_p"),
                "frequency_penalty": config.get("frequency_penalty"),
                "max_tokens": config.get("max_tokens"),
                "n": config.get("n"),
                "presence_penalty": config.get("presence_penalty")
            }
            return LLMConfig.create_config(config)
        
    
        return None


async def main():
    doc_store = DocumentStore(
        config=MongoConfig.default()
    )

    chunks = doc_store.find_document_chunks(
        # chunk_ids=[
        #     'e8c4ea03-5509-455c-a3e8-a31b270ecd7d',
        #     '24392918-224f-4d38-ad5b-7f625fc3f9ab',
        #     '9e0a6f68-e57f-41b7-bb6c-6a03b8f27cb2',
        #     '5cfcd6f2-0169-46e1-8174-eed52031bc00'
        # ]

        chunk_ids=[
          "cf083fbd-4e2d-4131-a1b3-d4eab66a270d",
          "dd118156-c52e-4892-8a8d-1453587dbcea",
          "240e5859-fa66-42fb-b785-cd0cf3b41c20",
          "becfcbf0-99ea-44a0-bac4-5f27e2ca06bd",
          "b79eb445-b8af-4726-ac2f-083666ff944d",
          "c36fa4f5-b170-46c1-804a-e60e57557207",
          "a4f50e98-61f3-45a7-b124-b80bc2a8a7d7",
          "783bec24-2d99-49f8-8e4d-e0c1fb77a66c",
          "f5abd8c3-6f7c-48ff-bfc7-3f6210447df9",
          "237bc3e8-8a56-4860-8792-f42fd43677e9"
        ],
        allowed_roles=["L1"]
    )

    for chunk in chunks:
        print(json.dumps(chunk, indent=2, ensure_ascii=False))
    
    # from beegen.llms.llm_executor import LLMExecutor
    # config = doc_store.find_llm_configurations(model="gpt-4o")
    # print(f"config: {config}")
    # llm = LLMExecutor(
    #     primary_config=config
    # )
    # async for chunk in llm.run(
    #     messages=[{'role': 'user', 'content': 'xin chào'}]
    # ):
    #     if chunk:
    #         content = chunk.choices[0].delta.content
    #         if content:
    #             print(content, end="")
    #         else:
    #             print("")
    #         if hasattr(chunk.choices[0], "message"):
    #             print('message = ', chunk.choices[0].message)
    #         yield chunk

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    
