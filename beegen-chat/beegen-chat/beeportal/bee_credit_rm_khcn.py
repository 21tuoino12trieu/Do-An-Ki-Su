import asyncio
from typing import Dict, List
from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from langfuse.decorators import langfuse_context, observe
import pandas as pd

from beegenerate.llms.llm_executor import LLMExecutor
from beegenerate.prompts.bee_credit_rm import TEMPLATE_RAG_PROMPT
from beegenerate.reranks.rerank_factory import RerankingFactory
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.storage.mongo.bot_store import BotStore
from beegenerate.storage.mongo.document_store import DocumentStore
from beegenerate.utils.common import transform_bot_id

from beegenerate.vectordb.milvus import MilvusStorage


class BeeCreditRM:
    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
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

        self.abbr_dict = self._load_abbreviation()
    
    def _load_abbreviation(self):
        """Load abbreviation"""
        abb_df = pd.read_csv(r'beeportal/bot_bee247/bee247/abbreviations.csv', encoding="utf-8-sig")
        abb_df["Abbreviation"] = abb_df["Abbreviation"].str.lower()
        abb_dict = dict(zip(abb_df["Abbreviation"], abb_df["Meaning"]))
        return abb_dict
    
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
            bot_id: str,
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
            bot_id=bot_id,
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
        
    @observe(name="BotCreditRM")
    async def run(
        self,
        messages: List[Dict], **kwargs
    ):
        langfuse_context.update_current_trace(name="BotCreditRM")
        original_query = messages[-1]['content'].strip()
        annotated_query = self.annotate_query(query=original_query)
        
        retrieval_tasks = [
            self._fetch_and_rank(
                bot_id=self.bot_config['id'],
                query=annotated_query,
                collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                retrieval_top_k=15,
                rerank_top_k=5,
                partition_names=['document']
            )
        ]

        # Execute all search requests concurrently
        document_records = await asyncio.gather(*retrieval_tasks)
        document_records = document_records[0]
        print(f"retrieval_result: {document_records}")
        documents = self._format_documents(
            documents=document_records
        )
        print(f"documents: {documents}")
        system_prompt = TEMPLATE_RAG_PROMPT.format(
            question=annotated_query,
            documents=documents
        )
        
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": annotated_query}
                ],
                docs=document_records
        ):
            yield chunk

async def main():
    from beeportal.beegen_bot_v2 import Bot
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig

    bot_id = "e3101ae4-a9be-4af6-9f9a-c97ec94e1ce0"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BeeCreditRM(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )

    async for chunk in bot.run(
            messages=[
                {"role": "user", "content": "BM41.1_Hop dong cam co vang"},
            ]    ,
            role_ids=["L1", "L2", "L3"]
        ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                response_text = chunk.choices[0].delta.content
                print(response_text, end="")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

    