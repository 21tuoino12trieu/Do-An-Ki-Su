"""
FastAPI server with OpenAI-compatible endpoints.
"""
import asyncio
import warnings

from beechat.beechat import BeeChatApp
from beeportal.beecrm.beecrm_bot import BeeCRMBot
from beeportal.bee_credit_rm_khcn import BeeCreditRM
from beeportal.bot_bee.bot_v2 import BeeBot
# from beeportal.bot_bee_fraud.bot import BotBeeFraud
from beeportal.bot_bee247.bot_flow_v2 import Bee247Bot
from beeportal.bot_enterprise_KHCN.bot_v2 import BeeEnterpriseKHCN
from beeportal.bot_text2sql.bot_v2 import Text2SqlBot
from beeportal.bee_ai_enterprises.bot import BeeAiEnterprises
from beeportal.bot_text2metadata.bot import Text2MetadataBot

from .routes import chat, health, session, chat_khcn
from .routes import chat_v2
from .routes.chat import bot_store, vec_store, doc_store, bot_manager
import sys
import traceback
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from beechat_khcn.app_khcn import BeeBankingApp

from beegenerate.configs import (
    RerankingConfig
)
from beegenerate.reranks import RerankingFactory
from beegenerate.loggings import LOGGER, RequestLoggingMiddleware
# from beeportal.bot_bee247.bot import Bee247Bot
from beektnb.beektnb2 import BeeKTNB
from beeportal.beegen_hros import BotHROS
from beeportal.beegen_bot_v2 import Bot
from beeportal.beehi_v2 import BeehiBot
from beeportal.credit_bo import CreditBot
# from beeportal.beegen_PC import BeePC
from beeportal.beegen_PC_v2 import BeePC
# from beeportal.beehi_integration import BeeHi_QHLD
from beeportal.beehi_QHLD import BeeHi_QHLD
from beeportal.beehi_QHLD_v2 import BeeHi_QHLD_v2
# from beeportal.beegen_HCM import BeeHCM
from beeportal.bot_hr.bot import BeeHR
from beeportal.beegen_KT_data import BeeKTData
from beeportal.beegen_KT import BeeKT
# from beeportal.beegen_KT_workflow import BeeAccountingBot
from beeportal.beeComplyAI import BeeComply
from beeportal.beerm_v1 import BotRM
from beeportal.bee_enterprise_KHCN import BotEPKHCN
# from beeportal.beehai import BeeHaiBot
from beeportal.bot_deposit.bot import BeeDeposit
from beeportal.bee_aio.bot import BeeAIO
from beeportal.bee_ai_enterprises_adk.bot import BeeAiEnterprisesADK
from beeportal.bee_ai_enterprises_adk_v2.bot import BeeAiEnterprisesADK as BeeAiEnterprisesADK_v2
from beeportal.bee_assistant.bot import BeeAssistant

from enum import Enum

# from beektnb.beektnb_bot_v1 import BotKTNB
from beektnb.beektnb_v2 import BotKTNB
from beemcp.services.manager import MCPManagerService, MCPManagerServiceDep, get_mcp_manager
from beeagent.crud.user import UserService, UserServiceDep
from beegenerate.storage.mongo.mongodb import MongoStorageDep, get_mongodb
from beemcp import beemcp
from beegenerate.loggings.loggers import lf
import sys
sys.stdout.reconfigure(encoding='utf-8') # type: ignore

_adk_cleanup_tasks = set()

def _on_adk_cleanup_done(task: asyncio.Task[None]) -> None:
    _adk_cleanup_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        LOGGER.error(
            "ADK bot cleanup failed: %s",
            exc,
            exc_info=(type(exc), exc, exc.__traceback__)
        )

