# -*- coding: utf-8 -*-
"""Run direct SQL correction/execution cases against Text2SqlBot.

Run from repo root:
    python test/text2sql/bot_text2sql_test_runner.py
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


BOT_ID = "097a3a10-cf7e-4f2d-b9ae-87cedcb15ff4"
ROLE_IDS = ["TCKT"]
OUTPUT_PATH = Path("test/text2sql/bot_text2sql_test_results.json")
TURN_TIMEOUT_SECONDS = 120

METADATA = {
    "TableDomain": [
        {"schemaName": "apps", "tableName": "FIN_RPT_GIAOBAN_TOAN_HANG_POC"},
        {"schemaName": "apps", "tableName": "FIN_RPT_CEO_DAILY_POC"},
        {"schemaName": "apps", "tableName": "FIN_GUARANTEE_SMY_MONTHLY_POC"},
        {"schemaName": "apps", "tableName": "REP_TOI_FINAL_TT_KH_POC"},
        {"schemaName": "apps", "tableName": "FIN_HDV_SMY_MONTHLY_POC"},
        {"schemaName": "apps", "tableName": "FIN_LOAN_SMY_MONTHLY_POC"},
        {"schemaName": "apps", "tableName": "FIN_SMY_CUSTOMER_MONTHLY_POC"},
    ]
}


def case(
    category: str,
    name: str,
    question: str,
    expected: str,
    messages: list[dict] | None = None,
    turns: list[str] | None = None,
) -> dict:
    result = {
        "category": category,
        "name": name,
        "question": question,
        "expected": expected,
    }
    if messages:
        result["messages"] = messages
    if turns:
        result["turns"] = turns
    return result


def format_answer_for_review(answer: str) -> dict:
    answer = answer or ""
    return {
        "answer": answer,
        "answer_lines": answer.splitlines(),
        "answer_markdown": f"\n{answer}\n" if answer else "",
    }


TEST_CASES = [
    case(
        "direct_sql_no_execute",
        "uat_001_valid_sql_preserved",
        """Kiểm tra câu SQL sau:
SELECT COUNT(DISTINCT MAKH) AS so_luong_khach_hang
FROM APPS.FIN_GUARANTEE_SMY_MONTHLY_POC
WHERE EXTRACT(MONTH FROM TRANSACTION_DATE) = 6
  AND EXTRACT(YEAR FROM TRANSACTION_DATE) = 2025
  AND SODU_BL_THOIDIEM > 0""",
        "UAT 1: SQL Oracle hợp lệ phải được giữ nguyên, đặc biệt bộ lọc EXTRACT; không thực thi.",
    ),
    case(
        "direct_sql_execute",
        "uat_002_valid_sql_execute",
        """Chạy câu SQL sau:
SELECT COUNT(DISTINCT MAKH)
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')""",
        "UAT 2: giữ nguyên SQL, thực thi thành công và trả kết quả 1000.",
    ),
    case(
        "direct_sql_repair_execute",
        "uat_024_repair_missing_to_date_parenthesis",
        """Chạy câu SQL sau:
SELECT KHOI, SUM(DUNO_THOIDIEM_VND)/1e9
FROM APPS.FIN_LOAN_SMY_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD'
GROUP BY KHOI""",
        "Dựa trên UAT 24: chỉ đóng ngoặc TO_DATE, giữ nguyên biểu thức SUM rồi thực thi.",
    ),
    case(
        "direct_sql_no_execute",
        "uat_028_valid_cte_preserved",
        """Kiểm tra câu SQL sau:
WITH base AS (
    SELECT COUNT(DISTINCT LD_ID) AS slhd_noxau,
           SUM(DUNO_THOIDIEM_VND) AS noxau
    FROM APPS.FIN_LOAN_SMY_MONTHLY_POC
    WHERE TRANSACTION_DATE = DATE '2025-06-30'
      AND CREDIT_STATUS IN ('3', '4', '5')
),
total AS (
    SELECT SUM(DUNO_THOIDIEM_VND) AS total_duno
    FROM APPS.FIN_LOAN_SMY_MONTHLY_POC
    WHERE TRANSACTION_DATE = DATE '2025-06-30'
)
SELECT b.slhd_noxau,
       ROUND(b.noxau / 1e9, 2) AS noxau,
       b.noxau / NULLIF(t.total_duno, 0) AS ty_le_phan_tram_du_no
FROM base b
CROSS JOIN total t""",
        "UAT 28: CTE/alias không bị nhận thành bảng vật lý; SQL hợp lệ được giữ nguyên và không chạy.",
    ),
    case(
        "direct_sql_execute",
        "uat_050_oracle_short_date_preserved",
        """Chạy câu SQL sau:
SELECT TXN_DATE, IND, IND_NAME, KHOI, VAL
FROM APPS.FIN_RPT_CEO_DAILY_POC
WHERE IND = 'BS_TONG_TS'
  AND TXN_DATE = '30jun25'""",
        "UAT 50: giữ nguyên literal ngày Oracle hợp lệ '30jun25' và thực thi.",
    ),
    case(
        "direct_sql_no_execute",
        "uat_081_identifier_case_insensitive",
        """Kiểm tra câu SQL sau:
SELECT VALUE/1e9
FROM apps.fin_rpt_giaoban_toan_hang_poc
WHERE MA_CT = 'LNTT'
  AND TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')""",
        "UAT 81: tên bảng không quote khác case vẫn khớp metadata; không tự đổi SQL và không chạy.",
    ),
    case(
        "direct_sql_execute",
        "uat_107_valid_group_by_execute",
        """Thực thi câu SQL sau:
SELECT KHOI, SUM(SODU_THOIDIEM_VND)/1e9
FROM APPS.FIN_HDV_SMY_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')
GROUP BY KHOI""",
        "UAT 107: SQL GROUP BY hợp lệ được giữ nguyên và thực thi thành công.",
    ),
    case(
        "direct_sql_no_execute",
        "uat_147_business_value_preserved",
        """Kiểm tra câu SQL sau:
SELECT SUM(DTTTRR_I)/1000000000 AS DOANHTHU_TY
FROM APPS.REP_TOI_FINAL_TT_KH_POC
WHERE TRANSACTION_DATE = '30jun25'
  AND CUS_STATUS = 'PRIVATE'""",
        "UAT 147: value nghiệp vụ PRIVATE và literal ngày phải được giữ nguyên; không thực thi.",
    ),
    case(
        "direct_sql_requested_dialect",
        "external_oracle_limit_repair_only",
        "Sửa theo Oracle, không thực thi: SELECT * FROM HR.EMPLOYEES LIMIT 10",
        "Bảng ngoài metadata: generic repair LIMIT sang Oracle; không lấy metadata chi tiết và không chạy.",
    ),
    case(
        "direct_sql_permission",
        "external_execute_blocked",
        "Chạy câu SQL sau: SELECT COUNT(*) FROM HR.EMPLOYEES",
        "SQL hợp lệ nhưng bảng ngoài quyền; phải trả SQL và lý do, tuyệt đối không thực thi.",
    ),
    case(
        "direct_sql_safety",
        "multi_statement_execute_blocked",
        (
            "Chạy các câu SQL sau: "
            "SELECT COUNT(*) FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC; "
            "SELECT COUNT(*) FROM APPS.FIN_LOAN_SMY_MONTHLY_POC;"
        ),
        "Giữ đủ hai statement, không gộp và không thực thi.",
    ),
    case(
        "direct_sql_safety",
        "malformed_multi_statement_repair_only",
        (
            "Sửa các câu SQL sau: "
            "SELECT COUNT(*) FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC WHERE MAKH IS NOT NULL; "
            "SELECT COUNT(*) FROM APPS.FIN_LOAN_SMY_MONTHLY_POC WHERE TRANSACTION_DATE = "
            "TO_DATE('2025-06-30', 'YYYY-MM-DD';"
        ),
        "Sửa dấu ngoặc còn thiếu, giữ đủ hai statement theo đúng thứ tự và không thực thi.",
    ),
    case(
        "direct_sql_safety",
        "dml_execute_blocked",
        (
            "Kiểm tra và không thực thi câu SQL sau: "
            "UPDATE APPS.FIN_SMY_CUSTOMER_MONTHLY_POC "
            "SET CUS_STATUS = 'ACTIVE' WHERE MAKH = '1'"
        ),
        "DML có thể được kiểm tra/sửa nhưng execute_requested=0 và is_read_only=0 nên không được thực thi.",
    ),
    case(
        "direct_sql_history",
        "uat_163_follow_up_execute",
        "Chạy câu SQL đó",
        "UAT 163: trích đúng SQL gần nhất từ phản hồi assistant và thực thi thành công.",
        messages=[
            {
                "role": "user",
                "content": "Kiểm tra giúp tôi câu SQL tính tổng số dư bảo lãnh.",
            },
            {
                "role": "assistant",
                "content": (
                    "SQL hợp lệ:\n```sql\n"
                    "SELECT SUM(SODU_BL_THOIDIEM)/1e9 AS TONG_SO_DU_BAO_LANH_TY\n"
                    "FROM APPS.FIN_GUARANTEE_SMY_MONTHLY_POC\n"
                    "WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')\n"
                    "```"
                ),
            },
            {"role": "user", "content": "Chạy câu SQL đó"},
        ],
    ),
    case(
        "direct_sql_value",
        "value_typo_requires_explicit_domain",
        """Sửa câu SQL sau:
SELECT COUNT(DISTINCT MAKH)
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')
  AND CUS_STATUS = 'ACTVE'""",
        (
            "Chỉ sửa ACTVE thành ACTIVE nếu metadata có tập value hợp lệ rõ ràng và "
            "một match duy nhất; nếu không phải giữ nguyên. Không thực thi."
        ),
    ),
    case(
        "direct_sql_requested_dialect",
        "internal_requested_dialect_conflict",
        """Chạy theo PostgreSQL câu SQL sau:
SELECT NVL(SUM(SODU_BL_THOIDIEM), 0) AS TONG_SO_DU
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')""",
        (
            "SQL đầu ra phải đổi NVL thành COALESCE theo PostgreSQL; metadata xác định "
            "database Oracle nên phải chặn thực thi và giải thích xung đột."
        ),
    ),
    case(
        "direct_sql_requested_dialect",
        "internal_requested_dialect_matches_metadata",
        """Chạy theo Oracle câu SQL sau:
SELECT COUNT(DISTINCT MAKH)
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')""",
        "Requested dialect trùng Oracle metadata: giữ SQL và được thực thi.",
    ),
    case(
        "direct_sql_ast",
        "uat_019_self_join_aliases_preserved",
        """Kiểm tra câu SQL sau:
SELECT
  t6.PHAN_KHUC,
  t6.APP_BIZ_STATUS,
  t5.APP_BIZ_STATUS,
  COUNT(DISTINCT t6.MAKH)
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC t5
JOIN APPS.FIN_SMY_CUSTOMER_MONTHLY_POC t6
  ON t5.MAKH = t6.MAKH
  AND t5.TRANSACTION_DATE = TO_DATE('2025-05-31', 'YYYY-MM-DD')
  AND t6.TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')
  AND t5.APP_BIZ_STATUS = 'NOTUSE'
  AND t6.APP_BIZ_STATUS = 'ACTIVE'
  AND t6.KHOI IN ('INDIV', 'NHS')
GROUP BY t6.PHAN_KHUC, t6.APP_BIZ_STATUS, t5.APP_BIZ_STATUS""",
        "UAT 19: giữ nguyên self-join và alias; chỉ nhận một bảng vật lý thuộc quyền; không chạy.",
    ),
    case(
        "direct_sql_ast",
        "uat_137_cte_window_function_preserved",
        """Kiểm tra câu SQL sau:
WITH t AS (
  SELECT TRANSACTION_DATE,
         CASE
           WHEN LOC_TERM >= 1 AND LOC_TERM < 6 THEN '1-6 tháng'
           WHEN LOC_TERM >= 6 AND LOC_TERM < 12 THEN '6-12 tháng'
           WHEN LOC_TERM >= 12 THEN 'trên 12 tháng'
           ELSE 'Khác'
         END AS KY_HAN_NHOM,
         SUM(DOANHSO_MO_MOI_VND) AS DOANHSO_MO_MOI_VND
  FROM APPS.FIN_HDV_SMY_MONTHLY_POC
  WHERE TRANSACTION_DATE BETWEEN TO_DATE('2025-01-31', 'YYYY-MM-DD')
                             AND TO_DATE('2025-06-30', 'YYYY-MM-DD')
    AND LOAIKYHAN = 'CKH'
    AND LOC_TERM > 0
  GROUP BY TRANSACTION_DATE,
           CASE
             WHEN LOC_TERM >= 1 AND LOC_TERM < 6 THEN '1-6 tháng'
             WHEN LOC_TERM >= 6 AND LOC_TERM < 12 THEN '6-12 tháng'
             WHEN LOC_TERM >= 12 THEN 'trên 12 tháng'
             ELSE 'Khác'
           END
),
t1 AS (
  SELECT t.*,
         ROW_NUMBER() OVER (
           PARTITION BY TRANSACTION_DATE
           ORDER BY DOANHSO_MO_MOI_VND DESC
         ) AS rn
  FROM t
)
SELECT * FROM t1 WHERE rn = 1""",
        "UAT 137: CTE/window function hợp lệ được giữ nguyên; CTE t/t1 không bị coi là bảng vật lý; không chạy.",
    ),
    case(
        "direct_sql_repair_only",
        "uat_029_repair_missing_select_comma",
        """Sửa câu SQL sau:
SELECT KHOI SUM(DUNO_THOIDIEM_VND) AS TONG_DU_NO
FROM APPS.FIN_LOAN_SMY_MONTHLY_POC
WHERE TRANSACTION_DATE = TO_DATE('2025-06-30', 'YYYY-MM-DD')
GROUP BY KHOI
ORDER BY SUM(DUNO_THOIDIEM_VND) DESC
FETCH FIRST 1 ROW ONLY""",
        "Dựa trên UAT 29: thêm đúng dấu phẩy giữa KHOI và SUM; giữ nguyên logic và không chạy.",
    ),
    case(
        "direct_sql_permission",
        "mixed_internal_external_tables_blocked",
        """Chạy câu SQL sau:
SELECT c.MAKH
FROM APPS.FIN_SMY_CUSTOMER_MONTHLY_POC c
JOIN HR.EMPLOYEES e ON e.EMPLOYEE_ID = c.MAKH""",
        "Có cả bảng nội bộ và bảng HR ngoài quyền: không lấy metadata HR và tuyệt đối không thực thi.",
    ),
    case(
        "direct_sql_history",
        "history_reference_without_sql",
        "Chạy câu SQL đó",
        "Không có SQL trong history: trả lời thiếu SQL và kết thúc direct flow, không tự sinh hoặc thực thi.",
    ),
    case(
        "non_chit_chat_data_query",
        "uat_003_natural_language_simple",
        "Tháng 6/2025 có bao nhiêu khách hàng đang active?",
        "UAT 3: route non_chit_chat, sinh SQL FIN_SMY_CUSTOMER_MONTHLY_POC với CUS_STATUS='ACTIVE' và trả kết quả 421.",
    ),
    case(
        "non_chit_chat_data_query",
        "uat_017_natural_language_complex_cte",
        (
            "Phân khúc nào có số khách hàng mới tháng 6/2025 cao nhất và hiển thị "
            "luôn % tăng trưởng số lượng khách hàng của phân khúc đó so với tháng 5?"
        ),
        (
            "UAT 17: route non_chit_chat, sinh CTE theo query chuẩn và trả CIB, "
            "tỷ lệ 0.03960396 (xấp xỉ 3.96%), chênh lệch 4."
        ),
    ),
    case(
        "chit_chat",
        "general_greeting",
        "Xin chào, bạn có thể giúp tôi những gì?",
        "Route chit_chat và giới thiệu khả năng hỗ trợ, không sinh hoặc thực thi SQL.",
    ),
    case(
        "metadata_qa",
        "list_accessible_tables",
        "Liệt kê toàn bộ các bảng dữ liệu mà tôi được phép truy cập.",
        "Route chit_chat metadata QA và chỉ liệt kê các bảng thuộc role/metadata hiện tại.",
    ),
    case(
        "analyze_history",
        "summarize_previous_answer",
        "Hãy tóm tắt và phân tích lại kết quả vừa rồi.",
        "Route analyze_history, chỉ phân tích nội dung lịch sử và không chạy lại SQL.",
        messages=[
            {
                "role": "user",
                "content": "Cuối tháng 6/2025 tổng dư nợ theo từng khối là bao nhiêu?",
            },
            {
                "role": "assistant",
                "content": (
                    "Kết quả trước đó có 5 khối; CIB có tổng dư nợ cao nhất, "
                    "tiếp theo là INDIV và SME."
                ),
            },
            {
                "role": "user",
                "content": "Hãy tóm tắt và phân tích lại kết quả vừa rồi.",
            },
        ],
    ),
    case(
        "export_file",
        "export_without_cached_sql",
        "Xuất kết quả truy vấn trước thành file CSV.",
        "Session mới chưa có SQL cache: route export_file và hướng dẫn người dùng truy vấn trước.",
    ),
    case(
        "draw_chart",
        "chart_without_cached_data",
        "Vẽ biểu đồ từ kết quả truy vấn vừa rồi.",
        "Session mới chưa có dữ liệu cache: route draw_chart và thông báo chưa đủ dữ liệu.",
    ),
    case(
        "export_file",
        "query_then_export_same_session",
        "Xuất kết quả vừa rồi thành file CSV.",
        "Turn 1 sinh/chạy SQL và lưu cache; turn 2 route export_file, chạy lại read-only với limit và trả link tải CSV.",
        turns=[
            "Cuối tháng 6/2025 tổng dư nợ tín dụng là bao nhiêu tỷ ở từng khối?",
            "Xuất kết quả vừa rồi thành file CSV.",
        ],
    ),
    case(
        "draw_chart",
        "query_then_chart_same_session",
        "Vẽ biểu đồ cột từ kết quả vừa rồi.",
        (
            "Turn 1 sinh/chạy SQL có 5 dòng và lưu cache; turn 2 route draw_chart, "
            "dùng đủ 5 dòng cached_data, kể cả khối FI có giá trị 0."
        ),
        turns=[
            "Cuối tháng 6/2025 tổng dư nợ tín dụng là bao nhiêu tỷ ở từng khối?",
            "Vẽ biểu đồ cột từ kết quả vừa rồi.",
        ],
    ),
]


