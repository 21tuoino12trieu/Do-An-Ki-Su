from beegenerate.prompts.beegen_common import (
    CHIT_CHAT_PROMPT,
    VERIFY_DOCUMENT_PROMPT,
    NON_CHIT_CHAT_PROMPT,
    REFUSE_PROMPT
)
import asyncio

from pydantic import BaseModel
import yaml

from beegenerate.prompts.beerm import RM_VERIFY_DOCUMENT_PROMPT, REWRITE_AND_CLASSIFY_PROMPT
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.llms.llm_executor import LLMExecutor

from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from typing import (
    List,
    Dict,
    Tuple,
    Any,
    TypeVar,
    Type
)

from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from langfuse.decorators import observe, langfuse_context

# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)


class InputQuery(BaseModel):
    query: str
    intent: str


class VerifyResult(BaseModel):
    output: str


def parse_model(
        input_text: str,
        model_class: Type[T]
) -> T:
    """
    Parse input text into a specified Pydantic model.
    
    Args:
        input_text: Input string in a format similar to YAML
        model_class: The Pydantic model class to parse into
        
    Returns:
        An instance of the specified model class
        
    Raises:
        ValueError: If parsing or validation fails
    """
    # Remove ```yaml``` markers if present
    cleaned_text = input_text
    if "```yaml" in input_text:
        # Split by ```yaml and ``` and take the content in between
        parts = input_text.split("```yaml")
        if len(parts) > 1:
            cleaned_text = parts[1].split("```")[0].strip()

    # Parse YAML
    try:
        data = yaml.safe_load(cleaned_text)
        if not data:
            raise ValueError("Empty or invalid YAML content")

        # Validate and create specified Pydantic model
        return model_class(**data)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format: {e}")
    except Exception as e:
        raise ValueError(f"Validation error: {e}")


