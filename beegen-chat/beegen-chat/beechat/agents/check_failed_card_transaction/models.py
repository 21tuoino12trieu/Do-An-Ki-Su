from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class CheckFailedCardTransactionFieldValidation(BaseModel):
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


class CheckFailedCardTransactionExtractedData(BaseModel):
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
    transaction_channel: Optional[Literal["ATM", "POS", "ECOM"]] = Field(
        None,
        description="Kênh thực hiện giao dịch (ATM / POS / Ecom)."
    )
    transaction_date: Optional[str] = Field(
        None,
        description="Thời gian giao dịch."
    )
    transaction_amount: Optional[float] = Field(
        None,
        description="Số tiền giao dịch."
    )
    transaction_error_message: Optional[str] = Field(
        None,
        description="Nội dung thông báo lỗi."
    )


class CheckFailedCardTransactionValidation(BaseModel):
    """Trạng thái xác thực chi tiết cho từng trường thông tin được khai thác."""
    account_number: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tài khoản."
    )
    card_first4: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số đầu thẻ."
    )
    card_last4: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số cuối thẻ."
    )
    card_id: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ID thẻ."
    )
    transaction_channel: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho kênh giao dịch."
    )
    transaction_date: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho thời gian giao dịch."
    )
    transaction_amount: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tiền giao dịch."
    )
    transaction_error_message: CheckFailedCardTransactionFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho thông báo lỗi."
    )


class CheckFailedCardTransactionExtractionResult(BaseModel):
    """
    Schema đầu ra cho quá trình khai thác và xác thực thông tin kiểm tra giao dịch thẻ không thành công.
    Sử dụng để hướng dẫn LLM trả về thông tin theo cấu trúc cụ thể này.
    """
    extracted_data: CheckFailedCardTransactionExtractedData = Field(
        ...,
        description="Thông tin đã khai thác được từ cuộc hội thoại với khách hàng."
    )
    is_complete: bool = Field(
        ...,
        description="""
Đã khai thác đủ các thông tin key chưa. 
Phần thông tin thẻ: Chỉ cần 4 số đầu + 4 số cuối, hoặc Số Seri thẻ, hoặc ID thẻ, hoặc số tài khoản (Chỉ cần 1 trong các thông tin, không cần cung cấp tất cả)
"""
    )
    missing_fields: List[
        Literal[
            "account_number",
            "card_first4",
            "card_last4",
            "card_id",
            "transaction_channel",
            "transaction_date",
            "transaction_amount"
        ]
    ] = Field(
        ...,
        description="Danh sách các trường thông tin quan trọng còn thiếu hoặc chưa hợp lệ."
    )
    validation: CheckFailedCardTransactionValidation = Field(
        ...,
        description="Trạng thái xác thực chi tiết cho từng trường thông tin."
    )
