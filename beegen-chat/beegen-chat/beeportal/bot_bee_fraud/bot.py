# from typing import Dict, List
# from beeapp.functions import annotate_query, format_filter_documents, get_intent_retriever, init_query
# from beeflow.nodes import PromptNode, CustomNode, START, END, ParserNode, LLMNode, BasicChainNode
# from beeflow.nodes.flow.branch_node import BranchNode
# from beeflow.nodes.graph.graph_node import GraphNode
# from beeflow.nodes.primitives.transform.code_node import CodeNode
# from beeflow.nodes.templates.basic_chain_node import BasicChainNode
# from beeflow.nodes.templates.retriever_node import RetrieverNode
# from beeflow.workflow import WorkflowEngine
# from beegen.loggings.loggers import LOGGER
# from beegen.prompts.prompt_manager import PromptManager
# from beegen.registry.model_registry import ModelRegistry
# from beegen.utils.common import fake_chunk_from, transform_bot_id
# from beeportal.bot_bee_fraud.core.database import Neo4jDB
# from beeportal.bot_bee_fraud.services.search_service import KeywordSearchService
# from beeportal.bot_bee_fraud.utils.data_preprocessing import clean_transaction_detail

# PROMPTS = PromptManager("beegen")

# class BotBeeFraud:
#     def __init__(self, bot_id: str):
#         self.bot_id = bot_id
#         mongo_engine = ModelRegistry.self().sync_mongo("aicenter-chatbot")
#         result = mongo_engine._find_one(collection_name="botinfo", query={"_id": self.bot_id})
#         self.name = result.get('data', {'name': {}}).get('name', None)
#         self.config = result.get('data', {'metadata': {}}).get('metadata', {})

#         self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")

#         self._build_flow()

#     def _build_flow(self):
#         with (WorkflowEngine(
#                 name="fraud_check_wf_v1",
#                 description="Workflow kiểm tra giao dịch lừa đảo",
#         ) as fraud_check_wf):

#             info_extract = BasicChainNode(
#                 name="info_extract",
#                 description="Pipeline for extract account_id, start_date, end_date from input",
#                 model="Qwen3-30B-A3B",
#                 user_prompt=PROMPTS["BEEFRAUD:FRAUD_CHECK_PROMPT"],
#                 inputs={"query": "fraud_check_wf_v1"},
#                 output_schema=["fraud_check: bool", "account_id: str", "start_date: str", "end_date: str"],
#                 parser="json",
#                 enable_thinking=False,
#                 stream=True
#             )

#             def extract_and_check_transactions(state) -> None:
#                 """
#                 Extracts account details from input and queries Neo4jDB for fraud transactions.
#                 """
#                 input_data = state["info_extract", "fraud_check"]
#                 suffix = "-MBB"

#                 if input_data:
#                     account_id = state["info_extract", "account_id"] if state["info_extract", "account_id"].endswith(suffix) \
#                         else state["info_extract", "account_id"] + suffix
#                     start_date = state["info_extract", "start_date"]
#                     end_date = state["info_extract", "end_date"]

#                     # Connect to Neo4jDB and retrieve the transactions
#                     with Neo4jDB() as db:
#                         transactions = db.get_transaction_to_account(
#                             to_account_number=account_id,
#                             from_date=start_date,
#                             to_date=end_date
#                         )
#                     if transactions:
#                         transactions = [
#                             (
#                                 txn["trans_date"],
#                                 txn["amount"],
#                                 clean_transaction_detail(txn["transaction_detail"]),
#                                 txn["transaction_id"]
#                             )
#                             for txn in transactions
#                             if clean_transaction_detail(txn["transaction_detail"])
#                                and clean_transaction_detail(txn["transaction_detail"]).strip()
#                         ]

#                     state["extract_and_query", "transactions"] = transactions

#             extract_and_query = CustomNode(
#                 name="extract_and_query",
#                 core=extract_and_check_transactions,
#                 output_schema=["transactions: List[Dict[str, Any]]"]
#             )

#             check_transactions = BranchNode(
#                 name="check_transactions",
#                 cases={
#                     "transactions": "keyword_matching"
#                 },
#                 default_target="instant_reply",
#                 inputs={
#                     "transactions": "extract_and_query"
#                 }
#             )

