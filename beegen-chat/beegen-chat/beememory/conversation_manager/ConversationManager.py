from beememory.prompt import MAIN_INPUT_PROMPT
from beememory.constant import db, milvus_client, embedding_model
from beememory.conversation_manager.handler_response import HandlerResponse

import random
import time
from typing import Callable, List, Dict, Any, AsyncGenerator, Optional
from datetime import datetime, timedelta
import threading
import queue
import asyncio
from dataclasses import dataclass
from enum import Enum
    
class ResponseGenerator:
    def __init__(self, model, db, get_chat_history):
        self.model = model
        self.get_chat_history = get_chat_history

    async def generate_response(self, user_id: str, query: str, sys_prompt: str) -> AsyncGenerator[str, None]:
        HISTORY = self.get_chat_history(user_id, top_n = 6)
        MEMORY_SUMMARY = db.get_summary_memory(user_id = user_id)
        CORE_MEMORY = db.get_core_memory(user_id=user_id)
        
        query_embedding = await embedding_model.run(texts=[query])
        
        #TODO: milvus
        archived_mem_embed = milvus_client.search_by_user_id(
            query_embeddings=query_embedding[0],
            user_id=user_id,
            suffix="archived",
            top_n=2
        )
        # archived_mem_embed = []
        
        ARCHIVED_MEMORY = str(archived_mem_embed)
        
        if len(HISTORY) == 0:
            history_string = "The history is empty. You must reply to the user's message"
        else:
            history_string = ""
            for entry in HISTORY:
                if entry["role"] == "user":
                    history_string += f"<User's chat>{entry['content'].strip()}</User's chat>\n"
                elif entry["role"] == "assistant":
                    history_string += f"<Your chat>{entry['content'].strip()}</Your chat>\n"
                
        prompt = f"{sys_prompt}\n\n{MAIN_INPUT_PROMPT}"
        prompt = prompt.format(message=query, 
                               history=history_string, 
                               summary = MEMORY_SUMMARY,
                               core_memory = CORE_MEMORY,
                               archived_memory = ARCHIVED_MEMORY)
        
        # print("PROMPT:")
        # print(prompt)
        # messages = [{"role": "user", "content": prompt}]
        
        
        
        
        response = ""
        async for chunk in HandlerResponse.handle_async_final_response(self.model.run, 
                                                            temperature=0.01, 
                                                            messages=[{'role': 'user', 'content': prompt}]):
            response = response + "\n" + chunk
            # print("CHUNKG:", chunk)
            yield chunk + "\n"
            await asyncio.sleep(0.001)
        
        
    
    def add_message(self, user_id, role, content):
        self.db.add_message(user_id=user_id, role=role, content=content)


