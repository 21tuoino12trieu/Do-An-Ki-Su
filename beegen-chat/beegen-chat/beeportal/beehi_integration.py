# from beehi_QHLD.data.prompt_v2 import (
#     CHIT_CHAT_PROMPT_QHLD,
#     VERIFY_DOCUMENT_PROMPT_QHLD,
#     NON_CHIT_CHAT_PROMPT_QHLD,
#     REFUSE_PROMPT_QHLD,
#     CONTEXT_ANALYSIS_PROMPT_QHLD,
#     DETECT_QHLD_FLOW_PROMPT_QHLD,
#     REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD
# )

# from beehi_QHLD.data.source_data import (
#     BEEHI_QHLD_SHORTCUT,
#     BEEHI_QHLD_CHUYENMON,
#     BEEHI_QHLD_KICHBAN,
#     BEEHI_QHLD_PHAMVI
# )

# # Import prompts from integration (need to add these to your prompt files)
# from beehi_QHLD.data.happy_hub import (
#     SYSTEM_PROMPT_INTENT,
#     SYSTEM_PROMPT_CHIT_CHAT,
#     SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED,
#     SYSTEM_PROMPT_NON_CHIT_CHAT,
#     SYSTEM_PROMPT_REFUSE,
#     SYSTEM_PROMPT_RELEVANCE_TOPIC,
#     SYSTEM_PROMPT_QUERY_CLARITY,
#     SYSTEM_PROMPT_PARTIAL_ANSWER
# )

# from langfuse.decorators import observe, langfuse_context
# from beegenerate.loggings.loggers import lf
# from pydantic import BaseModel
# import yaml
# import re
# import time

# from beegenerate.retrievers.vector_retriever import VectorRetriever
# from beegenerate.vectordb import MilvusStorage
# from beegenerate.reranks import RerankingFactory
# from beegenerate.storage import (
#     DocumentStore,
#     BotStore
# )

# from beegenerate.llms.llm_executor import LLMExecutor

# from openai import AsyncStream
# from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

# from typing import (
#     List,
#     Dict,
#     Tuple,
#     Any,
#     TypeVar,
#     Type
# )

# from datetime import datetime
# from beegenerate.utils.common import transform_bot_id

# from beegenerate.loggings import LOGGER

# # Create a generic type that must be a subclass of BaseModel
# T = TypeVar('T', bound=BaseModel)

# class ContextAnalysis(BaseModel):
#     pham_vi: str = ""  # Phạm vi vi phạm
#     chuyen_mon: str = ""  # Chuyên môn
#     kich_ban: str = ""  # Chi tiết kịch bản


# class InputQuery(BaseModel):
#     query: str


# class VerifyResult(BaseModel):
#     output: str


# class DocumentResult(BaseModel):
#     docs: List[Dict]
#     relevance_score: float
#     fully_answered: bool = False
#     partially_answered: bool = False
#     answered_info: str = ""
#     missing_info: str = ""

# class VerifyResult(BaseModel):
#     output: str


# def parse_model(
#         input_text: str,
#         model_class: Type[T]
# ) -> T:
#     """
#     Parse input text into a specified Pydantic model.
    
#     Args:
#         input_text: Input string in XML format
#         model_class: The Pydantic model class to parse into
        
#     Returns:
#         An instance of the specified model class
        
#     Raises:
#         ValueError: If parsing or validation fails
#     """
#     import xml.etree.ElementTree as ET
    
#     try:
#         # Parse XML
#         root = ET.fromstring(input_text)
        
#         # Extract data based on model class
#         data = {}
        
#         if model_class == InputQuery:
#             query_elem = root.find('query')
#             if query_elem is not None:
#                 data['query'] = query_elem.text or ""
#             else:
#                 raise ValueError("Missing query element")
                
#         elif model_class == ContextAnalysis:
#             pham_vi_elem = root.find('pham_vi')
#             chuyen_mon_elem = root.find('chuyen_mon')
#             kich_ban_elem = root.find('kich_ban')
            
#             data['pham_vi'] = pham_vi_elem.text or "" if pham_vi_elem is not None else ""
#             data['chuyen_mon'] = chuyen_mon_elem.text or "" if chuyen_mon_elem is not None else ""
#             data['kich_ban'] = kich_ban_elem.text or "" if kich_ban_elem is not None else ""
            
#         elif model_class == VerifyResult:
#             output_elem = root.find('output')
#             if output_elem is not None:
#                 data['output'] = output_elem.text or ""
#             else:
#                 raise ValueError("Missing output element")
        
