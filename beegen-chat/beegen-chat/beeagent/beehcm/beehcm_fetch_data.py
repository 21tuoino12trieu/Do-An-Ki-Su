import psycopg2
from psycopg2.extras import RealDictCursor

from .table_schema import table_schemas

def map_row_by_description(row: dict, field_map: dict) -> dict:
    """
    Chuyển key của row từ column name sang description tương ứng.

    Args:
        row (dict): 1 bản ghi từ DB
        field_map (dict): Mapping {column_name: description}

    Returns:
        dict: Row mới với key là description
    """
    new_row = {}
    for col, value in row.items():
        new_key = field_map.get(col, col)  # fallback nếu thiếu schema
        new_row[new_key] = value
    return new_row

# def fetch_user_all_data(username: str, table_schemas: list) -> dict:
#     """
#     Truy vấn toàn bộ thông tin của người dùng trong tất cả các bảng liên quan,
#     dựa vào username. Trả về dữ liệu theo cấu trúc JSON chuẩn.

#     Args:
#         username (str): Tên đăng nhập cần truy vấn.
#         conn_info (dict): Thông tin kết nối PostgreSQL.
#         table_schemas (list): Danh sách schema các bảng.

#     Returns:
#         dict: Dữ liệu dạng:
#         {
#             "tables": {
#                 "table1": [ {row}, {row}, ... ],
#                 "table2": [ {row}, ... ],
#                 ...
#             }
#         }
#     """

#     conn_info=DB_INFO

#     result_json = {"tables": {}}

#     # --- Bước 1: Lấy dữ liệu từ bảng gốc beehi_base_emp_info ---
#     base_table = "beehi_base_emp_info"
#     employeeid = None

#     try:
#         with psycopg2.connect(**conn_info) as conn:
#             with conn.cursor(cursor_factory=RealDictCursor) as cur:
#                 query = f"""
#                     SELECT * 
#                     FROM chatbot_beehi_hcm.{base_table}
#                     WHERE username = %s
#                 """
#                 cur.execute(query, (username,))
#                 base_rows = cur.fetchall()
#                 result_json["tables"][base_table] = [dict(r) for r in base_rows]

#                 if base_rows:
#                     employeeid = base_rows[0].get("employeeid")

#     except Exception as e:
#         print(f"Lỗi truy vấn bảng {base_table}: {e}")
#         result_json["tables"][base_table] = []
#         return result_json  # Không có bảng gốc thì không thể truy xuất các bảng phụ

#     # Nếu không có employeeid thì dừng lại
#     if not employeeid:
#         print("Không tìm thấy employeeid từ bảng beehi_base_emp_info.")
#         return result_json

#     # --- Bước 2: Truy vấn các bảng còn lại dựa vào employeeid ---
#     for schema in table_schemas:
#         table_name = schema["table_name"]

#         # Bỏ qua bảng gốc vì đã truy vấn phía trên
#         if table_name == base_table:
#             continue

#         # Xác định cột dùng để lọc: hầu hết đều có employeeid
#         filter_column = None
#         for f in schema["fields"]:
#             if f["name"] == "employeeid":
#                 filter_column = "employeeid"
#                 break

#         if not filter_column:
#             # Nếu bảng không có employeeid thì không liên quan tới user → bỏ qua
#             result_json["tables"][table_name] = []
#             continue

#         # Thực thi truy vấn
#         try:
#             with psycopg2.connect(**conn_info) as conn:
#                 with conn.cursor(cursor_factory=RealDictCursor) as cur:
#                     query = f"""
#                         SELECT * 
#                         FROM chatbot_beehi_hcm.{table_name}
#                         WHERE {filter_column} = %s
#                     """
#                     cur.execute(query, (employeeid,))
#                     rows = cur.fetchall()
#                     result_json["tables"][table_name] = [dict(r) for r in rows]

#         except Exception as e:
#             print(f"Lỗi truy vấn bảng {table_name}: {e}")
#             result_json["tables"][table_name] = []

#     return result_json


