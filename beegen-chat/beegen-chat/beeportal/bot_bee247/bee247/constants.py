from beegenerate.storage import MongoStorage
from beegenerate.configs import MongoConfig
from beegenerate.loggings import LOGGER
import uuid
from pathlib import Path


MONGO_STORAGE = MongoStorage(config=MongoConfig.from_yaml_file(Path("config/mongo.yaml")))


import json
def get_card_filename():
    CARD_KEYWORD = MONGO_STORAGE.find_with_output_fields(collection_name="filename_mapping", 
                                                            query={
                                                                "type": "card_filename"
                                                            },
                                                            output_fields={"mapping": 1, "_id": 0}
                                                            )
    
    CARD_KEYWORD = CARD_KEYWORD[0]['mapping']
    
    if isinstance(CARD_KEYWORD, str):
        CARD_KEYWORD = json.loads(CARD_KEYWORD)
    
    return CARD_KEYWORD

def get_card_keyword_unique():
    
    CARD_KEYWORD = MONGO_STORAGE.find_with_output_fields(collection_name="filename_mapping", 
                                                            query={
                                                                "type": "card_keyword"
                                                            },
                                                            output_fields={"mapping": 1, "_id": 0}
                                                            )
    
    # print("CARD KEYWORD:", CARD_KEYWORD)
    
    CARD_KEYWORD = CARD_KEYWORD[0]['mapping']
    
    if isinstance(CARD_KEYWORD, str):
        CARD_KEYWORD = json.loads(CARD_KEYWORD)

    unique_keywords = set()
    for keywords in CARD_KEYWORD.values():
        unique_keywords.update(keywords)
        
    result = list(unique_keywords)
    
    print(result)
    
    return result

def get_card_keyword_mapping():
    CARD_KEYWORD = MONGO_STORAGE.find_with_output_fields(collection_name="filename_mapping", 
                                                            query={
                                                                "type": "card_keyword"
                                                            },
                                                            output_fields={"mapping": 1, "_id": 0}
                                                            )
    
    CARD_KEYWORD = CARD_KEYWORD[0]['mapping']
    
    if isinstance(CARD_KEYWORD, str):
        CARD_KEYWORD = json.loads(CARD_KEYWORD)
    
    return CARD_KEYWORD


abbr_dict = {
    'mb': 'Ngân hàng TMCP Quân đội',
    'kh': 'Khách hàng',
    'vnđ': 'Việt Nam đồng',
    'tctqt': 'Tổ chức thẻ quốc tế',
    'tctd': 'tổ chức tín dụng',
    'tk': 'Tài khoản',
    'tktt': 'Tài khoản thanh toán',
    'tt': 'Thanh toán',
    'ttsk': 'Thanh toán sao kê',
    'cbnv': 'Cán bộ nhân viên',
    'thẻ tdqt': 'Thẻ tín dụng quốc tế',
    'gd': 'Giao dịch',
    'đvkd': 'Đơn vị kinh doanh',
    'cn': 'Chi nhánh',
    'pgd': 'Phòng giao dịch',
    'cn/pgd': 'Chi nhánh/Phòng giao dịch',
    'rm': 'chuyên viên quản lý Khách hàng',
    'gttt': 'giấy tờ tùy thân',
    'cmt': 'Chứng minh thư',
    'cccd': 'căn cước công dân/thẻ căn cước',
    'th': 'trường hợp',
    'tmcp': 'Thương mại cổ phần',
    'ph': 'Phát hành',
    'sgd': 'Sở giao dịch',
    'đvcnt': 'Đơn vị chấp nhận thẻ',
    'tdqt': 'Tín dụng quốc tế',
    'nhs': 'Ngân hàng số',
    'tb': 'Thông báo',
    'tsbđ': 'Tài sản bảo đảm',
    'hđlđ': 'Hợp đồng lao động',
    'qđ': 'Quyết định',
    'bhxh': 'Bảo hiểm xã hội',
    'nh': 'Ngân hàng',
    'hđqt': 'Hội đồng quản trị',
    'pgđl': 'Phó giám đốc',
    'khcn': 'Khách hàng cá nhân',
    'qtrr': 'Quản trị rủi ro',
    'cntt': 'Công nghệ thông tin',
    'qhkh': 'Quan hệ khách hàng',
    'tts': 'Tổng tài sản',
    'dvkh': 'Dịch vụ khách hàng',
    'tttt': 'Trung tâm thanh toán',
    'tttm': 'Tài trợ thương mại',
    'ptkd': 'Phát triển kinh doanh',
    'httd': 'Hỗ trợ tín dụng',
    'cmnd': 'Chứng minh nhân dân',
    'mokhoathe': 'Mở khóa thẻ, viết liền không dấu',
    'khoathe': 'Khóa thẻ, viết liền không dấu',
    'mo3d': 'Mở 3D, viết liền không dấu',
    'mointernet': 'Mở internet, viết liền không dấu',
    'donginternet': 'Đóng internet, viết liền không dấu',
    '4sốđầuthẻ': '4 số đầu tiên trong dãy số in nổi trên mặt thẻ',
    '4sốcuốithẻ': '4 số cuối cùng trong dãy số in nổi trên mặt thẻ',
    'sốcmt': 'Số giấy tờ tùy thân KH đăng ký với MB',
    'sđt': 'số điện thoại',
    'sdt': 'số điện thoại',
    'tks': 'tiết kiệm số',
    'tks cđ': 'tiết kiệm số cố định',
    'tks tl': 'tiết kiệm số tích lũy',
    'bđsd': 'biến động số dư',
    'sly-dy': 'Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)',
    'slaydy': 'Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)',
    'lay-dy': 'Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)'
}


if __name__ == "__main__":
    print(get_card_filename())