#         # Validate and create specified Pydantic model
#         return model_class(**data)
        
#     except ET.ParseError as e:
#         raise ValueError(f"Invalid XML format: {e}")
#     except Exception as e:
#         raise ValueError(f"Validation error: {e}")

# class BeeHi_QHLD:
#     """A chatbot class that handles conversations using LLM, document retrieval, and reranking.
    
#     This class implements a complete conversation flow including:
#     - Intent classification
#     - Document retrieval and reranking
#     - Handling both casual (chitchat) and information-seeking conversations
#     - Role-based access control for documents
    
#     Attributes:
#         bot_id (str): Unique identifier for the bot instance
#         bot_store (MongoStorage): Storage for bot configurations and metadata
#         bot_config (Dict[str, Any]): Bot-specific configuration settings
#         _llm (LLMExecutor): Language model execution handler
#         _retriever (VectorRetriever): Document retrieval component
#         _reranker (RerankingFactory): Document reranking component
#     """

#     def __init__(
#             self,
#             bot_config: Dict,
#             vec_store: MilvusStorage,
#             doc_store: DocumentStore,
#             bot_store: BotStore
#     ):
#         """Initialize the Bot instance with necessary components.
        
#         Args:
#             bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
#             vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
#             doc_store (DocumentStore): Document storage instance for retrieving and managing content
#             bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive
#         """
#         self.bot_config = bot_config

#         self._llm = LLMExecutor(
#             primary_config=self.bot_config['llm'],
#             config_store=bot_store
#         )

#         self._retriever = VectorRetriever(
#             config=bot_config['retrieval'],
#             vec_store=vec_store,
#             doc_store=doc_store
#         )

#         self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])

#     def _format_documents(
#             self,
#             documents: List[Dict]
#     ) -> str:
#         """Format a list of documents into a single string with separators.
        
#         Args:
#             documents: List of document dictionaries, each containing a 'content' field
            
#         Returns:
#             String containing all document contents separated by [SEP] tokens
#         """
#         documents_text = "\n[SEP]\n".join([d['content'] for d in documents])
#         return documents_text

#     def _create_attached_docs(
#             self,
#             documents: List[Dict]
#     ) -> List[Dict]:
#         """Create metadata for documents to be attached to LLM requests.
        
#         Args:
#             documents: List of document dictionaries containing 'id' and optional 'doc' fields
            
#         Returns:
#             List of dictionaries containing document metadata (id and source)
#         """
#         attached_docs = []
#         for r in documents:
#             chunk_info = {
#                 "id": r['id'],
#             }
#             if 'doc' in r:
#                 chunk_info['source'] = r['doc']

#             attached_docs.append(chunk_info)
#         return attached_docs

#     async def _stream_llm_response(
#             self,
#             messages: List[Dict]
#     ) -> str:
#         """Stream response from LLM and concatenate chunks into a single string.
        
#         Args:
#             messages: List of message dictionaries with 'role' and 'content' fields
            
#         Returns:
#             Concatenated response string from the LLM
            
#         Raises:
#             RuntimeError: If LLM streaming fails
#         """
#         try:
#             response_text = ""
#             async for chunk in self._llm.run(messages=messages):
#                 if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
#                     response_text += str(chunk.choices[0].delta.content)
#             return response_text
#         except Exception as e:
#             LOGGER.error(f"Error streaming LLM response: {e}")
#             raise RuntimeError(f"Failed to get LLM response: {str(e)}")

#     async def _generate_intent(
#             self,
#             messages: List[Dict],
#     ) -> InputQuery:
#         """Determine the intent of the user's latest message.
        
#         Uses conversation history and LLM to:
#         1. Rewrite the query for better understanding
#         2. Classify the intent as chitchat or non-chitchat
        
#         Args:
#             messages: List of conversation messages, each with 'role' and 'content'
            
#         Returns:
#             InputQuery object containing rewritten query and classified intent
            
#         Raises:
#             ValueError: If query parsing fails
#         """

#         # 1. get the user latest message and chat history 
#         query = messages[-1]['content']
#         # 2. Rewrite the conversation and classify the intent of user
#         _prompt = REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD.format(
#             definition=self.bot_config['definition'],
#             # conversation=_history,
#             shortcut = BEEHI_QHLD_SHORTCUT,
#             query=query
#         )
        
        
#         response_text = await self._stream_llm_response(
#         messages=[
#             {"role": "user", "content": _prompt}
#         ]
#         )


