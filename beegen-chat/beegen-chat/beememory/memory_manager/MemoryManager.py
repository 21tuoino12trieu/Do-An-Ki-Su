from beememory.constant import db
from beememory.prompt import RECURSIVE_SUMMARY_PROMPT, EXTRACT_MEMORY
from beememory.memory_manager.utils import *

import requests
from typing import Union, List
import json
import re
import numpy as np
import asyncio
from datetime import datetime

class MemoryManager:
    message_queue_url = "http://localhost:8002"


    SUMMARY_FLAG = "summary"
    CORE_FLAG = "core"
    
    ALL_FLAGS = [SUMMARY_FLAG, CORE_FLAG]
    
    @staticmethod
    def add_message(user_id: str, content: str, role: str, flag: Union[str, List[str]] = ""):
        if flag == "":
            flag = MemoryManager.ALL_FLAGS
            
        flags = [flag] if isinstance(flag, str) else flag
        
        if not flags or not all(isinstance(f, str) and f.strip() for f in flags):
            raise ValueError("Invalid flag(s): Must be a non-empty string or list of strings")

        endpoint = f"{MemoryManager.message_queue_url}/add-message"
        
        for f in flags:
            payload = {
                "user_id": user_id,
                "content": content,
                "role": role,
                "flag": f
            }
            
            try:
                response = requests.post(endpoint, json=payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to add message: {str(e)}")
    
    @staticmethod
    def get_messages(user_id: str, flag: str, min_size: int):
        try:
            get_endpoint = f"{MemoryManager.message_queue_url}/message-queue/{user_id}/{flag}?min_size={min_size}"
            response = requests.get(get_endpoint)
            response.raise_for_status()
            response = response.json()
            
            history = [
                {
                    'sender': r['role'],
                    'message': r['content']
                }
                for r in response
            ]
                
            return history
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get or process messages: {str(e)}")
    
    @staticmethod
    def mark_processed(user_id: str, flag: str):
        mark_endpoint = f"{MemoryManager.message_queue_url}/message-queue/mark-processed/{user_id}/{flag}"
        mark_response = requests.post(mark_endpoint)
        mark_response.raise_for_status()
        
    @staticmethod
    def mark_failed(user_id: str, flag: str):
        mark_endpoint = f"{MemoryManager.message_queue_url}/message-queue/mark-failed/{user_id}/{flag}"
        mark_response = requests.post(mark_endpoint)
        mark_response.raise_for_status()
        
    @staticmethod
    async def summary_messages(user_id: str, top_n: int):
        async def summary_task(user_id, top_n):
            try:
                history = MemoryManager.get_messages(user_id=user_id, flag=MemoryManager.SUMMARY_FLAG, min_size=top_n)
                previous_summary = db.get_summary_memory(user_id=user_id)
                
                if history and len(history) > 0:
                    
                    prompt = RECURSIVE_SUMMARY_PROMPT.format(previous_summary=previous_summary, history=history)
                    # messages = [{"role": "user", "content": prompt}]
                    
                    response = await validate_llm_request(max_retries=3, contents=prompt, validate_func=None)
                    
                    if response:
                        db.add_summary_memory(summary=response, user_id=user_id)
                    else:
                        Exception(f"LLM while extract summary memory from user {user_id}")
                        
            except Exception as e:
                stack_trace = traceback.format_exc()
                # ChatbotLogger.get_logger().error(stack_trace)

                MemoryManager.mark_failed(user_id=user_id, flag=MemoryManager.SUMMARY_FLAG)
                raise e
            finally:
                MemoryManager.mark_processed(user_id=user_id, flag=MemoryManager.SUMMARY_FLAG)
                
        # return MemoryManager.worker_pool.add_task(
        #     summary_task,
        #     user_id,
        #     top_n
        # )
        asyncio.create_task(summary_task(user_id, top_n))
        
        
        
    @staticmethod
    async def extract_core_message(user_id: str, top_n_history: int,):
        async def extract_core_task(user_id, top_n_history, max_retries=3):
            try:
                history = MemoryManager.get_messages(user_id=user_id, flag=MemoryManager.CORE_FLAG, min_size=top_n_history)
                        
                if not history or len(history) == 0:
                    return None
                    
                prompt = EXTRACT_MEMORY.format(history=history)
                # messages = [{"role": "user", "content": prompt}]
                
                memory_result = await validate_llm_request(max_retries=3, contents=prompt, validate_func=validate_extract_memory_json)
                
                if memory_result:
                    archived_memory = memory_result['archived']
                    core_memory = memory_result['core']
                    
                    try:
                        await handle_archived_memory(archived_memory=archived_memory, top_k=5, top_k_rerank=2, user_id=user_id)
                        await handle_core_memories(user_id=user_id, new_core_memories=core_memory)
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        raise Exception(stack_trace)

            except Exception as e:
                stack_trace = traceback.format_exc()

                MemoryManager.mark_failed(user_id=user_id, flag=MemoryManager.CORE_FLAG)
                
                raise e
            finally:
                MemoryManager.mark_processed(user_id=user_id, flag=MemoryManager.CORE_FLAG)
                
        # return MemoryManager.worker_pool.add_task(
        #     extract_core_task,
        #     user_id,
        #     top_n_history
        #     )
        
        asyncio.create_task(extract_core_task(user_id, top_n_history=top_n_history))
        
    @staticmethod
    def remove_all_messages(user_id: str, flag = ""):
        if flag == "":
            flag = MemoryManager.ALL_FLAGS
            
        if isinstance(flag, str):
            MemoryManager._remove_messages(user_id, flag)
        elif isinstance(flag, list) and all(isinstance(item, str) for item in flag):
            for f in flag:
                MemoryManager._remove_messages(user_id, f)
        else:
            raise TypeError("Input must be either a string or a list of strings")
        
    def _remove_messages(user_id: str, flag: str):
        result = MemoryManager.get_messages(user_id=user_id, flag=flag, min_size=0)
        