#             instant_reply = LLMNode(
#                 name="instant_reply",
#                 model="Qwen3-30B-A3B",
#                 inputs={
#                     "response": "Account ID không tồn tại trong cơ sở dữ liệu hoặc không phát sinh giao dịch trong khoảng thời gian cung cấp"
#                 },
#                 instant_response=True
#             )

#             def keyword_match_transactions(state) -> None:
#                 """Process a larger number of transactions in batches using keyword regex matching"""

#                 keyword_service = KeywordSearchService()
#                 trans_list = state["extract_and_query", "transactions"]
#                 keyword_matches = keyword_service.search_keyword_using_regex_v1(trans_list)
#                 keyword_count = len(keyword_matches)
#                 list_keyword = keyword_matches
#                 state["keyword_matching", "keyword_count"] = keyword_count
#                 state["keyword_matching", "list_keyword"] = dict(list_keyword)

#             keyword_matching = CustomNode(
#                 name="keyword_matching",
#                 core=keyword_match_transactions,
#                 output_schema=["keyword_count: int", "list_keyword: Dict[str, Any]"]
#             )

#             keyword_match_response = BasicChainNode(
#                 name="keyword_match_response",
#                 description="Pipeline for generate response based on keyword matching",
#                 model="Qwen3-30B-A3B",
#                 user_prompt=PROMPTS["BEEFRAUD:REPLY_PROMPT"],
#                 inputs={"query": "fraud_check_wf_v1", "keyword_count": "keyword_matching",
#                         "list_keyword": "keyword_matching"},
#                 enable_thinking=False,
#                 stream=True
#             )

#             check_for_keyword_match = BranchNode(
#                 name="check_for_keyword_match",
#                 cases={
#                     "keyword_count == 0": "llm_suggest_response"
#                 },
#                 default_target="keyword_match_response",
#                 inputs={
#                     "keyword_count": "keyword_matching",
#                 }
#             )

#             llm_suggest_response = BasicChainNode(
#                 name="llm_suggest_response",
#                 description="Pipeline for generate response using llm on transaction list",
#                 model="Qwen3-30B-A3B",
#                 user_prompt=PROMPTS["BEEFRAUD:EXTRACTION_PROMPT"],
#                 inputs={"transactions": "extract_and_query"},
#                 enable_thinking=False,
#                 stream=True
#             )

#             # Connect the workflow
#             START >> info_extract >> extract_and_query >> check_transactions >>[keyword_matching, instant_reply]
#             keyword_matching >> check_for_keyword_match >> [keyword_match_response, llm_suggest_response]
#             instant_reply >> END
#             keyword_match_response >> END
#             llm_suggest_response >> END
#             # START >> info_extract >> extract_and_query >> keyword_matching >> check_for_keyword_match >> keyword_match_response >> llm_suggest_response >> END

#         fraud_check_wf.compile()

#         self.workflow = fraud_check_wf

#     async def run(
#             self,
#             messages: List[Dict],
#             **kwargs
#     ):
#         """Main pipeline with updated logic flow."""
#         try:
#             async for chunk in self.workflow.run(
#                     inputs={
#                         "query": messages
#                     }
#             ):
#                 yield chunk
#         except Exception as e:
#             import traceback
#             LOGGER.error(traceback.format_exc(e))
#             default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
#             yield fake_chunk_from(
#                 content=default_answers,
#                 model="error"
#             )


# async def main():
#     bot = BotBeeFraud(bot_id="51cd8b7a-8402-4495-a623-febe262f3f6f")

#     async for chunk in bot.run(
#             messages=[{"role": "user",
#                    "content": "Tôi muốn kiểm tra các giao dịch có thể lừa đảo với tài khoản 42bfbd07f12d61a3bd0167cb2ab54a560ecd3926ef7c1ca39162515888c0b8fa-MBB từ ngày đầu năm 2024 đến tháng 6 năm 2025"}]
#     ):
#         print(chunk)

#     await asyncio.sleep(4)


# if __name__ == "__main__":
#     import asyncio

#     asyncio.run(main())

#     # Uncomment below to debug on Pycharm
#     # loop = asyncio.new_event_loop()
#     # asyncio.set_event_loop(loop)
#     # loop.run_until_complete(main())
#     # loop.close()