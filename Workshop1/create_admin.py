from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "users.db"

email = input("Email tài khoản cần cấp admin: ").strip().lower()
if not email:
    raise SystemExit("Bạn chưa nhập email.")

with sqlite3.connect(DB) as conn:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "is_active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    user = conn.execute(
        "SELECT id, full_name, email FROM users WHERE lower(email) = ?",
        (email,),
    ).fetchone()
    if user is None:
        raise SystemExit("Không tìm thấy tài khoản. Hãy đăng ký tài khoản trước.")

    conn.execute(
        "UPDATE users SET role = 'admin', is_active = 1 WHERE id = ?",
        (user[0],),
    )

print(f"Đã cấp quyền admin cho {user[1]} ({user[2]}).")
print("Mở lại website và truy cập /admin. Bản sửa app sẽ tự đọc lại quyền từ CSDL.")
