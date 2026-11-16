from pydantic.dataclasses import dataclass
from string import Template
# from ..llms_extend.litellm import litellm_model
import asyncio
from agents import Agent, Runner,  RunContextWrapper
import os
from agents.extensions.models.litellm_model import LitellmModel

# @dataclass
# class CheckOutput:
#     "is_db_query: trả về True hoặc False"
#     is_db_query:bool


# instruction="""
# ### BỐI CẢNH ###
# Bạn là hệ thống phân loại câu hỏi của người dùng (Intent Classifier).
# Nhiệm vụ của bạn là xác định xem người dùng có đang hỏi thông tin liên quan đến dữ liệu trong cơ sở dữ liệu hay không.

# ---

# ### THÔNG TIN VỀ CƠ SỞ DỮ LIỆU (SCHEMA) ###
# Thông tin cơ sở dữ liệu cung cấp cho bạn như sau:
# - Các bảng (table_name)
# - Mô tả bảng (description)
# - Danh sách trường (fields)
# - Mỗi trường gồm: name, description, data type

# Dưới đây là thông tin chi tiết về toàn bộ schema mà bạn sẽ dùng để đối chiếu:

# {table_schemas}

# ---

# ### CÁCH THỨC XỬ LÝ ###
# 1. Hiểu nội dung câu hỏi của người dùng.
# 2. So khớp câu hỏi với các bảng và trường trong biến "table_schemas".
# 3. Nếu câu hỏi liên quan đến bất kỳ thông tin nào có trong schema, hãy trả về true:
# 4. Nếu không khớp với dữ liệu trong schema, hãy trả về false:

# ---

# ### GHI NHỚ ###
# - Người dùng có thể hỏi bằng ngôn ngữ tự nhiên, không cần nhắc tên bảng hay tên cột.
# - Nếu câu hỏi liên quan đến nhân sự, thông tin cá nhân, chức danh, đơn vị, nghỉ phép, hợp đồng, bằng cấp, đánh giá, khen thưởng,... thì khả năng rất cao là thuộc nhóm truy vấn DB.
# - Chỉ trả về dạng bool

# ---

# """


