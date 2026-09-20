# -*- coding: utf-8 -*-
"""
MediCare AI - APEX MAXIMUM 100 MASTER VERIFICATION SUITE
Comprehensive regression test suite auditing 100% of user-facing routes,
design system tokens, canonical material surfaces, cinematic engine states,
zero legacy UI remnants, accessibility, and error handling.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(r"E:\AI.CHATBOT\Workshop1")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Mock database connection for isolated test execution
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1

with patch("psycopg_pool.ConnectionPool"):
    import database
    database.get_connection = MagicMock(return_value=mock_db_conn)
    import app as flask_app


class TestApexMaximum100Master(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = flask_app.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    # =========================================================================
    # 1. PUBLIC & CINEMATIC ENTRY ROUTES AUDIT
    # =========================================================================
    def test_01_public_landing_route(self):
        """Audit /landing: Returns landing.html with APEX Cinematic Entry elements."""
        resp = self.client.get("/landing")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("cinematicIntro", html)
        self.assertIn("intro-formation-stage", html)
        self.assertIn("heroMedicareCore", html)
        self.assertIn("Sức khỏe của bạn.", html)
        self.assertIn("Được hiểu theo thời gian.", html)

    def test_02_public_root_unauthenticated(self):
        """Audit / (guest): Renders landing.html for first-time visitors."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("cinematicIntro", html)
        self.assertIn("heroMedicareCore", html)

    def test_03_public_auth_routes(self):
        """Audit /login and /register: Renders auth.html with split screen and signature Core."""
        routes = ["/login", "/register"]
        for route in routes:
            with self.subTest(route=route):
                resp = self.client.get(route)
                self.assertEqual(resp.status_code, 200)
                html = resp.get_data(as_text=True)
                self.assertIn("auth-page", html)
                self.assertIn("auth-shell", html)
                self.assertIn("authVisualPanel", html)
                self.assertIn("authCardPanel", html)
                self.assertIn("authMedicareCore", html)

    # =========================================================================
    # 2. PRIVATE HEALTH OS STAGE ROUTES AUDIT
    # =========================================================================
    def test_04_private_root_authenticated(self):
        """Audit / (logged in): Renders index.html (Private Health OS Stage)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 99
            sess["user_email"] = "vip.patient@medicare.ai"
            sess["user_name"] = "BS. Hoàng Long"
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("page-personal-health-space", html)
        self.assertIn("medicareCore", html)
        self.assertIn("core-orbit-centerpiece", html)

    def test_05_private_dashboard_route(self):
        """Audit /dashboard: Renders Living Core and personal health orbit."""
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("page-personal-health-space", html)
        self.assertIn("medicareCore", html)
        self.assertIn("core-orbit-centerpiece", html)

    def test_06_private_workspace_chat_route(self):
        """Audit /tu-van: Renders Focused Medical Workspace with floating composer dock."""
        resp = self.client.get("/tu-van")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("chat-workspace", html)
        self.assertIn("historySidebar", html)
        self.assertIn("chatForm", html)
        self.assertIn("chatInput", html)

    def test_07_private_health_space_route(self):
        """Audit /suc-khoe-tien-ich: Renders Personal Health Space without legacy right rail."""
        resp = self.client.get("/suc-khoe-tien-ich")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("page-personal-health-space", html)
        self.assertIn("activeHealthIdentityModule", html)
        self.assertIn("compactFamilySwitcher", html)
        self.assertIn("healthSignalsBar", html)
        self.assertIn("healthSegmentedNav", html)
        # Verify 0 legacy UI remnants
        self.assertNotIn("health-context-rail", html)
        self.assertNotIn("add-family-card", html)
        self.assertNotIn(">-- cm<", html)
        self.assertNotIn(">-- kg<", html)

    def test_08_private_knowledge_route(self):
        """Audit /kien-thuc: Renders Medical Knowledge library with focal search and verified disclaimers."""
        resp = self.client.get("/kien-thuc")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("knowledgeSearch", html)
        self.assertIn("hero-quick-topics", html)
        self.assertIn("115", html)

    def test_09_private_health_news_route(self):
        """Audit /ban-tin-suc-khoe: Renders verified Health Editorial stream."""
        resp = self.client.get("/ban-tin-suc-khoe")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("news-public-shell", html)
        self.assertIn("newsPublicGrid", html)
        self.assertIn("TIN TỨC CHÍNH THỐNG ĐÃ KIỂM DUYỆT", html)

    def test_10_private_pharmacies_route(self):
        """Audit /nha-thuoc: Renders GPP Pharmacy Finder with GPS accuracy card."""
        resp = self.client.get("/nha-thuoc")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("map-shell", html)
        self.assertIn("location-status-card", html)
        self.assertIn("pharmacyMap", html)
        self.assertIn("googleMapFrame", html)

    # =========================================================================
    # 3. ADMIN CONSOLE SECURITY & ROUTE AUDIT
    # =========================================================================
    def test_11_admin_routes_unauthenticated_redirection(self):
        """Audit /admin sub-routes unauthenticated: Redirects safely with 302 to login."""
        admin_routes = [
            "/admin",
            "/admin/users",
            "/admin/chats",
            "/admin/news",
            "/admin/feedback",
        ]
        for route in admin_routes:
            with self.subTest(route=route):
                resp = self.client.get(route)
                self.assertEqual(resp.status_code, 302)

    # =========================================================================
    # 4. ERROR STATES & CONTENT NEGOTIATION AUDIT
    # =========================================================================
    def test_12_error_handlers_404(self):
        """Audit 404 handler: Returns error.html with 404 code and recovery actions."""
        resp = self.client.get("/non-existent-apex-path-404")
        self.assertEqual(resp.status_code, 404)
        html = resp.get_data(as_text=True)
        self.assertIn("404", html)
        self.assertIn("error-card", html)
        self.assertIn("error-actions", html)
        self.assertIn("error-emergency-strip", html)

    def test_13_error_handlers_content_negotiation(self):
        """Audit API error handler: Returns JSON for /api/ 404 requests."""
        resp = self.client.get("/api/non-existent-api-endpoint")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get("status"), 404)

    # =========================================================================
    # 5. MASTER DESIGN SYSTEM & CANONICAL MATERIAL SURFACES
    # =========================================================================
    def test_14_theme_css_canonical_surfaces(self):
        """Audit static/theme.css: Verifies all 6 Canonical Material Surfaces are defined."""
        theme_path = BASE_DIR / "static" / "theme.css"
        self.assertTrue(theme_path.exists())
        with open(theme_path, "r", encoding="utf-8") as f:
            css = f.read()

        # 6 Canonical Material Surfaces
        self.assertIn(".surface-ambient", css)
        self.assertIn(".surface-soft-solid", css)
        self.assertIn(".surface-frosted", css)
        self.assertIn(".surface-floating", css)
        self.assertIn(".surface-interactive", css)
        self.assertIn(".surface-critical", css)

        # Unified Button System
        self.assertIn(".btn-primary", css)
        self.assertIn(".btn-secondary", css)
        self.assertIn(".btn-ghost", css)
        self.assertIn(".btn-danger", css)
        self.assertIn(".btn-icon", css)

        # Form Controls
        self.assertIn(".input-field", css)
        self.assertIn(".textarea-field", css)
        self.assertIn(".select-field", css)

        # Reduced Motion Invariant
        self.assertIn("prefers-reduced-motion: reduce", css)

        # Command Palette
        self.assertIn(".cmd-palette-backdrop", css)
        self.assertIn(".cmd-palette-modal", css)

    # =========================================================================
    # 6. CINEMATIC GRAPHICS ENGINE AUDIT
    # =========================================================================
    def test_15_cinematic_engine_architecture(self):
        """Audit static/cinematic_engine.js: Verifies 8 Core states and performance tiers."""
        engine_path = BASE_DIR / "static" / "cinematic_engine.js"
        self.assertTrue(engine_path.exists())
        with open(engine_path, "r", encoding="utf-8") as f:
            js = f.read()

        # 8 Core States
        for state in [
            "IDLE",
            "LISTENING",
            "PROCESSING",
            "RESPONDING",
            "SUCCESS",
            "CAUTION",
            "URGENT",
            "EMERGENCY",
        ]:
            self.assertIn(state, js)

        # Performance tiers
        self.assertIn("BALANCED", js)
        self.assertIn("HIGH", js)

        # Device Pixel Ratio and Resource Lifecycle
        self.assertIn("devicePixelRatio", js)
        self.assertIn("cancelAnimationFrame", js)

    # =========================================================================
    # 7. ZERO LEGACY UI INVARIANTS
    # =========================================================================
    def test_16_zero_legacy_css_rail_grid(self):
        """Audit static/health_utilities.css: Verifies elimination of 340px fixed rail."""
        hu_css_path = BASE_DIR / "static" / "health_utilities.css"
        with open(hu_css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertNotIn("340px", css)
        self.assertNotIn(".health-context-rail", css)
        self.assertNotIn(".emergency-floating", css)

    # =========================================================================
    # 8. COMMON SYSTEM UI AUDIT
    # =========================================================================
    def test_17_common_js_system_components(self):
        """Audit static/common.js: Verifies Command Palette (Ctrl+K), Toast, and Settings."""
        common_path = BASE_DIR / "static" / "common.js"
        with open(common_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn("initCommandPalette", js)
        self.assertIn("cmdPaletteBackdrop", js)
        self.assertIn("showToast", js)
        self.assertIn("globalToast", js)
        self.assertIn("applyTheme", js)


if __name__ == "__main__":
    unittest.main()
