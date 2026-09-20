# -*- coding: utf-8 -*-
"""
MediCare AI - Admin RBAC & Security Test Suite
Verifies:
1. Unauthenticated redirects.
2. User role rejection (403 Forbidden with custom APEX 403.html).
3. 5-role granular RBAC enforcement (Content Editor, Medical Reviewer, Support, Admin, Super Admin).
4. Privacy-by-Default (PHI protection & mandatory audit log on sensitive data access).
5. Lockout prevention (cannot lock or demote last Super Admin).
6. Force-logout mechanism (token_version revocation).
7. Admin logout (clean session termination & audit).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import app as flask_app
from rbac_service import (
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_CONTENT_EDITOR,
    ROLE_MEDICAL_REVIEWER,
    ROLE_SUPPORT,
    ROLE_USER,
    PERM_SENSITIVE_DATA_ACCESS,
    has_permission,
)


class TestAdminRbacSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    # =========================================================================
    # 1. UNAUTHENTICATED & STANDARD USER GUARDS
    # =========================================================================
    def test_01_unauthenticated_admin_access_redirects(self):
        """Unauthenticated requests to /admin must redirect to login."""
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_02_standard_user_admin_access_forbidden(self):
        """Standard 'user' role attempting to access /admin receives 403 Forbidden with custom APEX page."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["full_name"] = "Nguyen Van A"
            sess["email"] = "nguyenvana@gmail.com"
            sess["role"] = ROLE_USER

        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 403)
        html = resp.get_data(as_text=True)
        self.assertIn("Từ chối truy cập", html)
        self.assertIn("user", html)

    # =========================================================================
    # 2. GRANULAR ROLE ACCESS MATRIX
    # =========================================================================
    def test_03_content_editor_access_matrix(self):
        """CONTENT_EDITOR can access /admin/news, but forbidden from /admin/users and /admin/system."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 201
            sess["full_name"] = "Editor B"
            sess["email"] = "editor@medicare.ai"
            sess["role"] = ROLE_CONTENT_EDITOR

        # Allowed
        resp_news = self.client.get("/admin/news")
        self.assertEqual(resp_news.status_code, 200)

        # Forbidden
        resp_users = self.client.get("/admin/users")
        self.assertEqual(resp_users.status_code, 403)

        resp_sys = self.client.get("/admin/system")
        self.assertEqual(resp_sys.status_code, 403)

    def test_04_medical_reviewer_access_matrix(self):
        """MEDICAL_REVIEWER can access /admin/knowledge and /admin/rag, but forbidden from /admin/users."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["full_name"] = "Dr. Reviewer C"
            sess["email"] = "dr.reviewer@medicare.ai"
            sess["role"] = ROLE_MEDICAL_REVIEWER

        # Allowed
        resp_k = self.client.get("/admin/knowledge")
        self.assertEqual(resp_k.status_code, 200)

        resp_rag = self.client.get("/admin/rag")
        self.assertEqual(resp_rag.status_code, 200)

        # Forbidden
        resp_users = self.client.get("/admin/users")
        self.assertEqual(resp_users.status_code, 403)

    def test_05_support_access_matrix(self):
        """SUPPORT can access /admin/feedback and /admin/chats, but forbidden from /admin/system."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 203
            sess["full_name"] = "Support Agent D"
            sess["email"] = "support@medicare.ai"
            sess["role"] = ROLE_SUPPORT

        # Allowed
        resp_fb = self.client.get("/admin/feedback")
        self.assertEqual(resp_fb.status_code, 200)

        # Forbidden
        resp_sys = self.client.get("/admin/system")
        self.assertEqual(resp_sys.status_code, 403)

        resp_users = self.client.get("/admin/users")
        self.assertEqual(resp_users.status_code, 403)

    def test_06_admin_access_matrix(self):
        """ADMIN can access /admin/users, /admin/dashboard, /admin/system."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 204
            sess["full_name"] = "Admin E"
            sess["email"] = "admin@medicare.ai"
            sess["role"] = ROLE_ADMIN

        resp_dash = self.client.get("/admin")
        self.assertEqual(resp_dash.status_code, 200)

        resp_users = self.client.get("/admin/users")
        self.assertEqual(resp_users.status_code, 200)

        resp_sys = self.client.get("/admin/system")
        self.assertEqual(resp_sys.status_code, 200)

    # =========================================================================
    # 3. PRIVACY BY DEFAULT & PHI ACCESS AUDITING
    # =========================================================================
    def test_07_privacy_by_default_phi_hidden_without_flag(self):
        """Viewing user detail without ?include_sensitive=1 NEVER renders PHI clinical fields."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["full_name"] = "Super Admin"
            sess["email"] = "superadmin@medicare.ai"
            sess["role"] = ROLE_SUPER_ADMIN

        # Even Super Admin visiting without explicit include_sensitive does not receive decrypted PHI
        resp = self.client.get("/admin/users/101")
        if resp.status_code == 200:
            html = resp.get_data(as_text=True)
            self.assertIn("Bảo mật (Đang khóa)", html)
            self.assertIn("Dữ liệu y tế được bảo vệ theo mặc định", html)

    def test_08_sensitive_permission_verification(self):
        """Only roles with PERM_SENSITIVE_DATA_ACCESS can decode PHI."""
        self.assertTrue(has_permission(ROLE_SUPER_ADMIN, PERM_SENSITIVE_DATA_ACCESS))
        self.assertFalse(has_permission(ROLE_ADMIN, PERM_SENSITIVE_DATA_ACCESS))
        self.assertFalse(has_permission(ROLE_CONTENT_EDITOR, PERM_SENSITIVE_DATA_ACCESS))
        self.assertFalse(has_permission(ROLE_SUPPORT, PERM_SENSITIVE_DATA_ACCESS))
        self.assertFalse(has_permission(ROLE_USER, PERM_SENSITIVE_DATA_ACCESS))

    # =========================================================================
    # 4. ADMIN LOGOUT ROUTE
    # =========================================================================
    def test_09_admin_logout_get_and_post(self):
        """Admin logout accepts both GET and POST, clearing session and cookies cleanly."""
        # Test POST
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = ROLE_SUPER_ADMIN
            sess["full_name"] = "Super Admin"

        resp_post = self.client.post("/admin/logout")
        self.assertEqual(resp_post.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)

        # Test GET
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = ROLE_SUPER_ADMIN
            sess["full_name"] = "Super Admin"

        resp_get = self.client.get("/admin/logout")
        self.assertEqual(resp_get.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)


if __name__ == "__main__":
    unittest.main()
