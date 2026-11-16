"""
Total Revenue API Service - Xử lý API calls cho domain Total Revenue
Gọi API transaction-integration với kind="asset" và API danh sách sổ tiết kiệm
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import aiohttp

from beechat_khcn.models.total_revenue_model import TotalRevenueAttributes, TotalRevenueIntent
from beechat_khcn.utils.Assest_hierachy import ASSET_HIERARCHY
from beegenerate.loggings import LOGGER

# Constants
DEFAULT_CURRENCY = "VND"
DEFAULT_STRING = "N/A"
SUCCESS_CODE = "0000"
DEFAULT_TIMEOUT = 90
DEBT_ASSET_PREFIXES = ("3", "31", "32", "33")
DEBT_KEYWORDS = ["KHOẢN NỢ", "DƯ NỢ", "VAY", "THẺ TÍN DỤNG", "TÍN DỤNG", "DEBT", "LOAN", "CREDIT", "OVERDRAFT"]


class AssetTypeHierarchy:
    """Cây phân cấp tài sản theo cấu trúc được định nghĩa"""

    @classmethod
    def get_asset_info(cls, asset_type: str) -> Dict[str, Any]:
        """Lấy thông tin chi tiết của asset dựa trên asset_type"""
        if not asset_type:
            return {
                "name": "Không xác định", "code": "", "type": "UNKNOWN", "type_name": "Không xác định",
                "invest_flag": "N", "level": 1, "parent_info": {"has_parent": False}, "path": "Không xác định"
            }

        return cls._find_asset_in_hierarchy(asset_type, ASSET_HIERARCHY) or {
            "name": f"Loại tài sản {asset_type}", "code": "", "type": "UNKNOWN", "type_name": "Không xác định",
            "invest_flag": "N", "level": 1, "parent_info": {"has_parent": False}, "path": f"Loại tài sản {asset_type}"
        }

    @classmethod
    def _find_asset_in_hierarchy(cls, asset_type: str, hierarchy: Dict, parent_path: List = None) -> Optional[Dict[str, Any]]:
        """Tìm asset trong cây phân cấp một cách đệ quy"""
        parent_path = parent_path or []

        for key, value in hierarchy.items():
            current_path = parent_path + [key]
            if key == asset_type:
                return cls._build_asset_info(value, current_path, hierarchy)
            if "children" in value and (result := cls._find_asset_in_hierarchy(asset_type, value["children"], current_path)):
                return result
        return None

    @classmethod
    def _build_asset_info(cls, asset_data: Dict, path: List, full_hierarchy: Dict) -> Dict[str, Any]:
        """Xây dựng thông tin asset hoàn chỉnh"""
        root_info = full_hierarchy.get(path[0], {})
        has_parent = len(path) > 1

        parent_info = {"has_parent": has_parent}
        if has_parent:
            parent_data = cls._get_parent_data(path[:-1], full_hierarchy)
            parent_info.update({
                "parent_code": path[-2],
                "parent_name": parent_data.get("name", "Không xác định"),
                "parent_path": " > ".join([full_hierarchy.get(p, {}).get("name", p) for p in path[:-1]])
            })

        return {
            "name": asset_data.get("name", "Không xác định"),
            "code": asset_data.get("code", ""),
            "type": root_info.get("type", "UNKNOWN"),
            "type_name": root_info.get("name", "Không xác định"),
            "invest_flag": asset_data.get("invest_flag", "N"),
            "level": len(path),
            "parent_info": parent_info,
            "path": " > ".join([full_hierarchy.get(p, {}).get("name", p) for p in path])
        }

    @classmethod
    def _get_parent_data(cls, path: List, hierarchy: Dict) -> Dict:
        """Tìm dữ liệu của parent theo path"""
        current = hierarchy
        for key in path:
            current = current.get(key) or current.get("children", {}).get(key, {})
        return current


class TotalRevenueApiService:
    """Service xử lý API calls cho Total Revenue domain"""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service
        self.api_url = "http://beegen-transaction-history.tanzu-dev.mbbank.com.vn/api/app/transaction-integration"
        self.timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        LOGGER.info("TotalRevenueApiService initialized")

    async def get_data_for_intent(self, intent: TotalRevenueIntent, attributes: TotalRevenueAttributes) -> Dict[str, Any]:
        """Lấy dữ liệu cần thiết cho từng intent và format sẵn"""
        customer_code = attributes.customer_code
        business_domain = attributes.business_domain or "MBB"

        LOGGER.info(f"Processing intent: {intent.value} for customer: {customer_code}")

        try:
            if intent in [TotalRevenueIntent.GET_TOTAL_ASSETS, TotalRevenueIntent.GET_NET_WORTH,
                          TotalRevenueIntent.GET_TOTAL_DEBT, TotalRevenueIntent.ASSET_HEALTH_CHECK]:
                return await self._handle_asset_intents(intent, customer_code, business_domain)

            if intent == TotalRevenueIntent.GET_INCOME_PROJECTION:
                return await self._handle_income_projection_intent(customer_code, business_domain)

            if intent == TotalRevenueIntent.TRIGGER_ASSET_SUMMARY_NOTIFICATION:
                return self._handle_notification_intent(intent, customer_code)

            if intent == TotalRevenueIntent.OUT_OF_SCOPE:
                return self._handle_out_of_scope_intent(intent)

        except Exception as e:
            LOGGER.error(f"API_EXCEPTION: {str(e)} for intent {intent.value}")
            return self._create_error_result(intent, customer_code, f"Lỗi xử lý dữ liệu: {str(e)}")

    def _handle_out_of_scope_intent(self, intent: TotalRevenueIntent) -> Dict[str, Any]:
        """Xử lý intent out of scope"""
        return {
            "intent": intent.value,
            "success": True,
            "formatted_data": ("Cảm ơn bạn đã quan tâm đến các tính năng tài chính của chúng tôi! "
                              "Tính năng bạn yêu cầu hiện đang được phát triển và sẽ sớm được cung cấp. "
                              "Trong thời gian chờ đợi, bạn có thể sử dụng các tính năng hiện có như: "
                              "xem tổng tài sản, tài sản ròng, dự báo thu nhập từ tiết kiệm. "
                              "Vui lòng liên hệ hotline 1900 588 822 để được hỗ trợ thêm.")
        }

    async def _handle_asset_intents(self, intent: TotalRevenueIntent, customer_code: str, business_domain: str) -> Dict[str, Any]:
        """Xử lý các intent liên quan đến tài sản"""
        asset_result = await self.fetch_total_assets(customer_code, business_domain)

        if asset_result.get("soaErrorCode") != SUCCESS_CODE:
            error_msg = asset_result.get("soaErrorDesc", "Không thể lấy dữ liệu tài sản")
            LOGGER.error(f"ASSET_API_FAIL: {error_msg}")
            return self._create_error_result(intent, customer_code, error_msg)

        all_customer_assets = asset_result.get("data", {}).get("customerAsset", [])
        if not all_customer_assets:
            return self._create_error_result(intent, customer_code, "Không có dữ liệu tài sản")

        # Single-pass filtering
        non_debt_assets, debt_assets = [], []
        for asset in all_customer_assets:
            (debt_assets if self._is_debt_asset(asset) else non_debt_assets).append(asset)

        filtered_assets = non_debt_assets if intent == TotalRevenueIntent.GET_TOTAL_ASSETS else all_customer_assets
        processed_assets = [self._format_customer_asset(asset) for asset in filtered_assets]

        formatted_data = (self._format_asset_data_with_separated_groups(processed_assets, non_debt_assets, debt_assets, customer_code)
                         if intent in [TotalRevenueIntent.GET_NET_WORTH, TotalRevenueIntent.ASSET_HEALTH_CHECK, TotalRevenueIntent.GET_TOTAL_DEBT]
                         else self._format_asset_data_for_intent(processed_assets, customer_code, intent))

        return {
            "intent": intent.value, "success": True, "customer_code": customer_code, "business_domain": business_domain,
            "total_assets_count": len(all_customer_assets), "filtered_assets_count": len(filtered_assets),
            "non_debt_assets_count": len(non_debt_assets), "debt_assets_count": len(debt_assets),
            "formatted_data": formatted_data
        }

    async def _handle_income_projection_intent(self, customer_code: str, business_domain: str) -> Dict[str, Any]:
        """Xử lý intent GET_INCOME_PROJECTION"""
        savings_result = await self.fetch_savings_with_transaction_integration(customer_code)

        if savings_result.get("status") != 200:
            error_msg = savings_result.get("error", "Không thể lấy dữ liệu tiết kiệm")
            LOGGER.error(f"SAVINGS_API_FAIL: {error_msg}")
            return self._create_error_result(TotalRevenueIntent.GET_INCOME_PROJECTION, customer_code, error_msg)

        LOGGER.info(f"SAVINGS_API_SUCCESS: Data processed for customer {customer_code}")
        return {
            "intent": TotalRevenueIntent.GET_INCOME_PROJECTION.value,
            "customer_code": customer_code,
            "success": True,
            "formatted_data": self._format_savings_data_for_intent(savings_result, customer_code)
        }

    def _handle_notification_intent(self, intent: TotalRevenueIntent, customer_code: str) -> Dict[str, Any]:
        """Xử lý intent thông báo tự động"""
        return {
            "intent": intent.value, "customer_code": customer_code, "success": True,
            "formatted_data": ("Hệ thống hiện chưa hỗ trợ tính năng thông báo định kỳ về tài sản. "
                              "Tính năng này sẽ được cập nhật trong phiên bản tiếp theo."),
            "notification_available": False
        }

    def _format_asset_data_for_intent(self, asset_items: List[Dict], customer_code: str, intent: TotalRevenueIntent) -> str:
        """Format asset data theo intent cụ thể"""
        filter_info_map = {
            TotalRevenueIntent.GET_TOTAL_ASSETS: "\n📝 LƯU Ý: Danh sách chỉ bao gồm tài sản (không bao gồm các khoản nợ)\n",
            TotalRevenueIntent.GET_TOTAL_DEBT: "\n📝 LƯU Ý: Danh sách chỉ bao gồm các khoản nợ\n"
        }

        if intent in [TotalRevenueIntent.GET_NET_WORTH, TotalRevenueIntent.ASSET_HEALTH_CHECK]:
            filter_info = "\n📝 LƯU Ý: Danh sách bao gồm toàn bộ tài sản và nợ\n"
        else:
            filter_info = filter_info_map.get(intent, "")

        formatted_data = self._format_raw_asset_data(asset_items, customer_code)
        if filter_info:
            lines = formatted_data.split('\n')
            if len(lines) > 3:
                lines.insert(3, filter_info)
                formatted_data = '\n'.join(lines)

        return formatted_data

    def _format_raw_asset_data(self, asset_items: List[Dict], customer_code: str) -> str:
        """Process raw asset items và tạo formatted summary"""
        totals = {"balance_vnd": 0, "investment": 0, "non_investment": 0}

        asset_details = []
        for i, asset in enumerate(asset_items, 1):
            if not asset:
                continue

            display_info = asset.get('displayInfo', {}) or {}
            invest_flag = asset.get('investFlag', 'N')
            balance_lcy = self._safe_float(asset.get('balanceLCY'))
            profit = self._safe_float(asset.get('profit'))

            # Format asset text
            asset_text = f"""
    TÀI SẢN {i}: {display_info.get('assetName', 'Không xác định')}
    🏢 THÔNG TIN CÔNG TY & KHÁCH HÀNG:
       - Mã công ty thành viên: {asset.get('businessDomain', 'Không xác định')}
       - Mã khách hàng: {asset.get('customerCode', 'Không xác định')}
    🏷️ THÔNG TIN LOẠI TÀI SẢN:
       - Mã loại tài sản: {asset.get('assetType', 'Không có')}
       - Tên tắt loại tài sản: {asset.get('assetTypeStName', 'Không có')}
    💼 THÔNG TIN ĐẦU TƯ:
       - Cờ đầu tư: {invest_flag} ({'Tài sản đầu tư' if invest_flag == 'Y' else 'Tài sản không đầu tư'})
       - Loại nắm giữ: {asset.get('holdingType', 'Không xác định')}
    📊 THÔNG TIN SỐ LƯỢNG & GIÁ TRỊ:
       - Số lượng nắm giữ: {self._safe_float(asset.get('holdingAmount')):,.2f}
       - Giá trên 1 đơn vị: {self._safe_float(asset.get('price')):,.2f} {asset.get('currency', DEFAULT_CURRENCY)}
       - Tổng giá trị (ngoại tệ): {self._safe_float(asset.get('balanceFCY')):,.2f} {asset.get('currency', DEFAULT_CURRENCY)}
       - Tổng giá trị (VND): {balance_lcy:,.0f} {DEFAULT_CURRENCY}
    💱 THÔNG TIN TIỀN TỆ:
       - Loại tiền tệ: {asset.get('currency', DEFAULT_CURRENCY)}
       - Tỷ giá hối đoái: {asset.get('exchangeRate', 'Không có')}
    📈 THÔNG TIN LỢI NHUẬN:
       - Lợi nhuận: {profit:,.0f} {DEFAULT_CURRENCY}
    """

            # Add detailed info if available
            asset_info_parsed = display_info.get('assetInfoParsed', {})
            detail_info = asset_info_parsed.get('display_info') or asset.get('assetInfo', '')
            if detail_info:
                asset_text += f"\n🔍 THÔNG TIN CHI TIẾT: {detail_info}"

            asset_details.append(asset_text)

            # Update totals
            totals["balance_vnd"] += balance_lcy
            if invest_flag == 'Y':
                totals["investment"] += balance_lcy
            else:
                totals["non_investment"] += balance_lcy

        # Calculate ratios
        investment_ratio = (totals["investment"] / totals["balance_vnd"] * 100) if totals["balance_vnd"] > 0 else 0
        non_investment_ratio = (totals["non_investment"] / totals["balance_vnd"] * 100) if totals["balance_vnd"] > 0 else 0

        return f"""=== THÔNG TIN DANH MỤC TÀI SẢN KHÁCH HÀNG ===
    Mã khách hàng: {customer_code or 'Không xác định'}
    Ngày cập nhật dữ liệu: {datetime.now().strftime('%d/%m/%Y')}
    Tổng số khoản tài sản: {len(asset_items)} khoản

    === CHI TIẾT TỪNG KHOẢN TÀI SẢN ===
    {''.join(asset_details)}

    📊 TỔNG KẾT DANH MỤC TÀI SẢN
    💰 TỔNG GIÁ TRỊ:
       - Tổng giá trị tất cả tài sản: {totals["balance_vnd"]:,.0f} {DEFAULT_CURRENCY}
       - Tổng tài sản đầu tư: {totals["investment"]:,.0f} {DEFAULT_CURRENCY}  
       - Tổng tài sản không đầu tư: {totals["non_investment"]:,.0f} {DEFAULT_CURRENCY}
    📈 TỶ TRỌNG:
       - Tỷ trọng tài sản đầu tư: {investment_ratio:.1f}%
       - Tỷ trọng tài sản không đầu tư: {non_investment_ratio:.1f}%
    📊 THỐNG KÊ:
       - Tổng số khoản: {len(asset_items)} khoản
       - Số khoản đầu tư: {sum(1 for asset in asset_items if asset and asset.get('investFlag') == 'Y')} khoản
       - Số khoản không đầu tư: {sum(1 for asset in asset_items if asset and asset.get('investFlag') != 'Y')} khoản
    """

    def _format_savings_data_for_intent(self, savings_result: Dict, customer_code: str) -> str:
        """Format savings data cho income projection intent"""
        savings_list = savings_result.get("data", [])
        if not savings_list:
            return f"Không có dữ liệu sổ tiết kiệm cho khách hàng {customer_code}"

        totals = {
            "principal": 0.0, "current_balance": 0.0, "interest_today": 0.0,
            "interest_maturity": 0.0, "blocked": 0.0
        }

        savings_details = []
        for i, saving in enumerate(savings_list, 1):
            try:
                # Extract basic info
                basic_info = {
                    'account_number': self._safe_string(saving.get('accountNumber')),
                    'customer_name': self._safe_string(saving.get('accountName')),
                    'customer_id': self._safe_string(saving.get('customerId')),
                    'account_type': self._safe_string(saving.get('accountType')),
                    'currency': self._safe_string(saving.get('accountCurrency'), DEFAULT_CURRENCY),
                    'channel': self._safe_string(saving.get('channel'))
                }

                # Extract product info
                product_info = saving.get('productInfo', [])
                product_data = {
                    'code': self._extract_product_info(product_info, 'Category', 'id'),
                    'name': self._extract_product_info(product_info, 'Category', 'name'),
                    'sub_code': self._extract_product_info(product_info, 'SubProduct', 'id'),
                    'sub_name': self._extract_product_info(product_info, 'SubProduct', 'name')
                }

                # Extract branch info
                branch_info = saving.get('branchInfo', [])
                branch_data = {}
                if branch_info:
                    branch_data = {
                        'code': self._safe_string(branch_info[0].get('code')),
                        'name': self._safe_string(branch_info[0].get('name'))
                    }

                # Extract financial info
                balance_info = saving.get('balance', {})
                interest_info = saving.get('interestInfo', {})
                tenor_info = saving.get('tenor', {})

                financial_data = {
                    'principal': self._safe_float(saving.get('principalAmount')),
                    'current_balance': self._safe_float(balance_info.get('current')),
                    'available_balance': self._safe_float(balance_info.get('available')),
                    'blocked': self._safe_float(balance_info.get('blocked')),
                    'interest_rate': self._safe_float(interest_info.get('interestRate')),
                    'interest_today': self._safe_float(interest_info.get('amtAccr')),
                    'interest_maturity': self._safe_float(saving.get('amtAccrMat')),
                    'term_value': self._safe_string(tenor_info.get('value')),
                    'term_unit': 'tháng' if tenor_info.get('unit') == 'M' else 'ngày' if tenor_info.get('unit') == 'D' else self._safe_string(tenor_info.get('unit', '')),
                    'open_date': self._format_date(self._safe_string(saving.get('openDate'), '')),
                    'maturity_date': self._format_date(self._safe_string(saving.get('maturityDate'), ''))
                }

                # Format saving text
                saving_text = f"""
