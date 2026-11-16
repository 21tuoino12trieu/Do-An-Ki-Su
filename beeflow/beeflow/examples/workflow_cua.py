# At the top of your main file, before any other imports
from pprint import pprint
import threading
import uuid

from pymongo import ReturnDocument
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.data.s3_node import S3Node
from beeflow.nodes.primitives.transform.doc_io_node import DocumentIONode
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.storage.s3_config import S3Operation
from examples.utils.doc_io import converter
from examples.utils.llm import schema_detector
from examples.utils.loop import document_preprocessed
from examples.utils.mongo import check_content, load_content, save_content, save_metadata, save_schema

from examples.utils.nlp import encode_to_base64

_scipy_lock = threading.Lock()

def fix_scipy_imports():
    with _scipy_lock:
        try:
            import scipy
            import scipy.sparse
            import scipy.sparse._lil
            scipy.sparse.lil_matrix((1, 1))  # Force initialization
            print("✅ Scipy pre-imported")
        except:
            pass

# Call immediately
fix_scipy_imports()

from typing import Dict, List
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.workflow import WorkflowEngine
from beegen.loggings.loggers import LOGGER
from beegen.prompts.prompt_manager import PromptManager
from beegen.utils.common import fake_chunk_from


PROMPTS = PromptManager("cua-extractor")

SCHEMA_DETECTION_JSON_FORMART='''
        {
        "fields": {
            "field_name_1": "Mô tả chi tiết + ví dụ" | null,
            "field_name_2": "Mô tả chi tiết + ví dụ" | null,
            "nested_field_1": {
                "description": "Mô tả tổng quan của nhóm nested_field_1 + ví dụ" | null,
                "child_field_1": "Mô tả chi tiết + ví dụ" | null,
                "child_field_2": "..." | null
            }
        },
        "metadata": {
            "document_type": "Mô tả chi tiết + ví dụ" | null,
            "issue_date": "Mô tả chi tiết + ví dụ" | null,
            "issuer": "Mô tả chi tiết + ví dụ" | null,
            "document_id": "Mô tả chi tiết + ví dụ" | null,
            các metadata khác | null
        },
        "tables": [
            {
            "table_id": "table_1" | null,
            "description": "Mô tả nội dung bảng nếu có" | null,
            "headers": ["header_1", "header_2", "..."],
            "value_rows": [
                ["giá trị 1", "giá trị 2", "..."],
                ["...", "...", "..."]
            ]
            },
            {
            "table_id": "table_2" | null,
            "description": "...",
            "headers": ["..."],
            "sample_rows": [["...", "..."]]
            }
        ]
        }
    '''

