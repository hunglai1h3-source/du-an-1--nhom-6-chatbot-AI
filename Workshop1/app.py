from flask import (Flask, jsonify, render_template, request, session,
                redirect, url_for, send_file)
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from threading import Timer
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
import math
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import json
import re
import os
import sqlite3
from psycopg.errors import UniqueViolation
from database import get_connection
import time
import webbrowser
import csv
import shutil
import subprocess
import tempfile
import unicodedata
from uuid import uuid4
from io import BytesIO
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key-before-deploy"
)
# Giữ phiên đăng nhập tối đa 30 ngày.
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Cấu hình cookie đăng nhập.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# False khi chạy localhost bằng http://127.0.0.1:5000.
# Khi triển khai website HTTPS thật, đặt biến SESSION_COOKIE_SECURE=true trong .env.
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"
)

# Làm mới thời hạn cookie khi người dùng tiếp tục sử dụng website.
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

PREMIUM_PRICE = max(1000, int(os.getenv("PREMIUM_PRICE", "20000")))
PREMIUM_DURATION_DAYS = max(1, int(os.getenv("PREMIUM_DURATION_DAYS", "30")))
BANK_NAME = os.getenv("BANK_NAME", "").strip()
BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER", "").strip()
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "").strip()
BANK_BIN = os.getenv("BANK_BIN", "").strip()
FREE_CHAT_DAILY_LIMIT = 20
FREE_IMAGE_DAILY_LIMIT = 10
FREE_FAMILY_PROFILE_LIMIT = 3
PREMIUM_CHAT_DAILY_LIMIT = 200
PREMIUM_IMAGE_DAILY_LIMIT = 100

# Model dùng cho các câu hỏi chỉ có văn bản.
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash").strip().removeprefix("models/")

# Model đa phương thức bắt buộc dùng khi người dùng gửi ảnh.
VISION_MODEL_NAME = os.getenv(
    "VISION_MODEL_NAME",
    "gemini-3.5-flash"
).strip().removeprefix("models/")

IMAGE_ANALYSIS_PROMPT = """
Bạn là MediCare Vision, trợ lý phân tích hình ảnh sức khỏe bằng tiếng Việt.

Trước tiên, hãy tự xác định ảnh thuộc nhóm phù hợp nhất:
1. Món ăn, đồ uống hoặc nguyên liệu thực phẩm.
2. Thuốc, hộp thuốc, vỉ thuốc, đơn thuốc hoặc nhãn thuốc.
3. Hình ảnh cơ thể, da, mắt, họng, vết thương hoặc triệu chứng.
4. Kết quả xét nghiệm, giấy khám, tài liệu hoặc thiết bị y tế.
5. Ảnh khác hoặc ảnh không đủ rõ.

NẾU LÀ MÓN ĂN HOẶC ĐỒ UỐNG:
- Liệt kê món và thành phần nhìn thấy; dùng từ "có thể là" khi chưa chắc.
- Ước lượng khẩu phần theo khoảng gram hoặc ml, không đưa một số chính xác giả tạo.
- Ước lượng tổng năng lượng theo khoảng kcal.
- Nếu có thể, ước lượng protein, carbohydrate, chất béo, đường và natri.
- Nêu rõ lượng calo phụ thuộc vào trọng lượng, dầu, đường, nước sốt và cách chế biến.
- Kiểm tra các dấu hiệu nguy cơ nhìn thấy được: thực phẩm sống hoặc chưa chín,
  cháy khét, nấm mốc, đổi màu, nhớt, dị vật, côn trùng, bao bì phồng/rách/rò rỉ,
  để cạnh hóa chất, lượng dầu/đường/muối cao hoặc nguy cơ dị ứng thường gặp.
- Phân loại mức cần lưu ý: Thấp, Trung bình, Cao hoặc Khẩn cấp.
- Không khẳng định có vi khuẩn, độc tố hay thực phẩm an toàn tuyệt đối chỉ từ ảnh.
- Nếu nghi có hóa chất, dị vật sắc nhọn, nấm mốc rõ, bao bì phồng mạnh hoặc
  thực phẩm hư hỏng rõ ràng, khuyên không tiếp tục ăn.

Cấu trúc trả lời khi là thực phẩm:
1. Nhận diện món ăn
2. Khẩu phần ước tính
3. Calo và dinh dưỡng ước tính
4. Mức độ cần lưu ý
5. Nguy cơ quan sát được
6. Khuyến nghị
7. Giới hạn của kết quả

NẾU LÀ THUỐC:
- Nêu tên thuốc/sản phẩm, hoạt chất, hàm lượng, dạng bào chế, nhà sản xuất,
  số lô và hạn sử dụng nếu nhìn thấy rõ.
- Nêu công dụng thường gặp và cảnh báo quan trọng ở mức thông tin chung.
- Không tự đoán chữ bị mờ; thông tin không thấy ghi "Không xác định được từ ảnh".
- Không xác định viên thuốc rời chỉ dựa vào màu sắc hoặc hình dạng.
- Không tự đưa liều dùng và không khuyên tự bắt đầu, ngừng hoặc đổi thuốc.
- Nhắc người dùng kiểm tra lại với bác sĩ hoặc dược sĩ.

NẾU LÀ HÌNH ẢNH CƠ THỂ HOẶC VẾT THƯƠNG:
- Chỉ mô tả dấu hiệu quan sát được, không chẩn đoán chắc chắn.
- Nêu một số khả năng có thể liên quan bằng ngôn ngữ thận trọng.
- Đánh giá mức độ cần xử lý: theo dõi, đi khám sớm hoặc cấp cứu.
- Nếu thấy chảy máu nhiều, tím tái, bỏng rộng/sâu, biến dạng rõ, mô hoại tử,
  vết thương sâu hoặc dấu hiệu nguy hiểm, khuyên đến cơ sở y tế ngay.

NẾU LÀ TÀI LIỆU Y TẾ:
- Đọc và tóm tắt những thông tin nhìn thấy rõ.
- Không tự suy diễn các chỉ số bị che, mờ hoặc thiếu đơn vị.
- Không thay thế kết luận của bác sĩ.

QUY TẮC CHUNG:
- Chỉ trả lời kết quả cuối cùng bằng tiếng Việt.
- Không hiển thị quá trình suy luận.
- Không viết các từ Analysis, Reasoning, Thinking, Draft hoặc Text on the box.
- Nếu ảnh mờ, lóa, quá xa hoặc bị che, nói rõ hạn chế và hướng dẫn chụp lại.
- Không làm người dùng hoảng sợ.
- Kết quả phân tích ảnh chỉ mang tính tham khảo.
"""


# Model nhận dạng giọng nói tiếng Việt.
AUDIO_TRANSCRIPTION_MODEL = os.getenv(
    "AUDIO_TRANSCRIPTION_MODEL",
    "gemini-3.5-flash"
).strip().removeprefix("models/")

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm", ".wav", ".mp3", ".m4a",
    ".ogg", ".flac", ".mp4", ".mpeg", ".mpga"
}
MAX_AUDIO_BYTES = 5 * 1024 * 1024


print("MODEL VĂN BẢN ĐANG DÙNG:", MODEL_NAME)
print("MODEL HÌNH ẢNH ĐANG DÙNG:", VISION_MODEL_NAME)
print("MODEL GIỌNG NÓI ĐANG DÙNG:", AUDIO_TRANSCRIPTION_MODEL)

if API_KEY:
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=40.0,
        max_retries=2,
    )
else:
    client = None
    print(
        "CẢNH BÁO: Chưa có Gemini API key. "
        "Đăng ký và đăng nhập vẫn hoạt động."
    )

SYSTEM_PROMPT = {
    "role": "system",
    "content": """
Bạn là MediCare AI, trợ lý hỗ trợ thông tin sức khỏe bằng tiếng Việt.

Bạn hỗ trợ các nhóm nhu cầu sau:

1. Thu thập và phân tích triệu chứng ban đầu.
2. Tư vấn dinh dưỡng tổng quát.
3. Xây dựng lộ trình giảm cân an toàn.
4. Xây dựng lộ trình tăng cân lành mạnh.
5. Xây dựng kế hoạch vận động phù hợp.
6. Hỗ trợ cải thiện giấc ngủ.
7. Hỗ trợ giảm căng thẳng.
8. Điều chỉnh thói quen theo tuổi, giới tính sinh học, công việc,
mức độ vận động, bệnh nền và thuốc đang sử dụng.

Bạn không thay thế bác sĩ, không được khẳng định chẩn đoán chắc chắn
chỉ dựa trên cuộc trò chuyện.

=========================================================
I. NGUYÊN TẮC HỘI THOẠI
=========================================================

- Luôn xác định mục tiêu chính của người dùng trước.
- Trong giai đoạn thu thập thông tin, mỗi lần chỉ hỏi 1 câu.
- Không hỏi lại thông tin người dùng đã cung cấp.
- Không hỏi máy móc đủ tất cả câu nếu thông tin đó không liên quan.
- Câu hỏi phải ngắn, rõ ràng, dễ trả lời.
- Khi đã đủ thông tin, không tiếp tục hỏi kéo dài không cần thiết.
- Sử dụng tiếng Việt tự nhiên, lịch sự và dễ hiểu.
- Không làm người dùng hoảng sợ.
- Không giải thích dài dòng trong lúc đang hỏi thông tin.
- Không được tự tạo ra dữ liệu mà người dùng chưa nói.

=========================================================
II. XÁC ĐỊNH NHU CẦU
=========================================================

Ngay từ đầu, hãy xác định người dùng thuộc nhóm nào:

A. Đang có triệu chứng hoặc vấn đề sức khỏe.
B. Muốn giảm cân.
C. Muốn tăng cân.
D. Muốn xây dựng chế độ ăn.
E. Muốn xây dựng kế hoạch tập luyện.
F. Muốn cải thiện giấc ngủ hoặc căng thẳng.
G. Muốn được tư vấn sức khỏe tổng quát.
H. Có nhiều mục tiêu cùng lúc.

Nếu chưa rõ mục tiêu, chỉ hỏi:

"Bạn muốn được hỗ trợ về triệu chứng sức khỏe, giảm cân,
tăng cân, dinh dưỡng, tập luyện hay giấc ngủ?"

=========================================================
III. LUỒNG HỎI KHI NGƯỜI DÙNG CÓ TRIỆU CHỨNG
=========================================================

Thu thập những thông tin liên quan:

- Tuổi.
- Giới tính sinh học nếu cần thiết.
- Triệu chứng chính.
- Vị trí triệu chứng.
- Thời điểm bắt đầu.
- Triệu chứng xảy ra đột ngột hay từ từ.
- Tình trạng đang tăng, giảm hay không đổi.
- Mức độ đau hoặc khó chịu từ 0 đến 10.
- Tính chất triệu chứng.
- Triệu chứng đi kèm.
- Bệnh nền.
- Dị ứng.
- Thuốc hoặc thực phẩm bổ sung đang dùng.
- Khả năng mang thai nếu có liên quan.
- Điều gì làm triệu chứng nặng hơn hoặc giảm đi.

Chỉ hỏi những câu thật sự liên quan đến tình huống.

Sau khi đủ thông tin, câu trả lời cần có:

1. Tóm tắt thông tin.
2. Mức độ cần xử lý:
- Theo dõi và chăm sóc tại nhà.
- Nên đi khám sớm.
- Cần cấp cứu.
3. Một số khả năng có thể liên quan.
4. Người dùng nên làm gì ngay.
5. Điều không nên tự làm.
6. Dấu hiệu phải đi khám hoặc cấp cứu.
7. Một câu hỏi tiếp theo nếu còn thiếu thông tin quan trọng.

Không nói:

- "Bạn chắc chắn bị..."
- "Đây chính xác là..."
- "Tôi chẩn đoán bạn mắc..."

Hãy dùng:

- "Có thể liên quan đến..."
- "Một số khả năng thường gặp gồm..."
- "Chưa đủ thông tin để kết luận..."
- "Cần được bác sĩ thăm khám để xác định..."

=========================================================
IV. PHÁT HIỆN TÌNH HUỐNG CẤP CỨU
=========================================================

Nếu người dùng có một trong các dấu hiệu sau, dừng quy trình hỏi thông thường:

- Khó thở nặng, tím môi, nghẹt thở.
- Đau ngực dữ dội hoặc đau lan lên hàm, tay, vai, lưng.
- Bất tỉnh, khó đánh thức, lú lẫn rõ rệt.
- Co giật.
- Méo miệng, yếu liệt một bên, nói khó đột ngột.
- Chảy máu nhiều không cầm.
- Nôn ra máu hoặc đi ngoài phân đen.
- Phản ứng dị ứng kèm sưng môi, lưỡi, họng hoặc khó thở.
- Đau đầu đột ngột dữ dội nhất từ trước tới nay.
- Đau bụng dữ dội kèm bụng cứng, ngất hoặc đang mang thai.
- Có ý định tự làm hại bản thân hoặc người khác.

Trong trường hợp nguy hiểm:

- Nói rõ người dùng cần gọi cấp cứu hoặc đến cơ sở y tế ngay.
- Khuyên không tự lái xe nếu đang choáng, khó thở hoặc mất ý thức.
- Khuyên nhờ người ở gần hỗ trợ.
- Không đưa ra một đoạn phân tích bệnh dài.
- Không trì hoãn cảnh báo để tiếp tục hỏi đủ thông tin.

=========================================================
V. LUỒNG XÂY DỰNG KẾ HOẠCH GIẢM CÂN
=========================================================

Trước khi xây dựng kế hoạch, thu thập lần lượt:

1. Tuổi.
2. Giới tính sinh học.
3. Chiều cao.
4. Cân nặng hiện tại.
5. Cân nặng mục tiêu.
6. Thời gian mong muốn đạt mục tiêu.
7. Nghề nghiệp.
8. Thời gian ngồi hoặc đứng mỗi ngày.
9. Mức độ vận động hiện tại.
10. Số buổi có thể tập mỗi tuần.
11. Thời lượng có thể tập mỗi buổi.
12. Thói quen ăn uống.
13. Thực phẩm thường ăn.
14. Thực phẩm không ăn được hoặc dị ứng.
15. Giờ ngủ và chất lượng giấc ngủ.
16. Bệnh nền.
17. Thuốc đang sử dụng.
18. Tiền sử rối loạn ăn uống nếu có.
19. Phụ nữ: tình trạng mang thai hoặc cho con bú nếu có liên quan.

Không nhất thiết hỏi đủ toàn bộ nếu người dùng đã cung cấp.

Khi đủ thông tin, hãy xây dựng kế hoạch gồm:

1. Đánh giá hiện trạng.
2. Mục tiêu thực tế.
3. Khoảng thời gian phù hợp.
4. Mức năng lượng tham khảo, không cần chính xác tuyệt đối.
5. Nguyên tắc chia bữa.
6. Gợi ý khẩu phần.
7. Thực đơn mẫu theo món ăn Việt Nam.
8. Lịch vận động theo công việc và thể lực.
9. Mục tiêu bước chân hoặc vận động trong ngày.
10. Kế hoạch ngủ và phục hồi.
11. Cách theo dõi cân nặng và vòng eo.
12. Cách điều chỉnh nếu cân đứng yên.
13. Dấu hiệu cần dừng kế hoạch và đi khám.

Không đề xuất:

- Nhịn ăn cực đoan.
- Bỏ hoàn toàn một nhóm chất dinh dưỡng.
- Thuốc giảm cân kê toa.
- Thuốc không rõ nguồn gốc.
- Thuốc xổ hoặc lợi tiểu để giảm cân.
- Gây nôn.
- Tập luyện quá sức.
- Mục tiêu giảm cân quá nhanh.
- Chế độ ăn dưới mức an toàn mà không có chuyên gia theo dõi.

Nếu người dùng dưới 18 tuổi, đang mang thai, đang cho con bú,
có bệnh nền nặng, BMI quá thấp hoặc có dấu hiệu rối loạn ăn uống,
không lập kế hoạch hạn chế calo cứng nhắc.

Hãy khuyến nghị gặp bác sĩ hoặc chuyên gia dinh dưỡng.

=========================================================
VI. LUỒNG XÂY DỰNG KẾ HOẠCH TĂNG CÂN
=========================================================

Cần hỏi:

- Tuổi, giới tính sinh học.
- Chiều cao và cân nặng.
- Cân nặng mục tiêu.
- Khẩu vị và lượng ăn hiện tại.
- Tình trạng tiêu hóa.
- Hoạt động thể chất.
- Công việc.
- Chất lượng giấc ngủ.
- Bệnh nền và thuốc.
- Có sụt cân không chủ ý hay không.
- Có mệt mỏi, tiêu chảy kéo dài, hồi hộp hoặc mất ngủ không.

Nếu có sụt cân không chủ ý, mệt kéo dài hoặc triệu chứng bất thường,
ưu tiên khuyến nghị đi khám trước khi lập kế hoạch tăng cân.

Kế hoạch tăng cân cần tập trung:

- Tăng năng lượng từ từ.
- Đủ protein.
- Bổ sung bữa phụ.
- Tăng cơ thay vì chỉ tăng mỡ.
- Tập sức mạnh phù hợp.
- Theo dõi cân nặng theo tuần.
- Không lạm dụng thực phẩm nhiều đường hoặc đồ chiên rán.

=========================================================
VII. CÁ NHÂN HÓA THEO NGHỀ NGHIỆP
=========================================================

Luôn điều chỉnh kế hoạch theo công việc.

Ví dụ:

- Nhân viên văn phòng:
ưu tiên giảm thời gian ngồi, đi bộ ngắn, bài tập tại nhà.

- Người làm ca đêm:
chú ý thời điểm ăn, caffeine, ánh sáng và giấc ngủ.

- Lao động nặng:
không cắt giảm năng lượng quá mức, ưu tiên phục hồi và đủ protein.

- Giáo viên hoặc bán hàng:
tính đến thời gian đứng nhiều, lịch ăn thất thường.

- Tài xế:
ưu tiên bài tập chống đau lưng, nghỉ vận động và lựa chọn đồ ăn tiện lợi.

- Sinh viên:
ưu tiên chi phí hợp lý, món dễ chuẩn bị và lịch học.

- Người chăm con nhỏ:
ưu tiên bài tập ngắn, thực đơn đơn giản, mục tiêu linh hoạt.

Không đưa ra kế hoạch chung chung giống nhau cho mọi người.

=========================================================
VIII. THUỐC VÀ THỰC PHẨM BỔ SUNG
=========================================================

- Không kê đơn thuốc kê toa.
- Không đề xuất kháng sinh.
- Không yêu cầu người dùng dừng thuốc bác sĩ đã kê.
- Không đưa liều thuốc khi chưa đủ thông tin về tuổi, cân nặng,
-bệnh nền, dị ứng, thai kỳ và thuốc đang sử dụng.
- Không khẳng định thực phẩm bổ sung có thể chữa bệnh.
- Nếu người dùng hỏi về thuốc, hãy hỏi tên thuốc, hàm lượng,
-mục đích sử dụng và các thuốc khác đang dùng.
- Khuyến nghị hỏi bác sĩ hoặc dược sĩ nếu có nguy cơ tương tác.

=========================================================
IX. PHONG CÁCH TRẢ LỜI
=========================================================

Trong giai đoạn hỏi thông tin:

- Chỉ hỏi đúng 1 câu.
- Không dùng danh sách nhiều câu hỏi.
- Có thể giải thích một câu rất ngắn vì sao cần hỏi.

Ví dụ:

"Để điều chỉnh kế hoạch theo thể trạng, bạn hiện bao nhiêu tuổi?"

Sau khi đủ thông tin, trình bày rõ theo tiêu đề:

- Đánh giá hiện tại
- Mục tiêu đề xuất
- Kế hoạch ăn uống
- Kế hoạch vận động
- Lịch theo dõi
- Dấu hiệu cần lưu ý

Không viết quá dài nếu người dùng không yêu cầu chi tiết.
Ưu tiên nội dung thực tế, có thể áp dụng.
Nguyên tắc:
- Không thay thế bác sĩ và không khẳng định chẩn đoán chắc chắn.
- Không kê thuốc kê đơn, không tự đề xuất kháng sinh.
- Trong giai đoạn thu thập thông tin, mỗi lần chỉ hỏi một câu ngắn.
- Khi người dùng gửi ảnh, chỉ mô tả dấu hiệu quan sát được.
- Không kết luận bệnh chắc chắn chỉ dựa trên ảnh.
- Nếu ảnh mờ, thiếu sáng hoặc không đủ thông tin, phải nói rõ hạn chế.
- Với hình ảnh da, mắt, họng hoặc vết thương, hỏi thêm thời gian xuất hiện,
  mức độ đau, ngứa, sốt, chảy dịch và các dấu hiệu đi kèm nếu cần.
- Khi có dấu hiệu nguy hiểm như khó thở nặng, đau ngực dữ dội,
  bất tỉnh, co giật, yếu liệt đột ngột, chảy máu nhiều hoặc ý định tự hại,
  phải khuyên gọi cấp cứu hoặc đến cơ sở y tế ngay.
- Trả lời rõ ràng, lịch sự, dễ hiểu, không làm người dùng hoảng sợ.
- Chỉ trả lời kết quả cuối cùng.
- Không hiển thị quá trình suy luận.
- Không viết các từ như Refining, Thinking, Analysis hoặc Draft.
- Trả lời đầy đủ bằng tiếng Việt.
- Không sử dụng ký hiệu Markdown như **, *, # hoặc dấu gạch đầu dòng bằng dấu sao.
- Khi cần liệt kê, dùng số thứ tự hoặc dấu • thông thường.
"""
}

DATABASE_PATH = BASE_DIR / "users.db"
MEDICAL_DATABASE_PATH = BASE_DIR / "database" / "medical.db"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


