import math
import re

def calc_math_expression(expression: str) -> str:
    """
    Công cụ tính toán các biểu thức toán học.
    Hữu ích cho việc tính lãi suất, lịch trả nợ, tính lương, thuế, và các phép tính tài chính.
    
    Args:
        expression (str): Biểu thức toán học cần tính (ví dụ: "50000000 * 0.1", "10000000 * (1+0.06/12)**12").
                          Hỗ trợ các hàm: sqrt, pow, log, abs, ceil, floor.
    
    Returns:
        str: Kết quả của phép tính hoặc thông báo lỗi.
    """
    try:
        # 1. Pre-processing: Làm sạch chuỗi đầu vào từ LLM
        # Xóa các ký tự tiền tệ và khoảng trắng thừa
        clean_expr = expression.strip()
        clean_expr = re.sub(r'[,$đVNDvnd]', '', clean_expr) 
        
        # Chuyển đổi ký hiệu phần trăm: 10% -> 0.10
        # Logic: Tìm số đứng trước %, thay thế bằng số/100
        clean_expr = re.sub(r'(\d+(?:\.\d+)?)%', lambda x: str(float(x.group(1))/100), clean_expr)
        
        # Chuyển đổi mũ từ ^ sang ** (LLM hay dùng ^ theo thói quen Excel/Text)
        clean_expr = clean_expr.replace('^', '**')

        # 2. Định nghĩa môi trường an toàn (Safe Environment)
        # Chỉ cho phép các hàm toán học an toàn, không cho phép import hay os system calls
        allowed_names = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "pow": pow,
        }
        # Thêm các hàm từ thư viện math (sin, cos, sqrt, log, exp...)
        allowed_names.update({k: v for k, v in math.__dict__.items() if not k.startswith("__")})

        # 3. Thực thi tính toán
        # eval() được giới hạn trong allowed_names để đảm bảo bảo mật
        result = eval(clean_expr, {"__builtins__": {}}, allowed_names)

        # 4. Định dạng kết quả
        # Nếu là số nguyên, trả về int, nếu là số thập phân quá dài, làm tròn 4 chữ số
        if isinstance(result, float):
            # Kiểm tra nếu là số nguyên dạng float (vd: 1000.0)
            if result.is_integer():
                return str(int(result))
            return str(round(result, 4)) # Làm tròn 4 số lẻ để gọn gàng
        
        return str(result)

    except ZeroDivisionError:
        return "Lỗi: Không thể chia cho 0."
    except SyntaxError:
        return f"Lỗi cú pháp: Không thể hiểu biểu thức '{expression}'."
    except Exception as e:
        return f"Lỗi tính toán: {str(e)}"

# --- Phần Test nhanh (Sẽ không chạy khi được import vào main) ---
if __name__ == "__main__":
    print(calc_math_expression("50,000,000 * 10%")) # Test xử lý tiền và %
    print(calc_math_expression("100 * (1 + 0.05/12)^12")) # Test lãi kép và mũ ^
    print(calc_math_expression("sqrt(144) + 10")) # Test hàm math
