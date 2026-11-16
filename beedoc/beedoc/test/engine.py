import asyncio
import os
import sys

# Ensure the package is in the search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from beedoc_v3.engine import BeedocEngine


async def test_engine_process(file_path: str) -> None:
    """Simple SDK-style example for end users."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    sdk = BeedocEngine()
    output = await sdk.process(file_path)

    print(f"output:{output}")

if __name__ == "__main__":
    # Example usage: python test/engine.py
    test_file = r"assets\855250762_huong_dan_kiem_tra_trang_thai_yeu_cau_cung_cap_gbc_cho_gd_luong_ach_tren_cardportal__danh_cho_tuyen_2 copy.html"
    asyncio.run(test_engine_process(test_file))
    # page_id = "621478801"
    # asyncio.run(test_engine_confluence(page_id))