# Suppress warnings
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="pydantic.main"
)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    LOGGER.info("Initializing bot services...")
    await fetch_and_map_flow_all_bots()
    # yield
    mcp_manager = MCPManagerService()
    await mcp_manager.batch_connect()
    try:
        yield {"mcp_manager": mcp_manager}
    finally:
        try:
            await mcp_manager.batch_cleanup()
        finally:
            try:
                # Close active ADK bots
                for bot_id, entry in bot_manager.items():
                    bot = entry.get("bot") if isinstance(entry, dict) else None
                    if isinstance(bot, (BeeAiEnterprisesADK, BeeAiEnterprisesADK_v2)):
                        task = asyncio.create_task(bot.aclose_best_effort(timeout=5.0))
                        _adk_cleanup_tasks.add(task)
                        task.add_done_callback(_on_adk_cleanup_done)

                if _adk_cleanup_tasks:
                    await asyncio.gather(*list(_adk_cleanup_tasks), return_exceptions=True)
            finally:
                lf.shutdown()


# Create FastAPI application
app = FastAPI(
    title="BeeGen API",
    description="OpenAI-compatible API for BeeGen bots",
    version="1.0.0",
    lifespan=lifespan
)

# Add HTTP logging middleware for Kafka request/response tracking
app.add_middleware(RequestLoggingMiddleware)


class BotType(str, Enum):
    """Enum representing different types of bots"""
    DEFAULT = "default"
    HR = "hr"
    CREDIT = "credit"
    LEGAL_AFFAIRS = "legal affairs"
    CS_247 = "CS_247"
    BeeHi_QHLD = "BeeHi_QHLD"
    Beehi_QHLD_v2 = "Beehi_QHLD_v2"
    BeeHCM = "BeeHCM"
    KTNB = "ktnb"
    KT = "kt"
    KT_worflow = "kt_workflow"
    KT_data = "kt_data"
    APP = "app"
    APP_WITHOUT_CONVERSATION = "app_without_conversation",
    RM = "relation management"
    ENTERPRISE_KHCN = "enterprise_khcn"
    BeeKTNB = "kiem_toan_noi_bo"
    HROS = "quan_ly_dau_tu"
    CRM = "crm"
    BeeComply = "Comply"
    # JiraAgent = "jira_agent"
    APP_KHCN = "app_khcn"
    BEEHAI = "beehai"
    BEE_CREDIT_RM_KHCN = "bee_credit_rm_khcn"
    BOT_BEE_FRAUD = "bot_bee_fraud"
    BOT_TEXT2SQL = "bot_text2sql"
    BOT_TEXT2METADATA = "bot_text2metadata"
    BOT_DEPOSIT = "bot_deposit"
    AIO = "beeaio"
    ENTERPRISES_ADK = "enterprises_adk"
    ENTERPRISES_ADK_V2 = "enterprises_adk_v2"
    BOT_AI_ENTERPRISES = "bot_ai_enterprises"
    ASSISTANT= "bee_assistant"
    # Add more bot types as needed


