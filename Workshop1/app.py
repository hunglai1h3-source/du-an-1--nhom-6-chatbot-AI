from flask import (Flask, jsonify, render_template, request, session,
                   redirect, url_for, send_file)
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from threading import Timer
from datetime import datetime, date
from functools import wraps
import math
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import json
import re
import os
import sqlite3
import time
import webbrowser
import csv
import shutil
from uuid import uuid4
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key-before-deploy"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Model dùng cho các câu hỏi chỉ có văn bản.
MODEL_NAME = "llama-3.1-8b-instant"

VISION_MODEL_NAME = os.getenv(
    "VISION_MODEL_NAME",
    "qwen/qwen3.6-27b"
).strip()
MEDICINE_IMAGE_PROMPT = """
Bạn là trợ lý hỗ trợ phân tích hình ảnh thuốc.

Hãy quan sát toàn bộ ảnh và tìm tất cả thuốc, hộp thuốc, vỉ thuốc,
chai thuốc, đơn thuốc hoặc nhãn thuốc xuất hiện trong ảnh.

Với từng thuốc, hãy cung cấp:
1. Tên thuốc nhìn thấy trên ảnh.
2. Hoạt chất.
3. Hàm lượng.
4. Dạng bào chế.
5. Nhà sản xuất.
6. Số lô và hạn sử dụng nếu nhìn thấy.
7. Toàn bộ chữ quan trọng đọc được trên bao bì.
8. Công dụng thường gặp.
9. Cảnh báo và chống chỉ định quan trọng.
10. Mức độ chắc chắn: cao, trung bình hoặc thấp.

Quy tắc an toàn:
- Không được tự đoán khi chữ hoặc hình ảnh không rõ.
- Thông tin không nhìn thấy phải ghi "Không xác định được từ ảnh".
- Không khẳng định chắc chắn danh tính của viên thuốc rời chỉ dựa vào màu sắc.
- Không tự đưa ra liều dùng cho người dùng.
- Không khuyên người dùng tự ý bắt đầu, ngừng hoặc đổi thuốc.
- Nếu ảnh mờ, bị lóa, bị che hoặc quá xa, hãy yêu cầu chụp lại.
- Nếu phát hiện nhiều thuốc, phải trình bày từng thuốc riêng biệt.
- Cuối câu trả lời phải nhắc người dùng kiểm tra lại với dược sĩ hoặc bác sĩ.
"""

# Model đa phương thức bắt buộc dùng khi người dùng gửi ảnh.
VISION_MODEL_NAME = os.getenv(
    "VISION_MODEL_NAME",
    "qwen/qwen3.6-27b"
).strip()


# Model nhận dạng giọng nói tiếng Việt.
AUDIO_TRANSCRIPTION_MODEL = os.getenv(
    "AUDIO_TRANSCRIPTION_MODEL",
    "whisper-large-v3-turbo"
).strip()

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
        base_url="https://api.groq.com/openai/v1",
        timeout=90.0,
        max_retries=1,
    )
else:
    client = None
    print(
        "CẢNH BÁO: Chưa có Groq API key. "
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
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS health_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            sex TEXT NOT NULL,
            birth_date TEXT,
            age INTEGER,
            height_cm REAL NOT NULL,
            activity_level TEXT NOT NULL DEFAULT 'sedentary',
            goal TEXT NOT NULL DEFAULT 'maintain',
            diet_preference TEXT,
            allergies TEXT,
            medical_notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight_kg REAL NOT NULL,
            note TEXT,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS water_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount_ml INTEGER NOT NULL,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Nâng cấp database cũ mà không xóa dữ liệu người dùng.
    user_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "role" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
        )
    if "is_active" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_user_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL
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
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            relationship TEXT NOT NULL DEFAULT 'Khác',
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            medical_conditions TEXT,
            allergies TEXT,
            avatar_seed TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_family_members_user
        ON family_members(user_id, updated_at)
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            updated_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL DEFAULT 'system',
            content TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_created ON chat_logs(created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_logs_user ON chat_logs(user_id)")

    connection.commit()
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


def get_active_system_prompt():
    connection = get_database()
    row = connection.execute(
        "SELECT content FROM prompt_versions WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    connection.close()
    if row:
        return {"role": "system", "content": row["content"]}
    return SYSTEM_PROMPT


def record_chat_log(question, answer, model, has_image, latency_ms, status="success", error_message="", usage=None):
    try:
        usage = usage or {}
        connection = get_database()
        connection.execute(
            """INSERT INTO chat_logs (user_id, question, answer, model, has_image, latency_ms,
                   prompt_tokens, completion_tokens, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.get("user_id"), str(question)[:4000], str(answer or "")[:12000],
             str(model)[:120], int(bool(has_image)), int(latency_ms or 0),
             int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0),
             str(status)[:30], str(error_message or "")[:1000]),
        )
        connection.commit()
        connection.close()
    except Exception as log_error:
        print("Không thể ghi chat log:", log_error)


def clean_history(history):
    if not isinstance(history, list):
        return []

    cleaned = []

    for item in history[-12:]:
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
                "content": content[:2000]
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

    print("CHI TIẾT LỖI GROQ:", repr(error))
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
                    "Groq đã hết lượt sử dụng hoặc vượt giới hạn hiện tại. "
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
                "Hệ thống Groq đang quá tải hoặc tạm thời không khả dụng. "
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
                "Không thể sử dụng model Groq đã cấu hình. "
                f"Text model: {MODEL_NAME}; vision model: {VISION_MODEL_NAME}. "
                "Hãy kiểm tra MODEL_NAME và VISION_MODEL_NAME trong file .env."
            )
        }), 404

    if (
        "timeout" in error_text
        or "timed out" in error_text
    ):
        return jsonify({
            "error": (
                "Groq phản hồi quá lâu. Vui lòng gửi lại câu hỏi."
            )
        }), 504

    if (
        "connection" in error_text
        or "network" in error_text
    ):
        return jsonify({
            "error": (
                "Không thể kết nối tới máy chủ Groq. "
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

    except sqlite3.IntegrityError as error:
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
    if "user_id" not in session:
        return jsonify({"logged_in": False})

    return jsonify({
        "logged_in": True,
        "user": {
            "id": session.get("user_id"),
            "full_name": session.get("full_name"),
            "email": session.get("email"),
            "phone": session.get("phone"),
            "role": session.get("role", "user")
        }
    })


@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Đăng xuất thành công."})



@app.post("/transcribe")
def transcribe_audio():
    """Nhận file ghi âm từ trình duyệt và chuyển giọng nói tiếng Việt thành chữ."""
    if client is None:
        return jsonify({
            "error": (
                "Chưa cấu hình Groq API key. "
                "Hãy kiểm tra file .env."
            )
        }), 503

    audio_file = request.files.get("audio")

    if audio_file is None or not audio_file.filename:
        return jsonify({
            "error": "Bạn chưa gửi file âm thanh."
        }), 400

    extension = Path(audio_file.filename).suffix.lower()

    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({
            "error": (
                "Định dạng âm thanh không được hỗ trợ. "
                "Hãy dùng WEBM, WAV, MP3, M4A, OGG hoặc FLAC."
            )
        }), 400

    audio_bytes = audio_file.read()

    if not audio_bytes:
        return jsonify({
            "error": "File âm thanh đang trống."
        }), 400

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({
            "error": "File âm thanh vượt quá dung lượng tối đa 5 MB."
        }), 400

    mime_type = (
        audio_file.mimetype
        or "application/octet-stream"
    )

    safe_filename = f"voice{extension}"

    try:
        transcription = (
            client.audio.transcriptions.create(
                file=(
                    safe_filename,
                    audio_bytes,
                    mime_type
                ),
                model=AUDIO_TRANSCRIPTION_MODEL,
                language="vi",
                response_format="json",
                temperature=0.0,
                prompt=(
                    "Đây là câu hỏi sức khỏe bằng tiếng Việt. "
                    "Giữ đúng tên thuốc, triệu chứng và thuật ngữ y tế."
                )
            )
        )

        transcript_text = str(
            getattr(transcription, "text", "") or ""
        ).strip()

        if not transcript_text:
            return jsonify({
                "error": (
                    "Không nhận dạng được lời nói. "
                    "Hãy nói lại gần micro hơn."
                )
            }), 422

        return jsonify({
            "text": transcript_text,
            "model": AUDIO_TRANSCRIPTION_MODEL
        })

    except Exception as error:
        print(
            "Groq speech-to-text error: "
            f"{type(error).__name__}: {error}"
        )
        return build_error_response(error)


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
    if client is None:
        return jsonify({
            "error": (
                "Chưa cấu hình Groq API key. "
                "Hãy kiểm tra file .env trong thư mục Workshop1."
            )
        }), 503

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

        if not user_message and not has_image:
            return jsonify({
                "error": "Bạn chưa nhập câu hỏi hoặc chọn ảnh."
            }), 400

        if len(user_message) > 4000:
            return jsonify({
                "error": "Nội dung quá dài. Vui lòng nhập dưới 4.000 ký tự."
            }), 400

        messages = [get_active_system_prompt()]

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
                profile_context = {
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

                messages.append({
                    "role": "system",
                    "content": (
                        "HỒ SƠ SỨC KHỎE DO NGƯỜI DÙNG TỰ KHAI:\n"
                        + json.dumps(
                            profile_context,
                            ensure_ascii=False
                        )
                        + "\nChỉ dùng hồ sơ này để cá nhân hóa an toàn. "
                        "Không coi dữ liệu tự khai là chẩn đoán."
                    ),
                })

        # Hồ sơ thành viên gia đình đang được chọn trên giao diện.
        if selected_profile:
            allowed_profile_fields = {
                key: selected_profile.get(key)
                for key in (
                    "id", "name", "relationship", "age", "gender",
                    "height", "weight", "condition", "allergies"
                )
                if selected_profile.get(key) not in (None, "")
            }
            if allowed_profile_fields:
                messages.append({
                    "role": "system",
                    "content": (
                        "THÀNH VIÊN GIA ĐÌNH ĐANG ĐƯỢC CHỌN ĐỂ TƯ VẤN:\n"
                        + json.dumps(allowed_profile_fields, ensure_ascii=False)
                        + "\nDữ liệu do người dùng tự khai. Chỉ dùng để cá nhân hóa "
                        "và không được nhầm với thành viên khác."
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
                limit=3
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

        if has_image:
            data_url = image_to_data_url(image_file)

            prompt_text = user_message or (
                "Hãy phân tích ảnh này. "
                "Nếu đây là hộp thuốc, vỉ thuốc, lọ thuốc hoặc nhãn thuốc, "
                "hãy đọc tên thuốc, hoạt chất, hàm lượng, dạng bào chế "
                "và nhà sản xuất nếu nhìn thấy rõ."
            )

            prompt_text += """

YÊU CẦU TRẢ LỜI:
- Chỉ trả lời kết quả cuối cùng bằng tiếng Việt.
- Không trình bày quá trình quan sát hoặc suy luận.
- Không viết các tiêu đề như "Text on the box", "Analysis", "Reasoning".
- Không liệt kê toàn bộ chữ trên bao bì.
- Không dịch từng dòng chữ sang tiếng Anh.
- Trả lời ngắn gọn theo cấu trúc:

1. Tên sản phẩm hoặc thuốc:
2. Hoạt chất và hàm lượng:
3. Công dụng ghi trên bao bì:
4. Dạng bào chế và số lượng:
5. Nhà sản xuất:
6. Lưu ý an toàn:

- Chỉ nêu thông tin nhìn thấy rõ trong ảnh.
- Nếu không đọc rõ, ghi "Không xác định".
- Không tự đưa liều dùng.
- Không xác định viên thuốc rời chỉ dựa vào màu sắc hoặc hình dạng.
"""

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

        if has_image:
            messages.insert(0, {
                "role": "system",
                "content": MEDICINE_IMAGE_PROMPT
            })

        start_time = time.perf_counter()

        selected_model = (
            VISION_MODEL_NAME
            if has_image
            else MODEL_NAME
        )

        max_output_tokens = 1500 if has_image else 1000

        response = client.chat.completions.create(
            model=selected_model,
            messages=messages,
            temperature=0.2 if has_image else 0.3,
            max_completion_tokens=max_output_tokens,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000)
        print(
            f"Thời gian Groq phản hồi bằng {selected_model}: "
            f"{elapsed_ms / 1000:.2f} giây"
        )
        if not response.choices:
            return jsonify({
                "error": "AI không trả về nội dung."
            }), 502

        reply = response.choices[0].message.content or ""

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
        record_chat_log(user_message or "[Ảnh được tải lên]", reply, selected_model, has_image, elapsed_ms, usage=usage_data)
        return jsonify({
            "reply": reply
        })

    except ValueError as error:
        return jsonify({
            "error": str(error)
        }), 400

    except Exception as error:
        print(
            f"Groq API error: "
            f"{type(error).__name__}: {error}"
        )

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
    if reminder_type not in {"water", "medicine", "weight", "exercise", "meal"}:
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
    now = datetime.now()
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
            "error": "Chưa cấu hình Groq API key."
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
        response = client.chat.completions.create(
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
        print(f"Groq API error: {type(error).__name__}: {error}")
        return build_error_response(error)



# =========================
# ADMIN MANAGEMENT MODULE - GIAI ĐOẠN 1
# =========================

def admin_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        if session.get("role") != "admin":
            return jsonify({"error": "Bạn không có quyền quản trị."}), 403
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
    }
    chart_rows = connection.execute("""
        WITH RECURSIVE dates(day) AS (
            SELECT date('now','-6 day') UNION ALL SELECT date(day,'+1 day') FROM dates WHERE day < date('now')
        )
        SELECT day, (SELECT COUNT(*) FROM chat_logs WHERE date(created_at)=day) chats,
                    (SELECT COUNT(*) FROM users WHERE date(created_at)=day) users
        FROM dates
    """).fetchall()
    recent_chats = connection.execute("""
        SELECT c.*, u.full_name FROM chat_logs c LEFT JOIN users u ON u.id=c.user_id
        ORDER BY c.id DESC LIMIT 8
    """).fetchall()
    connection.close()
    return render_template("admin/dashboard.html", stats=stats, chart_rows=chart_rows, recent_chats=recent_chats)


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
        (SELECT MAX(created_at) FROM chat_logs c WHERE c.user_id=u.id) last_activity
        FROM users u {clause} ORDER BY u.id DESC LIMIT ? OFFSET ?
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
    settings={"text_model":get_setting("text_model",MODEL_NAME),"vision_model":get_setting("vision_model",VISION_MODEL_NAME),"temperature":get_setting("temperature","0.3"),"max_tokens":get_setting("max_tokens","1000"),"provider":"Groq","api_configured":bool(API_KEY)}
    return render_template("admin/ai_settings.html",settings=settings)


@app.post("/admin/ai-settings")
@admin_required
def admin_ai_settings_save():
    allowed={"text_model","vision_model","temperature","max_tokens"}; connection=get_database()
    for key in allowed:
        value=request.form.get(key,"").strip()
        connection.execute("INSERT INTO system_settings(setting_key,setting_value,updated_by,updated_at) VALUES (?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP",(key,value,session["user_id"]))
    write_admin_log(connection,"update_ai_settings",details="Cần khởi động lại để áp dụng model"); connection.commit(); connection.close(); return redirect(url_for("admin_ai_settings"))


@app.get("/admin/audit-logs")
@admin_required
def admin_audit_logs():
    connection=get_database(); logs=connection.execute("SELECT l.*,a.full_name admin_name,u.full_name target_name FROM admin_audit_logs l JOIN users a ON a.id=l.admin_user_id LEFT JOIN users u ON u.id=l.target_user_id ORDER BY l.id DESC LIMIT 500").fetchall(); connection.close(); return render_template("admin/audit_logs.html",logs=logs)


@app.get("/admin/backup/users-db")
@admin_required
def admin_backup_users_db():
    connection=get_database(); write_admin_log(connection,"backup_database",details="Tải bản sao users.db"); connection.commit(); connection.close(); return send_file(DATABASE_PATH,as_attachment=True,download_name=f"users-backup-{datetime.now():%Y%m%d-%H%M%S}.db")


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear(); return redirect(url_for("index"))

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