L1 = ["Tín dụng", "Huy động vốn", "Kiều hối", "Sản phẩm đầu tư", "Bancas", "Thẻ tín dụng"]

MAJOR = """
Trồng lúa
Trồng ngô và cây lương thực có hạt khác
Trồng cây lấy củ có chất bột
Trồng cây mía
Trồng cây thuốc lá, thuốc lào
Trồng cây lấy sợi
Trồng cây có hạt chứa dầu
Trồng rau các loại
Trồng đậu các loại
Trồng hoa hàng năm
Trồng cây gia vị hàng năm
Trồng cây dược liệu, hương liệu hàng năm
Trồng cây hàng năm khác còn lại
Trồng nho
Trồng cây ăn quả vùng nhiệt đới và cận nhiệt đới
Trồng cam, quýt và các loại quả có múi khác
Trồng táo, mận và các loại quả có hạt như táo
Trồng nhãn, vải, chôm chôm
Trồng cây ăn quả khác
Trồng cây lấy quả chứa dầu
Trồng cây điều
Trồng cây hồ tiêu
Trồng cây cao su
Trồng cây cà phê
Trồng cây chè
Trồng cây gia vị lâu năm
Trồng cây dược liệu, hương liệu lâu năm
Trồng cây cảnh lâu năm
Trồng cây lâu năm khác còn lại
Nhân và chăm sóc cây giống hàng năm
Nhân và chăm sóc cây giống lâu năm
Sản xuất giống trâu, bò
Chăn nuôi trâu, bò
Sản xuất giống ngựa, lừa
Chăn nuôi ngựa, lừa, la
Sản xuất giống dê, cừu, hươu, nai
Chăn nuôi dê, cừu, hươu, nai
Sản xuất giống lợn
Chăn nuôi lợn
Hoạt động ấp trứng và sản xuất giống gia cầm
Chăn nuôi gà
Chăn nuôi vịt, ngan, ngỗng
Chăn nuôi gia cầm khác
Chăn nuôi khác
Trồng trọt, chăn nuôi hỗn hợp
Hoạt động dịch vụ trồng trọt
Hoạt động dịch vụ chăn nuôi
Hoạt động dịch vụ sau thu hoạch
Xử lý hạt giống để nhân giống
Săn bắt, đánh bẫy và hoạt động dịch vụ có liên quan
Trồng rừng và chăm sóc rừng cây thân gỗ
Trồng rừng và chăm sóc rừng họ tre
Trồng rừng và chăm sóc rừng khác
Ươm giống cây lâm nghiệp
Khai thác gỗ
Khai thác lâm sản khác trừ gỗ
Thu nhặt lâm sản khác trừ gỗ
Hoạt động dịch vụ lâm nghiệp
Khai thác thủy sản biển
Khai thác thủy sản nội địa
Nuôi cá
Nuôi tôm*
Nuôi thủy sản khác
Sản xuất giống thủy sản biển
Nuôi cá
Nuôi tôm
Nuôi thủy sản khác
Sản xuất giống thủy sản nội địa
Khai thác và thu gom than cứng
Khai thác và thu gom than non
Khai thác dầu thô
Khai thác khí đốt tự nhiên
Khai thác quặng sắt
Khai thác quặng uranium và quặng thorium
Khai thác quặng bôxít
Khai thác quặng kim loại khác không chứa sắt chưa được phân vào đâu
Khai thác quặng kim loại quý hiếm
Khai thác đá
Khai thác cát, sỏi
Khai thác đất sét
Khai thác khoáng hoá chất và khoáng phân bón
Khai thác và thu gom than bùn
Khai thác muối
Khai khoáng khác chưa được phân vào đâu
Hoạt động dịch vụ hỗ trợ khai thác dầu thô và khí tự nhiên
Hoạt động dịch vụ hỗ trợ khai khoáng khác
Giết mổ gia súc, gia cầm
Chế biến và bảo quản thịt
Chế biến và bảo quản các sản phẩm từ thịt
Chế biến và bảo quản thủy sản đông lạnh
Chế biến và bảo quản thủy sản khô
Chế biến và bảo quản nước mắm
Chế biến và bảo quản các sản phẩm khác từ thủy sản
Sản xuất nước ép từ rau quả
Chế biến và bảo quản rau quả khác
Sản xuất dầu, mỡ động vật
Sản xuất dầu, bơ thực vật
Chế biến sữa và các sản phẩm từ sữa
Xay xát
Sản xuất bột thô
Sản xuất tinh bột và các sản phẩm từ tinh bột
Sản xuất các loại bánh từ bột
Sản xuất đường
Sản xuất ca cao, sôcôla và bánh kẹo
Sản xuất mì ống, mỳ sợi và sản phẩm tương tự
Sản xuất món ăn, thức ăn chế biến sẵn từ thịt
Sản xuất món ăn, thức ăn chế biến sẵn từ thủy sản
Sản xuất món ăn, thức ăn chế biến sẵn khác
Sản xuất chè
Sản xuất cà phê
Sản xuất thực phẩm khác chưa được phân vào đâu
Sản xuất thức ăn gia súc, gia cầm và thuỷ sản
Chưng, tinh cất và pha chế các loại rượu mạnh
Sản xuất rượu vang
Sản xuất bia và mạch nha ủ men bia
Sản xuất nước khoáng, nước tinh khiết đóng chai
Sản xuất đồ uống không cồn
Sản xuất thuốc lá
Sản xuất thuốc hút khác
Sản xuất sợi
Sản xuất vải dệt thoi
Hoàn thiện sản phẩm dệt
Sản xuất vải dệt kim, vải đan móc và vải không dệt khác
Sản xuất hàng dệt sẵn (trừ trang phục)
Sản xuất thảm, chăn, đệm
Sản xuất các loại dây bện và lưới
Sản xuất các loại hàng dệt khác chưa được phân vào đâu
May trang phục (trừ trang phục từ da lông thú)
Sản xuất sản phẩm từ da lông thú
Sản xuất trang phục dệt kim, đan móc
Thuộc, sơ chế da; sơ chế và nhuộm da lông thú
Sản xuất vali, túi xách và các loại tương tự, sản xuất yên đệm
Sản xuất giày, dép
Cưa, xẻ và bào gỗ
Bảo quản gỗ
Sản xuất gỗ dán, gỗ lạng, ván ép và ván mỏng khác
Sản xuất đồ gỗ xây dựng
Sản xuất bao bì bằng gỗ
Sản xuất sản phẩm khác từ gỗ
Sản xuất sản phẩm từ lâm sản (trừ gỗ), cói và vật liệu tết bện
Sản xuất bột giấy, giấy và bìa
Sản xuất bao bì bằng giấy, bìa
Sản xuất giấy nhăn và bìa nhăn
Sản xuất các sản phẩm khác từ giấy và bìa chưa được phân vào đâu
In ấn
Dịch vụ liên quan đến in
Sao chép bản ghi các loại
Sản xuất than cốc
Sản xuất sản phẩm dầu mỏ tinh chế
Sản xuất khí công nghiệp
Sản xuất chất nhuộm và chất màu
Sản xuất hóa chất vô cơ cơ bản khác
Sản xuất hoá chất hữu cơ cơ bản khác
Sản xuất hóa chất cơ bản khác
Sản xuất phân bón và hợp chất ni tơ
Sản xuất plastic nguyên sinh
Sản xuất cao su tổng hợp dạng nguyên sinh
Sản xuất thuốc trừ sâu và sản phẩm hoá chất khác dùng trong nông nghiệp
Sản xuất sơn, véc ni và các chất sơn, quét tương tự, ma tít
Sản xuất mực in
Sản xuất mỹ phẩm
Sản xuất xà phòng, chất tẩy rửa, làm bóng và chế phẩm vệ sinh
Sản xuất sản phẩm hoá chất khác chưa được phân vào đâu
Sản xuất sợi nhân tạo
Sản xuất thuốc các loại
Sản xuất hoá dược và dược liệu
Sản xuất săm, lốp cao su; đắp và tái chế lốp cao su
Sản xuất sản phẩm khác từ cao su
Sản xuất bao bì từ plastic
Sản xuất sản phẩm khác từ plastic
Sản xuất thủy tinh phẳng và sản phẩm từ thủy tinh phẳng
Sản xuất thủy tinh rỗng và sản phẩm từ thủy tinh rỗng
Sản xuất sợi thủy tinh và sản phẩm từ sợi thủy tinh
Sản xuất thủy tinh khác và các sản phẩm từ thủy tinh
Sản xuất sản phẩm chịu lửa
Sản xuất vật liệu xây dựng từ đất sét
Sản xuất sản phẩm gốm sứ khác
Sản xuất xi măng
Sản xuất vôi
Sản xuất thạch cao
Sản xuất bê tông và các sản phẩm từ bê tông, xi măng và thạch cao
Cắt tạo dáng và hoàn thiện đá
Sản xuất sản phẩm từ chất khoáng phi kim loại khác chưa được phân vào đâu
Sản xuất sắt, thép, gang
Sản xuất kim loại quý
Sản xuất kim loại màu
Đúc sắt, thép
Đúc kim loại màu
Sản xuất các cấu kiện kim loại
Sản xuất thùng, bể chứa và dụng cụ chứa đựng bằng kim loại
Sản xuất nồi hơi (trừ nồi hơi trung tâm)
Sản xuất vũ khí và đạn dược
Rèn, dập, ép và cán kim loại; luyện bột kim loại
Gia công cơ khí; xử lý và tráng phủ kim loại
Sản xuất dao kéo, dụng cụ cầm tay và đồ kim loại thông dụng
Sản xuất đồ dùng bằng kim loại cho nhà bếp, nhà vệ sinh và nhà ăn
Sản xuất sản phẩm khác còn lại bằng kim loại chưa được phân vào đâu
Sản xuất linh kiện điện tử
Sản xuất máy vi tính và thiết bị ngoại vi của máy vi tính
Sản xuất thiết bị truyền thông
Sản xuất sản phẩm điện tử dân dụng
Sản xuất thiết bị đo lường, kiểm tra, định hướng và điều khiển
Sản xuất đồng hồ
Sản xuất thiết bị bức xạ, thiết bị điện tử trong y học, điện liệu pháp
Sản xuất thiết bị và dụng cụ quang học
Sản xuất băng, đĩa từ tính và quang học
Sản xuất mô tơ, máy phát
Sản xuất biến thế điện, thiết bị phân phối và điều khiển điện
Sản xuất pin và ắc quy
Sản xuất dây cáp, sợi cáp quang học
Sản xuất dây, cáp điện và điện tử khác
Sản xuất thiết bị dây dẫn điện các loại
Sản xuất thiết bị điện chiếu sáng
Sản xuất đồ điện dân dụng
Sản xuất thiết bị điện khác
Sản xuất động cơ, tua bin (trừ động cơ máy bay, ô tô, mô tô và xe máy)
Sản xuất thiết bị sử dụng năng lượng chiết lưu
Sản xuất máy bơm, máy nén, vòi và van khác
Sản xuất bi, bánh răng, hộp số, các bộ phận điều khiển và truyền chuyển động
Sản xuất lò nướng, lò luyện và lò nung
Sản xuất các thiết bị nâng, hạ và bốc xếp
Sản xuất máy móc và thiết bị văn phòng (trừ máy vi tính và thiết bị ngoại vi của máy vi tính)
Sản xuất dụng cụ cầm tay chạy bằng mô tơ hoặc khí nén
Sản xuất máy thông dụng khác
Sản xuất máy nông nghiệp và lâm nghiệp
Sản xuất máy công cụ và máy tạo hình kim loại
Sản xuất máy luyện kim
Sản xuất máy khai thác mỏ và xây dựng
Sản xuất máy chế biến thực phẩm, đồ uống và thuốc lá
Sản xuất máy cho ngành dệt, may và da
Sản xuất máy sản xuất vật liệu xây dựng
Sản xuất máy chuyên dụng khác chưa được phân vào đâu
Sản xuất ô tô và xe có động cơ khác
Sản xuất thân xe ô tô và xe có động cơ khác, rơ moóc và bán rơ moóc
Sản xuất phụ tùng và bộ phận phụ trợ cho xe ô tô và xe có động cơ khác
Đóng tàu và cấu kiện nổi
Đóng thuyền, xuồng thể thao và giải trí
Sản xuất đầu máy xe lửa, xe điện và toa xe
Sản xuất máy bay, tàu vũ trụ và máy móc liên quan
Sản xuất xe cơ giới chiến đấu dùng trong quân đội
Sản xuất mô tô, xe máy
Sản xuất xe đạp và xe cho người khuyết tật
Sản xuất phương tiện và thiết bị vận tải khác chưa được phân vào đâu
Sản xuất giường, tủ, bàn, ghế bằng gỗ
Sản xuất giường, tủ, bàn, ghế bằng kim loại
Sản xuất giường, tủ, bàn, ghế bằng vật liệu khác
Sản xuất đồ kim hoàn và chi tiết liên quan
Sản xuất đồ giả kim hoàn và chi tiết liên quan
Sản xuất nhạc cụ
Sản xuất dụng cụ thể dục, thể thao
Sản xuất đồ chơi, trò chơi
Sản xuất thiết bị, dụng cụ y tế, nha khoa
Sản xuất dụng cụ chỉnh hình, phục hồi chức năng
Sản xuất khác chưa được phân vào đâu
Sửa chữa các sản phẩm kim loại đúc sẵn
Sửa chữa máy móc, thiết bị
Sửa chữa thiết bị điện tử và quang học
Sửa chữa thiết bị điện
Sửa chữa và bảo dưỡng phương tiện vận tải (trừ ô tô, mô tô, xe máy và xe có động cơ khác)
Sửa chữa thiết bị khác
Lắp đặt máy móc và thiết bị công nghiệp
Thủy điện
Nhiệt điện than
Nhiệt điện khí
Điện hạt nhân
Điện gió
Điện mặt trời
Điện khác
Truyền tải điện
Phân phối điện
Sản xuất khí đốt
Phân phối nhiên liệu khí bằng đường ống
Sản xuất, phân phối hơi nước, nước nóng và điều hoà không khí
Sản xuất nước đá
Khai thác, xử lý và cung cấp nước
Thoát nước
Xử lý nước thải
Thu gom rác thải không độc hại
Thu gom rác thải y tế
Thu gom rác thải độc hại khác
Xử lý và tiêu hủy rác thải không độc hại
Xử lý và tiêu hủy rác thải y tế
Xử lý và tiêu hủy rác thải độc hại khác
Tái chế phế liệu kim loại
Tái chế phế liệu phi kim loại
Xử lý ô nhiễm và hoạt động quản lý chất thải khác
Xây dựng nhà để ở
Xây dựng nhà không để ở
Xây dựng công trình đường sắt
Xây dựng công trình đường bộ
Xây dựng công trình điện
Xây dựng công trình cấp, thoát nước
Xây dựng công trình viễn thông, thông tin liên lạc
Xây dựng công trình công ích khác
Xây dựng công trình thủy
Xây dựng công trình khai khoáng
Xây dựng công trình chế biến, chế tạo
Xây dựng công trình kỹ thuật dân dụng khác
Phá dỡ
Chuẩn bị mặt bằng
Lắp đặt hệ thống điện
Lắp đặt hệ thống cấp, thoát nước
Lắp đặt hệ thống sưởi và điều hoà không khí
Lắp đặt hệ thống xây dựng khác
Hoàn thiện công trình xây dựng
Hoạt động xây dựng chuyên dụng khác
Bán buôn ô tô con (loại 9 chỗ ngồi trở xuống)
Bán buôn xe có động cơ khác
Bán lẻ ô tô con (loại 9 chỗ ngồi trở xuống)
Đại lý ô tô con (loại 9 chỗ ngồi trở xuống)
Đại lý xe có động cơ khác
Bảo dưỡng, sửa chữa ô tô và xe có động cơ khác
Bán buôn phụ tùng và các bộ phận phụ trợ của ô tô và xe có động cơ khác
Bán lẻ phụ tùng và các bộ phận phụ trợ của ô tô con (loại 9 chỗ ngồi trở xuống)
Đại lý phụ tùng và các bộ phận phụ trợ của ô tô và xe có động cơ khác
Bán buôn mô tô, xe máy
Bán lẻ mô tô, xe máy
Đại lý mô tô, xe máy
Bảo dưỡng và sửa chữa mô tô, xe máy
Bán buôn phụ tùng và các bộ phận phụ trợ của mô tô, xe máy
Bán lẻ phụ tùng và các bộ phận phụ trợ của mô tô, xe máy
Đại lý phụ tùng và các bộ phận phụ trợ của mô tô, xe máy
Đại lý bán hàng hóa
Môi giới mua bán hàng hóa
Đấu giá hàng hóa
Bán buôn thóc, ngô và các loại hạt ngũ cốc khác
Bán buôn hoa và cây
Bán buôn động vật sống
Bán buôn thức ăn và nguyên liệu làm thức ăn cho gia súc, gia cầm và thủy sản
Bán buôn nông, lâm sản nguyên liệu khác (trừ gỗ, tre, nứa)
Bán buôn gạo, lúa mỳ, hạt ngũ cốc khác, bột mỳ
Bán buôn thịt và các sản phẩm từ thịt
Bán buôn thủy sản
Bán buôn rau, quả
Bán buôn cà phê
Bán buôn chè
Bán buôn đường, sữa và các sản phẩm sữa, bánh kẹo và các sản phẩm chế biến từ ngũ cốc, bột, tinh bột
Bán buôn thực phẩm khác
Bán buôn đồ uống có cồn
Bán buôn đồ uống không có cồn
Bán buôn sản phẩm thuốc lá, thuốc lào
Bán buôn vải
Bán buôn thảm, đệm, chăn, màn, rèm, ga trải giường, gối và hàng dệt khác
Bán buôn hàng may mặc
Bán buôn giày dép
Bán buôn vali, cặp, túi, ví, hàng da và giả da khác
Bán buôn dược phẩm và dụng cụ y tế
Bán buôn nước hoa, hàng mỹ phẩm và chế phẩm vệ sinh
Bán buôn hàng gốm, sứ, thủy tinh
Bán buôn đồ điện gia dụng, đèn và bộ đèn điện
Bán buôn giường, tủ, bàn ghế và đồ dùng nội thất tương tự
Bán buôn sách, báo, tạp chí, văn phòng phẩm
Bán buôn dụng cụ thể dục, thể thao
Bán buôn đồ dùng khác cho gia đình chưa được phân vào đâu
Bán buôn máy vi tính, thiết bị ngoại vi và phần mềm
Bán buôn thiết bị và linh kiện điện tử, viễn thông
Bán buôn máy móc, thiết bị và phụ tùng máy nông nghiệp
Bán buôn máy móc, thiết bị và phụ tùng máy khai khoáng, xây dựng
Bán buôn máy móc, thiết bị điện, vật liệu điện (máy phát điện, động cơ điện, dây điện và thiết bị khác dùng trong mạch điện)
Bán buôn máy móc, thiết bị và phụ tùng máy dệt, may, da giày
Bán buôn máy móc, thiết bị và phụ tùng máy văn phòng (trừ máy vi tính và thiết bị ngoại vi)
Bán buôn máy móc, thiết bị y tế
Bán buôn máy móc, thiết bị và phụ tùng máy khác chưa được phân vào đâu
Bán buôn than đá và nhiên liệu rắn khác
Bán buôn dầu thô
Bán buôn xăng dầu và các sản phẩm liên quan
Bán buôn khí đốt và các sản phẩm liên quan
Bán buôn quặng kim loại
Bán buôn sắt, thép
Bán buôn kim loại khác
Bán buôn vàng, bạc và kim loại quý khác
Bán buôn tre, nứa, gỗ cây và gỗ chế biến
Bán buôn xi măng
Bán buôn gạch xây, ngói, đá, cát, sỏi
Bán buôn kính xây dựng
Bán buôn sơn, vécni
Bán buôn gạch ốp lát và thiết bị vệ sinh
Bán buôn đồ ngũ kim
Bán buôn vật liệu, thiết bị lắp đặt khác trong xây dựng
Bán buôn phân bón, thuốc trừ sâu và hóa chất khác sử dụng trong nông nghiệp
Bán buôn hóa chất khác (trừ loại sử dụng trong nông nghiệp)
Bán buôn chất dẻo dạng nguyên sinh
Bán buôn cao su
Bán buôn tơ, xơ, sợi dệt
Bán buôn phụ liệu may mặc và giày dép
Bán buôn phế liệu, phế thải kim loại, phi kim loại
Bán buôn chuyên doanh khác còn lại chưa được phân vào đâu
Bán buôn tổng hợp
Bán lẻ trong siêu thị (Supermarket)
Bán lẻ trong cửa hàng tiện lợi (Minimarket)
Bán lẻ trong cửa hàng kinh doanh tổng hợp khác
Bán lẻ trong siêu thị (Supermarket)
Bán lẻ trong cửa hàng tiện lợi (Minimarket)
Bán lẻ trong cửa hàng kinh doanh tổng hợp khác
Bán lẻ lương thực trong các cửa hàng chuyên doanh
Bán lẻ thịt và các sản phẩm thịt trong các cửa hàng chuyên doanh
Bán lẻ thủy sản trong các cửa hàng chuyên doanh
Bán lẻ rau, quả trong các cửa hàng chuyên doanh
Bán lẻ đường, sữa và các sản phẩm sữa, bánh, mứt, kẹo và các sản phẩm chế biến từ ngữ cốc, bột, tinh bột trong các cửa hàng chuyên doanh
Bán lẻ thực phẩm khác trong các cửa hàng chuyên doanh
Bán lẻ đồ uống trong các cửa hàng chuyên doanh
Bán lẻ sản phẩm thuốc lá, thuốc lào trong các cửa hàng chuyên doanh
Bán lẻ nhiên liệu động cơ trong các cửa hàng chuyên doanh
Bán lẻ máy vi tính, thiết bị ngoại vi, phần mềm trong các cửa hàng chuyên doanh
Bán lẻ thiết bị viễn thông trong các cửa hàng chuyên doanh
Bán lẻ thiết bị nghe nhìn trong các cửa hàng chuyên doanh
Bán lẻ vải trong các cửa hàng chuyên doanh
Bán lẻ len, sợi, chỉ khâu và hàng dệt khác trong các cửa hàng chuyên doanh
Bán lẻ đồ ngũ kim trong các cửa hàng chuyên doanh
Bán lẻ sơn, màu, véc ni trong các cửa hàng chuyên doanh
Bán lẻ kính xây dựng trong các cửa hàng chuyên doanh
Bán lẻ xi măng, gạch xây, ngói, đá, cát sỏi, sắt thép và vật liệu xây dựng khác trong các cửa hàng chuyên doanh
Bán lẻ gạch ốp lát, thiết bị vệ sinh trong các cửa hàng chuyên doanh
Bán lẻ thiết bị lắp đặt khác trong xây dựng trong các cửa hàng chuyên doanh
Bán lẻ thảm, đệm, chăn, màn, rèm, vật liệu phủ tường và sàn trong các cửa hàng chuyên doanh
Bán lẻ đồ điện gia dụng, đèn và bộ đèn điện trong các cửa hàng chuyên doanh
Bán lẻ giường, tủ, bàn, ghế và đồ dùng nội thất tương tự trong các cửa hàng chuyên doanh
Bán lẻ đồ dùng gia đình bằng gốm, sứ, thủy tinh trong các cửa hàng chuyên doanh
Bán lẻ nhạc cụ trong các cửa hàng chuyên doanh
Bán lẻ đồ dùng gia đình khác còn lại chưa được phân vào đâu trong các cửa hàng chuyên doanh
Bán lẻ sách, báo, tạp chí văn phòng phẩm trong các cửa hàng chuyên doanh
Bán lẻ băng đĩa âm thanh, hình ảnh (kể cả băng, đĩa trắng) trong các cửa hàng chuyên doanh
Bán lẻ thiết bị, dụng cụ thể dục, thể thao trong các cửa hàng chuyên doanh
Bán lẻ trò chơi, đồ chơi trong các cửa hàng chuyên doanh
Bán lẻ hàng may mặc trong các cửa hàng chuyên doanh
Bán lẻ giày dép trong các cửa hàng chuyên doanh
Bán lẻ cặp, túi, ví, hàng da và giả da khác trong các cửa hàng chuyên doanh
Bán lẻ dược phẩm, dụng cụ y tế trong các cửa hàng chuyên doanh
Bán lẻ nước hoa, mỹ phẩm và vật phẩm vệ sinh trong các cửa hàng chuyên doanh
Bán thuốc đông y, bán thuốc nam trong các cửa hàng chuyên doanh
Bán lẻ hoa, cây cảnh, cá cảnh, chim cảnh, vật nuôi cảnh trong các cửa hàng chuyên doanh
Bán lẻ vàng, bạc, đá quí và đá bán quí, đồ trang sức trong các cửa hàng chuyên doanh
Bán lẻ hàng lưu niệm, hàng đan lát, hàng thủ công mỹ nghệ trong các cửa hàng chuyên doanh
Bán lẻ tranh, ảnh và các tác phẩm nghệ thuật khác (trừ đồ cổ) trong các cửa hàng chuyên doanh
Bán lẻ dầu hoả, gas, than nhiên liệu dùng cho gia đình trong các cửa hàng chuyên doanh
Bán lẻ đồng hồ, kính mắt trong các cửa hàng chuyên doanh
Bán lẻ máy ảnh, phim ảnh và vật liệu ảnh trong các cửa hàng chuyên doanh
Bán lẻ xe đạp và phụ tùng trong các cửa hàng chuyên doanh
Bán lẻ hàng hóa khác mới chưa được phân vào đâu trong các cửa hàng chuyên doanh
Bán lẻ hàng may mặc đã qua sử dụng trong các cửa hàng chuyên doanh
Bán lẻ hàng hóa khác đã qua sử dụng trong các cửa hàng chuyên doanh
Bán lẻ lương thực lưu động hoặc tại chợ
Bán lẻ thực phẩm khô, thực phẩm công nghiệp, đường sữa bánh kẹo lưu động hoặc tại chợ
Bán lẻ đồ uống lưu động hoặc tại chợ
Bán lẻ sản phẩm thuốc lá, thuốc lào lưu động hoặc tại chợ
Bán lẻ thịt gia súc, gia cầm tươi sống, đông lạnh lưu động hoặc tại chợ
Bán lẻ thủy sản tươi sống, đông lạnh lưu động hoặc tại chợ
Bán lẻ rau quả lưu động hoặc tại chợ
Bán lẻ thực phẩm chín lưu động hoặc tại chợ
Bán lẻ thực phẩm loại khác chưa được phân vào đâu
Bán lẻ hàng dệt lưu động hoặc tại chợ
Bán lẻ hàng may mặc lưu động hoặc tại chợ
Bán lẻ giày dép lưu động hoặc tại chợ
Bán lẻ thiết bị công nghệ thông tin liên lạc lưu động hoặc tại chợ
Bán lẻ đồ ngũ kim, sơn, kính và thiết bị lắp đặt khác trong xây dựng lưu động hoặc tại chợ
Bán lẻ thảm, đệm, chăn, màn, rèm, vật liệu phủ tường và sàn lưu động hoặc tại chợ
Bán lẻ đồ điện gia dụng, giường, tủ, bàn, ghế và đồ nội thất tương tự, đèn và bộ đèn điện, đồ dùng gia đình khác chưa được phân vào đâu lưu động hoặc tại chợ
Bán lẻ hàng văn hóa, giải trí lưu động hoặc tại chợ
Bán lẻ mỹ phẩm và vật phẩm vệ sinh lưu động hoặc tại chợ
Bán lẻ hàng gốm sứ, thủy tinh lưu động hoặc tại chợ
Bán lẻ hoa tươi, cây cảnh lưu động hoặc tại chợ
Bán lẻ vàng, bạc, đá quí và đá bán quí, đồ trang sức lưu động hoặc tại chợ
Bán lẻ hàng lưu niệm, hàng đan lát, hàng thủ công mỹ nghệ lưu động hoặc tại chợ
Bán lẻ đồng hồ, kính mắt lưu động hoặc tại chợ
Bán lẻ xe đạp và phụ tùng lưu động hoặc tại chợ
Bán lẻ hàng hóa đã qua sử dụng lưu động hoặc tại chợ
Bán lẻ hàng hóa khác chưa được phân vào đâu, lưu động hoặc tại chợ
Bán lẻ theo yêu cầu đặt hàng qua bưu điện hoặc internet
Bán lẻ hình thức khác chưa được phân vào đâu
Vận tải hành khách đường sắt
Vận tải hàng hóa đường sắt
Vận tải hành khách bằng xe buýt trong nội thành
Vận tải hành khách bằng xe buýt giữa nội thành và ngoại thành, liên tỉnh
Vận tải hành khách bằng xe buýt loại khác
Vận tải hành khách bằng hệ thống đường sắt ngầm hoặc đường sắt trên cao
Vận tải hành khách bằng taxi
Vận tải hành khách bàng mô tô, xe máy và xe có động cơ khác
Vận tải hành khách đường bộ loại khác trong nội thành, ngoại thành (trừ xe buýt)
Vận tải hành khách bằng xe khách nội tỉnh, liên tỉnh
Vận tải hành khách đường bộ khác chưa được phân vào đâu
Vận tải hàng hóa bằng ô tô chuyên dụng
Vận tải hàng hóa bằng ô tô loại khác (trừ ô tô chuyên dụng)
Vận tải hàng hóa bằng xe có động cơ loại khác
Vận tải hàng hóa bằng xe thô sơ
Vận tải hàng hóa bằng phương tiện đường bộ khác
Vận tải đường ống
Vận tải hành khách ven biển
Vận tải hành khách viễn dương
Vận tải hàng hóa ven biển
Vận tải hàng hóa viễn dương
Vận tải hành khách đường thủy nội địa bằng phương tiện cơ giới
Vận tải hành khách đường thủy nội địa bằng phương tiện thô sơ
Vận tải hàng hóa đường thủy nội địa bằng phương tiện cơ giới
Vận tải hàng hóa đường thủy nội địa bằng phương tiện thô sơ
Vận tải hành khách hàng không theo tuyến và lịch trình cố định
Vận tải hành khách hàng không loại khác
Vận tải hàng hóa hàng không theo tuyến và lịch trình cố định
Vận tải hàng hóa hàng không loại khác
Kho bãi và lưu giữ hàng hóa trong kho ngoại quan
Kho bãi và lưu giữ hàng hóa trong kho đông lạnh (trừ kho ngoại quan)
Kho bãi và lưu giữ hàng hóa trong kho loại khác
Hoạt động dịch vụ hỗ trợ trực tiếp cho vận tải đường sắt
Hoạt động điều hành cảng biển
Hoạt động dịch vụ hỗ trợ liên quan đến vận tải ven biển và viễn dương
Hoạt động điều hành cảng đường thủy nội địa
Hoạt động dịch vụ hỗ trợ liên quan đến vận tải đường thủy nội địa
Dịch vụ điều hành bay
Dịch vụ điều hành hoạt động cảng hàng không
Hoạt động dịch vụ hỗ trợ liên quan đến vận tải hàng không
Bốc xếp hàng hóa ga đường sắt
Bốc xếp hàng hóa đường bộ
Bốc xếp hàng hóa cảng biển
Bốc xếp hàng hóa cảng sông
Bốc xếp hàng hóa cảng hàng không
Bốc xếp hàng hóa loại khác
Hoạt động điều hành bến xe
Hoạt động quản lý, điều hành đường cao tốc, cầu, hầm đường bộ
Hoạt động quản lý bãi đỗ, trông giữ phương tiện đường bộ
Hoạt động dịch vụ khác hỗ trợ liên quan đến vận tải đường bộ
Dịch vụ đại lý, giao nhận vận chuyển
Logistics
Dịch vụ hỗ trợ khác liên quan đến vận tải chưa được phân vào đâu
Bưu chính
Chuyển phát
Khách sạn
Biệt thự hoặc căn hộ kinh doanh dịch vụ lưu trú ngắn ngày
Nhà khách, nhà nghỉ kinh doanh dịch vụ lưu trú ngắn ngày
Nhà trọ, phòng trọ và các cơ sở lưu trú ngắn ngày tương tự
Ký túc xá học sinh, sinh viên
Chỗ nghỉ trọ trên xe lưu động, lều quán, trại dùng để nghỉ tạm
Cơ sở lưu trú khác chưa được phân vào đâu
Nhà hàng, quán ăn, hàng ăn uống (trừ cửa hàng ăn uống thuộc chuỗi cửa hàng ăn nhanh)
Cửa hàng ăn uống thuộc chuỗi cửa hàng ăn nhanh
Dịch vụ ăn uống phục vụ lưu động khác
Cung cấp dịch vụ ăn uống theo hợp đồng không thường xuyên với khách hàng
Dịch vụ ăn uống khác
Quán rượu, bia, quầy bar
Quán cà phê, giải khát
Dịch vụ phục vụ đồ uống khác
Xuất bản sách trực tuyến
Xuất bản sách khác
Xuất bản các danh mục chỉ dẫn và địa chỉ trực tuyến
Xuất bản các danh mục chỉ dẫn và địa chỉ khác
Xuất bản báo, tạp chí và các ấn phẩm định kỳ trực tuyến
Xuất bản báo, tạp chí và các ấn phẩm định kỳ khác
Hoạt động xuất bản trực tuyến khác
Hoạt động xuất bản khác
Xuất bản phần mềm
Hoạt động sản xuất phim điện ảnh
Hoạt động sản xuất phim video
Hoạt động sản xuất chương trình truyền hình
Hoạt động hậu kỳ
Hoạt động phát hành phim điện ảnh, phim video và chương trình truyền hình
Hoạt động chiếu phim cố định
Hoạt động chiếu phim lưu động
Hoạt động ghi âm và xuất bản âm nhạc
Hoạt động phát thanh
Hoạt động truyền hình
Chương trình cáp, vệ tinh và các chương trình thuê bao khác
Hoạt động cung cấp trực tiếp dịch vụ viễn thông có dây
Hoạt động cung cấp dịch vụ viễn thông có dây sử dụng quyền truy cập hạ tầng viễn thông của đơn vị khác
Hoạt động cung cấp trực tiếp dịch vụ viễn thông không dây
Hoạt động cung cấp dịch vụ viễn thông không dây sử dụng quyền truy cập hạ tầng viễn thông của đơn vị khác
Hoạt động viễn thông vệ tinh
Hoạt động của các điểm truy cập internet
Hoạt động viễn thông khác chưa được phân vào đâu
Lập trình máy vi tính
Tư vấn máy vi tính và quản trị hệ thống máy vi tính
Hoạt động dịch vụ công nghệ thông tin và dịch vụ khác liên quan đến máy vi tính
Xử lý dữ liệu, cho thuê và các hoạt động liên quan
Cổng thông tin
Hoạt động thông tấn
Dịch vụ thông tin khác chưa được phân vào đâu
Hoạt động ngân hàng trung ương
Hoạt động trung gian tiền tệ khác
Hoạt động công ty nắm giữ tài sản
Hoạt động quỹ tín thác, các quỹ và các tổ chức tài chính khác
Hoạt động cho thuê tài chính
Hoạt động cấp tín dụng khác
Hoạt động dịch vụ tài chính khác chưa được phân vào đâu (trừ bảo hiểm và bảo hiểm xã hội)
Bảo hiểm nhân thọ
Bảo hiểm phi nhân thọ
Bảo hiểm y tế
Bảo hiểm sức khỏe khác
Tái bảo hiểm
Bảo hiểm xã hội
Quản lý thị trường tài chính
Môi giới hợp đồng hàng hóa và chứng khoán
Hoạt động hỗ trợ dịch vụ tài chính chưa được phân vào đâu
Đánh giá rủi ro và thiệt hại
Hoạt động của đại lý và môi giới bảo hiểm
Hoạt động hỗ trợ khác cho bảo hiểm và bảo hiểm xã hội
Hoạt động quản lý quỹ
Mua, bán nhà ở và quyền sử dụng đất ở
Mua, bán nhà và quyền sử dụng đất không để ở
Cho thuê, điều hành, quản lý nhà và đất ở
Cho thuê, điều hành, quản lý nhà và đất không để ở
Kinh doanh bất động sản khác
Tư vấn, môi giới bất động sản, quyền sử dụng đất
Đấu giá bất động sản, quyền sử dụng đất
Hoạt động đại diện, tư vấn pháp luật
Hướng dẫn chung và tư vấn, chuẩn bị các tài liệu pháp lý
Hoạt động pháp luật khác
Hoạt động liên quan đến kế toán, kiểm toán và tư vấn về thuế
Hoạt động của trụ sở văn phòng
Hoạt động tư vấn quản lý
Hoạt động kiến trúc
Hoạt động đo đạc và bản đồ
Hoạt động thăm dò địa chất, nguồn nước
Hoạt động tư vấn kỹ thuật có liên quan khác
Kiểm tra và phân tích kỹ thuật
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học tự nhiên
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học kỹ thuật và công nghệ
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học y, dược
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học nông nghiệp
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học xã hội
Nghiên cứu khoa học và phát triển công nghệ trong lĩnh vực khoa học nhân văn
Quảng cáo
Nghiên cứu thị trường và thăm dò dư luận
Hoạt động thiết kế chuyên dụng
Hoạt động nhiếp ảnh
Hoạt động khí tượng thủy văn
Hoạt động chuyên môn, khoa học và công nghệ khác còn lại chưa được phân vào đâu
Hoạt động thú y
Cho thuê ôtô
Cho thuê xe có động cơ khác
Cho thuê thiết bị thể thao, vui chơi giải trí
Cho thuê băng, đĩa video
Cho thuê đồ dùng cá nhân và gia đình khác
Cho thuê máy móc, thiết bị nông, lâm nghiệp không kèm người điều khiển
Cho thuê máy móc, thiết bị xây dựng không kèm người điều khiển
Cho thuê máy móc, thiết bị văn phòng (kể cả máy vi tính) không kèm người điều khiển
Cho thuê máy bay, phương tiện bay không kèm người điều khiển
Cho thuê tàu, thuyền và kết cấu nổi không kèm người điều khiển
Cho thuê máy móc, thiết bị và đồ dùng hữu hình khác, không kèm người điều khiển chưa được phân vào đâu
Cho thuê tài sản vô hình phi tài chính
Hoạt động của các trung tâm, đại lý tư vấn, giới thiệu và môi giới lao động, việc làm
Cung ứng lao động tạm thời
Cung ứng và quản lý nguồn lao động trong nước
Cung ứng và quản lý nguồn lao động đi làm việc ở nước ngoài
Đại lý du lịch
Điều hành tua du lịch
Dịch vụ đặt chỗ và các dịch vụ hỗ trợ liên quan đến quảng bá và tổ chức tua du lịch
Hoạt động bảo vệ tư nhân
Dịch vụ hệ thống bảo đảm an toàn
Dịch vụ điều tra
Dịch vụ hỗ trợ tổng hợp
Vệ sinh chung nhà cửa
Vệ sinh công nghiệp và các công trình chuyên biệt
Dịch vụ chăm sóc và duy trì cảnh quan
Dịch vụ hành chính văn phòng tổng hợp
Photo, chuẩn bị tài liệu
Hoạt động hỗ trợ văn phòng đặc biệt khác
Hoạt động dịch vụ liên quan đến các cuộc gọi
Tổ chức giới thiệu và xúc tiến thương mại
Hoạt động dịch vụ hỗ trợ thanh toán, tín dụng
Dịch vụ đóng gói
Hoạt động dịch vụ hỗ trợ kinh doanh khác còn lại chưa được phân vào đâu
Hoạt động của Đảng cộng sản, tổ chức chính trị - xã hội
Hoạt động quản lý nhà nước nói chung và kinh tế tổng hợp
Hoạt động quản lý nhà nước trong các lĩnh vực y tế, giáo dục, văn hóa và các dịch vụ xã hội khác (trừ bảo đảm xã hội bắt buộc)
Hoạt động quản lý nhà nước trong các lĩnh vực kinh tế chuyên ngành
Hoạt động đối ngoại
Hoạt động quốc phòng
Hoạt động an ninh, trật tự an toàn xã hội
Hoạt động bảo đảm xã hội bắt buộc
Giáo dục nhà trẻ
Giáo dục mẫu giáo
Giáo dục tiểu học
Giáo dục trung học cơ sở
Giáo dục trung học phổ thông
Đào tạo sơ cấp
Đào tạo trung cấp
Đào tạo cao đẳng
Đào tạo đại học
Đào tạo thạc sỹ
Đào tạo tiến sỹ
Giáo dục thể thao và giải trí
Giáo dục văn hóa nghệ thuật
Giáo dục khác chưa được phân vào đâu
Dịch vụ hỗ trợ giáo dục
Hoạt động của các bệnh viện
Hoạt động của các trạm y tế và trạm y tế bộ/ngành
Hoạt động của các phòng khám đa khoa, chuyên khoa
Hoạt động của các phòng khám nha khoa
Hoạt động y tế dự phòng
Hoạt động của hệ thống cơ sở chỉnh hình, phục hồi chức năng
Hoạt động y tế khác chưa được phân vào đâu
Hoạt động của các cơ sở nuôi dưỡng, điều dưỡng thương bệnh binh
Hoạt động của các cơ sở nuôi dưỡng, điều dưỡng các đối tượng khác
Hoạt động chăm sóc sức khoẻ người bị thiểu năng, tâm thần
Hoạt động chăm sóc sức khoẻ, cai nghiện phục hồi người nghiện
Hoạt động chăm sóc sức khoẻ người có công (trừ thương bệnh binh)
Hoạt động chăm sóc sức khoẻ người già
Hoạt động chăm sóc sức khoẻ người khuyết tật
Hoạt động chữa bệnh, phục hồi nhân phẩm cho đối tượng mại dâm
Hoạt động chăm sóc tập trung khác chưa được phân vào đâu
Hoạt động trợ giúp xã hội không tập trung đối với người có công (trừ thương bệnh binh)
Hoạt động trợ giúp xã hội không tập trung đối với thương bệnh binh
Hoạt động trợ giúp xã hội không tập trung đối với người già và người khuyết tật
Hoạt động trợ giúp xã hội không tập trung khác
Hoạt động sáng tác, nghệ thuật và giải trí
Hoạt động thư viện và lưu trữ
Hoạt động bảo tồn, bảo tàng
Hoạt động của các vườn bách thảo, bách thú và khu bảo tồn tự nhiên
Hoạt động xổ số
Hoạt động cá cược và đánh bạc
Hoạt động của các cơ sở thể thao
Hoạt động của các câu lạc bộ thể thao
Hoạt động thể thao khác
Hoạt động của các công viên vui chơi và công viên theo chủ đề
Hoạt động vui chơi giải trí khác chưa được phân vào đâu
Hoạt động của các hiệp hội kinh doanh và nghiệp chủ
Hoạt động của các hội nghề nghiệp
Hoạt động của công đoàn
Hoạt động của các tổ chức tôn giáo
Hoạt động của các tổ chức khác chưa được phân vào đâu
Sửa chữa máy vi tính và thiết bị ngoại vi
Sửa chữa thiết bị liên lạc
Sửa chữa thiết bị nghe nhìn điện tử gia dụng
Sửa chữa thiết bị, đồ dùng gia đình
Sửa chữa giày, dép, hàng da và giả da
Sửa chữa giường, tủ, bàn, ghế và đồ nội thất tương tư
Sửa chữa xe đạp, đồng hồ, đồ dùng cá nhân và gia đình khác chưa được phân vào đâu
Dịch vụ tắm hơi, massage và các dịch vụ tăng cường sức khoẻ tương tự (trừ hoạt động thể thao)
Giặt là, làm sạch các sản phẩm dệt và lông thú
Cắt tóc, làm đầu, gội đầu
Hoạt động dịch vụ phục vụ tang lễ
Hoạt động dịch vụ phục vụ hôn lễ
Hoạt động dịch vụ phục vụ cá nhân khác còn lại chưa được phân vào đâu
Hoạt động làm thuê công việc gia đình trong các hộ gia đình
Hoạt động sản xuất các sản phẩm vật chất tự tiêu dùng của hộ gia đình
Hoạt động sản xuất các sản phẩm dịch vụ tự tiêu dùng của hộ gia đình
Hoạt động của các tổ chức và cơ quan quốc tế
"""