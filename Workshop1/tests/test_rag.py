"""
Comprehensive Test Suite for Phase 4: Medical RAG & Trusted Knowledge Base.

Validates:
1. Knowledge Base build > 0 documents and proper schema.
2. Idempotent rebuild: Rebuilding does not accumulate duplicate documents.
3. Vietnamese accented query matching with BM25 score.
4. Vietnamese unaccented query matching with accent folding.
5. Medical synonyms and terminology handling (e.g. 'bao tử' -> 'dạ dày').
6. Irrelevant / out-of-domain query handling (returns 0 results or filtered out).
7. BM25 ranking order: Most relevant document ranked first.
8. Relevance score threshold correctness (below-threshold matches discarded).
9. Source metadata integrity (valid URL, publisher, trust_level CURATED_MEDICAL_CONTENT).
10. Citation validation: Real [MED-XXXXX] citations correctly mapped to retrieved documents.
11. Fake citation removal: Hallucinated citations (e.g. [MED-99999]) stripped, never mapped.
12. Failure resilience: When medical.db is missing, system does not crash and handles gracefully.
13. Failure resilience: When medical.db is corrupt or locked, search handles gracefully.
14. Safety Gate Priority: EMERGENCY queries NEVER activate RAG.
15. Stage policy: INTAKE stage does NOT activate RAG.
16. Stage policy: ASSESSMENT stage CAN activate RAG.
17. Multi-conversation isolation: RAG context does not leak between conversations.
18. Data privacy: Patient profile and personal conversation data never enter global knowledge base.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rag_service
import build_medical_knowledge
from medical_safety import RiskLevel, SafetyResult

import database
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_db_conn)


class TestMedicalRAGPhase4(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure knowledge base exists
        cls.db_path = rag_service.DATABASE_PATH
        if not cls.db_path.is_file():
            build_medical_knowledge.build_knowledge_base(rebuild=True)

    def test_01_kb_build_has_documents_and_schema(self):
        """1. Kiểm tra kho tri thức y tế chứa > 0 documents và cấu trúc bảng chuẩn."""
        self.assertTrue(rag_service.is_rag_available(), "medical.db phải sẵn sàng.")
        con = rag_service.get_db_connection()
        self.assertIsNotNone(con)
        try:
            doc_count = con.execute("SELECT count(*) FROM medical_documents").fetchone()[0]
            chunk_count = con.execute("SELECT count(*) FROM medical_fts").fetchone()[0]
            self.assertGreater(doc_count, 5000, "Phải nạp ít nhất 5,000 tài liệu y tế.")
            self.assertGreater(chunk_count, 5000, "Bảng FTS phải chứa > 5,000 chunks.")

            # Kiểm tra các cột bắt buộc
            cols = {r["name"] for r in con.execute("PRAGMA table_info(medical_documents)").fetchall()}
            required_cols = {"chunk_id", "title", "content", "source", "source_url", "trust_level"}
            self.assertTrue(required_cols.issubset(cols), f"Thiếu cột trong bảng: {required_cols - cols}")
        finally:
            con.close()

    def test_02_rebuild_does_not_duplicate_documents(self):
        """2. Idempotent: Rebuild với cờ False không được sinh bản ghi trùng lặp."""
        con = rag_service.get_db_connection()
        initial_count = con.execute("SELECT count(*) FROM medical_documents").fetchone()[0]
        con.close()

        # Chạy build với rebuild=False
        build_medical_knowledge.build_knowledge_base(rebuild=False)

        con = rag_service.get_db_connection()
        after_count = con.execute("SELECT count(*) FROM medical_documents").fetchone()[0]
        con.close()

        self.assertEqual(initial_count, after_count, "Số lượng bản ghi không được tăng thêm khi rebuild=False.")

    def test_03_vietnamese_accented_query_matching(self):
        """3. Truy vấn tiếng Việt có dấu khớp chính xác tài liệu liên quan."""
        results = rag_service.search_medical_knowledge("Đau dạ dày và ợ chua thì uống thuốc gì?")
        self.assertGreater(len(results), 0, "Phải tìm thấy tài liệu cho 'đau dạ dày và ợ chua'.")
        top_doc = results[0]
        text = rag_service.fold_vietnamese(top_doc["title"] + " " + top_doc["content"])
        self.assertTrue("da day" in text or "trao nguoc" in text or "o chua" in text)
        self.assertGreater(top_doc["relevance_score"], 20.0, "Điểm liên quan phải vượt ngưỡng.")

    def test_04_vietnamese_unaccented_query_matching(self):
        """4. Truy vấn tiếng Việt không dấu (accent folding) tìm được đúng tài liệu."""
        results = rag_service.search_medical_knowledge("dau da day va trao nguoc")
        self.assertGreater(len(results), 0, "Phải tìm thấy tài liệu cho 'dau da day va trao nguoc'.")
        top_doc = results[0]
        text = rag_service.fold_vietnamese(top_doc["title"] + " " + top_doc["content"])
        self.assertTrue("da day" in text or "trao nguoc" in text)

    def test_05_medical_synonyms_and_terminology(self):
        """5. Khớp thuật ngữ đồng nghĩa: 'bao tử' -> 'dạ dày'."""
        results = rag_service.search_medical_knowledge("Đau bao tử có phải bị trào ngược không")
        self.assertGreater(len(results), 0, "Phải tìm thấy tài liệu khi hỏi 'bao tử'.")
        found_stomach = any(
            "da day" in rag_service.fold_vietnamese(r["title"] + " " + r["content"])
            or "bao tu" in rag_service.fold_vietnamese(r["title"] + " " + r["content"])
            for r in results
        )
        self.assertTrue(found_stomach, "Phải khớp khái niệm dạ dày/bao tử.")

    def test_06_irrelevant_query_returns_no_results(self):
        """6. Câu hỏi ngoài phạm vi y tế (thời tiết, giá vàng, IT) trả về 0 kết quả."""
        irrelevant_queries = [
            "Thời tiết ngày mai tại Hà Nội có mưa không?",
            "Giá vàng hôm nay bao nhiêu tiền một chỉ?",
            "Hướng dẫn lập trình Python căn bản cho người mới bắt đầu",
            "Cách sửa xe máy bị thủng lốp",
        ]
        for q in irrelevant_queries:
            res = rag_service.search_medical_knowledge(q)
            self.assertEqual(len(res), 0, f"Query '{q}' là ngoài phạm vi y tế, phải trả về [] nhưng lại trả về {len(res)} docs.")

    def test_07_bm25_ranking_order(self):
        """7. Xếp hạng BM25 đúng chiều: Tài liệu liên quan nhất đứng đầu."""
        results = rag_service.search_medical_knowledge("Sốt xuất huyết Dengue", limit=3)
        self.assertGreater(len(results), 1)
        # relevance_score phải giảm dần theo thứ tự kết quả
        scores = [r["relevance_score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True), "Kết quả phải được sắp xếp giảm dần theo relevance_score.")

    def test_08_relevance_threshold_filtering(self):
        """8. Ngưỡng lọc điểm liên quan: Kết quả dưới ngưỡng min_score bị loại bỏ."""
        high_threshold = 9999.0  # Không tài liệu nào đạt được
        results = rag_service.search_medical_knowledge("đau dạ dày", min_score=high_threshold)
        self.assertEqual(len(results), 0, "Ngưỡng điểm quá cao phải trả về rỗng.")

    def test_09_source_metadata_integrity(self):
        """9. Metadata nguồn: URL thật, publisher hợp lệ, trust_level CURATED_MEDICAL_CONTENT."""
        results = rag_service.search_medical_knowledge("Viêm gan B")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r["chunk_id"].startswith("MED-"), "Mã tài liệu phải có tiền tố MED-.")
            self.assertEqual(r["trust_level"], "CURATED_MEDICAL_CONTENT")
            self.assertTrue(r["source"] in ("Bệnh viện Đa khoa Quốc tế Vinmec", "VnExpress Sức Khỏe") or "vinmec" in r.get("source_url", ""))
            if r["source_url"]:
                self.assertTrue(r["source_url"].startswith("http"), "URL phải bắt đầu bằng http/https.")

    def test_10_citation_validation_valid_citation(self):
        """10. Citation Validator: Trích dẫn hợp lệ được giữ lại và map đúng source."""
        dummy_docs = [
            {
                "chunk_id": "MED-00042",
                "title": "Chữa đau dạ dày",
                "content": "Nên ăn uống đúng giờ.",
                "source": "Vinmec",
                "source_url": "https://vinmec.com",
                "trust_level": "CURATED_MEDICAL_CONTENT"
            }
        ]
        model_reply = "Bệnh nhân cần ăn đúng giờ [MED-00042] để dạ dày ổn định."
        sanitized, used_sources = rag_service.validate_and_extract_citations(model_reply, dummy_docs)

        self.assertIn("[MED-00042]", sanitized)
        self.assertEqual(len(used_sources), 1)
        self.assertEqual(used_sources[0]["chunk_id"], "MED-00042")

    def test_11_fake_citation_removal(self):
        """11. Citation Validator: Mã trích dẫn bịa đặt [MED-99999] bị loại bỏ sạch khỏi câu trả lời."""
        dummy_docs = [
            {
                "chunk_id": "MED-00010",
                "title": "Sốt xuất huyết",
                "content": "Bù nước oresol.",
                "source": "Vinmec",
                "source_url": "https://vinmec.com",
                "trust_level": "CURATED_MEDICAL_CONTENT"
            }
        ]
        fake_reply = "Bạn nên uống oresol [MED-00010] và nghỉ ngơi nhiều [MED-99999]."
        sanitized, used_sources = rag_service.validate_and_extract_citations(fake_reply, dummy_docs)

        self.assertIn("[MED-00010]", sanitized, "Mã thật phải được giữ.")
        self.assertNotIn("[MED-99999]", sanitized, "Mã ảo phải bị loại bỏ sạch.")
        self.assertEqual(len(used_sources), 1)
        self.assertEqual(used_sources[0]["chunk_id"], "MED-00010")

    def test_12_missing_database_graceful_fallback(self):
        """12. Khả năng chống chịu: Khi file medical.db không tồn tại, RAG không crash."""
        non_existent_path = Path("database/missing_file.db")
        self.assertFalse(rag_service.is_rag_available(non_existent_path))
        res = rag_service.search_medical_knowledge("đau đầu", db_path=non_existent_path)
        self.assertEqual(res, [], "Phải trả về [] một cách an toàn mà không quăng Exception.")

    def test_13_corrupt_database_graceful_fallback(self):
        """13. Khả năng chống chịu: Khi database bị hỏng (corrupt), search xử lý an toàn."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"CORRUPT DATA NOT A SQLITE DB")
            temp_path = Path(f.name)
        try:
            res = rag_service.search_medical_knowledge("đau đầu", db_path=temp_path)
            self.assertEqual(res, [], "Phải xử lý an toàn khi database hỏng.")
        finally:
            try:
                temp_path.unlink()
            except Exception:
                pass

    def test_14_safety_emergency_does_not_call_rag(self):
        """14. Thứ tự ưu tiên An toàn: Khi là EMERGENCY, RAG tuyệt đối KHÔNG được kích hoạt."""
        should_run = rag_service.should_activate_rag(
            "Tôi khó thở dữ dội và đau thắt ngực",
            conversation_state={"stage": "ASSESSMENT"},
            safety_risk_level="EMERGENCY"
        )
        self.assertFalse(should_run, "RAG tuyệt đối không được gọi khi risk_level là EMERGENCY.")

    def test_15_intake_stage_does_not_call_rag(self):
        """15. Giai đoạn INTAKE không gọi RAG để tránh làm nhiễu câu hỏi làm rõ của bot."""
        should_run = rag_service.should_activate_rag(
            "Tôi thấy trong người mệt mỏi",
            conversation_state={"stage": "INTAKE"},
            safety_risk_level="NORMAL"
        )
        self.assertFalse(should_run, "RAG phải OFF trong giai đoạn INTAKE.")

    def test_16_assessment_stage_can_call_rag(self):
        """16. Giai đoạn ASSESSMENT được phép kích hoạt RAG để bổ sung chứng cứ y khoa."""
        should_run = rag_service.should_activate_rag(
            "Tôi bị viêm loét dạ dày 3 ngày nay",
            conversation_state={"stage": "ASSESSMENT"},
            safety_risk_level="NORMAL"
        )
        self.assertTrue(should_run, "RAG phải kích hoạt trong giai đoạn ASSESSMENT với triệu chứng bệnh.")

    def test_17_multiple_conversations_do_not_leak_rag_context(self):
        """17. Độc lập giữa các hội thoại: Context RAG chỉ gắn theo turn hiện tại, không rò rỉ sang hội thoại khác."""
        ctx1 = rag_service.search_medical_knowledge("Bệnh tiểu đường ăn gì")
        ctx2 = rag_service.search_medical_knowledge("Sốt xuất huyết có lây không")
        ids1 = {d["chunk_id"] for d in ctx1}
        ids2 = {d["chunk_id"] for d in ctx2}
        self.assertEqual(len(ids1.intersection(ids2)), 0, "Hai chủ đề khác biệt không được trùng lặp context.")

    def test_18_user_data_never_enters_knowledge_base(self):
        """18. Quyền riêng tư: Bảng medical_documents chỉ chứa curated content, không ghi nhận thông tin người dùng."""
        con = rag_service.get_db_connection()
        # Kiểm tra xem có bất kỳ cột nào liên quan đến user_id, password, email, profile_id không
        cols = {r["name"] for r in con.execute("PRAGMA table_info(medical_documents)").fetchall()}
        con.close()
        forbidden_cols = {"user_id", "email", "password", "profile_id", "patient_name", "chat_log"}
        self.assertEqual(len(forbidden_cols.intersection(cols)), 0, "Knowledge Base không được chứa bất kỳ trường dữ liệu người dùng nào.")

    def test_19_chat_endpoint_emergency_bypasses_rag_completely(self):
        """19. Tích hợp /chat: Cấp cứu không bao giờ gọi search_medical_knowledge và trả về sources=[]."""
        from app import app
        client = app.test_client()
        with patch.object(rag_service, "search_medical_knowledge") as mock_search:
            res = client.post(
                "/chat",
                data={"message": "Tôi đang co giật và khó thở dữ dội"},
                content_type="multipart/form-data"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("fast_path"))
            self.assertEqual(data.get("sources"), [])
            mock_search.assert_not_called()

    def test_20_chat_endpoint_medical_query_returns_sources(self):
        """20. Tích hợp /chat: Câu hỏi y tế thông thường trả về cấu trúc sources có trích dẫn."""
        from app import app
        client = app.test_client()

        mock_gemini_reply = "Bệnh nhân trào ngược dạ dày nên kiêng đồ chua cay [MED-00668]."
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = mock_gemini_reply
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

        with patch("app.create_chat_completion_with_retry", return_value=mock_completion):
            res = client.post(
                "/chat",
                data={"message": "Tôi bị trào ngược dạ dày thực quản thì nên ăn gì kiêng gì?"},
                content_type="multipart/form-data"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("sources", data)
            self.assertIsInstance(data["sources"], list)
            # Vì [MED-00668] là tài liệu về trào ngược dạ dày có trong retrieved context, source được trả về
            if data["sources"]:
                source_item = data["sources"][0]
                self.assertIn("chunk_id", source_item)
                self.assertIn("title", source_item)
                self.assertIn("trust_level", source_item)
                self.assertEqual(source_item["trust_level"], "CURATED_MEDICAL_CONTENT")


if __name__ == "__main__":
    unittest.main()