class BotRM:
    """A chatbot class that handles conversations using LLM, document retrieval, and reranking.
    
    This class implements a complete conversation flow including:
    - Intent classification
    - Document retrieval and reranking
    - Handling both casual (chitchat) and information-seeking conversations
    - Role-based access control for documents
    
    Attributes:
        bot_id (str): Unique identifier for the bot instance
        bot_store (MongoStorage): Storage for bot configurations and metadata
        bot_config (Dict[str, Any]): Bot-specific configuration settings
        _llm (LLMExecutor): Language model execution handler
        _retriever (VectorRetriever): Document retrieval component
        _reranker (RerankingFactory): Document reranking component
    """

    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize the Bot instance with necessary components.
        
        Args:
            bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
            vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
            doc_store (DocumentStore): Document storage instance for retrieving and managing content
            bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive
        """
        self.bot_config = bot_config

        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )

        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )

        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])

    @observe()
    def _format_documents(
            self,
            documents: List[Dict]
    ) -> str:
        """Format a list of documents into a single string with separators.
        
        Args:
            documents: List of document dictionaries, each containing a 'content' field
            
        Returns:
            String containing all document contents separated by [SEP] tokens
        """
        documents_text = "\n[SEP]\n".join([d['content'] for d in documents])
        return documents_text

    @observe()
    def _create_attached_docs(
            self,
            documents: List[Dict]
    ) -> List[Dict]:
        """Create metadata for documents to be attached to LLM requests.
        
        Args:
            documents: List of document dictionaries containing 'id' and optional 'doc' fields
            
        Returns:
            List of dictionaries containing document metadata (id and source)
        """
        attached_docs = []
        for r in documents:
            chunk_info = {
                "id": r['id'],
            }
            if 'doc' in r:
                chunk_info['source'] = r['doc']

            attached_docs.append(chunk_info)
        return attached_docs

    @observe()
    async def _stream_llm_response(
            self,
            messages: List[Dict]
    ) -> str:
        """Stream response from LLM and concatenate chunks into a single string.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' fields
            
        Returns:
            Concatenated response string from the LLM
            
        Raises:
            RuntimeError: If LLM streaming fails
        """
        try:
            response_text = ""
            async for chunk in self._llm.run(messages=messages):
                if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    response_text += str(chunk.choices[0].delta.content)
            return response_text
        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            langfuse_context.update_current_observation(level="ERROR", output=str(e))
            raise RuntimeError(f"Failed to get LLM response: {str(e)}")

    @observe()
    async def _generate_intent(
            self,
            messages: List[Dict],
    ) -> InputQuery:
        """Determine the intent of the user's latest message.
        
        Uses conversation history and LLM to:
        1. Rewrite the query for better understanding
        2. Classify the intent as chitchat or non-chitchat
        
        Args:
            messages: List of conversation messages, each with 'role' and 'content'
            
        Returns:
            InputQuery object containing rewritten query and classified intent
            
        Raises:
            ValueError: If query parsing fails
        """

        # 1. get the user latest message and chat history 
        query = messages[-1]['content']
        _history = [
            f"Người dùng: {m['content']}"
            if m['role'] == 'user'
            else f"BOT: {m['content']}"
            for m in messages[-6:-1]
        ]
        # 2. Rewrite the conversation and classify the intent of user
        _prompt = REWRITE_AND_CLASSIFY_PROMPT.format(
            definition=self.bot_config['definition'],
            conversation=_history,
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt + '/no_think'}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=InputQuery
        )

    @observe()
    async def _retrieval_and_rerank(
            self,
            input_query: InputQuery,
            role_ids: List[str] = [],
            topic: str = "default",
            valid_score: float = 0.5
    ) -> List[Dict]:
        """Retrieve and rerank documents based on query and role hierarchy.
        
        Performs two-stage search:
        1. Initial retrieval using vector similarity
        2. Reranking of retrieved documents
        
        Args:
            input_query: Query object containing search text
            role: Role level for filtering documents ("L1", "L2", "L3")
            topic: Topic category for filtering
            valid_score: Minimum score threshold for valid documents
            
        Returns:
            Dictionary containing:
                - 'docs': List of ranked documents
                - 'intent': Classified intent based on document relevance
                
        Note:
            Returns empty doc list if no documents score above valid_score
        """

        # 2. retrieve the relevan records by vector search
        retrieval_records = await self._retriever.run(
            query=input_query.query,
            bot_id=self.bot_config['id'],
            collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
            allowed_roles=role_ids,
            top_k=self \
                .bot_config['retrieval'] \
                .top_k,
            threshold=self \
                .bot_config['retrieval'] \
                .threshold
            # expr = " || ".join([f'role == "{r}"' for r in roles])
        )

        # 3. rerank the retrieval results
        reranked_results = await self._reranker.run(
            query=input_query.query,
            texts=[r['content'] for r in retrieval_records],
            top_k=self \
                .bot_config['reranking'] \
                .top_k,
            threshold=self \
                .bot_config['reranking'] \
                .threshold,
        )

        # 4. construct the final documents
        final_docs = []
        valid_count = 0
        for r in reranked_results:
            record = retrieval_records[r['index']]
            record['score'] = r['score']
            if record['score'] > valid_score:
                valid_count += 1
            final_docs.append(record)

        # 5. return dict
        return {
            'docs': final_docs,
            'intent': 'chitchat' if valid_count == 0 else 'non_chitchat'
        }

    @observe()
    async def _flow_chit_chat(
            self,
            query: str,
            docs: List[Dict]
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """Handle casual conversation flow.
        
        Args:
            query: User's input message
            docs: List of relevant documents for context
            
        Returns:
            Stream of response chunks from LLM
            
        Note:
            Uses casual conversation prompt template
        """
        # 1. create chitchat prompt
        system_prompt = CHIT_CHAT_PROMPT.format(
            definition=self.bot_config['definition']
        )

        # 2. create attached docs for output return (FE)
        attached_docs = self._create_attached_docs(
            documents=docs
        )

        # 3. create streaming response
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query + '/no_think'}
                ],
                docs=attached_docs
        ):
            yield chunk

    @observe()
    async def _verify_document(
            self,
            query: str,
            documents: List[Dict]
    ) -> VerifyResult:
        """Verify if retrieved documents match the user's query.
        
        Args:
            query: User's input query
            documents: List of retrieved documents to verify
            
        Returns:
            VerifyResult object indicating if documents match query
        """
        _prompt = VERIFY_DOCUMENT_PROMPT.format(
            query=query,
            documents=self._format_documents(
                documents=documents
            )
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt + '/no_think'}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=VerifyResult
        )

    @observe()
    async def _verify_document_logic(
            self,
            query: str,
            documents: List[Dict]
    ) -> VerifyResult:
        """Verify if retrieved documents match the user's query.
        
        Args:
            query: User's input query
            documents: List of retrieved documents to verify
            
        Returns:
            VerifyResult object indicating if documents match query
        """
        _prompt = RM_VERIFY_DOCUMENT_PROMPT.format(
            query=query,
            documents=self._format_documents(
                documents=documents
            )
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt + '/no_think'}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=VerifyResult
        )

    @observe()
    async def _flow_non_chit_chat(
            self,
            query: str,
            docs: List[Dict]
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """Handle information-seeking conversation flow.
        
        Args:
            query: User's input query
            docs: List of relevant documents
            
        Returns:
            Stream of response chunks from LLM
            
        Note:
            Verifies document relevance before generating response
        """
        # 1. verify the relevant of documents
        task_verify = asyncio.create_task(
            self._verify_document(query=query, documents=docs)
        )
        task_verify_logic = asyncio.create_task(
            self._verify_document_logic(query=query, documents=docs)
        )

        verify = await task_verify
        verify_logic = await task_verify_logic

        # 2. decide the flow matched/unmatched
        if verify.output == 'matched':
            current_date = datetime.now().strftime('%Y-%m-%d')

            system_prompt = NON_CHIT_CHAT_PROMPT.format(
                date=current_date,
                definition=self.bot_config['definition'],
                query=query,
                documents=self._format_documents(
                    documents=docs
                )
            )
        else:
            if verify_logic.output == 'matched':
                current_date = datetime.now().strftime('%Y-%m-%d')

                system_prompt = NON_CHIT_CHAT_PROMPT.format(
                    date=current_date,
                    definition=self.bot_config['definition'],
                    query=query,
                    documents=self._format_documents(
                        documents=docs
                    )
                )
            else:
                system_prompt = REFUSE_PROMPT.format(
                    definition=self.bot_config['definition']
                )

        # 3. create attached docs to return in bot results (for FE)
        attached_docs = self._create_attached_docs(
            documents=docs
        )

        # 4. create streaming response
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query + '/no_think'}
                ],
                docs=attached_docs
        ):
            yield chunk

    @observe(name="BotRM")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            topic: str = "default",
            **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        langfuse_context.update_current_trace(name="BotRM")
        # 1. rewrite the whole conversation into a query and classify the intent -> chitchat / non-chitchat
        input_query = await self._generate_intent(
            messages=messages
        )

        # 2. retrieval + rerank the relevant docs from db, 
        # it is also classify the relevant of documents based on threshold valid_score
        retrieval_result = await self._retrieval_and_rerank(
            input_query=input_query,
            role_ids=role_ids,
            topic=topic,
            valid_score=0.5
        )

        # 3. decide the flow chitchat or not based on the ensemble decide of both llm (from 1.) and rerank (from 2.)
        is_casual = (retrieval_result['intent'] == "chitchat") \
                    & (input_query.intent == "chit_chat")

        # 4. decide the flow, return streaming response
        if is_casual:
            async for chunk in self._flow_chit_chat(
                    query=input_query.query,
                    docs=retrieval_result['docs']
            ):
                yield chunk
        else:
            async for chunk in self._flow_non_chit_chat(
                    query=input_query.query,
                    docs=retrieval_result['docs']
            ):
                yield chunk

@observe(name ="BotRM")
async def main():
    from beeportal.beegen_bot_v2 import Bot
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig

    # bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_id = "269c75a7-b3dc-4a34-ae6f-a337ad7e8d34"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BotRM(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )

    async for chunk in bot.run(
            messages=[
                {"role": "user",
                 "content": "Đối tượng được nhà nước giao đất, có thu tiền sử dụng đất hàng năm có được sủ dụng quyền sử dụng đất và tài sản gắn liền với đất làm tài sản đảm bảo không"},
            ],
            role_ids=["L1"],
            topic="default"
    ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                response_text = chunk.choices[0].delta.content
                print(response_text, end="")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
