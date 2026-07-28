from database import get_connection

email = input("Email tài khoản cần cấp admin: ").strip().lower()

if not email:
    raise SystemExit("Bạn chưa nhập email.")

connection = get_connection()

try:
    user = connection.execute(
        """
        SELECT id, full_name, email
        FROM users
        WHERE LOWER(email)=?
        """,
        (email,),
    ).fetchone()

    if user is None:
        raise SystemExit("Không tìm thấy tài khoản.")

    connection.execute(
        """
        UPDATE users
        SET role='admin',
            is_active=1
        WHERE id=?
        """,
        (user["id"],),
    )

    connection.commit()

    print("===================================")
    print("Đã cấp quyền ADMIN thành công")
    print("Tên:", user["full_name"])
    print("Email:", user["email"])
    print("===================================")

finally:
    connection.close()