Sổ tiết kiệm {i}:
=== THÔNG TIN CƠ BẢN ===
- Số sổ tiết kiệm: {basic_info['account_number']}
- Tên khách hàng: {basic_info['customer_name']}
- Mã khách hàng: {basic_info['customer_id']}
- Loại tài khoản: {basic_info['account_type']}
- Loại tiền: {basic_info['currency']}
- Kênh giao dịch: {basic_info['channel']}

=== THÔNG TIN SẢN PHẨM ===
- Mã sản phẩm: {product_data['code']}
- Tên sản phẩm: {product_data['name']}
- Mã sản phẩm phụ: {product_data['sub_code']}
- Tên sản phẩm phụ: {product_data['sub_name']}

=== THÔNG TIN CHI NHÁNH ===
- Mã chi nhánh: {branch_data.get('code', DEFAULT_STRING)}
- Tên chi nhánh: {branch_data.get('name', DEFAULT_STRING)}

=== THÔNG TIN TÀI CHÍNH ===
- Số tiền gốc: {financial_data['principal']:,.0f} {DEFAULT_CURRENCY}
- Số dư hiện tại: {financial_data['current_balance']:,.0f} {DEFAULT_CURRENCY}
- Số dư khả dụng: {financial_data['available_balance']:,.0f} {DEFAULT_CURRENCY}
- Số tiền bị phong tỏa: {financial_data['blocked']:,.0f} {DEFAULT_CURRENCY}

