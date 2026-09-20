# -*- coding: utf-8 -*-
"""
MediCare AI - Admin Operations Test Suite
Verifies:
1. Admin Overview API (/admin/api/overview).
2. Admin Dashboard API (/admin/api/dashboard).
3. Admin Users API (/admin/api/users).
4. Admin Knowledge V2 APIs (/admin/api/knowledge/overview, documents, sources).
5. Admin RAG Operations API (/admin/api/rag/status).
6. Admin System Health API (/admin/api/system/health).
7. Admin Audit Logs API (/admin/api/audit-logs).
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import app as flask_app
from rbac_service import ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MEDICAL_REVIEWER


class TestAdminOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def _login_super_admin(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["full_name"] = "Super Admin"
            sess["email"] = "superadmin@medicare.ai"
            sess["role"] = ROLE_SUPER_ADMIN

    # =========================================================================
    # 1. OVERVIEW & DASHBOARD APIS
    # =========================================================================
    def test_01_api_overview(self):
        """Test /admin/api/overview returns system totals and health metadata."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("users", data)
        self.assertIn("chats", data)
        self.assertIn("news", data)
        self.assertIn("knowledge", data)
        self.assertIn("system", data)

    def test_02_api_dashboard(self):
        """Test /admin/api/dashboard returns real metrics for live frontend."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("stats", data)
        self.assertIn("chart", data)
        self.assertIn("recent_users", data)
        self.assertIn("recent_chats", data)
        self.assertIn("ai", data)

    # =========================================================================
    # 2. USERS API
    # =========================================================================
    def test_03_api_users(self):
        """Test /admin/api/users returns paginated list and role counts."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/users?per_page=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("counts", data)
        self.assertIn("super_admin", data["counts"])
        self.assertIn("admin", data["counts"])
        self.assertIn("user", data["counts"])

    # =========================================================================
    # 3. KNOWLEDGE V2 APIS
    # =========================================================================
    def test_04_api_knowledge_overview_and_docs(self):
        """Test Knowledge V2 endpoints: overview, documents, and sources."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 992
            sess["full_name"] = "Medical Reviewer"
            sess["email"] = "reviewer@medicare.ai"
            sess["role"] = ROLE_MEDICAL_REVIEWER

        resp_ov = self.client.get("/admin/api/knowledge/overview")
        self.assertEqual(resp_ov.status_code, 200)
        ov_data = resp_ov.get_json()
        self.assertTrue(ov_data.get("success"))
        self.assertIn("total_documents", ov_data)
        self.assertIn("tiers", ov_data)

        resp_docs = self.client.get("/admin/api/knowledge/documents?per_page=5")
        self.assertEqual(resp_docs.status_code, 200)
        docs_data = resp_docs.get_json()
        self.assertTrue(docs_data.get("success"))
        self.assertIn("items", docs_data)

        resp_src = self.client.get("/admin/api/knowledge/sources")
        self.assertEqual(resp_src.status_code, 200)
        src_data = resp_src.get_json()
        self.assertTrue(src_data.get("success"))
        self.assertIn("sources", src_data)

    # =========================================================================
    # 4. RAG OPERATIONS API
    # =========================================================================
    def test_05_api_rag_status(self):
        """Test /admin/api/rag/status returns real radar status."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/rag/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("active_engine", data)
        self.assertIn("v2", data)
        self.assertIn("features", data)
        self.assertTrue(data["features"]["authority_filter"])
        self.assertTrue(data["features"]["drug_recalls_guard"])

    # =========================================================================
    # 5. SYSTEM HEALTH API
    # =========================================================================
    def test_06_api_system_health(self):
        """Test /admin/api/system/health returns services status and safe env."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/system/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn(data.get("overall"), ["HEALTHY", "DEGRADED"])
        self.assertIn("database", data["services"])
        self.assertIn("ai_provider", data["services"])
        self.assertIn("knowledge_v2", data["services"])
        self.assertIn("safety_engine", data["services"])
        # Safe environment never reveals actual secrets
        self.assertIn("environment", data)
        self.assertNotIn("AIzaSy", str(data))

    # =========================================================================
    # 6. AUDIT LOGS API
    # =========================================================================
    def test_07_api_audit_logs(self):
        """Test /admin/api/audit-logs returns immutable audit records."""
        self._login_super_admin()
        resp = self.client.get("/admin/api/audit-logs?per_page=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("logs", data)
        self.assertIn("total", data)


if __name__ == "__main__":
    unittest.main()