class BeeCUA:
    def __init__(self, bot_id: str):
        # self.bot_id = bot_id
        # mongo_engine = ModelRegistry.self().sync_mongo("aicenter-chatbot")
        # result = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
        # self.name = result.get('data', {'name': {}}).get('name', None)
        # self.config = result.get('data', {'metadata': {}}).get('metadata', {})
        
        # self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")
        
        self._build_flow()
    
    def _build_flow(self):
        with WorkflowEngine(
            name="cua_extractor_workflow", 
            description="Đây là luồng schema detection của dự án CUA",
            inputs=INPUT,
            langfuse="cua-extractor"
        ) as cua_extractor_workflow:
            
            code_check_content = CodeNode(
                name="code_check_content",
                code_fn=check_content,
                inputs={"document_id": INPUT},
                # return_keys={"filter: dict"}
                # output: {"filter": Dict[str, Any]}
            )

            mongo_check_content = MongoNode(
                name="mongo_check_content",
                resource_key="mongo:aicenter-cua",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "cua_document",
                    "query": {code_check_content: "filter"},
                    "projection": {"_id": 1},
                },
                # output: {"data": {...} | None}
            )

            branch_content_exists = BranchNode(
                name="branch_content_exists",
                cases={
                    "data is not None": "graph_schema_detection",
                    "data is None": "graph_create_content",
                },
                inputs={"data": mongo_check_content},
            )

            with GraphNode(
                name="graph_schema_detection",
                description="Đây là luồng xử lý khi file đã tồn tại",
                inputs=INPUT,
                outputs=OUTPUT
            ) as graph_schema_detection:

                code_load_content = CodeNode(
                    name="code_load_content",
                    code_fn=load_content,
                    inputs={"document_id": INPUT},
                    # output: {"filter": Dict[str, Any]}
                )

                mongo_load_content = MongoNode(
                    name="mongo_load_content",
                    resource_key="mongo:aicenter-cua",
                    operation=MongoOperation.FIND_ONE,
                    inputs={
                        "collection_name": "cua_document",
                        "query": {code_load_content: "filter"},
                        "projection": {"pages.content": 1, "_id": 0},
                    },
                    # outputs={"data": {"pages": [{"content": "..."}]}} hoặc None
                )

                code_schema_detector = CodeNode(
                    name="code_schema_detector",
                    code_fn=schema_detector,
                    inputs={
                        "data": mongo_load_content,
                    },
                    # output: {"document_content": List[str|Any]}
                )

                llm_schema_detector = BasicChainNode(
                    name="llm_schema_detector",
                    resource_key="qwen-instruct-cua",
                    system_prompt=PROMPTS["CUA:SCHEMA_DETECTION_SYSTEM_PROMPT"],
                    user_prompt=PROMPTS["CUA:SCHEMA_DETECTION_USER_PROMPT"],
                    parser="json",
                    inputs={
                        "document_content": {code_schema_detector: "content"},
                        "json_format": SCHEMA_DETECTION_JSON_FORMART,
                    },
                    stream=False,
                    outputs={"content": OUTPUT}
                )

                code_save_schema = CodeNode(
                    name="code_save_schema",
                    code_fn=save_schema,
                    inputs={
                        "collection_name": "cua_document",
                        "schema": {llm_schema_detector: "content"},
                        "document_id": INPUT,
                    },
                    # output: {"filter": Dict[str, Any], "update": Dict[str, Any]}
                )

                mongo_save_schema = MongoNode(
                    name="mongo_save_schema",
                    resource_key="mongo:aicenter-cua",
                    operation=MongoOperation.FIND_ONE_AND_UPDATE,
                    inputs={
                        "collection_name": "cua_document",
                        "filter": {code_save_schema: "filter"},
                        "update": {code_save_schema: "update"},
                        "return_document": ReturnDocument.AFTER,
                        "upsert": True,
                    },
                )
                START >> code_load_content >> mongo_load_content >> code_schema_detector >> llm_schema_detector >> code_save_schema >> mongo_save_schema >> END 

            with GraphNode(
                name="graph_create_content",
                description="Đây là luồng xử lý khi file chưa tồn tại: get -> convert -> OCR ",
                inputs=INPUT,
                outputs=OUTPUT
            ) as graph_create_content:

                s3_get_document = S3Node(
                    name="s3_get_document",
                    resource_key="ai-rnd-knowledge",
                    operation=S3Operation.READ,
                    inputs={"key": {INPUT: "document_key"}, "bucket": "ai-knowledge-working"},
                    # output: có thể gồm "document_path" và/hoặc "document_bytes"
                )

                code_pdf2image_converter = CodeNode(
                    name="code_pdf2image_converter",
                    code_fn=converter,
                    inputs={
                        "document_path": s3_get_document,
                        "document_bytes": s3_get_document,
                    },
                    # output: {"document": Dict[str, Any]}
                )

                pdf2image_converter = DocumentIONode(
                    name="pdf2image_converter",
                    document_type="pdf",
                    output_format="base64",
                    inputs={
                        "path": code_pdf2image_converter,
                        "data": code_pdf2image_converter
                    },
                    # output: {"pages": [...], "document_type": "...", "document_name": "...", "total_pages": int, ...}
                )

                code_save_metadata = CodeNode(
                    name="code_save_metadata",
                    code_fn=save_metadata,
                    inputs={
                        "document_id": INPUT,
                        "document_path": pdf2image_converter,
                        "document_type": pdf2image_converter,
                        "document_name": pdf2image_converter,
                        "total_pages": pdf2image_converter,
                    },
                    # output: {"filter": Dict[str, Any], "update": Dict[str, Any]}
                )

                mongo_save_metadata = MongoNode(
                    name="mongo_save_metadata",
                    resource_key="mongo:aicenter-cua",
                    operation=MongoOperation.FIND_ONE_AND_UPDATE,
                    inputs={
                        "collection_name": "cua_document",
                        "filter": {code_save_metadata: "filter"},
                        "update": {code_save_metadata: "update"},
                        "return_document": ReturnDocument.AFTER,
                        "upsert": True,
                    },
                )

                code_document_preprocessed = CodeNode(
                    name="code_document_preprocessed",
                    code_fn=document_preprocessed,
                    inputs={"document_id": INPUT, "pages": pdf2image_converter},
                    # output: {"batch_data": List[Dict[str, Any]]}
                )

                with ForLoopNode(
                    name="for_each_document_preprocessed",
                    description="Loop với từng trang tài liệu sau khi xử lý",
                    inputs={"batch_data": code_document_preprocessed}
                ) as for_each_document_preprocessed:
                    s3_save_document_preprocessed=S3Node(
                        name="s3_save_document_preprocessed",
                        resource_key="ai-rnd-knowledge",
                        operation=S3Operation.WRITE,
                        inputs=INPUT            
                    )

                    vlm_ocr_processor = BasicChainNode(
                        name="vlm_ocr_processor",
                        resource_key="qwen-vl",
                        messages_template=[
                            {
                                "role": "system",
                                "content":  "{ocr_system_prompt}",
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,{base64_data}"}},
                                    {"type": "text", "text":  "{ocr_user_prompt}"},
                                ]
                            }    
                        ],
                        inputs={"base64_data": {INPUT: "content_base64"}, "ocr_system_prompt" : PROMPTS["CUA:OCR_SYSTEM_PROMPT"], "ocr_user_prompt" : PROMPTS["CUA:OCR_USER_PROMPT"]},
                        outputs={"content": OUTPUT["ocr_content"]},
                        stream=False
                    )

                    
                    code_save_content = CodeNode(
                        name="code_save_content",
                        code_fn=save_content,
                        inputs={
                            "page_content": {vlm_ocr_processor: "content"},
                            "page_number": INPUT,
                            "document_id": INPUT,
                        },
                        # output: {"filter": Dict[str, Any], "update": Dict[str, Any]}
                    )

                    mongo_save_content = MongoNode(
                        name="mongo_save_content",
                        resource_key="mongo:aicenter-cua",
                        operation=MongoOperation.FIND_ONE_AND_UPDATE,
                        inputs={
                            "collection_name": "cua_document",
                            "filter": {code_save_content: "filter"},
                            "update": {code_save_content: "update"},
                            "return_document": ReturnDocument.AFTER,
                            "upsert": True,
                        },
                    )
                    START >> [s3_save_document_preprocessed, vlm_ocr_processor] >> code_save_content  >> mongo_save_content >> END

                START >> s3_get_document >> code_pdf2image_converter >> pdf2image_converter
                pdf2image_converter >> [code_save_metadata, code_document_preprocessed]
                code_save_metadata >> mongo_save_metadata
                code_document_preprocessed >> for_each_document_preprocessed >> END    

            START >> code_check_content >> mongo_check_content >> branch_content_exists >> [graph_schema_detection, graph_create_content]
            # graph_create_content >> graph_schema_detection >> END
            graph_schema_detection >> END

            # START >> _mongo_check_content >> mongo_check_content >> check_content_exists >> graph_schema_detection >> END

            
        cua_extractor_workflow.compile()
                
        self.workflow = cua_extractor_workflow

        
    async def run(
        self,
        s3_key: str,
        role: str = "L1",
        topic: str = "default"
    ):
        """Main pipeline with updated logic flow."""
        results = await self.workflow.run(
            inputs={
                "document_key": s3_key,
                "document_id": encode_to_base64(s3_key)
            },
            request_id=str(uuid.uuid4())
        )
        pprint(results)

            
async def main():
    
    bot = BeeCUA(bot_id="71eff3f6-1fc4-48c4-8ca8-df836d26d4c5")
    await bot.run(s3_key="rnd/thaivd/work/cua/origin/sample2.pdf")

    await asyncio.sleep(4)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())