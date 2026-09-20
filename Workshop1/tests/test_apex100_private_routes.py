# -*- coding: utf-8 -*-
"""
MediCare AI - APEX 100 Private Routes Migration Tests
Verifies that all legacy elements have been eliminated and APEX Health OS
spatial architecture is in place across all private routes.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(r"E:\AI.CHATBOT\Workshop1")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Mock database connection for isolated test suite
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1

with patch("psycopg_pool.ConnectionPool"):
    import database
    database.get_connection = MagicMock(return_value=mock_db_conn)
    import app as flask_app


class TestApex100PrivateRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_health_utilities_legacy_elements_eliminated(self):
        """Kiểm tra /suc-khoe-tien-ich KHÔNG còn chứa bất kỳ legacy UI element nào."""
        response = self.client.get("/suc-khoe-tien-ich")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # 1. Zero 340px fixed right rail
        self.assertNotIn('class="health-context-rail"', html)
        self.assertNotIn('id="healthContextRail"', html)

        # 2. Zero floating legacy controls
        self.assertNotIn('class="emergency-floating"', html)
        self.assertNotIn('id="mcaiWidget"', html)

        # 3. Zero legacy giant add member card in template
        self.assertNotIn('class="add-family-card"', html)

        # 4. Zero fake metric placeholders
        self.assertNotIn('>-- cm<', html)
        self.assertNotIn('>-- kg<', html)

    def test_health_utilities_apex_elements_present(self):
        """Kiểm tra /suc-khoe-tien-ich chứa đầy đủ các phân hệ APEX Spatial Health Space."""
        response = self.client.get("/suc-khoe-tien-ich")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # 1. Body class & Ambient field
        self.assertIn("page-personal-health-space", html)
        self.assertIn("health-ambient-field", html)
        self.assertIn("ambient-glow-mesh", html)

        # 2. Active Health Identity Module
        self.assertIn('id="activeHealthIdentityModule"', html)
        self.assertIn('id="heroIdentityAvatar"', html)
        self.assertIn('id="heroIdentityName"', html)
        self.assertIn('class="identity-vitals-strip"', html)

        # 3. Compact Family Switcher
        self.assertIn('id="compactFamilySwitcher"', html)
        self.assertIn('id="compactFamilyPillList"', html)
        self.assertIn('id="compactAddMemberBtn"', html)

        # 4. Contextual Health Signals Bar
        self.assertIn('id="healthSignalsBar"', html)
        self.assertIn('id="signalReminderCard"', html)
        self.assertIn('id="signalEnvironmentCard"', html)
        self.assertIn("signal-support-card", html)

        # 5. APEX Segmented Navigation
        self.assertIn('id="healthSegmentedNav"', html)
        self.assertIn('data-section-target="family-health"', html)
        self.assertIn('data-section-target="symptom-tracking"', html)
        self.assertIn('data-section-target="health-metrics"', html)
        self.assertIn('data-section-target="health-report"', html)

        # 6. Real Data Fallbacks
        self.assertIn("Chưa cập nhật", html)
        self.assertIn("Không ghi nhận", html)

    def test_health_utilities_css_apex_architecture(self):
        """Kiểm tra static/health_utilities.css đã loại bỏ 340px grid và áp dụng spatial stage."""
        with open("static/health_utilities.css", "r", encoding="utf-8") as f:
            css = f.read()

        # Không còn định dạng 340px fixed rail
        self.assertNotIn("340px", css)
        self.assertNotIn("health-context-rail", css)
        self.assertNotIn("grid-template-columns: minmax(0, 1fr) 340px", css)

        # Chứa styling APEX
        self.assertIn(".personal-health-stage", css)
        self.assertIn(".health-identity-module", css)
        self.assertIn(".compact-family-switcher", css)
        self.assertIn(".health-signals-bar", css)
        self.assertIn(".health-segmented-nav", css)

        # Responsive & Retina
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("@media (min-width: 2560px)", css)

    def test_all_private_routes_status_code_and_contracts(self):
        """Kiểm tra tất cả private routes đều tải thành công với mã 200 hoặc redirect hợp lệ."""
        # 1. /tu-van
        r_chat = self.client.get("/tu-van")
        self.assertEqual(r_chat.status_code, 200)
        self.assertIn("app-nav-rail", r_chat.get_data(as_text=True))

        # 2. /suc-khoe-tien-ich
        r_util = self.client.get("/suc-khoe-tien-ich")
        self.assertEqual(r_util.status_code, 200)
        self.assertIn("page-personal-health-space", r_util.get_data(as_text=True))

        # 3. /ban-tin-suc-khoe
        r_news = self.client.get("/ban-tin-suc-khoe")
        self.assertEqual(r_news.status_code, 200)
        self.assertIn("app-nav-rail", r_news.get_data(as_text=True))

        # 4. /kien-thuc
        r_know = self.client.get("/kien-thuc")
        self.assertEqual(r_know.status_code, 200)
        self.assertIn("app-nav-rail", r_know.get_data(as_text=True))

        # 5. /nha-thuoc
        r_pharm = self.client.get("/nha-thuoc")
        self.assertEqual(r_pharm.status_code, 200)
        self.assertIn("app-nav-rail", r_pharm.get_data(as_text=True))

        # 6. /dashboard redirects to /login when unauthenticated
        r_dash = self.client.get("/dashboard")
        self.assertEqual(r_dash.status_code, 302)


if __name__ == "__main__":
    unittest.main()
