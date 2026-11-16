"""
BeeHi QHLD Bot - Cleaned Version with Enhanced Logging
Handles labor relations queries with context-aware document retrieval
"""

from typing import List, Dict, Tuple, Any, TypeVar, Type, Optional
import asyncio
import json
import re
from datetime import datetime
from pydantic import BaseModel

# Import components
from beegenerate.vectordb.base import VDBQuery
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import DocumentStore, BotStore
from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.utils.common import transform_bot_id
from beegenerate.loggings import LOGGER

from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk


from langfuse.decorators import observe, langfuse_context
from beegenerate.loggings.loggers import lf
import uuid

# Generic type for BaseModel
T = TypeVar('T', bound=BaseModel)

# Langfuse configuration
langfuse_app_name = "BeeHi_QHLD"
langfuse_session_id = langfuse_app_name + "_" + str(uuid.uuid4())


try:
    REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD = lf.get_prompt(name="REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD").prompt
    VERIFY_DOCUMENT_PROMPT_QHLD = lf.get_prompt(name="VERIFY_DOCUMENT_PROMPT_QHLD").prompt
    NON_CHIT_CHAT_PROMPT_QHLD = lf.get_prompt(name="NON_CHIT_CHAT_PROMPT_QHLD").prompt
    REFUSE_PROMPT_QHLD = lf.get_prompt(name="REFUSE_PROMPT_QHLD").prompt
    LLM_FILTER_PHASE1_PROMPT_QHLD = lf.get_prompt(name="LLM_FILTER_PHASE1_PROMPT_QHLD").prompt
    LLM_ANALYZE_CONTEXT_PROMPT_QHLD = lf.get_prompt(name="LLM_ANALYZE_CONTEXT_PROMPT_QHLD").prompt
    LLM_FILTER_BY_CONTEXT_PROMPT_QHLD = lf.get_prompt(name="LLM_FILTER_BY_CONTEXT_PROMPT_QHLD").prompt
    CLASSIFY_QUESTION_TYPE_PROMPT_QHLD = lf.get_prompt(name="CLASSIFY_QUESTION_TYPE_PROMPT_QHLD").prompt
    NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE = lf.get_prompt(name="NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE").prompt
    SYSTEM_PROMPT_INTENT = lf.get_prompt(name="SYSTEM_PROMPT_INTENT").prompt
    SYSTEM_PROMPT_CHIT_CHAT = lf.get_prompt(name="SYSTEM_PROMPT_CHIT_CHAT").prompt
    SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED = lf.get_prompt(name="SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED").prompt
    SYSTEM_PROMPT_NON_CHIT_CHAT = lf.get_prompt(name="SYSTEM_PROMPT_NON_CHIT_CHAT").prompt
    SYSTEM_PROMPT_REFUSE = lf.get_prompt(name="SYSTEM_PROMPT_REFUSE").prompt
    SYSTEM_PROMPT_RELEVANCE_TOPIC = lf.get_prompt(name="SYSTEM_PROMPT_RELEVANCE_TOPIC").prompt
    SYSTEM_PROMPT_QUERY_CLARITY = lf.get_prompt(name="SYSTEM_PROMPT_QUERY_CLARITY").prompt
    SYSTEM_PROMPT_PARTIAL_ANSWER = lf.get_prompt(name="SYSTEM_PROMPT_PARTIAL_ANSWER").prompt
    BEEHI_QHLD_SHORTCUT = lf.get_prompt(name="BEEHI_QHLD_SHORTCUT").prompt
    LOGGER.info("✓ Loaded prompts from Langfuse ")
except Exception as e:
    LOGGER.warning(f"⚠ Failed to load from Langfuse: {e}, using local prompts")
    from beehi_QHLD.data.prompt_v2 import (
        REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD,
        VERIFY_DOCUMENT_PROMPT_QHLD,
        NON_CHIT_CHAT_PROMPT_QHLD,
        REFUSE_PROMPT_QHLD,
        LLM_FILTER_PHASE1_PROMPT_QHLD,
        LLM_ANALYZE_CONTEXT_PROMPT_QHLD,
        LLM_FILTER_BY_CONTEXT_PROMPT_QHLD,
        CLASSIFY_QUESTION_TYPE_PROMPT_QHLD,
        NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE
    )
    from beehi_QHLD.data.happy_hub import (
        SYSTEM_PROMPT_INTENT,
        SYSTEM_PROMPT_CHIT_CHAT,
        SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED,
        SYSTEM_PROMPT_NON_CHIT_CHAT,
        SYSTEM_PROMPT_REFUSE,
        SYSTEM_PROMPT_RELEVANCE_TOPIC,
        SYSTEM_PROMPT_QUERY_CLARITY,
        SYSTEM_PROMPT_PARTIAL_ANSWER
    )
    from beehi_QHLD.data.source_data import (
        BEEHI_QHLD_SHORTCUT,
    )

    


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ContextAnalysis(BaseModel):
    """Context analysis result containing violation scope, expertise, and scenario"""
    pham_vi: str = ""       # Violation scope
    chuyen_mon: str = ""    # Expertise area
    kich_ban: str = ""      # Specific scenario


class InputQuery(BaseModel):
    """Rewritten and classified user query"""
    query: str

class QuestionType(BaseModel):
    """Classification of question type"""
    type: str  # "aggregate" | "specific" | "procedural"
    reasoning: str = ""

class VerifyResult(BaseModel):
    """Document verification result"""
    output: str  # "matched" or "unmatched"


class DocumentResult(BaseModel):
    """Enhanced document retrieval result with answer status"""
    docs: List[Dict]
    relevance_score: float
    fully_answered: bool = False
    partially_answered: bool = False
    answered_info: str = ""
    missing_info: str = ""


class ChunkMetadata(BaseModel):
    """Metadata for each chunk after Milvus search"""
    chunk_id: str
    partitions: List[str] = []              # Matched partitions: ["CHUYEN_MON", "KICH_BAN", ...]
    scores: Dict[str, float] = {}           # Score from each partition: {"chuyen_mon": 0.85, ...}


