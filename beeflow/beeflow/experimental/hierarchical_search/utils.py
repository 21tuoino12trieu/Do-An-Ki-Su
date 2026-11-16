
import unicodedata
import re
import json 
from pathlib import Path
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter

questions = [
    "Đối tượng áp dụng cho thẻ evipcare visa gồm những ai", 
    "Điều kiện phát hành thẻ Priority Pass gồm những gì",
    "thẻ Priority Pass có nhũng điều kiện gì để được phát hàng thẻ",
    "Đối tượng mở thẻ Mastercard Hi Ads ",
    "Điều kiện phát hành thẻ Mastercard Hi Ads trường hợp KH phát hành, định danh thẻ trên App MBBank",
    "Hồ sơ để phát hành QR trả sau",    # sai topic
    # distances to nearest centroid [0.3610372189775366, 0.39454941001669175, 0.3992069423062097]
    # Searching in topics: ['sản-phẩm/khdn/tktt', 'hướng-dẫn/hướng-dẫn-tra-cứu', 'Hướng-dẫn/hướng-dẫn-nhập-liệu'] with score: [0.37425391666920826, 0.3165159177698251, 0.3092301655609667]
    "Để làm thẻ JCB credit ở trên app MB cần những thủ tục gì ?",    #sai
#     distances to nearest centroid [0.2733191951781828, 0.3070480545475931, 0.3086646102915449]
# Searching in topics: ['sản-phẩm/khcn/ngân-hàng-điện-tử', 'sản-phẩm/khdn/ngân-hàng-điện-tử', 'sản-phẩm/khcn/the'] with score: [0.3727424178564454, 0.31489628023041333, 0.31236130191314115]
    "Hồ sơ thủ tục làm thẻ JCB credit ở chi nhánh CN/PGD MB ?",
    "Anh/Chị muốn nhận thẻ ghi nợ nội địa ở đâu?", #sai 
    #distances to nearest centroid [0.311065507315462, 0.32089638112919405, 0.33713571814123455]
# Searching in topics: ['sản-phẩm/khdn/the', 'sản-phẩm/khcn/the', 'Lãi-suất-biểu-phí'] with score: [0.35337919458980405, 0.3364290624666977, 0.31019174294349827]
    "Trường hợp KH chưa được cấp hạn mức thẻ tín dụng trước đó thì MB phát hành thẻ cho KH áp dụng theo chính sách nào?",
    "thời gian phát hàng thẻ vật lí của thẻ ghi nợ quốc tế Unionpay",
    "Điều kiện để nâng hạn mức tín dụng của thẻ đa năng JCB Hi ACCESSTRADE",
    "Hạn mức rút tiền của thẻ đa năng JCB Hi ACCESSTRADE",
    "Hạn mức thanh toán qua POS, Ecom của thẻ đa năng JCB Hi ACCESSTRADE",
    "Hạn mức rút tiền của thẻ đa năng  JCB Hi Sky",
    "Hạn mức thanh toán qua POS, Ecom của thẻ đa năng  JCB Hi Sky",
]

llm_questions = [
"Chuyển tiền trong nước chiều đi là gì?",  #test-files\Chuyển tiền_102. SẢN PHẨM CHUYỂN TIỀN TRONG NƯỚC KHCN.xlsx
"Chuyển tiền nhanh 24/7 qua Napas có thời gian xử lý như thế nào?",
"Khi chuyển tiền theo lô, hạn mức tối đa cho một giao dịch trong lô khi sử dụng gói Advance 1 tỷ là bao nhiêu?",  
"Điều kiện để được hỗ trợ tra soát gấp là gì?",  #test-files\Hướng dẫn nhập liệu_3.10 Hướng dẫn điều kiện hỗ trợ Tra soát gấp.xlsx
"Ai có thể yêu cầu hỗ trợ tra soát gấp?",
"Sản phẩm cho vay tái tài trợ cho KH SME dùng để làm gì?", #test-files\Sản phẩm cho vay_135. Cho vay Tái tài trợ cho KH SME.xlsx
"Điều kiện về lịch sử tín dụng của khách hàng SME khi xét duyệt cho vay tái tài trợ là gì?",
"Khi KH muốn chuyển nợ từ TCTD khác về MB và TSBĐ đang đảm bảo cho khoản vay tại TCTD cũ, thì quy trình thực hiện như thế nào nếu KH nhận nợ tại MB trước để trả nợ tại TCTD đã tài trợ?",
"App Thiện Nguyện giúp minh bạch tài chính như thế nào?",  #test-files\TKTT_94. Tài khoản thiện nguyện.xlsx   
"Người dùng có thể ủng hộ bằng những phương thức nào?",  #sai topic
"AI chatbot BeeKind hỗ trợ người dùng những gì?",  #sai topic
"Ai có thể là người đại diện hợp pháp để mở tài khoản tiết kiệm cho trẻ từ 0-15 tuổi?",  #test-files\Tiền gửi và CCTG_87. Tiết kiệm cho con.xlsx
"Cách nào có thể nộp thêm tiền vào tài khoản tiết kiệm?",
"Nếu ngày đến hạn tài khoản tiết kiệm trùng vào ngày lễ, thì ngân hàng xử lý thế nào?",
"Tài khoản thanh toán cá nhân là gì?",   #test-files\~$TKTT_97. Tài khoản thanh toán.xlsx
"Ai có thể mở tài khoản thanh toán tại MB?",
"Khi nào thì tài khoản thanh toán có thể bị đóng?",
]

