import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(r"E:\AI.CHATBOT\Workshop1")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Mock database connection for test suite
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1

with patch("psycopg_pool.ConnectionPool"):
    import database
    database.get_connection = MagicMock(return_value=mock_db_conn)
    import app as flask_app


class TestCinematicEntrySystem(unittest.TestCase):
    """
    Comprehensive Verification Suite for MEDICARE AI Cinematic Entry System (APEX Version)
    Covers Intro, Landing, Living Core, Auth (Login/Register), Route Protection, and Session Continuity.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.static_dir = BASE_DIR / "static"
        cls.templates_dir = BASE_DIR / "templates"

    def setUp(self):
        flask_app.rate_limiter.reset()
        flask_app.brute_force_protector.reset()
        mock_db_conn.execute.return_value.fetchone.return_value = None

    def test_01_cinematic_intro_and_landing_hero(self):
        """Khách chưa đăng nhập vào GET / thấy Cinematic Intro và Hero với signature MEDICARE Core."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        # Cinematic Intro elements
        self.assertIn('id="cinematicIntro"', html)
        self.assertIn("Hiểu bạn. Theo dõi bạn. Đồng hành cùng bạn.", html)
        self.assertIn('id="introSkipBtn"', html)
        # Hero with Living MEDICARE Core
        self.assertIn("medicare-core-v2", html)
        self.assertIn('id="heroMedicareCore"', html)
        self.assertIn("Sức khỏe của bạn.", html)
        self.assertIn("Được hiểu theo thời gian.", html)
        self.assertIn('id="landingCanvas"', html)

    def test_02_landing_scroll_storytelling_scenes(self):
        """Landing page đầy đủ 6 Scene kể chuyện y tế và không gian gia đình."""
        res = self.client.get("/landing")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        # Scene 01 to 06
        self.assertIn("SCENE 02 — ĐỒNG HÀNH", html)
        self.assertIn("Intake Engine", html)
        self.assertIn("SCENE 03 — AN TOÀN", html)
        self.assertIn("Medical Safety Guard V2", html)
        self.assertIn("SCENE 04 — ĐÁNG TIN", html)
        self.assertIn("Medical RAG Evidence Verification", html)
        self.assertIn("SCENE 05 — CÁ NHÂN HÓA", html)
        self.assertIn("family-member-card", html)
        self.assertIn("landing-cta-banner", html)

    def test_03_cinematic_auth_split_layout_and_core(self):
        """GET /login và /register render kiến trúc Split 60/40 với Living Core và Transition Stage."""
        for path in ["/login", "/register"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            html = res.data.decode("utf-8")
            # 60% Visual Zone with Core
            self.assertIn("auth-cinematic-panel", html)
            self.assertIn("auth-signature-core", html)
            self.assertIn('id="healthCanvas"', html)
            # 40% Auth Zone
            self.assertIn("auth-card-panel", html)
            self.assertIn('id="tabLoginBtn"', html)
            self.assertIn('id="tabRegisterBtn"', html)
            self.assertIn('id="loginForm"', html)
            self.assertIn('id="registerForm"', html)
            # Signature Login-Success Transition Stage
            self.assertIn('id="loginSuccessStage"', html)
            self.assertIn("transition-orb", html)

    def test_04_private_route_protection_guard(self):
        """Route /dashboard bắt buộc xác thực, chuyển hướng 302 về /login."""
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_05_authenticated_session_continuity(self):
        """Khi có phiên đăng nhập, GET / phục vụ thẳng Health OS index.html và /current-user trả logged_in."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999
            sess["full_name"] = "BS. Nguyen Van Test"
            sess["email"] = "testuser@medicare.ai"
            sess["role"] = "user"

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        # Renders Private Health OS
        self.assertIn("personal-health-space", html)
        self.assertIn("medicareCore", html)

    def test_06_login_validation_and_rejection(self):
        """POST /login từ chối dữ liệu thiếu hoặc không hợp lệ."""
        # Empty payload
        res = self.client.post("/login", json={})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("error", data)

        # Invalid credentials
        res = self.client.post("/login", json={"account": "unknown@test.vn", "password": "wrong_password_123"})
        self.assertIn(res.status_code, [401, 429])

    def test_07_register_validation_and_rejection(self):
        """POST /register kiểm tra chặt chẽ họ tên, định dạng email và độ dài mật khẩu."""
        # Short name
        res = self.client.post("/register", json={"full_name": "A", "email": "a@test.vn", "password": "123"})
        self.assertEqual(res.status_code, 400)

        # Invalid email
        res = self.client.post("/register", json={"full_name": "Nguyen Van A", "email": "invalid-email", "password": "password123"})
        self.assertEqual(res.status_code, 400)

        # Short password (<8)
        res = self.client.post("/register", json={"full_name": "Nguyen Van A", "email": "valid@test.vn", "password": "short", "confirm_password": "short"})
        self.assertEqual(res.status_code, 400)

    def test_08_static_assets_integrity(self):
        """Toàn bộ file CSS/JS phục vụ Cinematic Entry System tồn tại và hợp lệ."""
        assets = [
            "cinematic_engine.js",
            "landing.css",
            "landing.js",
            "auth.css",
            "auth.js",
            "theme.css"
        ]
        for asset in assets:
            path = self.static_dir / asset
            self.assertTrue(path.exists(), f"Asset {asset} missing")
            self.assertGreater(path.stat().st_size, 500, f"Asset {asset} too small")


if __name__ == "__main__":
    unittest.main()
