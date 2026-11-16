from beegenerate.configs.llm_config import LLMConfig, LLMType

if __name__ == "__main__":
    # llm_config = LLMConfig(
    #     api_key="REPLACE_WITH_LOCAL_SECRET",
    #     api_type= LLMType.AZURE,
    #     base_url="https://10.1.13.168:8443/mbdevai",
    #     api_version="2024-02-15-preview",
    #     model="azure-chat-engine-gpt-4o-base",
        
    #     temperature = 0.0,
    #     top_p = 1.0,
    #     n = 1,
    #     stream = True,
    #     stop = None,
    #     max_tokens = 4096,
    #     frequency_penalty = 0.0,
    #     presence_penalty = 0.0,
    #     response_format = None
    # )
    
    # llm_config.to_yaml_file("llm_config.yaml")
    from pathlib import Path
    
    llm_config = LLMConfig.from_yaml_file(Path("config/beehi.yaml"))
    
    print(llm_config)