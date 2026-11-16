

# table_schemas = [
#     {
#         "table_name": "beehi_base_emp_info",
#         "description": "Lưu trữ thông tin nhân sự cơ bản",
#         "fields": [
#             {"name": "username", "description": "Tên đăng nhập người dùng được đồng bộ từ keycloak MB về HCM", "data type":"text"},
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB (Khóa chính)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "fullname", "description": "Họ và tên đầy đủ", "data type":"text"},
#             {"name": "dateofbirth", "description": "Ngày tháng năm sinh", "data type":"text"},
#             {"name": "flagstatus", "description": "	Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#             {"name": "org_name_manage", "description": "Tên đơn vị quản lý", "data type":"text"},
#             {"name": "org_name_level_1", "description": "Tên đơn vị trực thuộc 1", "data type":"text"},
#             {"name": "org_name_level_2", "description": "Tên đơn vị trực thuộc 2", "data type":"text"},
#             {"name": "org_name_level_3", "description": "Tên đơn vị trực thuộc 3", "data type":"text"},
#             {"name": "org_level", "description": "Cấp của đơn vị hiện tại", "data type":"int4"},
#             {"name": "management_level", "description": "Cấp rank quản lý hiện tại", "data type":"int4"},
#             {"name": "job_name", "description": "Chức danh hiện tại", "data type":"text"}
#         ]
#     },
#     {
#         "table_name": "beehi_emp_concurrent_process_info",
#         "description": "Lưu trữ thông tin quá trình kiêm nhiệm. Một nhân viên có thể có nhiều quá trình kiêm nhiệm, mỗi quá trình 1 hàng trong bảng",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "jobname", "description": "Chức danh tại MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
#             {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
#             {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
#             {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
#             {"name": "concurrentprocessid", "description": "ID của bản ghi (khóa chính)", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_contract_process_info",
#         "description": "Lưu trữ thông tin quá trình hợp đồng. Một nhân viên có thể có nhiều hợp động, mỗi hợp động 1 hàng trong bảng",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
#             {"name": "contracttype", "description": "Loại Hợp đồng lao đồng", "data type":"text"},
#             {"name": "contractnumber", "description": "Số Hợp đồng lao đồng", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "contractprocessid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_degree_info",
#         "description": "Lưu trữ thông tin bằng cấp, chứng chỉ",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "degreetype", "description": "Loại bằng cấp", "data type":"text"},
#             {"name": "majorlevel", "description": "Trình độ", "data type":"text"},
#             {"name": "school", "description": "Trường (nơi học)", "data type":"text"},
#             {"name": "faculities", "description": "Chuyên ngành", "data type":"text"},
#             {"name": "certtype", "description": "Loại chứng chỉ", "data type":"text"},
#             {"name": "certificatename", "description": "Tên Chứng chỉ", "data type":"text"},
#             {"name": "certificateplace", "description": "Nơi cấp chứng chỉ", "data type":"text"},
#             {"name": "certificateresult", "description": "Kết quả xếp loại chứng chỉ", "data type":"text"},
#             {"name": "todate", "description": "Thời hạn của chứng chỉ", "data type":"text"},
#             {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
#             {"name": "educationdegreeid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_leave_info",
#         "description": "Lưu trữ thông tin quản lý nghỉ",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "leavetype", "description": "Loại nghỉ", "data type":"text"},
#             {"name": "fromtime", "description": "Thời gian bắt đầu nghỉ", "data type":"text"},
#             {"name": "totime", "description": "Thời gian cuối nghỉ (nghỉ đến ngày nào)", "data type":"text"},
#             {"name": "useddays", "description": "Số ngày phép đã sử dụng", "data type":"text"},
#             {"name": "remaindaysinyear", "description": "Số ngày phép còn lại trong năm", "data type":"text"},
#             {"name": "dayoff", "description": "Số ngày nghỉ", "data type":"text"},
#             {"name": "oldrequestid", "description": "ID của đơn được điều chỉnh", "data type":"text"},
#             {"name": "requestid", "description": "ID của bản ghi nghỉ", "data type":"text"},
#             {"name": "requestleaveid", "description": "ID lý do nghỉ của bản ghi nghỉ(Khóa chính)", "data type":"text"},
#             {"name": "status", "description": "Trạng thái của bản ghi.(status = 'Đã phê duyệt' hoặc status = 'Đã hủy')", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_mb_process_info",
#         "description": "Lưu trữ thông tin quá trình công tác tại MB. Một nhân viên có nhiều quá trình công tác tại MB → Mỗi quá trình công tác tại MB là 1 hàng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
#             {"name": "joincompanydate", "description": "Ngày vào làm việc tại MB", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "emptype", "description": "Đối tượng(loại nhân viên)", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
#             {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
#             {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
#             {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
#             {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
#             {"name": "jobname", "description": "Chức danh", "data type":"text"},
#             {"name": "level", "description": "Level của nhân viên", "data type":"text"},
#             {"name": "positiongroup", "description": "Nhóm vị trí (thuộc nhóm nào)", "data type":"text"},
#             {"name": "documentno", "description": "Số Quyết Định", "data type":"text"},
#             {"name": "documenttype", "description": "Hình thức thay đổi", "data type":"text"},
#             {"name": "region", "description": "Khu vực", "data type":"text"},
#             {"name": "subregion", "description": "Vùng miền", "data type":"text"},
#             {"name": "flagstatus", "description": "ID của bản ghi", "data type":"text"},
#             {"name": "workprocessid", "description": "Trạng thái của bản ghi(Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_party_army_info",
#         "description": "Lưu trữ dữ liệu đảng, quân nhân của nhân viên",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "partydate", "description": "Ngày vào Đảng (dự bị)", "data type":"text"},
#             {"name": "partyofficialdate", "description": "Ngày vào Đảng chính thức", "data type":"text"},
#             {"name": "partyplace", "description": "Nơi kết nạp", "data type":"text"},
#             {"name": "armyjoin", "description": "Ngày vào quân nhân", "data type":"text"},
#             {"name": "armylevel", "description": "Cấp bậc quân hàm", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_pre_mb_process_info",
#         "description": "Lưu trữ thông tin quá trình công tác trước MB. Một nhân viên có nhiều quá trình công tác trước MB → Mỗi quá trình công tác trước MB là 1 dòng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
#             {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
#             {"name": "organizationname", "description": "Đơn vị công tác", "data type":"text"},
#             {"name": "positionname", "description": "Chức danh", "data type":"text"},
#             {"name": "mission", "description": "Nhiệm vụ chính", "data type":"text"},
#             {"name": "reasonleave", "description": "Lý do chuyển", "data type":"text"},
#             {"name": "rewardinfo", "description": "Thông tin khen thưởng", "data type":"text"},
#             {"name": "decpline", "description": "Thông tin kỷ luật", "data type":"text"},
#             {"name": "flagstatus", "description": "ID bản ghi ghi", "data type":"text"},
#             {"name": "workedoutsideid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_rating_process_info",
#         "description": "Lưu trữ thông tin quá trình đánh giá. Một nhân viên có nhiều quá trình đánh giá → Mỗi quá trình đánh giá là 1 hàng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính 1)", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
#             {"name": "periodname", "description": "Kỳ đánh giá(Khóa chính 2)", "data type":"text"},
#             {"name": "resultfinal", "description": "Điểm xếp loại", "data type":"text"},
#             {"name": "ratingafter", "description": "Xếp loại sau phân bổ", "data type":"text"},
#         ]
#     },
#     {
#         "table_name": "beehi_emp_reward_process_info",
#         "description": "Lưu trữ thông tin quá trình khen thưởng. Một nhân viên có nhiều quá trình khen thưởng → Mỗi quá trình khen thưởng là 1 dòng.",
#         "fields": [
#             {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
#             {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
#             {"name": "rewardtype", "description": "Loại khen thưởng", "data type":"text"},
#             {"name": "rewardrecord", "description": "Danh hiệu khen thưởng", "data type":"text"},
#             {"name": "documentnumber", "description": "Số quyết định", "data type":"text"},
#             {"name": "fromdate", "description": "Ngày hiệu lực", "data type":"text"},
#             {"name": "reason", "description": "Lý do khen thưởng", "data type":"text"},
#             {"name": "flagstatus", "description": "ID bản ghi", "data type":"text"},
#             {"name": "rewardrecordid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"}
#         ]
#     },

