from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from dotenv import load_dotenv

from pathlib import Path
from threading import Timer
<<<<<<< HEAD
import time

# Load variables from .env file
load_dotenv()

app = Flask(__name__)
@app.route("/")
def index():
    return render_template("index.html")
=======
import os
import random
import time
import webbrowser


# =========================================================
# 1. CẤU HÌNH DỰ ÁN
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB


# =========================================================
# 2. CẤU HÌNH GEMINI API
# =========================================================

API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

if not API_KEY:
    raise RuntimeError(
        "Không tìm thấy OPENAI_API_KEY.\n"
        f"Hãy tạo file: {BASE_DIR / '.env'}\n"
        "Và thêm dòng:\n"
        "OPENAI_API_KEY=API_KEY_GEMINI_CUA_BAN"
    )

# Giữ model cũ theo yêu cầu.
# Có thể đổi trong .env bằng: MODEL_NAME=ten-model-khac
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash").strip()
>>>>>>> e399649 (upload project)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    timeout=45.0,
    max_retries=0,  # Tự retry bằng hàm bên dưới để kiểm soát rõ hơn
)


# =========================================================
# 3. PROMPT HỆ THỐNG
# =========================================================

SYSTEM_PROMPT = {
    "role": "system",
    "content": """
Bạn là trợ lý chăm sóc sức khỏe và xây dựng lối sống cá nhân hóa bằng tiếng Việt.

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
  bệnh nền, dị ứng, thai kỳ và thuốc đang sử dụng.
- Không khẳng định thực phẩm bổ sung có thể chữa bệnh.
- Nếu người dùng hỏi về thuốc, hãy hỏi tên thuốc, hàm lượng,
  mục đích sử dụng và các thuốc khác đang dùng.
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
"""
}
<<<<<<< HEAD
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    user_message = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_message:
        return jsonify({
            "error": "Vui lòng nhập nội dung cần tư vấn."
        }), 400

    try:
        messages = [SYSTEM_PROMPT]

        # Chỉ lấy 12 tin nhắn gần nhất
        for msg in history[-12:]:
            role = msg.get("role")
            content = msg.get("content")

            if role in ["user", "assistant"] and content:
                messages.append({
                    "role": role,
                    "content": content
                })

        messages.append({
            "role": "user",
            "content": user_message
        })

        
        response = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=messages
)

        reply = response.choices[0].message.content

        return jsonify({
            "reply": reply
        })

    except Exception as error:
        print(f"Lỗi gọi AI API: {error}")

        return jsonify({
            "error": "Hệ thống đang gặp lỗi. Vui lòng thử lại."
        }), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
    start_time = time.perf_counter()

=======


# =========================================================
# 4. HÀM TIỆN ÍCH
# =========================================================

def clean_history(history):
    """
    Làm sạch lịch sử từ frontend và giới hạn số lượng token gửi lên API.
    """
    if not isinstance(history, list):
        return []

    cleaned = []

    # Chỉ giữ 16 tin nhắn gần nhất để hạn chế lỗi quota/token.
    for item in history[-16:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if not content:
            continue

        cleaned.append({
            "role": role,
            "content": content[:2500]
        })

    return cleaned


def get_error_status(error):
    """
    Lấy HTTP status code từ lỗi API nếu thư viện cung cấp.
    """
    status_code = getattr(error, "status_code", None)

    if isinstance(status_code, int):
        return status_code

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)

    if isinstance(response_status, int):
        return response_status

    return None


def is_retryable_error(error):
    """
    Chỉ retry với lỗi tạm thời: 429, 500, 502, 503, 504 hoặc timeout/kết nối.
    """
    status_code = get_error_status(error)

    if status_code in {429, 500, 502, 503, 504}:
        return True

    error_text = str(error).lower()

    retry_keywords = (
        "429",
        "resource_exhausted",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "service unavailable",
        "timeout",
        "timed out",
        "connection error",
        "connection reset",
    )

    return any(keyword in error_text for keyword in retry_keywords)


def call_ai_with_retry(messages, max_retries=3):
    """
    Gọi Gemini qua endpoint tương thích OpenAI.
    Tự thử lại khi gặp lỗi tạm thời.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.3,
                max_tokens=1200,
            )

        except Exception as error:
            last_error = error

            if not is_retryable_error(error):
                raise

            if attempt >= max_retries - 1:
                break

            # Exponential backoff: khoảng 2s, 4s...
            wait_seconds = (2 ** (attempt + 1)) + random.uniform(0, 0.8)

            print(
                f"API tạm thời quá tải. "
                f"Thử lại lần {attempt + 2}/{max_retries} "
                f"sau {wait_seconds:.1f} giây..."
            )

            time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error

    raise RuntimeError("Không nhận được phản hồi từ dịch vụ AI.")


def build_error_response(error):
    """
    Chuyển lỗi kỹ thuật thành thông báo dễ hiểu cho giao diện.
    """
    status_code = get_error_status(error)
    error_text = str(error).lower()

    if (
        status_code == 429
        or "429" in error_text
        or "resource_exhausted" in error_text
        or "rate limit" in error_text
        or "too many requests" in error_text
        or "quota" in error_text
    ):
        return jsonify({
            "error": (
                "Gemini API đang vượt giới hạn sử dụng hoặc đã hết quota. "
                "Vui lòng chờ một lúc rồi thử lại. Nếu lỗi kéo dài, "
                "hãy kiểm tra quota hoặc billing của API key."
            ),
            "error_code": "RATE_LIMIT"
        }), 429

    if (
        status_code in {401, 403}
        or "api key" in error_text
        or "credential" in error_text
        or "unauthorized" in error_text
        or "permission denied" in error_text
    ):
        return jsonify({
            "error": (
                "API key không hợp lệ, hết quyền hoặc chưa được cấu hình đúng "
                "trong file .env."
            ),
            "error_code": "INVALID_API_KEY"
        }), 401

    if (
        status_code == 404
        or "404" in error_text
        or "model not found" in error_text
        or "not found for api version" in error_text
    ):
        return jsonify({
            "error": (
                f"Không tìm thấy hoặc không được phép dùng model '{MODEL_NAME}'. "
                "Hãy kiểm tra MODEL_NAME trong file .env."
            ),
            "error_code": "MODEL_NOT_FOUND"
        }), 404

    if status_code == 400 or "400" in error_text:
        return jsonify({
            "error": (
                "Yêu cầu gửi đến AI không hợp lệ. "
                "Có thể lịch sử hội thoại hoặc tên model chưa đúng."
            ),
            "error_code": "BAD_REQUEST"
        }), 400

    if status_code in {500, 502, 503, 504}:
        return jsonify({
            "error": (
                "Dịch vụ AI đang tạm thời không ổn định. "
                "Vui lòng thử lại sau ít phút."
            ),
            "error_code": "SERVICE_UNAVAILABLE"
        }), 503

    return jsonify({
        "error": (
            "Không thể kết nối với hệ thống AI. "
            "Vui lòng xem Terminal để biết lỗi kỹ thuật chi tiết."
        ),
        "error_code": "API_ERROR"
    }), 500


# =========================================================
# 5. ROUTES
# =========================================================

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL_NAME
    })


@app.post("/chat")
def chat():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Dữ liệu gửi lên không hợp lệ."
        }), 400

    user_message = str(data.get("message", "")).strip()
    history = clean_history(data.get("history", []))

    if not user_message:
        return jsonify({
            "error": "Bạn chưa nhập nội dung cần hỏi."
        }), 400

    if len(user_message) > 4000:
        return jsonify({
            "error": "Nội dung quá dài. Vui lòng nhập dưới 4.000 ký tự."
        }), 400

    messages = [
        SYSTEM_PROMPT,
        *history,
        {
            "role": "user",
            "content": user_message
        }
    ]

    try:
        response = call_ai_with_retry(messages)

        if not response.choices:
            return jsonify({
                "error": "AI không trả về nội dung. Vui lòng thử lại."
            }), 502

        reply = response.choices[0].message.content

        if not isinstance(reply, str) or not reply.strip():
            return jsonify({
                "error": "AI trả về nội dung trống. Vui lòng thử lại."
            }), 502

        return jsonify({
            "reply": reply.strip()
        })

    except Exception as error:
        print(f"Gemini API error: {type(error).__name__}: {error}")
        return build_error_response(error)


# =========================================================
# 6. CHẠY ỨNG DỤNG
# =========================================================

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    Timer(1.2, open_browser).start()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )
>>>>>>> e399649 (upload project)
