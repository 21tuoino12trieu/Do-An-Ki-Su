from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class PaymentMethodIntent(str, Enum):
    INTENT_TRANSFER_FROM_MB_ACCOUNT = "INTENT_TRANSFER_FROM_MB_ACCOUNT"
    INTENT_TRANSFER_FROM_OTHER_BANK = "INTENT_TRANSFER_FROM_OTHER_BANK"
    INTENT_CASH_DEPOSIT_AT_CRM = "INTENT_CASH_DEPOSIT_AT_CRM"
    INTENT_CASH_DEPOSIT_AT_BRANCH = "INTENT_CASH_DEPOSIT_AT_BRANCH"
    INTENT_MAIN = "INTENT_MAIN"
    INTENT_CHITCHAT = "INTENT_CHITCHAT"

    def __str__(self):
        return self.value


class RoleIntent(str, Enum):
    INTENT_MB_Y__OTHER_BANK_Y = "INTENT_MB_Y__OTHER_BANK_Y"
    INTENT_MB_Y__OTHER_BANK_N = "INTENT_MB_Y__OTHER_BANK_N"
    INTENT_MB_N__OTHER_BANK_Y = "INTENT_MB_N__OTHER_BANK_Y"
    INTENT_MB_N__OTHER_BANK_N = "INTENT_MB_N__OTHER_BANK_N"
    INTENT_MAIN = "INTENT_MAIN"

    def __str__(self):
        return self.value


class PaymentRouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: PaymentMethodIntent


class RoleRouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: RoleIntent


class FieldValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_present: bool = Field(..., description="Khách hàng có cung cấp hay chưa")
    is_valid_format: bool = Field(..., description="Thông tin có đúng định dạng hay không")
    error: Optional[str] = Field(None, description="Thông báo lỗi nếu có")


class MbTransferExtracted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mb_account_number: Optional[str] = Field(None, description="Số tài khoản MB thực hiện giao dịch")
    statement_payment_account_number: Optional[str] = Field(None, description="Số tài khoản được thanh toán sao kê")
    card_first4: Optional[str] = Field(None, description="4 số đầu thẻ")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    card_id: Optional[str] = Field(None, description="ID thẻ")
    transaction_date: Optional[str] = Field(None, description="Ngày giao dịch")
    transaction_amount: Optional[float] = Field(None, description="Số tiền giao dịch")


class MbTransferValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mb_account_number: FieldValidation
    statement_payment_account_number: FieldValidation
    card_first4: FieldValidation
    card_last4: FieldValidation
    card_id: FieldValidation
    transaction_date: FieldValidation
    transaction_amount: FieldValidation


class MbTransferExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_data: MbTransferExtracted
    validation: MbTransferValidation
    is_complete: bool
    missing_fields: List[str]


class OtherBankExtracted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_number: Optional[str] = Field(None, description="Số tài khoản hoặc thông tin thẻ")
    card_first4: Optional[str] = Field(None, description="4 số đầu thẻ")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    card_id: Optional[str] = Field(None, description="ID thẻ")
    transaction_date: Optional[str] = Field(None, description="Ngày giao dịch")
    transaction_amount: Optional[float] = Field(None, description="Số tiền giao dịch")
    transaction_id: Optional[str] = Field(None, description="Mã giao dịch")
    sender_bank: Optional[str] = Field(None, description="Ngân hàng chuyển")
    transfer_method: Optional[str] = Field(None, description="Hình thức chuyển")


class OtherBankValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_number: FieldValidation
    card_first4: FieldValidation
    card_last4: FieldValidation
    card_id: FieldValidation
    transaction_date: FieldValidation
    transaction_amount: FieldValidation
    transaction_id: FieldValidation
    sender_bank: FieldValidation
    transfer_method: FieldValidation


class OtherBankExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_data: OtherBankExtracted
    validation: OtherBankValidation
    is_complete: bool
    missing_fields: List[str]


class CrmExtracted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_first4: Optional[str] = Field(None, description="4 số đầu thẻ")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    card_id: Optional[str] = Field(None, description="ID thẻ")
    transaction_date: Optional[str] = Field(None, description="Ngày giao dịch")
    transaction_amount: Optional[float] = Field(None, description="Số tiền giao dịch")
    crm_machine_id: Optional[str] = Field(None, description="Mã hoặc địa chỉ máy CRM")


class CrmValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_first4: FieldValidation
    card_last4: FieldValidation
    card_id: FieldValidation
    transaction_date: FieldValidation
    transaction_amount: FieldValidation
    crm_machine_id: FieldValidation


class CrmExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_data: CrmExtracted
    validation: CrmValidation
    is_complete: bool
    missing_fields: List[str]


class BranchExtracted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_first4: Optional[str] = Field(None, description="4 số đầu thẻ")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    card_id: Optional[str] = Field(None, description="ID thẻ")
    transaction_date: Optional[str] = Field(None, description="Ngày giao dịch")
    transaction_amount: Optional[float] = Field(None, description="Số tiền giao dịch")
    branch_location: Optional[str] = Field(None, description="Tên/Địa chỉ CN/PGD MB")


class BranchValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_first4: FieldValidation
    card_last4: FieldValidation
    card_id: FieldValidation
    transaction_date: FieldValidation
    transaction_amount: FieldValidation
    branch_location: FieldValidation


class BranchExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_data: BranchExtracted
    validation: BranchValidation
    is_complete: bool
    missing_fields: List[str]
