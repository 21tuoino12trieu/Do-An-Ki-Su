# from beegen.embeddings import EmbeddingFactory
from beegenerate.reranks import RerankingFactory


from beegenerate.llms.core import LLMFactory, BaseLLM
from beegenerate.configs import (
    LLMConfig,
    CompletionConfig,
    RetrievalConfig,
    EmbeddingConfig,
    RerankingConfig,
)

from pathlib import Path
from typing import Dict, List
import yaml
import pandas as pd
import asyncio

from beegenerate.prompts.bee247_v2 import CARD_KEYWORD_EXTRACT_PROMPT
from bee247.constants import get_card_keyword_unique, get_card_keyword_mapping
from beegenerate.loggings import LOGGER


async def card_keyword_extract(
    llm: BaseLLM,
    query: str,
) -> Dict:
    response = ""
    try:
        async for chunk in llm.run(
            messages=[
                {
                    'role': 'user',
                    'content': CARD_KEYWORD_EXTRACT_PROMPT.format(
                        keywords=get_card_keyword_unique(),
                        question=query
                    )
                }
            ]
        ):
            content = chunk.choices[0].delta.content
            if content:
                response += content
                
        response = response.strip("\"").strip("?")
                
        extracted_keywords = eval(response)
        
        # print("Extract keywords:", extracted_keywords)
        
        card_ids = _filter_and_match_keyword(get_card_keyword_mapping(), extracted_keywords, get_card_keyword_unique())
        
        print(f"Extracted keyword: {extracted_keywords}")
        
        print(f"card ids: {card_ids}")
        return card_ids
    
    
    except Exception as e:
        # Handle other potential errors
        LOGGER.error(f"Error in card keyword extraction: {e}", exc_info=True)
        return None

def _filter_and_match_keyword(card_keyword_dict, input_list, unique_keywords):
    matching_keys = []
    
    if set(input_list) == {"priority", "visa"}:
        matching_keys = [
            key for key, keywords in card_keyword_dict.items()
            if "priority" in keywords and "visa" in keywords
        ]
        return matching_keys
    
    if "priority" in input_list:
        priority_keys = [
            key for key, keywords in card_keyword_dict.items()
            if "priority" in keywords
        ]
        matching_keys.extend(priority_keys)
        input_list = [item for item in input_list if item != "priority"]
    
    filtered_list = [item for item in input_list if item in unique_keywords]
    
    # print("Fltered keywords:", filtered_list)
    
    if len(filtered_list) > 0:
        matching_keys.extend([
            key for key, keywords in card_keyword_dict.items()
            if all(keyword in keywords for keyword in filtered_list)
        ])
        
    # print("Matching keys:", matching_keys)
    
    return matching_keys

async def main():
    # config = BotConfig.from_yaml_file(Path("config/bot.yaml"))
    
    llm = LLMFactory.create(
        llm_config=LLMConfig(
            api_key="mb123456789",
            api_type="vllm",
            base_url="http://10.1.39.127:30042/v1",
            model="model/beegen-model-v1"
        ),
        completion_config=CompletionConfig(temperature=0)
    )
    
    keywords = await card_keyword_extract(llm = llm, query = "cuộc sống có giống cuộc đời không em ?")
    print(keywords)
    
if __name__ == "__main__":
    asyncio.run(main())