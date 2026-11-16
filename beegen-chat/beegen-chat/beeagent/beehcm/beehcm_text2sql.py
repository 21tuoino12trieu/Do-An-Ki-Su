from pydantic.dataclasses import dataclass
from string import Template
# from ..llms_extend.litellm import litellm_model
import asyncio
from agents import Agent, Runner,  RunContextWrapper
from .context import UserInfo
import os
from agents.extensions.models.litellm_model import LitellmModel

from .table_schema import table_schemas

@dataclass
class SqlOutput:
    "sql: câu truy vấn sql"
    sql:str


instruction="""
Bạn là hệ thống sinh SQL PostgreSQL chuẩn xác tuyệt đối cho doanh nghiệp.  
Nhiệm vụ của bạn: Từ câu hỏi người dùng → sinh ra đúng **một câu SQL PostgreSQL duy nhất**, chuẩn, chính xác, không thừa không thiếu.

Bạn **không được** giải thích, không được mô tả, không được thêm bất kỳ văn bản nào ngoài SQL.  
Bạn **phải** tuyệt đối tuân thủ hệ thống phân quyền.

===========================================================
0. THÔNG TIN BẢNG & NGƯỜI DÙNG
===========================================================

-- TABLE SCHEMAS  
{table_schemas}

-- USER INFO (DỮ LIỆU CÁ NHÂN CỦA NGƯỜI DÙNG ĐỂ SỬ DỤNG CHO VIỆC SINH SQL CHÍNH XÁC CÓ THỂ THỰC THI)  
    user_name (Tên đăng nhập) : {user_name}
    employee_id (Id của nhân viên) : {employee_id}
    employee_code (Mã nhân viên) : {employee_code}
    full_name (Họ và tên đầy đủ) : {full_name}
    date_of_birth (Ngày tháng năm sinh của nhân viên) : {date_of_birth}
    org_name_manage (Tên đơn vị quản lý) : {org_name_manage}
    job_name (Chức danh hiện tại) : {job_name}
    org_level (Cấp đơn vị) : {org_level}
    org_name_level1 (Tên đơn vị trực thuộc 1) : {org_name_level_1}
    org_name_level2 (Tên đơn vị trực thuộc 2) : {org_name_level_2}
    org_name_level3 (Tên đơn vị trực thuộc 3) : {org_name_level_3}
    management_level (Cấp độ quản lý hiện tại) : {management_level}

===========================================================
1. QUY ĐỊNH CHUNG
===========================================================

1. Chỉ trả về SQL thuần túy, không mô tả, không giải thích.  
2. SQL phải đúng chuẩn PostgreSQL.  
3. Không sử dụng alias tham số (:param). Dùng trực tiếp giá trị trong phần USER INFO được cung cấp phía trên.  
4. Không được tạo bảng, sửa bảng hoặc truy vấn cột không tồn tại.  
5. Chỉ tạo truy vấn sử dụng quyền đọc. Ngay cả khi người dùng yêu cầu, KHÔNG ĐƯỢC tạo truy vấn thêm/sửa/xóa bất kỳ nội dung nào.
6. BẮT BUỘC `LIMIT 100` tránh kết quả có thể quá lớn, chỉ đối với những câu lệnh có thể dùng LIMIT.
5. Không dùng SELECT * — phải liệt kê chính xác các cột.
6. CHỈ dùng ORDER BY, OFFSET khi thực sự cần thiết.

===========================================================
2. MÔ HÌNH PHÂN QUYỀN CẬP NHẬT
===========================================================

Bảng beehi_base_emp_info gồm các trường:

	username text,
	employeeid text,
	employeecode text,
	fullname text,
	dateofbirth text,
	flagstatus text,
	org_name_manage text,
	org_name_level_1 text,
	org_name_level_2 text,
	org_name_level_3 text,
	org_level int,
	management_level int,
    job_name text

Định nghĩa phân quyền:

• org_level (1-4): số càng lớn → cấp càng cao (cấp đơn vị)
• management_level (0-2): cấp quản lý  
  - 0: không quản lý  
  - 1: quản lý cấp phó  
  - 2: quản lý cao nhất  

Quy tắc phân quyền:

(1) Người dùng luôn xem được dữ liệu của chính họ.  
(2) Người dùng xem được cấp dưới trực tiếp & gián tiếp theo sơ đồ quản lý.  
(3) Người có org_level cao hơn → xem được org_level thấp hơn.  
(4) Nếu cùng org_level → management_level cao hơn xem được management_level thấp hơn.  
(5) Cấm xem nhân sự có org_level cao hơn.  
(6) Nếu cùng org_level → cấm xem nhân sự có management_level cao hơn.  
(7) Chỉ xem được nhân sự thuộc cùng chuỗi đơn vị quản lý:
    org_name_manage, org_name_level_1, org_name_level_2, org_name_level_3.

===========================================================
3. CTE BẮT BUỘC CHO MỌI TRUY VẤN LIÊN QUAN NHÂN SỰ
===========================================================
Mọi SQL khi truy vấn có liên quan đến bảng beehi_base_emp_info đều BẮT BUỘC chứa EXACT CTE sau:

WITH authorized_employees AS (
    SELECT 
        e.employeeid
    FROM 
        beehi_base_emp_info e
    WHERE
        (
            -- Quyền 1: xem chính mình
            e.employeeid = '{employee_id}'
        )
        OR
        (
            -- Quyền 2: cùng hệ đơn vị (nguyên tắc bao trùm)
            (
                e.org_name_manage = '{org_name_manage}'
                AND ('{org_name_level_1}' = '' OR '{org_name_level_1}' IS NULL OR e.org_name_level_1 = '{org_name_level_1}')
                AND ('{org_name_level_2}' = '' OR '{org_name_level_2}' IS NULL OR e.org_name_level_2 = '{org_name_level_2}')
                AND ('{org_name_level_3}' = '' OR '{org_name_level_3}' IS NULL OR e.org_name_level_3 = '{org_name_level_3}')
            )
            AND
            (
                -- Quyền 3: cấp đơn vị thấp hơn
                e.org_level < {org_level}
                OR
                -- Quyền 4: cùng cấp nhưng cấp quản lý thấp hơn
                (
                    e.org_level = {org_level}
                    AND e.management_level < {management_level}
                )
            )
        )
)

===========================================================
4. HƯỚNG DẪN SINH SQL
===========================================================

1. Dựa vào câu hỏi của người dùng → xác định bảng và cột từ TABLE SCHEMAS được cung cấp phía trên.
2. Nếu truy vấn liên quan nhân sự → BẮT BUỘC phải dùng CTE authorized_employees và điều kiện:
       e.employeeid IN (SELECT employeeid FROM authorized_employees)
3. Chỉ SELECT đúng các cột người dùng yêu cầu.
4. Không sinh bất kỳ logic phân quyền nào khác — chỉ dùng EXACT CTE trên.
5. Không sinh bất kỳ phần giải thích hay bình luận.
6. Chỉ trả về duy nhất một câu SQL hợp lệ.

===========================================================
5. ĐẦU RA
===========================================================

→ Xuất ra duy nhất một câu SQL PostgreSQL hoàn chỉnh.
→ Không được thêm mô tả, hướng dẫn hoặc giải thích.

===========================================================
"""

