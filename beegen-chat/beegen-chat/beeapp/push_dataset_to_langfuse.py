import pandas as pd
from beegen_v1.registry.model_registry import ModelRegistry
from tqdm import tqdm

langfuse = ModelRegistry.self().langfuse("beegen")

# Read the specific sheet from the Excel file
file_path = "Bộ câu hỏi test - Chatbot AI 2.0.xlsx"
sheet_name = "Chat 1-1"

# Read the Excel file into a pandas DataFrame
df = pd.read_excel(file_path, sheet_name=sheet_name)

# Display basic information about the DataFrame
print("DataFrame shape:", df.shape)
print("\nColumn names:")
print(df.columns.tolist())
print("\nFirst few rows:")
print(df.head())

# If you want to verify the specific columns you mentioned
expected_columns = ["STT", "Sản phẩm", "Câu hỏi", "Câu trả lời mong muốn (Team dự án biên soạn)"]
print(f"\nExpected columns present: {all(col in df.columns for col in expected_columns)}")

# Rename columns to simpler English names
df.columns = ['STT', 'product', 'question', 'answer']

# Display updated column names
print("\nRenamed columns:")
print(df.columns.tolist())

# Display data types
print("\nData types:")
print(df.dtypes)

# Show the DataFrame with new column names
print("\nDataFrame with renamed columns:")
print(df.head())


df = df[["product", "question", "answer"]]
local_items = df.to_dict("records")

langfuse.create_dataset(name="beeapp_500_qa_2.0");

for item in tqdm(local_items):
    try:
        langfuse.create_dataset_item(
            dataset_name="beeapp_500_qa_2.0",
            input=item["question"],
            expected_output=item["answer"]
        )
    except ValueError:
        print(item)