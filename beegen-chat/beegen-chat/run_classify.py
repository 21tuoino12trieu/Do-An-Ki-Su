import openai
import os
import json
import re
from typing import Optional, List, Dict
import pandas as pd

# LLM config - hardcoded for now
LLM_CONFIG = {
    "key": "REPLACE_WITH_LOCAL_SECRET",
    "base_url": "https://llm-gateway-dev.mbbank.com.vn"
}

# Danh sách các domain để phân loại
DOMAINS = [
    "Sản phẩm cho CBNV",
    "Sản phẩm ô tô",
    "Sản phẩm",
    "Quy trình tín dụng KHCN",
    "Quy chế tín dụng KHCN",
    "Ghi nhận nguồn thu",
    "Khác"
]


def classify_category(
    questions: List[str],
    api_key: str = None,
    base_url: str = None,
    model: str = "gpt-4o",
    temperature: float = 0
) -> List[Dict[str, str]]:
    """
    Phân loại câu hỏi vào các domain đã cho sử dụng OpenAI API.
    """
    os.environ["NO_PROXY"] = "llm-gateway-dev.mbbank.com.vn"

    api_key = api_key or LLM_CONFIG["key"]
    base_url = base_url or LLM_CONFIG["base_url"]

    # Lọc bỏ các câu hỏi None hoặc empty
    valid_questions = [q for q in questions if q and str(q).strip()]

    if not valid_questions:
        return []

    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        # Tạo danh sách domain dưới dạng string
        domain_list = "\n".join([f"{i+1}. {d}" for i, d in enumerate(DOMAINS)])

        # Tạo prompt để phân loại
        results = []

        # Prompt mẫu để phân loại
        system_prompt = f"""Bạn là chuyên gia phân loại câu hỏi ngân hàng.
Hãy phân loại câu hỏi của khách hàng vào một trong các domain sau:
{domain_list}

Nguyên tắc phân loại:
- "Sản phẩm cho CBNV": Các câu hỏi về sản phẩm, dịch vụ dành riêng cho cán bộ nhân viên MB (lương trần, tín chấp CBNV, thế chấp CBNV, v.v.)
- "Sản phẩm ô tô": Các câu hỏi về sản phẩm cho vay mua ô tô, bảo hiểm ô tô, v.v.
- "Sản phẩm": Các câu hỏi chung về sản phẩm ngân hàng (vay mua nhà, tiết kiệm, thẻ, v.v.) - không phải CBNV
- "Quy trình tín dụng KHCN": Các câu hỏi về quy trình, thủ tục xét duyệt cấp tín dụng, hồ sơ, checklist, v.v.
- "Quy chế tín dụng KHCN": Các câu hỏi về quy định, thông báo, công văn quy định tín dụng (độ tuổi, TSBĐ, v.v.)
- "Ghi nhận nguồn thu": Các câu hỏi về ghi nhận nguồn thu, thông báo 6710, v.v.
- "Khác": Các câu hỏi không thuộc các loại trên

Trả về kết quả theo format JSON array, mỗi phần tử có format:
[{{"question": "câu hỏi", "domain": "domain tương ứng"}}]

Chỉ trả về JSON array, không giải thích gì thêm."""

        # Xử lý từng câu hỏi
        for i, question in enumerate(valid_questions):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Phân loại câu hỏi sau:\n{question}"}
                    ],
                    temperature=temperature,
                    stream=False,
                )

                result_text = response.choices[0].message.content

                # Parse JSON result
                try:
                    parsed = json.loads(result_text)
                    if isinstance(parsed, list):
                        results.extend(parsed)
                    else:
                        results.append(parsed)
                except json.JSONDecodeError:
                    # Thử tìm JSON trong text
                    json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        results.extend(parsed)
                    else:
                        # Fallback: gán "Khác"
                        results.append({"question": question, "domain": "Khác"})

                print(f"✓ Đã phân loại {i+1}/{len(valid_questions)}")

            except Exception as e:
                print(f"❌ Lỗi phân loại câu hỏi {i+1}: {e}")
                results.append({"question": question, "domain": "Khác"})

        return results

    except Exception as e:
        print(f"❌ Lỗi khi phân loại: {e}")
        return []


def classify_from_excel(
    input_file: str,
    output_file: str,
    question_column: str = "NGƯỜI DÙNG HỎI",
) -> None:
    """
    Đọc file Excel, phân loại câu hỏi và lưu kết quả.
    """
    # Đọc file Excel
    df = pd.read_excel(input_file)

    # Lấy cột câu hỏi
    questions = df[question_column].tolist()

    # Phân loại
    results = classify_category(questions)

    # Thêm cột domain vào dataframe
    domain_map = {r["question"]: r["domain"] for r in results}
    df["DOMAIN"] = df[question_column].map(lambda x: domain_map.get(str(x), "Khác") if pd.notna(x) else "Khác")

    # Lưu file Excel
    df.to_excel(output_file, index=False)
    print(f"✅ Đã lưu kết quả vào {output_file}")


if __name__ == "__main__":
    input_file = 'beeportal/bot_enterprise_KHCN/tín dụng output.xlsx'
    output_file = 'beeportal/bot_enterprise_KHCN/tín dụng classified.xlsx'

    classify_from_excel(input_file, output_file)
