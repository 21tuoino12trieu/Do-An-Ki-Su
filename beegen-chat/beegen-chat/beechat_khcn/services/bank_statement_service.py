"""
Balance API Service - Cleaned và tối ưu hóa
Xử lý gọi API sao kê và quản lý session account với simplified logic
"""
import asyncio
import json
from typing import Dict, List, Optional, Union, Any

import aiohttp

from beechat_khcn.services.unified_attribute_coordinator import UnifiedAttributeCoordinator
from beegenerate.loggings import LOGGER


class BalanceApiService:
    """Service xử lý API calls và account management cho balance retrieve"""

    def __init__(self, llm_service, user_profile_service=None):
        self.llm_service = llm_service
        self.api_url = "http://beegen-transaction-history.tanzu-dev.mbbank.com.vn/api/app/transaction-integration"
        self.timeout = aiohttp.ClientTimeout(total=90)
        self.user_profile_service = user_profile_service
        unified_coordinator = UnifiedAttributeCoordinator(user_profile_service, llm_service)
        self.balance_coordinator = unified_coordinator.get_balance_coordinator_interface()
        LOGGER.info("BalanceApiService initialized")

    async def fetch_transactions(self,
                                 account_number: str,
                                 from_date: str = None,
                                 to_date: str = None,
                                 limit: int = None) -> Dict[str, Any]:
        """Fetch transactions từ API với enhanced logging và standardized error handling"""

        if not self.balance_coordinator.validate_account_number(account_number):
            LOGGER.error(f"Account validation failed: {account_number}")
            return {
                "error": "Số tài khoản không hợp lệ hoặc không thuộc sở hữu của bạn. Vui lòng kiểm tra lại số tài khoản.",
                "transactions": [],
                "error_type": "validation_error"
            }

        if not from_date or not to_date:
            from_date, to_date = self.balance_coordinator.get_default_date_range()
            LOGGER.info(f"Using default date range: {from_date} to {to_date}")
        else:
            from_date = self.balance_coordinator.normalize_date_to_api_format(from_date, False)
            to_date = self.balance_coordinator.normalize_date_to_api_format(to_date, True)

            if not from_date or not to_date:
                LOGGER.error("Date format normalization failed")
                return {
                    "error": "Định dạng ngày tháng không hợp lệ. Vui lòng nhập ngày theo định dạng DD/MM/YYYY (ví dụ: 01/01/2024).",
                    "transactions": [],
                    "error_type": "date_format_error"
                }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                payload = {
                    "kind": "statement",
                    "account_number": account_number,
                    "from_date": from_date,
                    "to_date": to_date,
                    "offset": 1,
                }

                if limit:
                    payload["limit"] = limit

                LOGGER.info(f"API Call - URL: {self.api_url}")
                LOGGER.info(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

                async with session.post(self.api_url, json=payload) as response:
                    LOGGER.info(f"Response Status: {response.status}")

                    if response.status == 200:
                        data = await response.json()
                        return self._process_api_response(data, account_number)
                    elif response.status == 400:
                        error_text = await response.text()
                        LOGGER.error(f"Bad request - Status: {response.status}, Response: {error_text[:200]}")
                        return {
                            "error": "Yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin tài khoản và khoảng thời gian.",
                            "transactions": [],
                            "error_type": "bad_request"
                        }
                    elif response.status == 404:
                        error_text = await response.text()
                        LOGGER.error(f"Account not found - Status: {response.status}, Response: {error_text[:200]}")
                        return {
                            "error": "Không tìm thấy thông tin tài khoản. Vui lòng kiểm tra lại số tài khoản.",
                            "transactions": [],
                            "error_type": "account_not_found"
                        }
                    elif response.status == 500:
                        error_text = await response.text()
                        LOGGER.error(f"Server error - Status: {response.status}, Response: {error_text[:200]}")
                        return {
                            "error": "Hệ thống đang bảo trì. Vui lòng thử lại sau ít phút hoặc liên hệ hotline 1900 588 822.",
                            "transactions": [],
                            "error_type": "server_error"
                        }
                    else:
                        error_text = await response.text()
                        LOGGER.error(f"HTTP error - Status: {response.status}, Response: {error_text[:200]}")
                        return {
                            "error": f"Lỗi kết nối (HTTP {response.status}). Vui lòng thử lại sau hoặc liên hệ hotline 1900 588 822.",
                            "transactions": [],
                            "error_type": "http_error"
                        }

        except asyncio.TimeoutError:
            LOGGER.error(f"Request timeout after {self.timeout.total}s")
            return {
                "error": "Yêu cầu quá thời gian chờ. Vui lòng kiểm tra kết nối mạng và thử lại.",
                "transactions": [],
                "error_type": "timeout_error"
            }
        except aiohttp.ClientError as e:
            LOGGER.error(f"Network connection error: {str(e)}")
            return {
                "error": "Lỗi kết nối mạng. Vui lòng kiểm tra kết nối internet và thử lại.",
                "transactions": [],
                "error_type": "network_error"
            }
        except json.JSONDecodeError as e:
            LOGGER.error(f"Invalid JSON response: {str(e)}")
            return {
                "error": "Phản hồi từ hệ thống không hợp lệ. Vui lòng thử lại sau.",
                "transactions": [],
                "error_type": "json_error"
            }
        except Exception as e:
            LOGGER.error(f"Unexpected error: {str(e)} | Type: {type(e).__name__}")
            return {
                "error": f"Lỗi không xác định: {type(e).__name__}. Vui lòng liên hệ hotline 1900 588 822 để được hỗ trợ.",
                "transactions": [],
                "error_type": "unknown_error"
            }

    def _process_api_response(self, data: Union[List, Dict], account_number: str) -> Dict[str, Any]:
        """Process API response với correct field mapping"""
        try:
            if isinstance(data, list):
                transactions = data
            elif isinstance(data, dict):
                if "error" in data:
                    LOGGER.error(f"API returned error: {data['error']}")
                    return {
                        "error": f"Lỗi từ hệ thống: {data['error']}. Vui lòng thử lại sau hoặc liên hệ hotline 1900 588 822.",
                        "transactions": [],
                        "error_type": "api_business_error"
                    }

                transactions = data.get("data") or data.get("transactions")
                if transactions is None:
                    LOGGER.warning(f"No transaction data found in response for account: {account_number}")
                    return {
                        "error": f"Không tìm thấy dữ liệu giao dịch cho tài khoản {account_number} trong khoảng thời gian đã chọn.",
                        "transactions": [],
                        "error_type": "no_data"
                    }

                if not isinstance(transactions, list):
                    LOGGER.error(f"Invalid transaction data format: expected list, got {type(transactions)}")
                    return {
                        "error": "Dữ liệu giao dịch không đúng định dạng. Vui lòng thử lại sau.",
                        "transactions": [],
                        "error_type": "invalid_data_format"
                    }
            else:
                LOGGER.error(f"Invalid response format: expected list or dict, got {type(data)}")
                return {
                    "error": "Phản hồi từ hệ thống không đúng định dạng. Vui lòng thử lại sau.",
                    "transactions": [],
                    "error_type": "invalid_response_format"
                }

            result = {
                "transactions": transactions,
                "account_number": account_number,
                "total_count": len(transactions)
            }

            if isinstance(data, dict):
                result.update({k: v for k, v in data.items()
                               if k not in ('data', 'transactions', 'account_number', 'total_count')})

            LOGGER.info(f"Successfully processed {len(transactions)} transactions for account: {account_number}")
            return result

        except Exception as e:
            LOGGER.error(f"Error processing API response: {str(e)} | Type: {type(e).__name__}")
            return {
                "error": f"Lỗi xử lý dữ liệu: {type(e).__name__}. Vui lòng thử lại sau hoặc liên hệ hotline 1900 588 822.",
                "transactions": [],
                "error_type": "processing_error"
            }

    def format_transactions_for_llm(self, api_response: Union[Dict, List], account_number: str) -> str:
        """Format transaction data cho LLM consumption"""
        try:
            if isinstance(api_response, dict) and "error" in api_response:
                return f"Không thể lấy dữ liệu giao dịch: {api_response['error']}"

            if isinstance(api_response, list):
                transactions = api_response
            elif isinstance(api_response, dict):
                transactions = api_response.get("transactions", [])
            else:
                transactions = []

            if not transactions:
                return f"Không có giao dịch nào trong khoảng thời gian đã chọn cho tài khoản {account_number}."

            formatted_lines = [
                f"LỊCH SỬ GIAO DỊCH TÀI KHOẢN: {account_number}",
                f"Tổng số giao dịch: {len(transactions)}",
                "=" * 60
            ]

            for i, tx in enumerate(transactions, 1):
                if isinstance(tx, dict):
                    formatted_lines.extend([
                        f"GIAO DỊCH #{i}:",
                        f"   Ngày: {tx.get('day_transaction', 'N/A')}",
                        f"   Giờ: {tx.get('time_transaction', 'N/A')}",
                        f"   Loại: {tx.get('type_transaction', 'N/A')}",
                        f"   Số tiền: {tx.get('amount', 'N/A')}",
                        f"   Nội dung: {tx.get('content_transaction', 'N/A')}",
                        "-" * 40
                    ])

            LOGGER.info(f"Successfully formatted {len(transactions)} transactions for LLM")
            return "\n".join(formatted_lines)

        except Exception as e:
            LOGGER.error(f"Error formatting transactions for LLM: {str(e)} | Type: {type(e).__name__}")
            return f"Lỗi định dạng dữ liệu giao dịch cho tài khoản {account_number}. Vui lòng thử lại sau."