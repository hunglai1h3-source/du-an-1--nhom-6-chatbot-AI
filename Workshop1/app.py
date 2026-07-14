from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os
from dotenv import load_dotenv
import webbrowser
from threading import Timer
import time

# Load variables from .env file
load_dotenv()

app = Flask(__name__)
@app.route("/")
def index():
    return render_template("index.html")

# Initialize OpenAI client with Google Gemini's OpenAI-compatible endpoint
# This allows using the Gemini API Key (AIzaSy...) with the openai python package.
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# System prompt defining the AI's persona
SYSTEM_PROMPT = {
    "role": "system",
    "content": """
Bạn là chatbot tư vấn sức khỏe.

Khi người dùng mô tả triệu chứng lần đầu:

KHÔNG được kết luận.
KHÔNG được đưa thuốc.
KHÔNG được giải thích dài.

Hãy hỏi từng câu một.

Mỗi lần chỉ hỏi đúng 1 câu.

Sau khi thu thập đủ khoảng 5–8 thông tin mới được đưa ra đánh giá.

Các thông tin cần hỏi gồm:
- Tuổi
- Giới tính
- Triệu chứng
- Thời gian bị
- Mức độ đau
- Có sốt không
- Có bệnh nền không
- Có đang dùng thuốc không

Không hỏi nhiều câu trong cùng một lần.
"""
}
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

