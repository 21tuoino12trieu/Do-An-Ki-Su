# -*- coding: utf-8 -*-
"""
Script xuất dữ liệu RAG workflow từ bot BeeHR ra file Excel

Output columns:
- STT
- Câu hỏi đầu vào
- Câu trả lời của Agent
- Tool result (output của tool)
- Tool calls được sử dụng
- Doc IDs (IDs của documents được retrieve)
- Số lần iteration của agent
- Session ID
- Timestamp
- Status

Usage:
    python -m beeportal.bot_hr.scripts.export_rag_workflow
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
from beeportal.bot_hr.bot import BeeHR


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

    state = WorkflowState(
        indexer=self.indexer,
        inputs=inputs,
        user_id=kwargs.get('user_id', str(uuid.uuid4())),
        request_id=request_id,
        session_id=kwargs.get('session_id', str(uuid.uuid4()))
    )

    result = await self._graph.run(state)

    _captured_states[request_id] = state

    await STREAM_SERVICE.end_request(request_id)
    asyncio.create_task(self.flush(state=state))

    return result


WorkflowEngine.run = _patched_workflow_run


def get_captured_state(request_id: str) -> Optional[WorkflowState]:
    return _captured_states.get(request_id)


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class HRRAGExecutionData:
    """Lưu trữ dữ liệu từ một lần chạy BeeHR workflow"""
    input_question: str = ""
    tool_calls: List[Dict] = field(default_factory=list)
    retrieved_docs: List[Dict] = field(default_factory=list)
    doc_ids: List[Dict] = field(default_factory=list)
    agent_iterations: int = 0
    agent_answer: str = ""
    final_state_messages: List[Dict] = field(default_factory=list)
    request_id: str = ""
    session_id: str = ""
    bot_id: str = ""
    timestamp: str = ""
    status: str = "pending"
    error_message: str = ""


# =============================================================================
# State Extractor - Trích xuất metrics từ WorkflowState của BeeHR
# =============================================================================
class StateExtractor:
    """
    Trích xuất documents, tool_calls, iterations từ WorkflowState.

    BeeHR workflow node paths:
      - beeHR.react_agent.pev_loop.__inner__.planner_native
      - beeHR.react_agent.pev_loop.__inner__.tool_executor
      - beeHR.react_agent.pev_loop.__inner__.tool_executor.{tool_name}
    """

    REACT_AGENT_NODES = [
        "beeHR.react_agent",
        "beeHR.react_agent.pev_loop",
        "beeHR.react_agent.pev_loop.__inner__"
    ]
    FINAL_STATE_MESSAGES_VAR = "final_state_messages"
    TOOL_EXECUTOR_NODE = "beeHR.react_agent.pev_loop.__inner__.tool_executor"
    TOOL_EXECUTOR_OUTPUT_VAR = "result"

    def __init__(self, state: WorkflowState):
        self.state = state

    def extract_tool_calls(self) -> List[Dict]:
        """Trích xuất tool calls từ final_state_messages"""
        messages = self._get_final_state_messages()
        if not messages:
            return []

        tool_calls = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_calls.append({
                        "id": tc.get("id"),
                        "name": tc.get("function", {}).get("name"),
                        "arguments": tc.get("function", {}).get("arguments")
                    })
        return tool_calls

    def get_tool_outputs(self) -> List[Dict]:
        """Lấy tất cả outputs từ tool_executor"""
        outputs = []
        try:
            cell = self.state.get(self.TOOL_EXECUTOR_NODE, self.TOOL_EXECUTOR_OUTPUT_VAR)
            if cell is None:
                return outputs

            for ctx_id, value in cell.contexts.items():
                if value is not None:
                    outputs.append({
                        "tool_name": "tool_executor",
                        "output": value
                    })

            if hasattr(cell, 'contexts') is False and outputs == []:
                outputs.append({
                    "tool_name": "tool_executor",
                    "output": cell
                })

        except Exception as e:
            LOGGER.debug(f"Could not get tool outputs: {e}")

        return outputs

    def get_doc_ids(self) -> List[Dict]:
        """Lấy danh sách doc IDs từ tool outputs"""
        outputs = []
        tool_outputs = self.get_tool_outputs()

        for tool_output in tool_outputs:
            output = tool_output.get('output', {})
            if not isinstance(output, dict):
                continue

            doc_ids = []

            if "data" in output and isinstance(output["data"], list):
                for item in output["data"]:
                    if "_id" in item and "document_id" in item:
                        doc_ids.append({"chunk_id": item["_id"], "document_id": item["document_id"]})
                    elif "_id" in item:
                        doc_ids.append(item["_id"])

            if "docs" in output and isinstance(output["docs"], list):
                for item in output["docs"]:
                    if "doc" in item and "id" in item:
                        doc_ids.append({"chunk_id": item["id"], "document_id": item["doc"]})

            if doc_ids:
                outputs.append({
                    "tool_name": tool_output.get("tool_name", "unknown"),
                    "ids": doc_ids
                })

        return outputs

    def _detect_context_ids(self) -> List[str]:
        context_ids = set()
        for ex in self.state.execution_order:
            ctx = ex.get("context_id")
            if ctx:
                context_ids.add(ctx)
        return sorted(context_ids, reverse=True) + [None]

    def extract_iterations(self) -> int:
        """Đếm số iterations từ execution_order"""
        count = 0
        for ex in self.state.execution_order:
            node = ex.get("node", "")
            if "planner_native" in node or "planner" in node.lower():
                count += 1
        return count

    def _get_final_state_messages(self) -> List[Dict]:
        for ctx_id in self._detect_context_ids():
            for node_name in self.REACT_AGENT_NODES:
                messages = self._try_get_messages(node_name, self.FINAL_STATE_MESSAGES_VAR, ctx_id)
                if messages:
                    return messages
        return []

    def _try_get_messages(self, node_name: str, var_name: str, ctx_id: str) -> Optional[List[Dict]]:
        try:
            cell = self.state.get(node_name, var_name)
            if cell is None:
                return None
            if ctx_id is not None:
                value = cell.contexts.get(ctx_id)
            else:
                value = cell
            if hasattr(value, 'contexts'):
                value = value.contexts.get(ctx_id) or value.contexts.get(None, [])
            if value and isinstance(value, list) and len(value) > 0:
                return value
            return None
        except Exception as e:
            LOGGER.debug(f"Could not get {node_name}.{var_name}[ctx={ctx_id}]: {e}")
            return None

    def list_available_nodes(self) -> List[str]:
        nodes = set()
        for (node, var) in self.state._indexer:
            nodes.add(node)
        return sorted(list(nodes))

    def list_available_vars(self, node_name: str) -> List[str]:
        return [var for (n, var) in self.state._indexer if n == node_name]


# =============================================================================
# HR RAG Exporter
# =============================================================================
class HRRAGExporter:
    """Chạy BeeHR workflow và thu thập metrics"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self._bot = self._init_bot()

    def _init_bot(self) -> BeeHR:
        try:
            bot = BeeHR(bot_id=self.bot_id)
            LOGGER.info(f"Initialized BeeHR bot: {self.bot_id}")
            return bot
        except Exception as e:
            LOGGER.error(f"Failed to init bot: {e}")
            raise

    async def run(self, messages: List[Dict], session_id: Optional[str] = None, username: str = "liemlt1") -> HRRAGExecutionData:
        """Chạy workflow và thu thập dữ liệu"""

        request_id = str(uuid.uuid4())
        if not session_id:
            session_id = str(uuid.uuid4())

        collected_data = HRRAGExecutionData(
            input_question=messages[-1]['content'] if messages else "",
            request_id=request_id,
            session_id=session_id,
            bot_id=self.bot_id,
            timestamp=datetime.now().isoformat()
        )

        try:
            full_response = await self._stream_and_collect_response(messages, request_id, session_id, username)
            collected_data.agent_answer = full_response

            state = get_captured_state(request_id)
            if state:
                self._extract_metrics_from_state(state, collected_data)
            else:
                LOGGER.warning("No captured state found")

            collected_data.status = "success"

        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc())
            collected_data.agent_answer = f"Error: {str(e)}"
            collected_data.error_message = str(e)
            collected_data.status = "error"

        return collected_data

    async def _stream_and_collect_response(
        self,
        messages: List[Dict],
        request_id: str,
        session_id: str,
        username: str
    ) -> str:
        full_response = []

        async for chunk in self._bot.run(
            messages=messages,
            client_message_id=request_id,
            session_id=session_id,
            role_ids=["L1"],
            username=username,
            topic="default"
        ):
            try:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    full_response.append(delta)
            except Exception as e:
                LOGGER.warning(f"Chunk processing error: {e}")

        return "".join(full_response)

    def _extract_metrics_from_state(self, state: WorkflowState, collected_data: HRRAGExecutionData):
        extractor = StateExtractor(state)
        collected_data.tool_calls = extractor.extract_tool_calls()
        collected_data.retrieved_docs = extractor.get_tool_outputs()
        collected_data.doc_ids = extractor.get_doc_ids()
        messages = extractor._get_final_state_messages()
        if messages:
            collected_data.final_state_messages = messages
        collected_data.agent_iterations = extractor.extract_iterations()


