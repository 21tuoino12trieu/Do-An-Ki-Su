from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beegen.embeddings.vllm_embedding import EmbeddingResponse
from beeflow.nodes.base_node import INPUT, OUTPUT
from typing import Union, List, Optional 
import asyncio
import re 
from docx import Document
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import os
from pathlib import Path
from docx import Document

prompt_template = """VAI TRÒ
VAI TRÒ
Bạn là chuyên gia tối ưu hóa dữ liệu cho hệ thống Hybrid Search (BM25 + Vector) trong lĩnh vực Ngân hàng. Nhiệm vụ của bạn là trích xuất bộ từ khóa "đắt giá" nhất để phân biệt chunk này với hàng ngàn chunk khác.

MỤC TIÊU
Trích xuất từ khóa giúp hệ thống tìm kiếm chính xác sản phẩm/dịch vụ cụ thể, tránh gây nhiễu giữa các loại thẻ hoặc dịch vụ tương đồng.

NHIỆM VỤ
Trích xuất keyword cốt lõi
- Trích xuất tối đa 5 đến 6 keyword quan trọng nhất
- Keyword là từ hoặc cụm từ:
  - Người dùng có khả năng gõ khi tìm kiếm
  - Phản ánh đúng nội dung chính của chunk
- Ưu tiên:
  - Trích xuất tên đầy đủ và các biến thể của sản phẩm (Ví dụ: "Visa Platinum Priority", "Visa Led Hi"). Đây là từ khóa quan trọng nhất.
  - Chủ đề chính: định nghĩa, điều kiện, quyền lợi, phát hành, phí, đối tượng
- Loại bỏ các từ không có giá trị tìm kiếm và xuất hiện nhiều như:
  “và”, “là”, “của”, “theo”, “được”, “khi”, “tại”, “đối với”, “những”

Không viết lại nội dung:
- Không paraphrase chunk
- Không tạo câu hoàn chỉnh
- Không gộp keyword thành câu

ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC)

<keywords>
- ...
</keywords>

--------------------------------------------------
VÍ DỤ
--------------------------------------------------
1. Ví dụ 1
INPUT:
59. Thẻ tín dụng Visa Platinum Priority\n5.2 Giao dịch trên POS\nKH được phép thực hiện các giao dịch:\n•Thanh toán hàng hóa dịch vụ\n•Thanh toán hóa đơn\n

OUTPUT:
<keywords>
- Visa Platinum Priority
- giao dịch 
- POS
- thanh toán
</keywords>

--------------------------------------------------
2. Ví dụ 2:
INPUT:
55. Thẻ đa năng Phát sáng - Visa Led Hi Collection\n1. ĐỊNH NGHĨA SẢN PHẨM\n- Là dòng thẻ Hybrid – thẻ đa năng được kết hợp 2 tính năng của thẻ tín dụng và thẻ ghi nợ trên 1 thẻ, sử dụng nguồn tiền từ hạn mức thẻ tín dụng và số dư Tài khoản thanh toán để giao dịch. Thẻ được MB phối hợp cùng tổ chức thẻ quốc tế Visa phát hành.\n- Bộ sưu tập thẻ phát sáng: Thẻ đa năng phát sáng đầu tiên tại Việt Nam khi thanh toán không tiếp xúc tại máy POS (contactless) hoặc thiết bị động. Thẻ có đầy đủ tính năng của thẻ Hi Collection của MB.\n

OUTPUT:
<keywords>
- Visa Led Hi Collection
- định nghĩa 
- đa năng
- tín dụng
- ghi nợ
- phát sáng
</keywords>

--------------------------------------------------
INPUT THỰC TẾ
--------------------------------------------------
{chunk}
"""