# Initialize the reranker for flow classification


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
        ("bot này là bot tổng (router)", BotType.AIO),
        ("bot này của HR (bộ phận nhân sự)", BotType.HR),
        ("bot này của Credit (bộ phận tín dụng)", BotType.CREDIT),
        ("bot này của Pháp chế (bộ phận pháp chế)", BotType.LEGAL_AFFAIRS),
        ("bot này của bộ phân nhân sự chi nhánh", BotType.BeeHi_QHLD),
        ("bot này của toàn bộ nhân sự hiện có của MB", BotType.Beehi_QHLD_v2),
        ("bot này của bộ phân nhân sự - nguồn HCM", BotType.BeeHCM),
        ("bot này của 247 (bộ phận chăm sóc khách hàng 247 - khối vận hành)", BotType.CS_247),
        ("bot này của Kiểm toán nội bộ (bộ phận kiểm toán)", BotType.KTNB),
        ("bot này của bộ phận Kế toán (phiên bản thường)", BotType.KT),
        ("bot này của bộ phận Kế toán (phiên bản workflow)", BotType.KT_worflow),
        ("bot này của bộ phận Kế toán (phiên bản tra cứu)", BotType.KT_data),
        ("bot này là ong bee để chăm sóc khách hàng trên app (phiên bản có hội thoại)", BotType.APP),
        ("bot này là ong bee để chăm sóc khách hàng trên app (phiên bản không hội thoại)",
         BotType.APP_WITHOUT_CONVERSATION),
        ("bot này là bot Bee RM, chuyên hỗ trợ người dùng trả lời các câu hỏi về tài liệu.", BotType.RM),
        ("bot này là bot Enterprise KHCN (Khách hàng cá nhân), chuyên hỗ trợ người dùng trả lời các câu hỏi về tài liệu.", BotType.ENTERPRISE_KHCN),
        ("bot này là bot của kiểm toán nội bộ được update", BotType.BeeKTNB),
        ("bot này là bot của quản lý đầu tư và đối tác", BotType.HROS),
        ("bot này là bot của crm (Customer Relation Management)", BotType.CRM),
        ("bot này là bot Comply", BotType.BeeComply),
        # ("bot này là agent hỗ trợ sử dụng Jira cho mọi người", BotType.JiraAgent)
        ("bot này là bot của tư vấn tài chính khách hàng cá nhân", BotType.APP_KHCN),
        ("Beehi tiến hóa lên agent", BotType.BEEHAI),
        ("bot này là bot Tín dụng/RM KHCN", BotType.BEE_CREDIT_RM_KHCN),
        ("Đây là bot hỗ trợ truy vấn trong cơ sở dữ liệu người dùng tại MB", BotType.BOT_TEXT2SQL),
        ("Đây là bot hỗ trọ huy động vốn", BotType.BOT_DEPOSIT),
        ("Đây là bot cho luồng AI Enterprises mới 30062026 dev bằng google adk", BotType.ENTERPRISES_ADK),
        ("Đây là bot cho luồng AI Enterprises v2 dev bằng google adk", BotType.ENTERPRISES_ADK_V2),
        ("Đây là bot hỗ trọ huy động vốn", BotType.BOT_DEPOSIT),
        ("Đây là bot hỗ trợ truy vấn, sinh và cập nhật metadata cho các bảng dữ liệu trong hệ thống MB", BotType.BOT_TEXT2METADATA),
        ("Đây là bot hỗ trọ huy động vốn", BotType.BOT_DEPOSIT),
        ("Đây là bot trợ lí hỗ trợ công việc", BotType.ASSISTANT),
        ("Đây là bot cho luồng AI Enterprises mới 30062026", BotType.BOT_AI_ENTERPRISES)
        # ("bot này hỗ trợ tra cứu và cung cấp thông tin liên quan đến các tài khoản có dấu hiệu nghi ngờ gian lận hoặc lừa đảo", BotType.BOT_BEE_FRAUD)

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