#         return parse_model(
#             input_text=response_text,
#             model_class=InputQuery
#         )
        
#     async def _extract_QHLD(
#             self,
#             messages: List[Dict],
#     ) -> InputQuery:

#         # 1. get the user latest message and chat history 
#         query = messages[-1]['content']
#         # 2. Rewrite the conversation and classify the intent of user
#         _prompt = DETECT_QHLD_FLOW_PROMPT_QHLD.format(
#             pham_vi=BEEHI_QHLD_PHAMVI,
#             chuyen_mon=BEEHI_QHLD_CHUYENMON,
#             kich_ban=BEEHI_QHLD_KICHBAN,
#             query=query
#         )
#         response_text = await self._stream_llm_response(
#             messages=[
#                 {"role": "user", "content": _prompt}
#             ]
#         )


#         return response_text.split("<result>")[1].split("</result>")[0]
    
#     async def _analyze_context(
#             self,
#             query: str
#     ) -> ContextAnalysis:
#         """Phân tích ngữ cảnh câu hỏi để xác định phạm vi, chuyên môn và kịch bản.
        
#         Args:
#             query: Câu hỏi đã được rewrite từ bước generate_intent
            
#         Returns:
#             ContextAnalysis object chứa thông tin phân tích ngữ cảnh
#         """
#         _prompt = CONTEXT_ANALYSIS_PROMPT_QHLD.format(
#             pham_vi=BEEHI_QHLD_PHAMVI,
#             chuyen_mon=BEEHI_QHLD_CHUYENMON,
#             kich_ban=BEEHI_QHLD_KICHBAN,
#             query=query
#         )
        
#         response_text = await self._stream_llm_response(
#             messages=[
#                 {"role": "user", "content": _prompt}
#             ]
#         )
        
#         return parse_model(
#             input_text=response_text,
#             model_class=ContextAnalysis
#         )
    
#     async def _filter_documents_by_context(
#             self,
#             documents: List[Dict],
#             context: ContextAnalysis
#     ) -> List[Dict]:
#         """Lọc documents - giữ lại nếu match ít nhất 1 trong 3 thông tin"""
#         import re
        
#         # Nếu không có context nào thì giữ tất cả
#         if not any([context.chuyen_mon, context.pham_vi, context.kich_ban]):
#             return documents
        
#         filtered_docs = []
        
#         for doc in documents:
#             content = doc['content']
#             should_keep = False
            
#             # Chỉ cần match 1 trong 3 là giữ
#             if context.chuyen_mon and f"Chuyên môn: {context.chuyen_mon}" in content:
#                 should_keep = True
#             elif context.pham_vi and f"Phạm vi vi phạm: {context.pham_vi}" in content:
#                 should_keep = True  
#             elif context.kich_ban and f"Chi tiết kịch bản: {context.kich_ban}" in content:
#                 should_keep = True
                
#             if should_keep:
#                 filtered_docs.append(doc)
        
#         return filtered_docs
    
#     async def _analyze_query_intent_clarity(self, messages: List[Dict], query: str) -> Dict:
#         """Phân tích ý định và độ rõ ràng của câu hỏi trong một lần gọi LLM"""
#         # Format lịch sử hội thoại
#         history = []
#         message_pairs = []
#         current_pair = []

#         for msg in messages[:-1][::-1]:
#             current_pair.append(msg)
#             if len(current_pair) == 2:
#                 message_pairs.append(current_pair)
#                 current_pair = []
#             if len(message_pairs) == 4:
#                 break

#         # Đảo ngược cặp và làm phẳng
#         for pair in reversed(message_pairs):
#             history.extend(pair)

#         # Thêm bất kỳ tin nhắn đơn nào còn lại
#         if current_pair:
#             history.extend(reversed(current_pair))

#         # Format lịch sử hội thoại
#         formatted_history = [
#             f"{'Người dùng' if m['role'] == 'user' else 'BOT'}: {m['content']}"
#             for m in history
#         ]

#         # Tạo prompt kết hợp để phân tích
#         system_prompt = f"""
#         # Phần 1: Phân tích ý định
#         {SYSTEM_PROMPT_INTENT.format(conversation=formatted_history, documents="", relevance_score=0)}

#         # Phần 2: Phân tích độ rõ ràng
#         {SYSTEM_PROMPT_QUERY_CLARITY}

#         # Định dạng kết quả
#         <query>câu tóm tắt ý định của tin nhắn mới</query>
#         <intent>nhóm được phân loại</intent>
#         <greeting>chatbot đã chào hỏi người dùng chưa</greeting>
#         <clarity>nhãn độ rõ ràng</clarity>
#         """

