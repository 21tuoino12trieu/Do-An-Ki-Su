import requests
import json
import time
from typing import Dict, Any
import random
from datetime import datetime, timedelta

def make_extraction_request(
    url: str, 
    conversation: str, 
    request_time: str, 
    token: str
) -> Dict[str, Any]:
    """
    Make an extraction request to the specified endpoint with timing measurement
    
    Args:
        url: The endpoint URL
        conversation: The conversation text to analyze
        request_time: The timestamp for the request
        token: The authorization token
        
    Returns:
        Dict containing the response data and timing information
    """
    payload = json.dumps({
        "conversation": conversation,
        "time": request_time
    })
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        execution_time = time.time() - start_time
        
        return {
            'response_data': response.json(),
            'execution_time': execution_time,
            'status_code': response.status_code
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {str(e)}")
        execution_time = time.time() - start_time
        return {
            'error': str(e),
            'execution_time': execution_time,
            'status_code': getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        }
        

import random
import string

def generate_random_words(
    n: int,
    min_word_length: int = 3,
    max_word_length: int = 10
) -> str:
    """
    Generate a string of n random words.
    
    Args:
        n (int): Number of words to generate
        min_word_length (int): Minimum length of each word
        max_word_length (int): Maximum length of each word
        
    Returns:
        str: Space-separated random words
    """
    words = []
    vowels = 'aeiou'
    consonants = ''.join(set(string.ascii_lowercase) - set(vowels))
    
    for _ in range(n):
        # Generate random word length
        word_length = random.randint(min_word_length, max_word_length)
        
        # Generate word with alternating consonants and vowels for more pronounceable results
        word = ''
        for i in range(word_length):
            if i % 2 == 0:
                word += random.choice(consonants)
            else:
                word += random.choice(vowels)
                
        words.append(word)
    
    return ' '.join(words)
        
        
def get_keycloak_token():
    url = "http://10.1.27.43:8831/auth/realms/ms-core/protocol/openid-connect/token"
    payload = 'grant_type=client_credentials&client_id=ai_center&client_secret=REPLACE_WITH_LOCAL_SECRET'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        print(f"Error getting token: {str(e)}")
        return None
    

# Example usage
if __name__ == "__main__":
    url = "http://llm-api.tanzu-dev.mbbank.com.vn/fvoc-summary/extract"
    CONVERSATIONS = [
        """[Tổng đài viên]: trung tâm dịch vụ khách hàng linh xin nghe ạ bên em có thể hỗ trợ thông tin gì cho chị huyền ạ
[Khách hàng]: em em có thể coi giúp chị cái cái cái thẻ vi sa của chị hiện tại bây giờ có coi sao kê chị trả được nhiên không em
[Tổng đài viên]: vâng tức là hiện tại là chị huyền đang muốn kiểm tra du nợ đến hiện tại chị hay là như thế nào ạ
[Khách hàng]: có nghĩa là đăng tay thì mới sao kê vậy thì hiện tại ghi lại
[Khách hàng]: kê là chị sẽ đóng cái số tiền hiện tại bên đặt đúng không
[Tổng đài viên]: để để bên em kiểm tra lại thông tin thẻ trước đó chị huyền ạ chị huyền đọc ngoại giúp bên em số căn cước công dân đăng ký ở tại ngân hàng quân đội được không chị
[Khách hàng]: không chín ba một bảy chín không không tám sáu bốn bảy
[Khách hàng]: hai bốn tháng mười một một chín bảy chín
[Khách hàng]: ừ
[Tổng đài viên]: dạ vâng ạ chị cho em xin lại họ tên đầy đủ nữa chị nhá
[Khách hàng]: cung hành
[Tổng đài viên]: vâng với lại bốn số cuối của thẻ chị ạ
[Khách hàng]: số số xê vê vê là số trên
[Tổng đài viên]: à không không ạ mình không đọc si vi vi đâu chị ạ mình đọc cái số bốn số cuối ở trên mặt thẻ cho chị cái số lớn lớn ấy chị sao
[Khách hàng]: số hai tám tám
[Tổng đài viên]: vầng sáu hai tám tám
[Tổng đài viên]: sáu hai tám tám thì em đang thấy là nếu như chốt sao kê đến ngày mùng năm tháng mười một ấy chị
[Tổng đài viên]: thì cái thẻ này không có dư nợ
[Khách hàng]: rồi
[Tổng đài viên]: là mình tại vì trước đấy mình đã thanh toán cho ngân hàng nhưng mà đang thanh toán thừa tiền ra nên là hệ thống còn đang ghi nhận là mình đã thanh toán thừa năm trăm bốn mươi lăm nghìn hai trăm linh một đồng đấy là chốt đến ngày mùng năm chị nhá bên em chỉ được đến ngày chốt sao kê thôi chị ạ còn hiện tại nếu mà chị muốn xem được dư nợ cổng hiện tại tức là từ hôm mùng năm đến bây giờ chị là xem là có phát sinh thêm thì không ấy thì mình có thể vào áp ấy chị chị chọn vào phần là thẻ này xong sau tết là thanh toán thẻ ấy ở đấy có phần
[Tổng đài viên]: tư nỗi
[Khách hàng]: vâng em em bảo cho chị hỏi nếu mà em cho chị hỏi cái hôm bữa là
[Khách hàng]: em ơi hôm bữa chị đọc điêu năm trăm mấy hả em
[Tổng đài viên]: vầng hôm tính đến ngày mùng năm thì đang ghi nhận là nạp thừa lên là năm trăm bốn mươi lăm nghìn hai trăm linh một đồng
[Tổng đài viên]: minh và
[Khách hàng]: giờ năm trăm bốn lăm ngàn thì cho năm trăm đi thì bây giờ chị xài hai triệu thời chị tới bữa sao kê thì chị chỉ mà chị cũng thôi đúng không
[Tổng đài viên]: vâng nếu như sau này mà mình có chi tiêu rồi tức là từ thời điểm đấy trở đi ạ mà mình chi tiêu thêm thì bên em lại chốt sao kê dư nợ sang kỳ tới và nếu như phía trước minh đang độc thừa thì ngân hàng sẽ trừ cái số tiền thừa này đi trước ý xem là còn dư nợ còn lại là bao nhiêu thì ngân hàng lại chốt sao kê và báo lại cho mình tiếp chị ạ
[Khách hàng]: tại vì chị không có nhận được sao kê trên hệ thống trên ba meo nên là chị ông có biết hết đó tại chị đang làm thay liền cho
[Tổng đài viên]: i meo thì mình lại vầng không đăng ký đâu chị ạ phải đăng ký giúp bên em địa chỉ meo tại chi nhánh trước để những cái kỳ sao kê sau ấy thì ngân hàng chốt xong thì ngân hàng gửi về đầy đủ chị huyền
[Khách hàng]: ừ rồi nhưng mà bây giờ ở song đó chị đang đang còn là năm trăm sáu hàng năm trăm ngàn đi bây giờ chị dư nợ của chị là hai từ
[Khách hàng]: hai triệu này là là là không có trừ năm trăm ngàn đó đúng hông hai triệu là hai triệu phát sinh chị sử dụng đúng không
[Tổng đài viên]: nếu mà mình mình chi tiêu tại vì ở đây thì em trao đổi lại em bên em chỉ xem một đến ngày trước sau kê ấy thì bây giờ chị vào lại giúp bên em phần tổng dư lõ chị sẽ thấy nếu như mà mình có phát sinh thêm nhá chị nhá thì ngân hàng sau này ngân hàng chốt sao kê ngân hàng sẽ lấy cái số tiền dư đấy của mình ngân hàng trừ đi trước lấy tổng dư nợ trừ đi cái số tiền mà mình đã thừa trước còn lại bao nhiêu ý thì lúc đấy ngân hàng sẽ báo nốt cho mình trong sao kê để mình thanh toán tức là cái số tiền dư đấy mình cũng sẽ được trừ cho tháng sau thôi
[Khách hàng]: ừ ừ ừ rồi rồi chị coi là cho cả
[Tổng đài viên]: vâng thế chị theo dõi giúp bên em nhá đợi bên em rút sau kê xong thì bên em sẽ kiểm tra lại cho chị nếu mà chị cần thì chị báo lại chị ạ
[Khách hàng]: rồi cảm ơn ạ
[Tổng đài viên]: dạ vâng chị huyền có cần kiểm tra thông tin nào khác không ạ
[Khách hàng]: chưa hết rồi em cảm ơn rồi
[Tổng đài viên]: thế còn hỗ trợ thêm chị huyền liên hệ lại tổng đài ạ em chào chị huyền ạ em xin đóng yêu cầu của chị ạ
[Khách hàng]: vâng""",
        """[Tổng đài viên]: a lô
[Tổng đài viên]: dạ a lô ạ dạ vâng đây với số điện tại của anh tuấn anh đúng không ạ
[Khách hàng]: đúng rồi
[Tổng đài viên]: dạ vâng chào anh em là uyên liên hệ cho anh tuấn anh từ phía tổng đài ngân hàng quân đội ạ hiện tại thì bên phía ngân hàng có ghi nhận thông tin anh liên hệ tới tổng đài nhưng không gặp cứ tư vấn viên không biết hiện tại thì vấn đề của mình đã được hỗ trợ chưa anh
[Khách hàng]: chưa chị ơi
[Tổng đài viên]: dạ vâng không biết hiện tại thì anh đang gặp một vấn đề gì vậy ạ mình vui lòng thế hơn để hỗ trợ kiểm tra giúp anh nhá
[Khách hàng]: cái ngày hai cái ngày sáng ngày hai mươi hai tháng mười một á chị
[Tổng đài viên]: dạ vâng
[Khách hàng]: không giờ bốn mươi phút sáng á là em có thực hiện một bảy giao dịch nhưng mà nó không
[Khách hàng]: nó nó nó nó chịu tiền em nó không hoàn thành cái mã giao dịch
[Tổng đài viên]: sao em xin số căn cước công dân hoặc chúng tư nhân tạo tài khoản ngân hàng để hỗ trợ kiểm tra giao dịch giúp anh nhá
[Khách hàng]: cái số tài khoản ngân hàng á chị
[Tổng đài viên]: mình đọc phố gắn cước công dân hoặc chứng minh thư nhân dân ạ
[Khách hàng]: ờ
[Tổng đài viên]: à
[Khách hàng]: số căn cứ còn viên là không bảy
[Tổng đài viên]: chín
[Tổng đài viên]: dạ vâng
[Khách hàng]: chín chín không
[Tổng đài viên]: dạ vâng ạ
[Khách hàng]: ba năm năm bảy năm
[Tổng đài viên]: mình thực hiện giao dịch vào ngày hai mươi tháng mười một
[Khách hàng]: hai mươi hai hai mươi hai tháng mười một
[Tổng đài viên]: hai hai tháng mười một ạ số tiền là bao tiền vậy anh
[Khách hàng]: một triệu á chị
[Tổng đài viên]: một triệu vào lúc
[Khách hàng]: không giờ bốn mươi không giờ bốn mươi
[Tổng đài viên]: mười bốn mươi phút
[Tổng đài viên]: tức là hiện tại thì anh kiểm tra lại bên phía đơn vị vi en pây thì bên này xác nhận là chưa ghi nhận được cái giao dịch này đúng không anh
[Khách hàng]: đúng rồi
[Tổng đài viên]: dạ vâng trước tiên em rất là xin lỗi anh và trường hợp mình đang ngoài liên quan đến nội dung phản ánh nhá bên em sẽ tiếp nhận thông tin với yêu cầu tra soát đối soát lại giao dịch này trong trường hợp ngày khi có kết quả thì bên phía ngân hàng sẽ phản hồi qua vốn tại đăng ký tại ngân hàng ạ thời gian tra sát và tối đa là năm ngày làm việc không kể thứ bảy chủ nhật và ngày lễ
[Tổng đài viên]: ngoài ra thì trong quá trình mà anh chờ kết quả từ phía nhà em vui lòng lưu ý trong mọi trường hợp giúp em nhá là không cấp thông tin bảo bật như mã ô tê pê số thẻ mã ti vi mật khẩu ngân hàng tố có bất kỳ ai kể cả nhân viên ngân hàng giúp em đây không biết thông tin này ra thì anh tuấn anh cần em hỗ trợ thông tin nào khác không ạ
[Khách hàng]: không hỗ trợ thông tin này giùm mình
[Tổng đài viên]: dạ vâng vậy nếu cần hỗ trợ thông tin an có thể chủ động liên hệ lại sẽ tổng đài giúp em nhá
[Khách hàng]: dạ rồi cám ơn chị""",
        """[Tổng đài viên]: thanh vân dịch vụ khách hàng em long xin em có thể hỗ trợ thông tin gì cho anh
[Khách hàng]: dạ anh ơi ý là là bên em là có thể mờ bê của em là có thể là em bị tổn khóa rồi nhưng mà cái áp mờ bê của em á là em có đổi số điện thoại nên bây giờ làm xét lên thạc là nó nó nó đưa gì số điện thoại mà tờ cũ mà số điện thoại cũ của em là không còn nữa bây giờ làm sao anh
[Tổng đài viên]: dạ vâng tức là hiện tại là anh không đăng nhập được hóa phải không ạ hay là mình đang gặp vấn đề gì vậy ạ
[Khách hàng]: thì đang nhập vào áp là được rồi nhưng mà mình chuyển tiền hay là mình chuyển tiền đi á là bắt buộc là phải có cái sinh hoạt đúng không nhưng mà là cái sinh hoạt là mình mình mình nó gửi cứ cứ cái số mật nói vậy đó qua cái số điện thoại cũ của mình nhưng mà điền số điện thoại cũ của mình là mình không còn nữa
[Tổng đài viên]: sau này thì để hỗ trợ cái ô tê pê đấy thì anh vui lòng ra quầy en mình bên em căn cước công dân đăng ký số loại mới thì để các bạn ấy đăng ký cho anh cái ô tê pê để mình chuyển tiền ấy nhá
[Khách hàng]: ờ vậy hoài luôn hả
[Tổng đài viên]: dạ vâng thế anh bớt chút thời gian ra chi nhánh tin để các bạn ấy hỗ trợ anh nhá
[Khách hàng]: thẻ thì cũng lên nó không khó mã
[Khách hàng]: không
[Tổng đài viên]: à dạ vâng cái này chỉ hỗ trợ được này chi nhánh thôi anh ạ thì có gì em bớt thức thờ gian ra chi nhánh hộ em nhá
[Khách hàng]: vâng ô kê ô kê""",
        """[Tổng đài viên]: trung tâm dịch vụ khách hàng quỳnh anh xin nghe em có thể hỗ trợ thông tin để cho anh chị
[Khách hàng]: chị ơi em vừa mới đăng ký ở trên áp ấy đăng ký để mở cái thẻ ứng dụng ấy chị
[Tổng đài viên]: cho em xin tên của anh để tiện trao đổi ạ
[Khách hàng]: nguyễn văn anh
[Tổng đài viên]: dạ vâng thì em phan anh cần hỗ trợ thông tin vì gì về thẻ tín dụng ạ
[Khách hàng]: thế em đăng ký như bây giờ đăng ký ở trên áp đấy gì
[Khách hàng]: bây giờ chờ để về thì mình mới kích hoạt được rồi
[Tổng đài viên]: trường hợp này để hỗ trợ bảo mật thì anh thửi do anh văn anh cho em xin lại số căn cước không gian đăng ký ngân hàng em hỗ trợ kiểm tra
[Khách hàng]: không không một không chín năm
[Tổng đài viên]: dạ vâng ạ
[Khách hàng]: không hai ba bốn bảy một
[Tổng đài viên]: dạ vâng ạ cho em xin tên đầy đủ một tháng năm sinh của mình ạ
[Khách hàng]: nguyễn văn anh hai hai tháng chín năm một chín chín năm
[Tổng đài viên]: dạ vâng ạ
[Tổng đài viên]: cho em hỏi là anh đang phát hành thẻ nào đấy ạ đọc cho em bốn số cuối của thẻ
[Khách hàng]: rồi
[Tổng đài viên]: mình đang phát hành một cái thẻ là thẻ đa năng
[Tổng đài viên]: phát anh vào ngày bên bay đúng không anh
[Khách hàng]: tám tám sáu không
[Tổng đài viên]: ngày hôm nay em thấy anh phát hành ạ là thẻ đa năng thẻ vi da hai rít ạ thẻ này của anh đang để là thẻ phi vật lý mình chưa có phát hành thẻ cứng ạ em văn anh cần phải chọn một phần in thẻ vật lý anh nhập địa chỉ nhà thì trong khoảng từ năm đến bảy ngày ngân hàng trừ thứ bảy chủ nhật ngân hàng sẽ tiến hành giao thẻ về địa chỉ nhà cho anh ạ
[Khách hàng]: thế
[Tổng đài viên]: đúng rồi ạ mình phải chọn vào phần in thẻ vật lý cơ
[Tổng đài viên]: thì ngân hàng mà tiến hành hỗ trợ in thẻ về nhà được
[Khách hàng]: vậy qua rô về in thẻ ra hả chị
[Tổng đài viên]: đúng rồi ạ còn không thì nó sẽ là thẻ phi vật lý ở trên áp thôi
[Khách hàng]: đâu có rút từ tiền ở trong áp và luôn không mà giờ phải bắt đầu phải đi trời rút ở trên thị
[Tổng đài viên]: thẻ của anh là thẻ đa năng thẻ phi vật lý thẻ này có hỗ trợ rút tiền mặt
[Tổng đài viên]: thúc tiền từ hạn mức của thể của tài khoản thanh toán luôn vì thẻ này của anh không có hạn mức tín dụng
[Khách hàng]: thể của em vì tình bao tiền hả chị
[Tổng đài viên]: thẻ này của anh không có hạn mức ạ mình chưa được các hạn mức của thẻ tín dụng anh văn anh ạ
[Khách hàng]: dạ
[Khách hàng]: làm thế nào để được các bạn mức hả chị
[Tổng đài viên]: muốn cấp hạn mức thì anh sẽ chi tiêu nhiều hơn ở trên thẻ này để có lịch sử chi tiêu lịch sử tín dụng ngân hàng quân đội sẽ tự động thẩm định dựa trên những cái lịch sử này
[Tổng đài viên]: có điều đủ điều kiện cấp thẻ hạn mất có tín dụng có hạn mức ngân hàng sẽ gửi thông báo cho anh văn anh ạ
[Khách hàng]: vâng em cảm ơn anh
[Tổng đài viên]: dạ vâng anh cần em hỗ trợ thông tin nào khác được không anh
[Khách hàng]: rồi rồi
[Tổng đài viên]: em xin phép ứng yêu cầu khi nào cần hỗ trợ kết nối tổng đài giúp em cảm ơn em chào anh quan anh"""
    ]
    
    # token = get_keycloak_token()
    # conversation = CONVERSATIONS[0]
    
    # result = make_extraction_request(
    #     url=url, 
    #     conversation=conversation, 
    #     request_time="hihi", 
    #     token=token
    # )
    
    # print(result)

    total_start_time = time.time()
    results = []
    num_requests = 20
    
    for i in range(num_requests):
        token = get_keycloak_token()
        # Get random conversation
        conversation = generate_random_words(10, 3, 7) + random.choice(CONVERSATIONS)
        
        # Generate request time (current time plus random minutes)
        request_time = (datetime.now() + timedelta(minutes=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S.000")
        
        # Make request
        result = make_extraction_request(url, conversation, request_time, token)
        
        # Print progress
        print(f"\nRequest {i+1}/{num_requests}, length = {len(conversation.split())}")
        if 'error' in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Response: {json.dumps(result['response_data'], indent=2, ensure_ascii=False)}")
        print(f"Execution time: {result['execution_time']:.3f} seconds")
        print(f"Status code: {result['status_code']}")
        
        results.append(result)
        
        # Add small delay between requests
        time.sleep(0.5)
    
    # Calculate and print summary statistics
    total_time = time.time() - total_start_time
    successful_requests = len([r for r in results if 'error' not in r])
    avg_execution_time = sum(r['execution_time'] for r in results) / len(results)
    
    print("\nSummary:")
    print(f"Total requests: {num_requests}")
    print(f"Successful requests: {successful_requests}")
    print(f"Failed requests: {num_requests - successful_requests}")
    print(f"Average execution time: {avg_execution_time:.3f} seconds")
    print(f"Total run time: {total_time:.3f} seconds")