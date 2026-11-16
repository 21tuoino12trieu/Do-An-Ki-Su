from typing import Any, Dict, List, Optional
import asyncio
import re

from beeflow.workflow import WorkflowEngine
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.base_node import START, END, INPUT, OUTPUT


prompt_template = """
# VAI TRÒ
Bạn là chuyên gia tối ưu hóa tìm kiếm cho hệ thống Hybrid Search (BM25 + Vector)
trong lĩnh vực ngân hàng và tài chính.
Nhiệm vụ của bạn là trích xuất từ khóa có giá trị phân biệt cao nhất từ một đoạn
văn bản, giúp hệ thống định vị chính xác chunk này giữa hàng nghìn chunk tương đồng.

# BỐI CẢNH KỸ THUẬT
- Từ khóa được index cùng chunk trong vector database phục vụ Hybrid Search.
- BM25 hoạt động dựa trên khớp từ chính xác — từ khóa phải phản ánh cách
  người dùng thực sự gõ khi tìm kiếm, không phải cách văn bản được viết.
- Corpus chứa nhiều chunk gần giống nhau (cùng loại sản phẩm, khác phiên bản
  hoặc điều khoản) — từ khóa phải đủ cụ thể để phân biệt chunk này với
  các chunk còn lại.

# NHIỆM VỤ
Trích xuất tối đa 20 từ khóa hoặc cụm từ khóa có giá trị truy xuất cao nhất từ chunk (có thể ít hơn).

## Tiêu chí lựa chọn (theo thứ tự ưu tiên)

1. TÊN SẢN PHẨM / THƯƠNG HIỆU — ưu tiên cao nhất, không được bỏ sót.
   Trích xuất tên đầy đủ và tên viết tắt nếu cả hai xuất hiện trong chunk.
   Ví dụ danh mục cần chú ý:
   - Tên thẻ: "Visa Platinum Priority", "Mastercard World", "Napas 365"
   - Tên tài khoản: "Tài khoản số đẹp", "Tài khoản thanh toán thông minh"
   - Tên gói vay: "Vay mua nhà lãi suất ưu đãi", "Vay tín chấp MBBank"
   - Tên dịch vụ: "Internet Banking", "BankPlus", "Smart OTP"

2. CHỦ ĐỀ CHÍNH CỦA CHUNK — xác định chunk này nói về khía cạnh nào
   của sản phẩm. Chỉ lấy chủ đề đúng với nội dung, không suy diễn.
   Ví dụ danh mục:
   - Thông tin sản phẩm: "định nghĩa", "tính năng", "phân loại"
   - Điều kiện: "điều kiện mở thẻ", "đối tượng", "hồ sơ đăng ký"
   - Chi phí: "phí thường niên", "biểu phí", "lãi suất", "phí phạt"
   - Quyền lợi: "ưu đãi", "hoàn tiền", "tích điểm", "bảo hiểm"
   - Giao dịch: "hạn mức", "thanh toán", "rút tiền", "chuyển khoản"
   - Quy trình: "phát hành", "kích hoạt", "khóa thẻ", "tái tục"

3. THUẬT NGỮ CHUYÊN NGÀNH — từ kỹ thuật hoặc nghiệp vụ ngân hàng mà
   người dùng có thể dùng khi tìm kiếm.
   Ví dụ: "contactless", "OTP", "CVV", "PIN", "POS", "SWIFT", "IBAN",
   "tín dụng", "ghi nợ", "trả trước", "đa năng", "hybrid"

4. ĐỐI TƯỢNG KHÁCH HÀNG — nếu chunk đề cập rõ phân khúc mục tiêu.
   Ví dụ: "sinh viên", "khách hàng ưu tiên", "doanh nghiệp SME",
   "khách hàng VIP", "người lao động"

## Quy tắc loại trừ

- Chỉ được trích xuất từ/cụm từ xuất hiện nguyên văn trong chunk (đúng chính tả và ký tự). Nếu không có trong chunk, không được tạo ra.
- Loại bỏ stop word và từ nối không có giá trị tìm kiếm:
  "và", "là", "của", "theo", "được", "khi", "tại", "đối với",
  "những", "các", "này", "đó", "để", "có", "không"
- Loại bỏ từ xuất hiện ở hầu hết mọi chunk, trừ khi là một phần
  của tên riêng: "khách hàng", "ngân hàng", "thẻ", "dịch vụ"
- Không paraphrase hoặc diễn giải lại nội dung chunk
- Không tạo câu hoàn chỉnh
- Không gộp nhiều từ khóa thành một cụm trừ khi chúng là tên riêng

# ĐỊNH DẠNG ĐẦU RA
Chỉ trả về khối từ khóa. Không giải thích, không thêm bất kỳ nội dung nào khác.

<keywords>
- {{từ_khóa_1}}
- {{từ_khóa_2}}
- ...
</keywords>

# ĐẦU VÀO
{chunk}
"""