=== THÔNG TIN LÃI SUẤT ===
- Lãi suất: {financial_data['interest_rate']}%/năm
- Lãi tích lũy hiện tại: {financial_data['interest_today']:,.0f} {DEFAULT_CURRENCY}
- Lãi dự kiến đến đáo hạn: {financial_data['interest_maturity']:,.0f} {DEFAULT_CURRENCY}

=== THÔNG TIN KỲ HẠN ===
- Kỳ hạn: {financial_data['term_value']} {financial_data['term_unit']}
- Ngày mở sổ: {financial_data['open_date']}
- Ngày đáo hạn: {financial_data['maturity_date']}
"""

                savings_details.append(saving_text)

                # Update totals
                for key in ['principal', 'current_balance', 'interest_today', 'interest_maturity', 'blocked']:
                    totals[key] += financial_data[key] if key in financial_data else 0

            except Exception as e:
                LOGGER.error(f"Error parsing savings item {i}: {str(e)}")
                savings_details.append(f"\n\nSổ tiết kiệm {i}: Lỗi xử lý dữ liệu - {str(e)}\n")

        remaining_income = totals['interest_maturity'] - totals['interest_today']

        return f"""=== THÔNG TIN SỔ TIẾT KIỆM VÀ DỰ KIẾN THU NHẬP ===
