from beegenerate.configs import MongoConfig
from typing import Dict, List, Optional
import json
from .mongodb import MongoStorage

from beegenerate.loggings import LOGGER


class StorePC(MongoStorage):
    
    def __init__(
        self, 
        config: Optional[MongoConfig] = None
    ) -> None:
        super().__init__(config)
    
    def find_document_chunks(
        self,
        chunk_ids: List[str],
        collection_name: str = "dialogue"
    ) -> List[Dict]:
        r"""Retrieves document chunks and their metadata from MongoDB based on Milvus chunk IDs.

        Args:
            chunk_ids: List of chunk identifiers from Milvus.

        Returns:
            A dictionary mapping chunk IDs to their corresponding content and metadata.
        """
                
        # 1. find the chunks by input ids list
        chunks = self.find(
            collection_name=collection_name,
            query={
                "_id": {
                    "$in": chunk_ids
                }
            }
        )
                
        # 2. Mongo result did not keep the ids ordering, reorder them
        # Create a mapping of chunk_id to document
        chunk_map = {chunk['_id']: chunk for chunk in chunks}
        
        # Append documents in original order
        result = []        
        for _id in chunk_ids:
            if _id in chunk_map:
                chunk = chunk_map[_id]
                result.append({
                    'id': chunk['_id'],
                    'question': chunk['questions'][0]['text'],
                    'answer': chunk['answers'][0]['text']
                })
                        
        return result
        
def main():    
    doc_store = StorePC(
        config=MongoConfig.default()
    )
    
    chunks = doc_store.find_document_chunks(
        chunk_ids=[
            '5e1bd305-6c0c-4dba-b4b3-56d396fa0893'
        ]
    )
    
    for chunk in chunks:
        print(json.dumps(chunk, indent=2, ensure_ascii=False))
        

if __name__ == "__main__":
    main()