# -*- coding: utf-8 -*-
"""
Script xuất dữ liệu RAG từ workflow của bot_enterprise_KHCN ra file Excel

Output columns:
- STT
- Câu hỏi đầu vào
- Câu hỏi rewrite
- Intent
- Verify Result
- Doc IDs (IDs của documents được retrieve)
- Document content
- Score
- Câu trả lời của Bot
- Session ID
- Timestamp
- Status

Usage:
    python -m beeportal.bot_enterprise_KHCN.scripts.export_rag_workflow
"""

import asyncio
import json
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, project_root)

from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.nodes.base_node import INPUT, START, END
from beeflow.workflow import WorkflowEngine
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.state_value import VariableCell
from beegen.loggings.loggers import LOGGER
from beegen.registry.resource_hub import ResourceHub

# Import bot từ bot_v2.py
from beeportal.bot_enterprise_KHCN.bot_v2 import BeeEnterpriseKHCN


# =============================================================================
# Scipy pre-import để tránh threading issues
# =============================================================================
_scipy_lock = threading.Lock()


def fix_scipy_imports():
    with _scipy_lock:
        try:
            import scipy
            import scipy.sparse
            import scipy.sparse._lil
            scipy.sparse.lil_matrix((1, 1))
        except:
            pass


fix_scipy_imports()


# =============================================================================
# Monkey-patch WorkflowEngine để capture state sau khi workflow chạy xong
# =============================================================================
_captured_states: Dict[str, WorkflowState] = {}


