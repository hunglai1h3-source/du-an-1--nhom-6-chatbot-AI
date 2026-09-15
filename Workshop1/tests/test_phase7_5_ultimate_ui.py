import os
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class TestPhase75UltimateUI(unittest.TestCase):
    """Kiểm thử toàn diện Phase 7.5 - MediCare AI Ultimate UI (Premium Visual Experience V3)."""

    @classmethod
    def setUpClass(cls):
        # Mock remote DB connection pool to avoid network delays when importing app
        with patch("psycopg_pool.ConnectionPool") as mock_pool:
            mock_pool.return_value = MagicMock()
            import app as flask_app
            cls.app = flask_app.app
            cls.client = cls.app.test_client()

    def setUp(self):
        self.static_dir = BASE_DIR / "static"
        self.templates_dir = BASE_DIR / "templates"

    # ==========================================================================
    # 1. CINEMATIC AUTH EXPERIENCE (GET /login & GET /register)
    # ==========================================================================
    def test_01_auth_routes_return_200(self):
        """GET /login và GET /register trả về HTTP 200 và template auth.html."""
        res_login = self.client.get("/login")
        self.assertEqual(res_login.status_code, 200)
        html_login = res_login.data.decode("utf-8")
        self.assertIn("MediCare", html_login)
        self.assertIn("healthCanvas", html_login)
        self.assertIn('id="tabLoginBtn"', html_login)

        res_reg = self.client.get("/register")
        self.assertEqual(res_reg.status_code, 200)
        html_reg = res_reg.data.decode("utf-8")
        self.assertIn("Khởi tạo tài khoản", html_reg)
        self.assertIn('id="tabRegisterBtn"', html_reg)

    def test_02_auth_template_accessibility_and_forms(self):
        """templates/auth.html chứa đầy đủ nhãn, autocomplete, nút toggle mật khẩu."""
        auth_html_path = self.templates_dir / "auth.html"
        self.assertTrue(auth_html_path.exists())
        with open(auth_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Canvas & Storytelling
        self.assertIn('id="healthCanvas"', content)
        self.assertIn('class="cinematic-pillars"', content)
        self.assertIn("Bảo mật y tế đa lớp", content)

        # Form elements & Autocomplete
        self.assertIn('autocomplete="username"', content)
        self.assertIn('autocomplete="current-password"', content)
        self.assertIn('autocomplete="new-password"', content)
        self.assertIn('class="pwd-toggle-btn"', content)
        self.assertIn('id="rememberMe"', content)

    def test_03_auth_css_tokens_and_cinematic_rules(self):
        """static/auth.css chứa tokens, glassmorphism, responsive và prefers-reduced-motion."""
        auth_css_path = self.static_dir / "auth.css"
        self.assertTrue(auth_css_path.exists())
        with open(auth_css_path, "r", encoding="utf-8") as f:
            css = f.read()

        # Design Tokens
        self.assertIn("--med-primary:", css)
        self.assertIn("--cinematic-bg:", css)
        self.assertIn('html[data-theme="dark"]', css)

        # Layout & Performance
        self.assertIn(".auth-shell", css)
        self.assertIn(".auth-cinematic-panel", css)
        self.assertIn(".auth-glass-card", css)
        self.assertIn("@media (max-width: 1024px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

    def test_04_auth_js_canvas_and_energy_saving(self):
        """static/auth.js chứa động cơ sóng ECG, auto-pause khi tab ẩn và submit forms."""
        auth_js_path = self.static_dir / "auth.js"
        self.assertTrue(auth_js_path.exists())
        with open(auth_js_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn("class CinematicHealthCanvas", js)
        self.assertIn("drawEcgWave", js)
        self.assertIn("visibilitychange", js)
        self.assertIn("prefers-reduced-motion", js)
        self.assertIn('fetch("/login"', js)
        self.assertIn('fetch("/register"', js)

    # ==========================================================================
    # 2. DASHBOARD V3 (HOME OVERVIEW)
    # ==========================================================================
    def test_05_dashboard_template_hero_cta(self):
        """templates/index.html chứa Dashboard Hero hiện đại và CTA 'Trò chuyện với MediCare AI'."""
        index_html_path = self.templates_dir / "index.html"
        self.assertTrue(index_html_path.exists())
        with open(index_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('class="home-greeting"', content)
        self.assertIn('id="welcomeName"', content)
        self.assertIn('id="heroChatCta"', content)
        self.assertIn('href="/tu-van"', content)
        self.assertIn("Trò chuyện với MediCare AI", content)

    def test_06_dashboard_css_responsive_and_dark_mode(self):
        """static/dashboard.css không còn min-width: 1180px cứng, hỗ trợ html[data-theme='dark']."""
        dash_css_path = self.static_dir / "dashboard.css"
        self.assertTrue(dash_css_path.exists())
        with open(dash_css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertNotIn("min-width: 1180px", css)
        self.assertIn("min-width: 320px", css)
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn(".hero-chat-cta", css)

    # ==========================================================================
    # 3. CHAT EXPERIENCE V3
    # ==========================================================================
    def test_07_chat_ai_thinking_state(self):
        """static/chat.js render thinking state với pulse indicator y tế và typing-dots tương thích."""
        chat_js_path = self.static_dir / "chat.js"
        self.assertTrue(chat_js_path.exists())
        with open(chat_js_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn("ai-thinking-indicator", js)
        self.assertIn("medical-pulse-dot", js)
        self.assertIn("MediCare AI đang phân tích dữ liệu y tế...", js)
        self.assertIn("typing-dots", js)

    def test_08_chat_css_ambient_glow_and_sticky_composer(self):
        """static/chat.css chứa ambient medical glow và mobile sticky composer."""
        chat_css_path = self.static_dir / "chat.css"
        self.assertTrue(chat_css_path.exists())
        with open(chat_css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn(".ai-thinking-bubble", css)
        self.assertIn(".medical-pulse-dot", css)
        self.assertIn("@keyframes medicalPulse", css)
        self.assertIn("safe-area-inset-bottom", css)
        self.assertIn(".consultation-shell", css)


if __name__ == "__main__":
    unittest.main()
