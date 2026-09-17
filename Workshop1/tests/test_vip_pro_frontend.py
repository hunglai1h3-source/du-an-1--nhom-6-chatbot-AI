import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(r"E:\AI.CHATBOT\Workshop1")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

with patch("psycopg_pool.ConnectionPool"):
    import app as flask_app


class TestVIPProFrontend(unittest.TestCase):
    """Bộ kiểm tra xác minh kiến trúc và trải nghiệm mới của VIP Pro Frontend Rebuild."""

    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.client = cls.app.test_client()
        cls.static_dir = BASE_DIR / "static"
        cls.templates_dir = BASE_DIR / "templates"

    def test_01_public_landing_route_and_content(self):
        """Khách chưa đăng nhập vào GET / được phục vụ Public Landing Page mới."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Sức khỏe của bạn.", html)
        self.assertIn("Được hiểu theo thời gian.", html)
        self.assertIn('id="landingCanvas"', html)
        self.assertIn("AN TOÀN", html)
        self.assertIn("ĐÁNG TIN", html)
        self.assertIn("ĐỒNG HÀNH", html)
        self.assertIn("Medical Safety V2", html)
        self.assertIn("Medical RAG Chuẩn hóa", html)
        self.assertIn("Long-term Health Context", html)
        self.assertIn('href="/register"', html)
        self.assertIn('href="/login"', html)

    def test_02_explicit_landing_route(self):
        """Route /landing luôn trả về Public Landing Page."""
        res = self.client.get("/landing")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("landing-hero", html)

    def test_03_dashboard_route_guard_for_unauthenticated(self):
        """Route /dashboard yêu cầu đăng nhập, chuyển hướng người dùng chưa xác thực về /login."""
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_04_master_design_system_theme_css(self):
        """File static/theme.css chứa đầy đủ Master Design Tokens (L0-L4, Dark/Light, Motion)."""
        theme_path = self.static_dir / "theme.css"
        self.assertTrue(theme_path.exists())
        with open(theme_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn("--bg-l0:", css)
        self.assertIn("--bg-l4:", css)
        self.assertIn("--accent-primary: #0d9488", css)
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn("--bg-l0: #070b12", css)
        self.assertIn("--motion-cinematic: 700ms", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_05_landing_canvas_energy_savings_and_motion(self):
        """static/landing.js hỗ trợ visibilitychange auto-pause và prefers-reduced-motion."""
        landing_js_path = self.static_dir / "landing.js"
        self.assertTrue(landing_js_path.exists())
        with open(landing_js_path, "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("visibilitychange", js)
        self.assertIn("document.hidden", js)
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn("cancelAnimationFrame", js)

    def test_06_editorial_health_news_page(self):
        """GET /ban-tin-suc-khoe render giao diện tạp chí chuyên môn mới với theme.css."""
        res = self.client.get("/ban-tin-suc-khoe")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Bản tin sức khỏe", html)
        self.assertIn("theme.css", html)
        self.assertIn("news-public-grid", html)

    def test_07_medical_ai_workspace_bot_avatar_and_contracts(self):
        """templates/chat.html có biểu tượng pulse glyph SVG chuyên nghiệp, giữ nguyên hợp đồng UI/UX."""
        chat_html_path = self.templates_dir / "chat.html"
        with open(chat_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('class="bot-avatar"', html)
        self.assertIn("<svg", html)
        self.assertNotIn("🤖", html)
        self.assertIn('id="confirmDeleteModal"', html)
        self.assertIn('id="charCounter"', html)
        self.assertIn('id="mobileMenuButton"', html)


if __name__ == "__main__":
    unittest.main()
