from flask import Flask, jsonify, render_template, request, session
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from threading import Timer
from werkzeug.security import generate_password_hash, check_password_hash
import base64
import json
import os
import sqlite3
import time
import webbrowser

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

API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash").strip()
print("MODEL ĐANG DÙNG:", MODEL_NAME)

if API_KEY:
    client = OpenAI(
    api_key=API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    timeout=90.0,
    max_retries=1
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
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def get_database():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_database()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.commit()
    connection.close()


initialize_database()


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
                f"Không thể sử dụng model {MODEL_NAME}. "
                "Hãy kiểm tra tên model trong file .env."
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


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL_NAME
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

    session.clear()
    session["user_id"] = user["id"]
    session["full_name"] = user["full_name"]
    session["email"] = user["email"]
    session["phone"] = user["phone"]

    return jsonify({
        "message": "Đăng nhập thành công.",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "phone": user["phone"]
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
            "phone": session.get("phone")
        }
    })


@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Đăng xuất thành công."})


@app.post("/chat")
def chat():
    if client is None:
        return jsonify({
            "error": (
                "Chưa cấu hình Gemini API key. "
                "Đăng ký và đăng nhập vẫn sử dụng được.."
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

            image_file = None

        if not user_message and not image_file:
            return jsonify({
                "error": "Bạn chưa nhập câu hỏi hoặc chọn ảnh."
            }), 400

        if len(user_message) > 4000:
            return jsonify({
                "error": "Nội dung quá dài. Vui lòng nhập dưới 4.000 ký tự."
            }), 400

        messages = [SYSTEM_PROMPT, *history]

        if image_file:
            data_url = image_to_data_url(image_file)

            prompt_text = user_message or (
                "Hãy xem ảnh này và mô tả những dấu hiệu sức khỏe "
                "có thể quan sát được. Không chẩn đoán chắc chắn "
                "và hãy hỏi thêm thông tin cần thiết."
            )

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

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.3,
            max_tokens=1000,
            reasoning_effort="low"
        )

        print(
            f"Thời gian Gemini phản hồi: "
            f"{time.perf_counter() - start_time:.2f} giây"
        )

        if not response.choices:
            return jsonify({"error": "AI không trả về nội dung."}), 502

        reply = response.choices[0].message.content

        if not isinstance(reply, str) or not reply.strip():
            return jsonify({"error": "AI trả về nội dung trống."}), 502

        return jsonify({"reply": reply.strip()})

    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    except Exception as error:
        print(f"Gemini API error: {type(error).__name__}: {error}")
        return build_error_response(error)


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