class ParsedChunk(BaseModel):
    """Fully parsed chunk from MongoDB"""
    chunk_id: str
    chuyen_mon: str = ""
    pham_vi_vi_pham: str = ""
    kich_ban: str = ""
    quy_trinh: str = ""
    file_name: str = ""
    partition_scores: Dict[str, float] = {}
    
    @classmethod
    def from_mongo_content(cls, chunk_id: str, content_str: str, scores: Dict[str, float]):
        """Parse JSON content from MongoDB
        
        Args:
            chunk_id: Chunk ID
            content_str: JSON string from 'content' field in MongoDB
            scores: Dictionary of scores from partitions
            
        Returns:
            ParsedChunk object
        """
        try:
            content_data = json.loads(content_str)
            return cls(
                chunk_id=chunk_id,
                chuyen_mon=content_data.get('chuyen_mon', ''),
                pham_vi_vi_pham=content_data.get('pham_vi_vi_pham', ''),
                kich_ban=content_data.get('kich_ban', ''),
                quy_trinh=content_data.get('quy_trinh', ''),
                file_name=content_data.get('file_name', ''),
                partition_scores=scores
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in chunk {chunk_id}: {str(e)}")


class LLMFilterResult(BaseModel):
    """Result from LLM filter phase"""
    relevant_chunk_ids: List[str] = []
    reasoning: str = ""


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_model(input_text: str, model_class: Type[T]) -> T:
    """Parse XML input text into a specified Pydantic model
    
    Args:
        input_text: Input string in XML format
        model_class: The Pydantic model class to parse into
        
    Returns:
        An instance of the specified model class
    """
    import xml.etree.ElementTree as ET
    
    try:
        root = ET.fromstring(input_text)
        data = {}
        
        if model_class == InputQuery:
            query_elem = root.find('query')
            if query_elem is not None:
                data['query'] = query_elem.text or ""
            else:
                raise ValueError("Missing query element")
                
        elif model_class == ContextAnalysis:
            pham_vi_elem = root.find('pham_vi')
            chuyen_mon_elem = root.find('chuyen_mon')
            kich_ban_elem = root.find('kich_ban')
            
            data['pham_vi'] = pham_vi_elem.text or "" if pham_vi_elem is not None else ""
            data['chuyen_mon'] = chuyen_mon_elem.text or "" if chuyen_mon_elem is not None else ""
            data['kich_ban'] = kich_ban_elem.text or "" if kich_ban_elem is not None else ""
            
        elif model_class == VerifyResult:
            output_elem = root.find('output')
            if output_elem is not None:
                data['output'] = output_elem.text or ""
            else:
                raise ValueError("Missing output element")
        
        return model_class(**data)
        
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {e}")
    except Exception as e:
        raise ValueError(f"Validation error: {e}")


# ============================================================================
# MAIN BOT CLASS
# ============================================================================

class BeeHi_QHLD:
    """QHLD Chatbot with context-aware document retrieval and LLM filtering
    
    Main Features:
    - Parallel partition search (CHUYEN_MON, KICH_BAN, QUY_TRINH)
    - Multi-stage LLM filtering (relevance → context → final)
    - Fallback to normal flow when no QHLD content found
    - Enhanced logging for debugging
    """

    def __init__(
        self,
        bot_config: Dict,
        vec_store: MilvusStorage,
        doc_store: DocumentStore,
        bot_store: BotStore
    ):
        """Initialize BeeHi_QHLD bot
        
        Args:
            bot_config: Bot configuration with LLM, retrieval, reranking settings
            vec_store: Vector storage for embeddings
            doc_store: Document storage for content
            bot_store: Bot configuration storage
        """
        LOGGER.info("=" * 80)
        LOGGER.info("INITIALIZING BeeHi_QHLD Bot")
        LOGGER.info("=" * 80)
        
        self.bot_config = bot_config
        LOGGER.info(f"Bot ID: {bot_config['id']}")
        
        # Initialize components
        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )
        LOGGER.info("✓ LLM Executor initialized")
        
        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )
        LOGGER.info("✓ Vector Retriever initialized")
        
        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])
        LOGGER.info("✓ Reranker initialized")
        
        LOGGER.info("=" * 80)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _format_documents(self, documents: List[Dict]) -> str:
        """Format documents into a single string separated by [SEP] tokens"""
        return "\n[SEP]\n".join([d['content'] for d in documents])

    def _create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Create metadata for documents to attach to LLM requests"""
        attached_docs = []
        for r in documents:
            chunk_info = {"id": r['id']}
            if 'doc' in r:
                chunk_info['source'] = r['doc']
            attached_docs.append(chunk_info)
        return attached_docs
    @observe()
    async def _stream_llm_response(self, messages: List[Dict]) -> str:
        """Stream LLM response and concatenate chunks
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Concatenated response string
        """
        try:
            response_text = ""
            async for chunk in self._llm.run(messages=messages):
                if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    response_text += str(chunk.choices[0].delta.content)
            return response_text
        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            raise RuntimeError(f"Failed to get LLM response: {str(e)}")

    # ========================================================================
    # STEP 1: GENERATE INTENT (Expand abbreviations)
    # ========================================================================
    @observe()
    async def _generate_intent(self, messages: List[Dict]) -> InputQuery:
        """Generate intent by expanding abbreviations in user query
        
        Args:
            messages: Conversation history
            
        Returns:
            InputQuery with expanded query
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ STEP 1: GENERATE INTENT - Expand Abbreviations" + " " * 29 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")
        
        query = messages[-1]['content']
        LOGGER.info(f"Original query: {query}")
        
        prompt = REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD.format(
            definition=self.bot_config['definition'],
            shortcut=BEEHI_QHLD_SHORTCUT,
            query=query
        )
        
        LOGGER.info("Calling LLM with REWRITE_AND_CLASSIFY_PROMPT_v2_QHLD...")
        response_text = await self._stream_llm_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        input_query = parse_model(input_text=response_text, model_class=InputQuery)
        LOGGER.info(f"✓ Expanded query: {input_query.query}")
        LOGGER.info("")
        langfuse_context.update_current_trace(metadata=input_query)
        return input_query

    # ========================================================================
    # STEP 2: QHLD EXTRACTION V2
    # ========================================================================
    @observe()
    async def _classify_question_type(
        self,
        query: str
    ) -> QuestionType:
        """Classify question type before QHLD extraction
        
        Args:
            query: User query (after expand abbreviations)
            
        Returns:
            QuestionType object
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ STEP 1.5: CLASSIFY QUESTION TYPE" + " " * 45 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")
        
        prompt = CLASSIFY_QUESTION_TYPE_PROMPT_QHLD.format(query=query)
        
        LOGGER.info("Calling LLM with CLASSIFY_QUESTION_TYPE_PROMPT_QHLD...")
        response_text = await self._stream_llm_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        type_match = re.search(r'<type>(.*?)</type>', response_text, re.DOTALL)
        reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', response_text, re.DOTALL)
        
        question_type = QuestionType(
            type=type_match.group(1).strip() if type_match else "specific",
            reasoning=reasoning_match.group(1).strip() if reasoning_match else ""
        )
        
        LOGGER.info(f"✓ Question type: {question_type.type}")
        LOGGER.info(f"  Reasoning: {question_type.reasoning}")
        LOGGER.info("")
        
        return question_type
    @observe()
    async def _search_qhld_partitions(
        self,
        query: str,
        role_ids: List[str],
        bot_id: str
    ) -> Dict[str, ChunkMetadata]:
        """Search 3 QHLD partitions in parallel and strip prefixes
        
        Args:
            query: Search query
            role_ids: User role IDs
            bot_id: Bot ID for collection name
            
        Returns:
            Dict mapping clean chunk_id to ChunkMetadata
        """
        LOGGER.info("  ┌" + "─" * 76 + "┐")
        LOGGER.info("  │ SUB-STEP 2.1: Search QHLD Partitions (Parallel)" + " " * 27 + "│")
        LOGGER.info("  └" + "─" * 76 + "┘")
        
        collection_name = f"bot_{transform_bot_id(bot_id)}"
        top_k = self.bot_config['retrieval'].top_k
        threshold = self.bot_config['retrieval'].threshold
        
        LOGGER.info(f"  Collection: {collection_name}")
        LOGGER.info(f"  Top K: {top_k}, Threshold: {threshold}")
        
        vec_store = self._retriever._vec_store
        embedder = self._retriever._embedder

        # Generate embedding
        LOGGER.info("  Generating query embedding...")
        try:
            embedded_query = await embedder.run(query)
            if not embedded_query:
                LOGGER.error("  ✗ Failed to generate embedding")
                return {}
            embedded_query = embedded_query[0]
            LOGGER.info("  ✓ Embedding generated")
        except Exception as e:
            LOGGER.error(f"  ✗ Error during embedding: {e}")
            return {}

        # Prepare parallel searches
        partitions_to_search = {
            "CHUYEN_MON": "CUSTOM_HR_CHUYEN_MON",
            "KICH_BAN": "CUSTOM_HR_KICH_BAN",
            "QUY_TRINH": "CUSTOM_HR_QUY_TRINH"
        }
        
        LOGGER.info("  Launching 3 parallel searches...")
        search_tasks = []
        for partition_key, partition_name in partitions_to_search.items():
            LOGGER.info(f"    - {partition_key} ({partition_name})")
            task = vec_store.run(
                query=VDBQuery(
                    collection=collection_name,
                    query_vector=embedded_query,
                    top_k=top_k,
                    threshold=threshold,
                    output_fields=['chunk_id']
                ),
                partition_names=[partition_name]
            )
            search_tasks.append(task)
            
        results_from_milvus = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Build chunk metadata map with prefix stripping
        LOGGER.info("  Processing search results...")
        chunk_metadata_map: Dict[str, ChunkMetadata] = {}
        partition_keys = list(partitions_to_search.keys())
        
        for i, matches in enumerate(results_from_milvus):
            partition_key = partition_keys[i]
            
            if isinstance(matches, Exception):
                LOGGER.error(f"  ✗ Error in {partition_key}: {matches}")
                continue
            if not matches:
                LOGGER.info(f"  - {partition_key}: No matches")
                continue

            match_count = 0
            for match in matches:
                raw_id = match.record.id
                
                # Strip prefix if exists
                if '#' in raw_id:
                    clean_id = raw_id.split('#', 1)[1]
                else:
                    clean_id = raw_id
                
                if clean_id not in chunk_metadata_map:
                    chunk_metadata_map[clean_id] = ChunkMetadata(
                        chunk_id=clean_id,
                        partitions=[],
                        scores={}
                    )
                
                chunk_metadata_map[clean_id].partitions.append(partition_key)
                chunk_metadata_map[clean_id].scores[partition_key.lower()] = match.similarity
                match_count += 1
            
            LOGGER.info(f"  ✓ {partition_key}: {match_count} chunks found")

        # Summary statistics
        num_chuyen_mon = sum(1 for m in chunk_metadata_map.values() if "CHUYEN_MON" in m.partitions)
        num_kich_ban = sum(1 for m in chunk_metadata_map.values() if "KICH_BAN" in m.partitions)
        num_quy_trinh = sum(1 for m in chunk_metadata_map.values() if "QUY_TRINH" in m.partitions)

        LOGGER.info("  " + "─" * 76)
        LOGGER.info(f"  Summary: {len(chunk_metadata_map)} unique chunks")
        LOGGER.info(f"    • CHUYEN_MON: {num_chuyen_mon} chunks")
        LOGGER.info(f"    • KICH_BAN: {num_kich_ban} chunks")
        LOGGER.info(f"    • QUY_TRINH: {num_quy_trinh} chunks")
        LOGGER.info("")
            
        return chunk_metadata_map
    @observe()
    async def _fetch_and_parse_chunks(
        self,
        chunk_metadata_map: Dict[str, ChunkMetadata],
        role_names: List[str],
        bot_id: str
    ) -> List[ParsedChunk]:
        """Fetch chunks from MongoDB and parse JSON content
        
        Args:
            chunk_metadata_map: Map of chunk_id to metadata
            role_names: Role names (e.g., ['L2'])
            bot_id: Bot ID for filtering
            
        Returns:
            List of ParsedChunk sorted by composite score
        """
        LOGGER.info("  ┌" + "─" * 76 + "┐")
        LOGGER.info("  │ SUB-STEP 2.2: Fetch & Parse Chunks from MongoDB" + " " * 26 + "│")
        LOGGER.info("  └" + "─" * 76 + "┘")
        
        if not chunk_metadata_map:
            LOGGER.warning("  ✗ No chunks to fetch")
            return []

        chunk_ids = list(chunk_metadata_map.keys())
        LOGGER.info(f"  Fetching {len(chunk_ids)} chunks for roles: {role_names}")

        try:
            # Call find_document_chunks_v2 (handles role translation internally)
            mongo_chunks = self._retriever._doc_store.find_document_chunks_v2(
                chunk_ids=chunk_ids,
                allowed_roles=role_names,
                bot_id=bot_id
            )

            if not mongo_chunks:
                LOGGER.warning("  ✗ No chunks returned from MongoDB")
                return []

            LOGGER.info(f"  ✓ Retrieved {len(mongo_chunks)} chunks from MongoDB")
            
            # Parse chunks
            parsed_chunks = []
            failed_count = 0
            
            for mongo_chunk in mongo_chunks:
                chunk_id = mongo_chunk['id']
                content_str = mongo_chunk.get('raw_text', '')

                if not content_str or chunk_id not in chunk_metadata_map:
                    failed_count += 1
                    continue
                    
                scores = chunk_metadata_map[chunk_id].scores
                
                try:
                    parsed_chunk = ParsedChunk.from_mongo_content(
                        chunk_id=chunk_id,
                        content_str=content_str,
                        scores=scores
                    )
                    parsed_chunks.append(parsed_chunk)
                except ValueError as e:
                    LOGGER.error(f"  ✗ Failed to parse chunk {chunk_id}: {str(e)}")
                    failed_count += 1
                    continue
            
            # Sort by composite score
            def calc_composite_score(chunk: ParsedChunk) -> float:
                return (
                    chunk.partition_scores.get('kich_ban', 0) * 0.5 +
                    chunk.partition_scores.get('chuyen_mon', 0) * 0.3 +
                    chunk.partition_scores.get('quy_trinh', 0) * 0.2
                )
            
            parsed_chunks.sort(key=calc_composite_score, reverse=True)
            
            LOGGER.info(f"  ✓ Successfully parsed: {len(parsed_chunks)} chunks")
            if failed_count > 0:
                LOGGER.warning(f"  ⚠ Failed to parse: {failed_count} chunks")
            LOGGER.info("")
            
            return parsed_chunks
            
        except Exception as e:
            LOGGER.error(f"  ✗ Error in _fetch_and_parse_chunks: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    @observe()
    async def _llm_filter_relevant_chunks(
        self,
        query: str,
        parsed_chunks: List[ParsedChunk]
    ) -> LLMFilterResult:
        """LLM Filter Phase 1: Filter chunks relevant to query
        
        Args:
            query: Original query
            parsed_chunks: List of parsed chunks (15-24 chunks)
            
        Returns:
            LLMFilterResult with relevant chunk IDs
        """
        LOGGER.info("  ┌" + "─" * 76 + "┐")
        LOGGER.info("  │ SUB-STEP 2.3: LLM Filter Phase 1 - Relevance Filtering" + " " * 18 + "│")
        LOGGER.info("  └" + "─" * 76 + "┘")
        
        if not parsed_chunks:
            LOGGER.warning("  ✗ No chunks to filter")
            return LLMFilterResult(relevant_chunk_ids=[], reasoning="No chunks provided")
        
        LOGGER.info(f"  Input: {len(parsed_chunks)} chunks")
        
        # Format chunks info (metadata only, no full quy_trinh)
        chunks_info_lines = []
        for idx, chunk in enumerate(parsed_chunks, 1):
            chunk_info = f"""Chunk {idx} (ID: {chunk.chunk_id}):
    - Phạm vi vi phạm: {chunk.pham_vi_vi_pham}
    - Chuyên môn: {chunk.chuyen_mon}
    - Kịch bản: {chunk.kich_ban}
    - File: {chunk.file_name}"""
            chunks_info_lines.append(chunk_info)
        
        chunks_info = "\n".join(chunks_info_lines)
        
        prompt = LLM_FILTER_PHASE1_PROMPT_QHLD.format(
            query=query,
            chunks_info=chunks_info
        )
        
        LOGGER.info("  Calling LLM with LLM_FILTER_PHASE1_PROMPT_QHLD...")
        
        try:
            response_text = await self._stream_llm_response(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            relevant_chunks_match = re.search(
                r'<relevant_chunks>(.*?)</relevant_chunks>',
                response_text,
                re.DOTALL
            )
            reasoning_match = re.search(
                r'<reasoning>(.*?)</reasoning>',
                response_text,
                re.DOTALL
            )
            
            if not relevant_chunks_match:
                LOGGER.error("  ✗ Failed to parse LLM response")
                return LLMFilterResult(relevant_chunk_ids=[], reasoning="Parse error")
            
            relevant_chunks_str = relevant_chunks_match.group(1).strip()
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
            
            if not relevant_chunks_str:
                LOGGER.warning("  ⚠ LLM filtered out all chunks")
                LOGGER.info(f"  Reasoning: {reasoning}")
                return LLMFilterResult(relevant_chunk_ids=[], reasoning=reasoning)
            
            relevant_chunk_ids = [
                chunk_id.strip()
                for chunk_id in relevant_chunks_str.split(',')
                if chunk_id.strip()
            ]
            
            LOGGER.info(f"  ✓ Output: {len(relevant_chunk_ids)} relevant chunks")
            LOGGER.info(f"  Reasoning: {reasoning[:100]}..." if len(reasoning) > 100 else f"  Reasoning: {reasoning}")
            LOGGER.info("")
            
            return LLMFilterResult(
                relevant_chunk_ids=relevant_chunk_ids,
                reasoning=reasoning
            )
            
        except Exception as e:
            LOGGER.error(f"  ✗ Error in LLM filter: {str(e)}")
            return LLMFilterResult(
                relevant_chunk_ids=[chunk.chunk_id for chunk in parsed_chunks],
                reasoning=f"Error, kept all chunks: {str(e)}"
            )
    @observe()
    async def _llm_analyze_context_from_chunks(
        self,
        query: str,
        relevant_chunks: List[ParsedChunk]
    ) -> Tuple[ContextAnalysis, str]:
        """LLM Analyze Context: Determine best context from filtered chunks
        
        Args:
            query: Original query
            relevant_chunks: Filtered relevant chunks (5-8 chunks)
            
        Returns:
            Tuple of (ContextAnalysis, reasoning)
        """
        LOGGER.info("  ┌" + "─" * 76 + "┐")
        LOGGER.info("  │ SUB-STEP 2.4: LLM Analyze Context" + " " * 41 + "│")
        LOGGER.info("  └" + "─" * 76 + "┘")
        
        if not relevant_chunks:
            LOGGER.warning("  ✗ No chunks to analyze")
            return ContextAnalysis(), "No relevant chunks"
        
        LOGGER.info(f"  Input: {len(relevant_chunks)} relevant chunks")
        
        # Format chunks with FULL info including quy_trinh
        chunks_info_lines = []
        for idx, chunk in enumerate(relevant_chunks, 1):
            quy_trinh_display = chunk.quy_trinh
            if len(quy_trinh_display) > 2000:
                quy_trinh_display = quy_trinh_display[:2000] + "...[truncated]"
            
            composite_score = sum(chunk.partition_scores.values()) / max(len(chunk.partition_scores), 1)
            
            chunk_info = f"""
    ═══════════════════════════════════════════════════════════
    CHUNK {idx} (ID: {chunk.chunk_id})
    Composite Score: {composite_score:.3f}
    ───────────────────────────────────────────────────────────
    Phạm vi vi phạm: {chunk.pham_vi_vi_pham}
    Chuyên môn: {chunk.chuyen_mon}
    Kịch bản: {chunk.kich_ban}
    File: {chunk.file_name}
    ───────────────────────────────────────────────────────────
    Quy trình chi tiết:
    {quy_trinh_display}
    ═══════════════════════════════════════════════════════════"""
            chunks_info_lines.append(chunk_info)
        
        chunks_full_info = "\n".join(chunks_info_lines)
        
        prompt = LLM_ANALYZE_CONTEXT_PROMPT_QHLD.format(
            query=query,
            chunks_full_info=chunks_full_info
        )
        
        LOGGER.info("  Calling LLM with LLM_ANALYZE_CONTEXT_PROMPT_QHLD...")
        
        try:
            response_text = await self._stream_llm_response(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            pham_vi_match = re.search(r'<pham_vi>(.*?)</pham_vi>', response_text, re.DOTALL)
            chuyen_mon_match = re.search(r'<chuyen_mon>(.*?)</chuyen_mon>', response_text, re.DOTALL)
            kich_ban_match = re.search(r'<kich_ban>(.*?)</kich_ban>', response_text, re.DOTALL)
            reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', response_text, re.DOTALL)
            
            pham_vi = pham_vi_match.group(1).strip() if pham_vi_match else ""
            chuyen_mon = chuyen_mon_match.group(1).strip() if chuyen_mon_match else ""
            kich_ban = kich_ban_match.group(1).strip() if kich_ban_match else ""
            reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning"
            
            context = ContextAnalysis(
                pham_vi=pham_vi,
                chuyen_mon=chuyen_mon,
                kich_ban=kich_ban
            )
            
            LOGGER.info("  ✓ Context Analysis Result:")
            LOGGER.info(f"    • Phạm vi: {pham_vi or '(empty)'}")
            LOGGER.info(f"    • Chuyên môn: {chuyen_mon or '(empty)'}")
            LOGGER.info(f"    • Kịch bản: {kich_ban or '(empty)'}")
            LOGGER.info(f"  Reasoning: {reasoning[:100]}..." if len(reasoning) > 100 else f"  Reasoning: {reasoning}")
            LOGGER.info("")
            
            return context, reasoning
            
        except Exception as e:
            LOGGER.error(f"  ✗ Error in context analysis: {str(e)}")
            return ContextAnalysis(), f"Error: {str(e)}"
    @observe()
    async def _llm_filter_by_context(
        self,
        context: ContextAnalysis,
        relevant_chunks: List[ParsedChunk]
    ) -> List[ParsedChunk]:
        """LLM Filter by Context: Match chunks with determined context
        
        Args:
            context: Determined ContextAnalysis
            relevant_chunks: Relevant chunks (5-8 chunks)
            
        Returns:
            Filtered list of ParsedChunk (2-4 chunks typically)
        """
        LOGGER.info("  ┌" + "─" * 76 + "┐")
        LOGGER.info("  │ SUB-STEP 2.5: LLM Filter by Context" + " " * 39 + "│")
        LOGGER.info("  └" + "─" * 76 + "┘")
        
        if not relevant_chunks:
            LOGGER.warning("  ✗ No chunks to filter")
            return []
        
        # Check if context has any info
        if not any([context.pham_vi, context.chuyen_mon, context.kich_ban]):
            LOGGER.warning("  ⚠ Context is empty - returning all relevant chunks")
            return relevant_chunks
        
        LOGGER.info(f"  Input: {len(relevant_chunks)} chunks")
        LOGGER.info("  Context to match:")
        LOGGER.info(f"    • Phạm vi: {context.pham_vi or '(not specified)'}")
        LOGGER.info(f"    • Chuyên môn: {context.chuyen_mon or '(not specified)'}")
        LOGGER.info(f"    • Kịch bản: {context.kich_ban or '(not specified)'}")
        
        # Format chunks info (metadata only)
        chunks_info_lines = []
        for idx, chunk in enumerate(relevant_chunks, 1):
            chunk_info = f"""Chunk {idx} (ID: {chunk.chunk_id}):
    - Phạm vi vi phạm: {chunk.pham_vi_vi_pham}
    - Chuyên môn: {chunk.chuyen_mon}
    - Kịch bản: {chunk.kich_ban}"""
            chunks_info_lines.append(chunk_info)
        
        chunks_info = "\n".join(chunks_info_lines)
        
        prompt = LLM_FILTER_BY_CONTEXT_PROMPT_QHLD.format(
            pham_vi=context.pham_vi or "(không xác định)",
            chuyen_mon=context.chuyen_mon or "(không xác định)",
            kich_ban=context.kich_ban or "(không xác định)",
            chunks_info=chunks_info
        )
        
        LOGGER.info("  Calling LLM with LLM_FILTER_BY_CONTEXT_PROMPT_QHLD...")
        
        try:
            response_text = await self._stream_llm_response(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            matched_chunks_match = re.search(
                r'<matched_chunks>(.*?)</matched_chunks>',
                response_text,
                re.DOTALL
            )
            reasoning_match = re.search(
                r'<reasoning>(.*?)</reasoning>',
                response_text,
                re.DOTALL
            )
            
            if not matched_chunks_match:
                LOGGER.error("  ✗ Failed to parse LLM response - returning all chunks")
                return relevant_chunks
            
            matched_chunks_str = matched_chunks_match.group(1).strip()
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
            
            if not matched_chunks_str:
                LOGGER.warning("  ⚠ No chunks matched with context")
                LOGGER.info(f"  Reasoning: {reasoning}")
                return []
            
            matched_chunk_ids = [
                chunk_id.strip()
                for chunk_id in matched_chunks_str.split(',')
                if chunk_id.strip()
            ]
            
            filtered_chunks = [
                chunk for chunk in relevant_chunks
                if chunk.chunk_id in matched_chunk_ids
            ]
            
            LOGGER.info(f"  ✓ Output: {len(filtered_chunks)} matched chunks")
            LOGGER.info(f"  Reasoning: {reasoning[:100]}..." if len(reasoning) > 100 else f"  Reasoning: {reasoning}")
            LOGGER.info("")
            
            return filtered_chunks
            
        except Exception as e:
            LOGGER.error(f"  ✗ Error in context filtering: {str(e)}")
            return relevant_chunks
    
    # --- THAY ĐỔI BẮT ĐẦU: HÀM MỚI CHO LUỒNG AGGREGATE ---
    @observe()
    async def _handle_aggregate_question(
        self,
        messages: List[Dict],
        role_ids: List[str],
        bot_id: str
    ) -> Optional[Tuple[List[ParsedChunk], ContextAnalysis]]:
        """
        Handles the flow for 'aggregate' questions.
        This flow skips the early LLM filtering to maximize the number of chunks for aggregation.
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ AGGREGATE FLOW: Extracting content for aggregation" + " " * 22 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")

        query = messages[-1]['content']

        # 1. Search all partitions
        chunk_metadata_map = await self._search_qhld_partitions(query, role_ids, bot_id)
        if not chunk_metadata_map:
            LOGGER.warning("⚠ No chunks from partition search.")
            return None

        # 2. Fetch and parse all chunks found
        all_parsed_chunks = await self._fetch_and_parse_chunks(chunk_metadata_map, role_ids, bot_id)
        if not all_parsed_chunks:
            LOGGER.warning("⚠ No valid chunks after parsing.")
            return None
        
        LOGGER.info(f"✓ Found {len(all_parsed_chunks)} total chunks for aggregation.")

        # 3. Aggregate context directly from ALL parsed chunks (NO early filtering)
        LOGGER.info("  Aggregating context from all found chunks...")
        pham_vi_set = set()
        chuyen_mon_set = set()
        kich_ban_set = set()

        for chunk in all_parsed_chunks:
            if chunk.pham_vi_vi_pham:
                pham_vi_set.add(chunk.pham_vi_vi_pham.strip())
            if chunk.chuyen_mon:
                chuyen_mon_set.add(chunk.chuyen_mon.strip())
            if chunk.kich_ban:
                kich_ban_set.add(chunk.kich_ban.strip())
        
        aggregated_context = ContextAnalysis(
            pham_vi=", ".join(sorted(list(pham_vi_set))),
            chuyen_mon=", ".join(sorted(list(chuyen_mon_set))),
            kich_ban=", ".join(sorted(list(kich_ban_set)))
        )

        return all_parsed_chunks, aggregated_context
