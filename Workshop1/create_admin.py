from pathlib import Path
import sqlite3
DB=Path(__file__).resolve().parent/"users.db"
email=input("Email tài khoản cần cấp admin: ").strip().lower()
conn=sqlite3.connect(DB)
cols={r[1] for r in conn.execute("PRAGMA table_info(users)")}
if "role" not in cols: conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
if "is_active" not in cols: conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
row=conn.execute("SELECT id,full_name FROM users WHERE lower(email)=?",(email,)).fetchone()
if not row: raise SystemExit("Không tìm thấy tài khoản. Hãy đăng ký trước.")
conn.execute("UPDATE users SET role='admin',is_active=1 WHERE id=?",(row[0],)); conn.commit(); conn.close()
print("Đã cấp quyền admin cho",row[1])