async def _patched_workflow_run(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Patched run method - capture state sau khi workflow hoàn thành"""
    if 'request_id' not in kwargs:
        kwargs['request_id'] = str(uuid.uuid4())

    request_id = kwargs['request_id']

    # Tạo state cho workflow này
    state = WorkflowState(
        indexer=self.indexer,
        inputs=inputs,
        user_id=kwargs.get('user_id', str(uuid.uuid4())),
        request_id=request_id,
        session_id=kwargs.get('session_id', str(uuid.uuid4()))
    )

    # Chạy graph
    result = await self._graph.run(state)

    # Lưu state để inspect sau
    _captured_states[request_id] = state

    # End streaming và flush
    await STREAM_SERVICE.end_request(request_id)
    asyncio.create_task(self.flush(state=state))

    return result


# Apply patch
WorkflowEngine.run = _patched_workflow_run


def get_captured_state(request_id: str) -> Optional[WorkflowState]:
    """Lấy state đã capture bằng request_id"""
    return _captured_states.get(request_id)


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class EnterpriseRAGExecutionData:
    """Lưu trữ dữ liệu từ một lần chạy Enterprise KHCN RAG workflow"""
    # Input
    input_question: str = ""

    # Rewrite & Intent
    rewrite_query: str = ""
    intent: str = ""

    # Verify results
    verify_result: str = ""
    verify_result_logic: str = ""

    # Retrieved documents
    retrieved_docs: List[Dict] = field(default_factory=list)
    doc_count: int = 0

    # Bot response
    bot_answer: str = ""

    # Metadata
    request_id: str = ""
    session_id: str = ""
    bot_id: str = ""
    bot_name: str = ""
    timestamp: str = ""
    status: str = "pending"
    error_message: str = ""


# =============================================================================
# State Extractor - Trích xuất metrics từ WorkflowState
# =============================================================================
class StateExtractor:
    """
    Trích xuất dữ liệu từ WorkflowState của Enterprise KHCN workflow.

    Node paths trong workflow (đã verify từ test):
    - beeEnterpriseKHCN.generate_intent.rewrite (query, intent)
    - beeEnterpriseKHCN.retriver_and_rerank.standard_retriever (docs)
    - beeEnterpriseKHCN.retriver_and_rerank.format_retrieved_docs_fn (doc_contents, documents_text, ids)
    """

    # Node paths
    REWRITE_NODE = "beeEnterpriseKHCN.generate_intent.rewrite"
    RETRIEVER_NODE = "beeEnterpriseKHCN.retriver_and_rerank.standard_retriever"
    FORMAT_RETRIEVER_NODE = "beeEnterpriseKHCN.retriver_and_rerank.format_retrieved_docs_fn"
    VERIFY_NODE = "beeEnterpriseKHCN.verify_document"
    VERIFY_LOGIC_NODE = "beeEnterpriseKHCN.verify_document_logic"

    def __init__(self, state: WorkflowState):
        self.state = state

    # -------------------------------------------------------------------------
    # Rewrite Query & Intent
    # -------------------------------------------------------------------------
    def extract_rewrite_and_intent(self) -> Dict[str, str]:
        """Lấy rewrite query và intent"""
        result = {"query": "", "intent": ""}

        try:
            # Lấy query
            cell = self.state.get(self.REWRITE_NODE, "query")
            if cell:
                for ctx_id, value in cell.contexts.items():
                    if value is not None:
                        result["query"] = str(value)
                        break

            # Lấy intent
            cell = self.state.get(self.REWRITE_NODE, "intent")
            if cell:
                for ctx_id, value in cell.contexts.items():
                    if value is not None:
                        result["intent"] = str(value)
                        break
        except Exception as e:
            LOGGER.debug(f"Could not get rewrite/intent: {e}")

        return result

    # -------------------------------------------------------------------------
    # Verify Results
    # -------------------------------------------------------------------------
    def extract_verify_results(self) -> Dict[str, str]:
        """Lấy verify results từ các node verify (nếu có trong indexer)"""
        result = {"verify": "", "verify_logic": ""}

        # Thử nhiều path khác nhau cho verify node
        verify_paths = [
            ("beeEnterpriseKHCN.verify_document", "output"),
            ("beeEnterpriseKHCN.verify_document", "content"),
            (self.VERIFY_NODE, "output"),
        ]

        for node_path, var_name in verify_paths:
            try:
                if (node_path, var_name) in self.state._indexer:
                    cell = self.state.get(node_path, var_name)
                    if cell:
                        for ctx_id, value in cell.contexts.items():
                            if value is not None:
                                result["verify"] = str(value)
                                break
                    if result["verify"]:
                        break
            except Exception:
                pass

        # Thử nhiều path khác nhau cho verify logic node
        verify_logic_paths = [
            ("beeEnterpriseKHCN.verify_document_logic", "output"),
            ("beeEnterpriseKHCN.verify_document_logic", "content"),
            (self.VERIFY_LOGIC_NODE, "output"),
        ]

        for node_path, var_name in verify_logic_paths:
            try:
                if (node_path, var_name) in self.state._indexer:
                    cell = self.state.get(node_path, var_name)
                    if cell:
                        for ctx_id, value in cell.contexts.items():
                            if value is not None:
                                result["verify_logic"] = str(value)
                                break
                    if result["verify_logic"]:
                        break
            except Exception:
                pass

        return result

    # -------------------------------------------------------------------------
    # Retrieved Documents - Mỗi doc = 1 row
    # -------------------------------------------------------------------------
    def get_retrieved_docs(self) -> List[Dict]:
        """
        Lấy danh sách documents đã retrieve.

        Returns:
            List of docs, mỗi item gồm:
            - chunk_id: ID của chunk
            - content: nội dung document
            - score: điểm relevance
        """
        docs = []

        # Thử lấy từ standard_retriever trước (docs gốc từ retriever)
        try:
            cell = self.state.get(self.RETRIEVER_NODE, "docs")
            if cell:
                for ctx_id, value in cell.contexts.items():
                    if value is not None:
                        if isinstance(value, list):
                            for doc in value:
                                if isinstance(doc, dict) and "content" in doc:
                                    docs.append({
                                        "chunk_id": doc.get("id", doc.get("chunk_id", "")),
                                        "content": doc.get("content", ""),
                                        "score": doc.get("score", 0)
                                    })
        except Exception as e:
            LOGGER.debug(f"Could not get docs from standard_retriever: {e}")

        # Nếu không có docs từ retriever, thử lấy từ format_retrieved_docs_fn
        if not docs:
            try:
                cell = self.state.get(self.FORMAT_RETRIEVER_NODE, "ids")
                if cell:
                    for ctx_id, value in cell.contexts.items():
                        if value is not None:
                            if isinstance(value, list):
                                for doc in value:
                                    if isinstance(doc, dict):
                                        docs.append({
                                            "chunk_id": doc.get("id", ""),
                                            "content": "",  # format node không có content
                                            "score": doc.get("score", 0)
                                        })
            except Exception as e:
                LOGGER.debug(f"Could not get docs from format_retriever: {e}")

        LOGGER.info(f"Got {len(docs)} retrieved docs")
        return docs


# =============================================================================
# Enterprise RAG Exporter - Chạy workflow và thu thập dữ liệu
# =============================================================================
class EnterpriseRAGExporter:
    """Chạy Enterprise KHCN workflow và thu thập metrics"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self._bot = self._init_bot()

    def _init_bot(self) -> BeeEnterpriseKHCN:
        """Khởi tạo BeeEnterpriseKHCN bot"""
        try:
            bot = BeeEnterpriseKHCN(bot_id=self.bot_id)
            LOGGER.info(f"Initialized BeeEnterpriseKHCN bot: {self.bot_id}")
            return bot
        except Exception as e:
            LOGGER.error(f"Failed to init bot: {e}")
            raise

    async def run(self, messages: List[Dict], session_id: Optional[str] = None) -> EnterpriseRAGExecutionData:
        """Chạy workflow và thu thập dữ liệu"""

        request_id = str(uuid.uuid4())
        if not session_id:
            session_id = str(uuid.uuid4())

        # Khởi tạo data collector
        collected_data = EnterpriseRAGExecutionData(
            input_question=messages[-1]['content'] if messages else "",
            request_id=request_id,
            session_id=session_id,
            bot_id=self.bot_id,
            bot_name=self._bot.name or "",
            timestamp=datetime.now().isoformat()
        )

        try:
            # Chạy workflow với streaming để thu thập answer
            full_response = await self._stream_and_collect_response(messages, request_id, session_id)
            collected_data.bot_answer = full_response

            # Trích xuất metrics từ state
            state = get_captured_state(request_id)
            if state:
                self._extract_metrics_from_state(state, collected_data)
            else:
                LOGGER.warning("No captured state found")

            collected_data.status = "success"

        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc())
            collected_data.bot_answer = f"Error: {str(e)}"
            collected_data.error_message = str(e)
            collected_data.status = "error"

        return collected_data

    async def _stream_and_collect_response(
        self,
        messages: List[Dict],
        request_id: str,
        session_id: str
    ) -> str:
        """Stream response và thu thập answer text"""
        full_response = []

        async for chunk in self._bot.run(
            messages=messages,
            client_message_id=request_id,
            session_id=session_id,
            role_ids=["L1"]
        ):
            try:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    full_response.append(delta)
            except Exception as e:
                LOGGER.warning(f"Chunk processing error: {e}")

        return "".join(full_response)

    def _extract_metrics_from_state(self, state: WorkflowState, collected_data: EnterpriseRAGExecutionData):
        """Trích xuất metrics từ state sau khi workflow chạy xong"""
        extractor = StateExtractor(state)

        # Extract rewrite & intent
        rewrite_data = extractor.extract_rewrite_and_intent()
        collected_data.rewrite_query = rewrite_data.get("query", "")
        collected_data.intent = rewrite_data.get("intent", "")

        # Extract verify results
        verify_data = extractor.extract_verify_results()
        collected_data.verify_result = verify_data.get("verify", "")
        collected_data.verify_result_logic = verify_data.get("verify_logic", "")

        # Extract retrieved docs - mỗi doc = 1 row
        collected_data.retrieved_docs = extractor.get_retrieved_docs()
        collected_data.doc_count = len(collected_data.retrieved_docs)


