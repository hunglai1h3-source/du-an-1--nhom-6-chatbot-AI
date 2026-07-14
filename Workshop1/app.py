from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os
from dotenv import load_dotenv
import webbrowser
from threading import Timer

# Load variables from .env file
load_dotenv()
print(os.getenv("OPENAI_API_KEY"))
app = Flask(__name__)

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
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    history = data.get("history", [])

    if not user_message:
        return jsonify({"error": "Message is empty"}), 400

    try:
        # Build the conversation history for context
        messages = [SYSTEM_PROMPT]
        
        # Append previous conversation history
        for msg in history:
            messages.append({
                "role": msg.get("role"),
                "content": msg.get("content")
            })
            
        # Append the new user message
        messages.append({"role": "user", "content": user_message})

        # Call the API using gemini-3.5-flash model
        response = client.chat.completions.create(
            model="gemini-3.5-flash",
            messages=messages,
            temperature=0.7
        )

        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Error calling AI API: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:5000")
    app.run(debug=True)
    import webbrowser
from threading import Timer

chrome_path = "C:/Program Files/Google/Chrome/Application/chrome.exe %s"

def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    Timer(1, open_browser).start()
    app.run(debug=True, port=5000)