# table_schemas = [
#     {
#         "table_name": "beehi_base_emp_info",
#         "description": "Lưu trữ thông tin nhân sự cơ bản",
#         "fields": [
#             {"name": "username", "description": "Tên đăng nhập người dùng được đồng bộ từ keycloak MB về HCM", "data type":"text"},
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB (Khóa chính)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "fullname", "description": "Họ và tên đầy đủ", "data type":"text"},
#             {"name": "dateofbirth", "description": "Ngày tháng năm sinh", "data type":"text"},
#             {"name": "flagstatus", "description": "	Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"}
#         ]
#     },
#     {
#         "table_name": "beehi_emp_concurrent_process_info",
#         "description": "Lưu trữ thông tin quá trình kiêm nhiệm. Một nhân viên có thể có nhiều quá trình kiêm nhiệm, mỗi quá trình 1 hàng trong bảng",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "jobname", "description": "Chức danh tại MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
#             {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
#             {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
#             {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
#             {"name": "concurrentprocessid", "description": "ID của bản ghi (khóa chính)", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_contract_process_info",
#         "description": "Lưu trữ thông tin quá trình hợp đồng. Một nhân viên có thể có nhiều hợp động, mỗi hợp động 1 hàng trong bảng",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
#             {"name": "contracttype", "description": "Loại Hợp đồng lao đồng", "data type":"text"},
#             {"name": "contractnumber", "description": "Số Hợp đồng lao đồng", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "contractprocessid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_degree_info",
#         "description": "Lưu trữ thông tin bằng cấp, chứng chỉ",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "degreetype", "description": "Loại bằng cấp", "data type":"text"},
#             {"name": "majorlevel", "description": "Trình độ", "data type":"text"},
#             {"name": "school", "description": "Trường (nơi học)", "data type":"text"},
#             {"name": "faculities", "description": "Chuyên ngành", "data type":"text"},
#             {"name": "certtype", "description": "Loại chứng chỉ", "data type":"text"},
#             {"name": "certificatename", "description": "Tên Chứng chỉ", "data type":"text"},
#             {"name": "certificateplace", "description": "Nơi cấp chứng chỉ", "data type":"text"},
#             {"name": "certificateresult", "description": "Kết quả xếp loại chứng chỉ", "data type":"text"},
#             {"name": "todate", "description": "Thời hạn của chứng chỉ", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#             {"name": "educationdegreeid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_leave_info",
#         "description": "Lưu trữ thông tin quản lý nghỉ",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "leavetype", "description": "Loại nghỉ", "data type":"text"},
#             {"name": "fromtime", "description": "Thời gian bắt đầu nghỉ", "data type":"text"},
#             {"name": "totime", "description": "Thời gian cuối nghỉ (nghỉ đến ngày nào)", "data type":"text"},
#             {"name": "useddays", "description": "Số ngày phép đã sử dụng", "data type":"text"},
#             {"name": "remaindaysinyear", "description": "Số ngày phép còn lại trong năm", "data type":"text"},
#             {"name": "dayoff", "description": "Số ngày nghỉ", "data type":"text"},
#             {"name": "oldrequestid", "description": "ID của đơn được điều chỉnh", "data type":"text"},
#             {"name": "requestid", "description": "ID của bản ghi nghỉ", "data type":"text"},
#             {"name": "requestleaveid", "description": "ID lý do nghỉ của bản ghi nghỉ(Khóa chính)", "data type":"text"},
#             {"name": "status", "description": "Trạng thái của bản ghi.(status = 'Đã phê duyệt' hoặc status = 'Đã hủy')", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_mb_process_info",
#         "description": "Lưu trữ thông tin quá trình công tác tại MB. Một nhân viên có nhiều quá trình công tác tại MB → Mỗi quá trình công tác tại MB là 1 hàng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
#             {"name": "joincompanydate", "description": "Ngày vào làm việc tại MB", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "emptype", "description": "Đối tượng(loại nhân viên)", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
#             {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
#             {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
#             {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
#             {"name": "jobname", "description": "Chức danh", "data type":"text"},
#             {"name": "level", "description": "Level của nhân viên", "data type":"text"},
#             {"name": "positiongroup", "description": "Nhóm vị trí (thuộc nhóm nào)", "data type":"text"},
#             {"name": "documentno", "description": "Số Quyết Định", "data type":"text"},
#             {"name": "documenttype", "description": "Hình thức thay đổi", "data type":"text"},
#             {"name": "region", "description": "Khu vực", "data type":"text"},
#             {"name": "subregion", "description": "Vùng miền", "data type":"text"},
#             {"name": "flagstatus", "description": "ID của bản ghi", "data type":"text"},
#             {"name": "workprocessid", "description": "Trạng thái của bản ghi(Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_party_army_info",
#         "description": "Lưu trữ dữ liệu đảng, quân nhân của nhân viên",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "partydate", "description": "Ngày vào Đảng (dự bị)", "data type":"text"},
#             {"name": "partyofficialdate", "description": "Ngày vào Đảng chính thức", "data type":"text"},
#             {"name": "partyplace", "description": "Nơi kết nạp", "data type":"text"},
#             {"name": "armyjoin", "description": "Ngày vào quân nhân", "data type":"text"},
#             {"name": "armylevel", "description": "Cấp bậc quân hàm", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_pre_mb_process_info",
#         "description": "Lưu trữ thông tin quá trình công tác trước MB. Một nhân viên có nhiều quá trình công tác trước MB → Mỗi quá trình công tác trước MB là 1 dòng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "organizationname", "description": "Đơn vị công tác", "data type":"text"},
#             {"name": "positionname", "description": "Chức danh", "data type":"text"},
#             {"name": "mission", "description": "Nhiệm vụ chính", "data type":"text"},
#             {"name": "reasonleave", "description": "Lý do chuyển", "data type":"text"},
#             {"name": "rewardinfo", "description": "Thông tin khen thưởng", "data type":"text"},
#             {"name": "decpline", "description": "Thông tin kỷ luật", "data type":"text"},
#             {"name": "flagstatus", "description": "ID bản ghi ghi", "data type":"text"},
#             {"name": "workedoutsideid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_rating_process_info",
#         "description": "Lưu trữ thông tin quá trình đánh giá. Một nhân viên có nhiều quá trình đánh giá → Mỗi quá trình đánh giá là 1 hàng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính 1)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
#             {"name": "periodname", "description": "Kỳ đánh giá(Khóa chính 2)", "data type":"text"},
#             {"name": "resultfinal", "description": "Điểm xếp loại", "data type":"text"},
#             {"name": "ratingafter", "description": "Xếp loại sau phân bổ", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_reward_process_info",
#         "description": "Lưu trữ thông tin quá trình khen thưởng. Một nhân viên có nhiều quá trình khen thưởng → Mỗi quá trình khen thưởng là 1 dòng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "rewardtype", "description": "Loại khen thưởng", "data type":"text"},
#             {"name": "rewardrecord", "description": "Danh hiệu khen thưởng", "data type":"text"},
#             {"name": "documentnumber", "description": "Số quyết định", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày hiệu lực", "data type":"text"},
#             {"name": "reason", "description": "Lý do khen thưởng", "data type":"text"},
#             {"name": "flagstatus", "description": "ID bản ghi", "data type":"text"},
#             {"name": "rewardrecordid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"}
#         ]
#     },

