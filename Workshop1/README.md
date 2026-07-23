# MediCare AI – giao diện Trang chủ + Tư vấn AI riêng

Bộ code này được ghép trực tiếp từ `app(13).py` mới của dự án. Các phần AI, RAG, đăng nhập, admin, giọng nói, xử lý ảnh và database hiện có được giữ nguyên; chỉ bổ sung giao diện mới và các API cần thiết.

## File cần thay/thêm

```text
Workshop1/
├── app.py                         # thay bằng file mới
├── requirements.txt              # có thể giữ file hiện tại nếu giống nhau
├── templates/
│   ├── index.html                 # thay trang chủ
│   └── chat.html                  # thêm trang tư vấn riêng
└── static/
    ├── common.js                  # thêm
    ├── dashboard.css              # thêm/thay
    ├── dashboard.js               # thêm/thay
    ├── chat.css                   # thêm
    └── chat.js                    # thêm
```

Không chép đè `users.db`, `.env`, thư mục `database/` hoặc `data/`.

## Chạy dự án

```powershell
cd C:\AI.CHATBOT\Workshop1
python app.py
```

- Trang chủ: `http://127.0.0.1:5000/`
- Tư vấn AI: `http://127.0.0.1:5000/tu-van`

Sau khi thay file, nhấn `Ctrl + F5` để trình duyệt tải lại CSS/JS mới.

## Chức năng đã nối thật

- Trang `Tư vấn AI` riêng, mở trong cùng tab.
- Lịch sử trò chuyện, tìm kiếm, lọc yêu thích, mở lại và xóa lịch sử.
- Chọn đúng thành viên gia đình; hồ sơ được gửi cùng câu hỏi cho backend.
- Chuyên khoa được giữ thành tag và gửi vào ngữ cảnh AI.
- Gửi chữ, ảnh và ghi âm.
- Sao chép/lưu câu trả lời và xuất cuộc trò chuyện ra `.txt`.
- Đăng ký, đăng nhập và đăng xuất bằng API hiện có.
- Giao diện sáng/tối.
- Vị trí chính xác hơn bằng `watchPosition`, `enableHighAccuracy: true`, không dùng vị trí cache và chọn kết quả có sai số nhỏ nhất trong nhiều lần đo.
- Hiển thị sai số vị trí dạng `±... m` để không giả vờ rằng tọa độ luôn chính xác tuyệt đối.
- Backend lấy địa chỉ, thời tiết, AQI/PM2.5 và danh sách nhà thuốc gần nhất.
- Nút chỉ đường mở đúng nhà thuốc trên Google Maps.
- Nút gọi khẩn cấp `115`.

## Lưu ý về định vị

- Trên website triển khai, định vị cần chạy bằng `HTTPS`.
- `localhost` vẫn dùng được khi phát triển.
- Máy tính bàn thường xác định qua Wi‑Fi/mạng nên có thể sai số lớn hơn điện thoại có GPS.
- Hãy bật quyền Location của trình duyệt và Windows; khi cần chính xác hơn, dùng điện thoại hoặc bật Wi‑Fi.
- Public Nominatim/Overpass phù hợp cho demo và lưu lượng nhỏ. Khi triển khai nhiều người dùng, nên chuyển sang nhà cung cấp bản đồ có SLA hoặc tự host.

## Git và `users.db`

`users.db` là dữ liệu chạy trên từng máy, không nên tiếp tục commit lên GitHub. Sau khi nhóm thống nhất, thực hiện một lần:

```powershell
git rm --cached Workshop1/users.db
git add .gitignore
git commit -m "Ignore local database"
git push
```