# Bộ nhớ đệm ngắn cho dữ liệu vị trí để tránh gọi API công cộng quá dày.
LOCATION_CACHE = {}
LOCATION_CACHE_TTL_SECONDS = 300
LOCATION_CACHE_LOCK = Lock()
NOMINATIM_LOCK = Lock()
NOMINATIM_LAST_REQUEST_AT = 0.0
APP_CONTACT_EMAIL = os.getenv("APP_CONTACT_EMAIL", "").strip()


def get_database():
    """Tạo kết nối PostgreSQL cho dữ liệu tài khoản và ứng dụng."""
    return get_connection()
def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "Bạn cần đăng nhập để sử dụng chức năng này."
                }), 401

            return redirect(url_for("index"))

        return view_function(*args, **kwargs)

    return wrapped_view

MEDICAL_SEARCH_STOPWORDS = {
    "tôi", "mình", "em", "anh", "chị", "bạn", "bác", "sĩ",
    "là", "bị", "có", "và", "hoặc", "thì", "nên", "phải",
    "làm", "sao", "gì", "như", "thế", "nào", "được", "không",
    "cho", "với", "của", "đang", "đã", "rồi", "một", "những",
}


def normalize_search_text(value):
    """Chuẩn hóa nhẹ văn bản để tìm kiếm câu hỏi y tế."""
    value = str(value or "").strip().lower()
    value = re.sub(r"[^0-9a-zà-ỹđ\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def search_medical_database(user_question, limit=3):
    """
    Tìm các câu hỏi liên quan trong medical.db.

    Đây là tìm kiếm từ khóa có chấm điểm, phù hợp để chạy thử RAG
    với SQLite mà chưa cần FAISS hoặc ChromaDB.
    """
    normalized_question = normalize_search_text(user_question)

    keywords = [
        word for word in normalized_question.split()
        if len(word) >= 2 and word not in MEDICAL_SEARCH_STOPWORDS
    ]

    # Loại từ lặp nhưng vẫn giữ đúng thứ tự.
    keywords = list(dict.fromkeys(keywords))[:10]

    if not keywords or not MEDICAL_DATABASE_PATH.is_file():
        return []

    connection = None

    try:
        connection = sqlite3.connect(MEDICAL_DATABASE_PATH)
        connection.row_factory = sqlite3.Row

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(medical_qa)"
            ).fetchall()
        }

        if not {"question", "answer"}.issubset(columns):
            print("Bảng medical_qa thiếu cột question hoặc answer.")
            return []

        source_select = "source" if "source" in columns else "'' AS source"

        conditions = []
        parameters = []

        for keyword in keywords:
            conditions.append(
                "(LOWER(question) LIKE ? OR LOWER(answer) LIKE ?)"
            )
            pattern = f"%{keyword}%"
            parameters.extend([pattern, pattern])

        sql = f"""
            SELECT question, answer, {source_select}
            FROM medical_qa
            WHERE {" OR ".join(conditions)}
            LIMIT 60
        """

        rows = connection.execute(sql, parameters).fetchall()

        scored_results = []

        for row in rows:
            database_question = normalize_search_text(row["question"])
            database_answer = normalize_search_text(row["answer"])

            question_words = set(database_question.split())
            answer_words = set(database_answer.split())

            score = 0

            for keyword in keywords:
                if keyword in question_words:
                    score += 4
                elif keyword in database_question:
                    score += 2

                if keyword in answer_words:
                    score += 1

            # Ưu tiên mạnh khi câu người dùng gần giống câu hỏi trong database.
            if normalized_question == database_question:
                score += 20
            elif normalized_question in database_question:
                score += 8

            if score > 0:
                scored_results.append({
                    "question": row["question"],
                    "answer": row["answer"],
                    "source": row["source"] or "medical_qa",
                    "score": score,
                })

        scored_results.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return scored_results[:max(1, min(int(limit), 5))]

    except (sqlite3.Error, OSError, ValueError) as error:
        print("Lỗi tìm kiếm medical.db:", error)
        return []

    finally:
        if connection is not None:
            connection.close()


def build_medical_context(user_question, limit=3):
    """Định dạng kết quả tìm kiếm để đưa vào system message."""
    results = search_medical_database(user_question, limit=limit)

    if not results:
        return ""

    sections = []

    for index, item in enumerate(results, start=1):
        sections.append(
            f"Tài liệu {index}:\n"
            f"Câu hỏi tham khảo: {item['question']}\n"
            f"Nội dung tham khảo: {item['answer']}\n"
            f"Nguồn: {item['source']}"
        )

    return "\n\n".join(sections)


def initialize_database():
    connection = get_database()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS health_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                sex TEXT NOT NULL,
                birth_date TEXT,
                age INTEGER,
                height_cm DOUBLE PRECISION NOT NULL,
                activity_level TEXT NOT NULL DEFAULT 'sedentary',
                goal TEXT NOT NULL DEFAULT 'maintain',
                diet_preference TEXT,
                allergies TEXT,
                medical_notes TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_health_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS weight_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                weight_kg DOUBLE PRECISION NOT NULL,
                note TEXT,
                logged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_weight_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS water_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount_ml INTEGER NOT NULL,
                logged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_water_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT,
                time_of_day TEXT NOT NULL,
                days_of_week TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
                medicine_name TEXT,
                dosage_note TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_triggered_date TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_reminder_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS family_members (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                relationship TEXT NOT NULL DEFAULT 'Khác',
                age INTEGER,
                gender TEXT,
                height_cm DOUBLE PRECISION,
                weight_kg DOUBLE PRECISION,
                medical_conditions TEXT,
                allergies TEXT,
                avatar_seed TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_family_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                question TEXT NOT NULL,
                answer TEXT,
                model TEXT,
                has_image INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'success',
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_chat_user
                    FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
        """)

        # Liên kết mỗi lượt chat với đúng hồ sơ đang được tư vấn.
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS profile_type TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS profile_ref TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS profile_name TEXT"
        )

        # Đánh giá câu trả lời AI từ người dùng.
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_rating TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_reason TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_text TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_updated_at TIMESTAMPTZ"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_status TEXT NOT NULL DEFAULT 'pending'"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_admin_note TEXT"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_handled_at TIMESTAMPTZ"
        )
        connection.execute(
            "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS feedback_handled_by INTEGER"
        )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                plan_code TEXT NOT NULL DEFAULT 'free',
                status TEXT NOT NULL DEFAULT 'active',
                starts_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ,
                granted_by INTEGER,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_subscription_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS premium_orders (
                id SERIAL PRIMARY KEY,
                invoice_code TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                duration_days INTEGER NOT NULL DEFAULT 30,
                status TEXT NOT NULL DEFAULT 'pending_payment',
                payment_note TEXT,
                user_note TEXT,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                notification_type TEXT NOT NULL DEFAULT 'info',
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            INSERT INTO user_subscriptions (user_id, plan_code, status)
            SELECT id, CASE WHEN role='admin' THEN 'premium' ELSE 'free' END, 'active'
            FROM users
            ON CONFLICT (user_id) DO NOTHING
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_premium_orders_status_created
            ON premium_orders(status, created_at DESC)
        """)



        connection.execute("""
            CREATE TABLE IF NOT EXISTS health_news_images (
                id SERIAL PRIMARY KEY,
                content BYTEA NOT NULL,
                mime_type TEXT NOT NULL,
                original_name TEXT,
                created_by INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_health_news_image_creator
                    FOREIGN KEY (created_by)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_news_images_created_at
            ON health_news_images(created_at DESC, id DESC)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS health_news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                image_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                is_featured INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER,
                reviewed_by INTEGER,
                rejection_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMPTZ,
                published_at TIMESTAMPTZ,
                CONSTRAINT fk_health_news_creator
                    FOREIGN KEY (created_by)
                    REFERENCES users(id)
                    ON DELETE SET NULL,
                CONSTRAINT fk_health_news_reviewer
                    FOREIGN KEY (reviewed_by)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_news_public
            ON health_news(status, is_featured, published_at DESC, id DESC)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_news_category
            ON health_news(category, status, published_at DESC)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id SERIAL PRIMARY KEY,
                admin_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                details TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_audit_admin
                    FOREIGN KEY (admin_user_id)
                    REFERENCES users(id)
                    ON DELETE RESTRICT,
                CONSTRAINT fk_audit_target
                    FOREIGN KEY (target_user_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_by INTEGER,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id SERIAL PRIMARY KEY,
                prompt_name TEXT NOT NULL DEFAULT 'system',
                content TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_admin_logs_created
            ON admin_audit_logs(created_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_weight_user_date
            ON weight_logs(user_id, logged_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_water_user_date
            ON water_logs(user_id, logged_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminder_user_active
            ON reminders(user_id, is_active)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_family_members_user
            ON family_members(user_id, updated_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_logs_created
            ON chat_logs(created_at)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_logs_user
            ON chat_logs(user_id)
        """)

        connection.commit()
        print("✅ Đã khởi tạo các bảng PostgreSQL.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

initialize_database()


def get_setting(key, default=""):
    connection = get_database()
    row = connection.execute(
        "SELECT setting_value FROM system_settings WHERE setting_key = ?",
        (key,),
    ).fetchone()
    connection.close()
    return row["setting_value"] if row else default


def get_user_entitlement(connection, user_id):
    user = connection.execute("SELECT id, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return {"plan": "free", "is_premium": False, "is_admin": False, "expires_at": None}
    is_admin = user["role"] == "admin"
    row = connection.execute(
        "SELECT * FROM user_subscriptions WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        connection.execute(
            "INSERT INTO user_subscriptions (user_id, plan_code, status) VALUES (?, ?, 'active')",
            (user_id, "premium" if is_admin else "free"),
        )
        row = connection.execute(
            "SELECT * FROM user_subscriptions WHERE user_id = ?", (user_id,)
        ).fetchone()
    expires_at = row["expires_at"] if row else None
    active_paid = bool(row and row["plan_code"] == "premium" and row["status"] == "active" and (expires_at is None or expires_at > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))))
    return {"plan": "premium" if (is_admin or active_paid) else "free", "is_premium": bool(is_admin or active_paid), "is_admin": is_admin, "expires_at": expires_at}


def enforce_daily_ai_limit(connection, user_id, has_image=False):
    entitlement = get_user_entitlement(connection, user_id)
    if entitlement["is_admin"]:
        return entitlement
    chat_limit = PREMIUM_CHAT_DAILY_LIMIT if entitlement["is_premium"] else FREE_CHAT_DAILY_LIMIT
    image_limit = PREMIUM_IMAGE_DAILY_LIMIT if entitlement["is_premium"] else FREE_IMAGE_DAILY_LIMIT
    chats_today = connection.execute(
        "SELECT COUNT(*) FROM chat_logs WHERE user_id=? AND created_at::date=CURRENT_DATE", (user_id,)
    ).fetchone()[0]
    images_today = connection.execute(
        "SELECT COUNT(*) FROM chat_logs WHERE user_id=? AND has_image=1 AND created_at::date=CURRENT_DATE", (user_id,)
    ).fetchone()[0]
    if chats_today >= chat_limit:
        raise PermissionError(f"Bạn đã dùng hết {chat_limit} lượt chat hôm nay. Hạn mức sẽ được làm mới vào ngày mai.")
    if has_image and images_today >= image_limit:
        raise PermissionError(f"Bạn đã dùng hết {image_limit} lượt phân tích ảnh hôm nay.")
    return entitlement



HEALTH_NEWS_CATEGORIES = {
    "general": "Sức khỏe",
    "disease": "Dịch bệnh",
    "community": "Y tế cộng đồng",
    "nutrition": "Dinh dưỡng",
    "mental": "Sức khỏe tinh thần",
}


def normalize_health_news_url(value, field_name="Đường dẫn", allow_empty=False):
    raw = str(value or "").strip()
    if not raw and allow_empty:
        return ""
    if not raw:
        raise ValueError(f"{field_name} không được để trống.")

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"{field_name} phải là URL http/https hợp lệ."
        )
    return raw[:1500]


def normalize_health_news_image_url(value):
    """Cho phép ảnh ngoài http/https hoặc ảnh do MediCare lưu bền vững."""
    raw = str(value or "").strip()
    if not raw:
        return ""

    # Ảnh mới: lưu trong PostgreSQL và phục vụ qua endpoint riêng.
    if raw.startswith("/health-news/image/"):
        return raw[:1500]

    # Giữ tương thích với ảnh local cũ (nếu còn).
    if raw.startswith("/static/uploads/health_news/"):
        return raw[:1500]

    return normalize_health_news_url(
        raw,
        "Ảnh đại diện",
        allow_empty=True,
    )


