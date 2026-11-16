"""
Loan Management API Service - API calls cho loan management domain
Xử lý các API liên quan đến LD và AC
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import wraps

import aiohttp

from beegenerate.loggings import LOGGER
from beechat_khcn.models.loan_management_model import LoanManagementIntent, LoanManagementAttributes

# Constants
DEFAULT_CURRENCY = "VND"
DEFAULT_VALUE = "N/A"
DEFAULT_TIMEOUT = 60
DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%m/%d/%Y %H:%M"
API_SUCCESS_STATUS = 200

def safe_api_call(func):
    """Decorator for safe API calls with consistent error handling"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            LOGGER.error(f"Error in {func.__name__}: {str(e)}")
            error_type = type(e).__name__
            if "TimeoutError" in error_type:
                return {"status": 408, "error": f"Timeout after {self.timeout}s"}
            return {"status": 500, "error": f"System error: {str(e)}"}
    return wrapper

class LoanManagementApiService:
    """Service xử lý API calls cho loan management"""

    def __init__(self, llm_service=None) -> None:
        self.llm_service = llm_service
        self.ld_api_url = "http://beegen-transaction-history.tanzu-dev.mbbank.com.vn/api/app/transaction-integration"
        self.timeout = DEFAULT_TIMEOUT
        LOGGER.info("LoanManagementApiService initialized")

    def _safe_convert(self, value: str, convert_type: str, format_pattern: str = "") -> Any:
        """Safe conversion with null/empty handling"""
        if not value or value in ["", "0", None]:
            return 0.0 if convert_type == "amount" else ""

        try:
            if convert_type == "amount":
                return float(str(value).replace(",", "").replace(" ", "")) if str(value) else 0.0
            elif convert_type == "date" and len(str(value)) == 8 and str(value).isdigit():
                return datetime.strptime(str(value), "%Y%m%d").strftime(format_pattern or DATE_FORMAT)
            elif convert_type == "datetime" and len(str(value)) == 10 and str(value).isdigit():
                v = str(value)
                return f"{v[4:6]}/{v[2:4]}/20{v[:2]} {v[6:8]}:{v[8:10]}"
            return str(value) if value else ""
        except (ValueError, TypeError):
            return 0.0 if convert_type == "amount" else (str(value) if value else "")

    async def get_data_for_intent(self, intent: LoanManagementIntent, attributes: LoanManagementAttributes) -> Dict[str, Any]:
        """Main entry point để lấy data cho loan management intent"""
        if not attributes.customer_code:
            return {"intent": intent.value, "success": False, "customer_code": "UNKNOWN",
                   "error": "Thiếu mã khách hàng", "formatted_data": "Có lỗi xảy ra: Thiếu mã khách hàng"}

        customer_code = attributes.customer_code
        LOGGER.info(f"Processing intent: {intent.value} for customer: {customer_code}")

        handlers = {
            LoanManagementIntent.GET_ALL_LD: self._handle_get_all_ld_intent,
            LoanManagementIntent.GET_LD_INFO: lambda i, c: self._handle_ld_detail_intent(i, c, attributes.loan_id),
            LoanManagementIntent.GET_LD_PAYMENT_SCHEDULE: lambda i, c: self._handle_payment_schedule_intent(i, c, attributes),
            LoanManagementIntent.GET_TOTAL_OVERDUE_DEBT: self._handle_get_total_overdue_debt_intent,
            LoanManagementIntent.GET_AC_OVERDRAFT_LIST: self._handle_get_ac_overdraft_list_intent,
            LoanManagementIntent.OUT_OF_SCOPE: lambda i, c: {"intent": i.value, "success": True,
                "formatted_data": "Xin lỗi, yêu cầu của bạn không nằm trong phạm vi hỗ trợ về quản lý khoản vay. Vui lòng liên hệ hotline để được hỗ trợ tốt hơn."}
        }

        try:
            handler = handlers.get(intent)
            return await handler(intent, customer_code) if handler else {
                "intent": intent.value, "success": False, "customer_code": customer_code,
                "error": f"Intent không được hỗ trợ: {intent.value}",
                "formatted_data": f"Có lỗi xảy ra: Intent không được hỗ trợ: {intent.value}"
            }
        except Exception as e:
            LOGGER.error(f"Error processing intent {intent.value}: {str(e)}")
            return {"intent": intent.value, "success": False, "customer_code": customer_code,
                   "error": str(e), "formatted_data": f"Có lỗi xảy ra: {str(e)}"}

    async def _handle_ld_detail_intent(self, intent: LoanManagementIntent, customer_code: str, loan_id: Optional[str]) -> Dict[str, Any]:
        """Handle LD detail intent with loan selection if needed"""
        if not loan_id:
            return await self._handle_loan_selection(intent, customer_code)
        return await self._handle_get_ld_info_intent(intent, customer_code, loan_id)

    async def _handle_payment_schedule_intent(self, intent: LoanManagementIntent, customer_code: str, attributes: LoanManagementAttributes) -> Dict[str, Any]:
        """Handle payment schedule intent with loan selection if needed"""
        if not attributes.loan_id:
            return await self._handle_loan_selection(intent, customer_code)
        return await self._handle_get_ld_payment_schedule_intent(intent, customer_code, attributes.loan_id,
                                                                 attributes.start_date, attributes.end_date)

    async def _handle_loan_selection(self, intent: LoanManagementIntent, customer_code: str) -> Dict[str, Any]:
        """Handle loan selection logic"""
        loan_selection_result = await self._get_available_loan_ids_for_selection(customer_code)
        if loan_selection_result["status"] == "error":
            return {"intent": intent.value, "success": False, "customer_code": customer_code,
                   "error": loan_selection_result["message"], "formatted_data": f"Có lỗi xảy ra: {loan_selection_result['message']}"}
        return self._create_loan_selection_result(intent, customer_code, loan_selection_result)

    async def _handle_get_all_ld_intent(self, intent: LoanManagementIntent, customer_code: str) -> Dict[str, Any]:
        """Xử lý intent lấy danh sách khoản vay LD"""
        ld_response, pd_response = await asyncio.gather(
            self._call_ld_list_api(customer_code),
            self._call_overdue_debt_api(customer_code)
        )

        if ld_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, ld_response.get("error", "Lỗi API"))
        if pd_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, pd_response.get("error", "Lỗi API"))

        processed_data = self._process_grouped_loan_data(ld_response, pd_response, customer_code)

        overdue_summary = processed_data.get("overdueSummary", {})

        return {
            "intent": intent.value,
            "success": True,
            "customer_code": customer_code,
            "formatted_data": self._format_grouped_loan_data(processed_data, customer_code),
            "overdue_summary": overdue_summary,
            "has_overdue_debt": overdue_summary.get("totalOverdueDebt", 0) > 0
        }

    async def _handle_get_ld_info_intent(self, intent: LoanManagementIntent, customer_code: str, loan_id: str) -> Dict[str, Any]:
        """Xử lý intent lấy thông tin chi tiết hợp đồng LD"""
        ld_response, pd_response = await asyncio.gather(
            self._call_ld_list_api(customer_code),
            self._call_overdue_debt_api(customer_code)
        )

        if ld_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, ld_response.get("error", "Lỗi API"))

        ld_data = ld_response.get("data") or []
        pd_data = pd_response.get("data") or [] if pd_response.get("status") == API_SUCCESS_STATUS else []

        loan_detail = next((loan for loan in ld_data if loan.get("lDID") == loan_id), None)
        if loan_detail:
            processed_detail = self._process_ld_detail(loan_detail, pd_data, customer_code, loan_id)
        else:
            pd_detail = next((pd for pd in pd_data if len(pd.get("PdId", "")) > 2 and pd.get("PdId", "")[2:] == loan_id), None)
            if not pd_detail:
                return self._error_result(intent, customer_code, f"Không tìm thấy khoản vay {loan_id}")
            processed_detail = self._process_pd_as_loan_detail(pd_detail, customer_code, loan_id)

        return {
            "intent": intent.value, "success": True, "customer_code": customer_code, "loan_id": loan_id,
            "formatted_data": self._format_ld_detail_data(processed_detail, customer_code, loan_id)
        }

    async def _handle_get_ld_payment_schedule_intent(self, intent: LoanManagementIntent, customer_code: str,
                                                     loan_id: str, start_date: Optional[str] = None,
                                                     end_date: Optional[str] = None) -> Dict[str, Any]:
        """Xử lý intent lấy lịch thanh toán khoản vay LD"""
        ld_list_response = await self._call_ld_list_api(customer_code)
        if ld_list_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, ld_list_response.get("error", "Lỗi API"))

        available_loan_ids = [loan.get("lDID") for loan in ld_list_response.get("data") or [] if loan.get("lDID")]
        if loan_id not in available_loan_ids:
            formatted_message = f"Không tìm thấy khoản vay {loan_id} trong danh sách khoản vay của khách hàng {customer_code}."
            if available_loan_ids:
                formatted_message += f"\n🏦 Danh sách khoản vay hiện tại:\n"
                formatted_message += "\n".join(f"   {i}. {lid}" for i, lid in enumerate(available_loan_ids, 1))
                formatted_message += "\nVui lòng chọn một trong các khoản vay trên."

            return {
                "intent": intent.value, "success": False, "customer_code": customer_code, "loan_id": loan_id,
                "formatted_data": formatted_message, "available_loans": available_loan_ids
            }

        if not start_date or not end_date:
            today = datetime.now()
            start_date, end_date = today.strftime("%Y%m%d"), (today + timedelta(days=365)).strftime("%Y%m%d")

        api_response = await self._call_ld_payment_schedule_api(customer_code, loan_id, start_date, end_date)
        if api_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, api_response.get("error", "Lỗi API"))

        processed_data = self._process_ld_payment_response(api_response, customer_code, loan_id)
        return {
            "intent": intent.value, "success": True, "customer_code": customer_code, "loan_id": loan_id,
            "formatted_data": self._format_ld_payment_data(processed_data, customer_code, loan_id),
            "date_range": f"{start_date} to {end_date}", "data_type": "payment_schedule"
        }

    async def _handle_get_total_overdue_debt_intent(self, intent: LoanManagementIntent, customer_code: str) -> Dict[str, Any]:
        """Xử lý intent lấy tổng nợ quá hạn"""
        ld_response, pd_response = await asyncio.gather(
            self._call_ld_list_api(customer_code),
            self._call_overdue_debt_api(customer_code)
        )

        for response in [ld_response, pd_response]:
            if response.get("status") != API_SUCCESS_STATUS:
                return self._error_result(intent, customer_code, response.get("error", "Lỗi API"))

        processed_data = self._calculate_total_overdue_debt(ld_response, pd_response, customer_code)
        return {
            "intent": intent.value, "success": True, "customer_code": customer_code,
            "formatted_data": self._format_overdue_debt_data(processed_data, customer_code)
        }

    async def _handle_get_ac_overdraft_list_intent(self, intent: LoanManagementIntent, customer_code: str) -> Dict[str, Any]:
        """Xử lý intent lấy danh sách khoản vay thấu chi AC"""
        api_response = await self._call_ac_overdraft_list_api(customer_code)
        if api_response.get("status") != API_SUCCESS_STATUS:
            return self._error_result(intent, customer_code, api_response.get("error", "Lỗi API"))

        processed_data = self._process_ac_overdraft_response(api_response, customer_code)
        return {
            "intent": intent.value, "success": True, "customer_code": customer_code,
            "formatted_data": self._format_ac_overdraft_data(processed_data, customer_code),
            "overdraft_count": len(api_response.get("data") or [])
        }

    @safe_api_call
    async def _call_ld_list_api(self, customer_code: str) -> Dict[str, Any]:
        return await self._make_api_call({"kind": "ld_list", "customerId": customer_code})

    @safe_api_call
    async def _call_ld_payment_schedule_api(self, customer_code: str, loan_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._make_api_call({
            "kind": "repayment", "ldId": loan_id, "startDate": start_date, "endDate": end_date
        })

    @safe_api_call
    async def _call_overdue_debt_api(self, customer_code: str) -> Dict[str, Any]:
        return await self._make_api_call({"kind": "overdue_debt", "customerId": customer_code})

    @safe_api_call
    async def _call_ac_overdraft_list_api(self, customer_code: str) -> Dict[str, Any]:
        return await self._make_api_call({"kind": "overdraft_list", "customerId": customer_code})

    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """API caller với error handling"""
        LOGGER.info(f"API call: {payload.get('kind', 'unknown')}")

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.ld_api_url, json=payload, headers={'Content-Type': 'application/json'}) as response:
                if response.status == API_SUCCESS_STATUS:
                    response_text = await response.text()
                    try:
                        return json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError as e:
                        return {"status": 500, "error": f"Invalid JSON: {str(e)}"}
                return {"status": response.status, "error": f"HTTP {response.status}"}

    def _process_grouped_loan_data(self, ld_response: Dict[str, Any], pd_response: Dict[str, Any],
                                   customer_code: str) -> Dict[str, Any]:
        """Process grouped loan data"""
        pd_data = pd_response.get("data") or []
        ld_data = ld_response.get("data") or []
        pd_mapping = {pd.get("PdId", "")[2:]: pd for pd in pd_data if len(pd.get("PdId", "")) > 2}

        active_ld_ids = set()
        all_loans = []

        # NEW: Thêm variables để tính tổng overdue
        total_overdue_debt = 0
        total_overdue_principal = 0
        total_overdue_interest_penalty = 0
        overdue_loan_count = 0
        max_overdue_days_across_all = 0

        # Process active LD
        for loan in ld_data:
            loan_id = loan.get("lDID", "")
            active_ld_ids.add(loan_id)

            processed_loan = self._process_single_loan(loan)
            pd_record = pd_mapping.get(loan_id)

            # Enhanced overdue processing
            overdue_amount = self._safe_convert(pd_record.get("TotOverdueAmt", "0"), "amount") if pd_record else 0
            overdue_days = pd_record.get("MaxPDDays", "0") if pd_record else "0"

            # NEW: Chi tiết breakdown overdue cho từng loan
            overdue_detail = None
            if pd_record and overdue_amount > 0:
                principal_overdue = self._safe_convert(pd_record.get("PRAmountTotal", "0"), "amount")
                interest_overdue = self._safe_convert(pd_record.get("INAmountTotal", "0"), "amount")
                penalty_overdue = (self._safe_convert(pd_record.get("PEAmountTotal", "0"), "amount") +
                                   self._safe_convert(pd_record.get("PSAmountTotal", "0"), "amount"))

                overdue_detail = {
                    "principalAmount": principal_overdue,
                    "interestAmount": interest_overdue,
                    "penaltyAmount": penalty_overdue,
                    "totalAmount": overdue_amount
                }

                # NEW: Tích lũy tổng
                total_overdue_debt += overdue_amount
                total_overdue_principal += principal_overdue
                total_overdue_interest_penalty += interest_overdue + penalty_overdue
                overdue_loan_count += 1
                max_overdue_days_across_all = max(max_overdue_days_across_all, int(overdue_days or "0"))

            processed_loan.update({
                "hasPdRecord": bool(pd_record),
                "totalOverdueAmt": overdue_amount,
                "maxOverdueDays": overdue_days,
                "overdueDetail": overdue_detail  # NEW field
            })

            category, sub_product = self._extract_product_info(loan, pd_data, loan_id)
            processed_loan.update({
                "productName": self._get_product_name_from_mapping(category, sub_product),
                "category": category, "subProduct": sub_product
            })
            all_loans.append(processed_loan)

        # Process PD without active LD (full overdue debts)
        for pd in pd_data:
            pd_id = pd.get("PdId", "")
            if len(pd_id) > 2 and pd_id[2:] not in active_ld_ids:
                virtual_loan = self._create_virtual_loan_from_pd(pd, pd_id[2:])
                all_loans.append(virtual_loan)

                # NEW: Add full overdue to totals
                overdue_amount = virtual_loan.get("totalOverdueAmt", 0)
                if overdue_amount > 0:
                    total_overdue_debt += overdue_amount
                    overdue_loan_count += 1
                    max_overdue_days_across_all = max(max_overdue_days_across_all,
                                                      int(virtual_loan.get("maxOverdueDays", "0")))

        # NEW: Thêm overdue summary vào return
        return {
            "customerCode": customer_code,
            "loans": all_loans,
            "loanCount": len(all_loans),
            "overdueSummary": {
                "totalOverdueDebt": total_overdue_debt,
                "totalOverduePrincipal": total_overdue_principal,
                "totalOverdueInterestPenalty": total_overdue_interest_penalty,
                "overdueLoansCount": overdue_loan_count,
                "maxOverdueDaysAcrossAll": str(max_overdue_days_across_all)
            }
        }

    def _process_single_loan(self, loan: Dict[str, Any]) -> Dict[str, Any]:
        """Process thông tin từ API response"""
        drawdown_info = loan.get("drawdownInformation", {})

        return {
            "loanId": loan.get("lDID", ""),
            "customerId": loan.get("customerId", ""),
            "status": loan.get("status", ""),
            "recordStatus": loan.get("recordStatus", ""),
            "amount": self._safe_convert(loan.get("amount", "0"), "amount"),
            "currency": loan.get("currency", DEFAULT_CURRENCY),
            "interestRate": self._extract_interest_rate_from_object(loan.get("interestInfo", {})),
            "approveAmount": self._safe_convert(loan.get("approveAmount", "0"), "amount"),
            "outsAccruedInt": self._safe_convert(loan.get("outsAccruedInt", "0"), "amount"),
            "totalAmtToRepay": self._safe_convert(loan.get("totalAmtToRepay", "0"), "amount"),
            "totalOverdueAmt": self._safe_convert(loan.get("overDueAmountInfo", {}).get("totalOverdueAmt", "0"), "amount"),
            "valueDate": self._safe_convert(loan.get("valueDate", ""), "date"),
            "finMatDate": self._safe_convert(loan.get("finMatDate", ""), "date"),
            "nextPrincipalRepayDate": self._safe_convert(loan.get("nextPrincipalRepayDate", ""), "date"),
            "nextInterestRepayDate": self._safe_convert(loan.get("nextInterestRepayDate", ""), "date"),
            "origValDate": self._safe_convert(loan.get("origValDate", ""), "date"),
            "interestDueDate": self._safe_convert(loan.get("interestDueDate", ""), "datetime"),
            "nextPrincipalRepayAmount": self._safe_convert(loan.get("nextPrincipalRepayAmount", "0"), "amount"),
            "totalInterestAmount": self._safe_convert(loan.get("totInterestAmt", "0"), "amount"),
            "curMonthPrincipalRepayAmount": self._safe_convert(loan.get("curMonthPrincipalRepayAmount", "0"), "amount"),
            "curMonthInterestRepayAmount": self._safe_convert(loan.get("curMonthInterestRepayAmount", "0"), "amount"),
            "loanPurpose": loan.get("loanPurpose", DEFAULT_VALUE),
            "origPrincipalAmount": self._safe_convert(drawdown_info.get("rawdownIssuePrc", "0"), "amount") or self._safe_convert(loan.get("amount", "0"), "amount"),
            "drawdownAccount": drawdown_info.get("drawdownAccount", ""),
            "drawdownEntDate": self._safe_convert(drawdown_info.get("drawdownEntDate", ""), "date"),
            "drawdownNetAmt": self._safe_convert(drawdown_info.get("drawdownNetAmt", "0"), "amount"),
            "maxOverdueDays": loan.get("maxOverdueDays", "0"),
            "penaltyRate": loan.get("penaltyRate", "0")
        }

    def _process_ld_detail(self, loan_detail: Dict[str, Any], pd_data: List[Dict[str, Any]], customer_code: str,
                           loan_id: str) -> Dict[str, Any]:
        """Process LD detail"""
        processed_loan_data = self._process_single_loan(loan_detail)

        pd_mapping = {pd.get("PdId", "")[2:]: pd for pd in pd_data if len(pd.get("PdId", "")) > 2}
        pd_record = pd_mapping.get(loan_id)

        processed_loan_data.update({
            "hasPdRecord": bool(pd_record),
            "totalOverdueAmt": self._safe_convert(pd_record.get("TotOverdueAmt", "0"), "amount") if pd_record else 0,
            "maxOverdueDays": pd_record.get("MaxPDDays", "0") if pd_record else "0"
        })

        category, sub_product = self._extract_product_info(loan_detail, pd_data, loan_id)
        processed_loan_data.update({
            "productName": self._get_product_name_from_mapping(category, sub_product),
            "category": category, "subProduct": sub_product
        })

        return {"success": True, "data": processed_loan_data, "customer_code": customer_code, "loan_id": loan_id}

    def _process_pd_as_loan_detail(self, pd_detail: Dict[str, Any], customer_code: str, loan_id: str) -> Dict[str, Any]:
        """Process PD data thành loan detail format"""
        category, sub_product = pd_detail.get("Category", ""), pd_detail.get("SubProduct", "")
        return {
            "success": True,
            "data": {
                "loanId": loan_id, "customerId": pd_detail.get("CustomerId", ""), "status": "OVERDUE_CLOSED",
                "amount": 0, "currency": pd_detail.get("Currency", DEFAULT_CURRENCY),
                "totalOverdueAmt": self._safe_convert(pd_detail.get("TotOverdueAmt", "0"), "amount"),
                "productName": self._get_product_name_from_mapping(category, sub_product),
                "category": category, "subProduct": sub_product,
                "maxOverdueDays": pd_detail.get("MaxPDDays", "0"), "isPdOnly": True
            },
            "customer_code": customer_code, "loan_id": loan_id
        }

    def _process_ac_overdraft_response(self, api_response: Dict[str, Any], customer_code: str) -> Dict[str, Any]:
        """Process AC overdraft API response"""
        processed_overdrafts = []

        for overdraft in api_response.get("data") or []:
            balance_info = overdraft.get("balance", {})
            current_balance = self._safe_convert(balance_info.get("current", "0"), "amount")
            available = self._safe_convert(balance_info.get("available", "0"), "amount")
            overdraft_limit = self._safe_convert(balance_info.get("overDraftLimit", "0"), "amount")

            processed_overdraft = {
                "accountId": overdraft.get("acctId", ""),
                "accountName": overdraft.get("acctnName", ""),
                "accountShortName": overdraft.get("acctnShortName", ""),
                "customerName": overdraft.get("custName", ""),
                "productName": self._get_product_name_from_mapping(product_info_list=overdraft.get("productInfo", [])),
                "usedAmount": abs(current_balance) if current_balance < 0 else 0,
                "usableAmount": available,
                "overdueStatus": "Trong hạn",
                "interestRate": overdraft.get("interestRate", "0"),
                "openDate": self._safe_convert(overdraft.get("openDate", ""), "date"),
                "closeDate": self._safe_convert(overdraft.get("closeDate", ""), "date"),
                "overdraftLimit": overdraft_limit,
                "interestAccount": overdraft.get("interestLiquAcct", ""),
                "branchName": overdraft.get("branchInfo", {}).get("name", ""),
                "currentBalance": current_balance,
                "availableBalance": available,
                "limitDueDate": self._safe_convert(overdraft.get("overDraftLimitDueDate", ""), "date")
            }
            processed_overdrafts.append(processed_overdraft)

        return {"customerCode": customer_code, "overdrafts": processed_overdrafts, "overdraftCount": len(processed_overdrafts)}

    def _process_ld_payment_response(self, api_response: Dict[str, Any], customer_code: str, loan_id: str) -> Dict[str, Any]:
        """Process payment schedule response"""
        processed_payments = [
            {
                "dateSchedule": self._safe_convert(payment.get("dateSchedule", ""), "date"),
                "principalAmount": self._safe_convert(payment.get("principalAmount", "0"), "amount"),
                "interestAmount": self._safe_convert(payment.get("interestAmount", "0"), "amount"),
                "totalFees": self._safe_convert(payment.get("totalFees", "0"), "amount"),
                "totalPayment": self._safe_convert(payment.get("totalPayment", "0"), "amount"),
                "status": payment.get("status", ""),
                "actualPaymentDate": self._safe_convert(payment.get("actualPaymentDate", ""), "date")
            }
            for payment in api_response.get("data") or []
        ]
        return {"customerCode": customer_code, "loanId": loan_id, "payments": processed_payments, "paymentCount": len(processed_payments)}

    def _calculate_total_overdue_debt(self, ld_response: Dict[str, Any], pd_response: Dict[str, Any], customer_code: str) -> Dict[str, Any]:
        """Tính toán tổng nợ quá hạn - FIXED VERSION"""
        pd_data = pd_response.get("data") or []
        pd_mapping = {pd.get("PdId", "")[2:]: pd for pd in pd_data if len(pd.get("PdId", "")) > 2}

        active_ld_ids = {loan.get("lDID", "") for loan in ld_response.get("data") or []}

        partial_overdue_total = partial_overdue_principal = partial_overdue_interest_penalty = 0
        partial_overdue_debts = []

        # Process partial overdue (Active LD with PD record)
        for loan in ld_response.get("data") or []:
            loan_id = loan.get("lDID", "")
            if loan_id in pd_mapping:
                pd_record = pd_mapping[loan_id]

                amounts = {
                    "total": self._safe_convert(pd_record.get("TotOverdueAmt", "0"), "amount"),
                    "principal": self._safe_convert(pd_record.get("PRAmountTotal", "0"), "amount"),
                    "interest": self._safe_convert(pd_record.get("INAmountTotal", "0"), "amount"),
                    "penalty": (self._safe_convert(pd_record.get("PEAmountTotal", "0"), "amount") +
                                self._safe_convert(pd_record.get("PSAmountTotal", "0"), "amount"))
                }

                if amounts["total"] > 0:
                    partial_overdue_total += amounts["total"]
                    partial_overdue_principal += amounts["principal"]
                    partial_overdue_interest_penalty += amounts["interest"] + amounts["penalty"]

                    partial_overdue_debts.append({
                        "loanId": loan_id,
                        "productName": loan.get("productInformationType", {}).get("description", "Sản phẩm vay"),
                        "maxOverdueDays": pd_record.get("MaxPDDays", "0"),
                        "principalAmount": amounts["principal"],
                        "interestAmount": amounts["interest"],
                        "penaltyAmount": amounts["penalty"],
                        "totalAmount": amounts["total"]
                    })

        # Process full overdue (PD without active LD)
        full_overdue_total = full_overdue_principal = full_overdue_interest = full_overdue_penalty = 0
        full_overdue_debts = []

        for pd in pd_data:
            pd_id = pd.get("PdId", "")
            if len(pd_id) > 2 and pd_id[2:] not in active_ld_ids:
                amounts = {
                    "total": self._safe_convert(pd.get("TotOverdueAmt", "0"), "amount"),
                    "principal": self._safe_convert(pd.get("PRAmountTotal", "0"), "amount"),
                    "interest": self._safe_convert(pd.get("INAmountTotal", "0"), "amount"),
                    "penalty": (self._safe_convert(pd.get("PEAmountTotal", "0"), "amount") +
                               self._safe_convert(pd.get("PSAmountTotal", "0"), "amount"))
                }

                full_overdue_total += amounts["total"]
                full_overdue_principal += amounts["principal"]
                full_overdue_interest += amounts["interest"]
                full_overdue_penalty += amounts["penalty"]

                full_overdue_debts.append({
                    "pdId": pd_id,
                    "category": pd.get("Category", ""),
                    "subProduct": pd.get("SubProduct", ""),
                    "maxOverdueDays": pd.get("MaxPDDays", "0"),
                    "principalAmount": amounts["principal"],
                    "interestAmount": amounts["interest"],
                    "penaltyAmount": amounts["penalty"],
                    "totalAmount": amounts["total"]
                })

        return {
            "customerCode": customer_code,
            "totalOverdueDebt": partial_overdue_total + full_overdue_total,
            "totalPrincipal": partial_overdue_principal + full_overdue_principal,
            "totalInterestPenalty": partial_overdue_interest_penalty + full_overdue_interest + full_overdue_penalty,
            "partialOverdueDebts": partial_overdue_debts,
            "debts": full_overdue_debts
        }

    def _format_grouped_loan_data(self, processed_data: Dict[str, Any], customer_code: str) -> str:
        """Format grouped loan data"""
        loans = processed_data.get("loans", [])
        if not loans:
            return f"Khách hàng {customer_code} hiện tại không có khoản vay nào."

        # NEW: Thêm overdue summary header
        overdue_summary = processed_data.get("overdueSummary", {})
        total_overdue = overdue_summary.get("totalOverdueDebt", 0)

        result = f"📋 DANH SÁCH KHOẢN VAY - Khách hàng: {customer_code}\n"
        result += f"Tổng số khoản vay: {len(loans)}\n"

        # NEW: Hiển thị tổng overdue nếu có
        if total_overdue > 0:
            result += f"⚠️ TỔNG NỢ QUÁ HẠN: {total_overdue:,.0f} VND\n"
            result += f"📊 Số khoản vay có nợ quá hạn: {overdue_summary.get('overdueLoansCount', 0)}\n"
            result += f"📅 Số ngày quá hạn tối đa: {overdue_summary.get('maxOverdueDaysAcrossAll', '0')}\n"
        else:
            result += "✅ Không có nợ quá hạn\n"

        result += "\n"

        for i, loan in enumerate(loans, 1):
            loan_info = {
                "id": loan.get('loanId', DEFAULT_VALUE),
                "balance": loan.get('amount', 0),
                "currency": loan.get('currency', DEFAULT_CURRENCY),
                "rate": loan.get('interestRate', DEFAULT_VALUE),
                "product": loan.get('productName', 'Sản phẩm vay'),
                "overdue": loan.get('totalOverdueAmt', 0),
                "status": self._determine_loan_status(loan, loan.get('isPdOnly', False))
            }

            result += f"Khoản vay #{i}: {loan_info['id']}\n"
            result += f"   • Sản phẩm: {loan_info['product']}\n"
            result += f"   • Dư nợ: {loan_info['balance']:,.0f} {loan_info['currency']}\n"
            result += f"   • Lãi suất: {loan_info['rate']}%/năm\n"
            result += f"   • Trạng thái: {loan_info['status']}\n"

            if loan_info['overdue'] > 0:
                result += f"   • Số tiền quá hạn: {loan_info['overdue']:,.0f} {loan_info['currency']}\n"
                result += f"   • Số ngày quá hạn: {loan.get('maxOverdueDays', '0')}\n"

                # NEW: Chi tiết breakdown nếu có
                overdue_detail = loan.get('overdueDetail')
                if overdue_detail:
                    result += f"     - Gốc quá hạn: {overdue_detail['principalAmount']:,.0f} VND\n"
                    result += f"     - Lãi quá hạn: {overdue_detail['interestAmount']:,.0f} VND\n"
                    result += f"     - Phí phạt: {overdue_detail['penaltyAmount']:,.0f} VND\n"
            result += "\n"

        return result

    def _format_overdue_debt_data(self, processed_data: Dict[str, Any], customer_code: str) -> str:
        """Format overdue debt data"""
        total_debt = processed_data.get("totalOverdueDebt", 0)
        if total_debt == 0:
            return f"Khách hàng {customer_code} hiện tại không có nợ quá hạn."

        result = f"Tổng nợ quá hạn hiện tại của bạn là **{total_debt:,.0f} VND**.\n\nTrong đó:\n"

        # Format partial overdue debts
        for debt in processed_data.get("partialOverdueDebts", []):
            result += f"* {debt['loanId']} - {debt['productName']}\n"
            result += f"   * Tổng nợ quá hạn: {debt['totalAmount']:,.0f} VND\n"
            result += f"   * Gốc quá hạn: {debt['principalAmount']:,.0f} VND\n"
            result += f"   * Lãi, phí phạt quá hạn: {debt['interestAmount']:,.0f} VND\n"
            result += f"   * Số ngày quá hạn: {debt['maxOverdueDays']}\n"

        # Format full overdue debts
        for debt in processed_data.get("debts", []):
            product_name = self._get_product_name_from_mapping(str(debt.get('category', '')), str(debt.get('subProduct', '')))
            result += f"*{product_name}\n"
            result += f"   * Tổng số tiền quá hạn: {debt['totalAmount']:,.0f} VND\n"
            result += f"   * Số tiền gốc quá hạn: {debt['principalAmount']:,.0f} VND\n"
            result += f"   * Số tiền lãi quá hạn: {debt['interestAmount']:,.0f} VND\n"
            result += f"   * Số tiền phạt quá hạn: {debt['penaltyAmount']:,.0f} VND\n"
            result += f"   * Số ngày quá hạn: {debt['maxOverdueDays']}\n"

        return result

    def _format_ld_detail_data(self, processed_data: Dict[str, Any], customer_code: str, loan_id: str) -> str:
        """Format dữ liệu chi tiết khoản vay"""
        if not processed_data.get("success"):
            return f"Không thể lấy thông tin chi tiết khoản vay {loan_id}"

        loan = processed_data.get("data") or  {}
        if not loan:
            return f"Không tìm thấy thông tin khoản vay {loan_id}"

        info = {
            "balance": loan.get('amount', 0),
            "currency": loan.get('currency', DEFAULT_CURRENCY),
            "rate": loan.get('interestRate', DEFAULT_VALUE),
            "value_date": self._safe_convert(loan.get('valueDate', ''), 'date'),
            "mat_date": self._safe_convert(loan.get('finMatDate', ''), 'date'),
            "purpose": loan.get('loanPurpose', DEFAULT_VALUE),
            "overdue": loan.get('totalOverdueAmt', 0),
            "original": loan.get('origPrincipalAmount', loan.get('amount', 0)),
            "status": self._determine_loan_status(loan, loan.get('isPdOnly', False))
        }

        result = f"""📋 THÔNG TIN CHI TIẾT KHOẢN VAY: {loan_id}
        Số tiền vay ban đầu: {info['original']:,.0f} {info['currency']}
        Dư nợ hiện tại: {info['balance']:,.0f} {info['currency']}
        Trong hạn/Quá hạn: {info['status']}
        Lãi suất: {info['rate']}%/năm
        Ngày đăng ký: {info['value_date']}
        Ngày đáo hạn: {info['mat_date']}
        Mục đích khoản vay: {info['purpose']}
        
        ---
        
        THÔNG TIN GIẢI NGÂN:
        Tài khoản giải ngân: {loan.get('drawdownAccount', DEFAULT_VALUE)}
        Ngày giải ngân: {self._safe_convert(loan.get('drawdownEntDate', ''), 'date')}
        Số tiền giải ngân thực tế: {loan.get('drawdownNetAmt', 0):,.0f} {info['currency']}
        
        ---
        
        Kỳ thanh toán tiếp theo
        Ngày thanh toán gốc: {self._safe_convert(loan.get('nextPrincipalRepayDate', ''), 'date')}
        Số tiền gốc: {loan.get('nextPrincipalRepayAmount', 0):,.0f} {info['currency']}
        Ngày thanh toán lãi: {self._safe_convert(loan.get('nextInterestRepayDate', ''), 'date')}
        Tổng lãi phải trả: {loan.get('totalInterestAmount', 0):,.0f} {info['currency']}"""

        if info['overdue'] > 0:
            result += f"\n\n⚠️ THÔNG TIN QUÁ HẠN:\nSố tiền quá hạn: {info['overdue']:,.0f} {info['currency']}\nSố ngày quá hạn: {loan.get('maxOverdueDays', '0')}"

        return result

    def _format_ld_payment_data(self, processed_data: Dict[str, Any], customer_code: str, loan_id: str) -> str:
        """Format dữ liệu payment schedule"""
        payments = processed_data.get("payments", [])
        if not payments:
            return f"Không có dữ liệu lịch thanh toán cho khoản vay {loan_id}"

        result = f"📅 LỊCH THANH TOÁN KHOẢN VAY: {loan_id}\nKhách hàng: {customer_code}\nTổng số kỳ: {len(payments)}\n\n"

        for i, payment in enumerate(payments, 1):
            result += f"Kỳ {i} - {payment['dateSchedule']}:\n"
            result += f"   • Tiền gốc: {payment['principalAmount']:,.0f} VND\n"
            result += f"   • Tiền lãi: {payment['interestAmount']:,.0f} VND\n"
            if payment['totalFees'] > 0:
                result += f"   • Phí: {payment['totalFees']:,.0f} VND\n"
            result += f"   • Tổng thanh toán: {payment['totalPayment']:,.0f} VND\n"
            result += f"   • Trạng thái: {payment['status']}\n"
            if payment.get('actualPaymentDate'):
                result += f"   • Ngày TT thực tế: {payment['actualPaymentDate']}\n"
            result += "\n"

        return result

    def _format_ac_overdraft_data(self, processed_data: Dict[str, Any], customer_code: str) -> str:
        """Format AC overdraft data"""
        overdrafts = processed_data.get("overdrafts", [])
        if not overdrafts:
            return f"Khách hàng {customer_code} hiện tại không có khoản thấu chi nào."

        result = f"💳 DANH SÁCH KHOẢN VAY THẤU CHI AC\n"
        result += f"Khách hàng: {customer_code}\n"
        result += f"Tổng số tài khoản thấu chi: {len(overdrafts)}\n\n"

        for i, overdraft in enumerate(overdrafts, 1):
            result += f"🏦 TÀI KHOẢN {i}: {overdraft.get('accountId', '')}\n"
            result += f"   • Tên tài khoản: {overdraft.get('accountName', '')}\n"

            if overdraft.get('accountShortName'):
                result += f"   • Tên rút gọn: {overdraft.get('accountShortName', '')}\n"

            if overdraft.get('customerName'):
                result += f"   • Chủ tài khoản: {overdraft.get('customerName', '')}\n"

            result += f"   • Sản phẩm: {overdraft.get('productName', '')}\n"
            result += f"   • Hạn mức thấu chi: {overdraft.get('overdraftLimit', 0):,.0f} VND\n"
            result += f"   • Số tiền đã sử dụng: {overdraft.get('usedAmount', 0):,.0f} VND\n"
            result += f"   • Số tiền có thể sử dụng: {overdraft.get('usableAmount', 0):,.0f} VND\n"
            result += f"   • Số dư hiện tại: {overdraft.get('currentBalance', 0):,.0f} VND\n"
            result += f"   • Lãi suất: {overdraft.get('interestRate', '0')}%\n"
            if overdraft.get('openDate'):
                result += f"   • Ngày bắt đầu: {overdraft.get('openDate', '')}\n"
            if overdraft.get('closeDate'):
                result += f"   • Ngày kết thúc: {overdraft.get('closeDate', '')}\n"
            if overdraft.get('interestAccount'):
                result += f"   • Tài khoản thanh toán nợ: {overdraft.get('interestAccount', '')}\n"

            result += f"   • Trạng thái quá hạn: {overdraft.get('overdueStatus', 'Trong hạn')}\n"
            result += "\n"

        return result

    def _get_product_name_from_mapping(self, category: str = "", sub_product: str = "", product_info_list: Optional[List[Dict]] = None) -> str:
        """Get product name từ mapping file hoặc product info list"""
        if product_info_list:
            category_info = next((info for info in product_info_list if info.get("type") == "Category"), {})
            sub_product_info = next((info for info in product_info_list if info.get("type") == "SubProduct"), {})

            if not category_info:
                return "Thấu chi tài khoản"

            return self._get_mapped_product_name(category_info.get("id", ""), sub_product_info.get("id", ""), "Thấu chi tài khoản")

        return self._get_mapped_product_name(category, sub_product, f"Sản phẩm vay {category}")

    def _extract_product_info(self, loan_data: Dict[str, Any], pd_data: List[Dict], loan_id: str) -> Tuple[str, str]:
        """Extract category và subProduct từ PD hoặc LD data"""
        pd_match = next((pd for pd in pd_data if len(pd.get("PdId", "")) > 2 and pd.get("PdId", "")[2:] == loan_id), None)
        if pd_match:
            return pd_match.get("Category", ""), pd_match.get("SubProduct", "")

        product_info_type = loan_data.get("productInformationType", {})
        return product_info_type.get("category", ""), loan_data.get("subProduct", "") if product_info_type else ("", "")

    def _create_virtual_loan_from_pd(self, pd: Dict[str, Any], loan_id: str) -> Dict[str, Any]:
        """Create virtual loan từ PD data"""
        category, sub_product = pd.get("Category", ""), pd.get("SubProduct", "")
        overdue_amounts = self._calculate_overdue_amounts_from_pd(pd)

        virtual_loan = {
            "loanId": loan_id,
            "customerId": pd.get("CustomerId", ""),
            "status": "OVERDUE_CLOSED",
            "recordStatus": "CLOSED",
            "amount": 0,
            "currency": pd.get("Currency", DEFAULT_CURRENCY),
            "interestRate": DEFAULT_VALUE,
            "productName": self._get_product_name_from_mapping(category, sub_product),
            "category": category,
            "subProduct": sub_product,
            "totalOverdueAmt": overdue_amounts["total"],
            "maxOverdueDays": pd.get("MaxPDDays", "0"),
            "isPdOnly": True,
            "hasPdRecord": True
        }

        # NEW: Thêm overdue detail cho virtual loan
        if overdue_amounts["total"] > 0:
            virtual_loan["overdueDetail"] = {
                "principalAmount": overdue_amounts["principal"],
                "interestAmount": overdue_amounts["interest"],
                "penaltyAmount": overdue_amounts["penalty"],
                "totalAmount": overdue_amounts["total"]
            }

        return virtual_loan

    def _extract_interest_rate_from_object(self, interest_info: Dict[str, Any]) -> str:
        """Extract lãi suất từ interestInfo object"""
        if not interest_info or not isinstance(interest_info, dict):
            return DEFAULT_VALUE

        try:
            rate = float(interest_info.get("interestRate", "0") or "0")
            spread = float(interest_info.get("interestSpread", "0") or "0")
            return f"{rate + spread:.1f}" if rate > 0 else DEFAULT_VALUE
        except (ValueError, TypeError):
            return DEFAULT_VALUE

    def _error_result(self, intent: LoanManagementIntent, customer_code: str, error_msg: str) -> Dict[str, Any]:
        """Tạo kết quả lỗi"""
        return {
            "intent": intent.value, "success": False, "customer_code": customer_code,
            "error": error_msg, "formatted_data": f"Có lỗi xảy ra: {error_msg}"
        }

    async def _get_available_loan_ids_for_selection(self, customer_code: str) -> Dict[str, Any]:
        """Lấy danh sách loan_id available cho customer để hiển thị lựa chọn"""
        try:
            ld_list_response, pd_response = await asyncio.gather(
                self._call_ld_list_api(customer_code),
                self._call_overdue_debt_api(customer_code)
            )

            if ld_list_response.get("status") != API_SUCCESS_STATUS:
                return {"status": "error", "message": ld_list_response.get("error", "Không thể lấy danh sách khoản vay")}

            ld_data = ld_list_response.get("data") or []
            pd_data = pd_response.get("data") or [] if pd_response.get("status") == API_SUCCESS_STATUS else []

            pd_mapping = {pd.get("PdId", "")[2:]: pd for pd in pd_data if len(pd.get("PdId", "")) > 2}

            available_loan_ids = []
            loan_details = []
            active_ld_ids = set()

            # Process LD data
            for loan in ld_data:
                loan_id = loan.get("lDID")
                if loan_id:
                    active_ld_ids.add(loan_id)
                    available_loan_ids.append(loan_id)

                    has_pd_record = loan_id in pd_mapping
                    category, sub_product = self._extract_product_info(loan, pd_data, loan_id)

                    loan_details.append({
                        "loan_id": loan_id,
                        "amount": loan.get("amount", 0),
                        "currency": loan.get("currency", DEFAULT_CURRENCY),
                        "product_name": self._get_product_name_from_mapping(category, sub_product),
                        "status": "Quá hạn một phần" if has_pd_record else "Trong hạn",
                        "overdue_amount": self._safe_convert(pd_mapping[loan_id].get("TotOverdueAmt", "0"), "amount") if has_pd_record else 0,
                        "source": "LD"
                    })

            # Process PD data (full overdue)
            for pd in pd_data:
                pd_id = pd.get("PdId", "")
                if len(pd_id) > 2 and pd_id[2:] not in active_ld_ids:
                    related_ld_id = pd_id[2:]
                    available_loan_ids.append(related_ld_id)

                    loan_details.append({
                        "loan_id": related_ld_id,
                        "amount": 0,
                        "currency": pd.get("Currency", DEFAULT_CURRENCY),
                        "product_name": self._get_product_name_from_mapping(pd.get("Category", ""), pd.get("SubProduct", "")),
                        "status": "Quá hạn toàn phần",
                        "overdue_amount": self._safe_convert(pd.get("TotOverdueAmt", "0"), "amount"),
                        "source": "PD"
                    })

            return {"status": "success", "available_loan_ids": available_loan_ids, "loan_details": loan_details}

        except Exception as e:
            LOGGER.error(f"Error getting available loan IDs: {str(e)}")
            return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}

    def _create_loan_selection_result(self, intent: LoanManagementIntent, customer_code: str, loan_selection_data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo response hiển thị danh sách loan_id để khách hàng lựa chọn"""
        available_loan_ids = loan_selection_data.get("available_loan_ids", [])
        loan_details = loan_selection_data.get("loan_details", [])

        if not available_loan_ids:
            return {
                "intent": intent.value, "success": False, "customer_code": customer_code,
                "error": "Không có khoản vay",
                "formatted_data": f"Khách hàng {customer_code} hiện tại không có khoản vay nào.",
                "response_type": "no_loans_available"
            }

        formatted_message = f"🏦 Quý khách vui lòng chọn khoản vay mong muốn tra cứu trong danh sách khoản vay:\n\n"

        for i, loan_detail in enumerate(loan_details, 1):
            try:
                amount_formatted = f"{float(loan_detail['amount']):,.0f}" if loan_detail["amount"] else "0"
            except (ValueError, TypeError):
                amount_formatted = str(loan_detail["amount"]) if loan_detail["amount"] else "0"

            formatted_message += f"   {i}. {loan_detail['loan_id']}\n"
            formatted_message += f"      • Sản phẩm: {loan_detail['product_name']}\n"
            formatted_message += f"      • Dư nợ: {amount_formatted} {loan_detail['currency']}\n"
            formatted_message += f"      • Trạng thái: {loan_detail['status']}\n"

            if loan_detail.get("overdue_amount", 0) > 0:
                formatted_message += f"      • Số tiền quá hạn: {loan_detail['overdue_amount']:,.0f} {loan_detail['currency']}\n"
            formatted_message += "\n"

        return {
            "intent": intent.value, "success": True, "customer_code": customer_code,
            "loan_id": None, "available_loans": available_loan_ids,
            "loan_details": loan_details, "formatted_data": formatted_message,
            "response_type": "loan_selection", "requires_selection": True,
            "should_process_with_llm": False
        }

    def _determine_loan_status(self, loan: Dict[str, Any], is_from_pd_only: bool = False) -> str:
        """Xác định trạng thái khoản vay"""
        return "Quá hạn toàn phần" if is_from_pd_only else ("Quá hạn một phần" if loan.get('hasPdRecord', False) else "Trong hạn")

    def _get_mapped_product_name(self, category: str, sub_product: str, default_name: str) -> str:
        """Get product name từ mapping file với category và sub_product"""
        mapping_file = "beechat_khcn/utils/loan_product.json"

        if not os.path.exists(mapping_file):
            LOGGER.warning(f"Mapping file not found: {mapping_file}")
            return default_name

        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
        except Exception as e:
            LOGGER.warning(f"Error reading mapping file: {e}")
            return default_name

        if not isinstance(mapping_data, list):
            return default_name

        category_matches = [item for item in mapping_data if str(item.get("category", "")) == category]
        if not category_matches:
            return default_name

        extracted_sub_product = "" if sub_product and "-" in sub_product else sub_product
        exception_sub_ids = ["460", "387", "386"]

        if extracted_sub_product:
            if extracted_sub_product not in exception_sub_ids:
                # Exact match
                exact_match = next((item for item in category_matches
                                  if str(item.get("sub_productid", "")) == extracted_sub_product), None)
                if exact_match:
                    return exact_match.get("description", default_name)

                # Exception logic match
                exception_match = next((item for item in category_matches
                                      if "trừ sub" in str(item.get("sub_productid", "")) and
                                      all(sub_id in str(item.get("sub_productid", "")) for sub_id in exception_sub_ids)), None)
                if exception_match:
                    return exception_match.get("description", default_name)
            else:
                # Handle exception sub_ids
                exception_match = next((item for item in category_matches
                                      if str(item.get("sub_productid", "")) == extracted_sub_product), None)
                if exception_match:
                    return exception_match.get("description", default_name)

        # Default match
        default_match = next((item for item in category_matches if item.get("sub_productid") is None), None)
        return default_match.get("description", default_name) if default_match else (category_matches[0].get("description", default_name) if category_matches else default_name)

    def _calculate_overdue_amounts_from_pd(self, pd_record: Dict[str, Any]) -> Dict[str, Any]:
        """Private helper: Calculate overdue breakdown from PD record"""
        if not pd_record:
            return {"total": 0, "principal": 0, "interest": 0, "penalty": 0}

        return {
            "total": self._safe_convert(pd_record.get("TotOverdueAmt", "0"), "amount"),
            "principal": self._safe_convert(pd_record.get("PRAmountTotal", "0"), "amount"),
            "interest": self._safe_convert(pd_record.get("INAmountTotal", "0"), "amount"),
            "penalty": (self._safe_convert(pd_record.get("PEAmountTotal", "0"), "amount") +
                        self._safe_convert(pd_record.get("PSAmountTotal", "0"), "amount"))
        }


async def main():
    """Test function đơn giản cho LoanManagementApiService"""
    print("🚀 Starting LoanManagementApiService Test Suite...")
    print("=" * 80)

    service = LoanManagementApiService()
    test_customers = {"default": "6066617", "alternative": "6066617", "overdraft_ac": "6066617"}

    tests = [
        ("GET_ALL_LD", LoanManagementAttributes(customer_code=test_customers["default"])),
        ("GET_LD_INFO", LoanManagementAttributes(customer_code=test_customers["default"], loan_id="LD2610786090")),
        ("GET_LD_PAYMENT_SCHEDULE", LoanManagementAttributes(customer_code=test_customers["default"], loan_id="LD2610786090", start_date="20260221", end_date="20280321")),
        ("GET_AC_OVERDRAFT_LIST", LoanManagementAttributes(customer_code=test_customers["overdraft_ac"]))
    ]

    for i, (intent_name, attributes) in enumerate(tests, 1):
        print(f"\n📋 TEST {i}: {intent_name} Intent")
        print("-" * 50)
        try:
            intent = getattr(LoanManagementIntent, intent_name)
            result = await service.get_data_for_intent(intent, attributes)
            print(f"✅ Success: {result.get('success')}")
            if result.get('success'):
                print("📄 OUTPUT:")
                print(result.get('formatted_data', ''))
            else:
                print(f"Error: {result.get('error')}")
        except Exception as e:
            print(f"💥 Exception: {str(e)}")

    print("\n🏁 TEST SUITE COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    print("🚀 Starting LoanManagementApiService Test Suite...")
    asyncio.run(main())