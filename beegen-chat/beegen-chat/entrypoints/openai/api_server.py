from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from beeportal.beegen_bot_v2 import Bot
from beeportal.beehi_v2 import BeehiBot
from beeportal.credit_bo import CreditBot
from beegenerate.storage import BotStore, DocumentStore
from beegenerate.vectordb import MilvusStorage
from beegenerate.configs import RerankingConfig
from beegenerate.reranks import RerankingFactory
from beegenerate.loggings import LOGGER
from entrypoints.openai.keycloak_utils import KeycloakMiddleware
from enum import Enum
    

import warnings

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="pydantic.main"
)

app = FastAPI()   

# Global variables
bot_store = None
vec_store = None
doc_store = None
bot_manager = None
flow_mapping = None


@app.get("/actuator/prometheus", status_code=200)
async def health_check_2():
    return "OK"


@app.get("/actuator/health", status_code=200)
async def health_check():
    return "OK"


class BotType(str, Enum):
    """Enum representing different types of bots"""
    DEFAULT = "default"
    HR = "hr"
    CREDIT = "credit"
    # Add more bot types as needed
    
    
flow_classifier = RerankingFactory.create(
    config=RerankingConfig.default()
)

async def classify_flow(definition: str) -> BotType:
    """
    Classifies a bot definition into one of the supported bot types.
    
    Args:
        definition: The bot definition text
        
    Returns:
        The classified bot type
    """
    # Define classification patterns for each bot type
    classification_patterns = [
        ("bot này của HR (bộ phận nhân sự)", BotType.HR),
        ("bot này của Credit (bộ phận tín dụng)", BotType.CREDIT),
        # Add more patterns as needed
    ]
    
    # Run classification for each pattern
    results = []
    for pattern, bot_type in classification_patterns:
        score = await flow_classifier.run(
            query=definition,
            texts=[pattern]
        )
        results.append((bot_type, score[0]['score']))
        LOGGER.info(f"Classification for {bot_type}: {score[0]['score']}")
    
    # Find the highest scoring match
    matches = [(bot_type, score) for bot_type, score in results if score > 0.5]
    
    if not matches:
        LOGGER.info(f"No matching bot type found, defaulting to DEFAULT")
        return BotType.DEFAULT
    
    # Sort by score in descending order and take the highest
    best_match = sorted(matches, key=lambda x: x[1], reverse=True)[0]
    LOGGER.info(f"Best match: {best_match[0]} with score {best_match[1]}")
    
    return best_match[0]


async def create_bot_flow_mapping(bot_configs: Dict[str, Any]) -> Dict[str, BotType]:
    """
    Creates a mapping of bot IDs to their flow classifications.
    
    Args:
        bot_configs: Dictionary of bot configurations
        
    Returns:
        Dictionary mapping bot IDs to BotType
    """
    flow_mapping = {}
    
    for bot_id, config in bot_configs.items():
        try:
            # Get the definition from the bot config
            definition = config.get('definition', '')
            # Classify the flow
            bot_type = await classify_flow(definition)
            flow_mapping[bot_id] = bot_type
        except Exception as e:
            LOGGER.error(f"Error classifying flow for bot {bot_id}: {str(e)}")
            flow_mapping[bot_id] = BotType.DEFAULT  # Default on error
            
    return flow_mapping


security = HTTPBearer()


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        keycloak_middleware = KeycloakMiddleware(credentials.credentials)
        decoded_token = keycloak_middleware.verify_token()
        return decoded_token
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    