# --- THAY ĐỔI KẾT THÚC: HÀM MỚI CHO LUỒNG AGGREGATE ---
# --- THAY ĐỔI BẮT ĐẦU: HÀM MỚI CHO LUỒNG SPECIFIC ---
    @observe()
    async def _handle_specific_question(
        self,
        messages: List[Dict],
        role_ids: List[str],
        bot_id: str
    ) -> Optional[Tuple[List[ParsedChunk], ContextAnalysis]]:
        """
        Handles the flow for 'specific' questions.
        This flow uses the multi-stage filtering process to narrow down to the most relevant chunks.
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ SPECIFIC FLOW: Multi-stage filtering for detailed answer" + " " * 15 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")

        query = messages[-1]['content']

        # 1. Search all partitions
        chunk_metadata_map = await self._search_qhld_partitions(query, role_ids, bot_id)
        if not chunk_metadata_map:
            LOGGER.warning("⚠ No chunks from partition search.")
            return None

        # 2. Fetch and parse chunks
        parsed_chunks = await self._fetch_and_parse_chunks(chunk_metadata_map, role_ids, bot_id)
        if not parsed_chunks:
            LOGGER.warning("⚠ No valid chunks after parsing.")
            return None

        # 3. LLM Filter Phase 1: Relevance
        filter_result = await self._llm_filter_relevant_chunks(query, parsed_chunks)
        if not filter_result.relevant_chunk_ids:
            LOGGER.warning("⚠ No relevant chunks after LLM relevance filter.")
            return None
        relevant_chunks = [c for c in parsed_chunks if c.chunk_id in filter_result.relevant_chunk_ids]

        # 4. LLM Analyze Context
        context, _ = await self._llm_analyze_context_from_chunks(query, relevant_chunks)

        # 5. LLM Filter by Context
        final_chunks = await self._llm_filter_by_context(context, relevant_chunks)
        if not final_chunks:
            LOGGER.warning("⚠ No chunks matched context after final filtering.")
            return None
            
        return final_chunks, context
# --- THAY ĐỔI KẾT THÚC: HÀM MỚI CHO LUỒNG SPECIFIC ---


    # ========================================================================
    # STEP 3: VERIFY DOCUMENTS
    # ========================================================================
    @observe()
    async def _verify_document(
        self,
        query: str,
        documents: List[Dict]
    ) -> VerifyResult:
        """Verify if documents match the query
        
        Args:
            query: User query
            documents: List of documents
            
        Returns:
            VerifyResult with "matched" or "unmatched"
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ STEP 3: VERIFY DOCUMENTS" + " " * 53 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")
        
        prompt = VERIFY_DOCUMENT_PROMPT_QHLD.format(
            query=query,
            documents=self._format_documents(documents=documents)
        )
        
        # LOGGER.info(f"Prompt VERIFY_DOCUMENT_PROMPT_QHLD: {prompt}")        
        LOGGER.info("Calling LLM with VERIFY_DOCUMENT_PROMPT_QHLD...")
        response_text = await self._stream_llm_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        result = parse_model(input_text=response_text, model_class=VerifyResult)
        LOGGER.info(f"✓ Verification result: {result.output}")
        LOGGER.info("")
        
        return result

    # ========================================================================
    # STEP 4: GENERATE RESPONSE
    # ========================================================================
    @observe()
    async def _flow_non_chit_chat_v2(
        self,
        query: str,
        chunks: List[ParsedChunk],
        context: ContextAnalysis,
        question_type: QuestionType
    ) -> AsyncStream[ChatCompletionChunk]:
        """Generate response for QHLD flow
        
        Args:
            query: Original query
            chunks: Final filtered chunks
            context: Determined context
            
        Yields:
            Response chunks from LLM
        """
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ STEP 4: GENERATE RESPONSE - QHLD Flow" + " " * 39 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")
        
        # Convert ParsedChunk to a readable Dict format
        docs = []
        for i, chunk in enumerate(chunks, 1):
            # Thay vì tạo chuỗi JSON, hãy tạo một chuỗi văn bản có cấu trúc, dễ đọc
            content_str = f"Tài liệu tham khảo {i}:\n"
            if chunk.chuyen_mon:
                content_str += f"- Chuyên môn: {chunk.chuyen_mon}\n"
            if chunk.pham_vi_vi_pham:
                content_str += f"- Phạm vi vi phạm: {chunk.pham_vi_vi_pham}\n"
            if chunk.kich_ban:
                content_str += f"- Kịch bản: {chunk.kich_ban}\n"
            if chunk.file_name:
                content_str += f"- Tên file: {chunk.file_name}\n"
            # Bạn có thể cân nhắc có nên đưa quy trình vào hay không, tùy thuộc vào độ dài
            content_str += f"- Quy trình: {chunk.quy_trinh}\n"
            
            doc = {
                'id': chunk.chunk_id,
                'content': content_str,  # Sử dụng chuỗi đã được định dạng
                'score': sum(chunk.partition_scores.values()) / max(len(chunk.partition_scores), 1)
            }
            docs.append(doc)
        
        LOGGER.info(f"Documents to use: {len(docs)}")
        
        # Verify documents
        verify = await self._verify_document(query=query, documents=docs)
        
        # Generate system prompt
        # 🆕 Generate system prompt dựa vào question_type
        if verify.output == 'matched':
            LOGGER.info("✓ Documents matched - generating answer")
            
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # 🆕 CHỌN PROMPT PHÙ HỢP
            if question_type.type == "aggregate":
                LOGGER.info("  Using NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE")
                system_prompt = NON_CHIT_CHAT_PROMPT_QHLD_AGGREGATE.format(
                    query=query,
                    # documents=self._format_documents(documents=docs),
                    # documents="",
                    pham_vi=context.pham_vi or "Không có",
                    chuyen_mon=context.chuyen_mon or "Không có",
                    kich_ban=context.kich_ban or "Không có"
                )
                # print("========")
                # print(system_prompt)
                # print("========")
            else:
                LOGGER.info("  Using NON_CHIT_CHAT_PROMPT_QHLD (standard)")
                system_prompt = NON_CHIT_CHAT_PROMPT_QHLD.format(
                    pham_vi=context.pham_vi if context.pham_vi else "Chưa xác định",
                    chuyen_mon=context.chuyen_mon if context.chuyen_mon else "Chưa xác định",
                    kich_ban=context.kich_ban if context.kich_ban else "Chưa xác định",
                    query=query,
                    documents=self._format_documents(documents=docs)
                )
                # print("=======")
                # print(system_prompt)
                # print("=======")
        else:
            LOGGER.info("⚠ Documents not matched - refusing with REFUSE_PROMPT_QHLD")
            
            system_prompt = REFUSE_PROMPT_QHLD.format(
                definition=self.bot_config['definition']
            )
        
        attached_docs = self._create_attached_docs(documents=docs)
        
        LOGGER.info("Streaming response...")
        LOGGER.info("")
        
        async for chunk in self._llm.run(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            docs=attached_docs
        ):
            yield chunk

    # ========================================================================
    # NORMAL FLOW (Fallback)
    # ========================================================================

    @observe()
    async def _analyze_query_intent_clarity(
        self,
        messages: List[Dict],
        query: str
    ) -> Dict:
        """Analyze query intent and clarity for normal flow"""
        LOGGER.info("  Analyzing query intent and clarity...")
        
        # Format history
        history = []
        message_pairs = []
        current_pair = []

        for msg in messages[:-1][::-1]:
            current_pair.append(msg)
            if len(current_pair) == 2:
                message_pairs.append(current_pair)
                current_pair = []
            if len(message_pairs) == 4:
                break

        for pair in reversed(message_pairs):
            history.extend(pair)

        if current_pair:
            history.extend(reversed(current_pair))

        formatted_history = [
            f"{'Người dùng' if m['role'] == 'user' else 'BOT'}: {m['content']}"
            for m in history
        ]

        system_prompt = f"""
        # Phần 1: Phân tích ý định
        {SYSTEM_PROMPT_INTENT.format(conversation=formatted_history, documents="", relevance_score=0)}

        # Phần 2: Phân tích độ rõ ràng
        {SYSTEM_PROMPT_QUERY_CLARITY}

        # Định dạng kết quả
        <query>câu tóm tắt ý định của tin nhắn mới</query>
        <intent>nhóm được phân loại</intent>
        <greeting>chatbot đã chào hỏi người dùng chưa</greeting>
        <clarity>nhãn độ rõ ràng</clarity>
        """

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Tin nhắn mới: '{query}'"}
            ]
        )

        try:
            new_query = re.findall(r'<query>(.*?)</query>', response_text)[0]
            intent = re.findall(r'<intent>(.*?)</intent>', response_text)[0]
            greeting = re.findall(r'<greeting>(.*?)</greeting>', response_text)[0].lower() == 'true'
            clarity = re.findall(r'<clarity>(.*?)</clarity>', response_text)[0]

            result = {
                "query": new_query,
                "intent": intent,
                "greeting": greeting,
                "clarity_level": clarity,
            }
            
            LOGGER.info(f"  ✓ Intent: {intent}, Clarity: {clarity}")
            
        except (IndexError, Exception) as e:
            LOGGER.error(f"  ✗ Error parsing LLM response: {str(e)}")
            result = {
                "query": query,
                "intent": "require_document",
                "greeting": False,
                "clarity_level": "unclear",
            }

        return result
    @observe()
    async def _get_documents_enhanced(
        self,
        query: str,
        intent_query: str,
        role_ids: List[str],
        topic: str
    ) -> Dict:
        """Retrieve and verify documents with detailed assessment"""
        LOGGER.info("  Retrieving documents...")
        
        retrieval_records = await self._retriever.run(
            query=intent_query or query,
            bot_id=self.bot_config['id'],
            collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
            allowed_roles=role_ids,
            top_k=self.bot_config['retrieval'].top_k,
            threshold=self.bot_config['retrieval'].threshold,
        )

        if not retrieval_records:
            LOGGER.info("  ⚠ No documents retrieved")
            return {
                "docs": [],
                "relevance_score": 0.0,
                "fully_answered": False,
                "partially_answered": False,
                "answered_info": "",
                "missing_info": ""
            }

        LOGGER.info(f"  ✓ Retrieved {len(retrieval_records)} documents")
        
        # Reranking
        LOGGER.info("  Reranking documents...")
        reranked_results = await self._reranker.run(
            query=query,
            texts=[r['content'] for r in retrieval_records],
            top_k=self.bot_config['reranking'].top_k,
            threshold=self.bot_config['reranking'].threshold,
        )

        documents_to_verify = []
        for r in reranked_results:
            record = retrieval_records[r['index']]
            record['score'] = r['score']
            documents_to_verify.append(record)

        if not documents_to_verify:
            LOGGER.info("  ⚠ No documents after reranking")
            return {
                "docs": [],
                "relevance_score": 0.0,
                "fully_answered": False,
                "partially_answered": False,
                "answered_info": "",
                "missing_info": ""
            }

        LOGGER.info(f"  ✓ {len(documents_to_verify)} documents after reranking")
        
        # Verify documents
        LOGGER.info("  Verifying documents...")
        verification_results = await self._verify_documents_batch_enhanced(
            query=query,
            intent_query=intent_query or query,
            documents=documents_to_verify
        )

        final_docs = []
        max_score = 0
        fully_answered = False
        partially_answered = False
        answered_info = ""
        missing_info = ""

        for idx, result in enumerate(verification_results):
            if result["relevant"]:
                record = documents_to_verify[idx]
                record.update({
                    "fully_answered": result["fully_answered"],
                    "partially_answered": result["partially_answered"],
                    "answered_info": result["answered_info"],
                    "missing_info": result["missing_info"]
                })
                final_docs.append(record)
                max_score = max(max_score, record['score'])

                if result["fully_answered"]:
                    fully_answered = True
                    answered_info = result["answered_info"]
                elif result["partially_answered"] and not fully_answered:
                    partially_answered = True
                    answered_info = result["answered_info"]
                    missing_info = result["missing_info"]

        LOGGER.info(f"  ✓ {len(final_docs)} relevant documents after verification")
        
        return {
            "docs": final_docs,
            "relevance_score": max_score,
            "fully_answered": fully_answered,
            "partially_answered": partially_answered,
            "answered_info": answered_info,
            "missing_info": missing_info
        }

    @observe()
    async def _verify_documents_batch_enhanced(
        self,
        query: str,
        intent_query: str,
        documents: List[Dict]
    ) -> List[Dict]:
        """Verify multiple documents in one LLM call"""
        if not documents:
            return []

        verification_prompt = SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED
        formatted_docs = []
        for idx, doc in enumerate(documents, 1):
            formatted_docs.append(f"Document {idx}:\n{doc['content']}")

        all_docs = "\n\n".join(formatted_docs)

        messages = [
            {"role": "system", "content": verification_prompt},
            {"role": "user",
             "content": f"Câu hỏi gốc: {query}\nCâu tóm tắt ý định: {intent_query}\n\n"
                        f"Tài liệu để đánh giá:\n{all_docs}\n\n"
                        "Yêu cầu: Đánh giá từng tài liệu và trả về kết quả theo định dạng "
                        "<output>doc1:tra_loi_day_du/tra_loi_mot_phan/khong_lien_quan|doc2:...</output>"}
        ]

        response_text = await self._stream_llm_response(messages)

        match_output = re.search(r'<output>(.*?)</output>', response_text)
        match_answered = re.search(r'<answered_info>(.*?)</answered_info>', response_text)
        match_missing = re.search(r'<missing_info>(.*?)</missing_info>', response_text)

        if not match_output:
            return [{"relevant": False, "answered_info": "", "missing_info": ""} for _ in documents]

        results = match_output.group(1).strip().split('|')

        detailed_results = []
        for idx, result in enumerate(results):
            doc_result = {
                "relevant": False,
                "fully_answered": False,
                "partially_answered": False,
                "answered_info": match_answered.group(1).strip() if match_answered else "",
                "missing_info": match_missing.group(1).strip() if match_missing else ""
            }

            status = result.split(':')[1].strip()
            if status == "tra_loi_day_du":
                doc_result["relevant"] = True
                doc_result["fully_answered"] = True
            elif status == "tra_loi_mot_phan":
                doc_result["relevant"] = True
                doc_result["partially_answered"] = True

            detailed_results.append(doc_result)

        return detailed_results
    
    @observe()
    async def _check_temporal_relevance(self, query: str, documents: List[Dict]) -> bool:
        """Check temporal information in documents"""
        if not documents:
            return False

        year_match = re.findall(r'\b(202\d|203\d)\b', query)
        if not year_match:
            return True

        year_in_query = year_match[0]
        docs_text = self._format_documents(documents)

        prompt = f"""
        Vai trò: Chuyên gia phân tích thông tin thời gian

        Nhiệm vụ: Kiểm tra xem tài liệu có chứa thông tin về năm {year_in_query} không.

        Tài liệu:
        {docs_text}

        Yêu cầu: Chỉ trả lời "co_thong_tin" hoặc "khong_co_thong_tin"
        """

        response = await self._stream_llm_response([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Câu hỏi: {query}"}
        ])

        return "co_thong_tin" in response.lower()
    @observe()
    async def _generate_clarification_prompt(self, query: str, doc_result: DocumentResult) -> str:
        """Generate clarification prompt by analyzing documents"""
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_RELEVANCE_TOPIC},
                {"role": "user",
                 "content": f"Câu hỏi: {query}\nTài liệu cung cấp: {self._format_documents(doc_result.docs)}"}
            ]

            response = await self._stream_llm_response(messages)
            match = re.search(r'<topics>(.*?)</topics>', response)
            topics = match.group(1).split('|') if match else []

            if topics:
                topics_text = ", ".join(topics[:-1])
                if len(topics) > 1:
                    topics_text += f" hoặc {topics[-1]}"
                else:
                    topics_text = topics[0]

                return f"Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔\n" \
                       f"Bạn muốn tìm hiểu thông tin về một trong những chủ đề sau: {topics_text} đúng không?"

            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"
        except Exception as e:
            LOGGER.error(f"Error generating clarification: {str(e)}")
            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"
        
    @observe()
    async def _flow_normal_integration(
        self,
        messages: List[Dict],
        role_ids: List[str],
        topic: str = "default"
    ) -> AsyncStream[ChatCompletionChunk]:
        """Normal flow integration (fallback when no QHLD content)"""
        LOGGER.info("┌" + "─" * 78 + "┐")
        LOGGER.info("│ NORMAL FLOW - Integrated from Happy Hub" + " " * 37 + "│")
        LOGGER.info("└" + "─" * 78 + "┘")
        
        query = messages[-1]['content']
        LOGGER.info(f"Query: {query}")
        
        # Analyze intent and clarity
        analysis_result = await self._analyze_query_intent_clarity(messages, query)
        intent_query = analysis_result.get('query', query)

        # Retrieve documents
        doc_result = await self._get_documents_enhanced(
            query=query,
            intent_query=intent_query,
            role_ids=role_ids,
            topic=topic
        )

        # Determine response strategy
        if analysis_result['intent'] == "is_simple_chit_chat":
            LOGGER.info("Strategy: Simple chit-chat")
            prompt_system = SYSTEM_PROMPT_CHIT_CHAT.format(
                documents="",
                greeting=analysis_result['greeting']
            )
        else:
            if doc_result['docs'] and doc_result['relevance_score'] > self.bot_config.get('threshold', {}).get('doc_relevance', 0.01):
                if doc_result['fully_answered'] and analysis_result['clarity_level'] == "complete":
                    has_time_info = True
                    if re.findall(r'\b(202\d|203\d)\b', query):
                        has_time_info = await self._check_temporal_relevance(query, doc_result['docs'])

                    if has_time_info:
                        LOGGER.info("Strategy: Full answer with documents")
                        prompt_system = SYSTEM_PROMPT_NON_CHIT_CHAT.format(
                            date=datetime.now().strftime('%Y-%m-%d'),
                            documents=self._format_documents(doc_result['docs']),
                            greeting=analysis_result['greeting']
                        )
                    else:
                        LOGGER.info("Strategy: Refuse - missing temporal info")
                        prompt_system = SYSTEM_PROMPT_REFUSE

                elif doc_result['partially_answered']:
                    LOGGER.info("Strategy: Partial answer")
                    prompt_system = SYSTEM_PROMPT_PARTIAL_ANSWER.format(
                        date=datetime.now().strftime('%Y-%m-%d'),
                        documents=self._format_documents(doc_result['docs']),
                        greeting=analysis_result['greeting'],
                        answered_info=doc_result['answered_info'],
                        missing_info=doc_result['missing_info']
                    )

                elif analysis_result['clarity_level'] != "complete":
                    LOGGER.info("Strategy: Clarification needed")
                    clarification = await self._generate_clarification_prompt(
                        query,
                        DocumentResult(docs=doc_result['docs'], relevance_score=doc_result['relevance_score'])
                    )
                    prompt_system = f"""
                        Vai trò: Bạn là Bee Hi - trợ lý ảo thông minh của ngân hàng MB
                        Đưa ra nguyên văn câu trả lời sau:
                        {clarification}
                    """
                else:
                    LOGGER.info("Strategy: Refuse - insufficient info")
                    prompt_system = SYSTEM_PROMPT_REFUSE
            else:
                LOGGER.info("Strategy: Refuse - no relevant documents")
                prompt_system = SYSTEM_PROMPT_REFUSE

        response_messages = [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": query}
        ]

        attached_docs = self._create_attached_docs(doc_result['docs'])
        
        LOGGER.info("Streaming response...")
        LOGGER.info("")
        
        async for chunk in self._llm.run(
            messages=response_messages,
            docs=attached_docs
        ):
            yield chunk

    # ========================================================================
    # MAIN RUN METHOD
    # ========================================================================

    # --- THAY ĐỔI BẮT ĐẦU: SỬA ĐỔI HÀM RUN ---
    @observe(name=langfuse_app_name)
    async def run(
        self,
        messages: List[Dict],
        role_ids: Optional[List[str]] = None,
        topic: str = "default",
        **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:
        """
        Main entry point for bot conversation.
        Refactored to classify question type first and dispatch to the correct handler.
        """
        langfuse_context.update_current_trace(name=langfuse_app_name, session_id=langfuse_session_id)
        LOGGER.info("\n" + "=" * 80)
        LOGGER.info("BeeHi QHLD BOT - CONVERSATION START")
        LOGGER.info("=" * 80)

        if role_ids is None:
            role_ids = []

        LOGGER.info(f"Role IDs: {role_ids}")
        LOGGER.info(f"Topic: {topic}\n")

        # Fallback to normal flow if user is not L2
        if "L2" not in role_ids:
            LOGGER.info("→ Not L2 role → Using NORMAL FLOW")
            async for chunk in self._flow_normal_integration(
                messages=messages, role_ids=role_ids
            ):
                yield chunk
            return

        LOGGER.info("→ L2 role detected → Starting QHLD FLOW")

        # STEP 1: Expand abbreviations
        input_query = await self._generate_intent(messages=messages)

        # STEP 2: Classify question type EARLY
        question_type = await self._classify_question_type(query=input_query.query)

        # STEP 3: Dispatch to the appropriate handler based on question type
        result = None
        if question_type.type == "aggregate":
            LOGGER.info("→ Dispatching to AGGREGATE handler")
            result = await self._handle_aggregate_question(
                messages=messages,
                role_ids=role_ids,
                bot_id=self.bot_config['id']
            )
        else: # "specific"
            LOGGER.info("→ Dispatching to SPECIFIC handler")
            result = await self._handle_specific_question(
                messages=messages,
                role_ids=role_ids,
                bot_id=self.bot_config['id']
            )

        # STEP 4: Process the result from the handler
        if result is None:
            LOGGER.info("→ No QHLD content found from handler → Fallback to NORMAL FLOW")
            async for chunk in self._flow_normal_integration(
                messages=messages, role_ids=role_ids
            ):
                yield chunk
        else:
            final_chunks, context = result
            LOGGER.info(f"→ QHLD content found: {len(final_chunks)} chunks")
            LOGGER.info(f"  Context: pham_vi={context.pham_vi}, chuyen_mon={context.chuyen_mon}, kich_ban={context.kich_ban}\n")

            # STEP 5: Generate final response
            async for chunk in self._flow_non_chit_chat_v2(
                query=input_query.query,
                chunks=final_chunks,
                context=context,
                question_type=question_type
            ):
                yield chunk

        LOGGER.info("=" * 80)
        LOGGER.info("BeeHi QHLD BOT - CONVERSATION END")
        LOGGER.info("=" * 80)
# --- THAY ĐỔI KẾT THÚC: SỬA ĐỔI HÀM RUN ---



# ============================================================================
# MAIN FUNCTION FOR TESTING
# ============================================================================

async def main():
    """Test function for BeeHi_QHLD bot"""
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig

    bot_id = "5d816aa9-a21c-4f02-92bf-a28d09aa0ef9"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = BeeHi_QHLD(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )

    async for chunk in bot.run(
        messages=[
            {"role": "user", "content": "Phạm vi vi phạm đối với chuyên môn Người lao động đơn phương chấm dứt HĐLĐ là?"},
        ],
        role_ids=["L1","L2"],
        topic="default"
    ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                response_text = chunk.choices[0].delta.content
                print(response_text, end="")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())