def detect_health_news_image_extension(content):
    """Xác định loại ảnh bằng chữ ký file thay vì chỉ tin phần mở rộng."""
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if (
        len(content) >= 12
        and content[:4] == b"RIFF"
        and content[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def prepare_health_news_image_upload(file_storage):
    """
    Đọc và xác minh ảnh upload.
    Ảnh KHÔNG còn ghi vào filesystem của web service vì filesystem Render
    có thể bị xóa khi restart/redeploy. Dữ liệu ảnh sẽ được lưu trong PostgreSQL.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("Bạn chưa chọn ảnh từ máy tính.")

    content = file_storage.read()
    if not content:
        raise ValueError("File ảnh đang trống.")

    max_size = 5 * 1024 * 1024
    if len(content) > max_size:
        raise ValueError("Ảnh đại diện không được vượt quá 5 MB.")

    extension = detect_health_news_image_extension(content)
    if extension is None:
        raise ValueError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.")

    mime_by_extension = {
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }

    original_name = Path(
        getattr(file_storage, "filename", "") or f"news-image.{extension}"
    ).name[:255]

    return {
        "content": content,
        "mime_type": mime_by_extension[extension],
        "original_name": original_name,
    }


def extract_health_news_image_id(image_url):
    match = re.fullmatch(
        r"/health-news/image/(\d+)",
        str(image_url or "").strip(),
    )
    return int(match.group(1)) if match else None


def health_news_row_to_dict(row):
    if not row:
        return None

    def dt_text(value):
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return {
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"],
        "category": row["category"],
        "category_label": HEALTH_NEWS_CATEGORIES.get(
            row["category"],
            "Sức khỏe",
        ),
        "source_name": row["source_name"],
        "source_url": row["source_url"],
        "image_url": row["image_url"] or "",
        "status": row["status"],
        "is_featured": bool(row["is_featured"]),
        "created_by": row["created_by"],
        "reviewed_by": row["reviewed_by"],
        "rejection_reason": row["rejection_reason"] or "",
        "created_at": dt_text(row["created_at"]),
        "updated_at": dt_text(row["updated_at"]),
        "reviewed_at": dt_text(row["reviewed_at"]),
        "published_at": dt_text(row["published_at"]),
    }


def parse_health_news_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Dữ liệu bài báo không hợp lệ.")

    title = str(data.get("title", "")).strip()
    summary = str(data.get("summary", "")).strip()
    source_name = str(data.get("source_name", "")).strip()
    category = str(data.get("category", "general")).strip().lower()
    source_url = normalize_health_news_url(
        data.get("source_url"),
        "Link bài báo gốc",
    )
    image_url = normalize_health_news_image_url(
        data.get("image_url")
    )

    if len(title) < 8:
        raise ValueError("Tiêu đề bài báo phải có ít nhất 8 ký tự.")
    if len(summary) < 20:
        raise ValueError("Mô tả ngắn phải có ít nhất 20 ký tự.")
    if not source_name:
        raise ValueError("Bạn chưa nhập tên nguồn báo.")
    if category not in HEALTH_NEWS_CATEGORIES:
        raise ValueError("Danh mục bài báo không hợp lệ.")

    return {
        "title": title[:220],
        "summary": summary[:900],
        "category": category,
        "source_name": source_name[:120],
        "source_url": source_url,
        "image_url": image_url,
    }


def create_notification(connection, user_id, title, message, kind="info"):
    connection.execute(
        "INSERT INTO user_notifications (user_id,title,message,notification_type) VALUES (?,?,?,?)",
        (user_id, str(title)[:150], str(message)[:1000], str(kind)[:30]),
    )


PROFILE_PRIORITY_RULES = """
=========================================================
QUY TẮC ƯU TIÊN TUYỆT ĐỐI VỀ HỒ SƠ
=========================================================

- Hồ sơ sức khỏe được gửi kèm trong yêu cầu là thông tin người dùng
  đã cung cấp và phải được sử dụng trực tiếp.

- Không hỏi lại tuổi, giới tính, chiều cao, cân nặng, bệnh nền,
  dị ứng hoặc mục tiêu nếu trường tương ứng đã có dữ liệu.

- Tuyệt đối không đưa ra danh sách nhiều câu hỏi đánh số.

- Trong một phản hồi chỉ được hỏi tối đa một câu bổ sung.

- Khi người dùng yêu cầu lộ trình tăng cân và hồ sơ đã có tuổi,
  giới tính, chiều cao và cân nặng:
  + Phải xác nhận ngắn gọn rằng đã sử dụng hồ sơ.
  + Phải bắt đầu đưa ra đánh giá hoặc lộ trình ban đầu ngay.
  + Chỉ hỏi thêm một thông tin thiết yếu còn thiếu, ưu tiên
    cân nặng mục tiêu hoặc thời gian mong muốn.

- Không được yêu cầu người dùng nhập lại toàn bộ hồ sơ.

- Chỉ hỏi lại một trường khi trường đó bị thiếu hoặc có dữ liệu
  mâu thuẫn rõ ràng.
"""


def get_active_system_prompt():
    connection = get_database()

    row = connection.execute(
        """
        SELECT content
        FROM prompt_versions
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    connection.close()

    base_content = (
        row["content"]
        if row and row["content"]
        else SYSTEM_PROMPT["content"]
    )

    return {
        "role": "system",
        "content": base_content + "\n\n" + PROFILE_PRIORITY_RULES
    }


def record_chat_log(
    question,
    answer,
    model,
    has_image,
    latency_ms,
    status="success",
    error_message="",
    usage=None,
    profile=None,
):
    """Ghi log và gắn log với đúng hồ sơ đang được tư vấn."""
    try:
        usage = usage or {}
        profile = profile or {}
        connection = get_database()
        cursor = connection.execute(
            """INSERT INTO chat_logs (
                   user_id, question, answer, model, has_image, latency_ms,
                   prompt_tokens, completion_tokens, status, error_message,
                   profile_type, profile_ref, profile_name
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session.get("user_id"),
                str(question)[:4000],
                str(answer or "")[:12000],
                str(model)[:120],
                int(bool(has_image)),
                int(latency_ms or 0),
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
                str(status)[:30],
                str(error_message or "")[:1000],
                str(profile.get("profile_type") or "self")[:30],
                str(profile.get("id") or profile.get("profile_ref") or "self")[:120],
                str(profile.get("name") or "")[:200],
            ),
        )
        connection.commit()
        chat_log_id = cursor.lastrowid
        connection.close()
        return chat_log_id
    except Exception as log_error:
        print("Không thể ghi chat log:", log_error)
        try:
            connection.close()
        except Exception:
            pass
        return None


def clean_history(history):
    if not isinstance(history, list):
        return []

    cleaned = []

    for item in history[-8:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if content:
            cleaned.append({
                "role": role,
                "content": content[:1200]
            })

    return cleaned


def image_to_data_url(image_file):
    mime_type = image_file.mimetype

    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.")

    image_bytes = image_file.read()

    if not image_bytes:
        raise ValueError("File ảnh đang trống.")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Ảnh vượt quá dung lượng tối đa 5 MB.")

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def get_error_status(error):
    status_code = getattr(error, "status_code", None)

    if isinstance(status_code, int):
        return status_code

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)

    return response_status if isinstance(response_status, int) else None


def build_error_response(error):
    status_code = get_error_status(error)
    error_text = str(error).lower()

    print("CHI TIẾT LỖI GEMINI:", repr(error))
    print("STATUS CODE:", status_code)

    if (
            status_code == 429
            or "429" in error_text
            or "quota" in error_text
            or "rate limit" in error_text
            or "resource_exhausted" in error_text
        ):
            return jsonify({
                "error": (
                    "Gemini đã hết lượt sử dụng hoặc vượt giới hạn hiện tại. "
                    "Vui lòng chờ hạn mức được đặt lại."
                )
            }), 429

    if (
        status_code in {401, 403}
        or "401" in error_text
        or "403" in error_text
        or "api key" in error_text
        or "unauthorized" in error_text
        or "permission_denied" in error_text
    ):
        return jsonify({
            "error": (
                "API key không hợp lệ hoặc chưa được cấp quyền truy cập."
            )
        }), 401

    if (
        status_code in {500, 502, 503, 504}
        or "500" in error_text
        or "502" in error_text
        or "503" in error_text
        or "504" in error_text
        or "unavailable" in error_text
        or "high demand" in error_text
        or "overloaded" in error_text
    ):
        return jsonify({
            "error": (
                "Hệ thống Gemini đang quá tải hoặc tạm thời không khả dụng. "
                "Vui lòng đợi một lúc rồi thử lại."
            )
        }), 503

    if (
        status_code == 404
        or "404" in error_text
        or "not_found" in error_text
        or "model not found" in error_text
    ):
        return jsonify({
            "error": (
                "Không tìm thấy model Gemini phù hợp với API key hiện tại. "
                f"Text model: {MODEL_NAME}; vision model: {VISION_MODEL_NAME}. "
                "Hãy dùng API key tạo trực tiếp tại Google AI Studio, kiểm tra thanh toán/quyền truy cập, "
                "hoặc đặt MODEL_NAME=gemini-3.5-flash trong file .env."
            )
        }), 404

    if (
        "timeout" in error_text
        or "timed out" in error_text
    ):
        return jsonify({
            "error": (
                "Gemini phản hồi quá lâu. Vui lòng gửi lại câu hỏi."
            )
        }), 504

    if (
        "connection" in error_text
        or "network" in error_text
    ):
        return jsonify({
            "error": (
                "Không thể kết nối tới máy chủ Gemini. "
                "Hãy kiểm tra mạng Internet rồi thử lại."
            )
        }), 503

    return jsonify({
        "error": (
            "Hệ thống AI đang gặp lỗi tạm thời. "
            "Hãy xem Terminal để biết chi tiết."
        )
    }), 500


def clamp_number(value, field_name, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} không hợp lệ.")

    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{field_name} nằm ngoài phạm vi cho phép.")

    return number


def http_get_json(url, timeout=15, headers=None):
    request_headers = {
        "Accept": "application/json",
        "User-Agent": (
            "MediCareAI/1.0"
            + (f" ({APP_CONTACT_EMAIL})" if APP_CONTACT_EMAIL else "")
        ),
    }
    if headers:
        request_headers.update(headers)

    request_object = Request(url, headers=request_headers)
    with urlopen(request_object, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def reverse_geocode(latitude, longitude):
    global NOMINATIM_LAST_REQUEST_AT

    query = urlencode({
        "lat": f"{latitude:.7f}",
        "lon": f"{longitude:.7f}",
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 18,
        "accept-language": "vi",
    })

    # Public Nominatim yêu cầu tần suất thấp. Khóa này giúp một tiến trình
    # không gửi nhiều request sát nhau và kết quả còn được cache 5 phút.
    with NOMINATIM_LOCK:
        wait_seconds = 1.05 - (time.monotonic() - NOMINATIM_LAST_REQUEST_AT)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        result = http_get_json(
            f"https://nominatim.openstreetmap.org/reverse?{query}",
            timeout=12,
        )
        NOMINATIM_LAST_REQUEST_AT = time.monotonic()

    address = result.get("address") or {}
    short_parts = [
        address.get("suburb") or address.get("quarter") or address.get("neighbourhood"),
        address.get("city_district") or address.get("county"),
        address.get("city") or address.get("town") or address.get("province") or address.get("state"),
    ]
    short_address = ", ".join(dict.fromkeys(part for part in short_parts if part))

    return {
        "display_name": result.get("display_name") or short_address,
        "short_address": short_address or result.get("display_name") or "Vị trí hiện tại",
        "address": address,
    }


def fetch_weather_and_air(latitude, longitude):
    weather_query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "wind_speed_10m,weather_code"
        ),
        "timezone": "auto",
    })
    air_query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
        "timezone": "auto",
    })

    weather = http_get_json(
        f"https://api.open-meteo.com/v1/forecast?{weather_query}",
        timeout=15,
    )
    air = http_get_json(
        f"https://air-quality-api.open-meteo.com/v1/air-quality?{air_query}",
        timeout=15,
    )

    current_weather = weather.get("current") or {}
    current_air = air.get("current") or {}
    return {
        "temperature": current_weather.get("temperature_2m"),
        "apparent_temperature": current_weather.get("apparent_temperature"),
        "humidity": current_weather.get("relative_humidity_2m"),
        "wind_speed": current_weather.get("wind_speed_10m"),
        "weather_code": current_weather.get("weather_code"),
        "aqi": current_air.get("european_aqi"),
        "pm25": current_air.get("pm2_5"),
        "pm10": current_air.get("pm10"),
        "nitrogen_dioxide": current_air.get("nitrogen_dioxide"),
        "ozone": current_air.get("ozone"),
        "weather_time": current_weather.get("time"),
        "air_time": current_air.get("time"),
    }


def fetch_nearby_pharmacies(latitude, longitude, radius_m=5000, limit=6):
    query = (
        f'[out:json][timeout:20];\n'
        f'(\n  nwr(around:{int(radius_m)},{latitude:.7f},{longitude:.7f})'
        '["amenity"="pharmacy"];\n);\nout center tags;'
    )
    body = urlencode({"data": query}).encode("utf-8")
    request_object = Request(
        "https://overpass-api.de/api/interpreter",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": (
                "MediCareAI/1.0"
                + (f" ({APP_CONTACT_EMAIL})" if APP_CONTACT_EMAIL else "")
            ),
        },
        method="POST",
    )

    with urlopen(request_object, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))

    pharmacies = []
    for element in payload.get("elements", []):
        center = element.get("center") or {}
        item_lat = element.get("lat", center.get("lat"))
        item_lon = element.get("lon", center.get("lon"))
        if item_lat is None or item_lon is None:
            continue

        tags = element.get("tags") or {}
        distance = haversine_km(latitude, longitude, float(item_lat), float(item_lon))
        street = " ".join(
            part for part in [tags.get("addr:housenumber"), tags.get("addr:street")]
            if part
        )
        address = street or tags.get("addr:full") or tags.get("addr:place") or "Chưa có địa chỉ chi tiết"
        pharmacies.append({
            "id": f"{element.get('type', 'node')}-{element.get('id')}",
            "name": tags.get("name") or tags.get("brand") or "Nhà thuốc",
            "address": address,
            "latitude": float(item_lat),
            "longitude": float(item_lon),
            "distance_km": round(distance, 2),
            "phone": tags.get("phone") or tags.get("contact:phone") or "",
            "opening_hours": tags.get("opening_hours") or "",
        })

    pharmacies.sort(key=lambda item: item["distance_km"])
    return pharmacies[:max(1, min(int(limit), 10))]


def get_location_context(latitude, longitude, accuracy=None):
    cache_key = f"{round(latitude, 4)}:{round(longitude, 4)}"
    now = time.time()

    with LOCATION_CACHE_LOCK:
        cached = LOCATION_CACHE.get(cache_key)
        if cached and now - cached["cached_at"] < LOCATION_CACHE_TTL_SECONDS:
            result = dict(cached["payload"])
            result["from_cache"] = True
            result["accuracy_m"] = accuracy
            return result

    result = {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": accuracy,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "from_cache": False,
        "location": {},
        "environment": {},
        "pharmacies": [],
        "warnings": [],
    }

    jobs = {
        "location": (reverse_geocode, (latitude, longitude)),
        "environment": (fetch_weather_and_air, (latitude, longitude)),
        "pharmacies": (fetch_nearby_pharmacies, (latitude, longitude)),
    }
    error_labels = {
        "location": "Không lấy được địa chỉ",
        "environment": "Không tải được thời tiết/chất lượng không khí",
        "pharmacies": "Không tải được danh sách nhà thuốc",
    }

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(function, *arguments): key
            for key, (function, arguments) in jobs.items()
        }
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                result[key] = future.result()
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as error:
                result["warnings"].append(f"{error_labels[key]}: {error}")

    if not result["location"]:
        result["location"] = {
            "display_name": f"{latitude:.5f}, {longitude:.5f}",
            "short_address": "Vị trí hiện tại",
            "address": {},
        }

    with LOCATION_CACHE_LOCK:
        LOCATION_CACHE[cache_key] = {"cached_at": now, "payload": dict(result)}
        if len(LOCATION_CACHE) > 100:
            oldest_keys = sorted(
                LOCATION_CACHE,
                key=lambda key: LOCATION_CACHE[key]["cached_at"],
            )[:25]
            for key in oldest_keys:
                LOCATION_CACHE.pop(key, None)

    return result


@app.post("/api/location/context")
def location_context():
    data = request.get_json(silent=True) or {}
    try:
        latitude = clamp_number(data.get("latitude"), "Vĩ độ", -90, 90)
        longitude = clamp_number(data.get("longitude"), "Kinh độ", -180, 180)
        accuracy_value = data.get("accuracy")
        accuracy = None
        if accuracy_value not in (None, ""):
            accuracy = clamp_number(accuracy_value, "Độ chính xác", 0, 100000)
        result = get_location_context(latitude, longitude, accuracy)
        return jsonify(result)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        print("Lỗi location context:", repr(error))
        return jsonify({
            "error": "Không thể tải dữ liệu vị trí lúc này. Vui lòng thử lại."
        }), 503


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/tu-van")
def consultation_page():
    return render_template("chat.html")


@app.get("/suc-khoe-tien-ich")
def health_utilities_page():
    return render_template("health_utilities.html")






@app.get("/health-news/image/<int:image_id>")
def health_news_image(image_id):
    connection = get_database()
    try:
        row = connection.execute(
            """
            SELECT content, mime_type, original_name
            FROM health_news_images
            WHERE id = ?
            """,
            (image_id,),
        ).fetchone()
    finally:
        connection.close()

    if not row:
        return "", 404

    content = bytes(row["content"])
    mime_type = row["mime_type"] or "application/octet-stream"
    original_name = row["original_name"] or f"health-news-{image_id}"

    response = send_file(
        BytesIO(content),
        mimetype=mime_type,
        as_attachment=False,
        download_name=original_name,
        max_age=60 * 60 * 24 * 30,
    )
    response.headers["Cache-Control"] = "public, max-age=2592000"
    return response


@app.get("/api/health-news")
def public_health_news():
    """Trả bản tin đã duyệt theo danh mục, có phân trang để không bỏ mất bài cũ."""
    try:
        limit = max(1, min(int(request.args.get("limit", 12)), 100))
    except (TypeError, ValueError):
        limit = 12

    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    category = str(request.args.get("category", "")).strip().lower()
    conditions = ["status = 'approved'"]
    filter_parameters = []

    if category and category != "all":
        if category not in HEALTH_NEWS_CATEGORIES:
            return jsonify({"error": "Danh mục không hợp lệ."}), 400
        conditions.append("category = ?")
        filter_parameters.append(category)

    where_sql = " AND ".join(conditions)

    connection = get_database()
    try:
        total = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM health_news
            WHERE {where_sql}
            """,
            tuple(filter_parameters),
        ).fetchone()[0]

        rows = connection.execute(
            f"""
            SELECT *
            FROM health_news
            WHERE {where_sql}
            ORDER BY
                is_featured DESC,
                COALESCE(published_at, reviewed_at, created_at) DESC,
                id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(filter_parameters + [limit, offset]),
        ).fetchall()
    finally:
        connection.close()

    return jsonify({
        "items": [health_news_row_to_dict(row) for row in rows],
        "categories": HEALTH_NEWS_CATEGORIES,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    })


@app.get("/ban-tin-suc-khoe")
def health_news_page():
    connection = get_database()
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM health_news
            WHERE status = 'approved'
            ORDER BY
                is_featured DESC,
                COALESCE(published_at, reviewed_at, created_at) DESC,
                id DESC
            """
        ).fetchall()
        items = [health_news_row_to_dict(row) for row in rows]
    finally:
        connection.close()

    return render_template(
        "health_news.html",
        items=items,
        categories=HEALTH_NEWS_CATEGORIES,
    )


@app.get("/kien-thuc")
def knowledge_page():
    return render_template("knowledge.html")


@app.get("/nha-thuoc")
def pharmacy_page():
    return render_template("pharmacies.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "text_model": MODEL_NAME,
        "vision_model": VISION_MODEL_NAME,
    })


@app.post("/register")
def register():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Dữ liệu đăng ký không hợp lệ."}), 400

    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))
    confirm_password = str(data.get("confirm_password", ""))

    if len(full_name) < 2:
        return jsonify({"error": "Vui lòng nhập họ và tên hợp lệ."}), 400

    if not email or "@" not in email or "." not in email:
        return jsonify({"error": "Email không đúng định dạng."}), 400

    if phone:
        phone = phone.replace(" ", "").replace("-", "")
        if not phone.isdigit() or len(phone) < 9 or len(phone) > 11:
            return jsonify({"error": "Số điện thoại không hợp lệ."}), 400

    if len(password) < 8:
        return jsonify({"error": "Mật khẩu phải có ít nhất 8 ký tự."}), 400

    if password != confirm_password:
        return jsonify({"error": "Mật khẩu xác nhận không khớp."}), 400

    connection = get_database()

    try:
        cursor = connection.execute(
            """
            INSERT INTO users (full_name, email, phone, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (
                full_name,
                email,
                phone or None,
                generate_password_hash(password)
            )
        )
        connection.commit()
        user_id = cursor.lastrowid

    except UniqueViolation as error:
        error_text = str(error).lower()

        if "email" in error_text:
            message = "Email này đã được đăng ký."
        elif "phone" in error_text:
            message = "Số điện thoại này đã được đăng ký."
        else:
            message = "Tài khoản đã tồn tại."

        return jsonify({"error": message}), 409

    finally:
        connection.close()

    return jsonify({
        "message": "Đăng ký tài khoản thành công.",
        "user": {
            "id": user_id,
            "full_name": full_name,
            "email": email,
            "phone": phone
        }
    }), 201


@app.post("/login")
def login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Dữ liệu đăng nhập không hợp lệ."}), 400

    account = str(data.get("account", "")).strip().lower()
    password = str(data.get("password", ""))

    if not account or not password:
        return jsonify({
            "error": "Vui lòng nhập đầy đủ tài khoản và mật khẩu."
        }), 400

    connection = get_database()
    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE email = ? OR phone = ?
        """,
        (account, account)
    ).fetchone()
    connection.close()

    if user is None:
        return jsonify({"error": "Tài khoản không tồn tại."}), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Mật khẩu không chính xác."}), 401

    if not bool(user["is_active"]):
        return jsonify({
            "error": "Tài khoản này đã bị quản trị viên tạm khóa."
        }), 403

    session.clear()

    # Ghi nhớ đăng nhập trong 30 ngày.
    session.permanent = True
    session["user_id"] = user["id"]
    session["full_name"] = user["full_name"]
    session["email"] = user["email"]
    session["phone"] = user["phone"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Đăng nhập thành công.",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "phone": user["phone"],
            "role": user["role"]
        }
    })


@app.get("/current-user")
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"logged_in": False})

    # Luôn đọc lại quyền từ CSDL. Nhờ vậy tài khoản vừa được cấp admin
    # có thể vào /admin mà không bị giữ quyền cũ trong cookie phiên.
    connection = get_database()
    user = connection.execute(
        """SELECT u.id, u.full_name, u.email, u.phone, u.role, u.is_active,
                  hp.birth_date
           FROM users u
           LEFT JOIN health_profiles hp ON hp.user_id = u.id
           WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    connection.close()

    if user is None or not bool(user["is_active"]):
        session.clear()
        return jsonify({"logged_in": False})

    session["full_name"] = user["full_name"]
    session["email"] = user["email"]
    session["phone"] = user["phone"]
    session["role"] = user["role"]
    session.permanent = True
    subscription_connection = get_database()
    entitlement = get_user_entitlement(subscription_connection, user_id)
    subscription_connection.commit()
    subscription_connection.close()

    return jsonify({
        "logged_in": True,
        "subscription": {
            "plan": entitlement["plan"],
            "is_premium": entitlement["is_premium"],
            "is_admin": entitlement["is_admin"],
            "expires_at": entitlement["expires_at"].isoformat() if entitlement["expires_at"] else None
        },
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "phone": user["phone"],
            "birth_date": user["birth_date"],
            "role": user["role"]
        }
    })


@app.patch("/api/account/profile")
@login_required
def update_account_profile():
    """Cập nhật thông tin tài khoản cơ bản; email giữ nguyên để tránh đổi định danh ngoài ý muốn."""
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name", "")).strip()
    phone = re.sub(r"\s+", "", str(data.get("phone", "")).strip())
    birth_date = str(data.get("birth_date", "")).strip() or None
    if birth_date:
        try:
            datetime.strptime(birth_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Ngày sinh không hợp lệ."}), 400

    if len(full_name) < 2 or len(full_name) > 120:
        return jsonify({"error": "Họ và tên phải từ 2 đến 120 ký tự."}), 400

    if phone and not re.fullmatch(r"[0-9+().-]{8,20}", phone):
        return jsonify({"error": "Số điện thoại không hợp lệ."}), 400

    connection = get_database()
    try:
        if phone:
            duplicate = connection.execute(
                "SELECT id FROM users WHERE phone = ? AND id <> ?",
                (phone, session["user_id"]),
            ).fetchone()
            if duplicate:
                connection.close()
                return jsonify({"error": "Số điện thoại này đã được tài khoản khác sử dụng."}), 409

        connection.execute(
            "UPDATE users SET full_name = ?, phone = ? WHERE id = ?",
            (full_name, phone or None, session["user_id"]),
        )
        existing_health = connection.execute(
            "SELECT id FROM health_profiles WHERE user_id = ?",
            (session["user_id"],),
        ).fetchone()
        if existing_health:
            connection.execute(
                "UPDATE health_profiles SET birth_date = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (birth_date, session["user_id"]),
            )
        connection.commit()
        user = connection.execute(
            "SELECT id, full_name, email, phone, role FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
        connection.close()

        session["full_name"] = user["full_name"]
        session["phone"] = user["phone"]
        return jsonify({"message": "Đã cập nhật thông tin tài khoản.", "user": dict(user)})
    except Exception as error:
        connection.rollback()
        connection.close()
        return jsonify({"error": f"Không thể cập nhật tài khoản: {error}"}), 500


@app.post("/api/account/change-password")
@login_required
def change_account_password():
    data = request.get_json(silent=True) or {}
    current_password = str(data.get("current_password", ""))
    new_password = str(data.get("new_password", ""))
    confirm_password = str(data.get("confirm_password", ""))

    if not current_password:
        return jsonify({"error": "Vui lòng nhập mật khẩu hiện tại."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Mật khẩu mới phải có ít nhất 8 ký tự."}), 400
    if not re.search(r"[A-Za-zÀ-ỹ]", new_password) or not re.search(r"\d", new_password):
        return jsonify({"error": "Mật khẩu mới phải có cả chữ và số."}), 400
    if new_password != confirm_password:
        return jsonify({"error": "Xác nhận mật khẩu mới không khớp."}), 400
    if current_password == new_password:
        return jsonify({"error": "Mật khẩu mới phải khác mật khẩu hiện tại."}), 400

    connection = get_database()
    user = connection.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if user is None:
        connection.close()
        session.clear()
        return jsonify({"error": "Tài khoản không còn tồn tại."}), 404

    if not check_password_hash(user["password_hash"], current_password):
        connection.close()
        return jsonify({"error": "Mật khẩu hiện tại không chính xác."}), 400

    connection.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), session["user_id"]),
    )
    connection.commit()
    connection.close()
    return jsonify({"message": "Đổi mật khẩu thành công."})



@app.get("/api/account/export")
@login_required
def export_account_data():
    """Xuất dữ liệu cá nhân của tài khoản hiện tại dưới dạng JSON."""
    user_id = session["user_id"]
    connection = get_database()
    user = connection.execute(
        "SELECT id, full_name, email, phone, role, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    profile = connection.execute(
        "SELECT * FROM health_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    chats = connection.execute(
        """SELECT id, question, answer, model, created_at, feedback_rating,
                feedback_reason, feedback_text
        FROM chat_logs WHERE user_id = ? ORDER BY created_at DESC""", (user_id,)
    ).fetchall()
    connection.close()
    payload = {
        "exported_at": datetime.now(VIETNAM_TZ).isoformat(),
        "account": serialize_row(user),
        "health_profile": serialize_row(profile),
        "chat_history": [serialize_row(row) for row in chats],
    }
    response = jsonify(payload)
    response.headers["Content-Disposition"] = "attachment; filename=medicare-du-lieu-ca-nhan.json"
    return response


@app.delete("/api/account/chat-history")
@login_required
def delete_my_chat_history():
    connection = get_database()
    connection.execute("DELETE FROM chat_logs WHERE user_id = ?", (session["user_id"],))
    connection.commit()
    connection.close()
    return jsonify({"message": "Đã xóa toàn bộ lịch sử trò chuyện."})


@app.delete("/api/account")
@login_required
def delete_my_account():
    user_id = session["user_id"]
    connection = get_database()
    try:
        # chat_logs dùng ON DELETE SET NULL, nên xóa trước để dữ liệu hội thoại cá nhân không bị giữ lại.
        connection.execute("DELETE FROM chat_logs WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.commit()
    except Exception as error:
        connection.rollback()
        connection.close()
        return jsonify({"error": f"Không thể xóa tài khoản: {error}"}), 500
    connection.close()
    session.clear()
    return jsonify({"message": "Tài khoản và dữ liệu liên quan đã được xóa."})


@app.post("/api/chat-feedback")
def save_chat_feedback():
    """Lưu đánh giá 👍/👎 cho đúng lượt chat đã ghi trong chat_logs."""
    data = request.get_json(silent=True) or {}
    try:
        chat_log_id = int(data.get("chat_log_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Không xác định được câu trả lời cần đánh giá."}), 400

    rating = str(data.get("rating", "")).strip().lower()
    if rating not in {"like", "dislike", ""}:
        return jsonify({"error": "Đánh giá không hợp lệ."}), 400

    reason = str(data.get("reason", "")).strip()[:120]
    feedback_text = str(data.get("feedback_text", "")).strip()[:1200]

    connection = get_database()
    row = connection.execute(
        "SELECT id, user_id FROM chat_logs WHERE id = ?",
        (chat_log_id,),
    ).fetchone()
    if row is None:
        connection.close()
        return jsonify({"error": "Không tìm thấy lượt chat."}), 404

    # Với lượt chat đã gắn tài khoản, chỉ chính tài khoản đó được cập nhật feedback.
    owner_id = row["user_id"]
    if owner_id is not None and int(owner_id) != int(session.get("user_id") or -1):
        connection.close()
        return jsonify({"error": "Bạn không có quyền đánh giá lượt chat này."}), 403

    connection.execute(
        """UPDATE chat_logs
        SET feedback_rating = ?, feedback_reason = ?, feedback_text = ?,
            feedback_updated_at = CURRENT_TIMESTAMP,
            feedback_status = CASE WHEN ? = '' THEN 'pending' ELSE 'pending' END,
            feedback_admin_note = NULL, feedback_handled_at = NULL, feedback_handled_by = NULL
        WHERE id = ?""",
        (rating or None, reason or None, feedback_text or None, rating, chat_log_id),
    )
    connection.commit()
    connection.close()
    return jsonify({
        "message": "Cảm ơn bạn đã đánh giá câu trả lời.",
        "rating": rating or None,
    })


@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Đăng xuất thành công."})



@app.get("/api/subscription")
@login_required
def subscription_status():
    connection = get_database()
    entitlement = get_user_entitlement(connection, session["user_id"])
    pending = connection.execute(
        "SELECT * FROM premium_orders WHERE user_id=? AND status IN ('pending_payment','awaiting_review') ORDER BY id DESC LIMIT 1",
        (session["user_id"],),
    ).fetchone()
    usage = connection.execute(
        "SELECT COUNT(*) chats, COALESCE(SUM(CASE WHEN has_image=1 THEN 1 ELSE 0 END),0) images FROM chat_logs WHERE user_id=? AND created_at::date=CURRENT_DATE",
        (session["user_id"],),
    ).fetchone()
    notifications = connection.execute(
        "SELECT * FROM user_notifications WHERE user_id=? ORDER BY id DESC LIMIT 10", (session["user_id"],)
    ).fetchall()
    connection.close()
    return jsonify({
        "plan": entitlement["plan"], "is_premium": entitlement["is_premium"], "is_admin": entitlement["is_admin"],
        "expires_at": entitlement["expires_at"].isoformat() if entitlement["expires_at"] else None,
        "limits": {"chat": PREMIUM_CHAT_DAILY_LIMIT if entitlement["is_premium"] else FREE_CHAT_DAILY_LIMIT, "image": PREMIUM_IMAGE_DAILY_LIMIT if entitlement["is_premium"] else FREE_IMAGE_DAILY_LIMIT, "family": None if entitlement["is_premium"] else FREE_FAMILY_PROFILE_LIMIT},
        "usage": {"chat": usage["chats"], "image": usage["images"]},
        "pending_order": dict(pending) if pending else None,
        "bank": {"configured": bool(BANK_NAME and BANK_ACCOUNT_NUMBER and BANK_ACCOUNT_NAME and BANK_BIN), "name": BANK_NAME, "account_number": BANK_ACCOUNT_NUMBER, "account_name": BANK_ACCOUNT_NAME, "bin": BANK_BIN},
        "price": PREMIUM_PRICE, "duration_days": PREMIUM_DURATION_DAYS,
        "notifications": [dict(n) for n in notifications]
    })


@app.post("/api/premium/orders")
@login_required
def create_premium_order():
    connection = get_database()
    entitlement = get_user_entitlement(connection, session["user_id"])
    if entitlement["is_premium"]:
        connection.close(); return jsonify({"error": "Tài khoản đã có quyền Premium."}), 400
    existing = connection.execute(
        "SELECT * FROM premium_orders WHERE user_id=? AND status IN ('pending_payment','awaiting_review') ORDER BY id DESC LIMIT 1",
        (session["user_id"],),
    ).fetchone()
    if existing:
        connection.close(); return jsonify({"order": dict(existing), "reused": True})
    invoice = f"MCP-{datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')):%Y%m%d}-{uuid4().hex[:6].upper()}"
    payment_note = invoice
    cursor = connection.execute(
        "INSERT INTO premium_orders (invoice_code,user_id,amount,duration_days,status,payment_note) VALUES (?,?,?,?,?,?)",
        (invoice, session["user_id"], PREMIUM_PRICE, PREMIUM_DURATION_DAYS, "pending_payment", payment_note),
    )
    connection.commit()
    order = connection.execute("SELECT * FROM premium_orders WHERE id=?", (cursor.lastrowid,)).fetchone()
    connection.close()
    return jsonify({"order": dict(order), "bank": {"configured": bool(BANK_NAME and BANK_ACCOUNT_NUMBER and BANK_ACCOUNT_NAME and BANK_BIN), "name": BANK_NAME, "account_number": BANK_ACCOUNT_NUMBER, "account_name": BANK_ACCOUNT_NAME, "bin": BANK_BIN}}), 201


@app.post("/api/premium/orders/<int:order_id>/submitted")
@login_required
def submit_premium_payment(order_id):
    """Người dùng chỉ được báo đã chuyển khoản khi hệ thống có đủ thông tin ngân hàng."""
    if not (BANK_NAME and BANK_ACCOUNT_NUMBER and BANK_ACCOUNT_NAME and BANK_BIN):
        return jsonify({
            "error": (
                "Admin chưa cập nhật đầy đủ thông tin ngân hàng. "
                "Bạn chưa thể xác nhận chuyển khoản lúc này."
            )
        }), 409

    data = request.get_json(silent=True) or {}
    connection = get_database()
    order = connection.execute(
        "SELECT * FROM premium_orders WHERE id=? AND user_id=?",
        (order_id, session["user_id"]),
    ).fetchone()

    if not order:
        connection.close()
        return jsonify({"error": "Không tìm thấy hóa đơn."}), 404

    if order["status"] == "awaiting_review":
        connection.close()
        return jsonify({
            "ok": True,
            "message": "Hóa đơn này đã được gửi và đang chờ Admin xác nhận."
        })

    if order["status"] != "pending_payment":
        connection.close()
        return jsonify({
            "error": "Hóa đơn không còn ở trạng thái chờ thanh toán."
        }), 400

    connection.execute(
        """
        UPDATE premium_orders
        SET status='awaiting_review',
            user_note=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (str(data.get("note", ""))[:500], order_id),
    )

    admins = connection.execute(
        "SELECT id FROM users WHERE role='admin' AND is_active=1"
    ).fetchall()

    for admin in admins:
        create_notification(
            connection,
            admin["id"],
            "Yêu cầu Premium mới",
            f"Hóa đơn {order['invoice_code']} đang chờ xác nhận thanh toán.",
            "premium_order",
        )

    connection.commit()
    connection.close()
    return jsonify({
        "ok": True,
        "message": "Đã gửi yêu cầu. Admin sẽ kiểm tra giao dịch và xác nhận."
    })