def _prepare_prompt_node(chunk: str) -> Dict[str, Any]:
    prompt = prompt_template.format(chunk=chunk)
    return {"messages": [{"role": "user", "content": prompt}]}


def _extract_tag_block(text: str, tag: str) -> str:
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_keyword_list(block: str) -> List[str]:
    keywords = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("-"):
            line = line[1:].strip()
        if line:
            keywords.append(line)
    return keywords


def _parse_keywords_node(content: str) -> Dict[str, Any]:
    keywords_block = _extract_tag_block(content, "keywords")
    keywords = _parse_keyword_list(keywords_block)
    return {
        "keywords": keywords,
        "keywords_text": " ".join(keywords),
    }


class KeywordExtractor:
    def __init__(self, resource_key: str = "qwen-instruct-chat"):
        self.resource_key = resource_key
        self._workflow: Optional[WorkflowEngine] = None

    def _build_workflow(self) -> WorkflowEngine:
        with WorkflowEngine(
            name="keyword_extractor_workflow",
            description="Extract keywords from chunk text",
            langfuse="beegen-portal",
            inputs=INPUT,
        ) as workflow:
            prepare_prompt = CodeNode(
                name="prepare_keyword_prompt",
                code_fn=_prepare_prompt_node,
                inputs={"chunk": INPUT["chunk"]},
                return_keys=["messages: List[Dict[str, Any]]"],
            )

            extract_keywords_llm = LLMNode(
                name="extract_keywords_llm",
                resource_key=self.resource_key,
                inputs={
                    "messages": {prepare_prompt: "messages"},
                },
            )

            parse_keywords = CodeNode(
                name="parse_keywords",
                code_fn=_parse_keywords_node,
                inputs={"content": {extract_keywords_llm: "content"}},
                return_keys=[
                    "keywords: List[str]",
                    "keywords_text: str",
                ],
                outputs={
                    "keywords": OUTPUT,
                    "keywords_text": OUTPUT,
                },
            )

            START >> prepare_prompt >> extract_keywords_llm >> parse_keywords >> END

        workflow.compile()
        self._workflow = workflow
        return workflow

    async def extract(self, chunk: str) -> Dict[str, Any]:
        if self._workflow is None:
            self._workflow = self._build_workflow()
        return await self._workflow.run(inputs={"chunk": chunk})