#         response_text = await self._stream_llm_response(
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": f"Tin nhắn mới: '{query}'"}
#             ]
#         )

#         # Phân tích kết quả với xử lý lỗi
#         try:
#             new_query = re.findall(r'<query>(.*?)</query>', response_text)[0]
#             intent = re.findall(r'<intent>(.*?)</intent>', response_text)[0]
#             greeting = re.findall(r'<greeting>(.*?)</greeting>', response_text)[0].lower() == 'true'
#             clarity = re.findall(r'<clarity>(.*?)</clarity>', response_text)[0]

#             result = {
#                 "query": new_query,
#                 "intent": intent,
#                 "greeting": greeting,
#                 "clarity_level": clarity,
#             }
#         except (IndexError, Exception) as e:
#             LOGGER.error(f"Lỗi khi phân tích kết quả LLM: {str(e)}")
#             # Giá trị mặc định an toàn
#             result = {
#                 "query": query,
#                 "intent": "require_document",
#                 "greeting": False,
#                 "clarity_level": "unclear",
#             }

#         return result

#     async def _get_documents_enhanced(
#             self, query: str,
#             intent_query: str,
#             role_ids: List[str],
#             topic: str) -> Dict:
#         """Truy xuất và xác minh tài liệu liên quan với đánh giá chi tiết"""
        
#         # Truy xuất tài liệu dựa trên câu tóm tắt intent
#         retrieval_records = await self._retriever.run(
#             query=intent_query or query,  # Ưu tiên câu tóm tắt intent nếu có
#             bot_id=self.bot_config['id'],
#             collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
#             allowed_roles=role_ids,
#             top_k=self.bot_config['retrieval'].top_k,
#             threshold=self.bot_config['retrieval'].threshold,
#         )

#         # Nếu không có kết quả, trả về trống
#         if not retrieval_records:
#             return {
#                 "docs": [],
#                 "relevance_score": 0.0,
#                 "fully_answered": False,
#                 "partially_answered": False,
#                 "answered_info": "",
#                 "missing_info": ""
#             }

#         # Reranking
#         reranked_results = await self._reranker.run(
#             query=query,
#             texts=[r['content'] for r in retrieval_records],
#             top_k=self.bot_config['reranking'].top_k,
#             threshold=self.bot_config['reranking'].threshold,
#         )

#         # Chuẩn bị tài liệu cho xác minh
#         documents_to_verify = []
#         for r in reranked_results:
#             record = retrieval_records[r['index']]
#             record['score'] = r['score']
#             documents_to_verify.append(record)

#         # Nếu không có tài liệu để xác minh, trả về trống
#         if not documents_to_verify:
#             return {
#                 "docs": [],
#                 "relevance_score": 0.0,
#                 "fully_answered": False,
#                 "partially_answered": False,
#                 "answered_info": "",
#                 "missing_info": ""
#             }

#         # Xác minh tất cả tài liệu cùng lúc với đánh giá chi tiết
#         verification_results = await self._verify_documents_batch_enhanced(
#             query=query,
#             intent_query=intent_query or query,
#             documents=documents_to_verify
#         )

#         # Xử lý kết quả xác minh
#         final_docs = []
#         max_score = 0
#         fully_answered = False
#         partially_answered = False
#         answered_info = ""
#         missing_info = ""

#         for idx, result in enumerate(verification_results):
#             if result["relevant"]:
#                 record = documents_to_verify[idx]
#                 record.update({
#                     "fully_answered": result["fully_answered"],
#                     "partially_answered": result["partially_answered"],
#                     "answered_info": result["answered_info"],
#                     "missing_info": result["missing_info"]
#                 })
#                 final_docs.append(record)
#                 max_score = max(max_score, record['score'])

#                 # Cập nhật trạng thái trả lời
#                 if result["fully_answered"]:
#                     fully_answered = True
#                     answered_info = result["answered_info"]
#                 elif result["partially_answered"] and not fully_answered:
#                     partially_answered = True
#                     answered_info = result["answered_info"]
#                     missing_info = result["missing_info"]

#         return {
#             "docs": final_docs,
#             "relevance_score": max_score,
#             "fully_answered": fully_answered,
#             "partially_answered": partially_answered,
#             "answered_info": answered_info,
#             "missing_info": missing_info
#         }