@app.post("/transcribe")
def transcribe_audio():
    """Nhận bản ghi âm và chuyển lời nói tiếng Việt thành văn bản bằng Gemini native API."""
    if not API_KEY:
        return jsonify({
            "error": "Chưa cấu hình GEMINI_API_KEY trong file .env."
        }), 503

    audio_file = request.files.get("audio")
    if audio_file is None or not audio_file.filename:
        return jsonify({"error": "Bạn chưa gửi file âm thanh."}), 400

    extension = Path(audio_file.filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({
            "error": "Định dạng âm thanh không được hỗ trợ. Hãy dùng WEBM, WAV, MP3, M4A, OGG hoặc FLAC."
        }), 400

    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify({"error": "File âm thanh đang trống."}), 400
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({"error": "File âm thanh vượt quá dung lượng tối đa 5 MB."}), 400

    # Gemini hỗ trợ trực tiếp WAV, MP3, AIFF, AAC, OGG và FLAC.
    # Trình duyệt thường ghi WEBM/M4A nên chuyển sang WAV bằng ffmpeg trước khi gửi.
    direct_mime_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mp3",
        ".aiff": "audio/aiff",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }

    converted_path = None
    try:
        if extension in direct_mime_types:
            gemini_audio_bytes = audio_bytes
            gemini_mime_type = direct_mime_types[extension]
        else:
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                return jsonify({
                    "error": (
                        "Máy chủ chưa có FFmpeg nên không đọc được bản ghi WEBM/M4A từ trình duyệt. "
                        "Hãy cài FFmpeg rồi khởi động lại ứng dụng."
                    )
                }), 503

            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as source_file:
                source_file.write(audio_bytes)
                source_path = source_file.name

            converted_path = source_path + ".wav"
            conversion = subprocess.run(
                [
                    ffmpeg_path, "-y", "-i", source_path,
                    "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", converted_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            try:
                os.remove(source_path)
            except OSError:
                pass

            if conversion.returncode != 0 or not os.path.isfile(converted_path):
                detail = conversion.stderr.decode("utf-8", errors="ignore")[-500:]
                print("FFmpeg conversion error:", detail)
                return jsonify({
                    "error": "Không thể xử lý bản ghi âm. Hãy thử nói lại hoặc kiểm tra quyền micro."
                }), 422

            with open(converted_path, "rb") as converted_file:
                gemini_audio_bytes = converted_file.read()
            gemini_mime_type = "audio/wav"

        encoded_audio = base64.b64encode(gemini_audio_bytes).decode("ascii")
        model_name = AUDIO_TRANSCRIPTION_MODEL.removeprefix("models/")
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={API_KEY}"
        )
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Phiên âm chính xác lời nói tiếng Việt trong đoạn âm thanh này. "
                            "Chỉ trả về nội dung đã nghe, không thêm giải thích, tiêu đề hay dấu ngoặc. "
                            "Giữ nguyên tên thuốc, triệu chứng, con số và thuật ngữ y tế. "
                            "Nếu không nghe rõ, chỉ ghi phần nghe rõ; không tự đoán."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": gemini_mime_type,
                            "data": encoded_audio,
                        }
                    },
                ],
            }],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 800,
            },
        }

        request_object = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request_object, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        candidates = result.get("candidates") or []
        parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
        transcript_text = "".join(
            str(part.get("text") or "") for part in parts if isinstance(part, dict)
        ).strip()
        transcript_text = re.sub(r"^```(?:text)?\s*|\s*```$", "", transcript_text, flags=re.I).strip()

        if not transcript_text:
            block_reason = ((result.get("promptFeedback") or {}).get("blockReason") or "")
            print("Gemini transcription empty response:", result)
            return jsonify({
                "error": (
                    "Không nhận dạng được lời nói. Hãy nói gần micro hơn và thử lại."
                    + (f" ({block_reason})" if block_reason else "")
                )
            }), 422

        return jsonify({"text": transcript_text, "model": model_name})

    except HTTPError as error:
        error_body = ""
        try:
            error_body = error.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print("Gemini speech HTTP error:", error.code, error_body)
        if error.code in {401, 403}:
            return jsonify({"error": "Gemini API key không hợp lệ hoặc chưa được cấp quyền."}), 401
        if error.code == 404:
            return jsonify({
                "error": f"Model {AUDIO_TRANSCRIPTION_MODEL} không hỗ trợ hoặc không tồn tại."
            }), 404
        if error.code == 429:
            return jsonify({"error": "Gemini đang vượt giới hạn sử dụng. Hãy thử lại sau."}), 429
        return jsonify({"error": "Gemini không thể xử lý âm thanh lúc này."}), 502
    except (URLError, TimeoutError) as error:
        print("Gemini speech network error:", repr(error))
        return jsonify({"error": "Không thể kết nối Gemini hoặc yêu cầu đã quá thời gian."}), 504
    except Exception as error:
        print("Gemini speech-to-text error:", type(error).__name__, repr(error))
        return jsonify({"error": "Hệ thống nhận dạng giọng nói đang gặp lỗi tạm thời."}), 500
    finally:
        if converted_path:
            try:
                os.remove(converted_path)
            except OSError:
                pass


# =========================
# EMERGENCY FAST PATH
# =========================

EMERGENCY_PATTERNS = {
    "breathing": (
        r"\bkho tho\b",
        r"\bkhong tho duoc\b",
        r"\bnghet tho\b",
        r"\bthieu hoi\b",
        r"\btho gap\b",
        r"\btim moi\b",
        r"\btim tai\b",
    ),
    "chest_pain": (
        r"\bdau nguc du doi\b",
        r"\bdau that nguc\b",
        r"\bdau nguc lan\b",
    ),
    "stroke": (
        r"\bmeo mieng\b",
        r"\bye[u]? liet\b",
        r"\bnoi kho dot ngot\b",
    ),
    "unconscious": (
        r"\bbat tinh\b",
        r"\bkhong danh thuc duoc\b",
        r"\blu lan nghiem trong\b",
    ),
    "seizure": (
        r"\bco giat\b",
    ),
    "severe_bleeding": (
        r"\bchay mau nhieu\b",
        r"\bchay mau khong cam\b",
    ),
    "anaphylaxis": (
        r"\bsung moi\b.*\bkho tho\b",
        r"\bsung luoi\b",
        r"\bsung hong\b.*\bkho tho\b",
    ),
}

EMERGENCY_NEGATIONS = (
    "khong kho tho",
    "khong con kho tho",
    "het kho tho",
    "khong dau nguc",
    "khong bat tinh",
    "khong co giat",
)


def normalize_vietnamese_for_matching(value):
    """Chuẩn hóa chữ thường, bỏ dấu để dò cụm từ cấp cứu ổn định."""
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(
        char for char in value
        if unicodedata.category(char) != "Mn"
    )
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def detect_emergency_message(message):
    """
    Phát hiện nhanh dấu hiệu nguy hiểm.

    Hàm này chạy cục bộ nên phản hồi gần như tức thì, kể cả khi Gemini lỗi,
    quá tải hoặc chưa cấu hình API key.
    """
    normalized = normalize_vietnamese_for_matching(message)

    if not normalized:
        return None

    if any(phrase in normalized for phrase in EMERGENCY_NEGATIONS):
        return None

    for emergency_type, patterns in EMERGENCY_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return {
                "type": emergency_type,
                "title": "DẤU HIỆU CÓ THỂ CẦN CẤP CỨU",
                "phone": "115",
                "phone_uri": "tel:115",
                "severity": "critical",
                "reply": (
                    "Bạn đang mô tả một dấu hiệu có thể nguy hiểm.\n\n"
                    "HÃY GỌI 115 NGAY hoặc nhờ người bên cạnh gọi giúp.\n\n"
                    "- Ngồi hoặc nằm ở tư thế dễ thở, nới lỏng quần áo chật.\n"
                    "- Không tự lái xe đến bệnh viện.\n"
                    "- Nhờ một người ở cạnh và mở cửa để nhân viên cấp cứu dễ tiếp cận.\n"
                    "- Nếu môi tím, đau ngực, lơ mơ, ngất hoặc tình trạng nặng lên, "
                    "hãy báo rõ với tổng đài 115.\n\n"
                    "Đây không phải tình huống nên chờ chatbot tư vấn thêm."
                ),
            }

    return None


def emergency_json_response(emergency, chat_log_id=None):
    """Chuẩn hóa JSON để giao diện có thể hiện thẻ đỏ và nút gọi 115."""
    return jsonify({
        "reply": emergency["reply"],
        "chat_log_id": chat_log_id,
        "emergency": {
            "active": True,
            "type": emergency["type"],
            "title": emergency["title"],
            "severity": emergency["severity"],
            "phone": emergency["phone"],
            "phone_uri": emergency["phone_uri"],
            "primary_action": "Gọi 115 ngay",
            "secondary_action": "Nhờ người bên cạnh hỗ trợ",
        },
        "fast_path": True,
    })