async def main():
    extractor = KeywordExtractor()
    text = """
    BIM.PL 21 Quy dinh viec mua bao hiem - 8558 08.08.2024.pdf

QCĐH.B4.TD-KHDN/PL.21 > PHỤ LỤC 21. QUY ĐỊNH VỀ VIỆC MUA BẢO HIỂM VỚI TỪNG LOẠI TÀI SẢN > I. Loại bảo hiểm và số tiền bảo hiểm
1. Bên mua bảo hiểm mua các loại bảo hiểm bắt buộc theo quy định của pháp luật (Hiện tại là Điều 8 Luật kinh doanh bảo hiểm 2022 và văn bản sửa đổi/bổ sung/thay thế (nếu có)) đối với tài sản được MB nhận bảo đảm, bao gồm:  
| TT | Loại bảo hiểm | Số tiền bảo hiểm tối thiểu (Hiện tại theo Điều 24 và Điều 33 Nghị định số 67/2023/NĐ-CP ngày 06/9/2023 và văn bản sửa đổi/bổ sung/thay thế (nếu có)) |
| :--- | :--- | :--- |
| 1.1 | Bảo hiểm bắt buộc trong hoạt động đầu tư xây dựng (Chi tiết theo Mục 2, Phụ lục này); | Tối thiểu là giá trị đầy đủ của công trình khi hoàn thành (dự kiến), bao gồm toàn bộ vật liệu, chi phí nhân công, thiết bị lắp đặt vào công trình, cước phí vận chuyển, các loại thuế, phí khác và các hạng mục khác do chủ đầu tư cung cấp. Số tiền bảo hiểm tối thiểu đối với công trình trong thời gian xây dựng không được thấp hơn tổng giá trị hợp đồng xây dựng, kể cả giá trị điều chỉnh, bổ sung (nếu có). |
| 1.2 | Bảo hiểm cháy, nổ bắt buộc (Chi tiết theo Mục 3, Phụ lục này) | 1. Tối thiểu là giá trị tính thành tiền theo giá thị trường của các tài sản tại thời điểm giao kết hợp đồng bảo hiểm.<br>2. Trường hợp không xác định được giá thị trường của tài sản thì số tiền bảo hiểm cháy, nổ bắt buộc do các bên thỏa thuận như sau:<br>a) Đối với các tài sản là nhà, công trình và các tài sản gắn liền với nhà, công trình; máy móc, thiết bị: Số tiền bảo hiểm là giá trị tính thành tiền của tài sản theo giá trị còn lại hoặc giá trị thay thế của tài sản tại thời điểm giao kết hợp đồng bảo hiểm.<br>b) Đối với các tài sản là các loại hàng hóa, vật tư (bao gồm cả nguyên vật liệu, bán thành phẩm, thành phẩm): Số tiền bảo hiểm là giá trị tính thành tiền của tài sản căn cứ theo hóa đơn, chứng từ hợp lệ hoặc các tài liệu có liên quan. |
| 1.3 | Bảo hiểm bắt buộc khác theo quy định pháp luật từng thời kỳ | Theo quy định của pháp luật từng thời kỳ |  
2. Danh mục công trình mua bảo hiểm bắt buộc trong hoạt động đầu tư xây dựng (Hiện tại theo Điều 32 Nghị định số 67/2023/NĐ-CP ngày 06/9/2023 và văn bản sửa đổi/bổ sung/thay thế (nếu có))
2.1. Công trình có yêu cầu kỹ thuật đặc thù, điều kiện thi công xây dựng phức tạp theo quy định của pháp luật về xây dựng và pháp luật khác có liên quan.  
| 1.2 | Công trình, hạng mục công trình thuộc Danh mục công trình, hạng mục công trình có ảnh hưởng lớn đến an toàn, lợi ích cộng đồng (Hiện tại theo Phụ lục X Nghị định số 15/2021/NĐ-CP ngày 03/03/2021 hướng dẫn một số nội dung về quản lý dự án đầu tư xây dựng và văn bản sửa đổi/bổ sung/thay thế (nếu có)): | |
| :--- | :--- | :--- |
| **I** | **CÔNG TRÌNH DÂN DỤNG** | **Cấp công trình (Phân cấp công trình xây dựng được quy định theo Thông tư số 06/2021/TT-BXD ngày 30/6/2021 quy định về phân cấp công trình xây dựng và hướng dẫn áp dụng trong quản lý hoạt động đầu tư xây dựng và văn bản sửa đổi/bổ sung/thay thế (nếu có))** |
| I.1 | Nhà ở: Các tòa nhà chung cư, nhà ở tập thể khác | Cấp III trở lên |
| I.2 | Công trình công cộng | |
| I.2.1 | Công trình giáo dục, đào tạo, nghiên cứu | Cấp III trở lên |
| I.2.2 | Công trình y tế | Cấp III trở lên |
| I.2.3 | Công trình thể thao: Sân vận động; nhà thi đấu (các môn thể thao); bể bơi; sân thi đấu các môn thể thao có khán đài | Cấp III trở lên |
| I.2.4 | Công trình văn hóa: Trung tâm hội nghị, nhà hát, nhà văn hóa, câu lạc bộ, rạp chiếu phim, rạp xiếc, vũ trường; các công trình di tích; bảo tàng, thư viện, triển lãm, nhà trưng bày; tượng đài ngoài trời; công trình vui chơi giải trí; công trình văn hóa tập trung đông người và các công trình khác có chức năng tương đương | Cấp III trở lên |
| I.2.5 | Công trình thương mại: Trung tâm thương mại, siêu thị | Cấp III trở lên |
| | Nhà hàng, cửa hàng ăn uống, giải khát và các cơ sở tương tự | Cấp II trở lên |
| I.2.6 | Công trình dịch vụ: Khách sạn, nhà khách, nhà nghỉ; khu nghỉ dưỡng; biệt thự lưu trú; căn hộ lưu trú và các cơ sở tương tự; bưu điện, bưu cục, cơ sở cung cấp dịch vụ bưu chính, viễn thông khác | Cấp III trở lên |
| I.2.7 | Công trình trụ sở, văn phòng làm việc: Các tòa nhà sử dụng làm trụ sở, văn phòng làm việc | Cấp III trở lên |
| I.2.8 | Các công trình đa năng hoặc hỗn hợp: Các tòa nhà, kết cấu khác sử dụng đa năng hoặc hỗn hợp khác | Cấp III trở lên |  
| I.2.9 | Công trình phục vụ dân sinh khác | Các tòa nhà hoặc kết cấu khác được xây dựng phục vụ dân sinh | Cấp II trở lên |
| :--- | :--- | :--- | :--- |"""
    result = await extractor.extract(text)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
