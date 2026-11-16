import asyncio
from datetime import datetime
from typing import List, Dict, AsyncGenerator, Any

import pandas as pd
import yaml
from langfuse.decorators import observe, langfuse_context
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beegenerate.configs import (
    LLMConfig,
    MilvusConfig
)
from beegenerate.const import BEEGEN_ROOT
from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.prompts.bee247 import *
from beegenerate.prompts.bee247_v2 import *
from beegenerate.reranks.rerank_factory import RerankingFactory
from beegenerate.retrievers import VectorRetriever
from beegenerate.storage import (
    DocumentStore,
    BotStore
)
from beegenerate.vectordb import MilvusStorage
from beeportal.bot_bee247.bee247.constants import *
from beeportal.bot_bee247.bee247.conversation_processor import ConversationProcessor


class Bee247Bot:

    def __init__(
            self,
            bot_id: str,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize Bee247Bot with required components and configurations."""
        self.bot_id = bot_id
        self.collection_master = f"bot_{bot_id.replace('-', '_')}"
        self.collection_gw = f"{self.collection_master}_gwcode"
        self.collection_card = f"{self.collection_master}_THE"
        self.collection_fee = f"{self.collection_master}_BIEUPHI"
        self.collection_promotion = f"{self.collection_master}_UUDAI"

        self.bot_config = bot_config

        self._llm = LLMExecutor(
            primary_config=bot_config['llm'],
            config_store=bot_store
        )

        self._alt_llm = LLMExecutor(
            primary_config=LLMConfig.from_yaml_file(
                BEEGEN_ROOT / "config/llms/beegen_v1.yaml"),
            config_store=bot_store
        )

        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )
        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])

        self.abbr_dict = self._load_abbreviation()
        self.cep_account_mapping = self._load_STK_mapping()
        self.cep_mapping = self._load_cep_mapping()
        self.DOCUMENT_TEXT_CACHING = {}

        self.conversation_processor = ConversationProcessor(self.bot_id)

    ### LOAD SOME DATA ###

    def _load_abbreviation(self):
        """Load abbreviation"""
        abb_df = pd.read_csv(r'beeportal/bot_bee247/bee247/abbreviations.csv', encoding="utf-8-sig")
        abb_df["Abbreviation"] = abb_df["Abbreviation"].str.lower()
        abb_dict = dict(zip(abb_df["Abbreviation"], abb_df["Meaning"]))
        return abb_dict

    def _load_STK_mapping(self):
        """Load STK mapping data from Excel file using pandas, then convert to list of dictionaries."""
        try:
            # Read Excel using pandas
            df_stk = pd.read_excel(
                "examples/bee247/cep_stk_mapping.xlsx",
                index_col=None
            )

            # Convert DataFrame to list of dictionaries
            stk_data = df_stk.to_dict('records')
            return stk_data
        except Exception as e:
            LOGGER.error(f"Error loading STK mapping: {str(e)}", exc_info=True)
            return []

    def _load_cep_mapping(self):
        """Load CEP mapping data from Excel file using pandas, then convert to list of dictionaries."""
        try:
            # Read Excel using pandas
            df_cep = pd.read_excel(
                "examples/bee247/cep_step_mapping.xlsx",
                index_col=None
            )

            # Convert DataFrame to list of dictionaries
            cep_data = df_cep.to_dict('records')
            return cep_data
        except Exception as e:
            LOGGER.error(f"Error loading CEP mapping: {str(e)}", exc_info=True)
            return []

    ### BASIC USAGE FUNCTION ### 
    @observe()
    def cep_mapping_of(self, query: str):
        """
        Find account information in a query and return corresponding CEP mapping details.
        
        This function searches for account numbers in the input query,
        then fetches the associated group information and CEP steps.
        
        Args:
            query (str): Text that might contain an account number
                
        Returns:
            str: Formatted instruction text if an account number is found
            False: If no matching account is found or an error occurs
        """
        result = {
            "success": False,
            "message": "No matching found"
        }

        try:
            # Search for any account number that appears in the query
            for account_data in self.cep_account_mapping:
                account_number = account_data["stk"]

                # Skip if account number is missing or not found in query
                if not account_number or str(account_number).strip() not in query:
                    continue

                # Get the group for this account
                account_group = account_data["nhóm"]

                # Look up the CEP information for this group
                cep_info = next((item for item in self.cep_mapping if item["nhóm"] == account_group), None)

                if cep_info:
                    # Format the response using the template
                    result["message"] = CEP_MAPPING_PROMPT.format(
                        cep_account=account_data['stk'],
                        cep_name=account_data['tên'],
                        cep_group=cep_info["tên"]
                    )
                    result["success"] = True
                    return result

            # No matching account found
            return result

        except Exception as e:
            error_message = f"Error while mapping CEP: {str(e)}"
            LOGGER.warning(error_message, exc_info=True)

            result["success"] = False
            result["message"] = error_message
            return result

    @observe()
    def annotate_query(self, query: str):
        """Adds explanations after abbreviations found in text."""
        words = query.split()

        result = []
        for word in words:
            if word.lower() in self.abbr_dict:
                result.append(f"{word} ({self.abbr_dict[word.lower()]})")
            else:
                result.append(word)

        anns_query = " ".join(result)
        return anns_query

    @observe()
    async def _fetch_and_rank(
            self,
            query: str,
            collection: str,
            role_ids: List[str] = ['L1'],
            topic: str = "default",
            retrieval_top_k: int = 1,
            retrieval_threshold: float = 0,
            rerank_top_k: int = 1,
            rerank_threshold: float = 0,
            **kwargs
    ) -> List[Dict]:
        """Retrieves and reranks documents from Milvus based on query similarity.
       
        Performs a two-stage search process:
        1. Initial retrieval: Fetches top-k documents from Milvus based on vector similarity
        2. Reranking: Applies a more precise but computationally expensive reranking to improve results
        
        Args:
            query (str): The search query text
            role (str, optional): Access role level for document filtering ("L1", "L2", "L3"). Defaults to "L1".
            topic (str, optional): Topic category for document filtering. Defaults to "default".
            retrieval_top_k (int, optional): Number of documents to retrieve in first stage. Defaults to 1.
            retrieval_threshold (float, optional): Minimum similarity score for initial retrieval (0-1). Defaults to 0.
            rerank_top_k (int, optional): Number of documents to keep after reranking. Defaults to 1.
            rerank_threshold (float, optional): Minimum score threshold after reranking (0-1). Defaults to 0.
            **kwargs: Additional arguments passed to retrieval and reranking methods
            
        Returns:
            List[Dict]: List of retrieved and reranked documents, each containing metadata and content
        """
        # 1. retrieve the relevant records by vector search
        records = await self._retriever.run(
            query=query,
            bot_id=self.bot_id,
            collection=collection,
            top_k=retrieval_top_k,
            threshold=retrieval_threshold,
            allowed_roles=role_ids,
            **kwargs
        )

        # 3. rerank the retrieval results
        reranked_records = await self._reranker.run(
            query=query,
            texts=[r['content'] for r in records],
            top_k=rerank_top_k,
            threshold=rerank_threshold
        )

        # 4. construct the final documents
        final_docs = []
        for r in reranked_records:
            record = records[r['index']]
            record['score'] = r['score']
            final_docs.append(record)

        # 5. return docs
        return final_docs

    @observe()
    async def _rank(self, query: str, chunks_to_rerank: List[str], chunk_ids: List[str]) -> List[Dict]:
        """
        Rerank document chunks based on relevance to query.
        
        Args:
            query: Search query text
            chunks_to_rerank: List of text chunks to score
            chunk_ids: Corresponding IDs for each chunk
            
        Returns:
            List of dictionaries with reranked results (id, chunk, score)
        """
        if not chunks_to_rerank:
            return []

        # Get reranking scores
        reranked_scores = await self._reranker.run(query=query, texts=chunks_to_rerank, top_k=len(chunks_to_rerank))

        # Map scores to original chunks
        return [
            {
                "id": chunk_ids[score_info["index"]],
                "chunk": chunks_to_rerank[score_info["index"]],
                "score": score_info["score"]
            }
            for score_info in reranked_scores
        ]

    @observe()
    async def _llm_stream(
            self,
            prompt_template: str,
            inputs: Dict[str, Any] = {},
            **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Execute an LLM task with streaming mode.
        
        Args:
            llm: LLM execution engine
            inputs: Dictionary of values to format into the prompt template
            prompt_template: Template string with placeholders for inputs
            **kwargs: Additional arguments to pass to the LLM
            
        Returns:
            an AsyncGenerator of ChatCompletionChunk
        """
        # Format the prompt just once to avoid repeating this operation

        formatted_prompt = prompt_template.format(**inputs) if inputs else prompt_template
        messages = [{'role': 'user', 'content': formatted_prompt}]

        async for chunk in self._llm.run(messages=messages, **kwargs):
            yield chunk

    @observe()
    async def _llm_task(
            self,
            inputs: Dict[str, Any],
            prompt_template: str,
            stops: List[str] = None,
            **kwargs
    ) -> str:
        """Execute an LLM task with support for non-streaming mode.
        
        Args:
            llm: LLM execution engine
            inputs: Dictionary of values to format into the prompt template
            prompt_template: Template string with placeholders for inputs
            **kwargs: Additional arguments to pass to the LLM
            
        Returns:
            a complete response string (stream=False)
        """
        # Format the prompt just once to avoid repeating this operation
        formatted_prompt = prompt_template.format(**inputs)
        messages = [{'role': 'user', 'content': formatted_prompt}]

        # Non-stream mode: collect response efficiently
        content_chunks = []
        try:
            async for chunk in self._alt_llm.run(messages=messages, **kwargs):
                # Using walrus operator for conciseness
                if chunk.choices and (content := chunk.choices[0].delta.content):
                    if stops:
                        if content in stops:
                            return ''.join(content_chunks)

                    content_chunks.append(content)
        except Exception as e:
            # Handle exceptions rather than letting them propagate
            LOGGER.error(f"Error during LLM task execution: {e}")
            raise

        # Join chunks at the end (more efficient than string concatenation in a loop)
        return ''.join(content_chunks)

    ### MAIN FLOW ###
    @observe(name="Bee247Bot")
    async def run(self, messages: List[Dict], **kwargs) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Process user messages and generate appropriate responses.
        
        Routes queries to specialized handlers based on topic classification
        and cached content availability.
        """
        # Process and annotate query
        langfuse_context.update_current_trace(name="Bee247Bot")
        original_query = messages[-1]['content'].strip()
        annotated_original_query = self.annotate_query(query=original_query)
        enhanced_query, history = await self.conversation_processor.process_messages(messages=messages)
        annotated_query = self.annotate_query(query=enhanced_query)

        LOGGER.info(f"QUERY: {annotated_query}")
        if enhanced_query != annotated_query:
            LOGGER.info(f"Rewritten/annotated query: {annotated_query}")

        # 1. Initialize state with query
        state = {
            "query": annotated_query,
            "original_query": annotated_original_query,
            "enhanced_query": enhanced_query,
            "history": history
        }

        # 2. Check if we have a cached answer
        await self._check_cached_qa(state, **kwargs)

        final_response = ""
        if state['check_cached_qa']['check']:
            # Use cached answer if available
            async for chunk in self.stream_cached_answer(state):
                if chunk.choices:
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
            langfuse_context.update_current_observation(output=final_response)
            return

        # 3. Classify query topic
        await self._detect_query_topic(state)
        topic = state['detect_query_topic']['topic']
        LOGGER.info(f"Classified topic: {topic}")

        # 4. Route to appropriate handler based on topic

        # 4.1. card topic handler
        if "sản phẩm thẻ" in topic:
            await self._extract_matching_card_ids(state)
            if state['extract_matching_card_ids']['matched_ids']:
                async for chunk in self.stream_card_information(state):
                    if chunk.choices:
                        final_response += str(chunk.choices[0].delta.content)
                        yield chunk
                langfuse_context.update_current_observation(output=final_response)
                return

        # 4.2. Location-based query handling
        location_handlers = {
            "chi nhánh": ("cn_pgd", DOCUMENT_TEXT_PROMPT),
            "phòng giao dịch": ("cn_pgd", DOCUMENT_TEXT_PROMPT),
            "atm": ("atm", ATM_TEXT_PROMPT),
            "cdm": ("cdm_crm", DOCUMENT_TEXT_PROMPT),
            "crm": ("cdm_crm", DOCUMENT_TEXT_PROMPT),
            "smart bank": ("smart_bank", DOCUMENT_TEXT_PROMPT)
        }

        # Check if topic matches any location type
        for location_type, (doc_id, prompt) in location_handlers.items():
            if location_type in topic:
                async for chunk in self.generate_location_response(
                        state=state, doc_id=doc_id, prompt=prompt
                ):
                    if chunk.choices:
                        final_response += str(chunk.choices[0].delta.content)
                        yield chunk
                langfuse_context.update_current_observation(output=final_response)
                return

        # 5. Default to standard response for all other topics
        async for chunk in self.generate_standard_response(state):
            final_response += str(chunk.choices[0].delta.content if len(chunk.choices) != 0 else " ")
            yield chunk
        langfuse_context.update_current_observation(output=final_response)

    @observe()
    async def generate_location_response(self, state: Dict, doc_id: str, prompt: str) -> AsyncGenerator[
        ChatCompletionChunk, None]:
        """
        Answer queries about MB Bank branch and ATM locations.
        
        Args:
            query: User's location-related question
            document_text_id: ID of the location document to retrieve
            main_prompt: Template for the final LLM prompt
            
        Yields:
            Response chunks from the LLM
        """
        LOGGER.info(f"Processing location query for document: {doc_id}")

        # Initialize state
        query = state['query']
        state = {
            'query': query,
            'document_id': doc_id,
            'main_prompt': prompt,
            'document_texts': None,
            'keywords': None,
            'filtered_data': None,
            'final_prompt': None
        }

        # Execute the multi-step process
        await self._check_location_cache(state)
        if not state.get('check_location_cache'):
            if not state['check_location_cache'].get('document_texts'):
                LOGGER.warning(f"No location data available for {doc_id}")
                return

        await self._extract_location_terms(state)
        self._filter_locations(state)

        # Generate and stream response
        final_response = ""
        document_content = "[\n" + ',\n'.join(state['filter_locations']['data']) + "\n]"
        async for chunk in self._llm_stream(
                prompt_template=prompt,
                inputs={"question": query, "document_text": document_content},
                sleep=0.01
        ):
            if chunk.choices:
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
        langfuse_context.update_current_observation(output=final_response)

    @observe()
    def _filter_locations(self, state: Dict) -> None:
        """Filter location entries to match user's search terms."""
        keywords = state['extract_location_terms']['keywords']
        document_texts = state['check_location_cache']['document_texts']

        # Only filter if we have valid keywords other than 'false'
        # print("STATE:", state)
        if len(keywords) > 1 or 'false' not in keywords:
            filtered_data = [
                item for item in document_texts
                if any(term in item for term in keywords)
            ]

            # Only use filtered data if we found matches
            if filtered_data:
                if not 'filter_locations' in state:
                    state['filter_locations'] = {}
                state['filter_locations']['data'] = filtered_data
                return

        # Default: use all data if no filtering or no matches
        state['filter_locations'] = {
            'data': document_texts
        }

    @observe()
    async def _extract_location_terms(self, state: Dict) -> None:
        """Extract relevant location search terms from user query."""
        try:
            keywords_text = await self._llm_task(
                inputs={"message": state['query']},
                prompt_template=DOCUMENT_TEXT_KEYWORD_EXTRACT_PROMPT
            )

            # Process keywords
            state['extract_location_terms'] = {
                'keywords': [k.lower().strip() for k in keywords_text.split(',')]
            }
            LOGGER.info(f"Extracted location terms: {state['extract_location_terms']['keywords']}")
        except Exception as e:
            LOGGER.error(f"Error extracting location terms: {str(e)}")
            state['extract_location_terms'] = {
                'keywords': ["false"]
            }

    @observe()
    async def _check_location_cache(self, state: Dict) -> None:
        """Check if location data is current and update if needed."""
        document_id = state['document_id']

        # Get document metadata
        doc_data = MONGO_STORAGE.find_with_output_fields(
            collection_name="document_text",
            query={"document_id": document_id},
            output_fields={"updated_time": 1, "_id": 0}
        )

        if not doc_data:
            LOGGER.warning(f"Location document {document_id} not found")
            return

        db_updated_time = doc_data[0].get('updated_time')
        cache_entry = self.DOCUMENT_TEXT_CACHING.get(document_id, {})

        # Check if cache refresh is needed
        if not cache_entry or cache_entry.get('updated_time') != db_updated_time:
            await self._refresh_location_data(state, db_updated_time)

        state['check_location_cache'] = {
            'document_texts': self.DOCUMENT_TEXT_CACHING[document_id]['text']
        }

    @observe()
    async def _refresh_location_data(self, state: Dict, updated_time: str) -> None:
        """Retrieve location data from database and update cache."""
        document_id = state['document_id']

        # Retrieve document text
        text_data = MONGO_STORAGE.find_with_output_fields(
            collection_name="document_text",
            query={"document_id": document_id},
            output_fields={"text": 1, "_id": 0}
        )

        if not text_data or 'text' not in text_data[0]:
            LOGGER.warning(f"No location data found for {document_id}")
            return

        try:
            # Parse and process document
            document_json = json.loads(text_data[0]['text'])

            # Convert string values to lowercase
            for item in document_json:
                for key, value in item.items():
                    if isinstance(value, str):
                        item[key] = value.lower()

            # Format documents
            document_texts = [json.dumps(item, indent=0, ensure_ascii=False) for item in document_json]

            # Update cache
            self.DOCUMENT_TEXT_CACHING[document_id] = {
                'updated_time': updated_time,
                'text': document_texts
            }

        except Exception as e:
            LOGGER.error(f"Error processing location data {document_id}: {str(e)}")

    @observe()
    async def generate_standard_response(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Process query and stream LLM-generated response based on retrieved documents.
        
        Executes the full retrieval pipeline: searching across collections,
        preparing the appropriate prompt, and streaming the LLM response.
        
        Args:
            state: Dictionary containing user query and conversation context
            
        Yields:
            Response chunks from the LLM
        """
        # Execute search and prompt preparation
        await self._search_across_collections(state)
        await self._prepare_response_prompt(state)

        # Get prompt and document references
        answer_prompt = state['prepare_response_prompt']['prompt']
        doc_references = [
            {'id': doc['id']}
            for doc in state['search_across_collections']['final_docs']
        ]

        print('answer_prompt:')
        print(answer_prompt)

        final_response = ""
        # Stream response from LLM
        async for chunk in self._llm_stream(
                prompt_template=answer_prompt,
                docs=doc_references,
                sleep=0.01
        ):
            if chunk.choices:
                final_response += str(chunk.choices[0].delta.content if len(chunk.choices) != 0 else " ")
                yield chunk
        langfuse_context.update_current_observation(output=final_response)

    @observe()
    async def _prepare_response_prompt(self, state: Dict) -> None:
        """
        Prepare the final prompt for LLM response generation based on retrieved documents.
        
        Combines retrieved documents with special handling for CEP mapping and
        selects the appropriate prompt template based on document topics.
        
        Args:
            state: Dictionary containing query and search results
            
        Returns:
            str: Formatted prompt ready for LLM processing
        """
        query = state['query']
        retrieved_docs = state['search_across_collections']['final_docs']

        # Check for CEP account mapping
        cep_mapping_result = self.cep_mapping_of(query=query)

        # Format document texts with numbering
        formatted_docs = []
        if cep_mapping_result and 'success' in cep_mapping_result and cep_mapping_result['success']:
            # Add CEP mapping as first document if present
            formatted_docs.append(f'TÀI LIỆU 0:\n{cep_mapping_result["message"]}')
            # Add remaining documents with offset numbering
            for i, doc in enumerate(retrieved_docs):
                formatted_docs.append(f'TÀI LIỆU {i + 1}:\n{doc["chunk"]}')
        else:
            # Standard document numbering when no CEP mapping exists
            for i, doc in enumerate(retrieved_docs):
                formatted_docs.append(f'TÀI LIỆU {i}:\n{doc["chunk"]}')

        # Extract document titles and scores
        doc_topics = {}
        for i, doc in enumerate(retrieved_docs):
            title = formatted_docs[i].split("\n")[1]
            score = doc['score']

            # Keep highest score for each title
            doc_topics[title] = max(doc_topics.get(title, 0), score)

        # Get top document title
        top_doc_title = formatted_docs[0].split("\n")[1] if formatted_docs else ""

        # Select appropriate prompt template based on document topics
        docs_to_include = formatted_docs  # Include all docs
        template = NORMAL_RAG_ANSWER_PROMPT

        if "Các gói dịch vụ và hạn mức giao dịch của eMB (Internet Banking)" in doc_topics:
            # Use eMB-specific template
            template = EMB_RAG_ANSWER_PROMPT
            docs_to_include = formatted_docs[:3]  # Only include top 3 docs
        elif "Cẩm nang hỗ trợ định danh Khách hàng" in doc_topics:
            if (top_doc_title == "Cẩm nang hỗ trợ định danh Khách hàng" or
                    doc_topics["Cẩm nang hỗ trợ định danh Khách hàng"] > 0.85):
                # Use eKYC-specific template
                template = EKYC_RAG_ANSWER_PROMPT

        # Combine documents with separator
        documents_text = '\n------------------\n'.join(
            docs_to_include) if docs_to_include else "không tìm thấy tài liệu phù hợp"

        if state['history'] is not None:
            template = NORMAL_RAG_WITH_HISTORY_ANSWER_PROMPT
            # Format the final prompt with history
            state['prepare_response_prompt'] = {
                "prompt": template.format(
                    documents=documents_text,
                    date=datetime.now().date().strftime("%d/%m/%Y"),
                    question=query,
                    history=state['history']
                )
            }
        else:
            # Format the final prompt
            state['prepare_response_prompt'] = {
                "prompt": template.format(
                    documents=documents_text,
                    date=datetime.now().date().strftime("%d/%m/%Y"),
                    question=query
                )
            }

    @observe()
    async def _search_across_collections(self, state: Dict) -> None:
        """
        Search and rank documents across multiple collections.
        
        Retrieves documents from main collection, Q&A database, and 
        gw code collection, then performs final cross-collection ranking.
        
        Args:
            state: Dictionary containing the user query
            
        Returns:
            List of ranked document results across all collections
        """
        query = state['query']

        # Fetch from multiple collections in parallel
        retrieval_tasks = [
            self._fetch_and_rank(
                query=query,
                collection=self.collection_master,
                retrieval_top_k=16,
                rerank_top_k=3,
                partition_names=['document']
            ),
            self._fetch_and_rank(
                query=query,
                collection=self.collection_master,
                retrieval_top_k=16,
                rerank_top_k=2,
                partition_names=['QA']
            ),
            self._fetch_and_rank(
                query=query,
                collection=self.collection_gw,
                retrieval_top_k=16,
                rerank_top_k=2
            ),
            self._fetch_and_rank(
                query=query,
                collection=self.collection_fee,
                retrieval_top_k=16,
                rerank_top_k=2
            ),
            self._fetch_and_rank(
                query=query,
                collection=self.collection_promotion,
                retrieval_top_k=6,
                rerank_top_k=2
            )
        ]

        # Execute all search requests concurrently
        document_records, qa_records, gw_code_records, fee_records, promotion_records = await asyncio.gather(
            *retrieval_tasks)

        # Combine results from all collections
        all_results = document_records + qa_records + gw_code_records + fee_records + promotion_records

        # Prepare for cross-collection ranking
        chunks = [
            r['content'] + '\nHạn tài liệu/Chương trình: ' + r['valid_to'].strftime("Ngày %d/%m/%Y")
            if 'valid_to' in r and isinstance(r['valid_to'], datetime)
            else r['content']
            for r in all_results
        ]

        ids = [r['id'] for r in all_results]

        # Final ranking across all collections
        final_docs = await self._rank(query=query, chunks_to_rerank=chunks, chunk_ids=ids)
        state['search_across_collections'] = {
            "final_docs": final_docs
        }

    @observe()
    async def stream_card_information(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Retrieve and stream card information based on matched IDs.
        
        Gets relevant card documents for each matched topic ID, generates
        an introduction, then streams detailed information for each topic.
        
        Args:
            state: Dictionary containing query and matched card IDs
            
        Yields:
            LLM response chunks with card information
        """
        # Get matched topic IDs and metadata
        matched_card_ids = state['extract_matching_card_ids']['matched_ids']
        card_name_mapping = get_card_filename()
        card_topics = [card_name_mapping[card_id] for card_id in matched_card_ids]

        # Retrieve relevant documents for each topic
        topic_to_documents = {}
        citation_references = []

        for card_topic, card_id in zip(card_topics, matched_card_ids):
            # Get documents for this topic
            retrieved_documents = await self._fetch_and_rank(
                query=state['query'],
                collection=self.collection_card,
                retrieval_top_k=10,
                rerank_top_k=3,
                partition_names=[str(card_id)]
            )

            # Track for citation purposes
            citation_references.extend([{'id': doc['id']} for doc in retrieved_documents])
            topic_to_documents[card_topic] = retrieved_documents

        # Stream introduction section
        final_response = ""
        async for chunk in self._llm_stream(
                inputs={"question": state['query'], "topics": card_topics},
                prompt_template=TOPIC_SYNTHESIZE_INTRODUCTION_PROMPT,
                docs=citation_references
        ):
            if chunk.choices:
                final_response += str(chunk.choices[0].delta.content)
                yield chunk

        # Stream detailed information for each topic
        for card_topic in card_topics:
            document_contents = [doc['content'] for doc in topic_to_documents[card_topic]]
            async for chunk in self._llm_stream(
                    inputs={
                        "topic": card_topic,
                        "topics": card_topics,
                        "documents": "\n-------------------\n".join(document_contents),
                        "question": state['query']
                    },
                    prompt_template=TOPIC_SYNTHESIZE_LOCAL_PROMPT,
                    sleep=0.01,
                    docs=citation_references
            ):
                if chunk.choices:
                    final_response += str(chunk.choices[0].delta.content)
                    yield chunk
            langfuse_context.update_current_observation(output=final_response)

    @observe()
    async def _extract_matching_card_ids(self, state: Dict) -> None:
        """
        Extract card keywords from query and find matching card IDs.
        
        Uses LLM to identify card-related keywords and matches them against
        a card database to find relevant card IDs.
        
        Args:
            state: Dictionary containing query, updated with matching card IDs
        """

        # Helper function for matching keywords to cards
        def _find_matching_cards(
                keyword_dict: Dict,
                keywords: List,
                all_keywords: List
        ) -> List[str]:
            # Special case for "priority visa" combination
            if set(keywords) == {"priority", "visa"}:
                return [key for key, kw in keyword_dict.items()
                        if "priority" in kw and "visa" in kw]

            matches = []

            # Handle priority cards separately
            if "priority" in keywords:
                matches.extend([key for key, kw in keyword_dict.items()
                                if "priority" in kw])
                keywords = [k for k in keywords if k != "priority"]

            # Filter valid keywords and find matches
            valid_keywords = [k for k in keywords if k in all_keywords]
            if valid_keywords:
                matches.extend([key for key, kw in keyword_dict.items()
                                if all(k in kw for k in valid_keywords)])

            return matches

        # Get card keywords from LLM
        response = await self._llm_task(
            inputs={"question": state['query'], "keywords": get_card_keyword_unique()},
            prompt_template=CARD_KEYWORD_EXTRACT_PROMPT
        )

        # Clean and parse response
        extracted_keywords = eval(response.strip("\"").strip("?"))

        # Get unique keywords and mappings once
        card_keyword_mapping = get_card_keyword_mapping()
        unique_keywords = get_card_keyword_unique()

        # Find matching cards
        card_ids = _find_matching_cards(
            keyword_dict=card_keyword_mapping,
            keywords=extracted_keywords,
            all_keywords=unique_keywords
        )

        # Log results
        LOGGER.info(f"Extracted keywords: {extracted_keywords}")
        LOGGER.info(f"Card IDs: {card_ids}")

        # Update state
        state['extract_matching_card_ids'] = {
            'matched_ids': card_ids
        }

    @observe()
    async def _detect_query_topic(self, state: Dict) -> None:
        """
        Identify topic category of user query and store in state.
        
        Uses LLM to classify the query topic and updates state dictionary
        with the classification result.
        
        Args:
            state: Dictionary containing the user query, updated with topic
        """
        response = await self._llm_task(
            inputs={"question": state['query']},
            prompt_template=TOPIC_CLASSIFY_PROMPT,
            stops=['Ex']
        )
        response = response.replace('```', '').strip()
        result_dict = yaml.safe_load(response.replace('?', ''))

        result_dict['topic'] = str(result_dict['topic']).lower()
        state['detect_query_topic'] = result_dict

    @observe()
    async def stream_cached_answer(self, state: Dict) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream response using pre-cached Q&A content.
        
        Takes cached content from state and generates a streaming response
        using the question and cached answer.
        
        Args:
            state: Dictionary containing query and cached Q&A reference
            
        Yields:
            LLM response chunks based on cached content
        """
        # Cache hits
        final_response = ""
        cached_qa = state['check_cached_qa']['ref']
        async for chunk in self._llm_stream(
                inputs={
                    "question": state['query'],
                    "documents": cached_qa['content'],
                    "date": datetime.now().date()
                },
                prompt_template=NORMAL_RAG_ANSWER_PROMPT,
                sleep=0.01,
                docs=[{'id': cached_qa['id']}]
        ):
            if chunk.choices:
                final_response += str(chunk.choices[0].delta.content)
                yield chunk
        langfuse_context.update_current_observation(output=final_response)

    @observe()
    async def _check_cached_qa(self, state: Dict, **kwargs) -> None:
        """
        Check if query matches an existing cached Q&A entry.
        
        Retrieves similar Q&A pairs and uses LLM to determine if the query
        is semantically equivalent to a cached question.
        
        Args:
            query: User question to check
            **kwargs: Additional arguments for retrieval or LLM
            
        Returns:
            bool: True if query is already cached, False otherwise
        """
        # first, retrieve the top QA to filter the already-cached one
        query = state['query']
        qa_results = await self._fetch_and_rank(
            query=query,
            collection=self.collection_master,
            retrieval_top_k=5,
            rerank_top_k=1,
            partition_names=['QA']
        )
        for qa in qa_results:
            print(f"qa: {qa}")
            print("------------------------------")
        if len(qa_results) > 0:
            cached_qa = qa_results[0]
            LOGGER.info(cached_qa)

            # apply the found Q/A to filter the question
            filter_check = await self._llm_task(
                inputs={"question": query, "document": cached_qa['content']},
                prompt_template=QA_FILTER_PROMPT,
                **kwargs
            )

            result = "có" in filter_check.lower()
            state['check_cached_qa'] = {
                'check': result,
                'ref': cached_qa
            }
        else:
            LOGGER.info("No QA found.")
            state['check_cached_qa'] = {
                'check': False,
                'ref': "No QA found."
            }


async def main():
    bot_id = "cbc75713-2646-4331-84ad-645664ab86ef"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )
    bot = Bee247Bot(bot_id=bot_id, bot_config=bot_config,
                    vec_store=MilvusStorage(config=MilvusConfig.default()),
                    doc_store=DocumentStore(config=MongoConfig.default()),
                    bot_store=BotStore(config=MongoConfig.default()))

    async for chunk in bot.run(
            messages=[{"role": "user", "content": "KH ra CN mua USD nhưng CN điều hướng KH mua ngoại tệ khác"}],
            role_ids=["QM"],
            topic="default"
    ):
        pass


if __name__ == "__main__":
    asyncio.run(main())

    # from beegen.embeddings import EmbeddingFactory

    # bot = Bee247Bot(bot_id="4aa0843a-46d2-4acf-8b96-84d0d144a862")
    # vec_store = bot._retriever._vec_store
    # embed = bot._retriever._embedder

    # query = "'68. Thẻ tín dụng quốc tế Visa Credit.docx\nPhí thay đổi hạng thẻ của thẻ tín dụng Visa Credit?\n200.000 VND/thẻ (miễn phí nâng hạ hạng do thẻ hết hạn và phải đổi hạng do ko đủ đk ở hạng cũ)'".replace("'","")
    # # chunk_id = "e9a79d24-74fb-4a91-9234-93fdcb201790"
    # embedding = asyncio.run(embed.run(texts=[query]))
    # print(embedding[0])

    # collection = vec_store._load_collection(collection_name="Time2025_04_10T17_11_57_113854")
    # partition = collection.partition("QA")
    # print(f"Số bản ghi trong partition QA': {partition.num_entities}")

    # results = collection.query(
    #     expr=f'chunk_id == "{chunk_id}"',
    #     output_fields=["role", "vector", "chunk_id", "topic", "type"] 
    # )

    # vector_milvus = results[0]['vector']
    # from beegen.embeddings.vllm_embedding import cosine_similarity_search

    # print(cosine_similarity_search(vector_milvus, embedding))
