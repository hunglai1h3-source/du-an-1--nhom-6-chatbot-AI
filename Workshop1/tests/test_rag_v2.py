"""
Test Suite for Phase 8: Official Medical Knowledge V2 (Vietnam Trusted Clinical Knowledge System).

Validates:
1. V2 Database existence, schema, and document counts (Tier 1, Tier 2, Tier 3, Tier 4).
2. Source hierarchy and domain verification (is_domain_allowed, BLOCKED_DOMAINS).
3. Document Status filtering: ACTIVE included, SUPERSEDED excluded by default (0% leakage).
4. Lineage Tracking: Superseded documents correctly linked to newer active documents.
5. Official-First Composite Ranking: Official Tier 1 documents outrank Tier 4 on clinical guidelines.
6. Dengue Guideline Versioning: QD 2760/QD-BYT (ACTIVE) is retrieved; QD 3707 (SUPERSEDED) is excluded.
7. Anaphylaxis Guideline Versioning: TT 51/2017/TT-BYT (ACTIVE) is retrieved; TT 08 (SUPERSEDED) is excluded.
8. Hepatitis B Guideline Versioning: QD 3310/QD-BYT (ACTIVE) is retrieved; QD 5448 is superseded.
9. Drug Recall / Regulatory Notice: Cefuroxim 500mg batch recall retrieved on recall query.
10. Drug Warning Notice: Clopidogrel - Omeprazole interaction warning retrieved.
11. Citation Validation V2: Valid [BYT-XXXXX], [DAV-XXXXX], [WHO-XXXXX], [MED-XXXXX] citations mapped.
12. Hallucinated Citation Stripping: Fake citations [BYT-99999], [MED-88888] stripped cleanly.
13. Citation Authority Badges: Extracted citations contain authority_tier and official_badge.
14. Out-of-domain query handling: Non-medical queries return 0 results.
15. Vietnamese accented and unaccented matching in V2 FTS.
16. Safety Gate Priority: EMERGENCY risk level strictly bypasses RAG V2.
17. Stage Policy: INTAKE stage does NOT activate RAG; ASSESSMENT stage activates.
18. Multi-conversation isolation: Independent search results per query context.
19. Data privacy: medical_v2.db contains no patient or user account fields.
20. Fallback resilience: Missing V2 database falls back cleanly to V1 without crashing.
21. Fallback resilience: Corrupted database file handled gracefully.
22. Dual-engine toggle: rag_service.USE_RAG_V2 toggle switches between V2 and V1 engines.
23. Context Formatter V2: Produces structured official clinical evidence format for LLM.
24. Chat endpoint integration: /chat returns V2 sources with official authority badge.
25. Chat endpoint emergency fast-path: Emergency bypasses RAG and returns sources=[].
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rag_service
import rag_service_v2
import source_registry
from source_registry import TrustTier, DocumentStatus, DocumentType
from medical_safety import RiskLevel, SafetyResult

import database
mock_db_conn = MagicMock()
mock_db_conn.execute.return_value.fetchone.return_value = None
mock_db_conn.execute.return_value.fetchall.return_value = []
mock_db_conn.execute.return_value.lastrowid = 1
database.get_connection = MagicMock(return_value=mock_db_conn)


class TestOfficialMedicalKnowledgeV2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db_v2_path = rag_service_v2.DATABASE_V2_PATH
        cls.db_v1_path = rag_service.DATABASE_PATH
        # Ensure V2 DB exists
        if not cls.db_v2_path.is_file():
            import build_medical_knowledge_v2
            build_medical_knowledge_v2.build_knowledge_base_v2(rebuild=True)

    # -------------------------------------------------------------------------
    # 1. DATABASE SCHEMA & INTEGRITY
    # -------------------------------------------------------------------------
    def test_01_v2_database_exists_and_has_required_tables(self):
        """1. Kiểm tra database medical_v2.db tồn tại và chứa đủ các bảng V2 chuẩn."""
        self.assertTrue(rag_service_v2.is_rag_v2_available(), "medical_v2.db phải sẵn sàng.")
        con = rag_service_v2.get_v2_connection()
        self.assertIsNotNone(con)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            expected_tables = {"sources", "medical_documents_v2", "medical_chunks_v2", "document_relations", "drug_recalls_v2", "medical_fts_v2"}
            self.assertTrue(expected_tables.issubset(tables), f"Thiếu bảng: {expected_tables - tables}")

            doc_count = con.execute("SELECT count(*) FROM medical_documents_v2").fetchone()[0]
            chunk_count = con.execute("SELECT count(*) FROM medical_chunks_v2").fetchone()[0]
            self.assertGreaterEqual(doc_count, 11000, "Tổng tài liệu phải >= 11,000 bản ghi.")
            self.assertGreaterEqual(chunk_count, 11000, "Tổng chunks phải >= 11,000 bản ghi.")
        finally:
            con.close()

    def test_02_tier_distribution_and_official_documents(self):
        """2. Kiểm tra phân bổ 4 tầng tin cậy và có ít nhất 15 văn bản chính thức Tier 1."""
        con = rag_service_v2.get_v2_connection()
        try:
            tier_counts = dict(con.execute("SELECT trust_tier, count(*) FROM medical_documents_v2 GROUP BY trust_tier").fetchall())
            self.assertIn(TrustTier.TIER_1.value, tier_counts)
            self.assertGreaterEqual(tier_counts[TrustTier.TIER_1.value], 15, "Tier 1 phải có ít nhất 15 văn bản chính thức.")
            self.assertIn(TrustTier.TIER_4.value, tier_counts)
            self.assertGreaterEqual(tier_counts[TrustTier.TIER_4.value], 11000, "Tier 4 phải bảo lưu dữ liệu ViHealthQA.")
        finally:
            con.close()

    # -------------------------------------------------------------------------
    # 2. SOURCE REGISTRY & DOMAIN VERIFICATION
    # -------------------------------------------------------------------------
    def test_03_domain_whitelist_and_blacklist(self):
        """3. Kiểm duyệt domain: cho phép domain chính thức, chặn domain diễn đàn/quảng cáo."""
        # Allowed
        self.assertTrue(source_registry.is_domain_allowed("https://moh.gov.vn/huong-dan-dieu-tri"))
        self.assertTrue(source_registry.is_domain_allowed("https://dav.gov.vn/thu-hoi-thuoc"))
        self.assertTrue(source_registry.is_domain_allowed("https://who.int/emergencies/disease-outbreak-news"))
        self.assertTrue(source_registry.is_domain_allowed("https://benhviennhitrunguong.gov.vn/chuyen-khoa"))
        self.assertTrue(source_registry.is_domain_allowed("https://vinmec.com/vi/tin-tuc/thong-tin-duoc"))

        # Blocked
        self.assertFalse(source_registry.is_domain_allowed("https://webtretho.com/f/me-va-be"))
        self.assertFalse(source_registry.is_domain_allowed("https://lamchame.com/forum/suc-khoe"))
        self.assertFalse(source_registry.is_domain_allowed("https://facebook.com/groups/bacsi-online"))
        self.assertFalse(source_registry.is_domain_allowed("https://tiktok.com/@meovat-suckhoe"))

    # -------------------------------------------------------------------------
    # 3. DOCUMENT STATUS, VERSIONING & LINEAGE
    # -------------------------------------------------------------------------
    def test_04_status_filtering_zero_superseded_leakage(self):
        """4. Lọc trạng thái: Không rò rỉ tài liệu SUPERSEDED trong truy vấn mặc định (0% leakage)."""
        con = rag_service_v2.get_v2_connection()
        try:
            superseded_docs = con.execute(
                "SELECT document_id, document_number, title FROM medical_documents_v2 WHERE status = 'SUPERSEDED'"
            ).fetchall()
            self.assertGreater(len(superseded_docs), 0, "Cần có tài liệu SUPERSEDED để kiểm thử.")
            superseded_ids = {r[0] for r in superseded_docs}
        finally:
            con.close()

        test_queries = [
            "Hướng dẫn điều trị sốt xuất huyết Dengue",
            "Phác đồ xử trí sốc phản vệ",
            "Hướng dẫn chẩn đoán và điều trị viêm gan B mạn tính",
        ]
        for q in test_queries:
            results = rag_service_v2.search_official_medical_knowledge(q, limit=10)
            for r in results:
                self.assertNotIn(
                    r["document_id"],
                    superseded_ids,
                    f"Rò rỉ tài liệu hết hiệu lực {r['document_id']} ({r.get('document_number')}) trong query '{q}'"
                )
                self.assertEqual(r["status"], "ACTIVE", f"Kết quả trả về phải có status ACTIVE, nhận {r['status']}")

    def test_05_document_lineage_tracking(self):
        """5. Kiểm tra bảng document_relations và superseded_by ghi nhận quan hệ thay thế."""
        con = rag_service_v2.get_v2_connection()
        try:
            lineages = con.execute("SELECT source_doc_id, relation_type, target_doc_id FROM document_relations").fetchall()
            self.assertGreaterEqual(len(lineages), 3, "Phải ghi nhận ít nhất 3 quan hệ thay thế.")

            superseded_records = dict(
                con.execute("SELECT document_id, superseded_by FROM medical_documents_v2 WHERE superseded_by IS NOT NULL").fetchall()
            )
            # QĐ 3707 bị thay thế bởi QĐ 2760
            self.assertEqual(superseded_records.get("MOH-QD-3707-2020"), "MOH-QD-2760-2023")
            # TT 08 bị thay thế bởi TT 51
            self.assertEqual(superseded_records.get("MOH-TT-08-1999"), "MOH-TT-51-2017")
            # QĐ 5448 bị thay thế bởi QĐ 3310
            self.assertEqual(superseded_records.get("MOH-QD-5448-2014"), "MOH-QD-3310-2019")
        finally:
            con.close()

    def test_06_dengue_guideline_active_qd2760_ranks_top(self):
        """6. Quyết định 2760/QĐ-BYT (ACTIVE) được xếp hạng đầu, không nhầm sang QĐ 3707 (SUPERSEDED)."""
        results = rag_service_v2.search_official_medical_knowledge("Hướng dẫn chẩn đoán điều trị sốt xuất huyết Dengue")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["trust_tier"], TrustTier.TIER_1.value)
        self.assertEqual(top["document_id"], "MOH-QD-2760-2023")
        self.assertEqual(top["document_number"], "2760/QĐ-BYT")
        self.assertEqual(top["status"], "ACTIVE")

    def test_07_anaphylaxis_active_tt51_ranks_top(self):
        """7. Thông tư 51/2017/TT-BYT (ACTIVE) xử trí sốc phản vệ được xếp đầu."""
        results = rag_service_v2.search_official_medical_knowledge("Phác đồ xử trí cấp cứu phản vệ Adrenalin")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["trust_tier"], TrustTier.TIER_1.value)
        self.assertEqual(top["document_id"], "MOH-TT-51-2017")
        self.assertEqual(top["document_number"], "51/2017/TT-BYT")

    def test_08_hepatitis_b_active_qd3310_ranks_top(self):
        """8. Quyết định 3310/QĐ-BYT (ACTIVE) viêm gan B được xếp đầu."""
        results = rag_service_v2.search_official_medical_knowledge("Phác đồ điều trị viêm gan virus B Bộ Y tế")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["trust_tier"], TrustTier.TIER_1.value)
        self.assertEqual(top["document_id"], "MOH-QD-3310-2019")
        self.assertEqual(top["document_number"], "3310/QĐ-BYT")

    # -------------------------------------------------------------------------
    # 4. OFFICIAL-FIRST COMPOSITE RANKING
    # -------------------------------------------------------------------------
    def test_09_official_first_composite_ranking(self):
        """9. Official-First Composite Ranking: Văn bản Tier 1 Bộ Y tế vượt qua Tier 4 dù số từ khóa ít hơn."""
        results = rag_service_v2.search_official_medical_knowledge("Hướng dẫn chẩn đoán và điều trị tăng huyết áp", limit=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["trust_tier"], TrustTier.TIER_1.value)
        self.assertIn("3192/QĐ-BYT", results[0]["document_number"])

    # -------------------------------------------------------------------------
    # 5. DRUG RECALL & REGULATORY SAFETY
    # -------------------------------------------------------------------------
    def test_10_drug_recall_cefuroxim_exact_batch(self):
        """10. Cảnh báo thu hồi thuốc Cefuroxim 500mg lô 010223 từ Cục Quản lý Dược."""
        con = rag_service_v2.get_v2_connection()
        try:
            con.row_factory = sqlite3.Row
            recall = con.execute("SELECT * FROM drug_recalls_v2 WHERE drug_name LIKE '%Cefuroxim%'").fetchone()
            self.assertIsNotNone(recall, "Phải có bản ghi thu hồi thuốc Cefuroxim trong bảng drug_recalls_v2.")
            self.assertEqual(recall["batch_number"], "010223")
            self.assertEqual(recall["recall_level"], "Cấp độ 2")
        finally:
            con.close()

        results = rag_service_v2.search_official_medical_knowledge("Thu hồi thuốc Cefuroxim 500mg lô 010223")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["document_id"], "DAV-TB-1182-2024")
        self.assertIn("1182/QLD-CL", top["document_number"])
        self.assertEqual(top["trust_tier"], TrustTier.TIER_1.value)

    def test_11_drug_warning_clopidogrel_omeprazole(self):
        """11. Cảnh báo tương tác thuốc Clopidogrel và Omeprazole từ Cục Quản lý Dược."""
        results = rag_service_v2.search_official_medical_knowledge("Cảnh báo tương tác Clopidogrel và Omeprazole")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["document_id"], "DAV-CB-2450-2023")
        self.assertIn("2450/QLD-ĐK", top["document_number"])

    # -------------------------------------------------------------------------
    # 6. CITATION VALIDATION V2 & SANITIZATION
    # -------------------------------------------------------------------------
    def test_12_valid_v2_citations_mapped(self):
        """12. Trích dẫn hợp lệ [BYT-XXXXX], [DAV-XXXXX], [MED-XXXXX] được giữ lại và ánh xạ đúng."""
        dummy_docs = [
            {
                "chunk_id": "BYT-00001",
                "title": "Hướng dẫn chẩn đoán sốt xuất huyết",
                "content": "Bù dịch sớm và theo dõi dấu hiệu cảnh báo.",
                "source": "Bộ Y tế",
                "source_url": "https://moh.gov.vn",
                "document_number": "2760/QĐ-BYT",
                "authority_tier": "TIER_1",
                "official_badge": "★ Chính thức Bộ Y tế",
                "effective_date": "2023-07-04"
            },
            {
                "chunk_id": "MED-00042",
                "title": "Chữa đau dạ dày",
                "content": "Nên ăn uống đúng giờ.",
                "source": "Vinmec",
                "source_url": "https://vinmec.com",
                "document_number": "",
                "authority_tier": "TIER_4",
                "official_badge": "Tham khảo",
                "effective_date": None
            }
        ]
        reply = "Theo phác đồ [BYT-00001], cần bù dịch đúng lượng và ăn đúng giờ [MED-00042]."
        sanitized, used_sources = rag_service.validate_and_extract_citations(reply, dummy_docs)

        self.assertIn("[BYT-00001]", sanitized)
        self.assertIn("[MED-00042]", sanitized)
        self.assertEqual(len(used_sources), 2)
        self.assertEqual(used_sources[0]["chunk_id"], "BYT-00001")
        self.assertEqual(used_sources[0]["official_badge"], "★ Chính thức Bộ Y tế")

    def test_13_fake_citations_stripped_cleanly(self):
        """13. Mã trích dẫn bịa đặt [BYT-99999], [DAV-00000], [MED-88888] bị bóc sạch."""
        dummy_docs = [
            {
                "chunk_id": "BYT-00001",
                "title": "Sốt xuất huyết Dengue",
                "content": "Nghỉ ngơi và bù nước.",
                "source": "Bộ Y tế",
                "source_url": "https://moh.gov.vn",
                "document_number": "2760/QĐ-BYT",
                "authority_tier": "TIER_1",
                "official_badge": "★ Chính thức Bộ Y tế"
            }
        ]
        hallucinated_reply = (
            "Theo Bộ Y tế [BYT-00001], tuyệt đối không dùng aspirin. "
            "Ngoài ra theo thông tư ảo [BYT-99999] và công văn ảo [DAV-00000] cùng nguồn [MED-88888]."
        )
        sanitized, used_sources = rag_service.validate_and_extract_citations(hallucinated_reply, dummy_docs)

        self.assertIn("[BYT-00001]", sanitized, "Mã thật phải được giữ.")
        self.assertNotIn("[BYT-99999]", sanitized, "Mã [BYT-99999] bịa đặt phải bị gỡ.")
        self.assertNotIn("[DAV-00000]", sanitized, "Mã [DAV-00000] bịa đặt phải bị gỡ.")
        self.assertNotIn("[MED-88888]", sanitized, "Mã [MED-88888] bịa đặt phải bị gỡ.")
        self.assertEqual(len(used_sources), 1)
        self.assertEqual(used_sources[0]["chunk_id"], "BYT-00001")

    # -------------------------------------------------------------------------
    # 7. OUT-OF-DOMAIN & VIETNAMESE ACCENT HANDLING
    # -------------------------------------------------------------------------
    def test_14_out_of_domain_queries_return_empty(self):
        """14. Câu hỏi ngoài phạm vi y tế trả về rỗng trong RAG V2."""
        ood_queries = [
            "Thời tiết Hà Nội hôm nay mưa hay nắng?",
            "Tỷ giá USD/VND Vietcombank hôm nay bao nhiêu?",
            "Lập trình Flask Python RESTful API",
            "Giá xe ô tô VinFast VF8 mới nhất",
        ]
        for q in ood_queries:
            results = rag_service.search_medical_knowledge(q)
            self.assertEqual(len(results), 0, f"Query '{q}' là ngoài y tế, phải trả về []")

    def test_15_vietnamese_accented_and_unaccented(self):
        """15. Khớp đúng cả tiếng Việt có dấu và không dấu trong RAG V2."""
        res_accent = rag_service.search_medical_knowledge("Hướng dẫn sốt xuất huyết Dengue")
        self.assertGreater(len(res_accent), 0)

        res_unaccent = rag_service.search_medical_knowledge("huong dan sot xuat huyet dengue")
        self.assertGreater(len(res_unaccent), 0)

    # -------------------------------------------------------------------------
    # 8. SAFETY GATE & STAGE POLICY INTEGRATION
    # -------------------------------------------------------------------------
    def test_16_safety_emergency_bypasses_rag(self):
        """16. Trường hợp EMERGENCY tuyệt đối không kích hoạt RAG V2."""
        should_run = rag_service.should_activate_rag(
            "Tôi đau thắt ngực dữ dội và ngất xỉu",
            conversation_state={"stage": "ASSESSMENT"},
            safety_risk_level="EMERGENCY"
        )
        self.assertFalse(should_run, "RAG phải OFF trong trường hợp CẤP CỨU EMERGENCY.")

    def test_17_stage_policy_intake_vs_assessment(self):
        """17. Giai đoạn INTAKE không gọi RAG, giai đoạn ASSESSMENT được phép gọi RAG."""
        intake_run = rag_service.should_activate_rag(
            "Tôi bị đau bụng âm ỉ mấy hôm",
            conversation_state={"stage": "INTAKE"},
            safety_risk_level="NORMAL"
        )
        self.assertFalse(intake_run, "INTAKE stage không kích hoạt RAG.")

        assessment_run = rag_service.should_activate_rag(
            "Tôi bị đau bụng âm ỉ vùng thượng vị mấy hôm",
            conversation_state={"stage": "ASSESSMENT"},
            safety_risk_level="NORMAL"
        )
        self.assertTrue(assessment_run, "ASSESSMENT stage kích hoạt RAG.")

    # -------------------------------------------------------------------------
    # 9. MULTI-CONVERSATION ISOLATION & DATA PRIVACY
    # -------------------------------------------------------------------------
    def test_18_multi_conversation_isolation(self):
        """18. Độc lập dữ liệu giữa các hội thoại: Không rò rỉ context."""
        ctx_flu = rag_service.search_medical_knowledge("Phác đồ điều trị cúm mùa")
        ctx_gout = rag_service.search_medical_knowledge("Bệnh gút điều trị thế nào")
        ids_flu = {d["chunk_id"] for d in ctx_flu}
        ids_gout = {d["chunk_id"] for d in ctx_gout}
        self.assertEqual(len(ids_flu.intersection(ids_gout)), 0, "Context 2 chủ đề khác nhau không được giao nhau.")

    def test_19_privacy_no_user_columns_in_v2_db(self):
        """19. Quyền riêng tư: Database V2 tuyệt đối không chứa dữ liệu cá nhân hay người dùng."""
        con = rag_service_v2.get_v2_connection()
        try:
            for table in ["medical_documents_v2", "medical_chunks_v2", "sources"]:
                cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
                forbidden = {"user_id", "email", "password", "phone", "profile_id", "chat_history"}
                self.assertEqual(len(forbidden.intersection(cols)), 0, f"Bảng {table} chứa cột cấm.")
        finally:
            con.close()

    # -------------------------------------------------------------------------
    # 10. RESILIENCE, FALLBACK & DUAL ENGINE TOGGLE
    # -------------------------------------------------------------------------
    def test_20_missing_v2_database_falls_back_to_v1(self):
        """20. Khi medical_v2.db không tồn tại, tự động fallback về medical.db an toàn."""
        non_existent_path = Path("database/non_existent_v2.db")
        results = rag_service_v2.search_official_medical_knowledge("đau dạ dày", db_path=non_existent_path)
        self.assertEqual(results, [], "Khi file V2 không tồn tại, hàm V2 trả về [] không văng Exception.")

        # rag_service.search_medical_knowledge phải fallback về V1 an toàn khi V2 không khả dụng
        with patch.object(rag_service_v2, "is_knowledge_v2_available", return_value=False):
            res = rag_service.search_medical_knowledge("đau dạ dày")
            self.assertGreater(len(res), 0, "Fallback về V1 phải trả về kết quả từ medical.db.")

    def test_21_corrupt_v2_database_handled_gracefully(self):
        """21. Khi database V2 bị hỏng (corrupt), xử lý ngoại lệ an toàn."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"NOT A VALID SQLITE DATABASE FILE FOR RAG V2")
            temp_path = Path(f.name)
        try:
            res = rag_service_v2.search_official_medical_knowledge("sốt cao", db_path=temp_path)
            self.assertEqual(res, [], "Phải trả về [] một cách an toàn mà không sập hệ thống.")
        finally:
            try:
                temp_path.unlink()
            except Exception:
                pass

    def test_22_dual_engine_toggle_rag_v2(self):
        """22. Cờ USE_RAG_V2 chuyển đổi chính xác giữa 2 engine."""
        # USE_RAG_V2 = True -> Kết quả chứa authority_tier và official_badge
        rag_service.USE_RAG_V2 = True
        res_v2 = rag_service.search_medical_knowledge("Sốt xuất huyết Dengue")
        self.assertGreater(len(res_v2), 0)
        self.assertIn("authority_tier", res_v2[0])
        self.assertIn("official_badge", res_v2[0])

        # USE_RAG_V2 = False -> Kết quả từ V1 (trust_level CURATED_MEDICAL_CONTENT)
        rag_service.USE_RAG_V2 = False
        res_v1 = rag_service.search_medical_knowledge("Sốt xuất huyết Dengue")
        self.assertGreater(len(res_v1), 0)
        self.assertEqual(res_v1[0]["trust_level"], "CURATED_MEDICAL_CONTENT")

        # Khôi phục trạng thái mặc định
        rag_service.USE_RAG_V2 = True

    # -------------------------------------------------------------------------
    # 11. CONTEXT FORMATTER V2
    # -------------------------------------------------------------------------
    def test_23_context_formatter_v2_structure(self):
        """23. format_rag_context_v2 tạo cấu trúc chuẩn y khoa Việt Nam cho LLM."""
        dummy_docs = [
            {
                "chunk_id": "BYT-00001",
                "title": "Hướng dẫn chẩn đoán và điều trị sốt xuất huyết Dengue",
                "content": "Phân loại: Sốt xuất huyết Dengue, Sốt xuất huyết Dengue có dấu hiệu cảnh báo, Sốt xuất huyết Dengue nặng.",
                "source": "Bộ Y tế",
                "source_url": "https://moh.gov.vn",
                "document_number": "2760/QĐ-BYT",
                "trust_tier": "TIER_1",
                "authority_tier": "TIER_1",
                "official_badge": "★ Chính thức Bộ Y tế",
                "issue_date": "2023-07-04",
                "section_path": "Chẩn đoán > Phân độ lâm sàng"
            }
        ]
        formatted = rag_service_v2.format_rag_context_v2(dummy_docs)
        self.assertIn("NGUỒN TRI THỨC Y KHOA CHÍNH THỨC", formatted)
        self.assertIn("2760/QĐ-BYT", formatted)
        self.assertIn("2023-07-04", formatted)
        self.assertIn("[BYT-00001]", formatted)
        self.assertIn("Chẩn đoán > Phân độ lâm sàng", formatted)

    # -------------------------------------------------------------------------
    # 12. END-TO-END FLASK INTEGRATION
    # -------------------------------------------------------------------------
    def test_24_chat_endpoint_returns_v2_official_sources(self):
        """24. Tích hợp /chat: Trả về cấu trúc sources có nhãn chính thức Bộ Y tế."""
        from app import app
        client = app.test_client()

        mock_gemini_reply = "Theo hướng dẫn của Bộ Y tế [BYT-00001], bệnh nhân sốt xuất huyết cần theo dõi sát các dấu hiệu cảnh báo."
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = mock_gemini_reply
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = MagicMock(prompt_tokens=15, completion_tokens=25)

        with patch("app.create_chat_completion_with_retry", return_value=mock_completion):
            res = client.post(
                "/chat",
                data={"message": "Dấu hiệu cảnh báo sốt xuất huyết theo Bộ Y tế là gì?"},
                content_type="multipart/form-data"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn("sources", data)
            self.assertIsInstance(data["sources"], list)
            if data["sources"]:
                source_item = data["sources"][0]
                self.assertIn("chunk_id", source_item)
                self.assertIn("title", source_item)
                self.assertIn("authority_tier", source_item)
                self.assertIn("official_badge", source_item)

    def test_25_chat_endpoint_emergency_bypasses_rag_v2(self):
        """25. Tích hợp /chat: Cấp cứu 115 bỏ qua RAG V2 hoàn toàn và trả về sources=[]."""
        from app import app
        client = app.test_client()
        with patch.object(rag_service, "search_medical_knowledge") as mock_search:
            res = client.post(
                "/chat",
                data={"message": "Tôi đang bị sốc phản vệ khó thở tím tái sau khi tiêm thuốc"},
                content_type="multipart/form-data"
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("fast_path"))
            self.assertEqual(data.get("sources"), [])
            mock_search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