# =============================================================================
# Excel Exporter
# =============================================================================
class HRExcelExporter:
    """Export BeeHR data ra Excel file"""

    def __init__(self):
        self.execution_results: List[HRRAGExecutionData] = []

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

    def add_result(self, data: HRRAGExecutionData):
        self.execution_results.append(data)

    def export(self, output_path: str = "beehr_rag_export.xlsx"):
        wb = openpyxl.Workbook()
        self._create_main_sheet(wb)
        self._create_summary_sheet(wb)
        wb.save(output_path)
        print(f"[OK] Đã xuất file: {output_path}")
        return output_path

    def _create_main_sheet(self, wb: openpyxl.Workbook):
        ws = wb.active
        ws.title = "RAG Data"

        headers = [
            "STT", "Câu hỏi đầu vào", "Câu trả lời của Agent",
            "Tool result", "Tool calls", "Doc IDs", "Iterations",
            "Session ID", "Timestamp", "Status"
        ]

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = self.header_align
            cell.border = self.cell_border

        current_row = 2
        stt = 0

        for data in self.execution_results:
            stt += 1
            tool_outputs = data.retrieved_docs
            num_rows = max(len(tool_outputs), 1)

            question = data.input_question
            answer = data.agent_answer
            tool_calls = self._format_tool_calls(data.tool_calls)
            doc_ids = data.doc_ids
            iterations = data.agent_iterations
            session_id = data.session_id
            timestamp = data.timestamp
            status = data.status

            for i, tool_output_item in enumerate(tool_outputs):
                if i == 0:
                    ws.cell(row=current_row, column=1, value=stt)
                else:
                    ws.cell(row=current_row, column=1, value="")

                ws.cell(row=current_row, column=2, value=question if i == 0 else "")
                ws.cell(row=current_row, column=3, value=answer if i == 0 else "")

                output_val = tool_output_item.get('output', '')
                if isinstance(output_val, dict):
                    output_val = json.dumps(output_val, ensure_ascii=False, indent=2)
                if len(output_val) > 30000:
                    output_val = output_val[:30000] + "\n... [truncated]"
                ws.cell(row=current_row, column=4, value=output_val)

                tool_call_info = self._format_single_tool_call(data.tool_calls, i)
                ws.cell(row=current_row, column=5, value=tool_call_info)

                doc_id_info = self._format_single_doc_ids(doc_ids, i)
                ws.cell(row=current_row, column=6, value=doc_id_info)

                ws.cell(row=current_row, column=7, value=iterations if i == 0 else "")
                ws.cell(row=current_row, column=8, value=session_id if i == 0 else "")
                ws.cell(row=current_row, column=9, value=timestamp if i == 0 else "")
                ws.cell(row=current_row, column=10, value=status if i == 0 else "")

                for col in range(1, 11):
                    cell = ws.cell(row=current_row, column=col)
                    cell.border = self.cell_border
                    if col == 4:
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                    else:
                        cell.alignment = self.cell_align

                current_row += 1

            if num_rows > 1:
                merge_start = current_row - num_rows
                merge_end = current_row - 1

                ws.merge_cells(start_row=merge_start, start_column=1, end_row=merge_end, end_column=1)
                ws.cell(row=merge_start, column=1).alignment = Alignment(horizontal="center", vertical="center")

                ws.merge_cells(start_row=merge_start, start_column=2, end_row=merge_end, end_column=2)
                ws.cell(row=merge_start, column=2).alignment = Alignment(vertical="center", wrap_text=True)

                ws.merge_cells(start_row=merge_start, start_column=3, end_row=merge_end, end_column=3)
                ws.cell(row=merge_start, column=3).alignment = Alignment(vertical="center", wrap_text=True)

                ws.merge_cells(start_row=merge_start, start_column=7, end_row=merge_end, end_column=7)
                ws.cell(row=merge_start, column=7).alignment = Alignment(horizontal="center", vertical="center")

                ws.merge_cells(start_row=merge_start, start_column=8, end_row=merge_end, end_column=8)
                ws.merge_cells(start_row=merge_start, start_column=9, end_row=merge_end, end_column=9)
                ws.merge_cells(start_row=merge_start, start_column=10, end_row=merge_end, end_column=10)
                ws.cell(row=merge_start, column=10).alignment = Alignment(horizontal="center", vertical="center")

        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 30
        ws.column_dimensions['D'].width = 50
        ws.column_dimensions['E'].width = 20
        ws.column_dimensions['F'].width = 30
        ws.column_dimensions['G'].width = 10
        ws.column_dimensions['H'].width = 35
        ws.column_dimensions['I'].width = 20
        ws.column_dimensions['J'].width = 10

        for row in range(2, current_row):
            ws.row_dimensions[row].height = 60

    def _create_summary_sheet(self, wb: openpyxl.Workbook):
        ws = wb.create_sheet("Tổng kết")

        ws['A1'] = "BÁO CÁO TỔNG KẾT - BEE HR BOT"
        ws.merge_cells('A1:B1')
        ws['A1'].font = Font(bold=True, size=16, color="0D47A1")
        ws['A1'].alignment = Alignment(horizontal='center')

        summary_data = [
            ("Tổng số câu hỏi:", len(self.execution_results)),
            ("Thành công:", sum(1 for d in self.execution_results if d.status == "success")),
            ("Lỗi:", sum(1 for d in self.execution_results if d.status == "error")),
            ("Có tool outputs:", sum(1 for d in self.execution_results if d.retrieved_docs)),
            ("Không có tool outputs:", sum(1 for d in self.execution_results if not d.retrieved_docs)),
            ("Tổng tool outputs:", sum(len(d.retrieved_docs) for d in self.execution_results)),
            ("Tổng tool calls:", sum(len(d.tool_calls) for d in self.execution_results)),
            ("Tổng doc IDs:", sum(len(d.doc_ids) for d in self.execution_results)),
            ("Bot ID:", self.execution_results[0].bot_id if self.execution_results else "N/A"),
            ("Export time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]

        for row_idx, (label, value) in enumerate(summary_data, 3):
            ws[f'A{row_idx}'] = label
            ws[f'B{row_idx}'] = value
            ws[f'A{row_idx}'].font = Font(bold=True)

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 50

    @staticmethod
    def _format_tool_results(tool_outputs: List[Dict]) -> str:
        if not tool_outputs:
            return "Không có tool outputs"
        formatted = []
        for i, item in enumerate(tool_outputs, 1):
            tool_name = item.get('tool_name', 'unknown')
            output = item.get('output', {})
            output_str = json.dumps(output, ensure_ascii=False, indent=2)
            formatted.append(f"[{i}] Tool: {tool_name}\n{output_str}")
        return "\n" + "=" * 40 + "\n\n".join(formatted)

    @staticmethod
    def _format_tool_calls(tool_calls: List[Dict]) -> str:
        if not tool_calls:
            return "Không có tool calls"
        formatted = []
        for i, call in enumerate(tool_calls, 1):
            tool_name = call.get('name', 'unknown')
            args = call.get('arguments', {})
            formatted.append(f"[{i}] {tool_name}: {args}")
        return "\n".join(formatted)

    @staticmethod
    def _format_single_tool_call(tool_calls: List[Dict], index: int) -> str:
        if not tool_calls or index >= len(tool_calls):
            return ""
        call = tool_calls[index]
        tool_name = call.get('name', 'unknown')
        args = call.get('arguments', {})
        return f"{tool_name}: {args}"

    @staticmethod
    def _format_single_doc_ids(doc_ids: List[Dict], index: int) -> str:
        if not doc_ids or index >= len(doc_ids):
            return ""
        doc_id_item = doc_ids[index]
        ids = doc_id_item.get('ids', [])
        if not isinstance(ids, list):
            return str(ids)
        if ids and isinstance(ids[0], dict):
            formatted = []
            for item in ids:
                if "chunk_id" in item and "document_id" in item:
                    formatted.append(f"chunk: {item['chunk_id']}, doc: {item['document_id']}")
                else:
                    formatted.append(str(item))
            return ",\n".join(formatted)
        return ",\n".join(str(d) for d in ids)


# =============================================================================
# Main Entry Point
# =============================================================================
async def run_export(
    bot_id: str,
    questions: List[str],
    username: str = "liemlt1",
    output_file: str = "beehr_rag_export.xlsx"
):
    excel_exporter = HRExcelExporter()
    rag_exporter = HRRAGExporter(bot_id)

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Đang xử lý: {question[:60]}...")

        messages = [{"role": "user", "content": question}]
        result = await rag_exporter.run(messages, username=username)

        excel_exporter.add_result(result)

        print(f"  -> Answer length: {len(result.agent_answer)} chars")
        print(f"  -> Tool outputs: {len(result.retrieved_docs)}")
        print(f"  -> Tool calls: {len(result.tool_calls)}")
        print(f"  -> Doc IDs: {len(result.doc_ids)}")
        print(f"  -> Iterations: {result.agent_iterations}")
        print(f"  -> Status: {result.status}")

    excel_exporter.export(output_file)
    return output_file


def main():
    print("=" * 60)
    print("BeeHR RAG Workflow Data Export")
    print("=" * 60)

    HR_BOT_ID = "5d816aa9-a21c-4f02-92bf-a28d09aa0ef9"

    question_file = os.environ.get("QUESTION_FILE", r"D:\Download\Book1.xlsx")
    SAMPLE_QUESTIONS = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(question_file, data_only=True)
        ws = wb.active
        for row in list(ws.iter_rows(min_row=2, values_only=True))[:10]:
            q = row[0]
            if q and str(q).strip():
                SAMPLE_QUESTIONS.append(str(q).strip())
        print(f"[OK] Đã đọc {len(SAMPLE_QUESTIONS)} câu hỏi từ {question_file}")
    except Exception as e:
        print(f"[WARN] Không đọc được file Excel ({e}), dùng câu hỏi mẫu")
        SAMPLE_QUESTIONS = [
            "Chức danh của tôi là gì?",
            "Tôi còn bao nhiêu ngày phép?",
            "Đường dẫn HCM tại MB?",
        ]

    output_path = asyncio.run(run_export(
        bot_id=HR_BOT_ID,
        questions=SAMPLE_QUESTIONS,
        output_file="beehr_rag_export_v_[gemini-3.1-pro-chat].xlsx"
    ))

    print(f"\n[Xong] File đã được lưu tại: {output_path}")


if __name__ == "__main__":
    main()