Mã khách hàng: {customer_code}
Ngày cập nhật: {datetime.now().strftime('%d/%m/%Y')}
Tổng số sổ: {len(savings_list)} sổ

CHI TIẾT CÁC SỔ TIẾT KIỆM:{''.join(savings_details)}

=== TỔNG KẾT DỰ KIẾN THU NHẬP ===
Tổng số tiền gốc: {totals['principal']:,.0f} {DEFAULT_CURRENCY}
Tổng số dư hiện tại: {totals['current_balance']:,.0f} {DEFAULT_CURRENCY}
Tổng lãi tích lũy hiện tại: {totals['interest_today']:,.0f} {DEFAULT_CURRENCY}
Tổng lãi dự kiến đến đáo hạn: {totals['interest_maturity']:,.0f} {DEFAULT_CURRENCY}
Tổng số tiền bị phong tỏa: {totals['blocked']:,.0f} {DEFAULT_CURRENCY}

=== PHÂN TÍCH THU NHẬP ===
Thu nhập hiện tại từ lãi: {totals['interest_today']:,.0f} {DEFAULT_CURRENCY}
Thu nhập dự kiến khi đáo hạn: {totals['interest_maturity']:,.0f} {DEFAULT_CURRENCY}
Thu nhập còn lại đến đáo hạn: {remaining_income:,.0f} {DEFAULT_CURRENCY}
"""

    def _format_asset_data_with_separated_groups(self, all_processed_assets: List[Dict], non_debt_assets: List[Dict],
                                                 debt_assets: List[Dict], customer_code: str) -> str:
        """Format asset data với 2 nhóm tách biệt: tài sản và nợ"""
        processed_non_debt = [self._format_customer_asset(asset) for asset in non_debt_assets]
        processed_debt = [self._format_customer_asset(asset) for asset in debt_assets]

        total_non_debt = sum(self._safe_float(asset.get('balanceLCY', 0)) for asset in processed_non_debt)
        total_debt = sum(self._safe_float(asset.get('balanceLCY', 0)) for asset in processed_debt)

        # Format assets
        non_debt_text = ''.join(self._format_display_info_to_detailed_view(asset, i, "TÀI SẢN")
                               for i, asset in enumerate(processed_non_debt, 1)) if processed_non_debt else "\nKhông có tài sản nào trong nhóm này\n"
        debt_text = ''.join(self._format_display_info_to_detailed_view(asset, i, "KHOẢN NỢ")
                           for i, asset in enumerate(processed_debt, 1)) if processed_debt else "\nKhông có khoản nợ nào.\n"

        return f"""
    === THÔNG TIN TỔNG QUAN TÀI SẢN KHÁCH HÀNG ===
    Mã khách hàng: {customer_code}
    Ngày cập nhật dữ liệu: {datetime.now().strftime('%d/%m/%Y')}

    TỔNG QUAN:
    - Tổng số khoản tài sản: {len(non_debt_assets)} khoản
    - Tổng số khoản nợ: {len(debt_assets)} khoản
    - Tổng cộng: {len(all_processed_assets)} khoản

    NHÓM 1: DANH SÁCH TÀI SẢN (KHÔNG BAO GỒM NỢ)
    {non_debt_text}
    
    NHÓM 2: DANH SÁCH KHOẢN NỢ
    {debt_text}
    
    📈 TỔNG KẾT
    💰 Tổng giá trị tài sản: {total_non_debt:,.0f} {DEFAULT_CURRENCY}
    💳 Tổng dư nợ: {total_debt:,.0f} {DEFAULT_CURRENCY}
    🏆 Tài sản ròng: {(total_non_debt - total_debt):,.0f} {DEFAULT_CURRENCY}
