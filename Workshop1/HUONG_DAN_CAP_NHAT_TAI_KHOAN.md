# Cập nhật quản lý tài khoản

1. Chép đè `app.py`, `templates/admin/users.html`, `static/admin/admin.js`, `static/admin/admin.css`.
2. Không chép đè `users.db` và `.env`.
3. Dừng server, chạy lại `app.py`, sau đó nhấn Ctrl+F5.
4. Trang Người dùng mặc định chỉ hiện User. Chuyển tab Quản trị viên để xem Admin.
5. Dòng “Database đang đọc” giúp kiểm tra Admin và trang đăng ký có dùng cùng một file `users.db` hay không.
6. Nếu tài khoản mới vẫn không xuất hiện, kiểm tra server website thật và server Admin có cùng thư mục dự án/database hay không.
