import asyncio 
from typing import List, Dict, Any, Union, Optional
from wsgiref.util import application_uri

from mem0.reranker.base import BaseReranker
from mem0.utils.factory import LlmFactory
from mem0.configs.rerankers.base import BaseRerankerConfig

from beegen.reranks.vllm_reranker import VLLMReranker as BeegenVLLMReranker 
from beegen.configs import RerankingConfig as BeegenRerankConfig 

class VLLMReranker(BaseReranker):
    """
    An ASYNCHRONOUS mem0-compatible wrapper that uses the existing
    `beegen.reranks.vllm_reranker.VLLMReranker` client.
    """
    def __init__(self, config: Optional[BaseRerankerConfig] = None):
        # super().__init__(config) 
        self.config = config 
        model = self.config.model 
        base_url = self.config.base_url 
        api_key = self.config.api_key 
        self.top_k = self.config.top_k


        beegen_config = BeegenRerankConfig(
            api_key = api_key,
            base_url = base_url, 
            model = model, 
        )

        self.client = BeegenVLLMReranker(config= beegen_config)

    def rerank(self, query: str, documents: List) -> List[Dict[str, Any]]:
        # print(f"Original_memories: {documents}")

        is_dict= False
        if not documents: 
            return {"reranks": []}
        elif isinstance(documents[0], str):
            texts = documents
        elif isinstance(documents[0], dict):
            is_dict = True
            texts = [doc.get('memory', '') for doc in documents]
        else: 
            raise TypeError(f"Expected documents to be List[str] or List[Dict], got list of {type(documents[0]).__name__}")


        # Since this sync method is called from a thread without a running
        # event loop (via asyncio.to_thread), we can use asyncio.run().
        results = asyncio.run(self.client.run(query= query, texts= texts, top_k=self.top_k))

        reranked_docs = []
        
        for r in results:
            if is_dict:   
                reranked_docs.append({
                    **documents[r['index']],
                    "score": r['score']
                })
            else:
                reranked_docs.append({
                    "content": documents[r['index']],
                    "score": r['score']
                })
             
        return {
            "reranks": reranked_docs
        }