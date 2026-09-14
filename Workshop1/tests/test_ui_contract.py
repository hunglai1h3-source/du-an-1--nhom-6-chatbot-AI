import os
import unittest
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestUIContract(unittest.TestCase):
    """Kiểm tra hợp đồng giao diện người dùng Phase 6 UI/UX V2."""

    def setUp(self):
        self.static_dir = os.path.join(BASE_DIR, "static")
        self.templates_dir = os.path.join(BASE_DIR, "templates")

    def test_dead_files_removed(self):
        """Xác nhận các file mồ côi (chat-v2.js, chat-v2.css) đã bị xóa bỏ."""
        self.assertFalse(os.path.exists(os.path.join(self.static_dir, "chat-v2.js")))
        self.assertFalse(os.path.exists(os.path.join(self.static_dir, "chat-v2.css")))

    def test_chat_html_elements(self):
        """Xác nhận templates/chat.html có đầy đủ cấu trúc UI/UX V2."""
        chat_html_path = os.path.join(self.templates_dir, "chat.html")
        self.assertTrue(os.path.exists(chat_html_path))
        with open(chat_html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Mobile navigation & Drawers
        self.assertIn('id="mobileMenuButton"', content)
        self.assertIn('id="mobileContextButton"', content)
        self.assertIn('id="historySidebar"', content)
        self.assertIn('id="contextSidebar"', content)
        self.assertIn('id="sidebarBackdrop"', content)
        self.assertIn('id="toggleContextButton"', content)

        # Composer & Char counter
        self.assertIn('id="charCounter"', content)
        self.assertIn('class="composer-input-wrap"', content)

        # Confirm Delete Modal
        self.assertIn('id="confirmDeleteModal"', content)
        self.assertIn('id="confirmDeleteTitle"', content)
        self.assertIn('id="confirmDeleteMessage"', content)
        self.assertIn('id="cancelConfirmDeleteButton"', content)
        self.assertIn('id="actionConfirmDeleteButton"', content)

    def test_chat_css_tokens_and_components(self):
        """Xác nhận static/chat.css chứa đầy đủ Design Tokens y tế và các component mới."""
        chat_css_path = os.path.join(self.static_dir, "chat.css")
        self.assertTrue(os.path.exists(chat_css_path))
        with open(chat_css_path, "r", encoding="utf-8") as f:
            css = f.read()

        # Design Tokens
        self.assertIn("--med-primary:", css)
        self.assertIn("--med-emergency-bg:", css)
        self.assertIn("--med-urgent-bg:", css)
        self.assertIn("--med-caution-bg:", css)
        self.assertIn('html[data-theme="dark"]', css)

        # Component Classes
        self.assertIn(".welcome-hero", css)
        self.assertIn(".starter-cards", css)
        self.assertIn(".starter-card", css)
        self.assertIn(".rag-sources-panel", css)
        self.assertIn(".rag-source-card", css)
        self.assertIn(".risk-notice", css)
        self.assertIn(".char-counter", css)
        self.assertIn(".history-skeleton", css)
        self.assertIn(".confirm-modal-card", css)
        self.assertIn(".table-wrap", css)

        # Responsive & Accessibility
        self.assertIn("@media (max-width: 980px)", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_chat_js_logic(self):
        """Xác nhận static/chat.js có đầy đủ logic renderer V2, RAG sources, modal, drawer."""
        chat_js_path = os.path.join(self.static_dir, "chat.js")
        self.assertTrue(os.path.exists(chat_js_path))
        with open(chat_js_path, "r", encoding="utf-8") as f:
            js = f.read()

        # Renderers
        self.assertIn("function renderWelcomeHero(", js)
        self.assertIn("function renderSources(", js)
        self.assertIn("function renderRiskNotice(", js)
        self.assertIn("function openConfirmModal(", js)

        # Markdown V2 syntax
        self.assertIn("table-wrap", js)
        self.assertIn("<blockquote>", js)
        self.assertIn("<pre><code", js)
        self.assertIn("chat-link", js)

        # Source grounding logic
        self.assertIn("Bệnh viện ĐKQT Vinmec", js)
        self.assertIn("VnExpress Sức Khỏe", js)
        self.assertIn("ViHealthQA Y Khoa", js)

        # Input disabled state
        self.assertIn('$("#sendButton").disabled = true;', js)
        self.assertIn('$("#chatInput").disabled = true;', js)

        # Mobile drawer listeners
        self.assertIn("mobile-open", js)

    def test_tu_van_route(self):
        """Xác nhận route /tu-van trả về mã 200 OK và chứa template đã nâng cấp."""
        import app as flask_app
        with flask_app.app.test_client() as client:
            res = client.get("/tu-van")
            self.assertEqual(res.status_code, 200)
            html = res.data.decode("utf-8")
            self.assertIn("MediCare AI", html)
            self.assertIn('id="confirmDeleteModal"', html)
            self.assertIn('id="charCounter"', html)
            self.assertIn('id="mobileMenuButton"', html)


if __name__ == "__main__":
    unittest.main()
