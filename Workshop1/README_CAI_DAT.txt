CÁCH CÀI ĐẶT

1. Thay file static/common.js bằng common.js trong thư mục này.
2. Thay các template tương ứng: index.html, chat.html, knowledge.html, pharmacies.html.
3. Trong Flask app.py cần thêm cấu hình bên dưới để cookie đăng nhập thật sự tồn tại tối đa 30 ngày:

from datetime import timedelta

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Chỉ bật True khi website chạy HTTPS:
app.config["SESSION_COOKIE_SECURE"] = True

4. Trong route /login, sau khi kiểm tra đúng tài khoản, thêm:

session.permanent = True

Lưu ý: common.js đã tự kiểm tra mốc 30 ngày và gọi /logout. Cấu hình Flask ở trên là phần bắt buộc để cookie phía máy chủ cũng giữ đúng 30 ngày.
