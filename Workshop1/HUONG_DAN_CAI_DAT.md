# CÀI ĐẶT MEDICARE ADMIN V2

## 1. Sao lưu
Sao chép `app.py`, `users.db`, `.env` và thư mục `templates/admin`, `static/admin`.

## 2. Chép file
- `app.py` → `Workshop1/app.py`
- `templates/admin/*` → `Workshop1/templates/admin/`
- `static/admin/*` → `Workshop1/static/admin/`

Không thay `users.db`, `.env`, `database/medical.db`.

## 3. Dừng và chạy lại
```powershell
Ctrl + C
& "C:\Users\ADMIN\AppData\Local\Programs\Python\Python314\python.exe" app.py
```

## 4. Xóa cache trình duyệt
Mở `/admin`, nhấn `Ctrl + F5`.

## Sửa lỗi giao diện
CSS và JavaScript dùng:
```jinja2
{{ url_for('static', filename='admin/admin.css') }}
{{ url_for('static', filename='admin/admin.js') }}
```
nên không phụ thuộc thư mục chạy.

## Tự cập nhật
- Dashboard: 5 giây
- Người dùng: 5 giây
- Lịch sử chat: 5 giây
- Có nút làm mới thủ công
