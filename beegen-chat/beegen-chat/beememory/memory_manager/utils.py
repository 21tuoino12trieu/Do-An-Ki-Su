from beememory.conversation_manager.ConversationManager import HandlerResponse
from beememory.constant import model, milvus_client, embedding_model
from beememory.memory_manager import MemoryManager
from beememory.prompt import RELEVANT_ARCHIVED_MEMORY_EXTRACT, CORE_MEMORY_COMBINE
from beememory.constant.app_constant import *

import re
import json
from datetime import datetime
import traceback

async def handle_archived_memory(archived_memory: dict, user_id, top_k = 5, top_k_rerank=2):
    final_results = []
    try:
        for actor, memories in archived_memory.items():
            if memories:
                archived_partition_name = f"{user_id}_{actor}_archived"
                
                milvus_client.create_partition(archived_partition_name)
                
                embedding_texts = []
                for value, content in memories.items():
                    embedding_texts.append(f"{value}: {content}")
                    
                embeddings = await embedding_model.run(embedding_texts)
                
                #TODO: milvus
                old_archived_results = milvus_client.search_top_n(partition_name=archived_partition_name, query_embeddings=embeddings, top_k=top_k)
                # old_archived_results = []

                old_archived_results_reranked = []
                
                for text, old_archived_result in zip(embedding_texts, old_archived_results):
                    old_archived_result = [o['content'] for o in old_archived_result]
                    
                    # if len(old_archived_result) > 0:
                    #     reranked_results = await reranker_model.rerank(query=text, documents=old_archived_result, top_n=top_k_rerank)
                    #     reranked_results = reranked_results['documents']
                    # else:
                    #     reranked_results = []
                        
                    reranked_results = old_archived_result
                                    
                    old_archived_results_reranked.extend(reranked_results)
                    
                reranked_ids = mapping_content_id(content_id_objects=old_archived_results, contents=old_archived_results_reranked)
                    
                relevant_archived_prompt = RELEVANT_ARCHIVED_MEMORY_EXTRACT.format(old_facts = old_archived_results_reranked, new_facts = embedding_texts)
                # relevant_archived_messages = [{"role": "user", "content": relevant_archived_prompt}]
                
                relevant_archived_result = await validate_llm_request(max_retries=3, contents=relevant_archived_prompt, validate_func=validate_extract_relevant_archived)
                
                if relevant_archived_result:
                
                    if relevant_archived_result['inference_status'] or len(relevant_archived_result['final_fact_list']):
                        relevant_archived_result = relevant_archived_result['final_fact_list']
                        relevant_archived_embeddings = await embedding_model.run(relevant_archived_result)
                        
                        archived_embeddings = relevant_archived_embeddings
                        archived_texts = relevant_archived_result
                        
                        to_delete_ids = reranked_ids
                        to_delete_texts = old_archived_results_reranked
                    else:
                        archived_embeddings = embeddings
                        archived_texts = embedding_texts
                        
                        to_delete_ids = []
                        to_delete_texts = []
                    
                    
                    metadata_list = [
                        {
                            "created_at": datetime.now().isoformat(),
                            "last_access_at": None
                        }
                        for i in archived_embeddings
                    ]           
                    
                    final_results.append({
                        "archived_embeddings": archived_embeddings,
                        'archived_texts': archived_texts,
                        'metadata_list': metadata_list,
                        'to_delete_ids': to_delete_ids,
                        'archived_partition_name': archived_partition_name
                    })
                else:
                    raise Exception(f"LLM while extract archived memory from user {user_id}")
                    
        for result in final_results:
            #TODO: milvus
            milvus_client.insert_data(
                vectors=result['archived_embeddings'],
                contents=result['archived_texts'],
                partition_name=result['archived_partition_name'],
                metadata_list=result['metadata_list']
            )
            
            print(f"Inserted: {result['archived_texts']}")
            print(f"Partition name: {result['archived_partition_name']}")
            print(f"Metadata: {result['metadata_list']}")
            
            milvus_client.delete_by_ids(partition_name=result['archived_partition_name'], ids=result['to_delete_ids'])
            print(f"Delete ids: {result['to_delete_ids']}")
            pass
    except:
        stack_trace = traceback.format_exc()
        raise Exception(f"Exception while extract archived memory from user {user_id}\n{stack_trace}")
                
        
            