#     async def _verify_documents_batch_enhanced(
#             self,
#             query: str,
#             intent_query: str,
#             documents: List[Dict]) -> List[Dict]:
#         """Xác minh nhiều tài liệu trong một lần gọi LLM với đánh giá chi tiết hơn"""
#         if not documents:
#             return []

#         # Format tất cả tài liệu thành một tin nhắn
#         verification_prompt = SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED
#         formatted_docs = []
#         for idx, doc in enumerate(documents, 1):
#             formatted_docs.append(f"Document {idx}:\n{doc['content']}")

#         all_docs = "\n\n".join(formatted_docs)

#         # Tạo một tin nhắn xác minh với cả câu hỏi gốc và câu tóm tắt ý định
#         messages = [
#             {"role": "system", "content": verification_prompt},
#             {"role": "user",
#              "content": f"Câu hỏi gốc: {query}\nCâu tóm tắt ý định: {intent_query}\n\nTài liệu để đánh giá:\n{all_docs}\n\n" +
#                         "Yêu cầu: Đánh giá từng tài liệu và trả về kết quả theo định dạng "
#                         "<output>doc1:tra_loi_day_du/tra_loi_mot_phan/khong_lien_quan|doc2:tra_loi_day_du"
#                         "/tra_loi_mot_phan/khong_lien_quan|...</output>"}
#         ]

#         response_text = await self._stream_llm_response(messages)

#         # Trích xuất kết quả xác minh cơ bản
#         match_output = re.search(r'<output>(.*?)</output>', response_text)
#         match_answered = re.search(r'<answered_info>(.*?)</answered_info>', response_text)
#         match_missing = re.search(r'<missing_info>(.*?)</missing_info>', response_text)

#         if not match_output:
#             return [{"relevant": False, "answered_info": "", "missing_info": ""} for _ in documents]

#         results = match_output.group(1).strip().split('|')

#         # Tạo danh sách kết quả chi tiết
#         detailed_results = []
#         for idx, result in enumerate(results):
#             doc_result = {
#                 "relevant": False,
#                 "fully_answered": False,
#                 "partially_answered": False,
#                 "answered_info": match_answered.group(1).strip() if match_answered else "",
#                 "missing_info": match_missing.group(1).strip() if match_missing else ""
#             }

#             status = result.split(':')[1].strip()
#             if status == "tra_loi_day_du":
#                 doc_result["relevant"] = True
#                 doc_result["fully_answered"] = True
#             elif status == "tra_loi_mot_phan":
#                 doc_result["relevant"] = True
#                 doc_result["partially_answered"] = True

#             detailed_results.append(doc_result)

#         return detailed_results

#     async def _check_temporal_relevance(self, query: str, documents: List[Dict]) -> bool:
#         """Kiểm tra thông tin thời gian trong tài liệu"""
#         if not documents:
#             return False

#         # Tìm năm trong câu hỏi
#         year_match = re.findall(r'\b(202\d|203\d)\b', query)
#         if not year_match:
#             return True  # Không cần kiểm tra thời gian

#         year_in_query = year_match[0]
#         docs_text = self._format_documents(documents)

#         prompt = f"""
#         Vai trò: Chuyên gia phân tích thông tin thời gian

#         Nhiệm vụ: Kiểm tra xem tài liệu có chứa thông tin về năm {year_in_query} không.

#         Tài liệu:
#         {docs_text}

#         Yêu cầu: Chỉ trả lời "co_thong_tin" hoặc "khong_co_thong_tin"
#         """

#         response = await self._stream_llm_response([
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": f"Câu hỏi: {query}"}
#         ])

#         return "co_thong_tin" in response.lower()

#     async def _generate_clarification_prompt(self, query: str, doc_result: DocumentResult) -> str:
#         """Tạo gợi ý làm rõ bằng cách phân tích tài liệu và đề xuất chủ đề"""
#         try:
#             # Phân tích tài liệu để trích xuất chủ đề chính
#             messages = [
#                 {"role": "system", "content": SYSTEM_PROMPT_RELEVANCE_TOPIC},
#                 {"role": "user",
#                  "content": f"Câu hỏi: {query}\nTài liệu cung cấp: {self._format_documents(doc_result.docs)}"}
#             ]

#             # Lấy chủ đề từ LLM
#             response = await self._stream_llm_response(messages)
#             match = re.search(r'<topics>(.*?)</topics>', response)
#             topics = match.group(1).split('|') if match else []

#             # Format chủ đề thành câu hỏi
#             if topics:
#                 topics_text = ", ".join(topics[:-1])
#                 if len(topics) > 1:
#                     topics_text += f" hoặc {topics[-1]}"
#                 else:
#                     topics_text = topics[0]

