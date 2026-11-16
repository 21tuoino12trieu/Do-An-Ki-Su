from typing import List
from agents import Agent, Runner, RunContextWrapper
from pydantic.dataclasses import dataclass
import os
import asyncio

from .context import UserInfo

from agents.extensions.models.litellm_model import LitellmModel

from .table_schema import table_schemas
from beegenerate.loggings.loggers import lf

@dataclass
class TableExtractionResult:
    """
    LLM output: danh sách tên bảng cần dùng để truy vấn dữ liệu
    """
    tables: list[str]


instruction="""
    ### NHIỆM VỤ ###
    Bạn là một hệ thống phân tích câu hỏi và xác định **chính xác danh sách các bảng dữ liệu cần thiết** để truy xuất thông tin từ cơ sở dữ liệu.

    ### QUY TẮC XỬ LÝ ###
    1. Chỉ được sử dụng **table schema** cung cấp ở dưới.  
    2. Việc lựa chọn bảng phải **dựa hoàn toàn trên ngữ nghĩa của câu hỏi** + mô tả bảng.
    3. Bạn PHẢI hiểu các thông tin có trong từng bảng được cung cấp bên dưới (thông tin nằm ở phần description) để suy luận và lựa chọn chính xác các bảng có thể chứa dữ liệu.
    4. So khớp các thông tin ở câu hỏi với các trường thông tin trong từng bảng để chọn ra các bảng liên quan nhất. 
    5. Nếu thông tin nằm ở nhiều bảng thì phải chọn **đầy đủ tất cả các bảng liên quan**.  
    6. Không tự suy đoán bảng ngoài schema.

    ### TABLE SCHEMA ###
    Dưới đây là thông tin schema từ hệ thống (toàn bộ bảng + mô tả + cột):

    {table_schema}

    ### ĐẦU RA BẮT BUỘC ###
    Trả về kết quả dạng list[str] với đúng cấu trúc:

    ["table_name_1", "table_name_2", ...]
    

    ### YÊU CẦU TUÂN THỦ TUYỆT ĐỐI ###
    - BẮT BUỘC trả về danh sách các bảng có thể chứa đầy đủ thông tin để trả lời câu hỏi.
    - Không được trả về bảng không tồn tại trong schema.
    - Không diễn giải thêm.
    
    """

def create_table_extractor_agent(model) -> Agent:
    try:
        BEEHI_HCM_EXTRACT_TABLES= lf.get_prompt(name="BEEHI_HCM_EXTRACT_TABLES")
        print(f"Prompt type: {type(BEEHI_HCM_EXTRACT_TABLES)}")
        print("BEEHI_HCM_EXTRACT_TABLES: ", BEEHI_HCM_EXTRACT_TABLES)
        if hasattr(BEEHI_HCM_EXTRACT_TABLES, 'template'):
            print(f"Template length: {len(str(BEEHI_HCM_EXTRACT_TABLES.template)) if BEEHI_HCM_EXTRACT_TABLES.template else 0}")
    except  Exception as e:
        print(f"❌ Failed to fetch langfuse prompt: {e}")
        print("Using default instructions")
        BEEHI_HCM_EXTRACT_TABLES = instruction
        print(f"Using default instructions, length: {len(BEEHI_HCM_EXTRACT_TABLES)}")
    
    return Agent(
        name="BeeHCM Schema Table Extractor",
        model=model,
        instructions=BEEHI_HCM_EXTRACT_TABLES.compile(table_schema=table_schemas),
        output_type=TableExtractionResult
    )


table_extractor_agent = Agent(
    name="BeeHCM Schema Table Extractor",
    model=LitellmModel(
        model="gpt-4.1",
        api_key="REPLACE_WITH_LOCAL_SECRET",
        base_url="https://llm-gateway-dev.mbbank.com.vn"
    ),
    instructions=instruction.format(
            table_schema= table_schemas
    ),
    output_type=TableExtractionResult
)
async def main():
    question = "Chức danh của tôi tại VNG Corporation là gì?"

    print("run")
    result = await Runner.run(
        starting_agent=table_extractor_agent,
        input=question
    )

    print(result.final_output)
    print(result.final_output.tables)


if __name__ == "__main__":
    asyncio.run(main())
