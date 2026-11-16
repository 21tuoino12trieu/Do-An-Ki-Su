from typing import Optional, Literal, List
from pydantic import BaseModel, Field

CardDeliveryIntentEnum = Literal[
    'INTENT_SMARTBANK',
    'INTENT_HOME_OVER_7_DAYS',
    'INTENT_MAIN',
    'INTENT_CHITCHAT'
]

class CardDeliveryIntent(BaseModel):
    branch: CardDeliveryIntentEnum = Field(..., description="Card Delivery intent.")

# --- Định nghĩa cho $defs/field_validation ---
class BranchHomeFieldValidation(BaseModel):
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

# --- Định nghĩa cho extracted_data ---
class BranchHomeExtractedData(BaseModel):
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
    card_serial: Optional[str] = Field(
        None,
        description="Số seri của thẻ."
    )
    order_code: Optional[str] = Field(
        None,
        description="Mã vận đơn/Mã đơn hàng"
    )

# --- Định nghĩa cho validation ---
class BranchHomeValidation(BaseModel):
    """Trạng thái xác thực chi tiết cho từng trường thông tin được khai thác."""
    account_number: BranchHomeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số tài khoản."
    )
    card_first4: BranchHomeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số đầu thẻ."
    )
    card_last4: BranchHomeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho 4 số cuối thẻ."
    )
    card_id: BranchHomeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho ID thẻ."
    )
    card_serial: BranchHomeFieldValidation = Field(
        ...,
        description="Trạng thái xác thực cho số seri thẻ."
    )
    order_code: BranchHomeFieldValidation = Field(
        ...,
        description="Mã vận đơn/Mã đơn hàng"
    )

# --- Định nghĩa cho schema gốc (Root Model) ---
class BranchHomeExtractionResult(BaseModel):
    """
    Schema đầu ra cho quá trình khai thác và xác thực thông tin đăng ký vay.
    Sử dụng để hướng dẫn LLM trả về thông tin theo cấu trúc cụ thể này.
    """
    extracted_data: BranchHomeExtractedData = Field(
        ...,
        description="Thông tin đã khai thác được từ cuộc hội thoại với khách hàng."
    )
    is_complete: bool = Field(
        ...,
        description="""
Đã khai thác đủ các thông tin key chưa. 
Phần thông tin thẻ: Chỉ cần 4 số đầu + 4 số cuối, hoặc Số Seri thẻ, hoặc ID thẻ, hoăc số tài khoản (Chỉ cần 1 trong các thông tin, không cần cung cấp tất cả)
"""
    )
    missing_fields: List[
        Literal[
            "account_number",
            "card_first4",
            "card_last4",
            "card_id",
            "card_serial",
            "order_code"
        ]
    ] = Field(
        ...,
        description="Danh sách các trường thông tin quan trọng còn thiếu hoặc chưa hợp lệ."
    )
    validation: BranchHomeValidation = Field(
        ...,
        description="Trạng thái xác thực chi tiết cho từng trường thông tin."
    )


# Định nghĩa các $defs trước, vì chúng được tham chiếu bởi các phần khác
class BranchSmartBankFieldValidation(BaseModel):
    """
    Validation details for a single field.
    """
    is_present: bool = Field(description="Đã cung cấp hay chưa")
    is_valid_format: bool = Field(description="Đúng định dạng hay chưa")
    error: Optional[str] = Field(None, description="Thông báo lỗi nếu có")

# Định nghĩa các cấu trúc dữ liệu chính
class BranchSmartBankExtractedData(BaseModel):
    """
    Thông tin khai thác được từ khách hàng
    """
    card_first4: Optional[str] = Field(None, description="4 số đầu thẻ")
    card_last4: Optional[str] = Field(None, description="4 số cuối thẻ")
    card_id: Optional[str] = Field(None, description="ID thẻ")

class BranchSmartBankValidationResult(BaseModel):
    """
    Kết quả kiểm tra hợp lệ cho các trường dữ liệu
    """
    card_first4: BranchSmartBankFieldValidation
    card_last4: BranchSmartBankFieldValidation
    card_id: BranchSmartBankFieldValidation

# Định nghĩa Enum cho missing_fields để đảm bảo tính chính xác của dữ liệu
# Lưu ý: Các giá trị Literal phải khớp với các giá trị trong enum của schema gốc
MissingFieldEnum = Literal["card_first4", "card_last4", "card_id"]

class BranchSmartBankExtractionResult(BaseModel):
    """
    Kết quả tổng hợp việc trích xuất và xác thực thông tin thẻ từ khách hàng.
    """
    extracted_data: BranchSmartBankExtractedData = Field(description="Thông tin khai thác được từ khách hàng")
    validation: BranchSmartBankValidationResult
    is_complete: bool = Field(description="True nếu tất cả các trường thông tin cần thiết đã được khai thác và hợp lệ; False nếu còn thiếu hoặc có lỗi.")
    missing_fields: List[MissingFieldEnum] = Field(description="Danh sách thông tin còn thiếu")