def fetch_user_all_data(username: str, conn_info: dict, table_schemas: list) -> dict:
    """
    Truy vấn toàn bộ thông tin của người dùng trong tất cả các bảng liên quan,
    dựa vào username. Trả về dữ liệu theo cấu trúc JSON chuẩn,
    trong đó key của từng field là description trong table_schema.

    Args:
        username (str): Tên đăng nhập cần truy vấn
        conn_info (dict): Thông tin kết nối PostgreSQL
        table_schemas (list): Danh sách schema các bảng

    Returns:
        dict:
        {
            "tables": {
                "table_name": [
                    { "description_field": value, ... }
                ]
            }
        }
    """

    result_json = {"tables": {}}
    base_table = "beehi_base_emp_info"
    employeeid = None

    # -------------------------
    # BƯỚC 1: Truy vấn bảng gốc
    # -------------------------
    try:
        with psycopg2.connect(**conn_info) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT *
                    FROM chatbot_beehi_hcm.{base_table}
                    WHERE username = %s
                """
                cur.execute(query, (username,))
                base_rows = cur.fetchall()

                # Lấy schema của bảng gốc
                base_schema = next(
                    (s for s in table_schemas if s["table_name"] == base_table),
                    None
                )

                if base_schema:
                    field_map = {
                        f["name"]: f.get("description", f["name"])
                        for f in base_schema.get("fields", [])
                    }
                    mapped_rows = [
                        map_row_by_description(dict(r), field_map)
                        for r in base_rows
                    ]
                else:
                    mapped_rows = [dict(r) for r in base_rows]

                result_json["tables"][base_table] = mapped_rows

                if base_rows:
                    employeeid = base_rows[0].get("employeeid")

    except Exception as e:
        print(f"Lỗi truy vấn bảng {base_table}: {e}")
        result_json["tables"][base_table] = []
        return result_json

    # Không có employeeid thì dừng
    if not employeeid:
        print("Không tìm thấy employeeid từ bảng beehi_base_emp_info.")
        return result_json

    # ----------------------------------
    # BƯỚC 2: Truy vấn các bảng liên quan
    # ----------------------------------
    for schema in table_schemas:
        table_name = schema.get("table_name")

        if table_name == base_table:
            continue

        # Kiểm tra có cột employeeid không
        has_employeeid = any(
            f.get("name") == "employeeid"
            for f in schema.get("fields", [])
        )

        if not has_employeeid:
            result_json["tables"][table_name] = []
            continue

        # Tạo mapping column -> description
        field_map = {
            f["name"]: f.get("description", f["name"])
            for f in schema.get("fields", [])
        }

        try:
            with psycopg2.connect(**conn_info) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = f"""
                        SELECT *
                        FROM chatbot_beehi_hcm.{table_name}
                        WHERE employeeid = %s
                    """
                    cur.execute(query, (employeeid,))
                    rows = cur.fetchall()

                    mapped_rows = [
                        map_row_by_description(dict(r), field_map)
                        for r in rows
                    ]

                    result_json["tables"][table_name] = mapped_rows

        except Exception as e:
            print(f"Lỗi truy vấn bảng {table_name}: {e}")
            result_json["tables"][table_name] = []

    return result_json



DB_INFO = {
    "host": "10.215.107.49",
    "port": 5432,
    "database": "hr_information",
    "user": "hr_information",
    "password": "hr_information",
}
# user_data = fetch_user_all_data(
#     username="dannk.os",
#     conn_info=DB_INFO,
#     table_schemas=table_schemas
# )

# print(user_data)


def filter_user_data(all_user_data: dict, tables_to_include: list[str]) -> dict:
    """
    Lọc dữ liệu nhân sự theo danh sách tên bảng chỉ định.

    Args:
        all_user_data (dict): Dữ liệu đầy đủ lấy từ DB theo cấu trúc:
                              { "tables": { "table_name": list[list], ... } }
        tables_to_include (list[str]): Danh sách các tên bảng cần trích xuất.

    Returns:
        dict: Dữ liệu đã lọc theo cấu trúc:
              {
                  "tables": {
                      "table_name_1": [...],
                      "table_name_2": [...],
                      ...
                  }
              }
    """

    if "tables" not in all_user_data:
        return {"tables": {}}

    filtered = {"tables": {}}

    for table_name in tables_to_include:
        if table_name in all_user_data["tables"]:
            filtered["tables"][table_name] = all_user_data["tables"][table_name]
        else:
            # Nếu bảng không tồn tại, vẫn ghi vào để theo dõi
            filtered["tables"][table_name] = []

    return filtered


# need_tables = ["beehi_base_emp_info", "beehi_emp_leave_info"]

# filtered = filter_user_data(user_data, need_tables)

# print(filtered)