async def handle_core_memories(user_id, new_core_memories):
    
    try:
    
        old_core_memories = db.get_core_memory(user_id=user_id)
        
        prompt = CORE_MEMORY_COMBINE.format(old_facts=old_core_memories, new_facts=new_core_memories)
        # messages = [{"role": "user", "content": prompt}]
        
        core_memory_combined = await validate_llm_request(max_retries=3, contents=prompt, validate_func=validate_combine_core)
        
        if core_memory_combined:
        
            db.add_core_memory(user_id=user_id, core_memory=core_memory_combined['final_result'])

        else:
            # ChatbotLogger().get_logger().warn(f"Error while extract core memory from user {user_id}")
           raise Exception(f"LLM while extract summary core from user {user_id}")
    except Exception as e:
        stack_trace = traceback.format_exc()
        raise Exception(f"Error while extract core memmory from user {user_id}: \n{stack_trace}")

async def validate_llm_request(max_retries, contents, validate_func):
    final_result = None
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            
            response = await HandlerResponse.handle_response(
                run_function=model.run, 
                temperature=0.01, 
                messages=[{'role': 'user', 'content': contents}]
            )
            
            if validate_func:
                is_valid, result = validate_func(response)
            else:
                is_valid = True
                result = response
                
            if is_valid:
                final_result = result
                break
            else:
                print(f"Validation failed (attempt {retry_count + 1}/{max_retries}): {result}")
                retry_count += 1
                continue
                
        except Exception as e:
            print(f"Error in attempt {retry_count + 1}/{max_retries}: {str(e)}")
            retry_count += 1
            
    return final_result

def validate_extract_memory_json(response):
    if not response:
        return False, "Empty response"
        
    match = re.search(r'FINAL ANSWER:(.*)', response, re.IGNORECASE | re.DOTALL)
    if not match:
        return False, f"Response {response}:\nMissing 'FINAL ANSWER:' section"
        
    json_str = match.group(1).strip()
    
    try:
        json_data = json.loads(json_str)
        
        print(json_data)
        
        if not isinstance(json_data, dict):
            return False, f"Response {response}:\nJSON must be an object"
            
        required_fields = {"core", "archived"}
        if not all(field in json_data for field in required_fields):
            return False, f"Response {response}:\nMissing required fields. Must have 'core' and 'archived'"
            
        if not isinstance(json_data["core"], str):
            return False, f"Response {response}:\n'core' field must be a string"
            
        if not isinstance(json_data["archived"], dict):
            return False, f"Response {response}:\n'archived' field must be an object"
            
        archived = json_data["archived"]
        for key, value in archived.items():
            if not isinstance(value, dict):
                return False, f"Response {response}:\nValue for key {key} in 'archived' must be an object"
        
        return True, json_data
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {str(e)}"
    
def validate_extract_relevant_archived(response):
    try:
        data = json.loads(response)
        
        if not isinstance(data, dict):
            return False, f"Response {response}\nInput must be a JSON object (dictionary)"
            
        required_keys = {"reason", "inference_status", "final_fact_list"}
        if not all(key in data for key in required_keys):
            missing_keys = required_keys - set(data.keys())
            return False, f"Response {response}\nMissing required keys: {missing_keys}"
            
        if not isinstance(data["reason"], str):
            return False,f"Response {response}\nreason must be a string"
            
        if not isinstance(data["inference_status"], bool):
            return False, f"Response {response}\ninference_status must be a boolean"
            
        if not isinstance(data["final_fact_list"], list):
            return False, f"Response {response}\nfinal_fact_list must be a list"
            
        # If all validations pass, return True with the parsed JSON object
        return True, data
        
    except json.JSONDecodeError as e:
        return False, f"{response}\nInvalid JSON format: {str(e)}"
    
def validate_combine_core(response):
    
    try:
        data = json.loads(response)
        
        if not isinstance(data, dict):
            return False, f"Response {response}\nInput must be a JSON object (dictionary)"
            
        required_keys = {"final_result"}
        if not all(key in data for key in required_keys):
            missing_keys = required_keys - set(data.keys())
            return False, f"Response {response}\nMissing required keys: {missing_keys}"
            
        if not isinstance(data["final_result"], str):
            return False, f"Response {response}\nfinal_result must be a list"
            
        # If all validations pass, return True with the parsed JSON object
        return True, data
        
    except json.JSONDecodeError as e:
        return False, f"{response}\nInvalid JSON format: {str(e)}"
 
 
## Util functions   
def mapping_content_id(content_id_objects: list[list[dict]], contents: list[str]) -> list:
    # Create single mapping dictionary from all search results
    content_to_id = {}
    for search_results in content_id_objects:
        for search_result in search_results:
            content_to_id[search_result['content']] = search_result['id']
    
    # Map contents to their IDs
    reranked_ids = []
    for content in contents:
        if content in content_to_id:
            reranked_ids.append(content_to_id[content])
    
    return reranked_ids