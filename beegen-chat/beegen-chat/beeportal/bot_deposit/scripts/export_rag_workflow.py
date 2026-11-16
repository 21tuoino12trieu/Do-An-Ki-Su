# -*- coding: utf-8 -*-
"""
Script xuất dữ liệu RAG từ workflow của bot_deposit ra file Excel

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
    python -m beeportal.bot_deposit.scripts.export_rag_workflow
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
from beeportal.bot_deposit.bot import BeeDeposit


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
class DepositRAGExecutionData:
    """Lưu trữ dữ liệu từ một lần chạy Deposit RAG workflow"""
    # Input
    input_question: str = ""

    # Metrics từ state
    tool_calls: List[Dict] = field(default_factory=list)
    retrieved_docs: List[Dict] = field(default_factory=list)
    doc_ids: List[Dict] = field(default_factory=list)
    agent_iterations: int = 0

    # Output
    agent_answer: str = ""
    final_state_messages: List[Dict] = field(default_factory=list)

    # Metadata
    request_id: str = ""
    session_id: str = ""
    bot_id: str = ""
    timestamp: str = ""
    status: str = "pending"
    error_message: str = ""


# =============================================================================
# State Extractor - Trích xuất metrics từ WorkflowState
# =============================================================================
class StateExtractor:
    """
    Trích xuất documents, tool_calls, iterations từ WorkflowState.

    CÁCH ACCESS STATE:
    ==================

    1. WorkflowState có cấu trúc:
       - state._indexer: Mapping (node_name, var_name) -> index
       - state._values: List[VariableCell] - chứa giá trị theo index
       - state._values[index].contexts: Dict[context_id, value]
       - state.execution_order: List[Dict] - thứ tự execute các nodes

    2. Cách lấy giá trị:
       ```python
       cell = state.get(node_name, var_name)  # Lấy VariableCell
       value = cell.contexts.get(context_id)  # Lấy value với context_id
       # hoặc:
       value = cell.contexts.get(None)  # Lấy value không có context
       ```

    3. Node paths trong workflow:
       - beeDeposit.react_agent.pev_loop.__inner__.planner_native (LLM Node)
       - beeDeposit.react_agent.pev_loop.__inner__.tool_executor (Tool Executor)
       - beeDeposit.react_agent.pev_loop.__inner__.tool_executor.retrieval_graph (Retrieval Tool)
       - beeDeposit.react_agent.pev_loop.__inner__.tool_executor.{tool_name} (Các tools khác)

    4. Context IDs:
       - While loop tạo ra các context: "while[0]", "while[1]", "while[2]", ...
       - Nodes không trong while loop có context_id = None
    """

    # Node paths trong workflow
    REACT_AGENT_NODES = [
        "beeDeposit.react_agent",
        "beeDeposit.react_agent.pev_loop",
        "beeDeposit.react_agent.pev_loop.__inner__"
    ]
    FINAL_STATE_MESSAGES_VAR = "final_state_messages"
    TOOL_EXECUTOR_NODE = "beeDeposit.react_agent.pev_loop.__inner__.tool_executor"
    TOOL_EXECUTOR_OUTPUT_VAR = "result"

    def __init__(self, state: WorkflowState):
        self.state = state

    # -------------------------------------------------------------------------
    # Tool Calls - Trích xuất từ messages
    # -------------------------------------------------------------------------
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

        LOGGER.info(f"Extracted {len(tool_calls)} tool calls from messages")
        return tool_calls

    # -------------------------------------------------------------------------
    # Tool Outputs - Lấy output thuần của tool
    # -------------------------------------------------------------------------
    def get_tool_outputs(self) -> List[Dict]:
        """
        Lấy tất cả outputs từ tool_executor.

        Returns:
            List of tool outputs, mỗi item gồm:
            - tool_name: tên tool
            - output: raw output của tool
        """
        outputs = []
        try:
            cell = self.state.get(self.TOOL_EXECUTOR_NODE, self.TOOL_EXECUTOR_OUTPUT_VAR)
            if cell is None:
                return outputs

            # Lấy tất cả values từ cell.contexts
            for ctx_id, value in cell.contexts.items():
                if value is not None:
                    outputs.append({
                        "tool_name": "tool_executor",
                        "output": value
                    })

            # Nếu cell không phải VariableCell mà là giá trị trực tiếp
            if hasattr(cell, 'contexts') is False and outputs == []:
                outputs.append({
                    "tool_name": "tool_executor",
                    "output": cell
                })

        except Exception as e:
            LOGGER.debug(f"Could not get tool outputs: {e}")

        LOGGER.info(f"Got {len(outputs)} tool outputs")
        return outputs

    # -------------------------------------------------------------------------
    # Doc IDs - Lấy IDs của documents được retrieve từ Tool outputs
    # -------------------------------------------------------------------------
    def get_doc_ids(self) -> List[Dict]:
        """
        Lấy danh sách doc IDs từ Tool outputs.

        Tool output có thể có các format:
        1. {"data": [{"_id": "..."}]}
        2. {"docs": [{"id": "...", "doc": "..."}]}  -> lấy "doc" làm doc_id
        3. {"data": [{"document_id": "..."}]}
        4. {"_id": "..."}

        Returns:
            List of doc ID outputs, mỗi item gồm:
            - doc_ids: danh sách document IDs
        """
        outputs = []
        tool_outputs = self.get_tool_outputs()
        print("tool_outputs:")
        from pprint import pprint
        pprint(tool_outputs)

        for tool_output in tool_outputs:
            output = tool_output.get('output', {})
            if not isinstance(output, dict):
                continue

            doc_ids = []

            # Format 1: {"data": [{"_id": "..."}]}
            if "data" in output and isinstance(output["data"], list):
                for item in output["data"]:
                    if "_id" in item and "document_id" in item:
                        doc_ids.append({"chunk_id": item["_id"], "document_id": item["document_id"]})
                    elif "_id" in item:
                        doc_ids.append(item["_id"])

            print(doc_ids)

            # Format 2: {"docs": [{"id": "...", "doc": "..."}]}
            if "docs" in output and isinstance(output["docs"], list):
                for item in output["docs"]:
                    if "doc" in item and "id" in item:
                        doc_ids.append({"chunk_id": item["id"], "document_id": item["doc"]})

            # Format 3: {"document_id": "..."}
            # if "document_id" in output:
            #     doc_ids.append({"chunk_id": output["_id"], "document_id" : output["document_id"]})

            # # Format 4: {"_id": "..."}
            # if "_id" in output and "data" not in output and "docs" not in output:
            #     doc_ids.append(output["_id"])

            if doc_ids:
                outputs.append({
                    "tool_name": tool_output.get("tool_name", "unknown"),
                    "ids": doc_ids
                })

        LOGGER.info(f"Extracted {len(outputs)} doc ID outputs")
        return outputs

    def _detect_context_ids(self) -> List[str]:
        """Tự động detect tất cả context_ids từ execution_order"""
        context_ids = set()
        for ex in self.state.execution_order:
            ctx = ex.get("context_id")
            if ctx:
                context_ids.add(ctx)
        # Ưu tiên các context mới hơn
        return sorted(context_ids, reverse=True) + [None]

    # -------------------------------------------------------------------------
    # Generic State Value Access - Lấy giá trị bất kỳ từ state
    # -------------------------------------------------------------------------
    def get_state_value(self, node_path: str, var_name: str, default: Any = None) -> Any:
        """
        Lấy giá trị bất kỳ từ state.

        Args:
            node_path: Đường dẫn đầy đủ của node (VD: "beeDeposit.react_agent.pev_loop.__inner__.planner_native")
            var_name: Tên biến cần lấy (VD: "messages", "docs", "content")
            default: Giá trị mặc định nếu không tìm thấy

        Returns:
            Giá trị của biến hoặc default

        Ví dụ:
            # Lấy messages từ planner_native
            messages = extractor.get_state_value("beeDeposit.react_agent.pev_loop.__inner__.planner_native", "messages")

            # Lấy docs từ search_tool
            results = extractor.get_state_value("beeDeposit.react_agent.pev_loop.__inner__.tool_executor.search_tool", "results")

            # Lấy content từ final_output
            content = extractor.get_state_value("beeDeposit.react_agent.pev_loop.__inner__.final_output", "content")
        """
        for ctx_id in self._detect_context_ids():
            cell = self._get_state_cell(node_path, var_name, ctx_id)
            if cell is None:
                continue

            value = cell.contexts.get(ctx_id) if ctx_id else cell

            # Nếu value là VariableCell, lấy từ contexts
            if hasattr(value, 'contexts'):
                value = value.contexts.get(ctx_id) or value.contexts.get(None)

            if value is not None:
                return value

        return default

    def get_all_node_outputs(self, node_prefix: str) -> Dict[str, Any]:
        """
        Lấy tất cả outputs từ các nodes có prefix cho trước.

        Args:
            node_prefix: Prefix của node (VD: "beeDeposit.react_agent.pev_loop.__inner__.tool_executor")

        Returns:
            Dict mapping (node, var) -> value

        Ví dụ:
            # Lấy tất cả outputs từ tool_executor và các sub-nodes
            outputs = extractor.get_all_node_outputs("beeDeposit.react_agent.pev_loop.__inner__.tool_executor")
            # Kết quả: {
            #     ("retrieval_graph", "docs"): [...],
            #     ("search_tool", "results"): [...],
            #     ("get_document_content", "data"): {...}
            # }
        """
        results = {}
        for (node, var), index in self.state._indexer.items():
            if node.startswith(node_prefix):
                try:
                    value = self.state.get(node, var)
                    if hasattr(value, 'contexts'):
                        # Lấy giá trị đầu tiên không None
                        for ctx_id in self._detect_context_ids():
                            v = value.contexts.get(ctx_id)
                            if v is not None:
                                results[(node, var)] = v
                                break
                    else:
                        results[(node, var)] = value
                except Exception:
                    pass
        return results

    # -------------------------------------------------------------------------
    # Iterations
    # -------------------------------------------------------------------------
    def extract_iterations(self) -> int:
        """Đếm số iterations từ execution_order"""
        count = 0
        for ex in self.state.execution_order:
            node = ex.get("node", "")
            if "planner_native" in node or "planner" in node.lower():
                count += 1

        LOGGER.info(f"Counted {count} iterations from state")
        return count

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    def _get_final_state_messages(self) -> List[Dict]:
        """Lấy final_state_messages từ state"""
        for ctx_id in self._detect_context_ids():
            for node_name in self.REACT_AGENT_NODES:
                messages = self._try_get_messages(node_name, self.FINAL_STATE_MESSAGES_VAR, ctx_id)
                if messages:
                    LOGGER.info(f"Got messages from {node_name}.{self.FINAL_STATE_MESSAGES_VAR}[ctx={ctx_id}]: {len(messages)}")
                    return messages
        return []

    def _try_get_messages(self, node_name: str, var_name: str, ctx_id: str) -> Optional[List[Dict]]:
        """Thử lấy messages từ một node"""
        try:
            cell = self.state.get(node_name, var_name)
            if cell is None:
                return None

            # Get value từ VariableCell
            if ctx_id is not None:
                value = cell.contexts.get(ctx_id)
            else:
                value = cell

            # Check nếu value là VariableCell
            if hasattr(value, 'contexts'):
                value = value.contexts.get(ctx_id) or value.contexts.get(None, [])

            if value and isinstance(value, list) and len(value) > 0:
                return value

            return None
        except Exception as e:
            LOGGER.debug(f"Could not get {node_name}.{var_name}[ctx={ctx_id}]: {e}")
            return None

    def _get_state_cell(self, node_name: str, var_name: str, ctx_id: str) -> Optional[VariableCell]:
        """Lấy VariableCell từ state"""
        try:
            return self.state.get(node_name, var_name)
        except Exception as e:
            LOGGER.debug(f"Could not get cell {node_name}.{var_name}: {e}")
            return None

    def list_available_nodes(self) -> List[str]:
        """
        Liệt kê tất cả nodes có trong state indexer.
        Hữu ích để khám phá cấu trúc workflow.

        Returns:
            List of node names
        """
        nodes = set()
        for (node, var) in self.state._indexer:
            nodes.add(node)
        return sorted(list(nodes))

    def list_available_vars(self, node_name: str) -> List[str]:
        """
        Liệt kê tất cả biến của một node.

        Args:
            node_name: Tên node cần xem

        Returns:
            List of variable names
        """
        return [var for (n, var) in self.state._indexer if n == node_name]


# =============================================================================
# Deposit RAG Exporter - Chạy workflow và thu thập dữ liệu
# =============================================================================
class DepositRAGExporter:
    """Chạy Deposit workflow và thu thập metrics"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self._bot = self._init_bot()

    def _init_bot(self) -> BeeDeposit:
        """Khởi tạo BeeDeposit bot"""
        try:
            bot = BeeDeposit(bot_id=self.bot_id)
            LOGGER.info(f"Initialized BeeDeposit bot: {self.bot_id}")
            return bot
        except Exception as e:
            LOGGER.error(f"Failed to init bot: {e}")
            raise

    async def run(self, messages: List[Dict], session_id: Optional[str] = None) -> DepositRAGExecutionData:
        """Chạy workflow và thu thập dữ liệu"""

        request_id = str(uuid.uuid4())
        if not session_id:
            session_id = str(uuid.uuid4())

        # Khởi tạo data collector
        collected_data = DepositRAGExecutionData(
            input_question=messages[-1]['content'] if messages else "",
            request_id=request_id,
            session_id=session_id,
            bot_id=self.bot_id,
            timestamp=datetime.now().isoformat()
        )

        try:
            # Chạy workflow với streaming để thu thập answer
            full_response = await self._stream_and_collect_response(messages, request_id, session_id)
            collected_data.agent_answer = full_response

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
            collected_data.agent_answer = f"Error: {str(e)}"
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

    def _extract_metrics_from_state(self, state: WorkflowState, collected_data: DepositRAGExecutionData):
        """Trích xuất metrics từ state sau khi workflow chạy xong"""
        extractor = StateExtractor(state)

        # Extract tool calls
        collected_data.tool_calls = extractor.extract_tool_calls()

        # Extract tool outputs (bao gồm docs, search results, etc.)
        collected_data.retrieved_docs = extractor.get_tool_outputs()

        # Extract doc IDs
        collected_data.doc_ids = extractor.get_doc_ids()

        # Extract final state messages nếu có
        messages = extractor._get_final_state_messages()
        if messages:
            collected_data.final_state_messages = messages

        # Count iterations
        collected_data.agent_iterations = extractor.extract_iterations()


