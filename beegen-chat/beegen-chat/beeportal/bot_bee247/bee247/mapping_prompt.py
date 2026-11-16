from typing import Dict, Optional
from beeportal.utils import PROMPTS

# Template mapping với các topic MỚI từ LLM classification
TEMPLATE_MAPPING_PROMPTS: Dict[str, str] = {
    # Hướng dẫn
    "hướng dẫn định danh": PROMPTS["BEE247:HUONG_DAN"],
    "hướng dẫn xử lý": PROMPTS["BEE247:HUONG_DAN"],
    "Hướng dẫn": PROMPTS["BEE247:HUONG_DAN"],
    "kịch bản": PROMPTS["BEE247:KICH_BAN"],
    
    # Phí và lãi suất
    "lãi suất, biểu phí": PROMPTS["BEE247:LAI_SUAT_BIEU_PHI"],
    "Lãi suất": PROMPTS["BEE247:LAI_SUAT_BIEU_PHI"],
    "Biểu phí": PROMPTS["BEE247:LAI_SUAT_BIEU_PHI"],
    
    # Sản phẩm
    "sản phẩm thẻ": PROMPTS["BEE247:CARD"],
    "Sản phẩm - KHCN - Thẻ": PROMPTS["BEE247:CARD"],
    "Sản phẩm - KHDN - Thẻ": PROMPTS["BEE247:CARD"],

    "vay": PROMPTS["BEE247:VAY"],
    "Sản phẩm - KHCN - Chương trình Vay": PROMPTS["BEE247:VAY"],
    "Sản phẩm - KHDN - Chương trình Vay": PROMPTS["BEE247:VAY"],

    "ngân hàng điện tử": PROMPTS["BEE247:NGAN_HANG_DIEN_TU"],
    "Sản phẩm - KHCN - NHĐT": PROMPTS["BEE247:NGAN_HANG_DIEN_TU"],
    "Sản phẩm - KHDN - NHĐT": PROMPTS["BEE247:NGAN_HANG_DIEN_TU"],

    "tài khoản thanh toán": PROMPTS["BEE247:TKTT"],
    "Sản phẩm - KHCN - TKTT": PROMPTS["BEE247:TKTT"],
    "Sản phẩm - KHDN - TKTT": PROMPTS["BEE247:TKTT"],

    "chuyển tiền": PROMPTS["BEE247:CHUYEN_TIEN"],
    "Sản phẩm - KHCN - Chuyển tiền": PROMPTS["BEE247:CHUYEN_TIEN"],
    "Sản phẩm - KHDN - Chuyển tiền": PROMPTS["BEE247:CHUYEN_TIEN"],

    "tiền gửi và CCTG": PROMPTS["BEE247:TIEN_GUI_CCTG"],
    "Sản phẩm - KHCN - Tiền gửi & CCTG": PROMPTS["BEE247:TIEN_GUI_CCTG"],

    "tài trợ thương mại": PROMPTS["BEE247:TAI_TRO_THUONG_MAI"],
    "Sản phẩm - KHDN - Tài trợ thương mại": PROMPTS["BEE247:TAI_TRO_THUONG_MAI"],
    
    # Chương trình và dịch vụ
    "chương trình ưu đãi": PROMPTS["BEE247:UU_DAI"],
    "Sản phẩm - KHCN - Chương trình ưu đãi": PROMPTS["BEE247:UU_DAI"],
    "Sản phẩm - KHDN - Chương trình ưu đãi": PROMPTS["BEE247:UU_DAI"],

    "chuyên đề rủi ro": PROMPTS["BEE247:RUI_RO"],
    
    # Địa điểm
    "chi nhánh/phòng giao dịch": PROMPTS["BEE247:LOCATION"],
    "atm address": PROMPTS["BEE247:LOCATION"],
    "cdm/crm": PROMPTS["BEE247:LOCATION"],
    "smart bank": PROMPTS["BEE247:LOCATION"],
    "Mạng lưới": PROMPTS["BEE247:LOCATION"],
    
    # Khác
    "khác": PROMPTS["BEE247:OTHER"],
    "Sản phẩm - KHCN - Sản phẩm khác": PROMPTS["BEE247:OTHER"],

    # Standard
    "standard": PROMPTS["BEE247:TEMPLATE_TOPIC_ISSUES"]
}


def get_topic_prompt(topic: str) -> Optional[str]:
    if not topic:
        return None

    topic = topic.strip()
    
    # Thử tìm exact match trước
    prompt = TEMPLATE_MAPPING_PROMPTS.get(topic)
    
    # Nếu không có, thử lowercase
    if prompt is None:
        prompt = TEMPLATE_MAPPING_PROMPTS.get(topic.lower())
    
    return {
        "template": prompt,
    }