gen_question_prompt_template = """
Bạn là một chuyên gia kiểm thử chatbot (chatbot tester).

Nhiệm vụ của bạn:
- Dựa trên đoạn văn bản bên dưới
- Sinh ra các cặp CÂU HỎI - CÂU TRẢ LỜI mà người dùng THỰC TẾ có thể hỏi chatbot
- Không quá 3 câu hỏi.

YÊU CẦU:
1. Câu hỏi phải tự nhiên, giống người dùng thật
2. Câu trả lời PHẢI dựa 100% vào nội dung văn bản
3. Không suy diễn, không thêm kiến thức ngoài
4. Mỗi câu hỏi chỉ có 1 ý rõ ràng
5. Ưu tiên các dạng:
   - hỏi định nghĩa
   - hỏi quy trình
   - hỏi điều kiện / lưu ý
   - hỏi ai / khi nào / như thế nào

ĐỊNH DẠNG OUTPUT (BẮT BUỘC):
<qa_pairs>
- Q: ...
  A: ...
- Q: ...
  A: ...
</qa_pairs>

Văn bản:
"""

    
class LLM:
    def __init__(self, resource_key: str = "qwen-instruct-chat"):
        self.llm_node = LLMNode(
            name="llm0",
            resource_key= resource_key,
            inputs=INPUT,
            outputs=OUTPUT,
        )

        self.indexer = WorkflowIndexer(name="workflow01").add_node(self.llm_node).build()

    async def generate(self, text: str):
        prompt = prompt_template.format(chunk=text)

        state = WorkflowState(
            indexer=self.indexer,
            inputs={
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
        )

        output = await self.llm_node.run(state=state)

        # print(self.emb_node.trace_data(state, None))
        return self.extract_data(output['content'])
    
    async def generate_qa_pair(self, text: str):
        prompt = gen_question_prompt_template + text.strip()

        state = WorkflowState(
            indexer=self.indexer,
            inputs={
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
        )

        output = await self.llm_node.run(state=state)
        return self.extract_qa(output["content"])
    
    def extract_data(self, llm_output: str) -> Optional[str]:

        """
        Extract keywords và expanded_keywords từ LLM output
        """
        keywords_block = self.extract_tag_block(llm_output, "keywords")

        return " ".join(self.parse_keyword_list(keywords_block))
        
    def extract_tag_block(self, text: str, tag: str) -> str:
        """
        Lấy toàn bộ nội dung nằm trong <tag>...</tag>
        Trả về chuỗi rỗng nếu không tìm thấy
        """
        pattern = rf"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def extract_qa(self, llm_output: str) -> List[dict]:
        """
        Extract danh sách question-answer từ <qa_pairs>...</qa_pairs>
        """
        block = self.extract_tag_block(llm_output, "qa_pairs")
        return self.parse_qa_pairs(block)
    
    def parse_keyword_list(self, block: str) -> List[str]:
        """
        Chuyển block text trong tag thành list keyword sạch
        """
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
        
    def parse_qa_pairs(self, block: str) -> List[dict]:
        """
        Parse block text thành list:
        [
            {"question": "...", "answer": "..."},
            ...
        ]
        """
        qa_list = []
        current_q = None
        current_a = None

        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("- Q:"):
                if current_q and current_a:
                    qa_list.append({
                        "question": current_q,
                        "answer": current_a
                    })
                current_q = line.replace("- Q:", "").strip()
                current_a = None

            elif line.startswith("A:"):
                current_a = line.replace("A:", "").strip()

        if current_q and current_a:
            qa_list.append({
                "question": current_q,
                "answer": current_a
            })

        return qa_list
    

def read_docx(file_path: str) -> str:
    """
    Đọc toàn bộ nội dung text từ file .docx
    """
    path = Path(file_path)

    # 1. Check tồn tại
    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {path}")

    # 2. Check là file
    if not path.is_file():
        raise ValueError(f"Không phải file: {path}")

    # 3. Check extension
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Không phải file docx: {path}")
    
    doc = Document(file_path)
    paragraphs = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)



def write_qa_to_excel(
    qa_pairs: list,
    output_path: str,
    source_file: str
):
    """
    Ghi danh sách Q&A vào file Excel
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "chatbot_test_set"

    # Header
    headers = ["question", "answer", "source_file"]
    ws.append(headers)

    # Data
    for qa in qa_pairs:
        ws.append([
            qa["question"],
            qa["answer"],
            source_file
        ])

    # Auto fit column width
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 40

    wb.save(output_path)
    print(f"saved file at {output_path}")


def list_docx_files(folder_path: str) -> list[str]:
    """
    List tất cả file .docx (recursive) trong folder
    """
    docx_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".docx"):
                path = os.path.join(root, file)
                docx_files.append(path.replace("\\", "/"))
    return docx_files

async def main():
    import random 
    llm_node = LLM()

    #----------------------------------------
    # text =  "48. Thẻ đa năng Mastercard Hi Slay-dy (Hi Slay-dy Mastercard Collection)\n3.2 Điều kiện phát hành\n3.2.1 Đối với trường hợp KH phát hành, định danh thẻ trên App MBBank\nKH độ tuổi từ đủ 18 tuổi trở lên tại thời điểm phát hành/ định danh thẻ.\nLoại GTTT phải là CCCD gắn chíp hoặc Thẻ Căn cước đối với KH có quốc tịch VN; GTTT phải còn hiệu lực tại thời điểm thực hiện giao dịch phát hành/ định danh thẻ/ giao dịch thẻ\nKH hoàn thành thực hiện sinh trắc học trên APP MBBank\n3.2.2 Đối với trường hợp KH phát hành, định danh thẻ tại CN/PGD MB\nLoại GTTT phải là CCCD gắn chíp hoặc Thẻ Căn cước đối với KH có quốc tịch VN; GTTT phải còn hiệu lực tại thời điểm thực hiện giao dịch phát hành/ định danh thẻ/ giao dịch thẻ\n"
    text = "55. Thẻ đa năng Phát sáng - Visa Led Hi Collection\n1. ĐỊNH NGHĨA SẢN PHẨM\n- Là dòng thẻ Hybrid – thẻ đa năng được kết hợp 2 tính năng của thẻ tín dụng và thẻ ghi nợ trên 1 thẻ, sử dụng nguồn tiền từ hạn mức thẻ tín dụng và số dư Tài khoản thanh toán để giao dịch. Thẻ được MB phối hợp cùng tổ chức thẻ quốc tế Visa phát hành.\n- Bộ sưu tập thẻ phát sáng: Thẻ đa năng phát sáng đầu tiên tại Việt Nam khi thanh toán không tiếp xúc tại máy POS (contactless) hoặc thiết bị động. Thẻ có đầy đủ tính năng của thẻ Hi Collection của MB.\n"
    output = await llm_node.generate(text)
    print(output)

    # ###################################################
    # folder_path = "D:/tests/"
    # file_paths = list_docx_files(folder_path)

    # p=1

    # for file_path in file_paths: 
    #     try:
    #         n = random.random()
    #         if n > p: continue 

    #         text = read_docx(file_path)

    #         if not text.strip():
    #             print(f"File {file_path} không có nội dung")
    #             continue

    #         qa_pairs = await llm_node.generate_qa_pair(text)

    #         save_path= os.path.join("test-files", "_".join(file_path.split("/")[-2:]))
    #         save_path = save_path.replace(".docx", ".xlsx")
    #         write_qa_to_excel(
    #             qa_pairs=qa_pairs,
    #             output_path=save_path,
    #             source_file=file_path
    #         )
    #     except Exception as e: 
    #         print(e)
    #         continue



if __name__ == "__main__":
    asyncio.run(main())