"""
Unified API Service - Centralized API client with resilient data parsing
Handles missing fields gracefully without errors
"""

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import aiohttp
from beegenerate.loggings import LOGGER


# ==================== Configuration ====================
@dataclass
class APIEndpointConfig:
    """Configuration for API endpoints"""
    base_url: str
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 1


class APIType(Enum):
    """Supported API types"""
    BANK_STATEMENT = "bank_statement"
    TOTAL_ASSETS = "total_assets"
    TRANSACTION_HISTORY = "transaction_history"
    ACCOUNT_BALANCE = "account_balance"


# API configuration registry
API_CONFIGS = {
    APIType.BANK_STATEMENT: APIEndpointConfig(
        base_url="http://10.7.67.102:8000/api/app/bank-statement"
    ),
    APIType.TOTAL_ASSETS: APIEndpointConfig(
        base_url="http://10.7.67.102:8000/api/app/transaction-integration"
    )
}


# ==================== Safe Data Access Utilities ====================
class SafeDataAccess:
    """Utilities for safe data access with defaults"""

    @staticmethod
    def get_value(data: Dict, key: str, default: Any = None) -> Any:
        """Safely get value from dict with default"""
        if not isinstance(data, dict):
            return default
        return data.get(key, default)

    @staticmethod
    def get_nested(data: Dict, keys: List[str], default: Any = None) -> Any:
        """Safely get nested value from dict"""
        if not isinstance(data, dict):
            return default

        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default

            if current is None:
                return default

        return current

    @staticmethod
    def get_number(data: Dict, key: str, default: float = 0.0) -> float:
        """Safely get numeric value, always return float"""
        value = SafeDataAccess.get_value(data, key, default)
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_string(data: Dict, key: str, default: str = "") -> str:
        """Safely get string value"""
        value = SafeDataAccess.get_value(data, key, default)
        return str(value) if value is not None else default

    @staticmethod
    def get_list(data: Dict, key: str, default: List = None) -> List:
        """Safely get list value"""
        if default is None:
            default = []
        value = SafeDataAccess.get_value(data, key, default)
        return value if isinstance(value, list) else default

    @staticmethod
    def get_bool(data: Dict, key: str, default: bool = False) -> bool:
        """Safely get boolean value"""
        value = SafeDataAccess.get_value(data, key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', 'y', '1')
        return bool(value) if value is not None else default


# ==================== Asset Type Definitions ====================
class AssetTypeCode:
    """Asset type codes mapping"""
    CREDIT_CARD = "11"
    LOAN = "121"
    OVERDRAFT = "122"
    CASA = "211"  # Checking account
    DEPOSIT = "213"  # Savings deposit
    CERTIFICATE_DEPOSIT = "215"
    BOND = "22"
    GOLD = "28"
    REAL_ESTATE = "31"
    TRANSPORT = "32"

    # Asset levels
    LEVEL_1_DEBT = "1"  # Dư nợ
    LEVEL_1_ASSET = "2"  # Tài sản
    LEVEL_1_OTHER = "3"  # Khác

    @classmethod
    def get_asset_name(cls, code: str) -> str:
        """Get Vietnamese name for asset type"""
        mapping = {
            cls.CREDIT_CARD: "Thẻ tín dụng",
            cls.LOAN: "Vay theo hợp đồng tín dụng",
            cls.OVERDRAFT: "Tài khoản vay thấu chi",
            cls.CASA: "Tài khoản thanh toán",
            cls.DEPOSIT: "Tiền gửi tiết kiệm/Có kỳ hạn",
            cls.CERTIFICATE_DEPOSIT: "Chứng chỉ tiền gửi",
            cls.BOND: "Trái phiếu",
            cls.GOLD: "Vàng",
            cls.REAL_ESTATE: "Bất động sản",
            cls.TRANSPORT: "Phương tiện vận tải"
        }
        return mapping.get(code, "Không xác định")


# ==================== Response Models ====================
@dataclass
class ParsedAsset:
    """Parsed asset data with defaults"""
    business_domain: str = ""
    customer_code: str = ""
    asset_type: str = ""
    asset_type_name: str = "Không xác định"
    asset_type_level: int = 0
    asset_type_parent: str = ""
    is_investment: bool = False
    asset_info: str = ""
    holding_amount: float = 0.0
    price: float = 0.0
    balance_original: float = 0.0
    balance_vnd: float = 0.0
    currency: str = "VND"
    data_date: Optional[str] = None


@dataclass
class PortfolioMetrics:
    """Portfolio metrics with defaults"""
    total_debt: float = 0.0
    total_assets: float = 0.0
    net_worth: float = 0.0
    debt_to_asset_ratio: float = 0.0
    asset_allocation: Dict[str, float] = field(default_factory=lambda: {
        "deposits_pct": 0.0,
        "investments_pct": 0.0,
        "others_pct": 0.0
    })
    liquidity_ratio: float = 0.0
    investment_ratio: float = 0.0


@dataclass
class ParsedResponse:
    """Standard parsed response structure"""
    success: bool = True
    has_data: bool = False
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== Response Parsers ====================
class BaseResponseParser(ABC):
    """Base class for API response parsers with safe data access"""

    def __init__(self):
        self.safe = SafeDataAccess()

    @abstractmethod
    def parse(self, response_data: Optional[Dict]) -> ParsedResponse:
        """Parse raw API response to standardized format"""
        pass

    def validate_basic(self, response_data: Any) -> bool:
        """Basic validation - check if response is dict"""
        return isinstance(response_data, dict)


class TotalAssetsParser(BaseResponseParser):
    """Parser for total assets API with resilient field handling"""

    def parse(self, response_data: Optional[Dict]) -> ParsedResponse:
        """
        Parse total assets response with graceful handling of missing fields
        Always returns ParsedResponse, never throws errors
        """
        result = ParsedResponse()

        # Handle null or invalid response
        if not response_data:
            result.success = False
            result.message = "Không có dữ liệu phản hồi từ API"
            return result

        if not self.validate_basic(response_data):
            result.success = False
            result.message = "Định dạng dữ liệu không hợp lệ"
            return result

        # Check API status - flexible handling
        status = self.safe.get_string(response_data, 'status', 'unknown')
        soa_error_code = self.safe.get_string(response_data, 'soaErrorCode', '')
        soa_error_desc = self.safe.get_string(response_data, 'soaErrorDesc', '')

        # Log but don't fail on error codes
        if soa_error_code and soa_error_code != '0000':
            LOGGER.warning(f"API returned error code: {soa_error_code} - {soa_error_desc}")
            result.metadata['api_error_code'] = soa_error_code
            result.metadata['api_error_desc'] = soa_error_desc

        # Get data object - could be dict or list
        data = response_data.get('data')

        # Handle different data formats
        if isinstance(data, dict):
            parsed_data = self._parse_data_dict(data)
        elif isinstance(data, list):
            # If data is list, wrap in dict
            parsed_data = self._parse_data_list(data)
        else:
            # No data or unknown format - return empty but valid response
            parsed_data = self._get_empty_data_structure()
            result.has_data = False
            result.message = "Không có dữ liệu tài sản"

        # Always populate result data
        result.data = parsed_data
        result.success = True
        result.has_data = self._check_has_data(parsed_data)

        # Add metadata
        result.metadata.update({
            "api_status": status,
            "response_time": datetime.now().isoformat(),
            "data_date": self.safe.get_string(response_data, 'dataDate',
                                              datetime.now().strftime("%Y-%m-%d"))
        })

        return result

    def _parse_data_dict(self, data: Dict) -> Dict:
        """Parse data when it's a dictionary"""
        # Parse error members if any
        error_members = self._parse_error_members(
            self.safe.get_list(data, 'errorMember', [])
        )

        # Parse customer assets
        customer_assets = self._parse_customer_assets(
            self.safe.get_list(data, 'customerAsset', [])
        )

        # Parse asset summaries
        asset_summary = self._parse_asset_summary(
            self.safe.get_list(data, 'customerAssetSum', [])
        )

        investment_summary = self._parse_investment_summary(
            self.safe.get_list(data, 'customerAssetSumInvest', [])
        )

        # Calculate metrics - will return defaults if no data
        portfolio_metrics = self._calculate_portfolio_metrics(
            customer_assets, asset_summary
        )

        # Generate insights - will return empty if no data
        portfolio_insights = self._generate_portfolio_insights(portfolio_metrics)

        return {
            "customer_assets": customer_assets,
            "asset_summary": asset_summary,
            "investment_summary": investment_summary,
            "portfolio_metrics": portfolio_metrics,
            "portfolio_insights": portfolio_insights,
            "error_members": error_members
        }

    def _parse_data_list(self, data: List) -> Dict:
        """Parse data when it's a list (legacy format)"""
        # Convert list to expected format
        return {
            "customer_assets": {"raw_list": data},
            "asset_summary": {},
            "investment_summary": [],
            "portfolio_metrics": self._get_default_metrics(),
            "portfolio_insights": {},
            "error_members": []
        }

    def _get_empty_data_structure(self) -> Dict:
        """Return empty but valid data structure"""
        return {
            "customer_assets": {
                "debt": [],
                "deposits": [],
                "investments": [],
                "others": []
            },
            "asset_summary": {
                "level_1": [],
                "level_2": [],
                "level_3": []
            },
            "investment_summary": [],
            "portfolio_metrics": self._get_default_metrics(),
            "portfolio_insights": {
                "risk_profile": "Không có dữ liệu",
                "allocation_assessment": "Không có dữ liệu để đánh giá",
                "recommendations": []
            },
            "error_members": []
        }

    def _get_default_metrics(self) -> Dict:
        """Get default portfolio metrics"""
        return {
            "total_debt": 0.0,
            "total_assets": 0.0,
            "net_worth": 0.0,
            "debt_to_asset_ratio": 0.0,
            "asset_allocation": {
                "deposits_pct": 0.0,
                "investments_pct": 0.0,
                "others_pct": 0.0
            },
            "liquidity_ratio": 0.0,
            "investment_ratio": 0.0
        }

    def _check_has_data(self, parsed_data: Dict) -> bool:
        """Check if parsed data actually contains assets"""
        customer_assets = parsed_data.get('customer_assets', {})
        if isinstance(customer_assets, dict):
            for category in ['debt', 'deposits', 'investments', 'others']:
                if customer_assets.get(category):
                    return True
        return False

    def _parse_error_members(self, error_members: List) -> List[Dict]:
        """Parse error information with safe access"""
        parsed_errors = []
        for error in error_members:
            if not isinstance(error, dict):
                continue

            parsed_errors.append({
                "business_domain": self.safe.get_string(error, 'businessDomain', ''),
                "error_code": self.safe.get_string(error, 'errorCodeMem', ''),
                "error_desc": self.safe.get_string(error, 'errorDescMem', 'Không có mô tả'),
                "data_date": self.safe.get_string(error, 'dataDateMem', '')
            })
        return parsed_errors

    def _parse_customer_assets(self, assets: List) -> Dict:
        """Parse customer assets with safe field access"""
        categorized_assets = {
            "debt": [],
            "deposits": [],
            "investments": [],
            "others": []
        }

        for asset in assets:
            if not isinstance(asset, dict):
                continue

            # Safe extraction of all fields
            asset_type = self.safe.get_string(asset, 'assetType', '')

            parsed_asset = {
                "business_domain": self.safe.get_string(asset, 'businessDomain', 'N/A'),
                "customer_code": self.safe.get_string(asset, 'customerCode', ''),
                "asset_type": asset_type,
                "asset_type_name": AssetTypeCode.get_asset_name(asset_type) if asset_type else "Không xác định",
                "asset_type_level": self.safe.get_number(asset, 'assetTypeLevel', 0),
                "asset_type_parent": self.safe.get_string(asset, 'assetTypeParent', ''),
                "is_investment": self.safe.get_string(asset, 'investFlag', 'N') == 'Y',
                "asset_info": self.safe.get_string(asset, 'assetInfo', ''),
                "holding_amount": self.safe.get_number(asset, 'holdingAmount', 0),
                "price": self.safe.get_number(asset, 'price', 0),
                "balance_original": self.safe.get_number(asset, 'balanceFCY', 0),
                "balance_vnd": self.safe.get_number(asset, 'balanceLCY', 0),
                "currency": self.safe.get_string(asset, 'currency', 'VND'),
                "data_date": self.safe.get_string(asset, 'dataDate', '')
            }

            # Categorize based on parent type
            parent_type = parsed_asset['asset_type_parent']
            if parent_type.startswith('1'):
                categorized_assets["debt"].append(parsed_asset)
            elif parent_type.startswith('21'):
                categorized_assets["deposits"].append(parsed_asset)
            elif parsed_asset['is_investment']:
                categorized_assets["investments"].append(parsed_asset)
            else:
                categorized_assets["others"].append(parsed_asset)

        return categorized_assets

    def _parse_asset_summary(self, summaries: List) -> Dict:
        """Parse asset summary with safe access"""
        hierarchy = {
            "level_1": [],
            "level_2": [],
            "level_3": []
        }

        for summary in summaries:
            if not isinstance(summary, dict):
                continue

            level = self.safe.get_number(summary, 'assetTypeLevel', 0)

            parsed_summary = {
                "asset_type": self.safe.get_string(summary, 'assetType', ''),
                "asset_type_name": self.safe.get_string(summary, 'assetTypeStName', 'Không xác định'),
                "asset_type_level": level,
                "parent_type": self.safe.get_string(summary, 'assetTypeParent', ''),
                "parent_name": self.safe.get_string(summary, 'assetTypeParentStName', ''),
                "invest_flag": self.safe.get_string(summary, 'investFlagTP', 'N'),
                "balance_vnd": self.safe.get_number(summary, 'balanceLCY', 0)
            }

            if level == 1:
                hierarchy["level_1"].append(parsed_summary)
            elif level == 2:
                hierarchy["level_2"].append(parsed_summary)
            elif level == 3:
                hierarchy["level_3"].append(parsed_summary)

        return hierarchy

    def _parse_investment_summary(self, summaries: List) -> List[Dict]:
        """Parse investment summary with safe access"""
        investment_summary = []

        for summary in summaries:
            if not isinstance(summary, dict):
                continue

            investment_summary.append({
                "asset_type": self.safe.get_string(summary, 'assetType', ''),
                "asset_type_name": self.safe.get_string(summary, 'assetTypeStName', 'Không xác định'),
                "asset_type_level": self.safe.get_number(summary, 'assetTypeLevel', 0),
                "parent_type": self.safe.get_string(summary, 'assetTypeParent', ''),
                "balance_vnd": self.safe.get_number(summary, 'balanceLCY', 0)
            })

        return investment_summary

    def _calculate_portfolio_metrics(self, assets: Dict, summary: Dict) -> Dict:
        """Calculate metrics with safe defaults"""
        # Safe summation with defaults
        total_debt = sum(
            self.safe.get_number(a, 'balance_vnd', 0)
            for a in assets.get('debt', [])
        )
        total_deposits = sum(
            self.safe.get_number(a, 'balance_vnd', 0)
            for a in assets.get('deposits', [])
        )
        total_investments = sum(
            self.safe.get_number(a, 'balance_vnd', 0)
            for a in assets.get('investments', [])
        )
        total_others = sum(
            self.safe.get_number(a, 'balance_vnd', 0)
            for a in assets.get('others', [])
        )

        total_assets = total_deposits + total_investments + total_others
        net_worth = total_assets - total_debt

        # Safe percentage calculation
        def safe_percentage(value: float, total: float) -> float:
            if total > 0:
                return round((value / total * 100), 2)
            return 0.0

        return {
            "total_debt": total_debt,
            "total_assets": total_assets,
            "net_worth": net_worth,
            "debt_to_asset_ratio": safe_percentage(total_debt, total_assets + total_debt),
            "asset_allocation": {
                "deposits_pct": safe_percentage(total_deposits, total_assets),
                "investments_pct": safe_percentage(total_investments, total_assets),
                "others_pct": safe_percentage(total_others, total_assets)
            },
            "liquidity_ratio": safe_percentage(total_deposits, total_assets),
            "investment_ratio": safe_percentage(total_investments, total_assets)
        }

    def _generate_portfolio_insights(self, metrics: Dict) -> Dict:
        """Generate insights with safe access"""
        insights = {
            "risk_profile": "Không có dữ liệu",
            "allocation_assessment": "Không có dữ liệu để đánh giá",
            "recommendations": []
        }

        # Only generate insights if we have data
        total_assets = metrics.get('total_assets', 0)
        if total_assets <= 0:
            return insights

        debt_ratio = metrics.get('debt_to_asset_ratio', 0)
        allocation = metrics.get('asset_allocation', {})
        deposit_pct = allocation.get('deposits_pct', 0)
        investment_pct = allocation.get('investments_pct', 0)

        # Risk profile
        if debt_ratio > 60:
            insights["risk_profile"] = "Mức độ sử dụng đòn bẩy cao"
        elif investment_pct > 60:
            insights["risk_profile"] = "Định hướng tăng trưởng"
        elif deposit_pct > 60:
            insights["risk_profile"] = "Bảo toàn vốn"
        else:
            insights["risk_profile"] = "Cân bằng"

        # Allocation assessment
        if deposit_pct > 60:
            insights["allocation_assessment"] = "Tài sản được phân bổ chủ yếu vào kênh thanh khoản cao"
        elif investment_pct > 60:
            insights["allocation_assessment"] = "Phần lớn tài sản trong nhóm biến động theo thị trường"
        elif abs(deposit_pct - investment_pct) < 20:
            insights["allocation_assessment"] = "Danh mục phân bổ cân đối giữa các nhóm"
        else:
            insights["allocation_assessment"] = "Danh mục có phân bổ không đồng đều"

        # Recommendations
        if deposit_pct < 10 and total_assets > 0:
            insights["recommendations"].append("Cân nhắc duy trì quỹ dự phòng khẩn cấp")
        if debt_ratio > 50:
            insights["recommendations"].append("Xem xét giảm tỷ lệ nợ để giảm rủi ro")
        if investment_pct < 20 and metrics.get('net_worth', 0) > 0:
            insights["recommendations"].append("Có thể tăng tỷ trọng đầu tư cho mục tiêu dài hạn")

        return insights


class BankStatementParser(BaseResponseParser):
    """Parser for bank statement with resilient parsing"""

    def parse(self, response_data: Optional[Dict]) -> ParsedResponse:
        """Parse bank statement response"""
        result = ParsedResponse()

        if not response_data:
            result.success = False
            result.message = "Không có dữ liệu phản hồi"
            return result

        # Safe parsing implementation
        result.data = {
            "transactions": self.safe.get_list(response_data, 'transactions', []),
            "account_number": self.safe.get_string(response_data, 'account_number', ''),
            "from_date": self.safe.get_string(response_data, 'from_date', ''),
            "to_date": self.safe.get_string(response_data, 'to_date', ''),
            "total_debit": self.safe.get_number(response_data, 'total_debit', 0),
            "total_credit": self.safe.get_number(response_data, 'total_credit', 0)
        }

        result.success = True
        result.has_data = len(result.data.get('transactions', [])) > 0

        return result


# ==================== Main API Service ====================
class UnifiedAPIService:
    """
    Unified API service with resilient data handling
    Never fails on missing fields, always returns usable data
    """

    def __init__(self):
        """Initialize unified API service"""
        self.configs = API_CONFIGS
        self.parsers = {
            APIType.TOTAL_ASSETS: TotalAssetsParser(),
            APIType.BANK_STATEMENT: BankStatementParser()
        }
        self.session: Optional[aiohttp.ClientSession] = None
        LOGGER.info("UnifiedAPIService initialized with resilient parsing")

    async def fetch_data(
        self,
        api_type: APIType,
        params: Dict[str, Any],
        custom_config: Optional[APIEndpointConfig] = None
    ) -> ParsedResponse:
        """
        Fetch and parse data with complete error resilience
        Always returns ParsedResponse, never throws
        """
        # Get parser
        parser = self.parsers.get(api_type)
        if not parser:
            return ParsedResponse(
                success=False,
                message=f"No parser configured for {api_type.value}"
            )

        # Get configuration
        config = custom_config or self.configs.get(api_type)
        if not config:
            return ParsedResponse(
                success=False,
                message=f"No configuration for {api_type.value}"
            )

        try:
            # Build request
            request_data = self._build_request(api_type, params)

            # Execute request
            raw_response = await self._execute_request(
                config=config,
                request_data=request_data
            )

            # Parse response - parser handles all error cases
            return parser.parse(raw_response)

        except Exception as e:
            LOGGER.error(f"Unexpected error in fetch_data: {e}")
            return ParsedResponse(
                success=False,
                message="Lỗi không xác định khi truy vấn dữ liệu"
            )

    def _build_request(self, api_type: APIType, params: Dict) -> Dict:
        """Build request with safe parameter access"""
        safe = SafeDataAccess()

        if api_type == APIType.TOTAL_ASSETS:
            return {
                "kind": "asset",
                "business_domain": safe.get_string(params, "business_domain", "MBB"),
                "customer_code": safe.get_string(params, "customer_code", "")
            }
        elif api_type == APIType.BANK_STATEMENT:
            return {
                "account_number": safe.get_string(params, "account_number", ""),
                "from_date": safe.get_string(params, "from_date", ""),
                "to_date": safe.get_string(params, "to_date", "")
            }
        else:
            return params

    async def _execute_request(
        self,
        config: APIEndpointConfig,
        request_data: Dict,
        method: str = "POST"
    ) -> Optional[Dict]:
        """
        Execute request with resilient error handling
        Returns None on failure instead of error dict
        """
        headers = {'Content-Type': 'application/json'}
        timeout = aiohttp.ClientTimeout(total=config.timeout)

        for attempt in range(config.max_retries):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession(timeout=timeout)

                LOGGER.info(f"API Request attempt {attempt + 1}/{config.max_retries}")

                async with self.session.request(
                    method=method,
                    url=config.base_url,
                    json=request_data,
                    headers=headers
                ) as response:

                    # Try to get JSON regardless of status
                    try:
                        data = await response.json()
                        return data
                    except:
                        # Return empty dict if can't parse JSON
                        LOGGER.warning(f"Could not parse JSON response")
                        return {}

            except asyncio.TimeoutError:
                LOGGER.error(f"Request timeout (attempt {attempt + 1})")
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(config.retry_delay)
                    continue

            except Exception as e:
                LOGGER.error(f"Request error: {e}")
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(config.retry_delay)
                    continue

        # Return None after all retries failed
        return None

    async def get_total_assets(
        self,
        customer_code: str,
        business_domain: str = "MBB"
    ) -> ParsedResponse:
        """
        Get total assets with guaranteed response structure
        Never fails, always returns ParsedResponse
        """
        return await self.fetch_data(
            api_type=APIType.TOTAL_ASSETS,
            params={
                "customer_code": customer_code,
                "business_domain": business_domain
            }
        )

    def format_assets_for_display(self, parsed_response: ParsedResponse) -> str:
        """Format parsed response for display"""
        if not parsed_response.success:
            return f"⚠️ {parsed_response.message}"

        if not parsed_response.has_data:
            return "Không có dữ liệu tài sản để hiển thị"

        data = parsed_response.data
        metrics = data.get('portfolio_metrics', {})
        insights = data.get('portfolio_insights', {})

        output = []
        output.append("TỔNG QUAN TÀI SẢN")

        # Display with safe defaults
        total_assets = metrics.get('total_assets', 0)
        total_debt = metrics.get('total_debt', 0)
        net_worth = metrics.get('net_worth', 0)

        if total_assets > 0 or total_debt > 0:
           output.append(f"• Tổng tài sản: {total_assets:,.0f} VND")
           output.append(f"• Tổng dư nợ: {total_debt:,.0f} VND")
           output.append(f"• Tài sản ròng: {net_worth:,.0f} VND")
        else:
           output.append("• Chưa có thông tin tài sản")

       # Asset allocation
        allocation = metrics.get('asset_allocation', {})
        if any(allocation.values()):
           output.append("\n📈 PHÂN BỔ TÀI SẢN")
           output.append(f"• Tiền gửi: {allocation.get('deposits_pct', 0)}%")
           output.append(f"• Đầu tư: {allocation.get('investments_pct', 0)}%")
           output.append(f"• Khác: {allocation.get('others_pct', 0)}%")

       # Insights
        if insights.get('risk_profile') != "Không có dữ liệu":
           output.append("\n💡 ĐÁNH GIÁ DANH MỤC")
           output.append(f"• Hồ sơ rủi ro: {insights.get('risk_profile', 'N/A')}")
           output.append(f"• {insights.get('allocation_assessment', 'N/A')}")

       # Recommendations
        recommendations = insights.get('recommendations', [])
        if recommendations:
           output.append("\nGỢI Ý")
           for rec in recommendations:
               output.append(f"• {rec}")

        return "\n".join(output)

    async def __aenter__(self):
       """Async context manager entry"""
       self.session = aiohttp.ClientSession()
       return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
       """Async context manager exit"""
       if self.session:
           await self.session.close()


# ==================== Error Recovery Utilities ====================
class DataRecoveryService:
   """Service for recovering and enriching incomplete data"""

   @staticmethod
   def enrich_missing_asset_names(assets: List[Dict]) -> List[Dict]:
       """Add asset names for items missing names"""
       for asset in assets:
           if not asset.get('asset_type_name') or asset['asset_type_name'] == 'Không xác định':
               asset_type = asset.get('asset_type', '')
               if asset_type:
                   asset['asset_type_name'] = AssetTypeCode.get_asset_name(asset_type)
       return assets

   @staticmethod
   def estimate_missing_values(metrics: Dict) -> Dict:
       """Estimate missing values based on available data"""
       # If we have total assets but missing allocation percentages
       if metrics.get('total_assets', 0) > 0:
           allocation = metrics.get('asset_allocation', {})

           # Check if percentages sum to less than 100
           total_pct = sum(allocation.values())
           if total_pct < 100:
               # Assign remainder to 'others'
               allocation['others_pct'] = round(100 - total_pct, 2)

       return metrics

   @staticmethod
   def validate_data_consistency(parsed_response: ParsedResponse) -> ParsedResponse:
       """Validate and fix data consistency issues"""
       if not parsed_response.has_data:
           return parsed_response

       data = parsed_response.data

       # Check if customer assets match summaries
       customer_assets = data.get('customer_assets', {})
       metrics = data.get('portfolio_metrics', {})

       # Recalculate if there's mismatch
       if customer_assets and isinstance(customer_assets, dict):
           calculated_total = 0
           for category in ['deposits', 'investments', 'others']:
               category_total = sum(
                   item.get('balance_vnd', 0)
                   for item in customer_assets.get(category, [])
                   if isinstance(item, dict)
               )
               calculated_total += category_total

           # Update metrics if significantly different
           if abs(calculated_total - metrics.get('total_assets', 0)) > 1000:
               metrics['total_assets'] = calculated_total
               LOGGER.info(f"Recalculated total assets: {calculated_total}")

       return parsed_response


# ==================== Response Aggregator ====================
class ResponseAggregator:
   """Aggregate responses from multiple API calls"""

   @staticmethod
   def merge_responses(responses: List[ParsedResponse]) -> ParsedResponse:
       """Merge multiple parsed responses into one"""
       merged = ParsedResponse()

       # Check if any response was successful
       successful_responses = [r for r in responses if r.success]
       if not successful_responses:
           merged.success = False
           merged.message = "Không có phản hồi thành công từ API"
           return merged

       # Merge data from all successful responses
       merged_data = {}
       for response in successful_responses:
           if response.has_data:
               merged_data.update(response.data)

       merged.data = merged_data
       merged.has_data = bool(merged_data)
       merged.success = True

       return merged

   @staticmethod
   def aggregate_metrics(responses: List[ParsedResponse]) -> Dict:
       """Aggregate metrics from multiple responses"""
       total_metrics = {
           "total_debt": 0,
           "total_assets": 0,
           "net_worth": 0,
           "response_count": len(responses),
           "successful_count": sum(1 for r in responses if r.success),
           "data_count": sum(1 for r in responses if r.has_data)
       }

       for response in responses:
           if response.has_data:
               metrics = response.data.get('portfolio_metrics', {})
               total_metrics['total_debt'] += metrics.get('total_debt', 0)
               total_metrics['total_assets'] += metrics.get('total_assets', 0)
               total_metrics['net_worth'] += metrics.get('net_worth', 0)

       return total_metrics


# ==================== Usage Examples ====================
async def example_resilient_usage():
   """Example showing resilient data handling"""

   async with UnifiedAPIService() as api_service:
       # Test with various scenarios
       test_cases = [
           # Normal case
           {"customer_code": "6006939", "business_domain": "MBB"},
           # Missing domain - will use default
           {"customer_code": "6006939"},
           # Invalid customer code - will handle gracefully
           {"customer_code": ""},
       ]

       recovery_service = DataRecoveryService()
       aggregator = ResponseAggregator()

       responses = []

       for params in test_cases:
           print(f"\n🔍 Testing with params: {params}")

           # Get assets - always returns ParsedResponse
           result = await api_service.get_total_assets(**params)

           # Validate and fix consistency
           result = recovery_service.validate_data_consistency(result)

           # Display result
           print(f"Success: {result.success}")
           print(f"Has Data: {result.has_data}")
           print(f"Message: {result.message}")

           if result.has_data:
               # Format and display
               formatted = api_service.format_assets_for_display(result)
               print(formatted)

           responses.append(result)

       # Aggregate all responses
       print("\nAGGREGATED METRICS")
       aggregated = aggregator.aggregate_metrics(responses)
       for key, value in aggregated.items():
           print(f"• {key}: {value}")


async def example_missing_fields():
   """Example handling responses with missing fields"""

   # Simulate various API responses with missing fields
   test_responses = [
       # Complete response
       {
           "status": "success",
           "soaErrorCode": "0000",
           "data": {
               "customerAsset": [
                   {
                       "assetType": "211",
                       "balanceLCY": 1000000,
                       "assetTypeParent": "21"
                   }
               ]
           }
       },
       # Missing nested fields
       {
           "status": "success",
           "soaErrorCode": "0000",
           "data": {
               "customerAsset": [
                   {
                       "assetType": "213"
                       # Missing balanceLCY and other fields
                   }
               ]
           }
       },
       # Missing data field entirely
       {
           "status": "success",
           "soaErrorCode": "0000"
       },
       # Empty response
       {},
       # Null response
       None
   ]

   parser = TotalAssetsParser()

   for i, test_response in enumerate(test_responses, 1):
       print(f"\n Test Case {i}")
       print(f"Input: {test_response}")

       result = parser.parse(test_response)

       print(f"Success: {result.success}")
       print(f"Has Data: {result.has_data}")
       print(f"Message: {result.message}")

       if result.has_data:
           metrics = result.data.get('portfolio_metrics', {})
           print(f"Total Assets: {metrics.get('total_assets', 0):,.0f} VND")


async def example_error_handling():
   """Example of comprehensive error handling"""

   async with UnifiedAPIService() as api_service:
       # Test various error scenarios

       # Scenario 1: API timeout
       print("\n📝 Scenario 1: Simulating API timeout")
       custom_config = APIEndpointConfig(
           base_url="http://invalid-url-timeout-test.com",
           timeout=1,
           max_retries=2
       )

       result = await api_service.fetch_data(
           api_type=APIType.TOTAL_ASSETS,
           params={"customer_code": "test"},
           custom_config=custom_config
       )

       print(f"Result: {result.success}")
       print(f"Message: {result.message}")

       # Scenario 2: Invalid API type
       print("\n📝 Scenario 2: Invalid parser")
       try:
           invalid_type = APIType.TRANSACTION_HISTORY  # No parser configured
           result = await api_service.fetch_data(
               api_type=invalid_type,
               params={}
           )
           print(f"Result: {result.success}")
           print(f"Message: {result.message}")
       except Exception as e:
           print(f"Handled exception: {e}")


if __name__ == "__main__":
   print("🚀 Starting Resilient API Service Examples\n")

   # Run examples
   print("=" * 60)
   print("EXAMPLE 1: Resilient Usage")
   print("=" * 60)
   asyncio.run(example_resilient_usage())

   print("\n" + "=" * 60)
   print("EXAMPLE 2: Missing Fields Handling")
   print("=" * 60)
   asyncio.run(example_missing_fields())

   print("\n" + "=" * 60)
   print("EXAMPLE 3: Error Handling")
   print("=" * 60)
   asyncio.run(example_error_handling())