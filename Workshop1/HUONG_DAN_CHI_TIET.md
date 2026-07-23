# CÀI ADMIN DASHBOARD

1. Backup toàn bộ dự án, nhất là app.py và users.db.
2. Chép app.py mới vào thư mục Workshop1.
3. Chép templates/admin vào templates/admin và static/admin vào static/admin.
4. Chép create_admin.py cùng cấp với app.py.
5. Chạy `python app.py` một lần để tự nâng cấp database.
6. Đăng ký một tài khoản bình thường trên web.
7. Dừng server, chạy `python create_admin.py`, nhập email tài khoản đó.
8. Chạy lại `python app.py`, đăng nhập rồi mở `http://127.0.0.1:5000/admin`.
9. Khi deploy, mở `https://chatbotsuckhoe.site/admin`.

Chức năng: thống kê, tìm user, khóa/mở khóa, cấp/thu admin, nhật ký thao tác, sao lưu users.db.

An toàn: admin không thể tự khóa hoặc tự hạ quyền. Không bật debug=True trên server thật. Không đưa .env/users.db lên GitHub.
