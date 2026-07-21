from pathlib import Path
import re
import sqlite3
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
DATABASE_PATH = BASE_DIR / "database" / "medical.db"

PARQUET_PATH = RAW_DIR / "train-00000-of-00001.parquet"
TRAIN_PATH = RAW_DIR / "train.csv"
VAL_PATH = RAW_DIR / "val.csv"
TEST_PATH = RAW_DIR / "test.csv"


def normalize_text(value):
    """
    Chuẩn hóa văn bản để phát hiện câu hỏi trùng tốt hơn.
    """
    if pd.isna(value):
        return ""

    value = str(value).strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[?!.;,]+$", "", value)

    return value


# Kiểm tra các file có tồn tại không
required_files = [
    PARQUET_PATH,
    TRAIN_PATH,
    VAL_PATH,
    TEST_PATH,
]

for file_path in required_files:
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")


# Đọc dataset cũ
old_df = pd.read_parquet(PARQUET_PATH)

# Chỉ lấy các cột cần thiết
old_df = old_df[["question", "answer"]].copy()
old_df["link"] = ""
old_df["source"] = "vietnamese-medical-qa"


# Đọc 3 file ViHealthQA
train_df = pd.read_csv(TRAIN_PATH)
val_df = pd.read_csv(VAL_PATH)
test_df = pd.read_csv(TEST_PATH)

train_df["source"] = "ViHealthQA-train"
val_df["source"] = "ViHealthQA-val"
test_df["source"] = "ViHealthQA-test"


# Gộp 3 file CSV
vihealth_df = pd.concat(
    [train_df, val_df, test_df],
    ignore_index=True
)

# Chỉ giữ các cột cần thiết
vihealth_df = vihealth_df[
    ["question", "answer", "link", "source"]
].copy()


# Gộp dataset cũ và dataset mới
combined_df = pd.concat(
    [old_df, vihealth_df],
    ignore_index=True
)

print("Tổng dữ liệu trước khi làm sạch:", len(combined_df))


# Xóa dòng thiếu câu hỏi hoặc câu trả lời
combined_df = combined_df.dropna(
    subset=["question", "answer"]
)

combined_df["question"] = combined_df["question"].astype(str).str.strip()
combined_df["answer"] = combined_df["answer"].astype(str).str.strip()

combined_df = combined_df[
    (combined_df["question"] != "")
    & (combined_df["answer"] != "")
]


# Tạo cột dùng để kiểm tra trùng
combined_df["normalized_question"] = combined_df[
    "question"
].apply(normalize_text)


# Đếm số câu hỏi bị trùng
duplicate_count = combined_df.duplicated(
    subset=["normalized_question"]
).sum()

print("Số câu hỏi trùng phát hiện được:", duplicate_count)


# Xóa câu hỏi trùng, giữ bản đầu tiên
combined_df = combined_df.drop_duplicates(
    subset=["normalized_question"],
    keep="first"
)


# Xóa cột phụ
combined_df = combined_df.drop(
    columns=["normalized_question"]
)


# Tạo lại ID
combined_df = combined_df.reset_index(drop=True)
combined_df.insert(
    0,
    "id",
    range(1, len(combined_df) + 1)
)


# Đảm bảo thư mục database tồn tại
DATABASE_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)


# Ghi vào SQLite
connection = sqlite3.connect(DATABASE_PATH)

combined_df.to_sql(
    "medical_qa",
    connection,
    if_exists="replace",
    index=False
)

connection.close()


print("Tổng dữ liệu sau khi xóa trùng:", len(combined_df))
print("Đã cập nhật database tại:", DATABASE_PATH)