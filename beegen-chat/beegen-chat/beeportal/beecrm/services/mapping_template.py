from typing import Dict, Tuple, Optional, Any
from beeportal.utils import PROMPTS


TEMPLATE_MAPPING_ASKBACK: Dict[Tuple[str, str], str] = {
    # Format: (L1, L2): "template_name"
    
    # Tín dụng templates
    ("Tín dụng", "Nhà đất"): PROMPTS["BEECRM:GPT_TINDUNG_NHADAT_ASKBACK"],
    ("Tín dụng", "Nhà dự án"): PROMPTS["BEECRM:GPT_TINDUNG_NHADUAN_ASKBACK"],
    ("Tín dụng", "Ô tô"): PROMPTS["BEECRM:GPT_TINDUNG_OTO_ASKBACK"],
    ("Tín dụng", "SXKD"): PROMPTS["BEECRM:GPT_TINDUNG_SXKD_ASKBACK"],
    ("Tín dụng", "TD có TSBĐ"): PROMPTS["BEECRM:GPT_TINDUNG_TSBD_ASKBACK"],
    
    # Huy động vốn templates
    ("Huy động vốn", "Có kỳ hạn"): PROMPTS["BEECRM:GPT_HUYDONGVON_COKYHAN_ASKBACK"],
    ("Huy động vốn", "Không kỳ hạn"): PROMPTS["BEECRM:GPT_HUYDONGVON_KHONGKYHAN_ASKBACK"],
    
    # CDs templates
    ("CDs", ""): PROMPTS["BEECRM:GPT_CDs_ASKBACK"],
    
    # Bancas templates
    ("Bancas", "Phi nhân thọ"): PROMPTS["BEECRM:GPT_BANCAS_PHINHANTHO_ASKBACK"],
    ("Bancas", "Nhân thọ"): PROMPTS["BEECRM:GPT_BANCAS_NHANTHO_ASKBACK"],
    
    # Kiều hối templates
    ("Kiều hối", "Chuyển tiền QT"): PROMPTS["BEECRM:GPT_KIEUHOI_CHUYENTIENQT_ASKBACK"],
    ("Kiều hối", "Ngoại tệ mặt"): PROMPTS["BEECRM:GPT_KIEUHOI_NGOAITEMAT_ASKBACK"],
    
    # Thẻ templates
    ("Thẻ", ""): PROMPTS["BEECRM:GPT_CARD_ASKBACK"],
    
    # SP Đầu tư templates
    ("SP Đầu tư", ""): PROMPTS["BEECRM:GPT_SANPHAMDAUTU_ASKBACK"],
    
}


TEMPLATE_MAPPING_RCM: Dict[Tuple[str, str], str] = {
    # Format: (L1, L2): "template_name"
    
    # Tín dụng templates
    ("Tín dụng", "Nhà đất"): PROMPTS["BEECRM:GPT_TINDUNG_NHADAT_RCM"],
    ("Tín dụng", "Nhà dự án"): PROMPTS["BEECRM:GPT_TINDUNG_NHADUAN_RCM"],
    ("Tín dụng", "Ô tô"): PROMPTS["BEECRM:GPT_TINDUNG_OTO_RCM"],
    ("Tín dụng", "SXKD"): PROMPTS["BEECRM:GPT_TINDUNG_SXKD_RCM"],
    ("Tín dụng", "TD có TSBĐ"): PROMPTS["BEECRM:GPT_TINDUNG_TSBD_RCM"],
    
    # Huy động vốn templates
    ("Huy động vốn", "Có kỳ hạn"): PROMPTS["BEECRM:GPT_HUYDONGVON_COKYHAN_RCM"],
    ("Huy động vốn", "Không kỳ hạn"): PROMPTS["BEECRM:GPT_HUYDONGVON_KHONGKYHAN_RCM"],
    
    # CDs templates
    ("CDs", ""): PROMPTS["BEECRM:GPT_CDs_RCM"],
    
    # Bancas templates
    ("Bancas", "Phi nhân thọ"): PROMPTS["BEECRM:GPT_BANCAS_PHINHANTHO_RCM"],
    ("Bancas", "Nhân thọ"): PROMPTS["BEECRM:GPT_BANCAS_NHANTHO_RCM"],
    
    # Kiều hối templates
    ("Kiều hối", "Chuyển tiền QT"): PROMPTS["BEECRM:GPT_KIEUHOI_CHUYENTIENQT_RCM"],
    ("Kiều hối", "Ngoại tệ mặt"): PROMPTS["BEECRM:GPT_KIEUHOI_NGOAITEMAT_RCM"],
    
    # Thẻ templates
    ("Thẻ", ""): PROMPTS["BEECRM:GPT_CARD_RCM"],
    
    # SP Đầu tư templates
    ("SP Đầu tư", ""): PROMPTS["BEECRM:GPT_SANPHAMDAUTU_RCM"],
    
}

DEFAULT_TEMPLATE = "Bạn vui lòng cung cấp thêm thông tin chi tiết về mong muốn của bạn để tôi có thể hỗ trợ tốt hơn."