async def initialize_services():
    
    from beegenerate.configs import MongoConfig, MilvusConfig
    
    global bot_store, vec_store, doc_store, bot_manager, flow_mapping
    
    # Initialize stores
    bot_store = BotStore(config=MongoConfig.default())
    vec_store = MilvusStorage(config=MilvusConfig.default())
    doc_store = DocumentStore(config=MongoConfig.default())
    
    # Fetch bot configs
    bot_configs = bot_store.fetch_active_bots()
    
    # Create flow mapping
    flow_mapping = await create_bot_flow_mapping(bot_configs)
    
    # Initialize bot manager with conditional bot creation
    bot_manager = {}
    for bot_id, config in bot_configs.items():
        bot_type = flow_mapping.get(bot_id, BotType.DEFAULT)
        
        if bot_type == BotType.HR:
            # Create BeehiBot for HR flows
            bot_manager[bot_id] = BeehiBot(
                bot_config=config,
                vec_store=vec_store,
                doc_store=doc_store,
                bot_store=bot_store,
            )
        elif bot_type == BotType.CREDIT:
            # Create CreditBot for credit flows
            bot_manager[bot_id] = CreditBot(
                bot_config=config,
                vec_store=vec_store,
                doc_store=doc_store,
                bot_store=bot_store,
            )
        else:
            # Create regular Bot for other flows
            bot_manager[bot_id] = Bot(
                bot_config=config,
                vec_store=vec_store,
                doc_store=doc_store,
                bot_store=bot_store,
            )
            

@app.get("/refresh_config")
async def refresh_config():
    try:
        global bot_manager, flow_mapping
        new_bot_configs = bot_store.fetch_active_bots()
        
        # Update flow mapping
        new_flow_mapping = await create_bot_flow_mapping(new_bot_configs)
        
        # Update bot manager with conditional bot creation
        new_bot_manager = {}
        for bot_id, config in new_bot_configs.items():
            bot_type = new_flow_mapping.get(bot_id, BotType.DEFAULT)
            
            if bot_type == BotType.HR:
                # Create BeehiBot for HR flows
                new_bot_manager[bot_id] = BeehiBot(
                    bot_config=config,
                    vec_store=vec_store,
                    doc_store=doc_store,
                    bot_store=bot_store,
                )
            elif bot_type == BotType.CREDIT:
                # Create CreditBot for credit flows
                new_bot_manager[bot_id] = CreditBot(
                    bot_config=config,
                    vec_store=vec_store,
                    doc_store=doc_store,
                    bot_store=bot_store,
                )
            else:
                # Create regular Bot for other flows
                new_bot_manager[bot_id] = Bot(
                    bot_config=config,
                    vec_store=vec_store,
                    doc_store=doc_store,
                    bot_store=bot_store,
                )
        
        # Update globals
        flow_mapping = new_flow_mapping
        bot_manager = new_bot_manager
        
        response = {
            "status": "success",
            "message": "Configuration refresh completed",
            "details": {
                "total_bots": len(bot_manager),
                "flow_mapping": {k: v.value for k, v in flow_mapping.items()}
            }
        }
        
        return response
    except Exception as e:
        error_msg = f"Failed to refresh configuration: {str(e)}"
        LOGGER.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": error_msg
            }
        )


async def stream_response(data: Dict[str, Any]):
    messages = data.get("messages", [])
    bot_id = data.get("bot_id", None)
    role = data.get("role", None)
    topic = data.get("topic", None)
    metadata = data.get("metadata", {})
    
    bot = bot_manager[bot_id]        
    
    response_text = ""
    
    async for chunk in bot.run(
        messages=messages,
        role=role,
        topic=topic,
        metadata=metadata
    ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                response_text += str(chunk.choices[0].delta.content)
        yield f"data: {chunk.json()}\n\n"
    
    yield "data: [DONE]\n\n"
    

@app.post("/v1/chat/completions")
async def stream_model_response(
    request: Request,
    token: dict = Depends(verify_token),
):
    data = await request.json()
    return StreamingResponse(stream_response(data), media_type="text/event-stream")


@app.post("/v1/chat/completions_")
async def stream_model_response(
    request: Request
):
    data = await request.json()
    return StreamingResponse(stream_response(data), media_type="text/event-stream")


if __name__ == "__main__":
    from dotenv import load_dotenv
    import uvicorn
    import asyncio
    
    # Run initialization before starting the server
    asyncio.run(initialize_services())
    
    load_dotenv(override=True)
    
    uvicorn.run(
        app=app, 
        host="0.0.0.0", 
        port=8000,
        loop="asyncio"
    )