async def fetch_and_map_flow_all_bots():
    """
    Creates a mapping of bot IDs to their flow classifications.

    Args:
        bot_configs: Dictionary of bot configurations

    Returns:
        Dictionary mapping bot IDs to BotType
    """
    global bot_store, vec_store, doc_store, bot_manager
    LOGGER.info("Fetching bot configurations...")
    # Fetch bot configs
    bot_configs = bot_store.fetch_active_bots()

    for bot_id, config in bot_configs.items():
        bot_type = None
        try:
            # Get the definition from the bot config
            definition = config.get('definition', '')
            # Classify the flow
            bot_type = await classify_flow(definition)
     
            # if bot_type == BotType.CS_247:
            #     # Create Bee247Bot for HR flows
            #     LOGGER.info(f"Initializing Bee247 for bot {bot_id} (247 flow)")
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': Bee247Bot(
            #             bot_id=bot_id,
            #             bot_config=config,
            #             vec_store=vec_store,
            #             doc_store=doc_store,
            #             bot_store=bot_store
            #         )
            #     }

            if bot_type == BotType.CS_247:
                # Create Bee247Bot for HR flows
                LOGGER.info(f"Initializing Bee247 for bot {bot_id} (247 flow)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': Bee247Bot(
                        bot_id=bot_id,
                    )
                }

            elif bot_type == BotType.AIO:
                # Create BeeAio
                LOGGER.info(f"Initializing Bee All in One for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeAIO(
                        bot_id=bot_id,
                    )
                }

            elif bot_type == BotType.HR:
                # Create BeehiBot for HR flows
                LOGGER.info(
                    f"Initializing BeehiBot for bot {bot_id} (HR flow)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeehiBot(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            elif bot_type == BotType.CREDIT:
                # Create CreditBot for credit flows
                LOGGER.info(
                    f"Initializing Credit Bot for bot {bot_id} (Credit flow)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': CreditBot(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            elif bot_type == BotType.BeeHi_QHLD:
                # Create CreditBot for credit flows
                LOGGER.info(
                    f"Initializing BeeHi QHLD bot for bot {bot_id} (BeeHi_QHLD)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeHi_QHLD(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }

            elif bot_type == BotType.Beehi_QHLD_v2:
                    # Create CreditBot for credit flows
                # LOGGER.info(
                #     f"Initializing BeeHi QHLD V2 bot for bot {bot_id} (Beehi_QHLD_v2)")
                # bot_manager[bot_id] = {
                #     'config': config,
                #     'bot': BeeHi_QHLD_v2(
                #         bot_config=config,
                #         vec_store=vec_store,
                #         doc_store=doc_store,
                #         bot_store=bot_store
                #     )
                # }
                LOGGER.info(
                    f"Initializing BeeHCM bot for bot {bot_id} (BeeHCM)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeHR(
                        bot_id=bot_id
                    )
                }

            elif bot_type == BotType.BeeHCM:
                # Create CreditBot for credit flows
                LOGGER.info(
                    f"Initializing BeeHCM bot for bot {bot_id} (BeeHCM)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeHR(
                        bot_id=bot_id
                    )
                }

            elif bot_type == BotType.LEGAL_AFFAIRS:
                # Create CreditBot for credit flows
                LOGGER.info(
                    f"Initializing Credit Bot for bot {bot_id} (Legal)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeePC(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }

            elif bot_type == BotType.KTNB:
                # Create BotKTNB for KTNB
                LOGGER.info(f"Initializing KTNB Bot for bot {bot_id} (KTNB)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BotKTNB(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
                
            elif bot_type == BotType.KT:
                # Create BeegenKT for KT
                LOGGER.info(f"Initializing KT Bot for bot {bot_id} (KT)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeKT(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            # elif bot_type == BotType.KT_worflow:
            #     # Create BeegenKT for KT
            #     LOGGER.info(f"Initializing KT workflow Bot for bot {bot_id} (KT_workflow)")
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': BeeAccountingBot(
            #             bot_id=bot_id
            #         )
            #     }

            elif bot_type == BotType.KT_data:
                LOGGER.info(
                    f"Initializing KT data Bot for bot {bot_id} (KT_data)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeKTData(
                        bot_id=bot_id,
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            elif bot_type == BotType.BeeKTNB:
                # Create BeegenKT for KT
                LOGGER.info(
                    f"Initializing BeeKTNB Bot V2 for bot {bot_id} (KTNB)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeKTNB(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.APP:
                # Create BeegenKT for KT
                LOGGER.info(
                    f"Initializing BeeChat Bot (with conversation) for bot {bot_id} (App)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeChatApp(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.APP_KHCN:
                # Create BeegenKT for KT
                LOGGER.info(
                    f"Initializing Financial Consulting Bot for bot {bot_id} (App KHCN)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeBankingApp(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.RM:
                LOGGER.info(f"Initializing RM Bot for bot {bot_id} (RM)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BotRM(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }

            # elif bot_type == BotType.ENTERPRISE_KHCN:
            #     LOGGER.info(f"Initializing ENTERPRISE_KHCN Bot for bot {bot_id} (ENTERPRISE_KHCN)")
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': BotEPKHCN(
            #             bot_config=config,
            #             vec_store=vec_store,
            #             doc_store=doc_store,
            #             bot_store=bot_store
            #         )
            #     }
            elif bot_type == BotType.ENTERPRISE_KHCN:
                LOGGER.info(f"Initializing ENTERPRISE_KHCN Bot for bot {bot_id} (ENTERPRISE_KHCN)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeEnterpriseKHCN(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.HROS:
                LOGGER.info(f"Initializing QLDT Bot for bot {bot_id} (QLDT)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BotHROS(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            elif bot_type == BotType.BOT_DEPOSIT:
                LOGGER.info(f"Initializing BOT_DEPOSIT Bot for bot {bot_id} (BOT_DEPOSIT)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeDeposit(
                        bot_id=bot_id
                    )
                }
            # elif bot_type == BotType.JiraAgent:
            #     LOGGER.info(f"Initializing JiraAgent for {bot_id} (JiraAgent)")
            #     user_service = UserService(mongodb=get_mongodb())
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': JiraAgent(
            #             bot_id=bot_id,
            #             user_service=user_service
            #         )
            #     }
            elif bot_type == BotType.CRM:
                LOGGER.info(f"Initializing CRM Bot for bot {bot_id} (CRM)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeCRMBot(
                        bot_id=bot_id
                    )
                }

            # elif bot_type == BotType.BEEHAI:
            #     LOGGER.info(
            #         f"Initializing BeeHai Bot for bot {bot_id} (BeeHaiHR)")
            #     user_service = UserService(mongodb=get_mongodb())
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': BeeHaiBot(
            #             bot_id=bot_id,
            #             user_service=user_service
            #         )
            #     }

            elif bot_type == BotType.BeeComply:
                LOGGER.info(f"Initializing Comply Bot for bot {bot_id} (Comply)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeComply(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }

            elif bot_type == BotType.BEE_CREDIT_RM_KHCN:
                LOGGER.info(f"Initializing Tin dung/RM Bot for bot {bot_id} (Comply)")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeCreditRM(
                        bot_config=config,
                        vec_store=vec_store,
                        doc_store=doc_store,
                        bot_store=bot_store
                    )
                }
            elif bot_type == BotType.BOT_TEXT2SQL:
                LOGGER.info(f"Initializing Text2SQL Bot for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': Text2SqlBot(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.ENTERPRISES_ADK:
                LOGGER.info(f"Initializing AI ENTERPRISES ADK Bot for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeAiEnterprisesADK(
                        bot_id=bot_id
                    )
                }            
            elif bot_type == BotType.ASSISTANT:
                # Create Bee Assistant for everyone
                LOGGER.info(f"Initializing Bee Assistant for bot {bot_id} ")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeAssistant(
                        bot_id=bot_id,
                    )
                }
            # elif bot_type == BotType.BOT_BEE_FRAUD:
            #     LOGGER.info(f"Initializing Bot Bee Fraud for bot {bot_id} (Comply)")
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': BotBeeFraud(
            #             bot_id=bot_id
            #         )
            #     }

            # else:
            #     # Create regular Bot for other flows
            #     LOGGER.info(f"Initializing standard Bot for bot {bot_id}")
            #     bot_manager[bot_id] = {
            #         'config': config,
            #         'bot': Bot(
            #             bot_config=config,
            #             vec_store=vec_store,
            #             doc_store=doc_store,
            #             bot_store=bot_store
            #         )
            #     }
            elif bot_type == BotType.ENTERPRISES_ADK:
                LOGGER.info(f"Initializing AI ENTERPRISES ADK Bot for bot {bot_id}")
                old_bot = None
                try:
                    old_entry = bot_manager.get(bot_id)
                    old_bot = old_entry.get("bot") if isinstance(old_entry, dict) else None

                    new_bot = BeeAiEnterprisesADK(bot_id=bot_id)
                    bot_manager[bot_id] = {
                        'config': config,
                        'bot': new_bot
                    }

                    if isinstance(old_bot, BeeAiEnterprisesADK):
                        task = asyncio.create_task(old_bot.aclose_best_effort(timeout=5.0))
                        _adk_cleanup_tasks.add(task)
                        task.add_done_callback(_on_adk_cleanup_done)
                except Exception as e:
                    LOGGER.error(f"Error initializing ADK bot {bot_id}: {e}")
                    if old_bot is not None:
                        continue
                    raise
                continue

            elif bot_type == BotType.ENTERPRISES_ADK_V2:
                LOGGER.info(f"Initializing AI ENTERPRISES ADK V2 Bot for bot {bot_id}")
                old_bot = None
                try:
                    old_entry = bot_manager.get(bot_id)
                    old_bot = old_entry.get("bot") if isinstance(old_entry, dict) else None

                    new_bot = BeeAiEnterprisesADK_v2(bot_id=bot_id)
                    bot_manager[bot_id] = {
                        'config': config,
                        'bot': new_bot
                    }

                    if isinstance(old_bot, BeeAiEnterprisesADK_v2):
                        task = asyncio.create_task(old_bot.aclose_best_effort(timeout=5.0))
                        _adk_cleanup_tasks.add(task)
                        task.add_done_callback(_on_adk_cleanup_done)
                except Exception as e:
                    LOGGER.error(f"Error initializing ADK V2 bot {bot_id}: {e}")
                    if old_bot is not None:
                        continue
                    raise
                continue
            elif bot_type == BotType.BOT_AI_ENTERPRISES:
                LOGGER.info(f"Initializing AI ENTERPRISES Bot for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeAiEnterprises(
                        bot_id=bot_id
                    )
                }
            elif bot_type == BotType.BOT_TEXT2METADATA:
                LOGGER.info(f"Initializing Text2Metadata Bot for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': Text2MetadataBot(
                        bot_id=bot_id
                    )
                }
            else:
                # Create regular Bot for other flows
                LOGGER.info(f"Initializing standard Bot for bot {bot_id}")
                bot_manager[bot_id] = {
                    'config': config,
                    'bot': BeeBot(bot_id=bot_id)
                }

        except Exception as e:
            if bot_type == BotType.ENTERPRISES_ADK:
                raise
            LOGGER.error(
                f"Error classifying flow, choose standard Bot for bot {bot_id}: {str(e)}")
            # bot_manager[bot_id] = {
            #     'config': config,
            #     'bot': BeehiBot(
            #         bot_config=config,
            #         vec_store=vec_store,
            #         doc_store=doc_store,
            #         bot_store=bot_store
            #     )
            # }
            bot_manager[bot_id] = {
                'config': config,
                'bot': BeeBot(bot_id=bot_id)
            }
    LOGGER.info("Services initialized successfully")


# Configuration management
@app.get("/refresh_config")
async def refresh_config():
    """
    Refresh all bot configurations and recreate bot instances.

    Returns:
        JSON response with refresh status and details

    Raises:
        HTTPException: If refresh fails
    """
    try:
        await fetch_and_map_flow_all_bots()
        LOGGER.info(
            f"Configuration refresh completed for {len(bot_manager)} bots")

        response = {
            "status": "success",
            "message": "Configuration refresh completed",
            "details": {
                "total": len(bot_manager),
                "bots": {}
            }
        }

        for bot_id, bot_data in bot_manager.items():
            response["details"]["bots"][bot_id] = bot_data["config"]

        return response
    except Exception as e:
        # Capture full stack trace
        exc_type, exc_value, exc_traceback = sys.exc_info()
        stack_trace = traceback.format_exception(
            etype=exc_type,
            value=exc_value,
            tb=exc_traceback
        )

        error_msg = f"Failed to refresh configuration: {str(e)}"
        LOGGER.error(error_msg)
        LOGGER.error(f"Stack trace: {''.join(stack_trace)}")

        # Return detailed error information including stack trace
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": error_msg,
                "error_type": exc_type.__name__ if exc_type else type(e).__name__,
                "stack_trace": stack_trace,
                "line": exc_traceback.tb_lineno if exc_traceback else None
            }
        )


# Health check endpoints directly on the app (for backward compatibility)
@app.get("/actuator/prometheus", status_code=200)
async def prometheus_metrics_compat():
    """Endpoint for Prometheus metrics (compatibility endpoint)."""
    return await health.prometheus_metrics()


@app.get("/actuator/health", status_code=200)
async def health_check_compat():
    """Basic health check endpoint (compatibility endpoint)."""
    return await health.health_check()


# Import and include routers

# Include API routes
app.include_router(chat.router)
app.include_router(chat_v2.router)  # V2: không dùng mcp_manager
# app.include_router(chat_khcn.router)
app.include_router(chat_v2.router)
app.include_router(health.router)
app.include_router(session.router)
# app.include_router(beemcp.router)