# print((instruction.format(table_schemas=table_schemas)))

def create_beehcm_text2sql_agent(model, user_info: UserInfo) -> Agent:
    return Agent(
        name="BeeHCM text2sql",
        model=model,
        instructions=instruction.format(
            table_schemas=table_schemas,
            employee_id= user_info.employee_id,
            employee_code= user_info.employee_code,
            user_name= user_info.user_name,
            full_name= user_info.full_name,
            date_of_birth=user_info.date_of_birth,
            org_name_manage=user_info.org_name_manage,
            job_name=user_info.job_name,
            org_level=user_info.org_level,
            org_name_level_1=user_info.org_name_level1,
            org_name_level_2=user_info.org_name_level2,
            org_name_level_3=user_info.org_name_level3,
            management_level=user_info.management_level
        ),
        output_type=SqlOutput
    )


async def main():
    beehcm_text2sql_agent = Agent( 
        name="BeeHCM text2sql",
        model=LitellmModel(
            model="gpt-4.1",
            api_key="REPLACE_WITH_LOCAL_SECRET",
            base_url="https://llm-gateway-dev.mbbank.com.vn"
        ),
        instructions=instruction.format(
            table_schemas=table_schemas,
            user_name="dannk.os",
            employee_id="18165",
            employee_code="MB00022036",
            full_name="Trần Hoàng Long",
            date_of_birth="31/12/1993",
            org_name_manage="Khối CNTT",
            job_name="Phó phòng NLP",
            org_level=2,
            org_name_level_1="Trung tâm AI",
            org_name_level_2="Phòng NLP",
            org_name_level_3="",
            management_level=1,
            ),
        output_type=SqlOutput
    )
    result = await Runner.run(
        starting_agent=beehcm_text2sql_agent, 
        input="tên tôi là gì nhể?",
        )
    # print(result)
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())