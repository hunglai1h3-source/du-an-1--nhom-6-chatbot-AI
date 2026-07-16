from flask import Flask, jsonify, render_template, request, session
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

        messages = [SYSTEM_PROMPT]

        if "user_id" in session:
            connection = get_database()
            profile = connection.execute(
                "SELECT * FROM health_profiles WHERE user_id = ?",
                (session["user_id"],),
            ).fetchone()
            latest_weight = get_latest_weight(connection, session["user_id"])
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
                        + json.dumps(profile_context, ensure_ascii=False)
                        + "\nChỉ dùng hồ sơ này để cá nhân hóa an toàn. "
                          "Không coi dữ liệu tự khai là chẩn đoán."
                    ),
                })

        messages.extend(history)

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
        return jsonify({"error": "Chưa cấu hình Gemini API key."}), 503

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

Yêu cầu bắt buộc:
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
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1400,
            reasoning_effort="low",
        )

        if not response.choices:
            return jsonify({"error": "AI không trả về nội dung."}), 502

        reply = response.choices[0].message.content
        if not isinstance(reply, str) or not reply.strip():
            return jsonify({"error": "AI trả về nội dung trống."}), 502

        return jsonify({
            "reply": reply.strip(),
            "metrics": metrics,
        })

    except Exception as error:
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