import re
from typing import Dict, List, Tuple, Optional, Union


class AbbreviationHandler:
    """
    Class xử lý từ viết tắt trong lĩnh vực tài chính ngân hàng
    """

    def __init__(self):
        self.abbreviations = abbreviations = {
            "TSBĐ": "Tài sản bảo đảm",
            "KHDN": "Khách hàng doanh nghiệp",
            "GPXD": "Giấy phép xây dựng",
            "GCN": "Giấy chứng nhận",
            "UBND": "Ủy ban nhân dân",
            "BPBĐ": "Biện pháp bảo đảm",
            "ĐVKD": "Đơn vị kinh doanh",
            "TMCP": "Thương mại cổ phần",
            "XHTD": "Xếp hạng tín dụng",
            "TCTD": "Tổ chức tín dụng",
            "BCTC": "Báo cáo tài chính",
            "HTK": "Hàng tồn kho",
            "HĐTC": "Hợp đồng thế chấp",
            "ĐKGDBĐ": "Đăng ký giao dịch bảo đảm",
            "GDBĐ": "Giao dịch bảo đảm",
            "CTXD": "Công trình xây dựng",
            "TS": "Tài sản",
            "Sở TN và MT": "Sở tài nguyên và môi trường",
            "KH": "Khách hàng",
            "GP": "Giấy phép",
            "PTĐ": "Phòng thẩm định",
            "BCTĐ": "Báo cáo thẩm định",
            "KHCN": "Khách hàng cá nhân",
            "TSĐB": "Tài sản đảm bảo",
            "BĐS": "Bất động sản",
            "QSDĐ": "Quyền sử dụng đất",
            "TSGLVĐ": "Tài sản gắn liền với đất",
            "GCNQSDĐ": "Giấy chứng nhận quyền sử dụng đất",
            "QTRR": "Quản trị rủi ro",
            "Cấp PD, TĐ": "Cấp phê duyệt, thẩm định",
            "CN": "Chi nhánh",
            "HĐ": "Hợp đồng",
            "PA": "Phương án",
            "TBPD": "Thông báo phê duyệt",
            "QTTD": "Quy trình tín dụng",
            "HMTD": "Hạn mức tín dụng",
            "GĐPD": "Giám đốc phê duyệt",
            "CĐT": "Chủ đầu tư",
            "BCĐX": "Báo cáo đề xuất",
            "MMTB": "Máy móc thiết bị",
            "QĐN": "Quyền đòi nợ",
            "NH": "Ngân hàng",
            "GĐ": "Giám đốc",
            "PGĐ": "Phó giám đốc",
            "LCNK": "LC nhập khẩu",
            "TB": "Thông báo",
            "HĐTG": "Hợp đồng tiền gửi",
            "STK": "Sổ tiết kiệm",
            "GTCG": "Giấy tờ có giá",
            "SHK": "Sổ hộ khẩu",
            "CMND": "Chứng minh nhân dân",
            "HĐTD": "Hợp đồng tín dụng",
            "HĐBĐ": "Hợp đồng bảo đảm",
            "VPĐKĐĐ": "Văn phòng đăng ký đất đai",
            "VPCC": "Văn phòng công chứng",
            "HM": "Hạn mức",
            "GĐCN": "Giám đốc chi nhánh",
            "UQ": "Ủy quyền",
            "PGD": "Phòng giao dịch",
            "GTTT": "Giấy tờ tùy thân",
            "CCCD": "Căn cước công dân",
            "CSBH": "Chính sách bán hàng",
            "HĐCV": "Hợp đồng cho vay",
            "HĐMB": "Hợp đồng mua bán",
            "CV": "Chuyên viên",
            "KS": "Kiểm soát",
            "KSV": "Kiểm soát viên",
            "Thư ký HĐTD": "Thư ký Hội đồng tín dụng",
            "Hội đồng TD": "Hội đồng tín dụng",
            "VKTD": "Văn kiện tín dụng",
            "HTLS": "Hỗ trợ lãi suất",
            "TH": "Trường hợp",
            "VKTS": "Văn kiện tài sản",
            "CVHT": "Chuyên viên hỗ trợ",
            "UNC": "Ủy nhiệm chi",
            "PNK": "Phiếu nhập kho",
            "PTGN": "Phương thức giải ngân",
            "VD": "Ví dụ",
            "ĐXGN": "Đề xuất giải ngân",
            "TKTT": "Tài khoản thanh toán",
            "KUNN": "Khế ước nhận nợ",
            "VTC": "Vốn tự có",
            "GĐDV": "Giám đốc dịch vụ",
            "GDV": "Giao dịch viên",
            "HTCN": "Hỗ trợ chi nhánh",
            "VBTT": "Văn bản thỏa thuận",
            "BP Thẩm định": "Bộ phận thẩm định",
            "TSTC": "Tài sản thế chấp",
            "TT HTTD": "Trung tâm Hỗ trợ tín dụng",
            "CV HTTD": "Chuyên viên Hỗ trợ tín dụng",
            "SXKD": "Sản xuất kinh doanh",
            "CBQL": "Cán bộ quản lý",
            "LS": "Lãi suất",
            "HĐBH": "Hợp đồng bảo hiểm",
            "BH": "Bảo hiểm",
            "GNT": "Giấy nộp tiền",
            "GN": "Giải ngân",
            "BLĐ": "Ban lãnh đạo",
            "BBBG": "Biên bản bàn giao",
            "TNTH": "Trả nợ trước hạn",
            "QTS": "Quyền tài sản",
            "TK": "Tài khoản",
            "HS": "Hồ sơ",
            "CBNV": "Cán bộ nhân viên",
            "HĐTV": "Hội đồng thành viên",
            "HĐQT": "Hội đồng quản trị",
            "VBNN": "Văn bản nhận nợ",
            "TTTM": "Tài trợ thương mại",
            "TPP": "Trưởng phó phòng",
            "XNCCTD": "Xác nhận cung cấp tín dụng",
            "SĐT": "Số điện thoại",
            "VBUQ": "Văn bản ủy quyền",
            "HTTD": "Hỗ trợ tín dụng",
            "KPT": "Khoản phải thu",
            "BTT": "Bao thanh toán",
            "BCT": "Bộ chứng từ",
            "CNTT": "Chấp nhận thanh toán",
            "NHĐL": "Ngân hàng đại lý",
            "NTH": "Người thụ hưởng",
            "P.DVTTTM": "Phòng dịch vụ Tài trợ thương mại",
            "TTQT": "Thanh toán quốc tế",
            "HKTT": "Hộ khẩu thường trú",
            "BCKS": "Báo cáo kiểm soát",
            "BLNH": "Bảo lãnh nhận hàng",
            "BUT": "Bên ủy thác",
            "ĐCTC": "Định chế tài chính",
            "NHPH": "Ngân hàng phát hành",
            "UQNH": "Ủy quyền nhận hàng",
            "UTPHLC": "Ủy thác phát hành LC"
        }
        # Chuẩn hóa từ điển
        self.normalized_dict = {k.strip().upper(): v for k, v in self.abbreviations.items()}
        # Tạo pattern để tìm kiếm từ viết tắt
        self.pattern = self._create_search_pattern()

    def _create_search_pattern(self) -> re.Pattern:
        """
        Tạo pattern tìm kiếm các từ viết tắt viết hoa và đứng riêng
        """
        sorted_abbrs = sorted(self.normalized_dict.keys(), key=len, reverse=True)
        pattern = '|'.join(map(re.escape, sorted_abbrs))
        # Thêm điều kiện để đảm bảo từ viết tắt đứng một mình
        # (?<!\w) kiểm tra không có ký tự chữ đứng trước
        # (?!\w) kiểm tra không có ký tự chữ đứng sau
        return re.compile(f'(?<!\w)({pattern})(?!\w)')

    def find_unique_abbreviations(self, text: str) -> Dict[str, str]:
        """
        Tìm tất cả các từ viết tắt duy nhất trong văn bản và trả về dictionary
        chứa từ viết tắt và giải nghĩa của nó

        Args:
            text (str): Văn bản cần tìm kiếm

        Returns:
            Dict[str, str]: Dictionary chứa các cặp từ viết tắt và giải nghĩa
        """
        # Sử dụng set để lưu các từ viết tắt duy nhất
        unique_abbrs: Set[str] = set()

        # Tìm tất cả các từ viết tắt trong văn bản
        for match in self.pattern.finditer(text):
            abbr = match.group()
            # Chỉ xử lý nếu từ viết tắt có trong từ điển
            if abbr in self.normalized_dict:
                unique_abbrs.add(abbr)

        # Tạo dictionary kết quả
        result = {abbr: self.normalized_dict[abbr] for abbr in unique_abbrs}
        return result

    def is_valid_abbreviation(self, text: str) -> bool:
        """
        Kiểm tra xem một chuỗi có phải là từ viết tắt hợp lệ hay không

        Args:
            text (str): Chuỗi cần kiểm tra

        Returns:
            bool: True nếu là từ viết tắt hợp lệ, False nếu không phải
        """
        # Kiểm tra chuỗi có viết hoa hoàn toàn
        is_uppercase = text.isupper()
        # Kiểm tra chuỗi có trong từ điển
        is_in_dict = text in self.normalized_dict
        return is_uppercase and is_in_dict