# ]



table_schemas = [
    {
        "table_name": "beehi_base_emp_info",
        "description": "Lưu trữ thông tin nhân sự cơ bản",
        "fields": [
            {"name": "username", "description": "Tên đăng nhập người dùng được đồng bộ từ keycloak MB về HCM", "data type":"text"},
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB (Khóa chính)", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "fullname", "description": "Họ và tên đầy đủ", "data type":"text"},
            {"name": "dateofbirth", "description": "Ngày tháng năm sinh", "data type":"text"},
            {"name": "flagstatus", "description": "	Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"}
        ]
    },
    {
        "table_name": "beehi_emp_concurrent_process_info",
        "description": "Lưu trữ thông tin quá trình kiêm nhiệm. Một nhân viên có thể có nhiều quá trình kiêm nhiệm, mỗi quá trình 1 hàng trong bảng",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "jobname", "description": "Chức danh tại MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
            {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
            {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
            {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
            {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
            {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
            {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
            {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
            {"name": "concurrentprocessid", "description": "ID của bản ghi (khóa chính)", "data type":"text"},
            {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_contract_process_info",
        "description": "Lưu trữ thông tin quá trình hợp đồng. Một nhân viên có thể có nhiều hợp động, mỗi hợp động 1 hàng trong bảng",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "status", "description": "Trạng thái làm việc", "data type":"text"},
            {"name": "contracttype", "description": "Loại Hợp đồng lao đồng", "data type":"text"},
            {"name": "contractnumber", "description": "Số Hợp đồng lao đồng", "data type":"text"},
            {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
            {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
            {"name": "contractprocessid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
            {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_degree_info",
        "description": "Lưu trữ thông tin bằng cấp, chứng chỉ",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "degreetype", "description": "Loại bằng cấp", "data type":"text"},
            {"name": "majorlevel", "description": "Trình độ", "data type":"text"},
            {"name": "school", "description": "Trường (nơi học)", "data type":"text"},
            {"name": "faculities", "description": "Chuyên ngành", "data type":"text"},
            {"name": "certtype", "description": "Loại chứng chỉ", "data type":"text"},
            {"name": "certificatename", "description": "Tên Chứng chỉ", "data type":"text"},
            {"name": "certificateplace", "description": "Nơi cấp chứng chỉ", "data type":"text"},
            {"name": "certificateresult", "description": "Kết quả xếp loại chứng chỉ", "data type":"text"},
            {"name": "todate", "description": "Thời hạn của chứng chỉ", "data type":"text"},
            {"name": "flagstatus", "description": "Trạng thái bản ghi(1: Bản ghi hoạt động; 0: Bản ghi không hoạt động)", "data type":"text"},
            {"name": "educationdegreeid", "description": "ID của bản ghi (Khóa chính)", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_leave_info",
        "description": "Lưu trữ thông tin quản lý nghỉ",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "leavetype", "description": "Loại nghỉ", "data type":"text"},
            {"name": "fromtime", "description": "Thời gian bắt đầu nghỉ", "data type":"text"},
            {"name": "totime", "description": "Thời gian cuối nghỉ (nghỉ đến ngày nào)", "data type":"text"},
            {"name": "useddays", "description": "Số ngày phép đã sử dụng", "data type":"text"},
            {"name": "remaindaysinyear", "description": "Số ngày phép còn lại trong năm", "data type":"text"},
            {"name": "dayoff", "description": "Số ngày nghỉ", "data type":"text"},
            {"name": "oldrequestid", "description": "ID của đơn được điều chỉnh", "data type":"text"},
            {"name": "requestid", "description": "ID của bản ghi nghỉ", "data type":"text"},
            {"name": "requestleaveid", "description": "ID lý do nghỉ của bản ghi nghỉ(Khóa chính)", "data type":"text"},
            {"name": "status", "description": "Trạng thái của bản ghi.(status = 'Đã phê duyệt' hoặc status = 'Đã hủy')", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_mb_process_info",
        "description": "Lưu trữ thông tin quá trình công tác tại MB. Một nhân viên có nhiều quá trình công tác tại MB → Mỗi quá trình công tác tại MB là 1 hàng.",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
            {"name": "joincompanydate", "description": "Ngày vào làm việc tại MB", "data type":"text"},
            {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
            {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
            {"name": "emptype", "description": "Đối tượng(loại nhân viên)", "data type":"text"},
            {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
            {"name": "orgnamemanage", "description": "Đơn vị quản lý", "data type":"text"},
            {"name": "orgnamelevel1", "description": "Đơn vị trực thuộc 1", "data type":"text"},
            {"name": "orgnamelevel2", "description": "Đơn vị trực thuộc 2", "data type":"text"},
            {"name": "orgnamelevel3", "description": "Đơn vị trực thuộc 3", "data type":"text"},
            {"name": "orgnamelevel4", "description": "Đơn vị trực thuộc 4", "data type":"text"},
            {"name": "jobname", "description": "Chức danh, chức vụ của nhân viên", "data type":"text"},
            {"name": "level", "description": "Level của nhân viên", "data type":"text"},
            {"name": "positiongroup", "description": "Nhóm vị trí (thuộc nhóm nào)", "data type":"text"},
            {"name": "documentno", "description": "Số Quyết Định", "data type":"text"},
            {"name": "documenttype", "description": "Hình thức thay đổi", "data type":"text"},
            {"name": "region", "description": "Khu vực", "data type":"text"},
            {"name": "subregion", "description": "Vùng miền", "data type":"text"},
            {"name": "flagstatus", "description": "ID của bản ghi", "data type":"text"},
            {"name": "workprocessid", "description": "Trạng thái của bản ghi(Khóa chính)", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_party_army_info",
        "description": "Lưu trữ dữ liệu đảng, quân nhân của nhân viên",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính)", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "partydate", "description": "Ngày vào Đảng (dự bị)", "data type":"text"},
            {"name": "partyofficialdate", "description": "Ngày vào Đảng chính thức", "data type":"text"},
            {"name": "partyplace", "description": "Nơi kết nạp", "data type":"text"},
            {"name": "armyjoin", "description": "Ngày vào quân nhân", "data type":"text"},
            {"name": "armylevel", "description": "Cấp bậc quân hàm", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_pre_mb_process_info",
        "description": "Lưu trữ thông tin quá trình công tác trước khi vào MB. Một nhân viên có nhiều quá trình công tác trước MB → Mỗi quá trình công tác trước MB là 1 dòng.",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "fromdate", "description": "Ngày bắt đầu", "data type":"text"},
            {"name": "todate", "description": "Ngày kết thúc", "data type":"text"},
            {"name": "organizationname", "description": "Đơn vị công tác", "data type":"text"},
            {"name": "positionname", "description": "Chức danh khi đang công tác", "data type":"text"},
            {"name": "mission", "description": "Nhiệm vụ chính", "data type":"text"},
            {"name": "reasonleave", "description": "Lý do chuyển công tác", "data type":"text"},
            {"name": "rewardinfo", "description": "Thông tin khen thưởng", "data type":"text"},
            {"name": "decpline", "description": "Thông tin kỷ luật", "data type":"text"},
            {"name": "flagstatus", "description": "ID bản ghi ghi", "data type":"text"},
            {"name": "workedoutsideid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_rating_process_info",
        "description": "Lưu trữ thông tin quá trình đánh giá. Một nhân viên có nhiều quá trình đánh giá → Mỗi quá trình đánh giá là 1 hàng.",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB(Khóa chính 1)", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "status", "description": "Trạng thái làm việc (status = 'Hiện diện' hoặc status = 'Tạm hoãn' hoặc status = 'Đã nghỉ việc')", "data type":"text"},
            {"name": "periodname", "description": "Kỳ đánh giá(Khóa chính 2)", "data type":"text"},
            {"name": "resultfinal", "description": "Điểm xếp loại", "data type":"text"},
            {"name": "ratingafter", "description": "Xếp loại sau phân bổ", "data type":"text"},
        ]
    },
    {
        "table_name": "beehi_emp_reward_process_info",
        "description": "Lưu trữ thông tin quá trình khen thưởng. Một nhân viên có nhiều quá trình khen thưởng → Mỗi quá trình khen thưởng là 1 dòng.",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "rewardtype", "description": "Loại khen thưởng", "data type":"text"},
            {"name": "rewardrecord", "description": "Danh hiệu khen thưởng", "data type":"text"},
            {"name": "documentnumber", "description": "Số quyết định", "data type":"text"},
            {"name": "fromdate", "description": "Ngày hiệu lực", "data type":"text"},
            {"name": "reason", "description": "Lý do khen thưởng", "data type":"text"},
            {"name": "flagstatus", "description": "ID bản ghi", "data type":"text"},
            {"name": "rewardrecordid", "description": "Trạng thái bản ghi(Khóa chính)", "data type":"text"}
        ]
    },
    {
        "table_name": "beehi_emp_seniority_info",
        "description": "Lưu trữ thông tin dữ liệu thâm niên của nhân viên",
        "fields": [
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB (Khóa chính)", "data type":"text"},
            {"name": "employeecode", "description": "Mã nhân viên", "data type":"text"},
            {"name": "username", "description": "Tên đăng nhập người dùng được đồng bộ từ keycloak MB về HCM", "data type":"text"},
            {"name": "senioritymb", "description": "Tổng thâm niên tại MB", "data type":"text"},
            {"name": "posseniority", "description": "Thâm niên tại vị trị hiện tại ở MB", "data type":"text"}
        ]
    },
    {
        "table_name": "beehi_emp_annual_leave_info",
        "description": "Lưu trữ thông tin dữ liệu tổng số ngày nghỉ phép còn lại trong năm.",
        "fields": [
            {"name": "annual_leave_id", "description": "ID bản ghi (khóa chính)", "data type":"text"},
            {"name": "year", "description": "Năm hiện tại dùng để tính phép", "data type":"text"},
            {"name": "employeeid", "description": "ID của nhân viên tại HCM của MB", "data type":"text"},
            {"name": "total_days", "description": "	Tổng số ngày phép được nghỉ trong năm", "data type":"text"},
            {"name": "remain_days", "description": "Số ngày phép còn lại trong năm", "data type":"text"},
            {"name": "pos_bonus_days", "description": "Số ngày phép được tính thưởng", "data type":"text"},
            {"name": "senior_bonus_days", "description": "Số ngày phép được tính thưởng thâm niên", "data type":"text"},
            {"name": "annual_days", "description": "Số ngày phép hàng năm", "data type":"text"},
            {"name": "use_switched_days", "description": "Có sử dụng ngày phép chuyển đổi không", "data type":"text"},
            {"name": "used_days", "description": "Số ngày phép đã sử dụng", "data type":"text"},
            {"name": "from_date", "description": "Từ ngày", "data type":"text"}
        ]
    },

]