#                 return f"Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔\nBạn muốn tìm hiểu thông tin về một trong những chủ đề sau: {topics_text} đúng không?"

#             # Fallback nếu không có chủ đề
#             return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"
#         except Exception as e:
#             LOGGER.error(f"Lỗi khi tạo gợi ý làm rõ: {str(e)}")
#             return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"

#     async def _flow_normal_integration(
#             self,
#             messages: List[Dict],
#             role_ids: List[str],
#             topic: str = "default"
# ) -> AsyncStream[ChatCompletionChunk]:
#         # print("===================")
#         # print(messages)
#         # print(role_ids)
#         # print("===================")
#         """Luồng tích hợp từ integration.py cho flow normal"""
#         query = messages[-1]['content']
        
#         # 1. Song song hóa phân tích ý định và truy xuất tài liệu
#         analysis_result = await self._analyze_query_intent_clarity(messages, query)

#         # Sử dụng câu tóm tắt ý định để truy xuất tài liệu
#         intent_query = analysis_result.get('query', query)

#         # Truy xuất tài liệu với đánh giá chi tiết
#         doc_result = await self._get_documents_enhanced(
#             query=query,
#             intent_query=intent_query,
#             role_ids=role_ids,
#             topic=topic
#         )

#         # 2. Xử lý logic phản hồi
#         if analysis_result['intent'] == "is_simple_chit_chat":
#             # Xử lý trò chuyện đơn giản
#             prompt_system = SYSTEM_PROMPT_CHIT_CHAT.format(
#                 documents="",
#                 greeting=analysis_result['greeting']
#             )
#         else:
#             # Xử lý câu hỏi cần tài liệu
#             if doc_result['docs'] and doc_result['relevance_score'] > self.bot_config.get('threshold', {}).get('doc_relevance', 0.01):
#                 # Kiểm tra mức độ trả lời được
#                 if doc_result['fully_answered'] and analysis_result['clarity_level'] == "complete":
#                     # Kiểm tra thông tin thời gian nếu cần
#                     has_time_info = True
#                     if re.findall(r'\b(202\d|203\d)\b', query):
#                         has_time_info = await self._check_temporal_relevance(query, doc_result['docs'])
#                         LOGGER.info(f"Kết quả kiểm tra thông tin thời gian: {has_time_info}")

#                     if has_time_info:
#                         # Câu hỏi rõ ràng, có tài liệu liên quan với thông tin thời gian đầy đủ
#                         prompt_system = SYSTEM_PROMPT_NON_CHIT_CHAT.format(
#                             date=datetime.now().strftime('%Y-%m-%d'),
#                             documents=self._format_documents(doc_result['docs']),
#                             greeting=analysis_result['greeting']
#                         )
#                     else:
#                         # Tài liệu không chứa thông tin thời gian cần thiết
#                         prompt_system = SYSTEM_PROMPT_REFUSE

#                 elif doc_result['partially_answered']:
#                     # Trường hợp trả lời một phần
#                     prompt_system = SYSTEM_PROMPT_PARTIAL_ANSWER.format(
#                         date=datetime.now().strftime('%Y-%m-%d'),
#                         documents=self._format_documents(doc_result['docs']),
#                         greeting=analysis_result['greeting'],
#                         answered_info=doc_result['answered_info'],
#                         missing_info=doc_result['missing_info']
#                     )

#                 elif analysis_result['clarity_level'] != "complete":
#                     # Câu hỏi không rõ ràng nhưng có tài liệu liên quan
#                     clarification = await self._generate_clarification_prompt(
#                         query,
#                         DocumentResult(docs=doc_result['docs'], relevance_score=doc_result['relevance_score'])
#                     )
#                     prompt_system = f"""
#                         Vai trò: Bạn là Bee Hi - trợ lý ảo thông minh của ngân hàng MB
#                         Đưa ra nguyên văn câu trả lời sau:
#                         {clarification}
#                     """
#                 else:
#                     # Không đủ thông tin để trả lời
#                     prompt_system = SYSTEM_PROMPT_REFUSE
#             else:
#                 # Không có tài liệu liên quan
#                 prompt_system = SYSTEM_PROMPT_REFUSE

#         # 3. Tạo và trả về câu trả lời
#         response_messages = [
#             {"role": "system", "content": prompt_system},
#             {"role": "user", "content": query}
#         ]

#         # 4. Stream câu trả lời
#         attached_docs = self._create_attached_docs(doc_result['docs'])
        