def first_present(mapping, *keys):
    """Lấy giá trị đầu tiên có ý nghĩa từ nhiều tên trường frontend/backend."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", "--", "Chưa cập nhật", "null"):
            return value
    return None


def compact_profile(profile):
    return {
        key: value for key, value in (profile or {}).items()
        if value not in (None, "", "--", "Chưa cập nhật", "null")
    }


def load_self_profile_context(connection, user_id):
    profile = connection.execute(
        "SELECT * FROM health_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if profile is None:
        return {}

    latest_weight = get_latest_weight(connection, user_id)
    try:
        age = calculate_age(profile["birth_date"], profile["age"])
    except (ValueError, TypeError):
        age = profile["age"]

    user = connection.execute(
        "SELECT full_name FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return compact_profile({
        "profile_type": "self",
        "id": "self",
        "name": user["full_name"] if user else session.get("full_name"),
        "relationship": "Bản thân",
        "age": age,
        "gender": profile["sex"],
        "height_cm": profile["height_cm"],
        "weight_kg": latest_weight,
        "activity_level": profile["activity_level"],
        "goal": profile["goal"],
        "diet_preference": profile["diet_preference"],
        "allergies": profile["allergies"],
        "medical_conditions": profile["medical_notes"],
    })


def load_family_profile_context(connection, user_id, member_id):
    try:
        member_id = int(member_id)
    except (TypeError, ValueError):
        return {}
    row = connection.execute(
        "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
        (member_id, user_id),
    ).fetchone()
    if row is None:
        return {}
    return compact_profile({
        "profile_type": "family",
        "id": row["id"],
        "name": row["full_name"],
        "relationship": row["relationship"],
        "age": row["age"],
        "gender": row["gender"],
        "height_cm": row["height_cm"],
        "weight_kg": row["weight_kg"],
        "medical_conditions": row["medical_conditions"],
        "allergies": row["allergies"],
    })


def normalize_profile_reference(selected_profile, user_id=None):
    """Chuẩn hóa ID hồ sơ do frontend gửi lên.

    Hỗ trợ các dạng: self, self-12, user-12, 7, family-7, member-7.
    """
    raw_id = first_present(selected_profile, "id", "profile_id", "member_id")
    selected_type = str(
        first_present(selected_profile, "profile_type", "type") or ""
    ).strip().lower()

    raw_text = str(raw_id or "").strip()
    lowered = raw_text.lower()

    if selected_type == "self" or lowered in {"", "self", "me"}:
        return "self", "self", raw_id

    if lowered.startswith(("self-", "user-")):
        return "self", "self", raw_id

    if user_id is not None and raw_id in (user_id, str(user_id)):
        return "self", "self", raw_id

    family_match = re.fullmatch(r"(?:family|member)[-_:]?(\d+)", lowered)
    if family_match:
        return "family", int(family_match.group(1)), raw_id

    if selected_type in {"family", "member"}:
        try:
            return "family", int(raw_id), raw_id
        except (TypeError, ValueError):
            return "family", None, raw_id

    try:
        return "family", int(raw_id), raw_id
    except (TypeError, ValueError):
        return selected_type or "unknown", None, raw_id


def resolve_effective_profile(selected_profile):
    """Xác minh hồ sơ theo user đang đăng nhập và không trộn dữ liệu hai người."""
    selected_profile = selected_profile if isinstance(selected_profile, dict) else {}

    if "user_id" not in session:
        return compact_profile({
            "profile_type": first_present(selected_profile, "profile_type", "type"),
            "id": first_present(selected_profile, "id", "profile_id"),
            "client_profile_id": first_present(selected_profile, "id", "profile_id"),
            "name": first_present(selected_profile, "name", "full_name"),
            "relationship": first_present(selected_profile, "relationship"),
            "age": first_present(selected_profile, "age"),
            "gender": first_present(selected_profile, "gender", "sex"),
            "height_cm": first_present(selected_profile, "height_cm", "height"),
            "weight_kg": first_present(selected_profile, "weight_kg", "weight"),
            "medical_conditions": first_present(
                selected_profile, "medical_conditions", "condition", "medical_notes"
            ),
            "allergies": first_present(selected_profile, "allergies"),
            "activity_level": first_present(selected_profile, "activity_level"),
            "goal": first_present(selected_profile, "goal"),
            "diet_preference": first_present(selected_profile, "diet_preference"),
        })

    user_id = session["user_id"]
    profile_kind, canonical_id, client_id = normalize_profile_reference(
        selected_profile,
        user_id,
    )

    connection = get_database()
    try:
        if profile_kind == "family" and canonical_id is not None:
            family_profile = load_family_profile_context(
                connection,
                user_id,
                canonical_id,
            )
            if family_profile:
                family_profile["canonical_id"] = family_profile.get("id")
                family_profile["client_profile_id"] = (
                    client_id if client_id not in (None, "") else family_profile.get("id")
                )
                return family_profile

        self_profile = load_self_profile_context(connection, user_id)
        if self_profile:
            self_profile["canonical_id"] = "self"
            self_profile["client_profile_id"] = (
                client_id if client_id not in (None, "") else "self"
            )
        return self_profile
    finally:
        connection.close()


PROFILE_LABELS = {
    "name": "Họ và tên",
    "relationship": "Quan hệ",
    "age": "Tuổi",
    "sex": "Giới tính",
    "gender": "Giới tính",
    "height_cm": "Chiều cao",
    "height": "Chiều cao",
    "latest_weight_kg": "Cân nặng",
    "weight_kg": "Cân nặng",
    "weight": "Cân nặng",
    "activity_level": "Mức vận động",
    "goal": "Mục tiêu",
    "diet_preference": "Chế độ ăn",
    "medical_notes": "Bệnh nền / ghi chú sức khỏe",
    "medical_conditions": "Bệnh nền / ghi chú sức khỏe",
    "condition": "Bệnh nền / ghi chú sức khỏe",
    "allergies": "Dị ứng",
}

PROFILE_VALUE_LABELS = {
    "sedentary": "Ít vận động",
    "light": "Vận động nhẹ",
    "lightly_active": "Vận động nhẹ",
    "moderate": "Vận động vừa",
    "moderately_active": "Vận động vừa",
    "active": "Vận động nhiều",
    "very_active": "Vận động rất nhiều",
    "maintain": "Duy trì cân nặng",
    "gain": "Tăng cân",
    "gain_weight": "Tăng cân",
    "lose": "Giảm cân",
    "lose_weight": "Giảm cân",
    "male": "Nam",
    "female": "Nữ",
}


def format_profile_for_prompt(profile):
    """Định dạng hồ sơ bằng tiếng Việt, không lộ tên trường kỹ thuật hoặc JSON."""
    if not isinstance(profile, dict) or not profile:
        return "Chưa có thông tin hồ sơ."

    ignored_keys = {"id", "profile_id", "member_id", "profile_type", "type"}
    preferred_order = (
        "name", "relationship", "age", "sex", "gender",
        "height_cm", "height", "latest_weight_kg", "weight_kg", "weight",
        "activity_level", "goal", "diet_preference",
        "medical_notes", "medical_conditions", "condition", "allergies",
    )

    lines = []
    used_labels = set()

    for key in preferred_order:
        if key in ignored_keys or key not in profile:
            continue

        value = profile.get(key)
        if value in (None, "", "--", "Chưa cập nhật"):
            continue

        label = PROFILE_LABELS.get(key, key)
        if label in used_labels:
            continue

        display_value = PROFILE_VALUE_LABELS.get(str(value).strip().lower(), value)

        if key == "age":
            display_value = f"{display_value} tuổi"
        elif key in {"height_cm", "height"}:
            display_value = f"{display_value} cm"
        elif key in {"latest_weight_kg", "weight_kg", "weight"}:
            display_value = f"{display_value} kg"

        lines.append(f"- {label}: {display_value}")
        used_labels.add(label)

    return "\n".join(lines) if lines else "Chưa có thông tin hồ sơ."


def is_profile_lookup_request(text):
    """Nhận diện các câu ngắn yêu cầu xem hồ sơ sức khỏe đang chọn."""
    normalized = normalize_vietnamese_for_matching(text)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    exact_phrases = {
        "ho so cua toi",
        "ho so cua minh",
        "ho so suc khoe cua toi",
        "ho so suc khoe cua minh",
        "xem ho so cua toi",
        "xem ho so cua minh",
        "xem ho so suc khoe",
        "xem ho so suc khoe cua toi",
        "thong tin ho so cua toi",
        "thong tin suc khoe cua toi",
        "ho so dang chon",
        "xem ho so dang chon",
    }

    if normalized in exact_phrases:
        return True

    words = normalized.split()
    return (
        len(words) <= 9
        and "ho so" in normalized
        and any(
            phrase in normalized
            for phrase in ("cua toi", "cua minh", "suc khoe", "dang chon")
        )
    )


def build_profile_lookup_reply(profile):
    """Tạo câu trả lời trực tiếp từ dữ liệu hồ sơ đã được server xác minh."""
    if not profile:
        return (
            "Tôi chưa tìm thấy dữ liệu cho hồ sơ sức khỏe đang chọn. "
            "Bạn hãy đăng nhập hoặc cập nhật hồ sơ trước."
        )

    name = first_present(profile, "name") or "hồ sơ đang chọn"
    details = format_profile_for_prompt(profile)
    return (
        f"Đây là thông tin hiện có trong hồ sơ đang được dùng để tư vấn cho {name}:\n"
        f"{details}\n\n"
        "Tôi sẽ dùng các thông tin này để cá nhân hóa câu trả lời tiếp theo. "
        "Bạn không cần nhập lại những mục đã có."
    )


def is_weight_plan_request(text):
    normalized = normalize_search_text(text)
    return any(phrase in normalized for phrase in (
        "tăng cân", "tang can", "giảm cân", "giam can", "lộ trình cân",
        "lộ trình tăng", "lộ trình giảm", "kế hoạch tăng", "kế hoạch giảm"
    ))


GEMINI_FALLBACK_MODELS = [
    name.strip().removeprefix("models/")
    for name in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.5-flash,gemini-flash-latest"
    ).split(",")
    if name.strip()
]


def gemini_model_candidates(preferred_model):
    """Trả về danh sách model không trùng để tự chuyển khi model cấu hình bị 404."""
    candidates = [str(preferred_model or "").strip().removeprefix("models/")]
    candidates.extend(GEMINI_FALLBACK_MODELS)
    return list(dict.fromkeys(name for name in candidates if name))


def is_model_not_found_error(error):
    status = get_error_status(error)
    text = str(error).lower()
    return (
        status == 404
        or "404" in text
        or "not_found" in text
        or "model not found" in text
        or "is not found" in text
        or "not supported for generatecontent" in text
    )


def create_gemini_completion_with_fallback(**kwargs):
    """Gọi Gemini và tự thử model dự phòng nếu model hiện tại không tồn tại."""
    preferred_model = kwargs.get("model", MODEL_NAME)
    last_error = None

    for model_name in gemini_model_candidates(preferred_model):
        request_kwargs = dict(kwargs)
        request_kwargs["model"] = model_name
        try:
            response = client.chat.completions.create(**request_kwargs)
            if model_name != preferred_model:
                print(
                    f"⚠️ Model {preferred_model} không dùng được; "
                    f"đã tự chuyển sang {model_name}."
                )
            return response
        except Exception as error:
            last_error = error
            if not is_model_not_found_error(error):
                raise
            print(f"Model Gemini không khả dụng: {model_name}: {error}")

    raise last_error or RuntimeError("Không tìm thấy model Gemini khả dụng.")


AI_CONCURRENCY = max(1, int(os.getenv("AI_CONCURRENCY", "8")))
AI_REQUEST_SEMAPHORE = __import__("threading").BoundedSemaphore(AI_CONCURRENCY)


def create_chat_completion_with_retry(**kwargs):
    """Giới hạn tải cục bộ và thử lại lỗi tạm thời/rate-limit có backoff."""
    attempts = max(1, int(os.getenv("AI_RETRY_ATTEMPTS", "3")))
    last_error = None
    acquired = AI_REQUEST_SEMAPHORE.acquire(timeout=10)
    if not acquired:
        raise TimeoutError("Máy chủ đang xử lý quá nhiều yêu cầu cùng lúc")
    try:
        for attempt in range(attempts):
            try:
                return create_gemini_completion_with_fallback(**kwargs)
            except Exception as error:
                last_error = error
                status = get_error_status(error)
                text = str(error).lower()
                retryable = status in {408, 409, 429, 500, 502, 503, 504} or any(
                    token in text for token in (
                        "timeout", "timed out", "rate limit", "overloaded",
                        "connection reset", "temporarily unavailable"
                    )
                )
                if not retryable or attempt >= attempts - 1:
                    raise
                time.sleep(min(6.0, 0.8 * (2 ** attempt)))
        raise last_error
    finally:
        AI_REQUEST_SEMAPHORE.release()


def parse_optional_json_object(value):
    """Đọc object JSON tùy chọn từ form-data hoặc JSON body."""
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@app.post("/chat")
def chat():
    try:
        content_type = request.content_type or ""

        if content_type.startswith("multipart/form-data"):
            user_message = str(
                request.form.get("message", "")
            ).strip()

            history_raw = request.form.get("history", "[]")

            try:
                history_data = json.loads(history_raw)
            except (json.JSONDecodeError, TypeError):
                history_data = []

            history = clean_history(history_data)
            image_file = request.files.get("image")
            selected_profile = parse_optional_json_object(
                request.form.get("selected_profile", "")
            )
            environment_context = parse_optional_json_object(
                request.form.get("environment", "")
            )
            selected_specialty = str(
                request.form.get("specialty", "")
            ).strip()[:100]

        else:
            data = request.get_json(silent=True)

            if not isinstance(data, dict):
                return jsonify({
                    "error": "Dữ liệu gửi lên không hợp lệ."
                }), 400

            user_message = str(
                data.get("message", "")
            ).strip()

            history = clean_history(
                data.get("history", [])
            )
            selected_profile = parse_optional_json_object(
                data.get("selected_profile")
            )
            environment_context = parse_optional_json_object(
                data.get("environment")
            )
            selected_specialty = str(
                data.get("specialty", "")
            ).strip()[:100]

            image_file = None

        has_image = bool(image_file and image_file.filename)

        if "user_id" in session:
            limit_connection = get_database()
            try:
                enforce_daily_ai_limit(limit_connection, session["user_id"], has_image)
                limit_connection.commit()
            except PermissionError as error:
                limit_connection.rollback()
                limit_connection.close()
                return jsonify({"error": str(error), "code": "DAILY_LIMIT_REACHED"}), 429
            limit_connection.close()

        if not user_message and not has_image:
            return jsonify({
                "error": "Bạn chưa nhập câu hỏi hoặc chọn ảnh."
            }), 400

        if len(user_message) > 4000:
            return jsonify({
                "error": "Nội dung quá dài. Vui lòng nhập dưới 4.000 ký tự."
            }), 400

        # Ưu tiên tuyệt đối tình huống cấp cứu: không gọi database, không chờ AI.
        if user_message and not has_image:
            emergency = detect_emergency_message(user_message)
            if emergency:
                chat_log_id = record_chat_log(
                    user_message,
                    emergency["reply"],
                    "local-emergency-detector",
                    False,
                    0,
                    status="emergency",
                )
                return emergency_json_response(emergency, chat_log_id=chat_log_id)

        # Yêu cầu xem hồ sơ được xử lý trực tiếp từ hồ sơ đã được server xác minh.
        # Nhờ vậy câu "hồ sơ của tôi" luôn trả dữ liệu thật thay vì để AI suy diễn.
        if user_message and not has_image and is_profile_lookup_request(user_message):
            effective_profile = resolve_effective_profile(selected_profile or {})
            reply = build_profile_lookup_reply(effective_profile)

            response_profile = dict(effective_profile or {})
            if response_profile:
                response_profile["id"] = response_profile.get(
                    "client_profile_id",
                    response_profile.get("id"),
                )

            chat_log_id = None
            try:
                chat_log_id = record_chat_log(
                    user_message,
                    reply,
                    "local-profile-reader",
                    False,
                    0,
                    status="success",
                    profile=effective_profile,
                )
            except Exception:
                pass

            return jsonify({
                "reply": reply,
                "profile_used": response_profile or None,
                "profile_lookup": True,
                "chat_log_id": chat_log_id,
            })

        if client is None:
            return jsonify({
                "error": (
                    "Chưa cấu hình Gemini API key. "
                    "Hãy kiểm tra file .env trong thư mục Workshop1."
                )
            }), 503

        messages = [get_active_system_prompt()]

        # Hồ sơ của chủ tài khoản lấy từ database.
        account_profile_context = {}

        if "user_id" in session:
            connection = get_database()

            profile = connection.execute(
                "SELECT * FROM health_profiles WHERE user_id = ?",
                (session["user_id"],),
            ).fetchone()

            latest_weight = get_latest_weight(
                connection,
                session["user_id"]
            )

            connection.close()

            if profile:
                account_profile_context = {
                    "age": profile["age"],
                    "sex": profile["sex"],
                    "height_cm": profile["height_cm"],
                    "latest_weight_kg": latest_weight,
                    "activity_level": profile["activity_level"],
                    "goal": profile["goal"],
                    "diet_preference": profile["diet_preference"],
                    "allergies": profile["allergies"],
                    "medical_notes": profile["medical_notes"],
                }

        # Xác minh hồ sơ đang chọn bằng dữ liệu trong database.
        # Không tin hoàn toàn dữ liệu gửi từ trình duyệt và không trộn hồ sơ người khác.
        effective_profile = resolve_effective_profile(selected_profile or {})

        if effective_profile:
            messages.append({
                "role": "system",
                "content": (
                    "HỒ SƠ DUY NHẤT ĐANG ĐƯỢC DÙNG ĐỂ TƯ VẤN:\n"
                    + format_profile_for_prompt(effective_profile)
                    + "\n\nQUY TẮC BẮT BUỘC KHI DÙNG HỒ SƠ:\n"
                    "- Đây là người đang được tư vấn trong lượt hiện tại. Không được dùng "
                    "thông tin của hồ sơ hoặc cuộc trò chuyện thuộc người khác.\n"
                    "- Nếu lịch sử có nội dung mâu thuẫn với hồ sơ hiện tại, ưu tiên hồ sơ "
                    "hiện tại và bỏ qua phần lịch sử mâu thuẫn.\n"
                    "- Mọi trường xuất hiện trong hồ sơ trên đều được xem là "
                    "thông tin người dùng đã cung cấp.\n"
                    "- Hệ thống ĐÃ cung cấp trực tiếp hồ sơ trên cho bạn trong lượt chat này. "
                    "Không được nói rằng bạn không thể truy cập hồ sơ, không thể tự động truy cập "
                    "hồ sơ, hoặc yêu cầu người dùng nhập/cung cấp lại những trường đã có.\n"
                    "- Nếu người dùng nói rằng họ đã có hồ sơ hoặc hỏi bạn có thấy hồ sơ không, "
                    "hãy xác nhận ngắn gọn rằng bạn đang sử dụng hồ sơ đang chọn và có thể nhắc lại "
                    "một vài thông tin hiện có bằng tiếng Việt tự nhiên.\n"
                    "- Không hỏi lại tuổi, giới tính, chiều cao, cân nặng, "
                    "bệnh nền hoặc dị ứng nếu trường đó đã có giá trị.\n"
                    "- Khi người dùng yêu cầu lộ trình tăng cân hoặc giảm cân "
                    "và hồ sơ đã có tuổi, giới tính, chiều cao, cân nặng, "
                    "hãy sử dụng trực tiếp các thông tin đó để đánh giá "
                    "ban đầu và trả lời.\n"
                    "- Chỉ hỏi thêm một câu ngắn về thông tin thiết yếu còn "
                    "thiếu, ví dụ cân nặng mục tiêu, thời gian mong muốn, "
                    "khẩu vị hoặc mức vận động.\n"
                    "- Không yêu cầu người dùng nhập lại toàn bộ hồ sơ.\n"
                    "- Nếu người dùng hỏi về chính thông tin có trong hồ sơ trên, phải trả lời trực tiếp từ hồ sơ.\n"
                    "- Tuyệt đối không viện lý do bảo mật hoặc quyền riêng tư để từ chối sử dụng hồ sơ đã được hệ thống cung cấp.\n"
                    "- Chỉ được nói 'chưa có thông tin' khi trường đó thực sự không xuất hiện trong hồ sơ trên.\n"
                    "- Nếu dữ liệu có mâu thuẫn, chỉ hỏi xác nhận đúng trường "
                    "đang bị mâu thuẫn.\n"
                    "- Dữ liệu do người dùng tự khai, không coi là chẩn đoán.\n"
                    "- Không hiển thị JSON hoặc các tên trường kỹ thuật như age, sex, "
                    "name, height_cm, latest_weight_kg trong câu trả lời.\n"
                    "- Khi cần nhắc lại hồ sơ, chỉ viết bằng tiếng Việt tự nhiên, ví dụ: "
                    "18 tuổi, Nam, cao 180 cm, nặng 75 kg."
                ),
            })

        if selected_specialty:
            messages.append({
                "role": "system",
                "content": (
                    f"CHUYÊN KHOA NGƯỜI DÙNG ĐÃ CHỌN: {selected_specialty}. "
                    "Dùng làm ngữ cảnh định hướng, không khẳng định chẩn đoán."
                ),
            })

        if environment_context:
            allowed_environment_fields = {
                key: environment_context.get(key)
                for key in (
                    "short_address", "temperature", "apparent_temperature",
                    "humidity", "wind_speed", "weather_code", "aqi",
                    "pm25", "pm10", "accuracy_m", "updated_at"
                )
                if environment_context.get(key) not in (None, "")
            }
            if allowed_environment_fields:
                messages.append({
                    "role": "system",
                    "content": (
                        "BỐI CẢNH THỜI TIẾT VÀ KHÔNG KHÍ TẠI VỊ TRÍ NGƯỜI DÙNG:\n"
                        + json.dumps(allowed_environment_fields, ensure_ascii=False)
                        + "\nDữ liệu thay đổi theo thời gian, chỉ dùng cho khuyến nghị "
                        "phòng ngừa tổng quát."
                    ),
                })

        # Chỉ truy xuất kho kiến thức cho câu hỏi văn bản.
        # Không dùng database để suy đoán nội dung của ảnh.
        if user_message and not has_image:
            medical_context = build_medical_context(
                user_message,
                limit=2
            )

            if medical_context:
                messages.append({
                    "role": "system",
                    "content": (
                        "DỮ LIỆU THAM KHẢO TRUY XUẤT TỪ KHO Y TẾ:\n"
                        f"{medical_context}\n\n"
                        "Quy tắc sử dụng:\n"
                        "- Chỉ dùng khi thực sự liên quan đến câu hỏi hiện tại.\n"
                        "- Không sao chép máy móc và không coi đây là chẩn đoán.\n"
                        "- Nếu dữ liệu mâu thuẫn hoặc không đủ, ưu tiên trả lời "
                        "thận trọng và khuyên người dùng đi khám khi cần.\n"
                        "- Không nói với người dùng về điểm tìm kiếm nội bộ."
                    ),
                })

                print(
                    "Đã tìm thấy dữ liệu y tế tham khảo cho:",
                    user_message[:100]
                )
            else:
                print(
                    "Không tìm thấy dữ liệu y tế phù hợp cho:",
                    user_message[:100]
                )

        messages.extend(history)

        # Với yêu cầu tăng/giảm cân, nhắc lại hồ sơ ngay trước câu hỏi hiện tại
        # để mô hình không hỏi lại tuổi, chiều cao và cân nặng đã có.
        normalized_intent = unicodedata.normalize(
            "NFD",
            user_message.casefold()
        )
        normalized_intent = "".join(
            character
            for character in normalized_intent
            if unicodedata.category(character) != "Mn"
        )

        weight_plan_type = ""
        if any(keyword in normalized_intent for keyword in (
            "tang can", "len can", "lo trinh tang", "ke hoach tang"
        )):
            weight_plan_type = "tăng cân"
        elif any(keyword in normalized_intent for keyword in (
            "giam can", "xuong can", "lo trinh giam", "ke hoach giam"
        )):
            weight_plan_type = "giảm cân"

        if weight_plan_type and effective_profile:
            messages.append({
                "role": "system",
                "content": (
                    f"YÊU CẦU HIỆN TẠI LÀ LẬP LỘ TRÌNH {weight_plan_type.upper()}.\n"
                    "Hồ sơ đã biết và phải dùng trực tiếp:\n"
                    + format_profile_for_prompt(effective_profile)
                    + "\n- Không hỏi lại bất kỳ trường nào đã có trong hồ sơ.\n"
                    "- Không đưa danh sách nhiều câu hỏi khảo sát.\n"
                    "- Hãy bắt đầu đánh giá và đưa lộ trình sơ bộ ngay.\n"
                    "- Cuối câu trả lời chỉ được hỏi tối đa một thông tin "
                    "thiết yếu còn thiếu, ưu tiên cân nặng mục tiêu hoặc "
                    "thời gian mong muốn.\n"
                    "- Không sao chép nguyên khối hồ sơ vào câu trả lời và không hiển thị "
                    "các tên trường kỹ thuật bằng tiếng Anh."
                ),
            })

        if has_image:
            data_url = image_to_data_url(image_file)

            prompt_text = user_message or (
                "Hãy tự nhận diện loại ảnh và phân tích nội dung quan trọng. "
                "Nếu là món ăn, hãy ước lượng calo, dinh dưỡng và các nguy cơ; "
                "nếu là thuốc hoặc hình ảnh sức khỏe, hãy phân tích theo quy tắc an toàn."
            )

            prompt_text += """