fail_questions = [
    "Nếu KH có  15 thẻ, muốn mở thẻ mới nhưng tôi đóng 1 thẻ thì sau bao lâu thì làm được thẻ mới?",  #dung
    "thời gian phát hàng thẻ Mastercard Hi Green sau khi đăng kí thành công?",  #dung
    "Làm thế nào để thay đổi hạn mức tín dụng Thẻ Priority Pass?",  #dung topic, search sai 
    "KH có Thẻ đa năng Mastercard Hi Green muốn thay đổi tỷ lệ trích nợ hoặc số tài khoản trích nợ thì ra đâu ?",  #dung 
    "Phương pháp tính lãi giao dịch thanh toán tại POS của Thẻ tín dụng quốc tế JCB Credit là gì?",  #dung 
    "Giao dịch trên POS của thẻ JCB Hi Collection như thế nào?", #d
    "Thẻ JCB Hi Collection có in thẻ tại Smartbank được không?", #d
    "Hạn mức rút tiền ATM của thẻ đa năng JCB Hi Collection",  #d
    "Khách hàng cho rằng sao kê gửi sai ngày, vậy ngày sao kê chính thức là khi nào đối với Thẻ tín dụng quốc tế Visa Credit", #d
    "Khách hàng cho rằng sao kê đến muộn, ngân hàng có quy định gì về thời điểm gửi SMS nhắc nợ đối với Thẻ tín dụng quốc tế Visa Credit?", #d
    "Khi khách hàng không nhận được thông báo giao dịch thẻ JCB Hi ACCESSTRADE qua App, họ có thể thực hiện gia hạn thẻ tín dụng bằng cách nào?",
    "Đối tượng nào sẽ phải chịu phí khi điều chỉnh hạn mức tín dụng của thẻ đa năng và thẻ tín dụng?",
    "Khi thực hiện giao dịch thanh toán Ecom (online) với thẻ Visa Credit, khách hàng có cần nhập PIN không?",
    "Một số đơn vị chấp nhận thẻ (App/Web) có thể yêu cầu khách hàng nhập thêm thông tin gì khi thanh toán online qua thẻ Visa Credit?",
    "Tại sao MB không quy định việc nhập OTP trong mọi giao dịch Ecom với thẻ Visa Credit?",
    "Khi thực hiện giao dịch thanh toán Ecom (online) với thẻ đa năng Visa Hybrid, khách hàng có cần nhập PIN không?",
    "Khi thực hiện giao dịch thanh toán Ecom (online) với thẻ đa năng JCB Hi Shopee Food, khách hàng có cần nhập PIN không?",
    "Nếu khách hàng gặp lỗi kích hoạt thẻ tín dụng quốc tế Visa Credit do chưa định danh, hạn mức rút tiền mặt tối đa cho một giao dịch tại ATM là bao nhiêu?",
    "Trong trường hợp kích hoạt thẻ tín dụng quốc tế Visa Credit chưa thành công, khách hàng có thể mở hạn mức chi tiêu trong ngày bằng cách nào? ",
    "Nêu một số nguyên nhân dẫn đến thẻ ghi nợ nội địa bị khóa", #d
    "Phí dịch vụ khi sử dụng thẻ để thanh toán chi phí quảng cáo có gì khác biệt giữa các nền tảng (Facebook Ads, Google Ads, TikTok Ads) khi tôi là chủ thẻ?",
]

def normalize_text(s: str) -> str:
    """
    - lower
    - remove accent
    - replace special chars by space
    """
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def split_path_tokens(path: str) -> list[str]:
    """
    Split file path into normalized tokens
    """
    p = Path(path)
    parts = p.parts
    tokens = []
    for part in parts:
        norm = normalize_text(part)
        if norm:
            tokens.extend(norm.split())
    return tokens


def split_topic_tokens(topic: str) -> list[str]:
    """
    Split topic path into normalized tokens
    """
    parts = topic.split("/")
    tokens = []
    for part in parts:
        norm = normalize_text(part.replace("-", " "))
        if norm:
            tokens.extend(norm.split())
    return tokens


def is_path_match_topic(file_path: str, topic: str) -> bool:
    """
    Check whether file path matches topic
    """
    path_tokens = split_path_tokens(file_path)
    topic_tokens = split_topic_tokens(topic)

    if not topic_tokens:
        return False

    # check topic_tokens is a subsequence of path_tokens
    i = 0
    for token in path_tokens:
        if token == topic_tokens[i]:
            i += 1
            if i == len(topic_tokens):
                return True

    return False

def write_json(chunks, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print("done")