"""

    def _format_display_info_to_detailed_view(self, asset: Dict, index: int, asset_type_label: str) -> str:
        """Convert từ displayInfo đã được format sẵn thành detailed view"""
        display_info = asset.get('displayInfo', {})

        holding_amount = display_info.get('holdingAmount', 0)
        price = display_info.get('price', 0)
        balance_fcy = display_info.get('balanceFCY', 0)
        currency = display_info.get('currency', DEFAULT_CURRENCY)
        exchange_rate = display_info.get('exchangeRate', '')

        # Format holdings and price info
        holdings_text = (f"\n       - Số lượng nắm giữ: {holding_amount:,.2f}" if holding_amount
                        else "\n       - Số lượng nắm giữ: Không xác định")

        price_text = (f"\n       - Giá trên 1 đơn vị: {price:,.2f} {DEFAULT_CURRENCY}" if price
                     else "\n       - Giá trên 1 đơn vị: Không xác định")

        fcy_text = (f"\n       - Tổng giá trị (ngoại tệ): {balance_fcy:,.2f} {currency}"
                   if balance_fcy and currency != DEFAULT_CURRENCY else "")

        exchange_text = ""
        if exchange_rate:
            try:
                rate_num = float(exchange_rate)
                exchange_text = f"\n       - Tỷ giá hối đoái: {rate_num:,.4f}"
            except (ValueError, TypeError):
                exchange_text = "\n       - Tỷ giá hối đoái: Không có"

        # Get detailed info
        asset_info_parsed = display_info.get('assetInfoParsed', {})
        detail_info = asset_info_parsed.get('display_info', 'Không có thông tin')

        return f"""
    🏅 {asset_type_label} {index}: {display_info.get('assetName', 'Không xác định')}
    🏢 THÔNG TIN CÔNG TY & KHÁCH HÀNG:
    - Mã công ty thành viên: {display_info.get('businessDomain', 'MBS')}
    - Mã khách hàng: {display_info.get('customerCode', '')}

    🛡️ THÔNG TIN LOẠI TÀI SẢN:
    - Mã loại tài sản: {display_info.get('assetCode', '')}
    - Tên tắt loại tài sản: {display_info.get('assetTypeStName', 'Unknown')}
    - Cấp độ: {display_info.get('level', 1)}

    💼 THÔNG TIN ĐẦU TƯ:
    - Cờ đầu tư: {asset.get('investFlag', 'N')} ({display_info.get('investFlagDisplay', 'Tài sản không đầu tư')})
    - Loại nắm giữ: {display_info.get('holdingType', 'None')}

    📊 THÔNG TIN SỐ LƯỢNG & GIÁ TRỊ:{holdings_text}{price_text}{fcy_text}
       - Tổng giá trị (VND): {display_info.get('balanceVND', '0 VND')}

    💱 THÔNG TIN TIỀN TỆ:
    - Loại tiền tệ: {currency}{exchange_text}

    📈 THÔNG TIN LỢI NHUẬN:
    - Lợi nhuận: {display_info.get('profitDisplay', '0 VND')}

    ℹ️ THÔNG TIN CHI TIẾT: {detail_info}
    """

    def _create_error_result(self, intent: TotalRevenueIntent, customer_code: str, error_message: str) -> Dict[str, Any]:
        """Tạo kết quả lỗi chuẩn"""
        return {
            "intent": intent.value,
            "customer_code": customer_code,
            "success": False,
            "error": error_message,
            "formatted_data": f"Xin lỗi, đã xảy ra lỗi: {error_message}. Vui lòng thử lại sau hoặc liên hệ hỗ trợ."
        }

    async def fetch_total_assets(self, customer_code: str, business_domain: str) -> Dict[str, Any]:
        """Gọi API tổng tài sản"""
        if not customer_code or not customer_code.strip():
            LOGGER.error("Empty customer code provided")
            return {"soaErrorCode": "1001", "soaErrorDesc": "Mã khách hàng không được để trống", "data": {}}

        try:
            request_payload = {"kind": "asset", "customer_code": customer_code.strip(), "business_domain": business_domain}
            LOGGER.info(f"🔄 Calling asset API: {self.api_url}")

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(self.api_url, json=request_payload,
                                      headers={'Content-Type': 'application/json'}) as response:
                    LOGGER.info(f"📥 Asset API response status: {response.status}")

                    if response.status != 200:
                        LOGGER.error(f"Asset API HTTP error: {response.status}")
                        return {"soaErrorCode": f"HTTP_{response.status}",
                               "soaErrorDesc": f"API không phản hồi (HTTP {response.status})", "data": {}}

                    return self._process_asset_response(await response.json())

        except asyncio.TimeoutError:
            LOGGER.error("Asset API timeout")
            return {"soaErrorCode": "TIMEOUT", "soaErrorDesc": "Hệ thống đang quá tải, vui lòng thử lại sau", "data": {}}
        except Exception as e:
            LOGGER.error(f"Asset API error: {str(e)}")
            return {"soaErrorCode": "SYSTEM_ERROR", "soaErrorDesc": f"Lỗi hệ thống: {str(e)}", "data": {}}

    async def fetch_savings_with_transaction_integration(self, customer_code: str) -> Dict[str, Any]:
        """Gọi API transaction-integration với kind=saving_acc"""
        if not customer_code or not customer_code.strip():
            LOGGER.error("Empty customer code for savings API")
            return {"status": 400, "error": "Mã khách hàng không được để trống"}

        try:
            request_payload = {"kind": "saving_acc", "customerId": customer_code.strip()}

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(self.api_url, json=request_payload,
                                      headers={'Content-Type': 'application/json'}) as response:
                    LOGGER.info(f"📥 Savings API response status: {response.status}")

                    if response.status != 200:
                        LOGGER.error(f"Savings API HTTP error: {response.status}")
                        return {"status": response.status, "error": f"API không phản hồi (HTTP {response.status})"}

                    raw_data = await response.json()
                    return {"status": raw_data.get("status", 500), "error": raw_data.get("error", "Lỗi không xác định"),
                           "path": raw_data.get("path", ""), "clientMessageId": raw_data.get("clientMessageId", ""),
                           "data": raw_data.get("data", [])}

        except asyncio.TimeoutError:
            LOGGER.error("Savings API timeout")
            return {"status": 408, "error": "Hệ thống đang quá tải, vui lòng thử lại sau"}
        except Exception as e:
            LOGGER.error(f"Savings API error: {str(e)}")
            return {"status": 500, "error": f"Lỗi hệ thống: {str(e)}"}

    def _format_customer_asset(self, asset_item: Dict) -> Dict[str, Any]:
        """Format một item tài sản theo cấu trúc customerAsset"""
        hierarchy_info = AssetTypeHierarchy.get_asset_info(asset_item.get("assetType", ""))
        asset_info_parsed = self._parse_asset_info(asset_item.get("assetInfo", ""),
                                                  asset_item.get("assetType", ""), hierarchy_info)

        balance_lcy = self._safe_float(asset_item.get("balanceLCY"))
        profit = self._safe_float(asset_item.get("profit"))

        display_info = {
            'businessDomain': asset_item.get("businessDomain", ""),
            'customerCode': asset_item.get("customerCode", ""),
            'assetName': hierarchy_info["name"],
            'assetCode': asset_item.get("assetType", ""),
            'assetTypeStName': asset_item.get("assetTypeStName", ""),
            'level': asset_item.get("assetTypeLevel", 1),
            'investFlag': asset_item.get("investFlag", "N"),
            'investFlagDisplay': 'Tài sản đầu tư' if asset_item.get("investFlag") == 'Y' else 'Tài sản không đầu tư',
            'holdingType': asset_item.get("holdingType"),
            'holdingAmount': self._safe_float(asset_item.get("holdingAmount")),
            'price': self._safe_float(asset_item.get("price")),
            'balanceFCY': self._safe_float(asset_item.get("balanceFCY")),
            'balanceVND': f"{balance_lcy:,.0f} {DEFAULT_CURRENCY}" if balance_lcy else f"0 {DEFAULT_CURRENCY}",
            'currency': asset_item.get("currency", DEFAULT_CURRENCY),
            'exchangeRate': asset_item.get("exchangeRate", ""),
            'profitDisplay': f"{profit:,.0f} {DEFAULT_CURRENCY}" if profit else f"0 {DEFAULT_CURRENCY}",
            'assetInfoParsed': asset_info_parsed
        }

        return {**asset_item, 'displayInfo': display_info, 'hierarchyInfo': hierarchy_info}

    def _parse_asset_info(self, asset_info: str, asset_type: str, hierarchy_info: Dict[str, Any]) -> Dict[str, Any]:
        """Parse thông tin chi tiết tài sản từ trường assetInfo"""
        if not asset_info or not isinstance(asset_info, str):
            return {'raw_info': asset_info, 'display_info': "Không có thông tin"}

        asset_type_name = hierarchy_info.get("name", "").lower()
        parent_info = hierarchy_info.get("parent_info", {})
        parent_name = parent_info.get("parent_name", "").lower() if parent_info else ""

        # Asset type mapping
        type_mappings = [
            (['tiền gửi', 'tài khoản', 'account', 'deposit'], "Số tài khoản"),
            (['thẻ', 'card'], "Số thẻ"),
            (['cổ phiếu', 'stock', 'equity'], "Mã Cổ phiếu"),
            (['trái phiếu', 'bond'], "Mã Trái phiếu")
        ]

        for keywords, prefix in type_mappings:
            if any(keyword in asset_type_name or keyword in parent_name for keyword in keywords):
                return {'raw_info': asset_info, 'display_info': f"{prefix}: {asset_info.strip()}"}

        return {'raw_info': asset_info, 'display_info': asset_info}

    def _process_asset_response(self, raw_data: Dict) -> Dict[str, Any]:
        """Xử lý response từ API tài sản"""
        if not raw_data:
            return {"soaErrorCode": "NO_DATA", "soaErrorDesc": "Không có dữ liệu từ API", "data": {}}

        try:
            data = raw_data.get('data', {})
            asset_items = (data.get('customerAsset', []) if isinstance(data, dict) and 'customerAsset' in data
                          else data if isinstance(data, list) else [])

            if not asset_items:
                return {"soaErrorCode": SUCCESS_CODE, "soaErrorDesc": "Thành công - Không có tài sản",
                       "data": {"customerAsset": []}}

            customer_assets = [self._format_customer_asset(item) for item in asset_items]
            return {"soaErrorCode": SUCCESS_CODE, "soaErrorDesc": "Thành công",
                   "data": {"customerAsset": customer_assets}}

        except Exception as e:
            LOGGER.error(f"Process asset error: {str(e)}")
            return {"soaErrorCode": "PROCESS_ERROR", "soaErrorDesc": f"Lỗi xử lý dữ liệu: {str(e)}", "data": {}}

    def _is_debt_asset(self, asset: Dict, hierarchy_info: Dict = None) -> bool:
        """Xác định một tài sản có phải là khoản nợ hay không"""
        if not hierarchy_info:
            hierarchy_info = AssetTypeHierarchy.get_asset_info(asset.get("assetType", ""))

        asset_type_name = hierarchy_info.get("name", "").upper()
        parent_info = hierarchy_info.get("parent_info", {})
        asset_type_parent_name = parent_info.get("parent_name", "").upper() if parent_info else ""

        # Check keywords
        if any(keyword in asset_type_name or keyword in asset_type_parent_name for keyword in DEBT_KEYWORDS):
            return True

        # Check asset type prefix
        asset_type = asset.get("assetType", "")
        if asset_type.startswith(DEBT_ASSET_PREFIXES):
            return True

        # Check negative balance
        try:
            balance_lcy = float(asset.get("balanceLCY", 0))
            if balance_lcy < 0:
                return True
        except (ValueError, TypeError):
            pass

        return False

    def _extract_product_info(self, product_info: List[Dict], product_type: str, field: str) -> str:
        """Extract thông tin sản phẩm theo type và field"""
        for product in product_info:
            if product.get('type') == product_type:
                return product.get(field, DEFAULT_STRING)
        return DEFAULT_STRING

    def _format_date(self, date_str: str) -> str:
        """Format date từ YYYYMMDD sang DD/MM/YYYY"""
        if not date_str or len(date_str) != 8:
            return DEFAULT_STRING
        try:
            return f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
        except (ValueError, IndexError):
            return DEFAULT_STRING

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == '' or value == 'null':
            return default
        try:
            str_value = str(value).strip()
            return float(str_value) if str_value and str_value.lower() != 'none' else default
        except (ValueError, TypeError):
            return default

    def _safe_string(self, value: Any, default: str = DEFAULT_STRING) -> str:
        """Safely extract string value, handling None and empty values"""
        if value is None or value == '' or value == 'null':
            return default
        return str(value).strip() if str(value).strip() else default


async def main() -> None:
    """Test function để kiểm tra TotalRevenueApiService - Enhanced Version"""
    print("🚀 Testing TotalRevenueApiService - Enhanced Version")
    print("=" * 80)

    service = TotalRevenueApiService()
    test_customers = {"assets": "5260279", "savings": "3099128"}
    test_business_domain = "MBB"

    from beechat_khcn.models.total_revenue_model import TotalRevenueAttributes, TotalRevenueIntent

    tests = [
        (TotalRevenueIntent.GET_TOTAL_ASSETS, test_customers["assets"], "GET_TOTAL_ASSETS Intent (Chỉ tài sản)"),
        (TotalRevenueIntent.GET_NET_WORTH, test_customers["assets"], "GET_NET_WORTH Intent (Cả tài sản và nợ)"),
        (TotalRevenueIntent.GET_INCOME_PROJECTION, test_customers["savings"], "GET_INCOME_PROJECTION Intent (Dự kiến thu nhập)")
    ]

    for i, (intent, customer, description) in enumerate(tests, 1):
        print(f"\nTEST {i}: {description}")
        print("-" * 60)

        try:
            attributes = TotalRevenueAttributes(customer_code=customer, business_domain=test_business_domain)
            result = await service.get_data_for_intent(intent, attributes)

            print(f"Intent: {result.get('intent')}")
            print(f"Success: {result.get('success')}")
            print(f"Customer: {result.get('customer_code')}")

            if result.get('success'):
                formatted_data = result.get('formatted_data', '')
                print(f"Data Length: {len(formatted_data)} chars")
                print("\n" + "=" * 80)
                print(f"{intent.value.upper()} - FORMATTED DATA OUTPUT:")
                print("=" * 80)
                print(formatted_data)
                print("=" * 80)
            else:
                print(f"Error: {result.get('error')}")

        except Exception as e:
            print(f"{intent.value} Exception: {str(e)}")

    print("\n" + "=" * 80)
    print("TEST SUMMARY - Tests completed successfully")
    print("=" * 80)


if __name__ == "__main__":
    print("🚀 Starting TotalRevenueApiService Enhanced Test Suite...")
    asyncio.run(main())