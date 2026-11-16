import json
import pymongo
from pymongo.errors import ConnectionFailure
from pathlib import Path

# Giả định rằng file này được đặt ở vị trí có thể import được
# 'beegenerate.configs'. Dựa trên cấu trúc file bạn cung cấp,
# import này là chính xác.
try:
    from beegenerate.configs import MongoConfig
except ImportError:
    print(
        "Error: Could not import MongoConfig. Make sure this script is run from the project's root directory or the path is configured correctly.")
    exit(1)


def main():
    """
    Hàm chính để đọc kịch bản từ file scenarios.json và đẩy lên MongoDB.
    Hàm này có tính năng upsert để tránh tạo bản ghi trùng lặp khi chạy lại.
    """
    print("--- Starting Scenario Migration to MongoDB ---")

    # 1. Đọc và tải file scenarios.json
    scenarios_file_path = "beechat/services/scenario_management/scenarios.json"
    try:
        with open(scenarios_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            scenarios_from_file = data.get('scenarios', [])
            if not scenarios_from_file:
                print("Error: 'scenarios.json' is empty or does not contain a 'scenarios' key.")
                return
            print(f"Successfully loaded {len(scenarios_from_file)} scenarios from '{scenarios_file_path}'.")
    except FileNotFoundError:
        print(f"Error: The file '{scenarios_file_path}' was not found.")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse '{scenarios_file_path}'. Invalid JSON format: {e}")
        return

    # 2. Kết nối đến MongoDB
    collection = None
    try:
        config = MongoConfig.default()
        client = pymongo.MongoClient(config.uri)

        # Ping server để xác nhận kết nối
        client.admin.command('ping')

        db_name = config.authen_source
        db = client[db_name]
        collection = db['scenarios']
        print(f"Successfully connected to MongoDB. Database: '{db_name}', Collection: 'scenarios'.")
    except ConnectionFailure as e:
        print(
            f"Error: Could not connect to MongoDB at '{config.uri}'. Please check the connection string and network. Details: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB connection: {e}")
        return

    # 3. Di chuyển dữ liệu (sử dụng upsert để đảm bảo an toàn khi chạy lại)
    newly_inserted = 0
    updated = 0

    print("\nMigrating scenarios...")
    for scenario in scenarios_from_file:
        scenario_id = scenario.get("id")
        if not scenario_id:
            print(f"Skipping a scenario because it's missing the required 'id' field.")
            continue

        try:
            # upsert=True sẽ tạo mới nếu không tìm thấy, hoặc cập nhật nếu tìm thấy
            result = collection.update_one(
                {'id': scenario_id},  # Điều kiện lọc: tìm kịch bản có cùng 'id'
                {'$set': scenario},  # Dữ liệu để cập nhật hoặc tạo mới
                upsert=True  # Bật tính năng "update or insert"
            )

            if result.upserted_id:
                print(f"  - INSERTED new scenario: '{scenario_id}'")
                newly_inserted += 1
            elif result.modified_count > 0:
                print(f"  - UPDATED existing scenario: '{scenario_id}'")
                updated += 1
            else:
                # Trường hợp này xảy ra nếu dữ liệu trong DB và file giống hệt nhau
                print(f"  - SKIPPED scenario (no changes): '{scenario_id}'")


        except Exception as e:
            print(f"Error migrating scenario '{scenario_id}': {e}")

    print("\n--- Migration Complete ---")
    print("Summary:")
    print(f"  - Scenarios newly inserted: {newly_inserted}")
    print(f"  - Scenarios updated: {updated}")
    print(f"  - Total scenarios processed: {len(scenarios_from_file)}")
    print("You can now start the application. It will load scenarios from the database.")


if __name__ == "__main__":
    main()
