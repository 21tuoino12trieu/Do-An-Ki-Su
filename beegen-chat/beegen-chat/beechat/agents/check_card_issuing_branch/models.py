from typing import Optional, Literal, List
from pydantic import BaseModel, Field


class CardIssuingBranchFieldValidation(BaseModel):
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


class CardIssuingBranchExtractedData(BaseModel):
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


class CardIssuingBranchValidation(BaseModel):
    """Trạng thái xác thực chi tiết cho từng trường thông tin được khai thác."""
    card_first4: CardIssuingBranchFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số đầu thẻ."
    )
    card_last4: CardIssuingBranchFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số cuối thẻ."
    )
    card_id: CardIssuingBranchFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ID thẻ."
    )


class CardIssuingBranchExtractionResult(BaseModel):
    """
    Schema đầu ra cho quá trình khai thác và xác thực thông tin thẻ bị nuốt.
    Sử dụng để hướng dẫn LLM trả về thông tin theo cấu trúc cụ thể này.
    """
    extracted_data: CardIssuingBranchExtractedData = Field(
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
            "card_id"
        ]
    ] = Field(
        ...,
        description="Danh sách các trường thông tin quan trọng còn thiếu hoặc chưa hợp lệ."
    )
    validation: CardIssuingBranchValidation = Field(
        ...,
        description="Trạng thái xác thực chi tiết cho từng trường thông tin."
    )