#         async for chunk in self._llm.run(
#                 messages=response_messages,
#                 docs=attached_docs
#         ):
#             yield chunk
        
#     async def _retrieval_and_rerank_enhanced(
#             self,
#             input_query: InputQuery,
#             context: ContextAnalysis,
#             role_ids: List[str] = [],
#             topic: str = "default",
#             valid_score: float = 0.5
#     ) -> List[Dict]:
#         """Enhanced retrieval với context analysis.
        
#         Thêm context vào đầu query để cải thiện tìm kiếm.
#         """
#         # Tạo enhanced query với context ở đầu
#         context_prefix = ""
#         context_parts = []
        
#         if context.chuyen_mon:
#             context_parts.append(f"Chuyên môn: {context.chuyen_mon}\n")
#         if context.pham_vi:
#             context_parts.append(f"Phạm vi vi phạm: {context.pham_vi}\n")
#         if context.kich_ban:
#             context_parts.append(f"Chi tiết kịch bản: {context.kich_ban}\n")
            
#         if context_parts:
#             context_prefix = " ".join(context_parts) + " "
            
#         enhanced_query = context_prefix + input_query.query
        
        
#         # Thực hiện retrieval với enhanced query
#         retrieval_records = await self._retriever.run(
#             query=enhanced_query,
#             bot_id=self.bot_config['id'],
#             collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
#             allowed_roles=role_ids,
#             top_k=self.bot_config['retrieval'].top_k,
#             threshold=self.bot_config['retrieval'].threshold
#         )
        
#         # Filter documents based on context matching BEFORE reranking
#         filtered_records = await self._filter_documents_by_context(
#             documents=retrieval_records,
#             context=context
#         )
#         LOGGER.info(f"Filtered {len(retrieval_records)} -> {len(filtered_records)} documents")

#         # Sửa dòng reranking thành:
#         reranked_results = await self._reranker.run(
#             query=input_query.query,
#             texts=[r['content'] for r in filtered_records],  # Đổi từ retrieval_records -> filtered_records
#             top_k=self.bot_config['reranking'].top_k,
#             threshold=self.bot_config['reranking'].threshold,
#         )

#         # Sửa construct final documents:
#         final_docs = []
#         valid_count = 0
#         for r in reranked_results:
#             record = filtered_records[r['index']]  # Đổi từ retrieval_records -> filtered_records
#             record['score'] = r['score']
#             # Thêm context info vào document
#             record['context'] = {
#                 'pham_vi': context.pham_vi,
#                 'chuyen_mon': context.chuyen_mon,
#                 'kich_ban': context.kich_ban
#             }
#             if record['score'] > valid_score:
#                 valid_count += 1
#             final_docs.append(record)

#         return {
#             'docs': final_docs,
#             'context': context
#         }
    

#     async def _flow_chit_chat(
#             self,
#             query: str,
#             docs: List[Dict]
#     ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
#         """Handle casual conversation flow.
        
#         Args:
#             query: User's input message
#             docs: List of relevant documents for context
            
#         Returns:
#             Stream of response chunks from LLM
            
#         Note:
#             Uses casual conversation prompt template
#         """
#         # 1. create chitchat prompt
#         system_prompt = CHIT_CHAT_PROMPT_QHLD.format(
#             definition=self.bot_config['definition']
#         )

#         # 2. create attached docs for output return (FE)
#         attached_docs = self._create_attached_docs(
#             documents=docs
#         )

#         # 3. create streaming response
#         async for chunk in self._llm.run(
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": query}
#                 ],
#                 docs=attached_docs
#         ):
#             yield chunk

#     async def _verify_document(
#             self,
#             query: str,
#             documents: List[Dict]
#     ) -> VerifyResult:
#         """Verify if retrieved documents match the user's query.
        
#         Args:
#             query: User's input query
#             documents: List of retrieved documents to verify
            
#         Returns:
#             VerifyResult object indicating if documents match query
#         """
#         _prompt = VERIFY_DOCUMENT_PROMPT_QHLD.format(
#             query=query,
#             documents=self._format_documents(
#                 documents=documents
#             )
#         )

#         response_text = await self._stream_llm_response(
#             messages=[
#                 {"role": "user", "content": _prompt}
#             ]
#         )

#         return parse_model(
#             input_text=response_text,
#             model_class=VerifyResult
#         )
    
#     async def _flow_non_chit_chat(
#             self,
#             query: str,
#             docs: List[Dict],
#             context: ContextAnalysis  # Thêm parameter context
#     ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
#         """Handle information-seeking conversation flow.
        