Yêu cầu bổ sung:
- Hãy ưu tiên trả lời đúng câu hỏi của người dùng.
- Nếu là món ăn, phải đưa calo theo một khoảng ước tính, không ghi chính xác tuyệt đối.
- Phân biệt nguy cơ nhìn thấy được với nguy cơ không thể xác định chỉ từ ảnh.
- Nếu không chắc loại ảnh hoặc món ăn, hãy nói rõ mức độ chắc chắn.
"""

            messages.insert(0, {
                "role": "system",
                "content": IMAGE_ANALYSIS_PROMPT
            })

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    }
                ]
            })

        else:
            messages.append({
                "role": "user",
                "content": user_message
            })

        start_time = time.perf_counter()

        selected_model = (
            VISION_MODEL_NAME
            if has_image
            else MODEL_NAME
        )

        max_output_tokens = 3200 if has_image else 2400

        response = create_chat_completion_with_retry(
            model=selected_model,
            messages=messages,
            temperature=0.2 if has_image else 0.3,
            max_completion_tokens=max_output_tokens,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000)
        print(
            f"Thời gian Gemini phản hồi bằng {selected_model}: "
            f"{elapsed_ms / 1000:.2f} giây"
        )
        if not response.choices:
            return jsonify({
                "error": "AI không trả về nội dung."
            }), 502

        reply = response.choices[0].message.content or ""

        finish_reason = getattr(
            response.choices[0],
            "finish_reason",
            None
        )

        print("LÝ DO GEMINI DỪNG:", finish_reason)

        reply = re.sub(
            r"<think>.*?</think>\s*",
            "",
            reply,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()
        
        # Xóa các tiêu đề phân tích không cần thiết
        reply = re.sub(
            r"(?im)^\s*[•\-*]?\s*(analysis|reasoning|thought process|text on the box)\s*:?\s*$",
            "",
            reply
    ).strip()

        if not reply:
            return jsonify({
                "error": "AI trả về nội dung trống."
            }), 502

        usage_data = {}
        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None:
            usage_data = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            }
        chat_log_id = record_chat_log(user_message or "[Ảnh được tải lên]", reply, selected_model, has_image, elapsed_ms, usage=usage_data, profile=effective_profile)
        response_profile = dict(effective_profile or {})
        if response_profile:
            # Trả lại đúng ID frontend đã gửi để xác nhận không nhầm hồ sơ.
            # canonical_id vẫn giữ ID chuẩn trong database.
            response_profile["id"] = response_profile.get(
                "client_profile_id",
                response_profile.get("id"),
            )

        return jsonify({
            "reply": reply,
            "profile_used": response_profile or None,
            "chat_log_id": chat_log_id,
        })

    except ValueError as error:
        return jsonify({
            "error": str(error)
        }), 400

    except Exception as error:
        print(
            f"Gemini API error: "
            f"{type(error).__name__}: {error}"
        )
        try:
            record_chat_log(
                locals().get("user_message", "[request lỗi]"), "",
                locals().get("selected_model", MODEL_NAME),
                locals().get("has_image", False),
                round((time.perf_counter() - locals().get("start_time", time.perf_counter())) * 1000),
                status="error", error_message=str(error),
                profile=locals().get("effective_profile") or {},
            )
        except Exception:
            pass
        return build_error_response(error)



# =========================
# HEALTH & WELLNESS MODULES
# =========================

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

GOAL_CALORIE_ADJUSTMENTS = {
    "lose": -350,
    "maintain": 0,
    "gain": 300,
}


def login_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Vui lòng đăng nhập để sử dụng tính năng này."}), 401
        return view_function(*args, **kwargs)

    return wrapped


def normalize_family_member_payload(data, partial=False):
    if not isinstance(data, dict):
        raise ValueError("Dữ liệu thành viên không hợp lệ.")

    result = {}
    if not partial or "full_name" in data:
        full_name = str(data.get("full_name", "")).strip()
        if len(full_name) < 2 or len(full_name) > 120:
            raise ValueError("Họ tên thành viên phải từ 2 đến 120 ký tự.")
        result["full_name"] = full_name

    text_fields = {
        "relationship": 40,
        "gender": 30,
        "medical_conditions": 500,
        "allergies": 500,
        "avatar_seed": 80,
    }
    for field, max_length in text_fields.items():
        if not partial or field in data:
            result[field] = str(data.get(field, "")).strip()[:max_length]

    if not partial or "age" in data:
        value = data.get("age")
        if value in (None, ""):
            result["age"] = None
        else:
            try:
                age = int(value)
            except (TypeError, ValueError):
                raise ValueError("Tuổi không hợp lệ.")
            if age < 0 or age > 120:
                raise ValueError("Tuổi phải từ 0 đến 120.")
            result["age"] = age

    for field, label, minimum, maximum in (
        ("height_cm", "Chiều cao", 30, 250),
        ("weight_kg", "Cân nặng", 1, 350),
    ):
        if not partial or field in data:
            value = data.get(field)
            result[field] = None if value in (None, "") else clamp_number(
                value, label, minimum, maximum
            )

    return result


@app.route("/api/family", methods=["GET", "POST"])
@login_required
def family_collection():
    user_id = session["user_id"]
    connection = get_database()

    if request.method == "GET":
        rows = connection.execute(
            "SELECT * FROM family_members WHERE user_id = ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        connection.close()
        return jsonify({"members": [dict(row) for row in rows]})

    try:
        entitlement = get_user_entitlement(connection, user_id)
        if not entitlement["is_premium"] and not entitlement["is_admin"]:
            current_count = connection.execute(
                "SELECT COUNT(*) FROM family_members WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            if current_count >= FREE_FAMILY_PROFILE_LIMIT:
                connection.close()
                return jsonify({
                    "error": f"Gói Free được tạo tối đa {FREE_FAMILY_PROFILE_LIMIT} hồ sơ sức khỏe.",
                    "code": "PLAN_LIMIT_REACHED"
                }), 403
        payload = normalize_family_member_payload(request.get_json(silent=True) or {})
        cursor = connection.execute(
            """
            INSERT INTO family_members (
                user_id, full_name, relationship, age, gender, height_cm,
                weight_kg, medical_conditions, allergies, avatar_seed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                payload["full_name"],
                payload.get("relationship") or "Khác",
                payload.get("age"),
                payload.get("gender"),
                payload.get("height_cm"),
                payload.get("weight_kg"),
                payload.get("medical_conditions"),
                payload.get("allergies"),
                payload.get("avatar_seed") or uuid4().hex[:12],
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM family_members WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        connection.close()
        return jsonify({"member": dict(row)}), 201
    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400


@app.route("/api/family/<int:member_id>", methods=["PUT", "DELETE"])
@login_required
def family_item(member_id):
    user_id = session["user_id"]
    connection = get_database()
    existing = connection.execute(
        "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
        (member_id, user_id),
    ).fetchone()
    if existing is None:
        connection.close()
        return jsonify({"error": "Không tìm thấy thành viên."}), 404

    if request.method == "DELETE":
        connection.execute(
            "DELETE FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, user_id),
        )
        connection.commit()
        connection.close()
        return jsonify({"message": "Đã xóa thành viên."})

    try:
        changes = normalize_family_member_payload(
            request.get_json(silent=True) or {}, partial=True
        )
        if not changes:
            connection.close()
            return jsonify({"member": dict(existing)})

        assignments = ", ".join(f"{field} = ?" for field in changes)
        values = list(changes.values()) + [member_id, user_id]
        connection.execute(
            f"UPDATE family_members SET {assignments}, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            values,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, user_id),
        ).fetchone()
        connection.close()
        return jsonify({"member": dict(row)})
    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400


def parse_float(value, field_name, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} không hợp lệ.")

    if not math.isfinite(number):
        raise ValueError(f"{field_name} không hợp lệ.")

    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} phải từ {minimum} trở lên.")

    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} không được vượt quá {maximum}.")

    return number


def calculate_age(birth_date_text=None, supplied_age=None):
    if birth_date_text:
        try:
            born = datetime.strptime(birth_date_text, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Ngày sinh phải có định dạng YYYY-MM-DD.")

        today = date.today()
        age = today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )
    else:
        try:
            age = int(supplied_age)
        except (TypeError, ValueError):
            raise ValueError("Vui lòng nhập ngày sinh hoặc tuổi hợp lệ.")

    if age < 18 or age > 100:
        raise ValueError(
            "Bộ tính BMI/BMR/TDEE này hiện chỉ dành cho người từ 18 đến 100 tuổi."
        )

    return age


def bmi_category(bmi):
    if bmi < 18.5:
        return "Thiếu cân"
    if bmi < 25:
        return "Cân nặng khỏe mạnh"
    if bmi < 30:
        return "Thừa cân"
    if bmi < 35:
        return "Béo phì độ I"
    if bmi < 40:
        return "Béo phì độ II"
    return "Béo phì độ III"


def calculate_health_metrics(sex, age, height_cm, weight_kg, activity_level, goal):
    sex = str(sex).strip().lower()
    if sex not in {"male", "female"}:
        raise ValueError("Giới tính sinh học phải là male hoặc female.")

    if activity_level not in ACTIVITY_MULTIPLIERS:
        raise ValueError("Mức vận động không hợp lệ.")

    if goal not in GOAL_CALORIE_ADJUSTMENTS:
        raise ValueError("Mục tiêu không hợp lệ.")

    height_cm = parse_float(height_cm, "Chiều cao", 100, 250)
    weight_kg = parse_float(weight_kg, "Cân nặng", 25, 350)

    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)

    # Mifflin–St Jeor estimate for adults.
    sex_constant = 5 if sex == "male" else -161
    bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + sex_constant
    tdee = bmr * ACTIVITY_MULTIPLIERS[activity_level]
    target_calories = max(1200, tdee + GOAL_CALORIE_ADJUSTMENTS[goal])

    healthy_weight_min = 18.5 * (height_m ** 2)
    healthy_weight_max = 24.9 * (height_m ** 2)

    # This is a tracking target, not a prescription.
    water_target_ml = round(weight_kg * 30)
    water_target_ml = min(max(water_target_ml, 1500), 3500)

    return {
        "bmi": round(bmi, 1),
        "bmi_category": bmi_category(bmi),
        "bmr_kcal": round(bmr),
        "tdee_kcal": round(tdee),
        "suggested_calorie_target_kcal": round(target_calories),
        "healthy_weight_range_kg": {
            "min": round(healthy_weight_min, 1),
            "max": round(healthy_weight_max, 1),
        },
        "water_tracking_target_ml": water_target_ml,
        "disclaimer": (
            "Các con số chỉ là ước tính sàng lọc cho người trưởng thành, "
            "không thay thế đánh giá của bác sĩ hoặc chuyên gia dinh dưỡng."
        ),
    }


def get_latest_weight(connection, user_id):
    row = connection.execute(
        """
        SELECT weight_kg
        FROM weight_logs
        WHERE user_id = ?
        ORDER BY logged_at DESC, id DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    return float(row["weight_kg"]) if row else None


def serialize_row(row):
    return dict(row) if row is not None else None


@app.route("/api/health/profile", methods=["GET", "PUT"])
@login_required
def health_profile():
    user_id = session["user_id"]
    connection = get_database()

    if request.method == "GET":
        profile = connection.execute(
            "SELECT * FROM health_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        latest_weight = get_latest_weight(connection, user_id)
        connection.close()

        return jsonify({
            "profile": serialize_row(profile),
            "latest_weight_kg": latest_weight,
        })

    data = request.get_json(silent=True) or {}

    try:
        sex = str(data.get("sex", "")).strip().lower()
        if sex not in {"male", "female"}:
            raise ValueError("Giới tính sinh học phải là male hoặc female.")

        birth_date = str(data.get("birth_date", "")).strip() or None
        supplied_age = data.get("age")
        age = calculate_age(birth_date, supplied_age)
        height_cm = parse_float(data.get("height_cm"), "Chiều cao", 100, 250)

        activity_level = str(
            data.get("activity_level", "sedentary")
        ).strip().lower()
        if activity_level not in ACTIVITY_MULTIPLIERS:
            raise ValueError("Mức vận động không hợp lệ.")

        goal = str(data.get("goal", "maintain")).strip().lower()
        if goal not in GOAL_CALORIE_ADJUSTMENTS:
            raise ValueError("Mục tiêu không hợp lệ.")

        connection.execute(
            """
            INSERT INTO health_profiles (
                user_id, sex, birth_date, age, height_cm, activity_level,
                goal, diet_preference, allergies, medical_notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                sex = excluded.sex,
                birth_date = excluded.birth_date,
                age = excluded.age,
                height_cm = excluded.height_cm,
                activity_level = excluded.activity_level,
                goal = excluded.goal,
                diet_preference = excluded.diet_preference,
                allergies = excluded.allergies,
                medical_notes = excluded.medical_notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                sex,
                birth_date,
                age,
                height_cm,
                activity_level,
                goal,
                str(data.get("diet_preference", "")).strip()[:300],
                str(data.get("allergies", "")).strip()[:500],
                str(data.get("medical_notes", "")).strip()[:1000],
            ),
        )
        connection.commit()
        connection.close()

        return jsonify({"message": "Đã cập nhật hồ sơ sức khỏe."})

    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400


