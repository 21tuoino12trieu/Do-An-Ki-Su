"""
DAG Resolver - Tạo dag_id từ channel và process_type.

Convention:
    dag_cua_{channel}_{process_type}   (channel có giá trị)
    dag_cua_{process_type}             (channel None/rỗng)

Ngoại lệ (special mapping):
    process_type=quality → dag_cua_document_quality  (bất kể channel)

Ví dụ:
    "HCM" + "classification" → "dag_cua_hcm_classification"
    "HCM" + "extraction"     → "dag_cua_hcm_extraction"
    None  + "classification" → "dag_cua_classification"
    *     + "quality"        → "dag_cua_document_quality"
"""

from src.models.message import ProcessType
from src.models.exceptions import ProcessTypeNotFoundError


# DAG_PREFIX cố định, không thay đổi
_DAG_PREFIX = "dag_cua"

# Mapping đặc biệt: process_type → dag_id cố định, bỏ qua channel
_SPECIAL_DAG_MAP: dict[ProcessType, str] = {
    ProcessType.QUALITY: f"{_DAG_PREFIX}_document_quality",
}

def resolve_dag_id(process_type: ProcessType, channel: str | None) -> str:
    """
    Trả về dag_id theo convention dag_cua_{channel}_{process_type}.

    Ưu tiên:
      1. Nếu process_type có trong _SPECIAL_DAG_MAP → trả về dag_id cố định.
      2. Nếu channel có giá trị → dag_cua_{channel}_{process_type}
      3. Nếu channel None/rỗng  → dag_cua_{process_type}

    Args:
        process_type: Enum ProcessType đã validate.
        channel:      Mã kênh (hcm, pams, ...). None/rỗng được chấp nhận.

    Returns:
        dag_id dạng lowercase string.

    Raises:
        ProcessTypeNotFoundError: Nếu process_type không hợp lệ.
    """
    if process_type not in ProcessType.__members__.values():
        raise ProcessTypeNotFoundError(
            f"process_type '{process_type}' không tồn tại trong hệ thống"
        )

    # Kiểm tra special mapping trước
    if process_type in _SPECIAL_DAG_MAP:
        return _SPECIAL_DAG_MAP[process_type]

    # Convention thông thường
    channel_part = (channel or "").strip()
    if channel_part:
        return f"{_DAG_PREFIX}_{channel_part}_{process_type.value}".lower()
    return f"{_DAG_PREFIX}_{process_type.value}".lower()