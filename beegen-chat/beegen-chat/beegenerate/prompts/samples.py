DOCUMENT_FILTER_PROMPT = """Vai trò: Chuyên gia đánh giá và lọc tài liệu thông minh

Nhiệm vụ: 
1. Đánh giá từng tài liệu có liên quan đến câu hỏi không
2. Đánh giá tổng thể xem các tài liệu liên quan có thể trả lời được câu hỏi không

=== QUY TẮC ĐÁNH GIÁ TỪNG TÀI LIỆU ===

CÓ LIÊN QUAN nếu tài liệu:
- Chứa thông tin cụ thể về chủ đề được hỏi
- Đề cập đến sản phẩm/dịch vụ trong câu hỏi (kể cả một phần)
- Có thể đóng góp thông tin để trả lời câu hỏi (dù không đầy đủ)
- Liên quan đến ngữ cảnh hoặc lĩnh vực của câu hỏi

KHÔNG LIÊN QUAN chỉ khi tài liệu:
- Hoàn toàn không đề cập đến chủ đề được hỏi
- Về lĩnh vực/sản phẩm hoàn toàn khác không liên quan

=== QUY TẮC XỬ LÝ CÁC TRƯỜNG HỢP ĐẶC BIỆT ===

1. **Câu hỏi SO SÁNH** ("so sánh A và B", "khác biệt giữa A và B"):
   - Tài liệu về A hoặc B đều CÓ LIÊN QUAN
   - OVERALL_RELEVANT = true nếu có tài liệu về ít nhất một trong hai

2. **Câu hỏi TỔNG HỢP** ("các loại", "tất cả", "danh sách"):
   - Tài liệu về bất kỳ mục nào trong phạm vi đều CÓ LIÊN QUAN
   - OVERALL_RELEVANT = true nếu có ít nhất một tài liệu liên quan

3. **Câu hỏi về NHÓM SẢN PHẨM** ("thẻ tín dụng", "dịch vụ ngân hàng"):
   - Tài liệu về bất kỳ sản phẩm nào trong nhóm đều CÓ LIÊN QUAN
   - OVERALL_RELEVANT = true nếu có thông tin về nhóm sản phẩm đó

4. **Câu hỏi CỤ THỂ về một chủ đề**:
   - Tài liệu phải chứa thông tin trực tiếp về chủ đề đó
   - OVERALL_RELEVANT = true nếu có đủ thông tin chi tiết

=== QUY TẮC ĐÁNH GIÁ TỔNG THỂ ===

OVERALL_RELEVANT = true khi:
- Có ít nhất 1 tài liệu liên quan chứa thông tin hữu ích
- Các tài liệu kết hợp có thể cung cấp câu trả lời (dù từng phần)
- Đối với câu hỏi so sánh: có thông tin về ít nhất một đối tượng
- Đối với câu hỏi tổng hợp: có thông tin về ít nhất một phần của tổng thể

OVERALL_RELEVANT = false chỉ khi:
- Không có tài liệu nào liên quan đến câu hỏi
- Tất cả tài liệu đều về chủ đề hoàn toàn khác

=== VÍ DỤ PHÂN TÍCH ===

Ví dụ 1: "So sánh thẻ JCB và thẻ Visa"
- Tài liệu về thẻ JCB → CÓ LIÊN QUAN
- Tài liệu về thẻ Visa → CÓ LIÊN QUAN  
- Có ít nhất 1 tài liệu về JCB hoặc Visa → OVERALL_RELEVANT = true

Ví dụ 2: "Các loại thẻ tín dụng của MB"
- Tài liệu về bất kỳ thẻ tín dụng nào → CÓ LIÊN QUAN
- Có thông tin về thẻ tín dụng → OVERALL_RELEVANT = true

Ví dụ 3: "Phí thường niên thẻ Visa Infinite"
- Tài liệu về thẻ Visa Infinite với thông tin phí → CÓ LIÊN QUAN
- Tài liệu về thẻ Visa khác (không phải Infinite) → KHÔNG LIÊN QUAN
- Có thông tin cụ thể về Visa Infinite → OVERALL_RELEVANT = true/false

=== NGUYÊN TẮC QUAN TRỌNG ===
- **THOÁNG HƠN**: Ưu tiên giữ lại tài liệu có thể hữu ích thay vì loại bỏ quá nhiều
- **NGỮ CẢNH**: Xem xét mối liên hệ gián tiếp và khả năng kết hợp thông tin
- **THỰC DỤNG**: Đánh giá khả năng trả lời được câu hỏi từ các tài liệu có sẵn

Không đưa ra bất cứ phân tích nào, chỉ trả về XML với list IDs của các tài liệu CÓ LIÊN QUAN:
<relevant_docs>[1, 3, 5]</relevant_docs>
<overall_relevant>true</overall_relevant>

Nếu không có tài liệu nào liên quan:
<relevant_docs></relevant_docs>
<overall_relevant>false</overall_relevant>

Danh sách tài liệu:

============================================================ID: 0
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
2. DẤU HIỆU NHẬN BIẾT

•	Thẻ có logo MB và logo Tổ chức thẻ quốc tế Mastercard

•	Không in tên Khách hàng, không in số thẻ trên thẻ, có hình ảnh minh họa tùy theo bộ sưu tập thẻ.

•	1 chip và hình ảnh cột sóng contactless được tích hợp 2 tính năng của thẻ ghi nợ và thẻ tín dụng.

•	Trên hệ thống MB ghi nhận số BIN thẻ: 530416 

•	Thời hạn sử dụ
ID: 1
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
5. TÍNH NĂNG SẢN PHẨM
5.5 Giao dịch qua dịch vụ SMS Banking

KH có thể sử dụng dịch vụ SMS Banking để thực hiện một số tính năng:

•	Mở khóa thẻ: KH soạn tin theo cú pháp: MB MOKHOATHE SốCMT 4Sốđầuthẻ 4sốcuốithẻ gửi 8136

•	Khóa thẻ: KH soạn tin theo cú pháp: MB KHOATHE SốCMT 4Sốđầuthẻ 4sốcuốithẻ gửi 8136

•	Mở 3D Secure: KH soạn tin theo cú ph
ID: 2
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
5. TÍNH NĂNG SẢN PHẨM
5.3 Trên Internet

•	Thanh toán hàng hóa, dịch vụ (Thanh toán ecom - Thanh toán online) (trong và ngoài nước): sử dụng hạn mức thẻ tín dụng, nếu hạn mức thẻ tín dụng không đủ chuyển sử dụng nguồn TKTT. Giao dịch này không cần nhập PIN, tuy nhiên khi thực hiện giao dịch thanh toán online, 1 số đơn vị chấp nhận thẻ (ĐVCNT) (
ID: 3
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
9. LÃI SUẤT - PHÍ
9.4	Quy định khác

•	Phí và lãi cho giao dịch: 

-	Giao dịch thanh toán hàng hóa dịch vụ: không phải chịu phí. Chủ thẻ chỉ phải trả lãi cho giao dịch khi không thanh toán toàn bộ dư nợ sao kê đúng hạn.

-	Giao dịch rút tiền mặt: phải chịu phí rút tiền mặt và lãi tính từ ngày phát sinh giao dịch đến ngày thanh toán hết toàn bộ 
ID: 4
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
3. ĐỐI TƯỢNG KHÁCH HÀNG

	Áp dụng đối với tất cả các KHCN là người cư trú tại Việt Nam đủ điều kiện phát hành thẻ của MB và pháp luật.

	Độ tuổi: Từ 18-70 tuổi


ID: 5
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
5. TÍNH NĂNG SẢN PHẨM
5.2 Giao dịch rên POS

•	Thanh toán hàng hóa, dịch vụ (quẹt thẻ) (không cần nhập PIN) (trong và ngoài nước): sử dụng hạn mức thẻ tín dụng, nếu hạn mức thẻ tín dụng không đủ chuyển sử dụng nguồn TKTT


ID: 6
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
9. LÃI SUẤT - PHÍ
9.2 Phương pháp tính lãi

•	Cơ sở tính lãi: 1 năm có 365 ngày

•	Các giao dịch rút tiền mặt, vay siêu nhanh từ thẻ tín dụng không được miễn lãi

•	KH được miễn lãi trên các giao dịch thanh toán tại POS, Internet khi thanh toán 100% dư nợ trước 15h ngày đến hạn thanh toán, miễn lãi TỐI ĐA 45 ngày => Giải thích: Các giao dịch ch
ID: 7
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
2. DẤU HIỆU NHẬN BIẾT
2.3 Nhận diện thẻ

•	Thẻ có logo Tổ chức thẻ quốc tế MasterCard.

•	Không in tên Khách hàng, không in số thẻ trên thẻ, có hình ảnh minh họa tùy theo bộ sưu tập thẻ

•	1 chip và hình ảnh cột sóng contactless được tích hợp 2 tính năng của thẻ ghi nợ và thẻ tín dụng

•	Hình ảnh phôi 
ID: 8
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
8. QUY ĐỊNH VỀ THANH TOÁN SAO KÊ
8.3 Thứ tự ưu tiên thanh toán

MB thực hiện việc thu nợ theo thứ tự thời gian thực hiện giao dịch và theo thứ tự ưu tiên thanh toán số dư nợ, cụ thể như sau:

a, Dư nợ trong hạn - Thẻ tín dụng khi không có giao dịch trả góp và chỉ có giao dịch chi tiêu thông thường:

Hệ
ID: 9
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
5. TÍNH NĂNG SẢN PHẨM
5.2 Trên POS

Thanh toán hàng hóa, dịch vụ (quẹt thẻ) (không cần nhập PIN) (trong và ngoài nước): Sử dụng hạn mức thẻ tín dụng, nếu hạn mức thẻ tín dụng không đủ chuyển sử dụng nguồn TKTT


ID: 10
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
8. QUY ĐỊNH VỀ THANH TOÁN SAO KÊ
8.2 Hình thức thanh toán, Số tiền thanh toán

•	Thanh toán bằng tiền mặt: KH thực hiện nộp tiền mặt vào thẻ tại bất kỳ CRM 24/7 hoặc CN/PGD MB gần nhất vào các ngày làm việc trong tuần.

•	Thanh toán trích nợ tự động từ TKTT của KH: KH lựa chọn 1 trong 2 tỷ lệ thanh toá
ID: 11
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
9. LÃI SUẤT - PHÍ
9.1 Phương pháp tính lãi

•	Cơ sở tính lãi: 1 năm có 365 ngày

•	Các giao dịch rút tiền mặt, vay siêu nhanh từ thẻ tín dụng không được miễn lãi

•	KH được miễn lãi trên các giao dịch thanh toán tại POS, Internet khi thanh toán 100% dư nợ trước 15h ngày đến hạn thanh toán, miễn lãi TỐI
ID: 12
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
11. QUY ĐỊNH VỀ NÂNG HẠNG THẺ

•	Thẻ Dual và thẻ Hi Collection chỉ có 1 hạng trên hệ thống MB - hạng Gold

•	Trong trường hợp KH muốn nâng hạng (Platinum, Priority Platinum, Infinite): KH sẽ phát hành theo luồng thẻ Visa/JCB Credit để nâng hạng


ID: 13
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
2. DẤU HIỆU NHẬN BIẾT
2.2 Hình ảnh thẻ

Số lượng mẫu thẻ: 12 mẫu thẻ: AHRI; ASHE; BLITZCRANK; CAILYN; GAREN; KENNEN; LEE SIN; LUCIAN; LULU; LUX; RYZE; SAMIRA; TWISTED FATE; WUKONG; XIN ZHAO.


ID: 14
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
11. Các quy định khác

* Phí và lãi cho giao dịch: 

- Giao dịch thanh toán hàng hóa dịch vụ: không phải chịu phí. Chủ thẻ chỉ phải trả lãi cho giao dịch khi không thanh toán toàn bộ dư nợ sao kê đúng hạn.

- Giao dịch rút tiền mặt: phải chịu phí rút tiền mặt và lãi tính từ ngày phát sinh giao dịch đến ngày thanh toán hết toàn bộ số tiền giao dịch.

- Giao dị
ID: 15
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
12. Quy định về gia hạn và phát hành lại

- Với thẻ đa năng Hi Collection không gia hạn thẻ, thẻ hết hạn Khách hàng phát hành thẻ khác thay thế

- Thẻ Hi Collection: Không phát hành lại được


ID: 16
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
b, Dư nợ trong hạn - Thẻ tín dụng khi có cả giao dịch trả góp và giao dịch chi tiêu thông thường:

Hệ thống thực hiện quét thu theo thứ tự:

- Dư nợ trả góp hàng tháng theo kỳ sao kê: phí quản lý trả góp, dư nợ gốc trả góp hàng tháng theo kỳ sao kê. Tiếp đó thực hiện thu: 

- Dư nợ thông thường của thẻ tín dụng: Phí, phạt chậm thanh toán (nếu có) của dư nợ th
ID: 17
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
5.2 Trên POS:

Thanh toán hàng hóa, dịch vụ (quẹt thẻ) (không cần nhập PIN) (trong và ngoài nước): sử dụng hạn mức thẻ tín dụng, nếu hạn mức thẻ tín dụng không đủ chuyển sử dụng nguồn TKTT


ID: 18
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
8. Luồng đăng ký phát hành thẻ

Đăng ký phát hành & sử dụng thẻ phi vật lý:

Bước 1: Đăng nhập APP MBBank, Chọn "Thẻ" tại thanh điều hướng cuối màn hình
 Bước 2: Chọn "Phát hành thẻ"
 Bước 3: Tại tab thẻ đa năng, chọn "Tất cả"
 Bước 4: Chọn thẻ đa năng Hi Green, chọn tài khoản gắn thẻ và tỷ lệ thanh toán sao kê hàng tháng
 Bước 5: Chọn "Tiếp tục"
 Bước 6: Tại
ID: 19
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
9.3 Thứ tự ưu tiên thanh toán: 

MB thực hiện việc thu nợ theo thứ tự thời gian thực hiện giao dịch và theo thứ tự ưu tiên thanh toán số dư nợ, cụ thể như sau:


ID: 20
Nội dung: 54. Thẻ đa năng MB Mastercard Hi Green
6. Hạn mức tín dụng

- Tùy chọn hạn mức dựa trên hạn mức thẻ tín dụng MB hiện tại/ hạn mức tín dụng được MB cấp: 

     + Nếu thẻ tín dụng đang hoạt động hiện tại có hạn mức < 1,000,000 VND => Hạn mức thẻ Hybrid = 0

     + Nếu thẻ tín dụng đang hoạt động hiện tại có hạn mức >= 1,000,000 VND => Hạn mức thẻ Hybird = tùy chọn tối thiểu 1,000,000 VND, tối đa = h
ID: 21
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
2. DẤU HIỆU NHẬN BIẾT

•	Thẻ có logo MB và logo Tổ chức thẻ quốc tế Mastercard

•	Không in tên Khách hàng, không in số thẻ trên thẻ, có hình ảnh minh họa tùy theo bộ sưu tập thẻ.

•	1 chip và hình ảnh cột sóng contactless được tích hợp 2 tính năng của thẻ ghi nợ và thẻ tín dụng.

•	Trên hệ thống MB ghi nhận số BIN thẻ: 530416 

•	Thời hạn sử dụ
ID: 22
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
3. ĐỐI TƯỢNG KHÁCH HÀNG

	Áp dụng đối với tất cả các KHCN là người cư trú tại Việt Nam đủ điều kiện phát hành thẻ của MB và pháp luật.

	Độ tuổi: Từ 18-70 tuổi


ID: 23
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
5. TÍNH NĂNG SẢN PHẨM
5.2 Giao dịch rên POS

•	Thanh toán hàng hóa, dịch vụ (quẹt thẻ) (không cần nhập PIN) (trong và ngoài nước): sử dụng hạn mức thẻ tín dụng, nếu hạn mức thẻ tín dụng không đủ chuyển sử dụng nguồn TKTT


ID: 24
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
5. TÍNH NĂNG SẢN PHẨM
5.1 Giao dịch trên ATM/CRM

•	Rút tiền mặt (trong và ngoài nước):  

+ Giao dịch rút tiền trong nước: Sử dụng nguồn tiền tài khoản thanh toán

+ Giao dịch rút tiền nước ngoài: Sử dụng hạn mức thẻ tín dụng

•	Đổi PIN (chỉ áp dụng ATM MB)

•	Truy vấn hạn mức khả dụng

•	Sao kê 05 giao dịch gần nhất


ID: 25
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
4. QUY ĐỊNH VỀ THẺ CHÍNH, THẺ PHỤ

•	Không có thẻ phụ;

•	Tổng số lượng thẻ phát hành/định danh: 15 thẻ và mỗi sản phẩm không quá tối đa 10 thẻ (bao gồm cả thẻ đóng và thẻ đang hoạt động)

Lưu ý: Trường hợp KH đã vượt quá số thẻ được phép định danh (tối đa 15 thẻ và mỗi loại sản phẩm không quá tối đa 10 thẻ), nếu đóng thẻ thì sau thời gian 3 th
ID: 26
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
9. LÃI SUẤT - PHÍ
9.3 Quy định về phí thẻ Hi Slay-dy

•	Phí phát hành thẻ (đã bao gồm VAT):

Theo biểu phí được Quy định từng thời kỳ, tham khảo thêm biểu phí thẻ tín dụng tại đây: https://www.mbbank.com.vn/resources/files/BIEU-PHI/2025/KHCN---THE/2-bieu-phi-the-hi-collection---20250214.pdf 

•	Phí thường niên: 

Theo biểu phí được Quy định từn
ID: 27
Nội dung: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection)
12. QUY ĐỊNH VỀ PHÁT HÀNH LẠI THẺ

Không phát hành lại được, KH cần phát hành thẻ mới thay thế


ID: 28
Nội dung: File tài liệu: 48. Thẻ Hi Slay-dy (Hi Slay-dy Mastercard Collection).docx
Câu hỏi: Tôi có thể làm tối đa bao nhiêu thẻ Hi Collection?
Câu trả lời: Không giới hạn số thẻ mua /Khách hàng.
- Một tài khoản sẽ được định danh tối đa 10 thẻ
ID: 29
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
1. ĐỊNH NGHĨA SẢN PHẨM

-	Là dòng thẻ Hybrid – thẻ đa năng được kết hợp 2 tính năng của thẻ tín dụng và thẻ ghi nợ trên 1 thẻ mang thương hiệu tổ chức thẻ MasterCard, sử dụng nguồn tiền từ hạn mức thẻ tín dụng và số dư Tài khoản thanh toán để giao dịch.

-	Dòng thẻ đặc biệt hướng tới Khách hàng thuộc c
ID: 30
Nội dung: 60. Thẻ đa năng Master Hi League Of Legends (Hi LOL) (1)
THẺ ĐA NĂNG MASTER HI LEAGUE OF LEGENDS
2. DẤU HIỆU NHẬN BIẾT
2.1 Hình thức thẻ

Thẻ vật lý (KH thực hiện mua thẻ vật lý trên App MBBank/ Shopee (MBBank Offical) khi có nhu cầu)



Câu hỏi: thẻ hi slay có gì hay ho?"""