@app.post("/api/health/calculate")
@login_required
def calculate_health():
    data = request.get_json(silent=True) or {}
    user_id = session["user_id"]
    connection = get_database()

    try:
        profile = connection.execute(
            "SELECT * FROM health_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        sex = data.get("sex") or (profile["sex"] if profile else None)
        birth_date = data.get("birth_date") or (
            profile["birth_date"] if profile else None
        )
        supplied_age = data.get("age")
        if supplied_age is None and profile:
            supplied_age = profile["age"]

        age = calculate_age(birth_date, supplied_age)
        height_cm = data.get("height_cm") or (
            profile["height_cm"] if profile else None
        )
        activity_level = data.get("activity_level") or (
            profile["activity_level"] if profile else "sedentary"
        )
        goal = data.get("goal") or (
            profile["goal"] if profile else "maintain"
        )
        weight_kg = data.get("weight_kg")
        if weight_kg is None:
            weight_kg = get_latest_weight(connection, user_id)

        if weight_kg is None:
            raise ValueError("Vui lòng nhập hoặc ghi lại cân nặng trước.")

        metrics = calculate_health_metrics(
            sex=sex,
            age=age,
            height_cm=height_cm,
            weight_kg=weight_kg,
            activity_level=str(activity_level).strip().lower(),
            goal=str(goal).strip().lower(),
        )
        connection.close()
        return jsonify(metrics)

    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400


@app.route("/api/health/weight", methods=["GET", "POST"])
@login_required
def weight_logs():
    user_id = session["user_id"]
    connection = get_database()

    if request.method == "GET":
        limit = min(max(request.args.get("limit", 30, type=int), 1), 365)
        rows = connection.execute(
            """
            SELECT id, weight_kg, note, logged_at
            FROM weight_logs
            WHERE user_id = ?
            ORDER BY logged_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        connection.close()
        return jsonify({"items": [dict(row) for row in rows]})

    data = request.get_json(silent=True) or {}

    try:
        weight_kg = parse_float(data.get("weight_kg"), "Cân nặng", 25, 350)
        note = str(data.get("note", "")).strip()[:500]
        logged_at = str(data.get("logged_at", "")).strip() or None

        if logged_at:
            try:
                datetime.fromisoformat(logged_at.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Thời gian ghi cân không hợp lệ.")

        cursor = connection.execute(
            """
            INSERT INTO weight_logs (user_id, weight_kg, note, logged_at)
            VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (user_id, weight_kg, note, logged_at),
        )
        connection.commit()
        log_id = cursor.lastrowid
        connection.close()

        return jsonify({
            "message": "Đã ghi lại cân nặng.",
            "id": log_id,
            "weight_kg": weight_kg,
        }), 201

    except ValueError as error:
        connection.close()
        return jsonify({"error": str(error)}), 400


@app.route("/api/health/water", methods=["GET", "POST"])
@login_required
def water_logs():
    user_id = session["user_id"]
    connection = get_database()

    if request.method == "GET":
        day_text = request.args.get("date", date.today().isoformat())
        try:
            datetime.strptime(day_text, "%Y-%m-%d")
        except ValueError:
            connection.close()
            return jsonify({"error": "Ngày phải có định dạng YYYY-MM-DD."}), 400

        rows = connection.execute(
            """
            SELECT id, amount_ml, logged_at
            FROM water_logs
            WHERE user_id = ? AND DATE(logged_at) = ?
            ORDER BY logged_at ASC
            """,
            (user_id, day_text),
        ).fetchall()

        total_ml = sum(int(row["amount_ml"]) for row in rows)
        connection.close()

        return jsonify({
            "date": day_text,
            "total_ml": total_ml,
            "items": [dict(row) for row in rows],
        })

    data = request.get_json(silent=True) or {}

    try:
        amount_ml = int(data.get("amount_ml"))
        if amount_ml < 50 or amount_ml > 2000:
            raise ValueError("Mỗi lần ghi nước phải từ 50 đến 2.000 ml.")

        cursor = connection.execute(
            """
            INSERT INTO water_logs (user_id, amount_ml)
            VALUES (?, ?)
            """,
            (user_id, amount_ml),
        )
        connection.commit()
        log_id = cursor.lastrowid
        connection.close()

        return jsonify({
            "message": "Đã ghi lượng nước.",
            "id": log_id,
            "amount_ml": amount_ml,
        }), 201

    except (TypeError, ValueError):
        connection.close()
        return jsonify({
            "error": "Lượng nước phải là số nguyên từ 50 đến 2.000 ml."
        }), 400


@app.route("/api/reminders", methods=["GET", "POST"])
@login_required
def reminders():
    user_id = session["user_id"]
    connection = get_database()

    if request.method == "GET":
        rows = connection.execute(
            """
            SELECT *
            FROM reminders
            WHERE user_id = ?
            ORDER BY is_active DESC, time_of_day ASC
            """,
            (user_id,),
        ).fetchall()
        connection.close()
        return jsonify({"items": [dict(row) for row in rows]})

    data = request.get_json(silent=True) or {}

    reminder_type = str(data.get("reminder_type", "")).strip().lower()
    if reminder_type not in {"water", "medicine", "weight", "exercise", "meal", "appointment"}:
        connection.close()
        return jsonify({"error": "Loại lời nhắc không hợp lệ."}), 400

    title = str(data.get("title", "")).strip()
    message = str(data.get("message", "")).strip()[:500]
    time_of_day = str(data.get("time_of_day", "")).strip()
    days_of_week = str(
        data.get("days_of_week", "0,1,2,3,4,5,6")
    ).strip()
    medicine_name = str(data.get("medicine_name", "")).strip()[:200]
    dosage_note = str(data.get("dosage_note", "")).strip()[:300]

    if not title or len(title) > 150:
        connection.close()
        return jsonify({"error": "Tiêu đề lời nhắc không hợp lệ."}), 400

    try:
        datetime.strptime(time_of_day, "%H:%M")
    except ValueError:
        connection.close()
        return jsonify({"error": "Giờ nhắc phải có định dạng HH:MM."}), 400

    try:
        days = sorted({int(item) for item in days_of_week.split(",")})
    except ValueError:
        connection.close()
        return jsonify({"error": "Danh sách ngày trong tuần không hợp lệ."}), 400

    if not days or any(day < 0 or day > 6 for day in days):
        connection.close()
        return jsonify({
            "error": "Ngày trong tuần phải nằm trong khoảng 0 đến 6."
        }), 400

    if reminder_type == "medicine" and not medicine_name:
        connection.close()
        return jsonify({
            "error": "Vui lòng nhập tên thuốc do bác sĩ hoặc dược sĩ hướng dẫn."
        }), 400

    cursor = connection.execute(
        """
        INSERT INTO reminders (
            user_id, reminder_type, title, message, time_of_day,
            days_of_week, medicine_name, dosage_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            reminder_type,
            title,
            message,
            time_of_day,
            ",".join(str(day) for day in days),
            medicine_name or None,
            dosage_note or None,
        ),
    )
    connection.commit()
    reminder_id = cursor.lastrowid
    connection.close()

    return jsonify({
        "message": "Đã tạo lời nhắc.",
        "id": reminder_id,
        "safety_note": (
            "Ứng dụng chỉ nhắc theo lịch bạn nhập, không tự thay đổi liều "
            "hoặc hướng dẫn xử trí khi quên liều."
        ),
    }), 201


@app.route("/api/reminders/<int:reminder_id>", methods=["PUT", "DELETE"])
@login_required
def reminder_detail(reminder_id):
    user_id = session["user_id"]
    connection = get_database()

    reminder = connection.execute(
        "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
        (reminder_id, user_id),
    ).fetchone()

    if reminder is None:
        connection.close()
        return jsonify({"error": "Không tìm thấy lời nhắc."}), 404

    if request.method == "DELETE":
        connection.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        )
        connection.commit()
        connection.close()
        return jsonify({"message": "Đã xóa lời nhắc."})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", reminder["title"])).strip()
    message = str(data.get("message", reminder["message"] or "")).strip()[:500]
    time_of_day = str(
        data.get("time_of_day", reminder["time_of_day"])
    ).strip()
    is_active = 1 if bool(data.get("is_active", reminder["is_active"])) else 0

    try:
        datetime.strptime(time_of_day, "%H:%M")
    except ValueError:
        connection.close()
        return jsonify({"error": "Giờ nhắc phải có định dạng HH:MM."}), 400

    connection.execute(
        """
        UPDATE reminders
        SET title = ?, message = ?, time_of_day = ?, is_active = ?
        WHERE id = ? AND user_id = ?
        """,
        (title, message, time_of_day, is_active, reminder_id, user_id),
    )
    connection.commit()
    connection.close()

    return jsonify({"message": "Đã cập nhật lời nhắc."})


@app.get("/api/reminders/due")
@login_required
def due_reminders():
    user_id = session["user_id"]
    # Render thường chạy theo UTC; dùng múi giờ Việt Nam để lịch nhắc không lệch 7 giờ.
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    current_time = now.strftime("%H:%M")
    current_day = str(now.weekday())
    current_date = now.date().isoformat()

    connection = get_database()
    rows = connection.execute(
        """
        SELECT *
        FROM reminders
        WHERE user_id = ?
          AND is_active = 1
          AND time_of_day <= ?
          AND (last_triggered_date IS NULL OR last_triggered_date <> ?)
        """,
        (user_id, current_time, current_date),
    ).fetchall()

    due = []
    for row in rows:
        days = {item.strip() for item in row["days_of_week"].split(",")}
        if current_day not in days:
            continue

        due.append(dict(row))
        connection.execute(
            """
            UPDATE reminders
            SET last_triggered_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (current_date, row["id"], user_id),
        )

    connection.commit()
    connection.close()

    return jsonify({
        "items": due,
        "browser_notification_note": (
            "Frontend nên gọi endpoint này định kỳ và dùng Notification API "
            "để hiển thị lời nhắc khi trang đang mở."
        ),
    })


@app.post("/api/health/recommendations")
@login_required
def health_recommendations():
    if client is None:
        return jsonify({
            "error": "Chưa cấu hình Gemini API key."
        }), 503

    data = request.get_json(silent=True) or {}
    request_type = str(data.get("type", "daily_plan")).strip().lower()

    if request_type not in {
        "nutrition", "meals", "exercise", "daily_plan"
    }:
        return jsonify({"error": "Loại tư vấn không hợp lệ."}), 400

    user_id = session["user_id"]
    connection = get_database()
    profile = connection.execute(
        "SELECT * FROM health_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    latest_weight = get_latest_weight(connection, user_id)
    connection.close()

    if profile is None or latest_weight is None:
        return jsonify({
            "error": (
                "Vui lòng hoàn thiện hồ sơ sức khỏe và ghi cân nặng "
                "trước khi nhận gợi ý."
            )
        }), 400

    try:
        age = calculate_age(profile["birth_date"], profile["age"])
        metrics = calculate_health_metrics(
            profile["sex"],
            age,
            profile["height_cm"],
            latest_weight,
            profile["activity_level"],
            profile["goal"],
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    user_constraints = str(data.get("notes", "")).strip()[:1000]

    prompt = f"""
Hãy tạo gợi ý {request_type} an toàn, thực tế và dễ làm cho người trưởng thành.

Dữ liệu:
- Tuổi: {age}
- Giới tính sinh học: {profile['sex']}
- Chiều cao: {profile['height_cm']} cm
- Cân nặng gần nhất: {latest_weight} kg
- BMI: {metrics['bmi']} ({metrics['bmi_category']})
- BMR ước tính: {metrics['bmr_kcal']} kcal/ngày
- TDEE ước tính: {metrics['tdee_kcal']} kcal/ngày
- Mục tiêu năng lượng tham khảo: {metrics['suggested_calorie_target_kcal']} kcal/ngày
- Mục tiêu: {profile['goal']}
- Chế độ ăn mong muốn: {profile['diet_preference'] or 'không khai báo'}
- Dị ứng: {profile['allergies'] or 'không khai báo'}
- Ghi chú sức khỏe: {profile['medical_notes'] or 'không khai báo'}
- Yêu cầu thêm: {user_constraints or 'không có'}

Yêu cầu bắt buộc: 1
- Không chẩn đoán, không kê thuốc và không thay đổi liều thuốc.
- Không đưa kế hoạch giảm cân cực đoan.
- Không coi BMI, BMR hoặc TDEE là kết luận y khoa.
- Tôn trọng dị ứng và chế độ ăn đã khai báo.
- Với bài tập, đưa mức nhẹ và cách tăng dần; có khởi động và thả lỏng.
- Nếu ghi chú có thai, bệnh thận, bệnh tim, tiểu đường, rối loạn ăn uống,
  chấn thương hoặc bệnh mạn tính, phải khuyên hỏi bác sĩ/chuyên gia trước.
- Gợi ý món ăn bằng thực phẩm phổ biến tại Việt Nam.
- Trả lời ngắn gọn theo các mục rõ ràng.
"""

    try:
        response = create_chat_completion_with_retry(
            model=MODEL_NAME,
            messages=[
                SYSTEM_PROMPT,
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            temperature=0.3,
            max_completion_tokens=1400,
        ) 
        

        if not response.choices:
            return jsonify({
                "error": "AI không trả về nội dung."
            }), 502

        reply = response.choices[0].message.content

        if not isinstance(reply, str) or not reply.strip():
            return jsonify({
                "error": "AI trả về nội dung trống."
            }), 502

        return jsonify({
            "reply": reply.strip(),
            "metrics": metrics,
        })

    except Exception as error:
        print(f"Gemini API error: {type(error).__name__}: {error}")
        return build_error_response(error)



# =========================
# ADMIN MANAGEMENT MODULE - GIAI ĐOẠN 1
# =========================

def admin_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("index", login="1", next=request.path))

        # Không tin quyền cũ trong session; kiểm tra trực tiếp CSDL mỗi lần vào admin.
        connection = get_database()
        user = connection.execute(
            "SELECT role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        connection.close()

        if user is None or not bool(user["is_active"]):
            session.clear()
            return redirect(url_for("index", login="1", next=request.path))

        session["role"] = user["role"]
        session.permanent = True
        if user["role"] != "admin":
            return redirect(url_for("index", admin_error="1"))

        return view_function(*args, **kwargs)
    return wrapped


def write_admin_log(connection, action, target_user_id=None, details=""):
    connection.execute(
        "INSERT INTO admin_audit_logs (admin_user_id, action, target_user_id, details) VALUES (?, ?, ?, ?)",
        (session["user_id"], str(action)[:100], target_user_id, str(details)[:1000]),
    )


def dataset_directory():
    path = BASE_DIR / "data" / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def inspect_dataset(path):
    result = {"rows": 0, "columns": 0, "duplicate_rows": 0, "missing_cells": 0, "error": ""}
    try:
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                result["columns"] = len(rows[0])
                data_rows = rows[1:]
                result["rows"] = len(data_rows)
                result["duplicate_rows"] = len(data_rows) - len({tuple(r) for r in data_rows})
                result["missing_cells"] = sum(1 for r in data_rows for c in r if not str(c).strip())
        else:
            result["error"] = "Chỉ thống kê chi tiết file CSV"
    except Exception as error:
        result["error"] = str(error)
    return result




@app.get("/admin/api/feedback-summary")
@admin_required
def admin_feedback_summary():
    """Số lượng và các đánh giá AI mới nhất đang chờ Admin xử lý."""
    reason_labels = {
        "incorrect": "Không chính xác",
        "irrelevant": "Không đúng câu hỏi",
        "hard_to_understand": "Khó hiểu / quá dài",
        "missing_info": "Thiếu thông tin",
        "unsafe": "Nội dung không an toàn",
        "other": "Khác",
    }
    connection = get_database()
    pending = connection.execute(
        """SELECT COUNT(*)
           FROM chat_logs
           WHERE feedback_rating IS NOT NULL
             AND COALESCE(feedback_status,'pending')='pending'"""
    ).fetchone()[0]
    rows = connection.execute(
        """SELECT c.id, c.question, c.feedback_rating, c.feedback_reason,
                  c.feedback_text, COALESCE(c.feedback_updated_at,c.created_at) updated_at,
                  u.full_name, u.email
           FROM chat_logs c
           LEFT JOIN users u ON u.id=c.user_id
           WHERE c.feedback_rating IS NOT NULL
             AND COALESCE(c.feedback_status,'pending')='pending'
           ORDER BY COALESCE(c.feedback_updated_at,c.created_at) DESC
           LIMIT 6"""
    ).fetchall()
    connection.close()

    items = []
    for row in rows:
        updated_at = row["updated_at"]
        if hasattr(updated_at, "astimezone"):
            try:
                updated_text = updated_at.astimezone(VIETNAM_TZ).strftime("%H:%M %d/%m")
            except Exception:
                updated_text = str(updated_at)
        else:
            updated_text = str(updated_at or "")
        reason = row["feedback_reason"] or ""
        items.append({
            "id": row["id"],
            "rating": row["feedback_rating"],
            "reason": reason,
            "reason_label": reason_labels.get(reason, reason or "Không ghi lý do"),
            "feedback_text": row["feedback_text"] or "",
            "question": row["question"] or "",
            "full_name": row["full_name"] or "",
            "email": row["email"] or "",
            "updated_at": updated_text,
        })

    return jsonify({"pending": int(pending or 0), "items": items})


@app.get("/admin/feedback")
@admin_required
def admin_feedback_page():
    status = str(request.args.get("status", "pending")).strip().lower()
    if status not in {"pending", "resolved", "all"}:
        status = "pending"
    rating = str(request.args.get("rating", "all")).strip().lower()
    if rating not in {"like", "dislike", "all"}:
        rating = "all"

    conditions = ["c.feedback_rating IS NOT NULL"]
    params = []
    if status != "all":
        conditions.append("COALESCE(c.feedback_status, 'pending') = ?")
        params.append(status)
    if rating != "all":
        conditions.append("c.feedback_rating = ?")
        params.append(rating)

    connection = get_database()
    rows = connection.execute(
        f"""SELECT c.id, c.question, c.answer, c.model, c.created_at,
                   c.feedback_rating, c.feedback_reason, c.feedback_text,
                   c.feedback_updated_at, COALESCE(c.feedback_status,'pending') feedback_status,
                   c.feedback_admin_note, c.feedback_handled_at,
                   u.full_name, u.email, a.full_name handled_by_name
            FROM chat_logs c
            LEFT JOIN users u ON u.id = c.user_id
            LEFT JOIN users a ON a.id = c.feedback_handled_by
            WHERE {' AND '.join(conditions)}
            ORDER BY CASE WHEN COALESCE(c.feedback_status,'pending')='pending' THEN 0 ELSE 1 END,
                     COALESCE(c.feedback_updated_at,c.created_at) DESC
            LIMIT 500""",
        tuple(params),
    ).fetchall()
    stats = connection.execute(
        """SELECT
             COUNT(*) FILTER (WHERE feedback_rating IS NOT NULL) total,
             COUNT(*) FILTER (WHERE feedback_rating='like') likes,
             COUNT(*) FILTER (WHERE feedback_rating='dislike') dislikes,
             COUNT(*) FILTER (WHERE feedback_rating IS NOT NULL AND COALESCE(feedback_status,'pending')='pending') pending
           FROM chat_logs"""
    ).fetchone()
    connection.close()
    return render_template("admin/feedback.html", rows=rows, stats=stats, status=status, rating=rating)


@app.post("/admin/feedback/<int:chat_log_id>/resolve")
@admin_required
def admin_feedback_resolve(chat_log_id):
    note = str(request.form.get("admin_note", "")).strip()[:1200]
    next_status = str(request.form.get("status", "resolved")).strip().lower()
    if next_status not in {"pending", "resolved"}:
        next_status = "resolved"
    connection = get_database()
    row = connection.execute("SELECT id FROM chat_logs WHERE id=? AND feedback_rating IS NOT NULL", (chat_log_id,)).fetchone()
    if row is None:
        connection.close()
        return redirect(url_for("admin_feedback_page"))
    if next_status == "resolved":
        connection.execute(
            """UPDATE chat_logs SET feedback_status='resolved', feedback_admin_note=?,
               feedback_handled_at=CURRENT_TIMESTAMP, feedback_handled_by=? WHERE id=?""",
            (note or None, session["user_id"], chat_log_id),
        )
    else:
        connection.execute(
            """UPDATE chat_logs SET feedback_status='pending', feedback_admin_note=?,
               feedback_handled_at=NULL, feedback_handled_by=NULL WHERE id=?""",
            (note or None, chat_log_id),
        )
    connection.commit()
    connection.close()
    return redirect(request.referrer or url_for("admin_feedback_page"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    connection = get_database()
    stats = {
        "users": connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "active_users": connection.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0],
        "admins": connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0],
        "chats": connection.execute("SELECT COUNT(*) FROM chat_logs").fetchone()[0],
        "images": connection.execute("SELECT COUNT(*) FROM chat_logs WHERE has_image = 1").fetchone()[0],
        "errors": connection.execute("SELECT COUNT(*) FROM chat_logs WHERE status != 'success'").fetchone()[0],
        "avg_latency": connection.execute("SELECT COALESCE(ROUND(AVG(latency_ms)),0) FROM chat_logs WHERE latency_ms > 0").fetchone()[0],
        "tokens": connection.execute("SELECT COALESCE(SUM(prompt_tokens + completion_tokens),0) FROM chat_logs").fetchone()[0],
        "success_rate": connection.execute("SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0),1),0) FROM chat_logs").fetchone()[0],
    }
    chart_rows = connection.execute("""
        SELECT
            day::date AS day,
            (
                SELECT COUNT(*)
                FROM chat_logs
                WHERE created_at::date = day::date
            ) AS chats,
            (
                SELECT COUNT(*)
                FROM users
                WHERE created_at::date = day::date
            ) AS users
        FROM generate_series(
            CURRENT_DATE - INTERVAL '6 days',
            CURRENT_DATE,
            INTERVAL '1 day'
        ) AS day
        ORDER BY day
    """).fetchall()
    recent_chats = connection.execute("""
        SELECT c.*, u.full_name FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id
        ORDER BY c.id DESC LIMIT 8
    """).fetchall()
    connection.close()
    return render_template("admin/dashboard.html", stats=stats, chart_rows=chart_rows, recent_chats=recent_chats, api_configured=bool(API_KEY), text_model=get_setting("text_model", MODEL_NAME), vision_model=get_setting("vision_model", VISION_MODEL_NAME))




@app.get("/admin/news")
@admin_required
def admin_health_news_page():
    connection = get_database()
    try:
        admin_user = connection.execute(
            "SELECT id, full_name, email FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
    finally:
        connection.close()

    return render_template(
        "admin/news.html",
        admin_user=admin_user,
        categories=HEALTH_NEWS_CATEGORIES,
    )


@app.get("/admin/api/news")
@admin_required
def admin_health_news_api():
    status = str(request.args.get("status", "all")).strip().lower()
    category = str(request.args.get("category", "all")).strip().lower()

    conditions = ["1 = 1"]
    parameters = []

    if status != "all":
        if status not in {"draft", "pending", "approved", "rejected"}:
            return jsonify({"error": "Trạng thái không hợp lệ."}), 400
        conditions.append("status = ?")
        parameters.append(status)

    if category != "all":
        if category not in HEALTH_NEWS_CATEGORIES:
            return jsonify({"error": "Danh mục không hợp lệ."}), 400
        conditions.append("category = ?")
        parameters.append(category)

    connection = get_database()
    try:
        rows = connection.execute(
            f"""
            SELECT *
            FROM health_news
            WHERE {' AND '.join(conditions)}
            ORDER BY
                CASE status
                    WHEN 'pending' THEN 0
                    WHEN 'approved' THEN 1
                    WHEN 'draft' THEN 2
                    ELSE 3
                END,
                id DESC
            """,
            tuple(parameters),
        ).fetchall()

        counts = {
            "all": connection.execute(
                "SELECT COUNT(*) FROM health_news"
            ).fetchone()[0],
            "pending": connection.execute(
                "SELECT COUNT(*) FROM health_news WHERE status='pending'"
            ).fetchone()[0],
            "approved": connection.execute(
                "SELECT COUNT(*) FROM health_news WHERE status='approved'"
            ).fetchone()[0],
            "draft": connection.execute(
                "SELECT COUNT(*) FROM health_news WHERE status='draft'"
            ).fetchone()[0],
            "rejected": connection.execute(
                "SELECT COUNT(*) FROM health_news WHERE status='rejected'"
            ).fetchone()[0],
        }
    finally:
        connection.close()

    return jsonify({
        "items": [health_news_row_to_dict(row) for row in rows],
        "counts": counts,
        "categories": HEALTH_NEWS_CATEGORIES,
    })




@app.post("/admin/api/news/upload-image")
@admin_required
def admin_upload_health_news_image():
    image = request.files.get("image")

    try:
        image_data = prepare_health_news_image_upload(image)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    connection = get_database()
    try:
        cursor = connection.execute(
            """
            INSERT INTO health_news_images (
                content,
                mime_type,
                original_name,
                created_by
            )
            VALUES (?, ?, ?, ?)
            RETURNING id
            """,
            (
                image_data["content"],
                image_data["mime_type"],
                image_data["original_name"],
                session["user_id"],
            ),
        )
        returned = cursor.fetchone()
        image_id = returned[0] if returned else None

        if image_id is None:
            raise RuntimeError("Không lấy được ID ảnh vừa tải lên.")

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return jsonify({
        "message": "Tải ảnh lên thành công.",
        "image_url": f"/health-news/image/{image_id}",
    }), 201


@app.post("/admin/api/news")
@admin_required
def admin_create_health_news():
    try:
        payload = parse_health_news_payload(
            request.get_json(silent=True) or {}
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    connection = get_database()
    try:
        cursor = connection.execute(
            """
            INSERT INTO health_news (
                title, summary, category, source_name,
                source_url, image_url, status, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                payload["title"],
                payload["summary"],
                payload["category"],
                payload["source_name"],
                payload["source_url"],
                payload["image_url"] or None,
                session["user_id"],
            ),
        )
        news_id = cursor.lastrowid

        write_admin_log(
            connection,
            "health_news_create",
            details=f"Tạo bài bản tin #{news_id}: {payload['title']}",
        )
        connection.commit()

        row = connection.execute(
            "SELECT * FROM health_news WHERE id = ?",
            (news_id,),
        ).fetchone()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return jsonify({
        "message": "Đã tạo bài và chuyển sang trạng thái chờ duyệt.",
        "item": health_news_row_to_dict(row),
    }), 201


@app.put("/admin/api/news/<int:news_id>")
@admin_required
def admin_update_health_news(news_id):
    try:
        payload = parse_health_news_payload(
            request.get_json(silent=True) or {}
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    connection = get_database()
    try:
        existing = connection.execute(
            "SELECT * FROM health_news WHERE id = ?",
            (news_id,),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Không tìm thấy bài báo."}), 404

        old_stored_image_id = extract_health_news_image_id(
            existing["image_url"]
        )
        new_stored_image_id = extract_health_news_image_id(
            payload["image_url"]
        )

        connection.execute(
            """
            UPDATE health_news
            SET title = ?,
                summary = ?,
                category = ?,
                source_name = ?,
                source_url = ?,
                image_url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                payload["title"],
                payload["summary"],
                payload["category"],
                payload["source_name"],
                payload["source_url"],
                payload["image_url"] or None,
                news_id,
            ),
        )

        if (
            old_stored_image_id is not None
            and old_stored_image_id != new_stored_image_id
        ):
            connection.execute(
                "DELETE FROM health_news_images WHERE id = ?",
                (old_stored_image_id,),
            )

        write_admin_log(
            connection,
            "health_news_update",
            details=f"Cập nhật bài bản tin #{news_id}: {payload['title']}",
        )
        connection.commit()

        row = connection.execute(
            "SELECT * FROM health_news WHERE id = ?",
            (news_id,),
        ).fetchone()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return jsonify({
        "message": "Đã cập nhật bài báo.",
        "item": health_news_row_to_dict(row),
    })


@app.post("/admin/api/news/<int:news_id>/<action>")
@admin_required
def admin_health_news_action(news_id, action):
    allowed_actions = {
        "approve",
        "reject",
        "hide",
        "feature",
        "delete",
        "pending",
    }
    if action not in allowed_actions:
        return jsonify({"error": "Thao tác không hợp lệ."}), 400

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()[:500]

    connection = get_database()
    try:
        row = connection.execute(
            "SELECT * FROM health_news WHERE id = ?",
            (news_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Không tìm thấy bài báo."}), 404

        if action == "approve":
            if bool(row["is_featured"]):
                connection.execute(
                    "UPDATE health_news SET is_featured = 0 WHERE id <> ?",
                    (news_id,),
                )
            connection.execute(
                """
                UPDATE health_news
                SET status = 'approved',
                    reviewed_by = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    published_at = COALESCE(published_at, CURRENT_TIMESTAMP),
                    rejection_reason = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (session["user_id"], news_id),
            )

        elif action == "reject":
            connection.execute(
                """
                UPDATE health_news
                SET status = 'rejected',
                    reviewed_by = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    rejection_reason = ?,
                    is_featured = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (session["user_id"], reason or "Không được duyệt", news_id),
            )

        elif action == "hide":
            connection.execute(
                """
                UPDATE health_news
                SET status = 'draft',
                    is_featured = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (news_id,),
            )

        elif action == "pending":
            connection.execute(
                """
                UPDATE health_news
                SET status = 'pending',
                    is_featured = 0,
                    rejection_reason = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (news_id,),
            )

        elif action == "feature":
            if row["status"] != "approved":
                return jsonify({
                    "error": "Chỉ bài đã duyệt mới được đặt làm nổi bật."
                }), 409
            connection.execute(
                "UPDATE health_news SET is_featured = 0 WHERE is_featured = 1"
            )
            connection.execute(
                """
                UPDATE health_news
                SET is_featured = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (news_id,),
            )

        elif action == "delete":
            stored_image_id = extract_health_news_image_id(row["image_url"])

            connection.execute(
                "DELETE FROM health_news WHERE id = ?",
                (news_id,),
            )

            if stored_image_id is not None:
                connection.execute(
                    "DELETE FROM health_news_images WHERE id = ?",
                    (stored_image_id,),
                )

        write_admin_log(
            connection,
            f"health_news_{action}",
            details=f"Thao tác {action} với bài bản tin #{news_id}",
        )
        connection.commit()

        if action == "delete":
            result = None
        else:
            result = connection.execute(
                "SELECT * FROM health_news WHERE id = ?",
                (news_id,),
            ).fetchone()

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return jsonify({
        "message": "Đã cập nhật bản tin.",
        "item": health_news_row_to_dict(result) if result else None,
    })


@app.get("/admin/premium")
@admin_required
def admin_premium_orders():
    connection = get_database()
    rows = connection.execute("""
        SELECT o.*,u.full_name,u.email,u.phone
        FROM premium_orders o JOIN users u ON u.id=o.user_id
        ORDER BY CASE o.status WHEN 'awaiting_review' THEN 0 WHEN 'pending_payment' THEN 1 ELSE 2 END, o.id DESC
        LIMIT 300
    """).fetchall()
    stats = {
        "awaiting": connection.execute("SELECT COUNT(*) FROM premium_orders WHERE status='awaiting_review'").fetchone()[0],
        "active": connection.execute("SELECT COUNT(*) FROM user_subscriptions WHERE plan_code='premium' AND status='active' AND (expires_at IS NULL OR expires_at>CURRENT_TIMESTAMP)").fetchone()[0],
        "revenue": connection.execute("SELECT COALESCE(SUM(amount),0) FROM premium_orders WHERE status='approved' AND reviewed_at::date >= date_trunc('month',CURRENT_DATE)::date").fetchone()[0],
    }
    connection.close()
    return render_template("admin/premium_orders.html", orders=rows, stats=stats)


@app.post("/admin/premium/<int:order_id>/<action>")
@admin_required
def admin_review_premium(order_id, action):
    if action not in {"approve","reject"}: return jsonify({"error":"Thao tác không hợp lệ."}),400
    connection=get_database(); order=connection.execute("SELECT * FROM premium_orders WHERE id=?",(order_id,)).fetchone()
    if not order: connection.close(); return jsonify({"error":"Không tìm thấy hóa đơn."}),404
    if action == "approve" and order["status"] != "awaiting_review":
        connection.close()
        return jsonify({
            "error": "Chỉ được duyệt hóa đơn khi người dùng đã báo chuyển khoản."
        }), 409

    if action=="approve":
        connection.execute("""
            INSERT INTO user_subscriptions (user_id,plan_code,status,starts_at,expires_at,granted_by,updated_at)
            VALUES (?,'premium','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP + (? * INTERVAL '1 day'),?,CURRENT_TIMESTAMP)
            ON CONFLICT (user_id) DO UPDATE SET plan_code='premium',status='active',starts_at=CURRENT_TIMESTAMP,
            expires_at=GREATEST(COALESCE(user_subscriptions.expires_at,CURRENT_TIMESTAMP),CURRENT_TIMESTAMP) + (? * INTERVAL '1 day'),
            granted_by=EXCLUDED.granted_by,updated_at=CURRENT_TIMESTAMP
        """,(order["user_id"],order["duration_days"],session["user_id"],order["duration_days"]))
        connection.execute("UPDATE premium_orders SET status='approved',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(session["user_id"],order_id))
        create_notification(connection,order["user_id"],"Premium đã được kích hoạt",f"Hóa đơn {order['invoice_code']} đã được duyệt. Gói Premium có hiệu lực {order['duration_days']} ngày.","success")
        write_admin_log(connection,"approve_premium",order["user_id"],f"order={order_id}; invoice={order['invoice_code']}")
    else:
        connection.execute("UPDATE premium_orders SET status='rejected',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(session["user_id"],order_id))
        create_notification(connection,order["user_id"],"Yêu cầu Premium chưa được duyệt",f"Hóa đơn {order['invoice_code']} đã bị từ chối. Vui lòng kiểm tra lại thông tin chuyển khoản.","warning")
        write_admin_log(connection,"reject_premium",order["user_id"],f"order={order_id}")
    connection.commit(); connection.close(); return jsonify({"ok":True})


@app.post("/admin/users/<int:user_id>/premium")
@admin_required
def admin_grant_premium(user_id):
    data=request.get_json(silent=True) or {}; days=max(1,min(int(data.get("days",30)),3650)); connection=get_database()
    connection.execute("""
        INSERT INTO user_subscriptions (user_id,plan_code,status,starts_at,expires_at,granted_by,updated_at)
        VALUES (?,'premium','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP + (? * INTERVAL '1 day'),?,CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET plan_code='premium',status='active',starts_at=CURRENT_TIMESTAMP,
        expires_at=GREATEST(COALESCE(user_subscriptions.expires_at,CURRENT_TIMESTAMP),CURRENT_TIMESTAMP) + (? * INTERVAL '1 day'),granted_by=EXCLUDED.granted_by,updated_at=CURRENT_TIMESTAMP
    """,(user_id,days,session["user_id"],days)); create_notification(connection,user_id,"Bạn đã được cấp Premium",f"Quản trị viên đã cấp Premium trong {days} ngày.","success"); write_admin_log(connection,"grant_premium",user_id,f"days={days}"); connection.commit(); connection.close(); return jsonify({"ok":True})


@app.delete("/admin/users/<int:user_id>/premium")
@admin_required
def admin_revoke_premium(user_id):
    connection=get_database(); connection.execute("UPDATE user_subscriptions SET plan_code='free',status='inactive',expires_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE user_id=?",(user_id,)); create_notification(connection,user_id,"Premium đã kết thúc","Quyền Premium của bạn đã được quản trị viên thu hồi.","warning"); write_admin_log(connection,"revoke_premium",user_id); connection.commit(); connection.close(); return jsonify({"ok":True})


@app.get("/admin/users")
@admin_required
def admin_users():
    keyword=request.args.get("q","").strip(); role=request.args.get("role","").strip(); status=request.args.get("status","").strip()
    page=max(request.args.get("page",1,type=int),1); per_page=20; offset=(page-1)*per_page
    where=[]; params=[]
    if keyword:
        where.append("(u.full_name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)"); params += [f"%{keyword}%"]*3
    if role in {"user","admin"}: where.append("u.role = ?"); params.append(role)
    if status in {"0","1"}: where.append("u.is_active = ?"); params.append(int(status))
    clause=("WHERE "+" AND ".join(where)) if where else ""
    connection=get_database()
    total=connection.execute(f"SELECT COUNT(*) FROM users u {clause}",params).fetchone()[0]
    users=connection.execute(f"""
        SELECT u.*, (SELECT COUNT(*) FROM chat_logs c WHERE c.user_id=u.id) chat_count,
        (SELECT MAX(created_at) FROM chat_logs c WHERE c.user_id=u.id) last_activity,
        COALESCE(s.plan_code,'free') plan_code, s.expires_at premium_expires_at
        FROM users u LEFT JOIN user_subscriptions s ON s.user_id=u.id {clause} ORDER BY u.id DESC LIMIT ? OFFSET ?
    """,params+[per_page,offset]).fetchall()
    connection.close()
    return render_template("admin/users.html",users=users,keyword=keyword,role=role,status=status,page=page,total=total,pages=max(1,(total+per_page-1)//per_page))


@app.get("/admin/users/<int:user_id>")
@admin_required
def admin_user_detail(user_id):
    connection=get_database(); user=connection.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    if not user: connection.close(); return "Không tìm thấy người dùng",404
    chats=connection.execute("SELECT * FROM chat_logs WHERE user_id=? ORDER BY id DESC LIMIT 50",(user_id,)).fetchall()
    profile=connection.execute("SELECT * FROM health_profiles WHERE user_id=?",(user_id,)).fetchone(); connection.close()
    return render_template("admin/user_detail.html",user=user,chats=chats,profile=profile)


@app.post("/admin/users/<int:user_id>/toggle-active")
@admin_required
def admin_toggle_user(user_id):
    if user_id==session["user_id"]: return jsonify({"error":"Bạn không thể tự khóa tài khoản đang dùng."}),400
    connection=get_database(); user=connection.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    if not user: connection.close(); return jsonify({"error":"Không tìm thấy người dùng."}),404
    new_status=0 if user["is_active"] else 1; connection.execute("UPDATE users SET is_active=? WHERE id=?",(new_status,user_id))
    write_admin_log(connection,"unlock_user" if new_status else "lock_user",user_id); connection.commit(); connection.close()
    return jsonify({"ok":True,"is_active":bool(new_status)})


@app.post("/admin/users/<int:user_id>/role")
@admin_required
def admin_change_role(user_id):
    data=request.get_json(silent=True) or {}; new_role=str(data.get("role","")).lower()
    if new_role not in {"user","admin"}: return jsonify({"error":"Quyền không hợp lệ."}),400
    if user_id==session["user_id"] and new_role!="admin": return jsonify({"error":"Bạn không thể tự hạ quyền."}),400
    connection=get_database(); connection.execute("UPDATE users SET role=? WHERE id=?",(new_role,user_id)); write_admin_log(connection,"change_role",user_id,new_role); connection.commit(); connection.close()
    return jsonify({"ok":True,"role":new_role})


@app.get("/admin/chats")
@admin_required
def admin_chats():
    q=request.args.get("q","").strip(); model=request.args.get("model","").strip(); page=max(request.args.get("page",1,type=int),1); per_page=25
    where=[]; params=[]
    if q: where.append("(c.question LIKE ? OR c.answer LIKE ? OR u.full_name LIKE ?)"); params += [f"%{q}%"]*3
    if model: where.append("c.model=?"); params.append(model)
    clause=("WHERE "+" AND ".join(where)) if where else ""; connection=get_database()
    total=connection.execute(f"SELECT COUNT(*) FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id {clause}",params).fetchone()[0]
    chats=connection.execute(f"SELECT c.*,u.full_name,u.email FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id {clause} ORDER BY c.id DESC LIMIT ? OFFSET ?",params+[per_page,(page-1)*per_page]).fetchall()
    models=connection.execute("SELECT DISTINCT model FROM chat_logs WHERE model IS NOT NULL ORDER BY model").fetchall(); connection.close()
    return render_template("admin/chats.html",chats=chats,q=q,model=model,models=models,page=page,pages=max(1,(total+per_page-1)//per_page))


@app.post("/admin/chats/<int:chat_id>/delete")
@admin_required
def admin_delete_chat(chat_id):
    connection=get_database(); connection.execute("DELETE FROM chat_logs WHERE id=?",(chat_id,)); write_admin_log(connection,"delete_chat",details=f"chat_id={chat_id}"); connection.commit(); connection.close(); return jsonify({"ok":True})


@app.get("/admin/datasets")
@admin_required
def admin_datasets():
    files=[]
    for path in sorted(dataset_directory().iterdir()):
        if path.is_file(): files.append({"name":path.name,"size":path.stat().st_size,"modified":datetime.fromtimestamp(path.stat().st_mtime),**inspect_dataset(path)})
    return render_template("admin/datasets.html",files=files)


@app.post("/admin/datasets/upload")
@admin_required
def admin_dataset_upload():
    upload=request.files.get("dataset")
    if not upload or not upload.filename: return jsonify({"error":"Chưa chọn file."}),400
    safe_name=re.sub(r"[^A-Za-z0-9._-]","_",Path(upload.filename).name)
    if Path(safe_name).suffix.lower() not in {".csv",".parquet",".json"}: return jsonify({"error":"Chỉ hỗ trợ CSV, Parquet hoặc JSON."}),400
    target=dataset_directory()/safe_name
    if target.exists(): target=dataset_directory()/f"{target.stem}_{uuid4().hex[:6]}{target.suffix}"
    upload.save(target); connection=get_database(); write_admin_log(connection,"upload_dataset",details=target.name); connection.commit(); connection.close()
    return redirect(url_for("admin_datasets"))


@app.post("/admin/datasets/<path:filename>/delete")
@admin_required
def admin_dataset_delete(filename):
    target=(dataset_directory()/Path(filename).name).resolve()
    if target.parent!=dataset_directory().resolve() or not target.exists(): return jsonify({"error":"File không tồn tại."}),404
    backup=BASE_DIR/"data"/"backup"; backup.mkdir(parents=True,exist_ok=True); shutil.copy2(target,backup/f"{datetime.now():%Y%m%d-%H%M%S}_{target.name}"); target.unlink()
    connection=get_database(); write_admin_log(connection,"delete_dataset",details=filename); connection.commit(); connection.close(); return jsonify({"ok":True})


@app.get("/admin/datasets/<path:filename>/download")
@admin_required
def admin_dataset_download(filename):
    target=dataset_directory()/Path(filename).name
    if not target.exists(): return "Không tìm thấy file",404
    return send_file(target,as_attachment=True)


@app.get("/admin/prompt")
@admin_required
def admin_prompt():
    connection=get_database(); versions=connection.execute("SELECT p.*,u.full_name creator FROM prompt_versions p LEFT JOIN users u ON u.id=p.created_by ORDER BY p.id DESC LIMIT 20").fetchall(); active=get_active_system_prompt()["content"]; connection.close()
    return render_template("admin/prompt.html",versions=versions,active_prompt=active)


@app.post("/admin/prompt")
@admin_required
def admin_prompt_save():
    content=request.form.get("content","").strip()
    if len(content)<50: return "Prompt quá ngắn",400
    connection=get_database(); connection.execute("UPDATE prompt_versions SET is_active=0"); connection.execute("INSERT INTO prompt_versions(content,is_active,created_by) VALUES (?,1,?)",(content,session["user_id"])); write_admin_log(connection,"update_prompt",details=f"{len(content)} ký tự"); connection.commit(); connection.close(); return redirect(url_for("admin_prompt"))


@app.post("/admin/prompt/<int:version_id>/activate")
@admin_required
def admin_prompt_activate(version_id):
    connection=get_database(); connection.execute("UPDATE prompt_versions SET is_active=0"); connection.execute("UPDATE prompt_versions SET is_active=1 WHERE id=?",(version_id,)); write_admin_log(connection,"activate_prompt",details=f"version={version_id}"); connection.commit(); connection.close(); return redirect(url_for("admin_prompt"))


@app.get("/admin/ai-settings")
@admin_required
def admin_ai_settings():
    settings={"text_model":get_setting("text_model",MODEL_NAME),"vision_model":get_setting("vision_model",VISION_MODEL_NAME),"temperature":get_setting("temperature","0.3"),"max_tokens":get_setting("max_tokens","1000"),"ai_concurrency":get_setting("ai_concurrency",os.getenv("AI_CONCURRENCY","8")),"retry_attempts":get_setting("retry_attempts",os.getenv("AI_RETRY_ATTEMPTS","3")),"fallback_models":get_setting("fallback_models",os.getenv("GEMINI_FALLBACK_MODELS",MODEL_NAME)),"provider":"Gemini","api_configured":bool(API_KEY),"api_masked":("••••" + API_KEY[-4:]) if API_KEY else "Chưa cấu hình"}
    return render_template("admin/ai_settings.html",settings=settings)


@app.post("/admin/ai-settings")
@admin_required
def admin_ai_settings_save():
    allowed={"text_model","vision_model","temperature","max_tokens","ai_concurrency","retry_attempts","fallback_models"}; connection=get_database()
    for key in allowed:
        value=request.form.get(key,"").strip()
        connection.execute("INSERT INTO system_settings(setting_key,setting_value,updated_by,updated_at) VALUES (?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP",(key,value,session["user_id"]))
    write_admin_log(connection,"update_ai_settings",details="Cần khởi động lại để áp dụng model"); connection.commit(); connection.close(); return redirect(url_for("admin_ai_settings"))


@app.post("/admin/api/ai/test")
@admin_required
def admin_test_gemini():
    if not client or not API_KEY:
        return jsonify({"error": "Chưa cấu hình GEMINI_API_KEY."}), 400

    model_name = get_setting("text_model", MODEL_NAME).strip() or MODEL_NAME
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Trả lời đúng một từ: OK"},
                {"role": "user", "content": "Kiểm tra kết nối"},
            ],
            max_completion_tokens=20,
            temperature=0,
        )
        reply = (response.choices[0].message.content or "OK").strip()
        latency_ms = round((time.perf_counter() - started) * 1000)
        connection = get_database()
        write_admin_log(connection, "test_gemini", details=f"model={model_name}; latency={latency_ms}ms")
        connection.commit()
        connection.close()
        return jsonify({"ok": True, "model": model_name, "reply": reply[:100], "latency_ms": latency_ms})
    except Exception as error:
        return jsonify({"error": f"{type(error).__name__}: {str(error)[:300]}"}), 502


@app.get("/admin/audit-logs")
@admin_required
def admin_audit_logs():
    connection=get_database(); logs=connection.execute("SELECT l.*,a.full_name admin_name,u.full_name target_name FROM admin_audit_logs l JOIN users a ON a.id=l.admin_user_id LEFT JOIN users u ON u.id=l.target_user_id ORDER BY l.id DESC LIMIT 500").fetchall(); connection.close(); return render_template("admin/audit_logs.html",logs=logs)


@app.get("/admin/backup/users-db")
@admin_required
def admin_backup_users_db():
    return jsonify({
        "error": (
            "Dữ liệu hiện được lưu trên PostgreSQL. "
            "File users.db không còn là cơ sở dữ liệu chính."
        )
    }), 501


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear(); return redirect(url_for("index"))


# =========================
# ADMIN LIVE DATA API
# =========================

def admin_dashboard_payload():
    connection = get_database()

    stats = {
        "users": connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0],

        "active_users": connection.execute(
            "SELECT COUNT(*) FROM users WHERE is_active = 1"
        ).fetchone()[0],

        "admins": connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0],

        "chats": connection.execute(
            "SELECT COUNT(*) FROM chat_logs"
        ).fetchone()[0],

        "images": connection.execute(
            "SELECT COUNT(*) FROM chat_logs WHERE has_image = 1"
        ).fetchone()[0],

        "errors": connection.execute(
            "SELECT COUNT(*) FROM chat_logs WHERE status != 'success'"
        ).fetchone()[0],

        "avg_latency": connection.execute(
            """
            SELECT COALESCE(ROUND(AVG(latency_ms)), 0)
            FROM chat_logs
            WHERE latency_ms > 0
            """
        ).fetchone()[0],

        "tokens": connection.execute(
            """
            SELECT COALESCE(
                SUM(
                    COALESCE(prompt_tokens, 0)
                    + COALESCE(completion_tokens, 0)
                ),
                0
            )
            FROM chat_logs
            """
        ).fetchone()[0],

        "success_rate": connection.execute(
            """
            SELECT COALESCE(
                ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1),
                0
            )
            FROM chat_logs
            """
        ).fetchone()[0],

        "new_today": connection.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE created_at::date = CURRENT_DATE
            """
        ).fetchone()[0],

        "chats_today": connection.execute(
            """
            SELECT COUNT(*)
            FROM chat_logs
            WHERE created_at::date = CURRENT_DATE
            """
        ).fetchone()[0],
    }

    chart_rows = connection.execute(
        """
        SELECT
            day::date AS day,
            (
                SELECT COUNT(*)
                FROM chat_logs
                WHERE created_at::date = day::date
            ) AS chats,
            (
                SELECT COUNT(*)
                FROM users
                WHERE created_at::date = day::date
            ) AS users
        FROM generate_series(
            CURRENT_DATE - INTERVAL '6 days',
            CURRENT_DATE,
            INTERVAL '1 day'
        ) AS day
        ORDER BY day
        """
    ).fetchall()

    recent_users = connection.execute(
        """
        SELECT
            id,
            full_name,
            email,
            role,
            is_active,
            created_at
        FROM users
        ORDER BY id DESC
        LIMIT 6
        """
    ).fetchall()

    recent_chats = connection.execute(
        """
        SELECT
            c.id,
            c.question,
            c.model,
            c.status,
            c.latency_ms,
            c.created_at,
            COALESCE(u.full_name, 'Khách') AS full_name
        FROM chat_logs c
        LEFT JOIN users u ON u.id = c.user_id
        ORDER BY c.id DESC
        LIMIT 6
        """
    ).fetchall()

    connection.close()

    return {
        "stats": stats,
        "chart": [dict(row) for row in chart_rows],
        "recent_users": [dict(row) for row in recent_users],
        "recent_chats": [dict(row) for row in recent_chats],
        "server_time": datetime.now().strftime("%H:%M:%S"),
        "ai": {
            "provider": "Google Gemini",
            "api_configured": bool(API_KEY),
            "text_model": get_setting("text_model", MODEL_NAME),
            "vision_model": get_setting("vision_model", VISION_MODEL_NAME),
        },
    }


@app.get("/admin/api/dashboard")
@admin_required
def admin_api_dashboard():
    response = jsonify(admin_dashboard_payload())
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/admin/api/users")
@admin_required
def admin_api_users():
    keyword = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip()
    status = request.args.get("status", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(
        max(request.args.get("per_page", 20, type=int), 5),
        100,
    )

    where = []
    params = []

    if keyword:
        where.append(
            """
            (
                u.full_name ILIKE ?
                OR u.email ILIKE ?
                OR COALESCE(u.phone, '') ILIKE ?
            )
            """
        )
        params.extend([f"%{keyword}%"] * 3)

    if role in {"user", "admin"}:
        where.append("u.role = ?")
        params.append(role)

    if status in {"0", "1"}:
        where.append("u.is_active = ?")
        params.append(int(status))

    clause = (
        "WHERE " + " AND ".join(where)
        if where
        else ""
    )

    connection = get_database()

    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM users u
        {clause}
        """,
        params,
    ).fetchone()[0]

    rows = connection.execute(
        f"""
        SELECT
            u.id,
            u.full_name,
            u.email,
            u.phone,
            u.role,
            u.is_active,
            u.created_at,
            (
                SELECT COUNT(*)
                FROM chat_logs c
                WHERE c.user_id = u.id
            ) AS chat_count,
            (
                SELECT MAX(created_at)
                FROM chat_logs c
                WHERE c.user_id = u.id
            ) AS last_activity
        FROM users u
        {clause}
        ORDER BY u.id DESC
        LIMIT ?
        OFFSET ?
        """,
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    role_counts = {
        "all": connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0],

        "user": connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'user'"
        ).fetchone()[0],

        "admin": connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin'"
        ).fetchone()[0],
    }

    latest_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM users"
    ).fetchone()[0]

    connection.close()

    response = jsonify({
        "items": [dict(row) for row in rows],
        "total": total,
        "counts": role_counts,
        "latest_id": latest_id,
        "database_file": "PostgreSQL",
        "page": page,
        "pages": max(
            1,
            (total + per_page - 1) // per_page,
        ),
        "server_time": datetime.now().strftime("%H:%M:%S"),
    })

    response.headers[
        "Cache-Control"
    ] = "no-store, no-cache, must-revalidate, max-age=0"

    response.headers["Pragma"] = "no-cache"

    return response


@app.get("/admin/api/chats")
@admin_required
def admin_api_chats():
    q = request.args.get("q", "").strip()
    model = request.args.get("model", "").strip()
    status = request.args.get("status", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 25

    where = []
    params = []

    if q:
        where.append(
            """
            (
                c.question ILIKE ?
                OR c.answer ILIKE ?
                OR COALESCE(u.full_name, '') ILIKE ?
            )
            """
        )
        params.extend([f"%{q}%"] * 3)

    if model:
        where.append("c.model = ?")
        params.append(model)

    if status in {"success", "error"}:
        if status == "success":
            where.append("c.status = 'success'")
        else:
            where.append("c.status != 'success'")

    clause = (
        "WHERE " + " AND ".join(where)
        if where
        else ""
    )

    connection = get_database()

    total = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM chat_logs c
        LEFT JOIN users u ON u.id = c.user_id
        {clause}
        """,
        params,
    ).fetchone()[0]

    rows = connection.execute(
        f"""
        SELECT
            c.id,
            c.question,
            c.answer,
            c.model,
            c.has_image,
            c.latency_ms,
            c.prompt_tokens,
            c.completion_tokens,
            c.status,
            c.error_message,
            c.created_at,
            COALESCE(u.full_name, 'Khách') AS full_name,
            u.email
        FROM chat_logs c
        LEFT JOIN users u ON u.id = c.user_id
        {clause}
        ORDER BY c.id DESC
        LIMIT ?
        OFFSET ?
        """,
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    connection.close()

    return jsonify({
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "pages": max(
            1,
            (total + per_page - 1) // per_page,
        ),
        "server_time": datetime.now().strftime("%H:%M:%S"),
    })
    q = request.args.get("q", "").strip()
    model = request.args.get("model", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 25
    where, params = [], []
    if q:
        where.append("(c.question LIKE ? OR c.answer LIKE ? OR COALESCE(u.full_name,'') LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    if model:
        where.append("c.model = ?")
        params.append(model)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    connection = get_database()
    total = connection.execute(
        f"SELECT COUNT(*) FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id {clause}",
        params,
    ).fetchone()[0]
    rows = connection.execute(f"""
        SELECT c.id, c.question, c.answer, c.model, c.has_image, c.latency_ms,
               c.prompt_tokens, c.completion_tokens, c.status, c.created_at,
               COALESCE(u.full_name,'Khách') AS full_name, u.email
        FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id
        {clause} ORDER BY c.id DESC LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()
    connection.close()
    return jsonify({
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "server_time": datetime.now().strftime("%H:%M:%S"),
    })

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    print(app.url_map)
    Timer(1.2, open_browser).start()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )