import bm25s
import numpy as np
import asyncio

from typing import List, Dict, Any, Optional

class BM25Search:
    """Use BM25 to search similarity documents

    Args:
        corpus (List[dict]): BM25 use corpus to create vocab
        path_stopword (str): List stopword of Vietnamese
        lowercase (Bool): if true, lower text before tokenzer

    """
    def __init__(
        self,
        corpus: List[dict]=None,
        path_stopword: str="external/data/stopword.txt",
        lowercase: bool=True
    ) -> None:
        
        with open(path_stopword, 'r', encoding='utf-8') as f:
            stopwords = f.read().strip().split('\n')

        if corpus:
            self.corpus = corpus
            self.stopwords= stopwords
            self.lowercase = lowercase

            self.corpus_text = self._get_corpus_text()
            self.model_bm25 = self._create_model_bm25()
        else:
            self.stopwords= stopwords
            self.lowercase = lowercase
            self.model_bm25 = bm25s.BM25()
        
    
    def _get_corpus_text(self):
        if self.lowercase: 
            texts = [item['text'].lower() for item in self.corpus]
        else:
            texts = [item['text'] for item in self.corpus]
        
        return texts
    
    def _create_model_bm25(self):
        # Tokeinze corpus
        corpus_tokens = bm25s.tokenize(self.corpus_text, stopwords=self.stopwords)
        
        # Init model
        model_bm25 = bm25s.BM25(corpus=self.corpus)
        model_bm25.index(corpus_tokens)
        
        return model_bm25
    
    def save_model_bm25(
        self, 
        path='models/model_bm25s'
    ) -> None:
        self.model_bm25.save(path)
    
    def load_model_bm25(
        self, 
        path='models/model_bm25s', 
        load_corpus=True
    ) -> None:
        self.model_bm25 = bm25s.BM25.load(path, load_corpus=load_corpus)
    
    def _search(
        self, 
        query: str, 
        top_k: int
    ):
        """ Search documents similar to the query
            
            Args:
                query (str): question of user
                top_k (int): number of potential documents returned
            
            Return:
                List[str]: List of chunk ids
        """
        if self.lowercase:
            query_tokens = bm25s.tokenize(query.lower(), stopwords=self.stopwords)
        else:
            query_tokens = bm25s.tokenize(query, stopwords=self.stopwords)
        
        results, scores = self.model_bm25.retrieve(query_tokens, k=top_k)
        results, scores = results[0], scores[0]
        
        responses = [item['metadata']['chunk_id'] for item in results]
    
        return responses
    

    async def run(
        self, 
        query: str, 
        top_k: int):
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._search(query, top_k),
        )