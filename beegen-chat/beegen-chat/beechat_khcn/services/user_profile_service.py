"""
User Profile Service - Xử lý thông tin profile từ topic JSON
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from beegenerate.loggings import LOGGER


@dataclass
class UserProfile:
    """User profile data extracted from topic JSON"""
    user_name: Optional[str] = None  # Thay thế cho xung_ho
    marital_status: Optional[str] = None  # Thay thế cho hon_nhan
    education: Optional[str] = None  # Thay thế cho hoc_van
    current_job: Optional[str] = None  # Thay thế cho viec_lam
    job_position: Optional[str] = None  # Thay thế cho vi_tri
    work_duration: Optional[str] = None  # Thay thế cho thoi_gian_lam_viec
    industries: Optional[str] = None  # Thay thế cho nganh_nghe
    has_children: Optional[str] = None  # Thay thế cho so_con
    monthly_income: Optional[str] = None  # Thay thế cho thu_nhap_thang
    banking_purposes: List[str] = None  # Thay thế cho muc_dich_ngan_hang
    account_list: List[str] = None  # Thay thế cho danh_sach_tai_khoan
    customer_code: Optional[str] = None
    # Thêm các trường mới
    birth_date: Optional[str] = None
    gender: Optional[str] = None

    def __post_init__(self):
        if self.banking_purposes is None:
            self.banking_purposes = []
        if self.account_list is None:
            self.account_list = []

    def get_display_name(self) -> str:
        """Get user display name for greeting"""
        return self.user_name if self.user_name else "bạn"

    def get_account_list(self) -> List[str]:
        """Get list of user accounts"""
        return self.account_list if self.account_list else []

    def get_customer_code(self) -> Optional[str]:
        """Get customer code from profile"""
        return self.customer_code

    def to_dict(self) -> Dict:
        """Convert to dictionary for easy access"""
        return {
            'user_name': self.user_name,
            'marital_status': self.marital_status,
            'education': self.education,
            'current_job': self.current_job,
            'job_position': self.job_position,
            'work_duration': self.work_duration,
            'industries': self.industries,
            'has_children': self.has_children,
            'monthly_income': self.monthly_income,
            'banking_purposes': self.banking_purposes,
            'account_list': self.account_list,
            'birth_date': self.birth_date,
            'gender': self.gender,
            'customer_code': self.customer_code
        }


class UserProfileService:
    """Service to parse and manage user profile from topic JSON"""

    def __init__(self):
        self._profiles = {}  # Cache profiles by session_id
        LOGGER.info("UserProfileService initialized")

    def parse_topic_json(self, topic_json: str) -> Optional[UserProfile]:
        """Parse topic JSON string to UserProfile object"""
        try:
            if not topic_json or not topic_json.strip():
                LOGGER.warning("Empty topic JSON provided")
                return None

            # Parse JSON string
            profile_data = json.loads(topic_json)

            # LOG RAW PROFILE DATA
            LOGGER.info(f"RAW PROFILE DATA:")
            for key, value in profile_data.items():
                if key == 'accountList' and isinstance(value, list):
                    LOGGER.info(f"   {key}: {len(value)} accounts - {value}")
            customer_code = None
            user_id = profile_data.get('userId') or profile_data.get('userID')  # Hỗ trợ cả 2 format
            if user_id:
                customer_code = str(user_id).strip()
                LOGGER.info(f"   📝 Customer code parsed from userID: {customer_code}")

            # Create UserProfile object với mapping mới
            profile = UserProfile(
                user_name=profile_data.get('name'),
                marital_status=profile_data.get('maritalStatus'),
                education=profile_data.get('education'),
                current_job=profile_data.get('currentJob'),
                job_position=profile_data.get('jobPosition'),
                work_duration=profile_data.get('workDuration'),
                industries=profile_data.get('industries'),
                has_children=profile_data.get('hasChildren'),
                monthly_income=profile_data.get('monthlyIncome'),
                banking_purposes=profile_data.get('bankingPurposes', []),
                account_list=profile_data.get('accountList', []),
                birth_date=profile_data.get('birthDate'),
                gender=profile_data.get('gender'),
                customer_code=customer_code
            )

            # LOG MAPPED PROFILE
            LOGGER.info(f"PROFILE MAPPING COMPLETED:")
            LOGGER.info(f"   📝 Display Name: {profile.get_display_name()}")
            LOGGER.info(f"   🏦 Account Count: {len(profile.get_account_list())}")
            LOGGER.info(f"   👤 Customer Code: {profile.get_customer_code()}")

            return profile

        except json.JSONDecodeError as e:
            LOGGER.error(f"Invalid JSON in topic field: {e}")
            LOGGER.error(f"   Raw topic: {topic_json[:200]}...")
            return None
        except Exception as e:
            LOGGER.error(f"Error parsing topic JSON: {e}")
            LOGGER.error(f"   Raw topic: {topic_json[:200]}...")
            return None

    def validate_topic_format(self, topic_json: str) -> bool:
        """
        Validate if topic JSON string follows expected format
        Support both old and new format keys
        """
        if not topic_json or not topic_json.strip():
            return False

        try:
            data = json.loads(topic_json)

            # Check if it's a dictionary
            if not isinstance(data, dict):
                return False

            # Check for expected keys (support both old and new formats)
            expected_keys_new = ['name', 'accountList']
            expected_keys_old = ['xung_ho', 'danh_sach_tai_khoan', 'muc_dich_ngan_hang']

            has_new_format = any(key in data for key in expected_keys_new)
            has_old_format = any(key in data for key in expected_keys_old)

            has_expected_key = has_new_format or has_old_format

            LOGGER.info(
                f"Topic validation - Has expected keys: {has_expected_key} (new: {has_new_format}, old: {has_old_format})")
            return has_expected_key

        except json.JSONDecodeError:
            LOGGER.error("Topic JSON validation failed - Invalid JSON format")
            return False
        except Exception as e:
            LOGGER.error(f"Topic validation error: {e}")
            return False

    def store_profile(self, session_id: str, profile: UserProfile):
        """Store profile for session"""
        self._profiles[session_id] = profile
        LOGGER.info(f"💾 Profile stored for session: {session_id}")

    def get_profile(self, session_id: str) -> Optional[UserProfile]:
        """Get profile for session"""
        return self._profiles.get(session_id)

    def get_user_name(self, session_id: str) -> Optional[str]:
        """Get user name for session"""
        profile = self.get_profile(session_id)
        return profile.get_display_name() if profile else None

    def get_user_accounts(self, session_id: str) -> List[str]:
        """
        Get user accounts - delegates to sorted version for consistency.

        Args:
            session_id: Session ID to get accounts

        Returns:
            List of sorted account numbers
        """
        return self.get_sorted_user_accounts(session_id)

    def get_customer_code(self, session_id: str) -> Optional[str]:
        """THÊM METHOD MỚI: Get customer code from user profile"""
        profile = self.get_profile(session_id)
        if profile and profile.get_customer_code():
            LOGGER.info(f"Found customer code in profile: {profile.get_customer_code()}")
            return profile.get_customer_code()

        LOGGER.info(f"No customer code found in profile for session: {session_id}")
        return None

    def has_customer_code(self, session_id: str) -> bool:
        """THÊM METHOD MỚI: Check if customer code exists in profile"""
        customer_code = self.get_customer_code(session_id)
        exists = customer_code is not None and len(customer_code.strip()) > 0
        LOGGER.info(f"🔍 Customer code exists check for session {session_id}: {exists}")
        return exists

    def get_sorted_user_accounts(self, session_id: str) -> List[str]:
        """
        Get user accounts with consistent sorting order.
        All account list usage should go through this method.
        """
        profile = self.get_profile(session_id)
        LOGGER.info(f"🔍 Getting sorted accounts for session {session_id}: {profile is not None}")

        if profile:
            accounts = profile.get_account_list()
            LOGGER.info(f"Retrieved {len(accounts)} accounts from profile: {accounts}")  # ADD LOG

            # Validate and sort accounts consistently
            validated_accounts = []
            for acc in accounts:
                if acc and isinstance(acc, str) and len(str(acc)) >= 6 and str(acc).isdigit():
                    validated_accounts.append(str(acc))

            # Sort accounts consistently - this ensures same order everywhere
            validated_accounts.sort()

            LOGGER.info(f"Sorted validated accounts: {validated_accounts}")
            return validated_accounts
        else:
            LOGGER.info(f"No profile found for session {session_id}")
            return []