from typing import Dict, Any, Optional
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.data.redis_node import RedisNode
from beegen.configs.cache.redis_config import RedisOperation
import json


from typing import Dict, Any, Optional

from typing import Dict, Any, Optional

from typing import Dict, Any, Optional

import json
from typing import Dict, Any, Optional

def manage_session_hierarchy_with_comparison(
    cached: Dict[str, Optional[str]],
    count_scenario: int,
    L1: Optional[str] = None,
    L2: Optional[str] = None,
    L3: Optional[str] = None,
) -> Dict[str, str]:
    """
    Xử lý logic hierarchy L1, L2, L3 với việc so sánh giá trị cũ và mới.
    
    Logic:
    - Nếu cập nhật L1 mới (khác L1 cũ):
      + Nếu L2 cũng được cung cấp -> set L1, L2, reset L3
      + Nếu L2 không được cung cấp -> set L1, reset L2, L3
    - Nếu cập nhật L2 mới (khác L2 cũ) -> set L2, reset L3
    - Nếu cập nhật L3 (khác None) -> set L1="Tín dụng", L2="SXKD", giữ L3
    
    Args:
        cached: Dict chứa giá trị cũ từ Redis {"L1": "...", "L2": "...", "L3": "..."}
        L1: Giá trị L1 mới (None hoặc empty string nếu không cập nhật)
        L2: Giá trị L2 mới (None hoặc empty string nếu không cập nhật)
        L3: Giá trị L3 mới (None hoặc empty string nếu không cập nhật)
        
    Returns:
        Dict với key "updated_cache" chứa JSON string của L1, L2, L3
        {"updated_cache": '{"L1": "...", "L2": "...", "L3": "..."}'}
    """
    # Lấy giá trị cũ từ cached, convert empty string thành None
    old_L1 = cached.get("L1") or None
    old_L2 = cached.get("L2") or None
    old_L3 = cached.get("L3") or None
    
    # Convert empty string thành None cho giá trị mới
    new_L1 = L1 if L1 else None
    new_L2 = L2 if L2 else None
    new_L3 = L3 if L3 else None
    
    # Khởi tạo result với giá trị cũ
    result = {
        "L1": old_L1,
        "L2": old_L2,
        "L3": old_L3,
        "count_scenario": count_scenario,
    }
    
    # Logic 3: Nếu L3 được cung cấp -> set L1="Tín dụng", L2="SXKD"
    # Ưu tiên check L3 trước vì nó override L1 và L2
    if new_L3 is not None:
        result["L1"] = "Tín dụng"
        result["L2"] = "SXKD"
        result["L3"] = new_L3
        return {"updated_cache": json.dumps(result, ensure_ascii=False)}
    
    # Logic 1: Nếu L1 được cung cấp
    if new_L1 is not None:
        # Nếu L1 mới khác L1 cũ
        if new_L1 != old_L1:
            result["L1"] = new_L1
            # Nếu L2 cũng được cung cấp cùng lúc -> set L2, reset L3
            if new_L2 is not None:
                result["L2"] = new_L2
                result["L3"] = None
            else:
                # L2 không được cung cấp -> reset cả L2 và L3
                result["L2"] = None
                result["L3"] = None
            return {"updated_cache": json.dumps(result, ensure_ascii=False)}
        else:
            # L1 không thay đổi, giữ nguyên
            result["L1"] = new_L1
    
    # Logic 2: Nếu L2 được cung cấp (và L1 không thay đổi hoặc không được cung cấp)
    if new_L2 is not None:
        # Nếu L2 mới khác L2 cũ -> reset L3
        if new_L2 != old_L2:
            result["L2"] = new_L2
            result["L3"] = None
            return {"updated_cache": json.dumps(result, ensure_ascii=False)}
        else:
            # L2 không thay đổi, giữ nguyên
            result["L2"] = new_L2
    
    return {"updated_cache": json.dumps(result, ensure_ascii=False)}

def prepare_redis_key(session_id: str) -> Dict[str, str]:
    """Tạo Redis key từ session_id."""
    return {
        "key": f"{session_id}"
    }


def parse_session_data(
    session_id: str,
    redis_value: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Parse dữ liệu session từ Redis response.
    
    Args:
        session_id: ID của session
        redis_value: Response từ RedisNode GET operation
        
    Returns:
        Dict với key "session_cache" chứa toàn bộ thông tin session
    """
    if not redis_value or redis_value.get("value") is None:
        return {
            "session_cache": {
                "session_id": session_id,
                "username": None,
                "L1": None,
                "L2": None,
                "L3": None,
                "exists": False
            }
        }
    
    try:
        value = redis_value.get("value")
        if isinstance(value, str):
            data = json.loads(value)
        else:
            data = value
        
        return {
            "session_cache": {
                "session_id": data.get("session_id", session_id),
                "username": data.get("username"),
                "L1": data.get("L1"),
                "L2": data.get("L2"),
                "L3": data.get("L3"),
                "exists": True
            }
        }
    except Exception as e:
        print(f"Error parsing session data: {e}")
        return {
            "session_cache": {
                "session_id": session_id,
                "username": None,
                "L1": None,
                "L2": None,
                "L3": None,
                "exists": False
            }
        }