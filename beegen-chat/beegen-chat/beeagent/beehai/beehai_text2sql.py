from agents import Agent, RunContextWrapper

from ..llms_extend.litellm import litellm_model
from .context import UserInfo


def instructions(
    context: RunContextWrapper[UserInfo], agent: Agent[UserInfo]
) -> str:
    def get_few_shot_examples():
        return [
            {
                "nl": "How many active users are currently assigned to projects?",
                "sql": (
                    "SELECT COUNT(*)\n"
                    "FROM public.beehi_user_info_jsonb\n"
                    "WHERE is_active_on_project = TRUE;"
                )
            },
            {
                "nl": "List full names and join dates of users whose latest evaluation score is above 90.",
                "sql": (
                    "SELECT full_name, join_company_date\n"
                    "FROM public.beehi_user_info_jsonb\n"
                    "WHERE latest_eval_score > 90;"
                )
            }
        ]

    # Full schema DDL with comments
    SCHEMA_DDL = """
    CREATE TABLE public.beehi_user_info_jsonb
    (
        id                        serial PRIMARY KEY,
        username                  varchar(255) NOT NULL UNIQUE,
        employee_id               varchar(64)  NOT NULL,
        employee_code             varchar(64)  NOT NULL,
        full_name                 varchar(255) NOT NULL,
        date_of_birth             date,
        join_company_date         date,
        current_job_name          varchar(255),
        current_org_manage        varchar(255),
        current_level             varchar(255),
        current_position_group    varchar(255),
        current_contract_type     varchar(255),
        current_contract_end_date date,
        latest_eval_period        varchar(255),
        latest_eval_score         numeric,
        is_active_on_project      boolean,
        current_project_count     integer,
        degrees_and_certs         jsonb,
        party_army_info           jsonb,
        work_history_external     jsonb,
        work_history_mb           jsonb,
        projects                  jsonb,
        contracts                 jsonb,
        evaluations               jsonb,
        training                  jsonb,
        rewards                   jsonb,
        leave_history             jsonb
    );

    comment on table public.beehi_user_info_jsonb is 'Bảng thông tin người dùng hợp nhất với cả các trường trạng thái hiện tại và dữ liệu lịch sử JSONB.';
    comment on column public.beehi_user_info_jsonb.username is 'Tên đăng nhập người dùng được đồng bộ từ keycloak MB về HCM.';
    comment on column public.beehi_user_info_jsonb.employee_id is 'ID của nhân viên tại HCM.';
    comment on column public.beehi_user_info_jsonb.employee_code is 'Mã nhân viên.';
    comment on column public.beehi_user_info_jsonb.full_name is 'Họ tên của nhân viên.';
    comment on column public.beehi_user_info_jsonb.date_of_birth is 'Ngày sinh của nhân viên.';
    comment on column public.beehi_user_info_jsonb.join_company_date is 'Ngày vào MB.';
    comment on column public.beehi_user_info_jsonb.current_job_name is 'Chức danh công việc hiện tại của người dùng tại MB.';
    comment on column public.beehi_user_info_jsonb.current_org_manage is 'Đơn vị quản lý hiện tại của người dùng.';
    comment on column public.beehi_user_info_jsonb.current_level is 'Cấp bậc hiện tại của người dùng.';
    comment on column public.beehi_user_info_jsonb.current_position_group is 'Nhóm vị trí hiện tại của người dùng.';
    comment on column public.beehi_user_info_jsonb.current_contract_type is 'Loại hợp đồng hiện tại của người dùng.';
    comment on column public.beehi_user_info_jsonb.current_contract_end_date is 'Ngày kết thúc hợp đồng hiện tại của người dùng.';
    comment on column public.beehi_user_info_jsonb.latest_eval_period is 'Kỳ đánh giá gần nhất của người dùng.';
    comment on column public.beehi_user_info_jsonb.latest_eval_score is 'Điểm xếp loại gần nhất của người dùng.';
    comment on column public.beehi_user_info_jsonb.is_active_on_project is 'True nếu người dùng hiện đang được chỉ định cho bất kỳ dự án đang hoạt động nào.';
    comment on column public.beehi_user_info_jsonb.current_project_count is 'Tổng số dự án mà người dùng hiện đang tham gia.';
    comment on column public.beehi_user_info_jsonb.degrees_and_certs is 'Mảng JSON hoàn chỉnh của tất cả bằng cấp và chứng chỉ của người dùng.';
    comment on column public.beehi_user_info_jsonb.party_army_info is 'Mảng JSON hoàn chỉnh của tất cả thông tin đảng và quân nhân của người dùng.';
    comment on column public.beehi_user_info_jsonb.work_history_external is 'Mảng JSON hoàn chỉnh của tất cả quá trình công tác trước MB của người dùng.';
    comment on column public.beehi_user_info_jsonb.work_history_mb is 'Mảng JSON hoàn chỉnh của tất cả quá trình công tác tại MB của người dùng.';
    comment on column public.beehi_user_info_jsonb.projects is 'Mảng JSON hoàn chỉnh của tất cả các dự án mà người dùng đã tham gia.';
    comment on column public.beehi_user_info_jsonb.contracts is 'Mảng JSON hoàn chỉnh của tất cả quá trình hợp đồng của người dùng.';
    comment on column public.beehi_user_info_jsonb.evaluations is 'Mảng JSON hoàn chỉnh của tất cả quá trình đánh giá của người dùng.';
    comment on column public.beehi_user_info_jsonb.training is 'Mảng JSON hoàn chỉnh của tất cả quá trình đào tạo của người dùng.';
    comment on column public.beehi_user_info_jsonb.rewards is 'Mảng JSON hoàn chỉnh của tất cả quá trình khen thưởng của người dùng.';
    comment on column public.beehi_user_info_jsonb.leave_history is 'Mảng JSON hoàn chỉnh của tất cả thông tin quản lý nghỉ của người dùng.';

    ALTER TABLE public.beehi_user_info_jsonb
        OWNER TO hr_information;
    """

    # One example row (as JSON-like string)
    SAMPLE_ROW = """
    {
        "id": 157,
        "username": "phamtphong401",
        "employee_id": "MB00000155",
        "employee_code": "MB00000155",
        "full_name": "Phạm Tiến Phong",
        "date_of_birth": "1982-06-17",
        "join_company_date": "2020-08-28",
        "current_job_name": "Chuyên viên cao cấp",
        "current_org_manage": "Khối Kế toán tài chính",
        "current_level": "Chuyên viên cao cấp",
        "current_position_group": "Nhân viên",
        "current_contract_type": "Hợp đồng lao động không xác định thời hạn",
        "current_contract_end_date": null,
        "latest_eval_period": "Năm 2024",
        "latest_eval_score": 92,
        "is_active_on_project": false,
        "current_project_count": 2,
        "degrees_and_certs": [{"school": "Đại học Kinh tế Quốc dân", "to_date": "2010-06-06", "cert_type": "Degree", "faculities": "Tài chính ngân hàng", "major_level": "Đại học", "certificate_name": "Cử nhân Kinh tế", "certificate_place": "Hà Nội", "certificate_result": "Giỏi"}, {"school": "Đại học Bách khoa TP.HCM", "to_date": "2017-05-24", "cert_type": "Certificate", "faculities": "Quản lý", "major_level": "Chứng chỉ", "validity_period": "5 năm", "certificate_name": "Lãnh đạo", "certificate_place": "Hà Nội", "certificate_result": "Xuất sắc"}],
        "party_army_info": [{"army_rank": null, "army_join_date": null, "party_location": "MB", "party_join_date": "2019-03-25", "party_official_date": "2020-03-24"}],
        "work_history_external": [{"mission": "Thực hiện các công việc chuyên môn theo phân công", "to_date": "2017-03-29", "decpline": null, "from_date": "2013-10-10", "reward_info": null, "reason_leave": "Mức lương tốt hơn", "position_name": "Chuyên viên tín dụng", "organization_name": "Techcombank"}, {"mission": "Thực hiện các công việc chuyên môn theo phân công", "to_date": "2013-08-02", "decpline": null, "from_date": "2013-02-19", "reward_info": null, "reason_leave": "Tìm cơ hội phát triển tốt hơn", "position_name": "Chuyên viên CSKH", "organization_name": "Sacombank"}],
        "work_history_mb": [{"level": "Nhân viên", "region": "North", "to_date": "2022-04-02", "job_name": "Nhân viên", "from_date": "2020-10-21", "subregion": "Hanoi", "document_no": null, "seniority_MB": 0, "document_type": "Thăng tiến", "emp_type_code": "Chính thức", "pos_seniority": 4, "position_group": "Nhân viên", "org_name_level1": "Phòng Vận hành IT", "org_name_level2": null, "org_name_level3": null, "org_name_manage": "Khối Công nghệ thông tin", "join_campany_date": "2020-08-28"}, {"level": "Chuyên viên", "region": "North", "to_date": "2024-01-04", "job_name": "Chuyên viên", "from_date": "2022-07-17", "subregion": "Hanoi", "document_no": "193/QĐ-HS", "seniority_MB": 2, "document_type": "Tuyển dụng", "emp_type_code": "Chính thức", "pos_seniority": 2, "position_group": "Nhân viên", "org_name_level1": "Phòng Truyền thông", "org_name_level2": null, "org_name_level3": null, "org_name_manage": "Khối Marketing", "join_campany_date": "2020-08-28"}, {"level": "Chuyên viên cao cấp", "region": "North", "to_date": null, "job_name": "Chuyên viên cao cấp", "from_date": "2024-06-13", "subregion": "Hanoi", "document_no": "514/QĐ-HS", "seniority_MB": 4, "document_type": "Bổ nhiệm", "emp_type_code": "Chính thức", "pos_seniority": 4, "position_group": "Nhân viên", "org_name_level1": "Phòng Kiểm soát hoạt động", "org_name_level2": null, "org_name_level3": null, "org_name_manage": "Khối Kiểm soát nội bộ", "join_campany_date": "2020-08-28"}],
        "projects": [],
        "contracts": [{"to_date": "2020-10-27", "from_date": "2020-08-28", "contract_type": "Hợp đồng thử việc", "contract_number": "TV2684"}, {"to_date": "2021-10-27", "from_date": "2020-10-27", "contract_type": "Hợp đồng lao động có thời hạn", "contract_number": "HD8142"}, {"to_date": null, "from_date": "2021-10-27", "contract_type": "Hợp đồng lao động không xác định thời hạn", "contract_number": "KTH2530"}],
        "evaluations": [{"period_code": "Kỳ 1.2020", "rating_after": "A", "result_final": 98}, {"period_code": "Năm 2020", "rating_after": "B", "result_final": 106}, {"period_code": "Kỳ 1.2021", "rating_after": "A+", "result_final": 108}, {"period_code": "Năm 2021", "rating_after": "C", "result_final": 103}, {"period_code": "Kỳ 1.2022", "rating_after": "A+", "result_final": 97}, {"period_code": "Năm 2022", "rating_after": "B", "result_final": 108}, {"period_code": "Kỳ 1.2023", "rating_after": "A", "result_final": 121}, {"period_code": "Năm 2023", "rating_after": "B", "result_final": 104}, {"period_code": "Kỳ 1.2024", "rating_after": "A+", "result_final": 113}, {"period_code": "Năm 2024", "rating_after": "A", "result_final": 112}],
        "training": [{"status": "Đạt", "end_time": "2023-09-28", "start_time": "2023-09-21", "edu_prog_name": "Quản lý thời gian", "edu_contract_type": "External", "key_learning_point": "Nâng cao kiến thức chuyên môn và kỹ năng mềm"}, {"status": "Đạt", "end_time": "2022-09-30", "start_time": "2022-09-02", "edu_prog_name": "Đào tạo tân nhân viên", "edu_contract_type": "External", "key_learning_point": "Nâng cao kiến thức chuyên môn và kỹ năng mềm"}, {"status": "Đạt", "end_time": "2021-11-30", "start_time": "2021-11-12", "edu_prog_name": "Excel nâng cao", "edu_contract_type": "External", "key_learning_point": "Nâng cao kiến thức chuyên môn và kỹ năng mềm"}],
        "rewards": [{"reason": "Có thành tích nổi bật trong công việc", "from_date": "2021-12-13", "reward_type": "Thành tích", "reward_record": "Nhân viên tiêu biểu", "document_number": "702/QĐ-KT"}, {"reason": "Có thành tích nổi bật trong công việc", "from_date": "2023-12-16", "reward_type": "Đột xuất", "reward_record": "Có thành tích nổi bật", "document_number": "550/QĐ-KT"}, {"reason": "Có thành tích nổi bật trong công việc", "from_date": "2021-05-20", "reward_type": "Định kỳ", "reward_record": "Gương mẫu trong công việc", "document_number": "478/QĐ-KT"}],
        "leave_history": [{"status": "Đã phê duyệt", "to_time": "2024-08-15 17:00", "from_time": "2024-08-15 17:00", "used_days": 0.5, "leave_type": "Nghỉ ốm", "remain_days_in_year": 14}, {"status": "Chờ phê duyệt", "to_time": "2024-11-09 17:30", "from_time": "2024-11-06 09:00", "used_days": 4, "leave_type": "Nghỉ tang", "remain_days_in_year": 19}, {"status": "Chờ phê duyệt", "to_time": "2023-02-18 17:30", "from_time": "2023-02-14 08:30", "used_days": 5, "leave_type": "Nghỉ cưới", "remain_days_in_year": 13}, {"status": "Đã phê duyệt", "to_time": "2024-05-15 17:30", "from_time": "2024-05-11 16:00", "used_days": 5, "leave_type": "Nghỉ tang", "remain_days_in_year": 5}, {"status": "Chờ phê duyệt", "to_time": "2024-06-11 14:00", "from_time": "2024-06-11 14:00", "used_days": 0.5, "leave_type": "Nghỉ phép", "remain_days_in_year": 10}, {"status": "Chờ phê duyệt", "to_time": "2024-01-29 17:30", "from_time": "2024-01-29 15:00", "used_days": 1, "leave_type": "Nghỉ ốm", "remain_days_in_year": 13}, {"status": "Chờ phê duyệt", "to_time": "2024-01-16 17:30", "from_time": "2024-01-15 17:00", "used_days": 2, "leave_type": "Nghỉ phép", "remain_days_in_year": 10}, {"status": "Đã phê duyệt", "to_time": "2024-01-16 17:30", "from_time": "2024-01-15 14:30", "used_days": 2, "leave_type": "Nghỉ ốm", "remain_days_in_year": 8}, {"status": "Đã phê duyệt", "to_time": "2024-04-24 17:30", "from_time": "2024-04-23 09:00", "used_days": 2, "leave_type": "Nghỉ phép", "remain_days_in_year": 20}, {"status": "Chờ phê duyệt", "to_time": "2024-04-13 17:30", "from_time": "2024-04-12 09:00", "used_days": 2, "leave_type": "Nghỉ phép", "remain_days_in_year": 20}]
    }
    """

    def build_prompt(schema: str, sample: str, examples: list) -> str:
        lines = [
            "You are a PostgreSQL expert. Given the schema, sample data, and user question, generate a valid SQL SELECT query. Output only the SQL."
            "Instructions must follow:"
            "- Only use schema, tables that provided. DO NOT use information that does not exist."
            "- Only generate query that use read permission. Even if user asked, DO NOT try to add/edit/delete anything.",
            "",
            "-- Schema DDL --",
            schema,
            "",
            "-- Sample Row --",
            sample,
            "",
            "-- Examples --"
        ]
        for ex in examples:
            lines.append(f"-- NL: {ex['nl']}\n{ex['sql']}")
        lines.append("")
        return "\n".join(lines)

    examples = get_few_shot_examples()

    # Stage 1: full context
    final_prompt = build_prompt(SCHEMA_DDL, SAMPLE_ROW, examples)

    return f"""
    # User's information
    Name: {context.context.name}
    Username: {context.context.username}

    # Instructions
    {final_prompt}
"""


# Remember to assign MCP to agent
text2sql_agent = Agent[UserInfo](
    name="SQL Expert",
    model=litellm_model,
    instructions=instructions,
)