# =============================================================================
# Excel Exporter - Xuất dữ liệu ra file Excel
# =============================================================================
class DepositExcelExporter:
    """Export Deposit RAG data ra Excel file"""

    def __init__(self):
        self.execution_results: List[DepositRAGExecutionData] = []

        # Styles
        self.header_font = Font(bold=True, color="FFFFFF", size=11)
        self.header_fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
        self.header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.cell_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        self.cell_align = Alignment(vertical="top", wrap_text=True)

    def add_result(self, data: DepositRAGExecutionData):
        """Thêm một kết quả execution"""
        self.execution_results.append(data)

    def export(self, output_path: str = "deposit_rag_export.xlsx"):
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
        """Tạo sheet chính với dữ liệu RAG - mỗi tool là một hàng"""
        ws = wb.active
        ws.title = "RAG Data"

        headers = [
            "STT", "Câu hỏi đầu vào", "Câu trả lời của Agent",
            "Tool result", "Tool calls", "Doc IDs", "Iterations",
            "Session ID", "Timestamp", "Status"
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

        # Mỗi câu hỏi có thể có nhiều tool outputs -> nhiều hàng
        for data in self.execution_results:
            stt += 1
            tool_outputs = data.retrieved_docs
            num_rows = max(len(tool_outputs), 1)  # Ít nhất 1 hàng

            # Format các giá trị cần gộp
            question = data.input_question
            answer = data.agent_answer
            tool_calls = self._format_tool_calls(data.tool_calls)
            doc_ids = data.doc_ids
            iterations = data.agent_iterations
            session_id = data.session_id
            timestamp = data.timestamp
            status = data.status

            # Ghi từng tool output là một hàng
            for i, tool_output_item in enumerate(tool_outputs):
                # STT - chỉ hàng đầu tiên
                if i == 0:
                    ws.cell(row=current_row, column=1, value=stt)
                else:
                    ws.cell(row=current_row, column=1, value="")

                # Câu hỏi - gộp tất cả các hàng
                ws.cell(row=current_row, column=2, value=question if i == 0 else "")

                # Answer - gộp tất cả các hàng
                ws.cell(row=current_row, column=3, value=answer if i == 0 else "")

                # Tool result - mỗi hàng một tool output
                output_val = tool_output_item.get('output', '')
                if isinstance(output_val, dict):
                    output_val = json.dumps(output_val, ensure_ascii=False, indent=2)
                # Truncate nếu quá dài (> 30000 ký tự)
                if len(output_val) > 30000:
                    output_val = output_val[:30000] + "\n... [truncated]"
                ws.cell(row=current_row, column=4, value=output_val)

                # Tool calls - tương ứng với mỗi tool result
                tool_call_info = self._format_single_tool_call(data.tool_calls, i)
                ws.cell(row=current_row, column=5, value=tool_call_info)

                # Doc IDs - tương ứng với mỗi tool result
                doc_id_info = self._format_single_doc_ids(doc_ids, i)
                ws.cell(row=current_row, column=6, value=doc_id_info)

                # Iterations - gộp
                ws.cell(row=current_row, column=7, value=iterations if i == 0 else "")

                # Session ID - gộp
                ws.cell(row=current_row, column=8, value=session_id if i == 0 else "")

                # Timestamp - gộp
                ws.cell(row=current_row, column=9, value=timestamp if i == 0 else "")

                # Status - gộp
                ws.cell(row=current_row, column=10, value=status if i == 0 else "")

                # Apply styles
                for col in range(1, 11):
                    cell = ws.cell(row=current_row, column=col)
                    cell.border = self.cell_border
                    if col == 4:
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                    else:
                        cell.alignment = self.cell_align

                current_row += 1

            # Merge các ô cho cùng một câu hỏi (trừ Tool result)
            if num_rows > 1:
                merge_start = current_row - num_rows
                merge_end = current_row - 1

                # Merge STT
                ws.merge_cells(start_row=merge_start, start_column=1, end_row=merge_end, end_column=1)
                ws.cell(row=merge_start, column=1).alignment = Alignment(horizontal="center", vertical="center")

                # Merge Câu hỏi
                ws.merge_cells(start_row=merge_start, start_column=2, end_row=merge_end, end_column=2)
                ws.cell(row=merge_start, column=2).alignment = Alignment(vertical="center", wrap_text=True)

                # Merge Answer
                ws.merge_cells(start_row=merge_start, start_column=3, end_row=merge_end, end_column=3)
                ws.cell(row=merge_start, column=3).alignment = Alignment(vertical="center", wrap_text=True)

                # Không merge Tool calls - mỗi hàng một tool call tương ứng với tool result

                # Không merge Doc IDs - mỗi hàng một doc IDs tương ứng với tool result

                # Merge Iterations
                ws.merge_cells(start_row=merge_start, start_column=7, end_row=merge_end, end_column=7)
                ws.cell(row=merge_start, column=7).alignment = Alignment(horizontal="center", vertical="center")

                # Merge Session ID
                ws.merge_cells(start_row=merge_start, start_column=8, end_row=merge_end, end_column=8)

                # Merge Timestamp
                ws.merge_cells(start_row=merge_start, start_column=9, end_row=merge_end, end_column=9)

                # Merge Status
                ws.merge_cells(start_row=merge_start, start_column=10, end_row=merge_end, end_column=10)
                ws.cell(row=merge_start, column=10).alignment = Alignment(horizontal="center", vertical="center")

        # Column widths
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

        # Row heights
        for row in range(2, current_row):
            ws.row_dimensions[row].height = 60

    def _create_summary_sheet(self, wb: openpyxl.Workbook):
        """Tạo sheet tổng kết"""
        ws = wb.create_sheet("Tổng kết")

        ws['A1'] = "BÁO CÁO TỔNG KẾT - DEPOSIT BOT"
        ws.merge_cells('A1:B1')
        ws['A1'].font = Font(bold=True, size=16, color="1B5E20")
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
    def _format_tool_result(tool_outputs: List[Dict]) -> str:
        """Format tool outputs thành readable text"""
        if not tool_outputs:
            return "Không có tool outputs"

        formatted = []
        for i, item in enumerate(tool_outputs, 1):
            tool_name = item.get('tool_name', 'unknown')
            output = item.get('output', {})
            output_str = json.dumps(output, ensure_ascii=False, indent=2)

            # Truncate nếu quá dài
            # if len(output_str) > 500:
            #     output_str = output_str[:500] + "..."

            formatted.append(f"[{i}] Tool: {tool_name}\n{output_str}")

        return "\n" + "=" * 40 + "\n\n".join(formatted)

    @staticmethod
    def _format_tool_calls(tool_calls: List[Dict]) -> str:
        """Format tool calls thành readable text"""
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
        """Format một tool call cụ thể theo index"""
        if not tool_calls or index >= len(tool_calls):
            return ""

        call = tool_calls[index]
        tool_name = call.get('name', 'unknown')
        args = call.get('arguments', {})
        return f"{tool_name}: {args}"

    @staticmethod
    def _format_single_doc_ids(doc_ids: List[Dict], index: int) -> str:
        """Format doc IDs từ get_references_ids theo index"""
        if not doc_ids or index >= len(doc_ids):
            return ""

        doc_id_item = doc_ids[index]
        doc_ids_list = doc_id_item.get('ids', [])

        if not isinstance(doc_ids_list, list):
            return str(doc_ids_list)

        # Xử lý list of dicts (VD: [{"chunk_id": "...", "document_id": "..."}])
        if doc_ids_list and isinstance(doc_ids_list[0], dict):
            formatted = []
            for item in doc_ids_list:
                if "chunk_id" in item and "document_id" in item:
                    formatted.append(f"chunk: {item['chunk_id']}, doc: {item['document_id']}")
                else:
                    formatted.append(str(item))
            return ",\n".join(formatted)

        return ",\n".join(str(d) for d in doc_ids_list)


# =============================================================================
# Main Entry Point
# =============================================================================
async def run_export(
    bot_id: str,
    questions: List[str],
    output_file: str = "deposit_rag_export.xlsx"
):
    """
    Chạy export với danh sách câu hỏi

    Args:
        bot_id: ID của bot deposit
        questions: Danh sách câu hỏi cần export
        output_file: Đường dẫn file Excel output
    """
    excel_exporter = DepositExcelExporter()
    rag_exporter = DepositRAGExporter(bot_id)

    for i, question in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Đang xử lý: {question[:60]}...")

        messages = [{"role": "user", "content": question}]
        result = await rag_exporter.run(messages)

        excel_exporter.add_result(result)

        print(f"  -> Answer length: {len(result.agent_answer)} chars")
        print(f"  -> Tool outputs: {len(result.retrieved_docs)}")
        print(f"  -> Tool calls: {len(result.tool_calls)}")
        print(f"  -> Doc IDs: {len(result.doc_ids)}")
        print(f"  -> Status: {result.status}")

    excel_exporter.export(output_file)
    return output_file


def main():
    """Main entry point"""
    print("=" * 60)
    print("Deposit RAG Workflow Data Export")
    print("=" * 60)

    # Bot ID cho deposit (thay đổi theo bot thực tế)
    DEPOSIT_BOT_ID = "347f7a6e-83d2-4cfa-9e85-6bc080c234c4"

    # Danh sách câu hỏi mẫu
    SAMPLE_QUESTIONS = [
        "Bạn có những đầu tài liệu nào",
        "Chương trình đường đua rực lửa? (dùng tool search keyword)",
        "Tìm cho tôi Sản phẩm tiết kiệm nào có lãi suất cao nhất? tìm lần lươt các đầu tài liệu",
        "Lấy cho tôi tài liệu có id: 31825c17-18da-4b2e-a13c-93966b550634",
        "Chương trình đường đua rực lửa? (dùng retrieval_graph)"
    ]

    output_path = asyncio.run(run_export(
        bot_id=DEPOSIT_BOT_ID,
        questions=SAMPLE_QUESTIONS,
        output_file="deposit_rag_export.xlsx"
    ))

    print(f"\n[Xong] File đã được lưu tại: {output_path}")


if __name__ == "__main__":
    main()
