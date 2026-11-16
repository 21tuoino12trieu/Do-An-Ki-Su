from beegenerate.configs.db.mongo_config import MongoConfig
from typing import Dict, List, Optional
import json
from .mongodb import MongoStorage

from beegenerate.loggings import LOGGER
from beegenerate.const import BEEGEN_ROOT

from beememory.prompt import MAIN_CHAT_SYSTEM_PROMPT
from beememory.constant.caching import USER_SUMMARY_MEMORY_CACHING, USER_ROOT_MEMORY_CACHING

import time


class MemoryStore(MongoStorage):
    
    def __init__(
        self, 
        config: Optional[MongoConfig] = None
    ) -> None:
        super().__init__(config)
        
        self.chatbot_db = config.chatbot_db
        self.users_table = config.users_table
        self.chat_history_table = config.chat_history_table
        self.memory_summary_table = config.memory_summary_table
        self.memory_core_table = config.memory_core_table
    
    def query_user_by_id(self, user_id=None):
        table = self._client[self.chatbot_db][self.users_table]
        if user_id:
            user_info = table.find_one({'id' : user_id})
        else:
            user_info = [r for r in table.find({})]
        return user_info


    def add_user(self, user_id):
        table = self._client[self.chatbot_db][self.users_table]
        cursor = table.insert_one({"id" : user_id,
                                    "status" : True,
                                    "created_at" : int(time.time()),
                                    "updated_at" : int(time.time())})
        return cursor
    
        
    def delete_user_by_id(self, user_id):
            
        table = self._client[self.chatbot_db][self.users_table]
        cursor = table.delete_one({"id" : user_id})
    
        return cursor
    
    
    
    def update_user_by_id(self, user_id, update_query):
        table = self._client[self.chatbot_db][self.users_table]
        cursor = table.update_one({"id" : user_id},
                                    {"$set" : {**update_query, "updated_at" : int(time.time())}})
        return cursor
    
    def decode_user_id_in_chat_table(self, user_id, update_query):
        table = self._client[self.chatbot_db][self.chat_history_table]   
        cursor = table.update_many({"user_id" : user_id},
                                  {"$set" : update_query})
        return cursor
    
    def decode_user_id_in_memory_summary_table(self, user_id, update_query):
        table = self._client[self.chatbot_db][self.memory_summary_table]   
        cursor = table.update_many({"user_id" : user_id},
                                  {"$set" : update_query})
        return cursor
    
    def query_message_by_user_id(self, user_id, top_n=-1):
        table = self._client[self.chatbot_db][self.chat_history_table]
        
        query = {'user_id': user_id}
        
        if top_n > 0:
            cursor = table.find(query).sort('created_at', -1).limit(top_n)
            messages = list(cursor)
            messages.reverse()
        else:
            cursor = table.find(query).sort('created_at', 1)
            messages = list(cursor)
        
        # Convert to desired format
        history = [(row['role'], row['content']) for row in messages]
        return history

    def add_message(self, user_id, content, role):
        table = self._client[self.chatbot_db][self.chat_history_table]
        cursor = table.insert_one({'user_id' : user_id,
                                   'content' : content,
                                   'role' : role,
                                   'created_at' : int(time.time())})
        return cursor
    
    def add_summary_memory(self, user_id, summary):
        table = self._client[self.chatbot_db][self.memory_summary_table]
        
        result = table.update_one(
            {'user_id': user_id}, 
            {
                '$set': {
                    'summary': summary,
                    'created_at': int(time.time())
                }
            },
            upsert=True  # This ensures creation if document doesn't exist
        )
        USER_SUMMARY_MEMORY_CACHING[user_id] = summary
                
        return result
    
    def add_core_memory(self, user_id, core_memory):
        table = self._client[self.chatbot_db][self.memory_core_table]
        
        result = table.update_one(
            {'user_id': user_id}, 
            {
                '$set': {
                    'core_memory': core_memory,
                    'created_at': int(time.time())
                }
            },
            upsert=True  # This ensures creation if document doesn't exist
        )
        USER_ROOT_MEMORY_CACHING[user_id] = core_memory
                
        return result
    
    def get_summary_memory(self, user_id):
        if user_id not in USER_SUMMARY_MEMORY_CACHING:
            table = self._client[self.chatbot_db][self.memory_summary_table]
            
            # Find all records matching user_id
            records = list(table.find({'user_id': user_id}))
            
            if not records:
                USER_SUMMARY_MEMORY_CACHING[user_id] = ""
            else:  
                if len(records) > 1:
                    # ChatbotLogger.get_logger().warning(f"Found multiple summary records for user_id {user_id}")
                    pass
                    
                USER_SUMMARY_MEMORY_CACHING[user_id] = records[0]['summary']
                
        else:
            pass
            
        return USER_SUMMARY_MEMORY_CACHING[user_id]
        
    
    def get_core_memory(self, user_id):
        if user_id not in USER_ROOT_MEMORY_CACHING:
            table = self._client[self.chatbot_db][self.memory_core_table]
            records = list(table.find({'user_id': user_id}))
            
            if not records:
                USER_ROOT_MEMORY_CACHING[user_id] = ""
            else:
                if len(records) > 1:
                    # ChatbotLogger.get_logger().warning(f"Found multiple records for user {user_id} root memory")
                    pass
                
                USER_ROOT_MEMORY_CACHING[user_id] = records[0]['core_memory']                
        else:
            pass
        return USER_ROOT_MEMORY_CACHING[user_id]

        

    def get_user_id(self, user_id, force_create = True):
        
        if force_create and not self.query_user_by_id(user_id=user_id):
            self.add_user(user_id=user_id)
             
        return user_id