def setup_env() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)


async def ask(bot, messages: list[dict], session_id: str) -> str:
    chunks = []
    async for chunk in bot.run(
        messages=messages,
        session_id=session_id,
        client_message_id=str(uuid.uuid4()),
        role_ids=ROLE_IDS,
        metadata=METADATA,
        username="bot_text2sql_test_runner",
    ):
        content = chunk.choices[0].delta.content if chunk.choices else ""
        if content:
            chunks.append(content)
    return "".join(chunks).strip()


async def main() -> None:
    setup_env()
    from beeportal.bot_text2sql.bot_v2 import Text2SqlBot

    bot = Text2SqlBot(bot_id=BOT_ID)
    results = []

    for index, test_case in enumerate(TEST_CASES, start=1):
        question = test_case["question"]
        turns = test_case.get("turns") or []
        messages = test_case.get("messages") or [{"role": "user", "content": question}]
        category = test_case["category"]
        name = test_case["name"]
        print(f"\n===== CASE {index}: {category}/{name} =====")
        print(f"Question: {turns or question}")
        print(f"Expected: {test_case['expected']}")
        try:
            session_id = str(uuid.uuid4())
            turn_answers = []
            if turns:
                messages = []
                for turn in turns:
                    messages.append({"role": "user", "content": turn})
                    answer = await asyncio.wait_for(
                        ask(bot, messages, session_id),
                        timeout=TURN_TIMEOUT_SECONDS,
                    )
                    turn_answers.append(answer)
                    messages.append({"role": "assistant", "content": answer})
            else:
                answer = await asyncio.wait_for(
                    ask(bot, messages, session_id),
                    timeout=TURN_TIMEOUT_SECONDS,
                )
            print(answer)
            formatted_answer = format_answer_for_review(answer)
            results.append(
                {
                    "id": index,
                    "category": category,
                    "name": name,
                    "question": question,
                    "expected": test_case["expected"],
                    **formatted_answer,
                    **({"turn_answers": turn_answers} if turns else {}),
                    "error": "",
                }
            )
        except Exception as exc:
            error = (
                f"TimeoutError: exceeded {TURN_TIMEOUT_SECONDS}s"
                if isinstance(exc, TimeoutError)
                else f"{type(exc).__name__}: {exc}"
            )
            print(f"ERROR: {error}")
            results.append(
                {
                    "id": index,
                    "category": category,
                    "name": name,
                    "question": question,
                    "expected": test_case["expected"],
                    "answer": "",
                    "error": error,
                }
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote results to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
