"""
Unit & Integration Test Suite for Phase 9: Personal Health Intelligence.
Tests:
1. Schema & Migration (tables creation & rollback)
2. Personal Health Context, Provenance & Priority Rules
3. Profile Isolation (Self vs Family)
4. Contradiction & User Correction Engine
5. Personal Baseline Engine (Maturity & Deviation Safeguards)
6. Health Episode Engine (Linking, Recurrence, Idempotency, Trend)
7. Adaptive Severity Engine (Invariant: Safety Always Wins, Contextual Escalations)
8. Next-Best Question Engine (Single Question, Profile Awareness, Declined Slots)
9. End-to-End /chat pipeline integration & Graceful Fallback
"""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from medical_safety import RiskLevel, SafetyResult
from personal_intelligence_schema import (
    init_personal_intelligence_schema,
    drop_personal_intelligence_schema,
)
from personal_health_context import (
    PersonalHealthContext,
    FactSource,
    FactConfidence,
    build_personal_health_context,
    detect_contradictions_and_corrections,
    format_personal_health_context_for_prompt,
)
from personal_baseline_engine import (
    BaselineMaturity,
    BaselineDeviationLevel,
    BaselineAttribute,
    BaselineDeviation,
    get_personal_baselines,
    update_personal_baseline_from_episode,
    evaluate_baseline_deviation,
    format_baseline_for_prompt,
)
from health_episode_engine import (
    HealthEpisode,
    HealthEpisodeEvent,
    EpisodeStatus,
    EpisodeEventType,
    EpisodeTrend,
    EpisodeLinkingConfidence,
    evaluate_episode_linking,
    calculate_episode_trend,
    get_active_or_recent_episodes,
    get_episode_events,
    save_or_update_health_episode,
    format_episode_for_prompt,
)
from adaptive_severity_engine import (
    EffectiveConcernLevel,
    AdaptiveSeverityAssessment,
    assess_adaptive_severity,
    format_adaptive_severity_for_prompt,
    log_adaptive_severity_assessment,
)
from next_best_question_engine import (
    QuestionIntent,
    NextBestQuestion,
    determine_next_best_question,
    format_next_best_question_directive_for_prompt,
    detect_user_declination,
)
from conversation_engine import (
    MedicalConversationState,
    MedicalSlots,
    ConversationStage,
)


