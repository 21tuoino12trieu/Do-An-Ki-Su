import asyncio


async def run():
    from mem0 import Memory
    import os
    
    os.environ["OPENAI_API_KEY"] = "sk-_FcF3ua4t3rRfFtmTJQgHQ"
    os.environ["OPENAI_BASE_URL"] = "https://llm-gateway-dev.mbbank.com.vn/"
    os.environ["NO_PROXY"] = "llm-gateway-dev.mbbank.com.vn"
    
    config = {
        "llm": {
            "provider": "openai",
            "config": {
                "model": "gpt-4.1-nano-2025-04-14",
                "temperature": 0.2,
                "max_tokens": 2000,
            }
        },
        # "custom_fact_extraction_prompt": custom_fact_extraction_prompt,
        "version": "v1.1"
    }

    m = Memory.from_config(config_dict=config)
    print(m)
    
    custom_fact_extraction_prompt = """
    Please only extract entities containing customer support information, order details, and user information. 
    Here are some few shot examples:

    Input: Hi.
    Output: {{"facts" : []}}

    Input: The weather is nice today.
    Output: {{"facts" : []}}

    Input: My order #12345 hasn't arrived yet.
    Output: {{"facts" : ["Order #12345 not received"]}}

    Input: I'm John Doe, and I'd like to return the shoes I bought last week.
    Output: {{"facts" : ["Customer name: John Doe", "Wants to return shoes", "Purchase made last week"]}}

    Input: I ordered a red shirt, size medium, but received a blue one instead.
    Output: {{"facts" : ["Ordered red shirt, size medium", "Received blue shirt instead"]}}

    Return the facts and customer information in a json format as shown above.
    """

    m.custom_fact_extraction_prompt = custom_fact_extraction_prompt
    print(m)
    m.custom_update_memory_prompt

if __name__ == "__main__":
    asyncio.run(run())