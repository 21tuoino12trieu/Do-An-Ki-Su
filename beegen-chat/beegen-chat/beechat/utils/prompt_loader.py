import inspect
import importlib
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from beegenerate.loggings.loggers import lf

WEEKDAY_MAP = {
    0: "thứ hai",
    1: "thứ ba",
    2: "thứ tư",
    3: "thứ năm",
    4: "thứ sáu",
    5: "thứ bảy",
    6: "chủ nhật",
}

def format_datetime_vi(dt: datetime) -> str:
    """
    Format datetime thành chuỗi:
    '12 giờ 34 phút, thứ sáu ngày 3 tháng 4 năm 2026'
    """
    return (
        f"{dt.strftime('%H')} giờ {dt.strftime('%M')} phút, "
        f"{WEEKDAY_MAP[dt.weekday()]} "
        f"ngày {dt.day} tháng {dt.month} năm {dt.year}"
    )

class DefaultDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"

def get_prompt(prompt_name: str, ttl: int=60):
    """
    Tạm thời sử dụng prompt local cho folder beechat.

    Langfuse prompt loading được tạm comment out để có thể rollback dễ dàng khi cần.
    """
    now = format_datetime_vi(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")))

    # ---------------------------------------------------------------------------
    # TẠM THỜI OFF LANGFUSE PROMPT LOADING (UNCOMMENT KHỐI BÊN DƯỚI ĐỂ ROLLBACK)
    # ---------------------------------------------------------------------------
    # try:
    #     formatted_prompt_name = f"BEEAPP_{prompt_name}"
    #     prompt_obj = lf.get_prompt(name=formatted_prompt_name, cache_ttl_seconds=ttl)
    #
    #     # Langfuse SDK thường trả về object có thuộc tính `.prompt`
    #     if hasattr(prompt_obj, "prompt"):
    #         return prompt_obj.prompt.format_map(DefaultDict(current_date=now))
    #     if isinstance(prompt_obj, str):
    #         return prompt_obj.format_map(DefaultDict(current_date=now))
    #     return str(prompt_obj).format_map(DefaultDict(current_date=now))
    # except Exception as e:
    #     pass
    # ---------------------------------------------------------------------------

    # 1. Lấy prompt constant trong caller globals (module gọi get_prompt)
    frame = inspect.currentframe()
    caller_globals = frame.f_back.f_globals if frame and frame.f_back else {}
    if prompt_name in caller_globals:
        return caller_globals[prompt_name].format_map(DefaultDict(current_date=now))

    # 2. Lấy prompt constants được export qua package `beechat.prompts`
    try:
        prompts_pkg = importlib.import_module("beechat.prompts")
        if hasattr(prompts_pkg, prompt_name):
            return getattr(prompts_pkg, prompt_name).format_map(DefaultDict(current_date=now))
    except Exception as e:
        pass

    raise KeyError(
        f"Không tìm thấy prompt constant '{prompt_name}' trong caller globals "
        f"hoặc trong package 'beechat.prompts'."
    )

if __name__ == "__main__":
    print(get_prompt("ANALIZE_TOPIC_AND_SENTIMENT_PROMPT"))
