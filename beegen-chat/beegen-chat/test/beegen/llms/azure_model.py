import pymongo

# --- Thông tin kết nối từ logs của bạn ---
uri = "mongodb://nlpdev:LOCAL_PASSWORD@10.215.107.53:27017/?authSource=aicenter_chatbot&readPreference=primary&appname=MongoDB%20Compass&ssl=false&directConnection=true"

# --- Dữ liệu để kiểm tra (lấy từ logs) ---
# Một chunk_id mẫu đã được Milvus tìm thấy
test_chunk_id = 'c5ca2077-329b-4805-b80d-52ffcbdb2be6' 
# Role đang được sử dụng để truy vấn
test_allowed_roles = ['L2']
# Tên database (suy đoán từ authSource, bạn có thể cần thay đổi nếu không chính xác)
db_name = "aicenter_chatbot"
# Collection chứa thông tin chunk
chunk_collection_name = "chunk_data"
# Collection chứa tài liệu gốc (sử dụng trong $lookup)
doc_collection_name = "documents"

def simple_db_test():
    """
    Hàm đơn giản để kiểm tra kết nối và logic truy vấn MongoDB từng bước.
    """
    client = None
    try:
        # 1. Kết nối đến MongoDB
        print("--- Đang thử kết nối đến MongoDB... ---")
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Lệnh ismaster đơn giản để kiểm tra kết nối mà không cần quyền cao
        client.admin.command('ismaster')
        print("✅ Kết nối thành công!")
        
        # 2. Chọn database
        db = client[db_name]
        print(f"✅ Đã chọn database: '{db_name}'")

        # 3. Test 1: Tìm chunk trong collection `chunk_data`
        print(f"\n--- Test 1: Tìm chunk '{test_chunk_id}' trong collection '{chunk_collection_name}' ---")
        chunk_collection = db[chunk_collection_name]
        # Giả định trường chứa ID là 'chunk_id' như trong pipeline
        chunk = chunk_collection.find_one({"chunk_id": test_chunk_id})
        
        if chunk:
            print(f"✅ Đã tìm thấy chunk trong '{chunk_collection_name}':")
            print(chunk)
            doc_id = chunk.get("doc_id")
        else:
            print(f"❌ LỖI: Không tìm thấy chunk có chunk_id '{test_chunk_id}' trong '{chunk_collection_name}'.")
            print("Gợi ý: Vui lòng xác minh lại `chunk_collection_name` và đảm bảo dữ liệu tồn tại.")
            return

        # 4. Test 2: Tìm document tương ứng trong collection `documents`
        if not doc_id:
            print(f"\n❌ LỖI: Chunk tìm được không có trường 'doc_id'.")
            return
            
        print(f"\n--- Test 2: Tìm document có _id '{doc_id}' trong collection '{doc_collection_name}' ---")
        doc_collection = db[doc_collection_name]
        document = doc_collection.find_one({"_id": doc_id})

        if document:
            print(f"✅ Đã tìm thấy document trong '{doc_collection_name}':")
            print(document)
            doc_roles = document.get("role_ids")
        else:
            print(f"❌ LỖI: Không tìm thấy document có _id '{doc_id}' trong '{doc_collection_name}'.")
            print("Gợi ý: Vui lòng xác minh lại `doc_collection_name` và đảm bảo document cha tồn tại.")
            # Thử tìm trong 'dialogue' collection như một phương án phụ
            print(f"--- Thử tìm trong collection 'dialogue' ---")
            dialogue_collection = db["dialogue"]
            dialogue_doc = dialogue_collection.find_one({"_id": doc_id})
            if dialogue_doc:
                print("✅ Đã tìm thấy document trong 'dialogue':")
                print(dialogue_doc)
                doc_roles = dialogue_doc.get("role_ids")
            else:
                return

        # 5. Test 3: Kiểm tra quyền truy cập (role)
        if not doc_roles:
            print(f"\n❌ LỖI: Document tìm được không có trường 'role_ids'.")
            return

        print(f"\n--- Test 3: Kiểm tra roles. Role cho phép: {test_allowed_roles}, Role của document: {doc_roles} ---")
        
        # Kiểm tra sự giao nhau giữa 2 danh sách role
        if set(test_allowed_roles).intersection(set(doc_roles)):
            print("✅ Kiểm tra Role THÀNH CÔNG. Người dùng có quyền truy cập document này.")
        else:
            print("❌ LỖI: Kiểm tra Role THẤT BẠI. Role cho phép không khớp với role của document.")
            print("Đây có thể là lý do chính khiến hàm `find_document_chunks` trả về rỗng.")

    except pymongo.errors.ConnectionFailure as e:
        print(f"❌ Kết nối MongoDB thất bại: {e}")
        print("Gợi ý: Vui lòng kiểm tra chuỗi kết nối (URI), cài đặt firewall và đảm bảo server database đang chạy.")
    except pymongo.errors.OperationFailure as e:
        print(f"❌ Thao tác MongoDB thất bại: {e}")
        print("Gợi ý: Thường là lỗi xác thực. Vui lòng kiểm tra lại username, password, và `authSource` database.")
    except Exception as e:
        print(f"Một lỗi không mong muốn đã xảy ra: {e}")
    finally:
        if client:
            client.close()
            print("\n--- Đã đóng kết nối. ---")

# Chạy hàm kiểm tra
simple_db_test()
