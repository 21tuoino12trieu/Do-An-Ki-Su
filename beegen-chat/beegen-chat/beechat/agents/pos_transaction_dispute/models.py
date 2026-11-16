from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class PosTransactionDisputeFieldValidation(BaseModel):
    """Chi tiết trạng thái xác thực của một trường thông tin."""
    is_present: bool = Field(
        ...,
        description="Cho biết thông tin đã được khách hàng cung cấp hay chưa."
    )
    is_valid_format: bool = Field(
        ...,
        description="Cho biết thông tin cung cấp có đúng định dạng yêu cầu hay không."
    )
    error: Optional[str] = Field(
        None,
        description="Thông báo lỗi nếu thông tin không hợp lệ. Trả về null nếu không có lỗi."
    )


class PosTransactionDisputeExtractedData(BaseModel):
    """Thông tin khai thác được từ khách hàng."""
    account_number: Optional[str] = Field(
        None,
        description="Số tài khoản ngân hàng."
    )
    card_first4: Optional[str] = Field(
        None,
        description="4 số đầu của số thẻ."
    )
    card_last4: Optional[str] = Field(
        None,
        description="4 số cuối của số thẻ."
    )
    card_id: Optional[str] = Field(
        None,
        description="Mã định danh (ID) của thẻ."
    )
    transaction_date: Optional[str] = Field(
        None,
        description="Ngày giao dịch."
    )
    transaction_amount: Optional[str] = Field(
        None,
        description="Số tiền giao dịch."
    )
    pos_bank_type: Optional[Literal["MB", "OTHER_BANK"]] = Field(
        None,
        description="POS của MB hay ngân hàng khác."
    )


class PosTransactionDisputeValidation(BaseModel):
    """Trạng thái xác thực chi tiết cho từng trường thông tin được khai thác."""
    account_number: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tài khoản."
    )
    card_first4: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số đầu thẻ."
    )
    card_last4: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số cuối thẻ."
    )
    card_id: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ID thẻ."
    )
    transaction_date: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ngày giao dịch."
    )
    transaction_amount: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tiền giao dịch."
    )
    pos_bank_type: PosTransactionDisputeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho loại POS."
    )


class PosTransactionDisputeExtractionResult(BaseModel):
    """
    Schema đầu ra cho quá trình khai thác và xác thực thông tin tra soát giao dịch POS.
    Sử dụng để hướng dẫn LLM trả về thông tin theo cấu trúc cụ thể này.
    """
    extracted_data: PosTransactionDisputeExtractedData = Field(
        ...,
        description="Thông tin đã khai thác được từ cuộc hội thoại với khách hàng."
    )
    is_complete: bool = Field(
        ...,
        description="""
Đã khai thác đủ các thông tin key chưa. 
Phần thông tin thẻ: Chỉ cần 4 số đầu + 4 số cuối, hoặc ID thẻ, hoặc tài khoản (Chỉ cần 1 trong các thông tin, không cần cung cấp tất cả)
"""
    )
    missing_fields: List[
        Literal[
            "account_number",
            "card_first4",
            "card_last4",
            "card_id",
            "transaction_date",
            "transaction_amount",
            "pos_bank_type"
        ]
    ] = Field(
        ...,
        description="Danh sách các trường thông tin quan trọng còn thiếu hoặc chưa hợp lệ."
    )
    validation: PosTransactionDisputeValidation = Field(
        ...,
        description="Trạng thái xác thực chi tiết cho từng trường thông tin."
    )
