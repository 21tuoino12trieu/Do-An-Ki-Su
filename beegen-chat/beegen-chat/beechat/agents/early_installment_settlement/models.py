from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class EarlyInstallmentSettlementFieldValidation(BaseModel):
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


class EarlyInstallmentSettlementExtractedData(BaseModel):
    """Thông tin khai thác được từ khách hàng."""
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
    installment_amount: Optional[float] = Field(
        None,
        description="Số tiền đăng ký trả góp."
    )
    installment_tenor: Optional[int] = Field(
        None,
        description="Kỳ hạn trả góp (tháng)."
    )


class EarlyInstallmentSettlementValidation(BaseModel):
    """Trạng thái xác thực chi tiết cho từng trường thông tin được khai thác."""
    card_first4: EarlyInstallmentSettlementFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số đầu thẻ."
    )
    card_last4: EarlyInstallmentSettlementFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số cuối thẻ."
    )
    card_id: EarlyInstallmentSettlementFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ID thẻ."
    )
    installment_amount: EarlyInstallmentSettlementFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tiền trả góp."
    )
    installment_tenor: EarlyInstallmentSettlementFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho kỳ hạn trả góp."
    )


class EarlyInstallmentSettlementExtractionResult(BaseModel):
    """
    Schema đầu ra cho quá trình khai thác và xác thực thông tin tất toán trả góp.
    Sử dụng để hướng dẫn LLM trả về thông tin theo cấu trúc cụ thể này.
    """
    extracted_data: EarlyInstallmentSettlementExtractedData = Field(
        ...,
        description="Thông tin đã khai thác được từ cuộc hội thoại với khách hàng."
    )
    is_complete: bool = Field(
        ...,
        description="""
Đã khai thác đủ các thông tin key chưa. 
Phần thông tin thẻ: Chỉ cần 4 số đầu + 4 số cuối, hoặc ID thẻ (Chỉ cần 1 trong các thông tin, không cần cung cấp tất cả)
"""
    )
    missing_fields: List[
        Literal[
            "card_first4",
            "card_last4",
            "card_id",
            "installment_amount",
            "installment_tenor"
        ]
    ] = Field(
        ...,
        description="Danh sách các trường thông tin quan trọng còn thiếu hoặc chưa hợp lệ."
    )
    validation: EarlyInstallmentSettlementValidation = Field(
        ...,
        description="Trạng thái xác thực chi tiết cho từng trường thông tin."
    )