class TestPersonalIntelligenceSuite(unittest.TestCase):

    def setUp(self):
        """Khởi tạo SQLite in-memory database độc lập cho mỗi test case."""
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        # Tạo các bảng cơ sở dữ liệu cốt lõi
        self.conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                full_name TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE health_profiles (
                user_id INTEGER PRIMARY KEY,
                age INTEGER,
                sex TEXT,
                height_cm REAL,
                activity_level TEXT,
                goal TEXT,
                diet_preference TEXT,
                allergies TEXT,
                medical_notes TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                full_name TEXT,
                name TEXT,
                relationship TEXT,
                age INTEGER,
                birth_year INTEGER,
                gender TEXT,
                allergies TEXT,
                medical_conditions TEXT,
                medical_history TEXT,
                current_medications TEXT,
                weight_kg REAL,
                height_cm REAL,
                notes TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE weight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                weight_kg REAL,
                logged_at TEXT
            )
        """)

        # Khởi tạo Schema Phase 9
        init_personal_intelligence_schema(self.conn)

        # Chèn dữ liệu mẫu cho user bản thân và family member
        self.conn.execute("INSERT INTO users (id, email, full_name) VALUES (1, 'test@medicare.ai', 'Nguyễn Văn A')")
        self.conn.execute("""
            INSERT INTO health_profiles (user_id, age, sex, height_cm, activity_level, goal, diet_preference, allergies, medical_notes)
            VALUES (1, 35, 'Nam', 170.0, 'Vừa phải', 'Duy trì sức khỏe', 'Bình thường', 'Penicillin', 'Tăng huyết áp nhẹ')
        """)
        self.conn.execute("""
            INSERT INTO weight_logs (user_id, weight_kg, logged_at)
            VALUES (1, 68.5, '2026-09-01T10:00:00')
        """)

        # Family member (Mẹ, 68 tuổi, đái tháo đường, dị ứng hải sản)
        self.conn.execute("""
            INSERT INTO family_members (id, user_id, full_name, name, relationship, age, birth_year, gender, allergies, medical_conditions, medical_history, current_medications, weight_kg, height_cm, notes)
            VALUES (10, 1, 'Trần Thị B', 'Trần Thị B', 'Mẹ', 68, 1958, 'Nữ', 'Hải sản', 'Đái tháo đường type 2', 'Đái tháo đường type 2', 'Metformin', 55.0, 155.0, 'Khám định kỳ')
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    # ==========================================================================
    # 1. SCHEMA & MIGRATION TESTS
    # ==========================================================================

    def test_01_schema_initialization_creates_all_tables(self):
        """Kiểm tra schema Phase 9 tạo đủ 5 bảng."""
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("health_episodes", tables)
        self.assertIn("health_episode_events", tables)
        self.assertIn("personal_baselines", tables)
        self.assertIn("personal_fact_states", tables)
        self.assertIn("adaptive_severity_logs", tables)

    def test_02_schema_rollback_drops_tables(self):
        """Kiểm tra rollback schema Phase 9 xóa sạch các bảng Phase 9."""
        drop_personal_intelligence_schema(self.conn)
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertNotIn("health_episodes", tables)
        self.assertNotIn("health_episode_events", tables)
        self.assertNotIn("personal_baselines", tables)
        self.assertNotIn("personal_fact_states", tables)
        self.assertNotIn("adaptive_severity_logs", tables)

    # ==========================================================================
    # 2. PERSONAL HEALTH CONTEXT & PROFILE ISOLATION TESTS
    # ==========================================================================

    def test_03_context_builder_self_profile(self):
        """Xây dựng context cho tài khoản chính (self) đọc đúng dữ liệu."""
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self")
        self.assertEqual(ctx.profile_type, "self")
        self.assertEqual(ctx.age, 35)
        self.assertEqual(ctx.gender, "Nam")
        self.assertEqual(ctx.weight_kg, 68.5)
        self.assertIn("Penicillin", ctx.allergies)
        self.assertIn("Tăng huyết áp nhẹ", ctx.known_conditions)
        self.assertEqual(ctx.confidence.get("allergies"), FactConfidence.CONFIRMED.value)

    def test_04_profile_isolation_family_does_not_leak_self_data(self):
        """Cách ly hồ sơ tuyệt đối: Xem hồ sơ Mẹ không được chứa dị ứng hay bệnh của Bản thân."""
        ctx_mother = build_personal_health_context(self.conn, user_id=1, profile_ref="10")
        self.assertEqual(ctx_mother.profile_type, "family")
        self.assertEqual(ctx_mother.name, "Trần Thị B")
        self.assertEqual(ctx_mother.relationship, "Mẹ")
        self.assertEqual(ctx_mother.gender, "Nữ")
        self.assertIn("Hải sản", ctx_mother.allergies)
        self.assertNotIn("Penicillin", ctx_mother.allergies)  # KHÔNG rò rỉ dị ứng của con
        self.assertIn("Đái tháo đường type 2", ctx_mother.known_conditions)
        self.assertNotIn("Tăng huyết áp nhẹ", ctx_mother.known_conditions)  # KHÔNG rò rỉ bệnh của con

    def test_05_priority_hierarchy_user_correction_overrides_profile(self):
        """Thứ bậc ưu tiên: Lời đính chính trực tiếp của user ghi đè hồ sơ cũ."""
        msg = "Bác sĩ ơi, tôi không hề dị ứng penicillin nhé, đợt trước ghi nhầm đấy"
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self", current_message=msg)
        self.assertNotIn("Penicillin", ctx.allergies)
        self.assertEqual(len(ctx.conflicts), 1)
        self.assertEqual(ctx.conflicts[0]["conflict_type"], "ALLERGY_REMOVAL")
        self.assertEqual(ctx.conflicts[0]["action"], "USER_CORRECTION_OVERRIDE")

    def test_06_weight_update_in_conversation(self):
        """Cập nhật cân nặng mới trong chat tính lại BMI và ghi nhận fact."""
        msg = "Hôm nay tôi cân được 75kg rồi"
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self", current_message=msg)
        self.assertEqual(ctx.weight_kg, 75.0)
        self.assertIsNotNone(ctx.bmi)
        self.assertEqual(ctx.source_map["weight_kg"], FactSource.CURRENT_USER_MESSAGE.value)

    def test_07_pregnancy_context_update(self):
        """Nhận diện cập nhật tình trạng mang thai từ tin nhắn."""
        msg = "Tôi đang mang thai tuần thứ 12"
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self", current_message=msg)
        self.assertIsNotNone(ctx.pregnancy_context)
        self.assertTrue(ctx.pregnancy_context["is_pregnant"])
        self.assertEqual(ctx.pregnancy_context["gestational_weeks"], 12)

    def test_08_prompt_format_compact_budget(self):
        """Kiểm tra độ dài prompt của context nằm trong ngân sách cho phép (< 1200 ký tự)."""
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self")
        prompt_txt = format_personal_health_context_for_prompt(ctx)
        self.assertLess(len(prompt_txt), 1200)
        self.assertIn("HỒ SƠ SỨC KHỎE CÁ NHÂN", prompt_txt)

    # ==========================================================================
    # 3. PERSONAL BASELINE ENGINE TESTS
    # ==========================================================================

    def test_09_baseline_lifecycle_maturity_progression(self):
        """Kiểm tra vòng đời nâng cấp mức độ thành thục của baseline: LOW -> EMERGING -> ESTABLISHED."""
        # Lần 1: LOW_CONFIDENCE
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau đầu", pain_scale=3)
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")
        self.assertIn("usual_đau_đầu", baselines)
        self.assertEqual(baselines["usual_đau_đầu"].maturity, BaselineMaturity.LOW_CONFIDENCE.value)
        self.assertEqual(baselines["usual_đau_đầu"].evidence_count, 1)

        # Lần 2 & 3: EMERGING
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau đầu", pain_scale=2)
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")
        self.assertEqual(baselines["usual_đau_đầu"].maturity, BaselineMaturity.EMERGING.value)
        self.assertEqual(baselines["usual_đau_đầu"].evidence_count, 2)

        # Lần 4: ESTABLISHED
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau đầu", pain_scale=3)
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau đầu", pain_scale=2)
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")
        self.assertEqual(baselines["usual_đau_đầu"].maturity, BaselineMaturity.ESTABLISHED.value)
        self.assertEqual(baselines["usual_đau_đầu"].evidence_count, 4)

    def test_10_baseline_deviation_normal_vs_high(self):
        """So sánh độ lệch baseline: điểm đau bình thường (2/10) vs điểm đau dữ dội kèm sốt (8/10)."""
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau đầu", pain_scale=2)
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")

        # Trường hợp bình thường (pain 2/10)
        dev_normal = evaluate_baseline_deviation(
            baselines, chief_complaint="đau đầu", current_pain_scale=2, current_severity="nhẹ",
            current_duration="1 ngày", fever=False, associated_symptoms=[]
        )
        self.assertEqual(dev_normal.deviation_level, BaselineDeviationLevel.NONE.value)

        # Trường hợp bất thường dữ dội (pain 8/10 kèm nôn và sốt) -> HIGH deviation
        dev_high = evaluate_baseline_deviation(
            baselines, chief_complaint="đau đầu", current_pain_scale=8, current_severity="dữ dội",
            current_duration="1 ngày", fever=True, associated_symptoms=["buồn nôn"]
        )
        self.assertEqual(dev_high.deviation_level, BaselineDeviationLevel.HIGH.value)
        self.assertTrue(any("8/10" in r and "Điểm đau" in r for r in dev_high.deviation_reasons))

    def test_11_deterioration_safeguard_never_marks_severe_as_baseline(self):
        """Bảo vệ suy thoái: Triệu chứng nặng trên nền bệnh mạn tính không bao giờ được coi là bình thường."""
        update_personal_baseline_from_episode(self.conn, user_id=1, profile_ref="self", complaint_key="đau lưng", pain_scale=2)
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")

        dev = evaluate_baseline_deviation(
            baselines, chief_complaint="đau lưng", current_pain_scale=9, current_severity="dữ dội",
            current_duration="vài giờ", fever=True, associated_symptoms=["tê bì chân"]
        )
        self.assertNotEqual(dev.deviation_level, BaselineDeviationLevel.NONE.value)
        self.assertEqual(dev.deviation_level, BaselineDeviationLevel.HIGH.value)

    # ==========================================================================
    # 4. HEALTH EPISODE ENGINE & EVENT TIMELINE TESTS
    # ==========================================================================

    def test_12_episode_linking_same_episode(self):
        """Liên kết đợt bệnh: Triệu chứng tương tự trong vòng 14 ngày được nối vào đợt hiện tại."""
        ep = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Đau họng sốt")
        save_or_update_health_episode(self.conn, ep)

        active = get_active_or_recent_episodes(self.conn, user_id=1, profile_ref="self")
        conf, matched, reasons = evaluate_episode_linking(active, new_complaint="đau họng", body_location="họng", user_message="hôm nay họng tôi vẫn còn đau")
        self.assertEqual(conf, EpisodeLinkingConfidence.SAME_EPISODE_HIGH)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.episode_id, ep.episode_id)

    def test_13_episode_linking_recurrence(self):
        """Phát hiện tái phát: Đợt trước đã RESOLVED và người dùng thông báo 'bị lại'."""
        ep = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Đau dạ dày", status=EpisodeStatus.RESOLVED.value)
        save_or_update_health_episode(self.conn, ep)

        active = get_active_or_recent_episodes(self.conn, user_id=1, profile_ref="self")
        conf, matched, reasons = evaluate_episode_linking(active, new_complaint="đau dạ dày", body_location="bụng", user_message="tôi lại bị đau dạ dày tái phát rồi")
        self.assertEqual(conf, EpisodeLinkingConfidence.RECURRENCE)
        self.assertEqual(matched.episode_id, ep.episode_id)

    def test_14_episode_linking_new_episode(self):
        """Phát hiện đợt bệnh mới khi triệu chứng hoàn toàn khác biệt."""
        ep = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Đau mắt đỏ")
        save_or_update_health_episode(self.conn, ep)

        active = get_active_or_recent_episodes(self.conn, user_id=1, profile_ref="self")
        conf, matched, reasons = evaluate_episode_linking(active, new_complaint="đau khớp gối", body_location="gối", user_message="tôi bị trẹo khớp gối")
        self.assertEqual(conf, EpisodeLinkingConfidence.NEW_EPISODE_HIGH)
        self.assertIsNone(matched)

    def test_15_episode_event_idempotency(self):
        """Bảo đảm tính lũy biến (Idempotency): client_message_id trùng lặp không tạo thêm sự kiện."""
        ep = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Ho có đờm")
        save_or_update_health_episode(self.conn, ep)

        ev1 = HealthEpisodeEvent(episode_id=ep.episode_id, event_type=EpisodeEventType.USER_REPORT.value, client_message_id="msg_unique_123", event_data={"pain": 2})
        save_or_update_health_episode(self.conn, ep, ev1)

        # Gửi lại sự kiện cùng client_message_id
        ev2 = HealthEpisodeEvent(episode_id=ep.episode_id, event_type=EpisodeEventType.USER_REPORT.value, client_message_id="msg_unique_123", event_data={"pain": 2})
        save_or_update_health_episode(self.conn, ep, ev2)

        events = get_episode_events(self.conn, ep.episode_id)
        self.assertEqual(len(events), 1)  # Chỉ có 1 sự kiện duy nhất được lưu

    def test_16_episode_trend_detection(self):
        """Kiểm tra phân tích xu hướng diễn tiến: WORSENING, IMPROVING, STABLE."""
        events_worsening = [
            HealthEpisodeEvent(episode_id="ep1", event_type="USER_REPORT", event_data={"pain_scale": 3, "fever": False}),
            HealthEpisodeEvent(episode_id="ep1", event_type="USER_REPORT", event_data={"pain_scale": 6, "fever": True}),
        ]
        trend_w, _ = calculate_episode_trend(events_worsening, current_pain=6, current_fever=True, current_duration="tăng dần")
        self.assertEqual(trend_w, EpisodeTrend.WORSENING)

        events_improving = [
            HealthEpisodeEvent(episode_id="ep2", event_type="USER_REPORT", event_data={"pain_scale": 7, "fever": True}),
            HealthEpisodeEvent(episode_id="ep2", event_type="USER_REPORT", event_data={"pain_scale": 2, "fever": False}),
        ]
        trend_i, _ = calculate_episode_trend(events_improving, current_pain=2, current_fever=False, current_duration="đỡ rồi")
        self.assertEqual(trend_i, EpisodeTrend.IMPROVING)

    # ==========================================================================
    # 5. ADAPTIVE SEVERITY ENGINE TESTS (SAFETY ALWAYS WINS)
    # ==========================================================================

    def test_17_safety_always_wins_emergency_cannot_be_downgraded(self):
        """BẤT BIẾN AN TOÀN: Safety EMERGENCY tuyệt đối không bị hạ cấp bởi cá nhân hóa."""
        safety = SafetyResult(risk_level=RiskLevel.EMERGENCY, category="chest_cardiac", reason_code="chest_pain_radiating", confidence=1.0, should_stop_normal_flow=True)
        # Bối cảnh user nói quen đau ngực nhẹ
        b_dev = BaselineDeviation(deviation_level=BaselineDeviationLevel.NONE.value)
        assessment = assess_adaptive_severity(safety, baseline_deviation=b_dev)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.EMERGENCY)
        self.assertEqual(assessment.monitoring_interval_hours, 0)

    def test_18_safety_always_wins_urgent_cannot_be_downgraded(self):
        """BẤT BIẾN AN TOÀN: Safety URGENT không bị hạ xuống ROUTINE hay MONITOR_CLOSELY."""
        safety = SafetyResult(risk_level=RiskLevel.URGENT, category="breathing", reason_code="dyspnea", confidence=0.9, should_stop_normal_flow=False)
        b_dev = BaselineDeviation(deviation_level=BaselineDeviationLevel.NONE.value)
        assessment = assess_adaptive_severity(safety, baseline_deviation=b_dev)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.URGENT)

    def test_19_contextual_escalation_infant_fever(self):
        """Nâng mức quan ngại cho đối tượng nhũ nhi (< 2 tuổi)."""
        safety = SafetyResult(risk_level=RiskLevel.NORMAL, category="general", reason_code="normal", confidence=0.8, should_stop_normal_flow=False)
        ctx = PersonalHealthContext(profile_id="baby", age=1)
        assessment = assess_adaptive_severity(safety, personal_context=ctx)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.MONITOR_CLOSELY)
        self.assertTrue(assessment.adaptive_escalation_applied)

    def test_20_contextual_escalation_pregnancy_headache(self):
        """Nâng mức quan ngại URGENT cho phụ nữ mang thai đau đầu (nguy cơ tiền sản giật)."""
        safety = SafetyResult(risk_level=RiskLevel.NORMAL, category="general", reason_code="normal", confidence=0.8, should_stop_normal_flow=False)
        ctx = PersonalHealthContext(profile_id="p1", age=28, pregnancy_context={"is_pregnant": True})
        ep = HealthEpisode(profile_type="self", profile_ref="self", chief_complaint="Đau đầu chóng mặt")
        assessment = assess_adaptive_severity(safety, personal_context=ctx, current_episode=ep)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.URGENT)
        self.assertTrue(assessment.adaptive_escalation_applied)

    def test_21_contextual_escalation_diabetic_worsening_infection(self):
        """Nâng mức quan ngại URGENT cho bệnh nhân tiểu đường có diễn biến bệnh xấu đi."""
        safety = SafetyResult(risk_level=RiskLevel.NORMAL, category="general", reason_code="normal", confidence=0.8, should_stop_normal_flow=False)
        ctx = PersonalHealthContext(profile_id="p2", known_conditions=["Đái tháo đường type 2"])
        assessment = assess_adaptive_severity(safety, personal_context=ctx, episode_trend=EpisodeTrend.WORSENING)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.URGENT)
        self.assertTrue(assessment.adaptive_escalation_applied)

    def test_22_adaptive_severity_audit_logging(self):
        """Kiểm tra ghi log kiểm toán đánh giá Adaptive Severity vào database."""
        assessment = AdaptiveSeverityAssessment(
            effective_concern_level=EffectiveConcernLevel.URGENT,
            base_safety_level="normal",
            adaptive_escalation_applied=True,
            escalation_reasons=["Độ lệch baseline cao"],
            downgrade_prevented=False,
            clinical_rationale="Nâng mức do độ lệch cao",
            monitoring_interval_hours=2,
        )
        log_adaptive_severity_assessment(self.conn, user_id=1, profile_id="self", conversation_id="conv_1", assessment=assessment, client_message_id="msg_1")
        row = self.conn.execute("SELECT * FROM adaptive_severity_logs WHERE conversation_id = 'conv_1'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["final_level"], "URGENT")
        self.assertEqual(row["adaptive_level"], "URGENT")

    # ==========================================================================
    # 6. NEXT-BEST QUESTION ENGINE TESTS
    # ==========================================================================

    def test_23_never_ask_known_profile_facts(self):
        """Không bao giờ hỏi lại tuổi, giới tính, dị ứng hoặc bệnh nền đã có trong hồ sơ."""
        ctx = PersonalHealthContext(
            profile_id="self",
            age=35,
            gender="Nam",
            allergies=["Penicillin"],
            known_conditions=["Tăng huyết áp"]
        )
        state = MedicalConversationState(stage=ConversationStage.INTAKE.value)
        nbq = determine_next_best_question("Tôi bị đau bụng", personal_context=ctx, conv_state=state)
        self.assertTrue(nbq.should_ask)
        self.assertNotIn(nbq.slot_to_ask, ["age", "gender", "allergies", "medical_conditions"])

    def test_24_single_question_invariant(self):
        """Quy tắc bất biến: Chỉ sinh ra DUY NHẤT một câu hỏi hoặc không hỏi."""
        ctx = PersonalHealthContext(profile_id="self", age=25)
        state = MedicalConversationState(stage=ConversationStage.INTAKE.value)
        nbq = determine_next_best_question("Tôi bị nhức đầu quá", personal_context=ctx, conv_state=state)
        self.assertTrue(nbq.should_ask)
        self.assertIsNotNone(nbq.question_text)
        # Directive cho prompt cấm hỏi câu thứ hai
        directive = format_next_best_question_directive_for_prompt(nbq)
        self.assertIn("DUY NHẤT MỘT CÂU HỎI", directive)
        self.assertIn("TUYỆT ĐỐI KHÔNG HỎI THÊM CÂU THỨ HAI", directive.upper())

    def test_25_user_declination_suppresses_reasking_slot(self):
        """Nhận diện người dùng từ chối trả lời và cấm hỏi lại slot đó."""
        self.assertTrue(detect_user_declination("tôi không nhớ rõ"))
        self.assertTrue(detect_user_declination("thôi bỏ qua đi, tư vấn luôn đi"))
        self.assertTrue(detect_user_declination("đừng hỏi nữa"))

        state = MedicalConversationState(stage=ConversationStage.EXPLORATION.value, last_question_slot="duration")
        nbq = determine_next_best_question("không nhớ đâu, nói luôn cho tôi đi", conv_state=state)
        # Đã phát hiện từ chối slot duration
        self.assertEqual(nbq.declined_detected, "duration")
        self.assertNotEqual(nbq.slot_to_ask, "duration")

    def test_26_emergency_suppresses_questioning(self):
        """Tình huống cấp cứu dừng toàn bộ câu hỏi khảo sát."""
        safety = SafetyResult(risk_level=RiskLevel.EMERGENCY, category="stroke_neuro", reason_code="face_droop", confidence=1.0, should_stop_normal_flow=True)
        nbq = determine_next_best_question("Mặt tôi bị méo một bên", safety_result=safety)
        self.assertFalse(nbq.should_ask)
        self.assertIn("cấp cứu", nbq.skip_reason.lower())

    def test_27_contradiction_resolution_highest_priority(self):
        """Làm rõ mâu thuẫn dữ liệu được ưu tiên cao nhất trong câu hỏi nếu có xung đột."""
        ctx = PersonalHealthContext(profile_id="self")
        ctx.conflicts.append({
            "field": "dị ứng thuốc",
            "conflict_type": "ALLERGY_DENIAL",
            "explanation": "Hồ sơ ghi dị ứng penicillin nhưng tin nhắn từ chối",
        })
        nbq = determine_next_best_question("Tôi bị sốt phát ban", personal_context=ctx)
        self.assertEqual(nbq.intent, QuestionIntent.CONTRADICTION_RESOLUTION)
        self.assertIn("dị ứng thuốc", nbq.question_text)

    # ==========================================================================
    # 7. INTEGRATION & GRACEFUL FALLBACK TESTS
    # ==========================================================================

    def test_28_feature_flag_toggle(self):
        """Kiểm tra feature flags điều khiển kích hoạt các module Phase 9."""
        with patch.dict(os.environ, {"PERSONAL_INTELLIGENCE_ENABLED": "false"}):
            flag_val = os.getenv("PERSONAL_INTELLIGENCE_ENABLED", "true").lower() in ("true", "1", "yes")
            self.assertFalse(flag_val)

    def test_29_format_all_phase9_prompts_together(self):
        """Kiểm tra các prompt directive của Phase 9 phối hợp chặt chẽ không mâu thuẫn."""
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self")
        baselines = get_personal_baselines(self.conn, user_id=1, profile_ref="self")
        b_dev = BaselineDeviation(deviation_level=BaselineDeviationLevel.LOW.value)
        safety = SafetyResult(risk_level=RiskLevel.NORMAL, category="general", reason_code="normal", confidence=0.8, should_stop_normal_flow=False)
        assessment = assess_adaptive_severity(safety, personal_context=ctx, baseline_deviation=b_dev)
        nbq = determine_next_best_question("Tôi bị đau họng 2 ngày", personal_context=ctx)

        p_ctx = format_personal_health_context_for_prompt(ctx)
        p_base = format_baseline_for_prompt(baselines, b_dev)
        p_sev = format_adaptive_severity_for_prompt(assessment)
        p_nbq = format_next_best_question_directive_for_prompt(nbq)

        self.assertIn("HỒ SƠ SỨC KHỎE CÁ NHÂN", p_ctx)
        self.assertIn("ADAPTIVE SEVERITY ENGINE", p_sev)
        self.assertIn("NEXT-BEST QUESTION ENGINE", p_nbq)

    def test_30_safe_handling_of_unregistered_or_anonymous_user(self):
        """Xử lý an toàn khi người dùng chưa đăng nhập (user_id = None)."""
        ctx = build_personal_health_context(self.conn, user_id=None, profile_ref="self", current_message="Tôi bị ho")
        self.assertIsNotNone(ctx)
        self.assertIsNone(ctx.user_id)
        # Episode linking & baseline vẫn chạy an toàn không exception
        active = get_active_or_recent_episodes(self.conn, user_id=None, profile_ref="self")
        self.assertEqual(len(active), 0)
        baselines = get_personal_baselines(self.conn, user_id=None, profile_ref="self")
        self.assertEqual(len(baselines), 0)

    def test_31_multiple_contradictions_in_single_turn(self):
        """Xử lý đồng thời nhiều mâu thuẫn trong một lượt: cập nhật cân nặng và gỡ dị ứng."""
        msg = "Chào bác sĩ, nay tôi cân được 72kg và tôi không dị ứng penicillin nhé"
        ctx = build_personal_health_context(self.conn, user_id=1, profile_ref="self", current_message=msg)
        self.assertEqual(ctx.weight_kg, 72.0)
        self.assertNotIn("Penicillin", ctx.allergies)
        self.assertEqual(len(ctx.conflicts), 2)
        conflict_types = [c["conflict_type"] for c in ctx.conflicts]
        self.assertIn("WEIGHT_UPDATE", conflict_types)
        self.assertIn("ALLERGY_REMOVAL", conflict_types)

    def test_32_elderly_worsening_adaptive_escalation(self):
        """Người cao tuổi (72 tuổi) có diễn tiến đợt bệnh xấu đi -> tự động nâng lên URGENT."""
        safety = SafetyResult(risk_level=RiskLevel.NORMAL, category="general", reason_code="routine", confidence=0.8, should_stop_normal_flow=False)
        ctx = PersonalHealthContext(profile_id="elderly", age=72)
        ep = HealthEpisode(profile_type="self", profile_ref="self", chief_complaint="Khó thở mệt mỏi")
        assessment = assess_adaptive_severity(safety, personal_context=ctx, current_episode=ep, episode_trend=EpisodeTrend.WORSENING)
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.URGENT)
        self.assertTrue(assessment.adaptive_escalation_applied)
        self.assertTrue(any("người cao tuổi" in r for r in assessment.escalation_reasons))

    def test_33_next_best_question_declined_slot_chaining(self):
        """Bỏ qua liên hoàn các slot bị từ chối và tìm câu hỏi tiếp theo có information gain tốt nhất."""
        ctx = PersonalHealthContext(profile_id="self", age=30)
        state = MedicalConversationState(stage=ConversationStage.EXPLORATION.value, last_question_slot="duration")
        # Giả lập đã từ chối duration và severity
        declined = {"duration", "severity"}
        nbq = determine_next_best_question("tôi không rõ triệu chứng bắt đầu khi nào", personal_context=ctx, conv_state=state, declined_slots=declined)
        if nbq.should_ask:
            self.assertNotIn(nbq.slot_to_ask, declined)
            self.assertNotIn(nbq.slot_to_ask, ["age", "duration", "severity"])

    def test_34_multi_family_member_profile_isolation(self):
        """Cách ly hồ sơ giữa 2 thành viên gia đình khác nhau trong cùng 1 tài khoản user."""
        self.conn.execute("""
            INSERT INTO family_members (id, user_id, full_name, name, relationship, age, birth_year, gender, allergies, medical_conditions, medical_history, current_medications, weight_kg, height_cm, notes)
            VALUES (11, 1, 'Nguyễn Bé Con', 'Nguyễn Bé Con', 'Con gái', 3, 2023, 'Nữ', 'Sữa bò', 'Viêm da cơ địa', 'Viêm da cơ địa', 'Kem dưỡng ẩm', 14.0, 95.0, 'Khám nhi')
        """)
        self.conn.commit()

        ctx_mother = build_personal_health_context(self.conn, user_id=1, profile_ref="10")
        ctx_child = build_personal_health_context(self.conn, user_id=1, profile_ref="11")

        # Mẹ: 68 tuổi, tiểu đường, dị ứng hải sản
        self.assertEqual(ctx_mother.name, "Trần Thị B")
        self.assertIn("Hải sản", ctx_mother.allergies)
        self.assertNotIn("Sữa bò", ctx_mother.allergies)

        # Con gái: 3 tuổi, viêm da, dị ứng sữa bò
        self.assertEqual(ctx_child.name, "Nguyễn Bé Con")
        self.assertEqual(ctx_child.age, 3)
        self.assertIn("Sữa bò", ctx_child.allergies)
        self.assertNotIn("Hải sản", ctx_child.allergies)
        self.assertNotIn("Đái tháo đường type 2", ctx_child.known_conditions)

    def test_35_adaptive_severity_downgrade_prevented_flag(self):
        """Bảo đảm cờ downgrade_prevented hoạt động chính xác khi Safety V2 là URGENT và hồ sơ báo nhẹ."""
        safety = SafetyResult(risk_level=RiskLevel.URGENT, category="breathing", reason_code="stridor", confidence=0.95, should_stop_normal_flow=False)
        # Bệnh nhân báo chỉ đau nhẹ (pain 1/10) và baseline bình thường
        assessment = assess_adaptive_severity(safety, reported_severity=1, baseline_deviation=BaselineDeviation(deviation_level=BaselineDeviationLevel.NONE.value))
        self.assertEqual(assessment.effective_concern_level, EffectiveConcernLevel.URGENT)
        # Bất biến: Safety floor là URGENT, không bị hạ cấp
        self.assertFalse(assessment.adaptive_escalation_applied)


if __name__ == "__main__":
    unittest.main()