# ]

# print((instruction.format(table_schemas=table_schemas)))

@dataclass
class UserIntent:
    """
    is_hcm_related: True - Câu hỏi liên quan đến HCM (dựa trên các bảng thông tin có trong table_schema)
    """
    is_hcm_related: bool

from beegenerate.loggings.loggers import lf

instruction=f"""
    ### BỐI CẢNH ###
    Bạn là hệ thống phân loại câu hỏi của MB HCM. Nhiệm vụ của bạn là xác định xem câu hỏi của người dùng có liên quan đến thông tin cá nhân của hay không.

    ### QUY TẮC PHÂN LOẠI ###
    **Trả về TRUE nếu câu hỏi liên quan đến:**
    - Thông tin cơ bản của nhân sự (họ và tên, ngày sinh, chức vụ, đơn vị,..)
    - Quá trình công tác tại MB (thời  gian công tác, tên vị trí công tác,...)
    - Quá trình kiêm nhiệm (các chức vụ kiêm nhiệm khi làm việc)
    - Thông tin hợp đồng lao động (thời hạn lao động, nội dung lao động,..)
    - Bằng cấp, chứng chỉ (thông tin bằng cấp, chứng chỉ của người lao động)
    - Thông tin ngày phép, nghỉ phép 
    - Đánh giá nhân viên (xếp loại của nhân viên, kì đánh giá)
    - Khen thưởng, kỷ luật 
    - Thông tin Đảng, quân nhân (ngày vào đảng, ngày nhập ngũ,...)
    - Quá trình công tác trước MB (trước đây làm ở đâu?)
    - Các thông tin liên quan đế CÁ NHÂN khác của người dùng

    **Trả về FALSE nếu câu hỏi:**
    - Các câu hỏi chung chung, không liên quan
    - Và tất cả các thông tin KHÔNG liên quan còn lại tới bất kì thông tin nào bên trên!

    ### ĐẦU RA ###
    Chỉ trả về JSON với một trường boolean:
    {{
    "is_hcm_related": true/false
    }}

    Ví dụ:
    - "Tôi còn bao nhiêu ngày phép?" -> {{"is_hcm_related": true}}
    - "Chào bạn" -> {{"is_hcm_related": false}}
    - "Thông tin nhân viên Nguyễn Văn A" -> {{"is_hcm_related": true}}
    - "Thời tiết hôm nay thế nào?" -> {{"is_hcm_related": false}}
    """

def create_hcm_calssify_agent(model) -> Agent:
    print("=== Starting create_hcm_calssify_agent ===")
    print(f"Input model type: {type(model)}")

    try:
        print("Attempting to fetch BEEHI_HCM_CLASSIFY prompt from langfuse...")
        BEEHI_HCM_CLASSIFY= lf.get_prompt(name="BEEHI_HCM_CLASSIFY").prompt
        print(" Successfully fetched langfuse context: ", BEEHI_HCM_CLASSIFY[:100] + "..." if len(BEEHI_HCM_CLASSIFY) > 100 else BEEHI_HCM_CLASSIFY)
    except Exception as e:
        print(f"!!! Failed to fetch langfuse prompt: {str(e)}")
        print("Using default instruction instead")
        BEEHI_HCM_CLASSIFY= instruction
        print(f"Using default instruction, length: {len(BEEHI_HCM_CLASSIFY)}")

    print("Creating Agent with the following parameters:")
    print(f"  - Name: HCM classify")
    print(f"  - Model: {model}")
    print(f"  - Output type: {UserIntent}")
    print(f"  - Instructions length: {len(BEEHI_HCM_CLASSIFY)}")

    try:
        agent = Agent(
            name="HCM classify",
            model=model,
            instructions=BEEHI_HCM_CLASSIFY,
            output_type=UserIntent
        )
        print("=== Agent created successfully ===")
        return agent
    except Exception as e:
        print(f"!!! ERROR creating agent: {str(e)}")
        print(f"!!! Error type: {type(e)}")
        raise  # Re-raise the exception after logging


# async def main():
#     hcm_calssify_agent = Agent(
#         name="HCM classify",
#         model=LitellmModel(
#             model="gpt-4.1",
#             api_key="REPLACE_WITH_LOCAL_SECRET",
#             base_url="https://llm-gateway-dev.mbbank.com.vn"
#         ),
#         instructions=instruction.format(
#             table_schemas=table_schemas
#             ),
#         output_type=CheckOutput
#     )
#     result = await Runner.run(
#         starting_agent=hcm_calssify_agent, 
#         input="tôi tên là gì?",
#         )
#     print(result)
#     print(result.final_output.is_db_query)
#     if result.final_output.is_db_query:
#         print("Oke")

# if __name__ == "__main__":
#     asyncio.run(main())
