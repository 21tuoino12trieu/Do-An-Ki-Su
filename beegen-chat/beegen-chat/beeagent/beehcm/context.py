from pydantic.dataclasses import dataclass
from agents.mcp import ToolFilterContext
from typing import Optional

@dataclass
class UserInfo:
    """
    Data class representing Jira user information.

    Attributes:
        user_name (str): Tên đăng nhập
        employee_id (str): Id của nhân viên
        employee_code : Mã nhân viên
        full_name (str): Họ và tên đầy đủ
        date_of_birth (str): Ngày tháng năm sinh của nhân viên
        current_time (str): Thời gian hiện tại
        org_name_manage (str): Tên đơn vị quản lý
        job_name (str): Chức danh hiện tại
        org_level (int): Cấp đơn vị
        org_name_level1 (str): Tên đơn vị trực thuộc 1
        org_name_level2 (str): Tên đơn vị trực thuộc 2  
        org_name_level3 (str): Tên đơn vị trực thuộc 3
        management_level (int): Cấp độ quản lý hiện tại
    """
    user_name: Optional[str] = ""
    employee_id: Optional[str] = ""
    employee_code:Optional[str] = ""
    full_name: Optional[str] = ""
    date_of_birth: Optional[str] = ""
    current_time: Optional[str] = ""
    org_name_manage: Optional[str] = ""
    job_name: Optional[str] = ""
    org_level: Optional[int] = 0
    org_name_level1: Optional[str] = ""
    org_name_level2: Optional[str] = ""
    org_name_level3: Optional[str] = ""
    management_level: Optional[int] = 0
