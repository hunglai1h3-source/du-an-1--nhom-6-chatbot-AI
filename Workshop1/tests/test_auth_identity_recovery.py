# -*- coding: utf-8 -*-
"""
MediCare AI - Auth Identity Recovery Tests
Verifies that:
1. Two-identity separation is enforced (Account User vs Active Health Profile).
2. Server-Side Hydration First renders user identity directly in DOM.
3. Authenticated sessions never silently fallback to "Khách".
4. /current-user gracefully falls back to session metadata on database error.
5. /logout supports both GET and POST, clearing session cleanly.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Mock database connection for test isolation
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1

with patch("psycopg_pool.ConnectionPool"):
    import database
    database.get_connection = MagicMock(return_value=mock_db_conn)
    import app as flask_app


class TestAuthIdentityRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    # =========================================================================
    # 1. SERVER-SIDE HYDRATION & CONTEXT PROCESSOR AUDIT
    # =========================================================================
    def test_01_unauthenticated_landing_page(self):
        """Unauthenticated user visiting / receives public landing page with no account identity."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("heroMedicareCore", html)
        self.assertNotIn("Chào LAI HOANG PHI HUNG", html)

    def test_02_authenticated_home_server_side_hydration(self):
        """Authenticated user visiting / gets index.html with real account identity directly in DOM."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "LAI HOANG PHI HUNG"
            sess["email"] = "hunglai@example.com"
            sess["role"] = "user"

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # 1. Welcome greeting renders real name, not "Khách"
        self.assertIn('Chào <span id="welcomeName">LAI HOANG PHI HUNG</span>.', html)
        self.assertNotIn('Chào <span id="welcomeName">Khách</span>.', html)

        # 2. Header account pill renders real name and initial
        self.assertIn('id="accountName" data-account-name>LAI HOANG PHI HUNG</span>', html)
        self.assertIn('id="accountAvatar">L</span>', html)
        self.assertNotIn('id="accountName" data-account-name>Khách</span>', html)

        # 3. Rail avatar renders initial
        self.assertIn('id="railUserAvatar" title="Hồ sơ">L</div>', html)

    def test_03_authenticated_chat_workspace_hydration(self):
        """Authenticated user on /tu-van gets account user in header, separate from consultation chip."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "LAI HOANG PHI HUNG"
            sess["email"] = "hunglai@example.com"
            sess["role"] = "user"

        resp = self.client.get("/tu-van")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Header account button has account user identity
        self.assertIn('id="accountAvatar">L</span>', html)
        self.assertIn('id="accountName" data-account-name>LAI HOANG PHI HUNG</strong>', html)

        # Center consultation chip retains its independent profile binding
        self.assertIn('id="selectedProfileName"', html)
        self.assertIn('id="selectedProfileAvatar"', html)

    def test_04_authenticated_health_utilities_hydration(self):
        """Authenticated user on /suc-khoe-tien-ich gets server-hydrated account identity."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "LAI HOANG PHI HUNG"
            sess["email"] = "hunglai@example.com"

        resp = self.client.get("/suc-khoe-tien-ich")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn('id="accountAvatar">L</span>', html)
        self.assertIn('id="accountName" data-account-name>LAI HOANG PHI HUNG</strong>', html)
        self.assertIn('id="welcomeName">LAI HOANG PHI HUNG</span>', html)

    def test_05_authenticated_knowledge_and_pharmacies_hydration(self):
        """Authenticated user on /kien-thuc and /nha-thuoc receives server-hydrated account identity."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "BS. Hoàng Long"
            sess["email"] = "hoanglong@medicare.ai"

        # 1. Knowledge
        resp_k = self.client.get("/kien-thuc")
        self.assertEqual(resp_k.status_code, 200)
        html_k = resp_k.get_data(as_text=True)
        self.assertIn('id="accountAvatar">B</span>', html_k)
        self.assertIn('id="accountName" data-account-name>BS. Hoàng Long</strong>', html_k)

        # 2. Pharmacies
        resp_p = self.client.get("/nha-thuoc")
        self.assertEqual(resp_p.status_code, 200)
        html_p = resp_p.get_data(as_text=True)
        self.assertIn('id="accountAvatar">B</span>', html_p)
        self.assertIn('id="accountName" data-account-name>BS. Hoàng Long</strong>', html_p)

    # =========================================================================
    # 2. CURRENT-USER RESILIENCE AUDIT
    # =========================================================================
    def test_06_current_user_unauthenticated(self):
        """Unauthenticated /current-user returns logged_in: False."""
        resp = self.client.get("/current-user")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data.get("logged_in"))

    def test_07_current_user_db_error_fallback_to_session(self):
        """If database throws an error during /current-user, session metadata preserves login state."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 99
            sess["full_name"] = "Tran Thi Mai"
            sess["email"] = "mai.tran@example.com"
            sess["role"] = "user"

        with patch.object(flask_app, "get_database", side_effect=Exception("DB connection timeout")):
            resp = self.client.get("/current-user")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("logged_in"))
            self.assertEqual(data.get("user", {}).get("full_name"), "Tran Thi Mai")
            self.assertEqual(data.get("user", {}).get("email"), "mai.tran@example.com")

    # =========================================================================
    # 3. LOGOUT CONTROLS AUDIT
    # =========================================================================
    def test_08_logout_post(self):
        """POST /logout clears session and returns success JSON."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "LAI HOANG PHI HUNG"

        resp = self.client.post("/logout")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("Đăng xuất thành công", data.get("message", ""))

        # Verify session is cleared
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    def test_09_logout_get_redirects_to_landing(self):
        """GET /logout clears session and redirects with 302 to landing page."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 42
            sess["full_name"] = "LAI HOANG PHI HUNG"

        resp = self.client.get("/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.location.endswith("/landing") or resp.location == "/landing")

        # Verify session is cleared
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("user_id"))

    # =========================================================================
    # 4. USER_NAME FALLBACK AUDIT
    # =========================================================================
    def test_10_user_name_key_fallback(self):
        """If session has user_name instead of full_name, context processor correctly extracts it."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "BS. Nguyen Van B"
            sess["user_email"] = "doctor.b@medicare.ai"

        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Chào <span id="welcomeName">BS. Nguyen Van B</span>.', html)
        self.assertIn('id="accountName" data-account-name>BS. Nguyen Van B</span>', html)
        self.assertIn('id="accountAvatar">B</span>', html)


if __name__ == "__main__":
    unittest.main()