# =============================================================================
# Excel Exporter - Xuất dữ liệu ra file Excel
# =============================================================================
class EnterpriseExcelExporter:
    """Export Enterprise KHCN RAG data ra Excel file"""

    def __init__(self):
        self.execution_results: List[EnterpriseRAGExecutionData] = []

        # Styles
        self.header_font = Font(bold=True, color="FFFFFF", size=11)
        self.header_fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
        self.header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.cell_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        self.cell_align = Alignment(vertical="top", wrap_text=True)

    def add_result(self, data: EnterpriseRAGExecutionData):
        """Thêm một kết quả execution"""
        self.execution_results.append(data)

    def export(self, output_path: str = "enterprise_khcn_rag_export.xlsx"):
        """Export tất cả data ra Excel"""

        wb = openpyxl.Workbook()

        # Sheet 1: Main Data
        self._create_main_sheet(wb)

        # Sheet 2: Summary
        self._create_summary_sheet(wb)

        wb.save(output_path)
        print(f"[OK] Đã xuất file: {output_path}")
        return output_path

    def _create_main_sheet(self, wb: openpyxl.Workbook):
        """Tạo sheet chính với dữ liệu RAG - mỗi document là một hàng"""
        ws = wb.active
        ws.title = "RAG Data"

        headers = [
            "STT", "Câu hỏi đầu vào", "Câu hỏi rewrite", "Intent",
            "Verify Result", "Doc IDs", "Document content", "Score",
            "Câu trả lời của Bot", "Session ID", "Timestamp", "Status"
        ]

        # Header row
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.header_align
            cell.border = self.cell_border

        current_row = 2
        stt = 0

        # Mỗi câu hỏi có thể có nhiều docs -> nhiều hàng
        for data in self.execution_results:
            stt += 1
            docs = data.retrieved_docs
            num_rows = max(len(docs), 1)  # Ít nhất 1 hàng

            # Format các giá trị cần gộp
            question = data.input_question
            rewrite_query = data.rewrite_query
            intent = data.intent
            verify = f"Doc: {data.verify_result} | Logic: {data.verify_result_logic}"
            answer = data.bot_answer
            session_id = data.session_id
            timestamp = data.timestamp
            status = data.status

            # Ghi từng doc là một hàng
            for i, doc in enumerate(docs):
                # STT - chỉ hàng đầu tiên
                if i == 0:
                    ws.cell(row=current_row, column=1, value=stt)
                else:
                    ws.cell(row=current_row, column=1, value="")

                # Câu hỏi - gộp tất cả các hàng
                ws.cell(row=current_row, column=2, value=question if i == 0 else "")

                # Rewrite query - gộp
                ws.cell(row=current_row, column=3, value=rewrite_query if i == 0 else "")

                # Intent - gộp
                ws.cell(row=current_row, column=4, value=intent if i == 0 else "")

                # Verify Result - gộp
                ws.cell(row=current_row, column=5, value=verify if i == 0 else "")

                # Doc ID
                doc_id = doc.get('chunk_id', '')
                ws.cell(row=current_row, column=6, value=doc_id)

                # Document content
                content = "'" + doc.get('content', '')
                if len(content) > 10000:
                    content =  content[:10000] + "\n... [truncated]"
                ws.cell(row=current_row, column=7, value=content)

                # Score
                score = doc.get('score', 0)
                ws.cell(row=current_row, column=8, value=round(score, 4) if score else "")

                # Answer - gộp
                ws.cell(row=current_row, column=9, value=answer if i == 0 else "")

                # Session ID - gộp
                ws.cell(row=current_row, column=10, value=session_id if i == 0 else "")

                # Timestamp - gộp
                ws.cell(row=current_row, column=11, value=timestamp if i == 0 else "")

                # Status - gộp
                ws.cell(row=current_row, column=12, value=status if i == 0 else "")

                # Apply styles
                for col in range(1, 13):
                    cell = ws.cell(row=current_row, column=col)
                    cell.border = self.cell_border
                    if col == 7:  # Document content
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                    else:
                        cell.alignment = self.cell_align

                current_row += 1

            # Merge các ô cho cùng một câu hỏi (trừ Doc IDs, content, score)
            if num_rows > 1:
                merge_start = current_row - num_rows
                merge_end = current_row - 1

                # Merge STT
                ws.merge_cells(start_row=merge_start, start_column=1, end_row=merge_end, end_column=1)
                ws.cell(row=merge_start, column=1).alignment = Alignment(horizontal="center", vertical="center")

                # Merge Câu hỏi
                ws.merge_cells(start_row=merge_start, start_column=2, end_row=merge_end, end_column=2)
                ws.cell(row=merge_start, column=2).alignment = Alignment(vertical="center", wrap_text=True)

                # Merge Rewrite query
                ws.merge_cells(start_row=merge_start, start_column=3, end_row=merge_end, end_column=3)
                ws.cell(row=merge_start, column=3).alignment = Alignment(vertical="center", wrap_text=True)

                # Merge Intent
                ws.merge_cells(start_row=merge_start, start_column=4, end_row=merge_end, end_column=4)
                ws.cell(row=merge_start, column=4).alignment = Alignment(horizontal="center", vertical="center")

                # Merge Verify Result
                ws.merge_cells(start_row=merge_start, start_column=5, end_row=merge_end, end_column=5)
                ws.cell(row=merge_start, column=5).alignment = Alignment(vertical="center", wrap_text=True)

                # Không merge Doc IDs - mỗi hàng một doc ID

                # Không merge Document content - mỗi hàng một doc

                # Không merge Score - mỗi hàng một score

                # Merge Answer
                ws.merge_cells(start_row=merge_start, start_column=9, end_row=merge_end, end_column=9)
                ws.cell(row=merge_start, column=9).alignment = Alignment(vertical="center", wrap_text=True)

                # Merge Session ID
                ws.merge_cells(start_row=merge_start, start_column=10, end_row=merge_end, end_column=10)

                # Merge Timestamp
                ws.merge_cells(start_row=merge_start, start_column=11, end_row=merge_end, end_column=11)

                # Merge Status
                ws.merge_cells(start_row=merge_start, start_column=12, end_row=merge_end, end_column=12)
                ws.cell(row=merge_start, column=12).alignment = Alignment(horizontal="center", vertical="center")

        # Column widths
        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 30
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 40
        ws.column_dimensions['G'].width = 50
        ws.column_dimensions['H'].width = 10
        ws.column_dimensions['I'].width = 40
        ws.column_dimensions['J'].width = 35
        ws.column_dimensions['K'].width = 20
        ws.column_dimensions['L'].width = 10

        # Row heights
        for row in range(2, current_row):
            ws.row_dimensions[row].height = 60

    def _create_summary_sheet(self, wb: openpyxl.Workbook):
        """Tạo sheet tổng kết"""
        ws = wb.create_sheet("Tổng kết")

        ws['A1'] = "BÁO CÁO TỔNG KẾT - ENTERPRISE KHCN BOT"
        ws.merge_cells('A1:B1')
        ws['A1'].font = Font(bold=True, size=16, color="0D47A1")
        ws['A1'].alignment = Alignment(horizontal='center')

        summary_data = [
            ("Tổng số câu hỏi:", len(self.execution_results)),
            ("Thành công:", sum(1 for d in self.execution_results if d.status == "success")),
            ("Lỗi:", sum(1 for d in self.execution_results if d.status == "error")),
            ("Chit-chat:", sum(1 for d in self.execution_results if d.intent == "chit_chat")),
            ("Non-chit-chat:", sum(1 for d in self.execution_results if d.intent == "non_chit_chat")),
            ("Documents matched:", sum(1 for d in self.execution_results if d.verify_result == "matched")),
            ("Documents unmatched:", sum(1 for d in self.execution_results if d.verify_result == "unmatched")),
            ("Có documents:", sum(1 for d in self.execution_results if d.doc_count > 0)),
            ("Không có documents:", sum(1 for d in self.execution_results if d.doc_count == 0)),
            ("Tổng documents retrieved:", sum(d.doc_count for d in self.execution_results)),
            ("Bot ID:", self.execution_results[0].bot_id if self.execution_results else "N/A"),
            ("Bot Name:", self.execution_results[0].bot_name if self.execution_results else "N/A"),
            ("Export time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]

        for row_idx, (label, value) in enumerate(summary_data, 3):
            ws[f'A{row_idx}'] = label
            ws[f'B{row_idx}'] = value
            ws[f'A{row_idx}'].font = Font(bold=True)

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 50


# =============================================================================
# Main Entry Point
# =============================================================================
async def run_export(
    bot_id: str,
    questions: List[str],
    output_file: str = "enterprise_khcn_rag_export.xlsx"
):
    """
    Chạy export với danh sách câu hỏi

    Args:
        bot_id: ID của bot enterprise KHCN
        questions: Danh sách câu hỏi cần export
        output_file: Đường dẫn file Excel output
    """
    excel_exporter = EnterpriseExcelExporter()
    rag_exporter = EnterpriseRAGExporter(bot_id)

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Đang xử lý: {question[:60]}...")

        messages = [{"role": "user", "content": question}]
        result = await rag_exporter.run(messages)

        excel_exporter.add_result(result)

        print(f"  -> Rewrite: {result.rewrite_query[:50] if result.rewrite_query else 'N/A'}...")
        print(f"  -> Intent: {result.intent}")
        print(f"  -> Verify: {result.verify_result}")
        print(f"  -> Docs retrieved: {result.doc_count}")
        print(f"  -> Answer length: {len(result.bot_answer)} chars")
        print(f"  -> Status: {result.status}")

    excel_exporter.export(output_file)
    return output_file


def main():
    """Main entry point"""
    print("=" * 60)
    print("Enterprise KHCN RAG Workflow Data Export")
    print("=" * 60)

    # Bot ID cho enterprise KHCN (thay đổi theo bot thực tế)
    ENTERPRISE_BOT_ID = "dfb5a874-b980-4275-bd34-0ddbd1acefdf"

    # Danh sách câu hỏi mẫu
    SAMPLE_QUESTIONS = [
        "Quy trình xin nghỉ phép như thế nào?",
        "Chính sách lương thưởng của công ty là gì?",
        "Hướng dẫn sử dụng phần mềm ERP",
        "Chào buổi sáng!",
    ]

    output_path = asyncio.run(run_export(
        bot_id=ENTERPRISE_BOT_ID,
        questions=SAMPLE_QUESTIONS,
        output_file="enterprise_khcn_rag_export.xlsx"
    ))

    print(f"\n[Xong] File đã được lưu tại: {output_path}")


if __name__ == "__main__":
    main()
