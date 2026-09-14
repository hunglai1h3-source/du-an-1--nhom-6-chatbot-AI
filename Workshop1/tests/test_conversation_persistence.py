"""
Unit and Integration Tests for Phase 3: Conversation Persistence & Long-Term Context Memory.
"""
import unittest
import json
import sqlite3
from unittest.mock import patch, MagicMock

import database

# Mock database connection before importing app
mock_conn = MagicMock()
mock_conn.execute.return_value.fetchone.return_value = None
mock_conn.execute.return_value.fetchall.return_value = []
mock_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_conn)

from app import app
from conversation_engine import MedicalConversationState, ConversationStage, NextAction
from conversation_repository import (
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
    update_conversation_summary,
    get_conversation_summary,
    update_conversation_activity,
    delete_conversation,
    clear_conversation_messages,
    save_message,
    get_conversation_messages,
    get_recent_messages,
    verify_conversation_ownership,
)
from conversation_memory import (
    should_update_summary,
    generate_structured_summary,
    build_conversation_context,
    MAX_RECENT_MESSAGES_FOR_PROMPT,
)


def create_in_memory_db():
    """Tạo một in-memory SQLite database mô phỏng cho conversation persistence."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            title TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
            profile_id TEXT,
            summary TEXT,
            turn_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            client_message_id TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            conversation_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question TEXT NOT NULL,
            answer TEXT,
            model TEXT,
            has_image INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'success',
            error_message TEXT,
            profile_type TEXT,
            profile_ref TEXT,
            profile_name TEXT,
            feedback_rating TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


class DbConnectionWrapper:
    """Wrapper cho SQLite connection trong test giúp app.py gọi .close() mà không ngắt in-memory DB."""
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self.lastrowid = None

    def execute(self, sql, params=None):
        cursor = self._conn.execute(sql, tuple(params or ()))
        self.lastrowid = cursor.lastrowid
        return cursor

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # Giữ kết nối in-memory mở giữa các request trong test
        pass


class TestConversationPersistence(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self.db = create_in_memory_db()
        self.db_wrapper = DbConnectionWrapper(self.db)

    def tearDown(self):
        self.db.close()

    def test_01_conversation_creation_and_retrieval(self):
        """1. Tạo conversation mới và truy xuất lại thông tin."""
        conv = create_conversation(
            self.db,
            conversation_id="conv_test_01",
            user_id=10,
            title="Tư vấn đau họng",
            profile_id="self-10",
        )
        self.db.commit()

        self.assertEqual(conv["id"], "conv_test_01")
        self.assertEqual(conv["user_id"], 10)
        self.assertEqual(conv["title"], "Tư vấn đau họng")

        fetched = get_conversation(self.db, "conv_test_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], "conv_test_01")
        self.assertEqual(fetched["user_id"], 10)
        self.assertEqual(fetched["title"], "Tư vấn đau họng")
        self.assertEqual(fetched["profile_id"], "self-10")

    def test_02_ownership_verification_user_isolation(self):
        """2. Xác thực quyền sở hữu: User B không thể truy cập conversation của User A."""
        create_conversation(
            self.db,
            conversation_id="conv_user_a",
            user_id=1,
            title="Khám của User A",
        )
        self.db.commit()

        # User A truy cập -> Cho phép
        ok_a, conv_a = verify_conversation_ownership(self.db, "conv_user_a", user_id=1)
        self.assertTrue(ok_a)
        self.assertIsNotNone(conv_a)

        # User B truy cập -> Bị từ chối
        ok_b, conv_b = verify_conversation_ownership(self.db, "conv_user_a", user_id=2)
        self.assertFalse(ok_b)

        # Guest conversation (user_id IS NULL) -> Cho phép
        create_conversation(
            self.db,
            conversation_id="conv_guest",
            user_id=None,
            title="Khách vãng lai",
        )
        self.db.commit()
        ok_guest, _ = verify_conversation_ownership(self.db, "conv_guest", user_id=None)
        self.assertTrue(ok_guest)

    def test_03_message_persistence_and_chronological_ordering(self):
        """3. Lưu tin nhắn và kiểm tra thứ tự thời gian tăng dần."""
        create_conversation(self.db, conversation_id="conv_msg_test", user_id=1)
        self.db.commit()

        save_message(self.db, "conv_msg_test", "user", "Tin 1: Tôi bị sốt")
        save_message(self.db, "conv_msg_test", "assistant", "Tin 2: Bạn sốt bao nhiêu độ?")
        save_message(self.db, "conv_msg_test", "user", "Tin 3: Khoảng 38.5 độ")
        self.db.commit()

        messages = get_conversation_messages(self.db, "conv_msg_test")
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "Tin 1: Tôi bị sốt")
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["content"], "Tin 2: Bạn sốt bao nhiêu độ?")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "Tin 3: Khoảng 38.5 độ")

    def test_04_idempotent_message_deduplication(self):
        """4. Idempotency: Không lưu trùng tin nhắn khi gửi lặp lại cùng client_message_id."""
        create_conversation(self.db, conversation_id="conv_dedup", user_id=1)
        self.db.commit()

        # Gửi lần 1
        msg1 = save_message(
            self.db,
            "conv_dedup",
            "user",
            "Tôi bị đau đầu",
            client_message_id="client_uuid_abc_123",
        )
        self.db.commit()

        # Gửi lần 2 (network retry) cùng client_message_id
        msg2 = save_message(
            self.db,
            "conv_dedup",
            "user",
            "Tôi bị đau đầu",
            client_message_id="client_uuid_abc_123",
        )
        self.db.commit()

        messages = get_conversation_messages(self.db, "conv_dedup")
        self.assertEqual(len(messages), 1)
        self.assertEqual(msg1["content"], msg2["content"])

    def test_05_long_term_context_memory_building(self):
        """5. Long-term Context Memory: Kiểm tra rolling summarization và xây dựng context cân bằng."""
        # Ngưỡng kích hoạt summary
        self.assertFalse(should_update_summary(turn_count=2, total_message_count=4))
        self.assertTrue(should_update_summary(turn_count=6, total_message_count=12, has_summary=False))

        # Tóm tắt hội thoại
        test_turns = [
            {"role": "user", "content": "Tôi bị đau bụng dưới bên phải 3 ngày rồi"},
            {"role": "assistant", "content": "Bạn hãy theo dõi thêm, nếu đau quặn dữ dội cần đi khám sớm"},
            {"role": "user", "content": "Đau khoảng 6/10, hôm nay có sốt nhẹ"},
            {"role": "assistant", "content": "Lưu ý uống nhiều nước và nghỉ ngơi"},
        ]
        summary = generate_structured_summary(test_turns)
        self.assertIn("đau bụng", summary.lower())
        self.assertIn("theo dõi", summary.lower())

        # Xây dựng balanced context cho Gemini
        state = MedicalConversationState(conversation_id="c1", user_id=1)
        state.slots.chief_complaint = "đau bụng dưới"
        recent = [
            {"role": "user", "content": f"Câu hỏi thứ {i}"}
            for i in range(15)
        ]
        prompts = build_conversation_context(state=state, summary=summary, recent_messages=recent)

        # Đảm bảo có State prompt, Summary prompt, và Recent messages bị giới hạn tối đa MAX_RECENT_MESSAGES_FOR_PROMPT
        has_state_prompt = any("đau bụng dưới" in p["content"] for p in prompts if p["role"] == "system")
        has_summary_prompt = any("TÓM TẮT DIỄN BIẾN" in p["content"] for p in prompts if p["role"] == "system")
        recent_count = sum(1 for p in prompts if p["role"] == "user")

        self.assertTrue(has_state_prompt)
        self.assertTrue(has_summary_prompt)
        self.assertLessEqual(recent_count, MAX_RECENT_MESSAGES_FOR_PROMPT)

    def test_06_clear_conversation_messages_and_state(self):
        """6. Xóa tin nhắn trong cuộc trò chuyện nhưng giữ lại bản ghi conversation."""
        create_conversation(self.db, "conv_clear_test", user_id=1, title="Hội thoại cần xóa")
        save_message(self.db, "conv_clear_test", "user", "Tin 1")
        save_message(self.db, "conv_clear_test", "assistant", "Tin 2")
        update_conversation_summary(self.db, "conv_clear_test", "Tóm tắt cũ")
        self.db.commit()

        cleared = clear_conversation_messages(self.db, "conv_clear_test", user_id=1)
        self.db.commit()
        self.assertTrue(cleared)

        # Tin nhắn đã sạch
        msgs = get_conversation_messages(self.db, "conv_clear_test")
        self.assertEqual(len(msgs), 0)

        # Conversation record vẫn còn với summary = None
        conv = get_conversation(self.db, "conv_clear_test")
        self.assertIsNotNone(conv)
        self.assertEqual(conv["summary"], "")
        self.assertEqual(conv["turn_count"], 0)

    def test_07_delete_conversation_cascades(self):
        """7. Xóa conversation -> xóa sạch bản ghi và toàn bộ tin nhắn liên quan."""
        create_conversation(self.db, "conv_delete_test", user_id=1)
        save_message(self.db, "conv_delete_test", "user", "Tin nhắn trước khi xóa")
        self.db.commit()

        deleted = delete_conversation(self.db, "conv_delete_test", user_id=1)
        self.db.commit()
        self.assertTrue(deleted)

        self.assertIsNone(get_conversation(self.db, "conv_delete_test"))
        self.assertEqual(len(get_conversation_messages(self.db, "conv_delete_test")), 0)

    def test_08_api_conversations_ownership_enforcement(self):
        """8. REST API /api/conversations kiểm tra quyền sở hữu chính xác."""
        with patch("app.get_database", return_value=self.db_wrapper):
            # Tạo conversation thuộc user 1
            create_conversation(self.db, "conv_user_1", user_id=1, title="Chat của User 1")
            save_message(self.db, "conv_user_1", "user", "Bí mật y tế của user 1")
            self.db.commit()

            # User 2 đăng nhập cố tình đọc tin nhắn của User 1 -> 403 Forbidden
            with self.client.session_transaction() as sess:
                sess["user_id"] = 2

            res = self.client.get("/api/conversations/conv_user_1/messages")
            self.assertEqual(res.status_code, 403)

            # User 2 cố xóa tin nhắn của User 1 -> 403 Forbidden
            res_delete = self.client.delete("/api/conversations/conv_user_1")
            self.assertEqual(res_delete.status_code, 403)

            # User 2 cố clear conversation của User 1 -> 403 Forbidden
            res_clear = self.client.post("/api/conversations/conv_user_1/clear")
            self.assertEqual(res_clear.status_code, 403)

            # User 1 đăng nhập đọc tin nhắn -> 200 OK
            with self.client.session_transaction() as sess:
                sess["user_id"] = 1

            res_owner = self.client.get("/api/conversations/conv_user_1/messages")
            self.assertEqual(res_owner.status_code, 200)
            data = res_owner.get_json()
            self.assertEqual(len(data["messages"]), 1)
            self.assertEqual(data["messages"][0]["content"], "Bí mật y tế của user 1")

    def test_09_chat_endpoint_emergency_persistence(self):
        """9. Tin nhắn EMERGENCY ngắt luồng nhưng vẫn được lưu vào PostgreSQL."""
        with patch("app.get_database", return_value=self.db_wrapper):
            res = self.client.post(
                "/chat",
                data={
                    "message": "Tôi đau ngực dữ dội và không thở nổi",
                    "conversation_id": "conv_emergency_test",
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("fast_path"))
            self.assertEqual(data.get("conversation_id"), "conv_emergency_test")

            # Kiểm tra tin nhắn đã được lưu vào DB
            messages = get_conversation_messages(self.db, "conv_emergency_test")
            self.assertGreaterEqual(len(messages), 1)
            self.assertEqual(messages[0]["role"], "user")
            self.assertIn("đau ngực dữ dội", messages[0]["content"])

    def test_10_database_failure_resilience(self):
        """10. Khả năng chống chịu lỗi: Khi DB gặp sự cố, các hàm repository không crash."""
        bad_conn = MagicMock()
        bad_conn.execute.side_effect = RuntimeError("DB connection lost")

        # Không ném Exception làm crash ứng dụng
        self.assertIsNone(get_conversation(bad_conn, "c1"))
        self.assertEqual(list_conversations(bad_conn, 1), [])
        self.assertFalse(update_conversation_title(bad_conn, "c1", "title"))
        self.assertFalse(delete_conversation(bad_conn, "c1", 1))
        self.assertFalse(clear_conversation_messages(bad_conn, "c1", 1))
        self.assertEqual(get_conversation_messages(bad_conn, "c1"), [])
        self.assertEqual(get_recent_messages(bad_conn, "c1"), [])


if __name__ == "__main__":
    unittest.main()