#         Args:
#             query: User's input query
#             docs: List of relevant documents
#             context: Context analysis containing pham_vi, chuyen_mon, kich_ban
            
#         Returns:
#             Stream of response chunks from LLM
            
#         Note:
#             Verifies document relevance before generating response
#         """
#         # 1. verify the relevant of documents
#         verify = await self._verify_document(
#             query=query,
#             documents=docs
#         )

#         # 2. decide the flow matched/unmatched
#         if verify.output == 'matched':
#             current_date = datetime.now().strftime('%Y-%m-%d')

#             system_prompt = NON_CHIT_CHAT_PROMPT_QHLD.format(
#                 date=current_date,
#                 definition=self.bot_config['definition'],
#                 pham_vi=context.pham_vi if context.pham_vi else "Chưa xác định",
#                 chuyen_mon=context.chuyen_mon if context.chuyen_mon else "Chưa xác định", 
#                 kich_ban=context.kich_ban if context.kich_ban else "Chưa xác định",
#                 query=query,
#                 documents=self._format_documents(
#                     documents=docs
#                 )
#             )
#         else:
#             system_prompt = REFUSE_PROMPT_QHLD.format(
#                 definition=self.bot_config['definition']
#             )

#         # 3. create attached docs to return in bot results (for FE)
#         attached_docs = self._create_attached_docs(
#             documents=docs
#         )

#         # 4. create streaming response
#         async for chunk in self._llm.run(
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": query}
#                 ],
#                 docs=attached_docs
#         ):
#             yield chunk
    
#     # Updated main run method
#     async def run(
#         self,
#         messages: List[Dict],
#         role_ids=None,
#         topic: str = "default",
#         **kwargs
# ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
#         if role_ids is None:
#             role_ids = []
            
#         if "L2" in role_ids:
#             print("=++++++++++++++")
#             # 1. Generate intent như cũ
#             input_query = await self._generate_intent(
#                 messages=messages
#             )
            
#             # 2. Extract QHLD information
#             extract_infor = await self._extract_QHLD(
#                 messages=messages
#             )
            
            
#             # 3. Decide flow based on extract_infor
#             if extract_infor == "normal":
                
#                 async for chunk in self._flow_normal_integration(messages=messages, role_ids=role_ids):
#                     yield chunk
                    
#             else:  # extract_infor == "non_normal"
#                 # 4. Analyze context - phân tích phạm vi, chuyên môn, kịch bản
#                 context_analysis = await self._analyze_context(
#                     query=input_query.query
#                 )
                
#                 # 5. Enhanced retrieval với context analysis
#                 retrieval_result = await self._retrieval_and_rerank_enhanced(
#                     input_query=input_query,
#                     context=context_analysis,
#                     role_ids=role_ids,
#                     topic=topic,
#                     valid_score=0.5
#                 )
                
#                 # 6. Execute non_chit_chat flow
#                 async for chunk in self._flow_non_chit_chat(
#                         query=input_query.query,
#                         docs=retrieval_result['docs'],
#                         context=context_analysis
#                 ):
#                     yield chunk
#         else:
#             async for chunk in self._flow_normal_integration(messages=messages, role_ids=role_ids):
#                 yield chunk          
            

# async def main():
#     from beeportal.beegen_bot_v2 import Bot
#     from beegenerate.storage import BotStore
#     from beegenerate.configs import MongoConfig, MilvusConfig

#     bot_id = "5d816aa9-a21c-4f02-92bf-a28d09aa0ef9"
#     bot_store = BotStore(config=MongoConfig.default())
#     bot_config = bot_store.fetch_bot_details(
#         bot_id=bot_id
#     )

#     bot = BeeHi_QHLD(
#         bot_config=bot_config,
#         vec_store=MilvusStorage(config=MilvusConfig.default()),
#         doc_store=DocumentStore(config=MongoConfig.default()),
#         bot_store=BotStore(config=MongoConfig.default())
#     )

#     async for chunk in bot.run(
#             messages=[
#                 {"role": "user", "content": "Có bao nhiêu loại chuyên môn chấm dứt hợp đồng lao động?"},
#             ],
#             role_ids=["L1"],
#             topic="default"
#     ):
#         if len(chunk.choices) > 0:
#             if chunk.choices[0].delta.content is not None:
#                 response_text = chunk.choices[0].delta.content
#                 # print(response_text, end="")


# if __name__ == "__main__":
#     import asyncio

#     asyncio.run(main())
