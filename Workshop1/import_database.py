from pathlib import Path
import sqlite3

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

DATASET_PATH = (
    BASE_DIR
    / "data"
    / "raw"
    / "train-00000-of-00001.parquet"
)

DATABASE_PATH = (
    BASE_DIR
    / "database"
    / "medical.db"
)


if not DATASET_PATH.exists():
    raise FileNotFoundError(
        f"Không tìm thấy file: {DATASET_PATH}"
    )

if not DATASET_PATH.is_file():
    raise ValueError(
        f"Đường dẫn này đang là thư mục, không phải file: "
        f"{DATASET_PATH}"
    )

print("Đang đọc dataset...")
df = pd.read_parquet(DATASET_PATH)

print("Số dòng:", len(df))
print("Các cột:", df.columns.tolist())
print(df.head())

required_columns = {"question", "answer"}

if not required_columns.issubset(df.columns):
    raise ValueError(
        "Dataset phải có cột question và answer. "
        f"Các cột hiện có: {df.columns.tolist()}"
    )

df = df[["question", "answer"]].dropna()

df["question"] = df["question"].astype(str).str.strip()
df["answer"] = df["answer"].astype(str).str.strip()

df = df[
    (df["question"] != "")
    & (df["answer"] != "")
]

DATABASE_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)

connection = sqlite3.connect(DATABASE_PATH)

df.to_sql(
    "medical_qa",
    connection,
    if_exists="replace",
    index=False
)

connection.close()

print(f"Đã nhập {len(df)} dòng vào database.")
print(f"Database được tạo tại: {DATABASE_PATH}")