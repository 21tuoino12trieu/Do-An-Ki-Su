ASSET_HIERARCHY = {
    # 1. LIABILITY - KHOẢN NỢ
    "1": {
        "name": "Khoản nợ",
        "type": "LIABILITY",
        "invest_flag": "N",
        "children": {
            "11": {
                "name": "Thẻ tín dụng",
                "code": "Ccard",
                "detail": "Danh sách thẻ (hiển thị theo cấu trúc [Số thẻ – Loại Tiền tệ])",
                "invest_flag": "N"
            },
            "12": {
                "name": "Vay vốn",
                "code": "Loan",
                "detail": "Tổng hợp các khoản vay",
                "invest_flag": "N",
                "children": {
                    "121": {
                        "name": "Vay theo hợp đồng tín dụng",
                        "code": "Sdebt",
                        "detail": "Danh sách khế ước (hiển thị theo cấu trúc [Số hợp đồng vay – Loại Tiền tệ])",
                        "invest_flag": "N"
                    },
                    "122": {
                        "name": "Vay thấu chi",
                        "code": "Tdebt",
                        "detail": "Danh sách khoản vay (hiển thị theo cấu trúc [Số hợp đồng vay – Loại Tiền tệ])",
                        "invest_flag": "N"
                    },
                    "123": {
                        "name": "Vay margin",
                        "code": "Margin",
                        "detail": "Số tổng hợp",
                        "invest_flag": "Y"
                    },
                    "124": {
                        "name": "Vay ứng trước",
                        "code": "Prepaid",
                        "detail": "Số tổng hợp",
                        "invest_flag": "Y"
                    }
                }
            }
        }
    },

    # 2. ASSET - TÀI SẢN ĐẦU TƯ
    "2": {
        "name": "Tài sản đầu tư",
        "type": "ASSET",
        "invest_flag": "Y",
        "children": {
            "21": {
                "name": "Huy động vốn",
                "code": "Deposit",
                "detail": "Các loại tài khoản và tiền gửi",
                "invest_flag": "N",
                "children": {
                    "211": {
                        "name": "Tài khoản thanh toán",
                        "code": "Current",
                        "detail": "Danh sách tài khoản (hiển thị theo cấu trúc [Số tài khoản – Loại Tiền tệ])",
                        "invest_flag": "N"
                    },
                    "212": {
                        "name": "Tài khoản thanh toán chứng khoán",
                        "code": "Seurrent",
                        "detail": "Danh sách tài khoản",
                        "invest_flag": "Y"
                    },
                    "213": {
                        "name": "Tiền gửi tiết kiệm/Có kỳ hạn",
                        "code": "Saving",
                        "detail": "Danh sách tài khoản (hiển thị theo cấu trúc [Số tài khoản – Loại Tiền tệ])",
                        "invest_flag": "N"
                    },
                    "214": {
                        "name": "MBS vay Khách hàng",
                        "code": "Sesaving",
                        "detail": "Số tổng hợp",
                        "invest_flag": "Y"
                    },
                    "215": {
                        "name": "Chứng chỉ tiền gửi",
                        "code": "CDS",
                        "detail": "Danh sách chứng chỉ tiền gửi",
                        "invest_flag": "N"
                    }
                }
            },
            "22": {
                "name": "Trái phiếu",
                "code": "Bond",
                "detail": "Danh sách trái phiếu",
                "invest_flag": "Y"
            },
            "23": {
                "name": "Cổ phiếu",
                "code": "Stock",
                "detail": "Danh sách cổ phiếu",
                "invest_flag": "Y"
            },
            "24": {
                "name": "Chứng chỉ quỹ",
                "code": "Fund",
                "detail": "Danh sách chứng chỉ quỹ",
                "invest_flag": "Y"
            },
            "25": {
                "name": "Chứng quyền",
                "code": "CW",
                "detail": "Danh sách chứng quyền",
                "invest_flag": "Y"
            },
            "26": {
                "name": "Phái sinh",
                "code": "Future",
                "detail": "Hợp đồng tương lai",
                "invest_flag": "Y",
                "children": {
                    "261": {
                        "name": "Hợp đồng tương lai chỉ số cổ phiếu",
                        "code": "IndexFuture",
                        "detail": "Danh sách mã phái sinh",
                        "invest_flag": "Y"
                    },
                    "262": {
                        "name": "Hợp đồng tương lai trái phiếu chính phủ",
                        "code": "BondFuture",
                        "detail": "Danh sách mã phái sinh",
                        "invest_flag": "Y"
                    }
                }
            },
            "27": {
                "name": "Ủy thác đầu tư",
                "code": "InvestTrust",
                "detail": "Sản phẩm ủy thác đầu tư",
                "invest_flag": "Y"
            },
            "28": {
                "name": "Vàng",
                "code": "Gold",
                "detail": "Đầu tư vàng",
                "invest_flag": "Y"
            },
            "29": {
                "name": "Bảo hiểm",
                "code": "Insurance",
                "detail": "Danh sách hợp đồng bảo hiểm",
                "invest_flag": "Y"
            }
        }
    },

    # 3. COLLATERAL - TÀI SẢN ĐẢM BẢO
    "3": {
        "name": "Tài sản đảm bảo",
        "type": "COLLATERAL",
        "invest_flag": "N",
        "children": {
            "31": {
                "name": "Bất động sản",
                "code": "Land",
                "detail": "Không có chi tiết",
                "invest_flag": "N"
            },
            "32": {
                "name": "Phương tiện vận tải",
                "code": "Transport",
                "detail": "Không có chi tiết",
                "invest_flag": "N"
            }
        }
    }
}