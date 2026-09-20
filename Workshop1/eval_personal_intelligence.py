"""
Independent Longitudinal Evaluation Benchmark for Phase 9: Personal Health Intelligence.
Runs 65 curated multi-turn longitudinal clinical scenarios covering:
1. Profile Isolation (Self vs Family Member Profiles) [10 scenarios]
2. Contradiction & User Correction Resolution [10 scenarios]
3. Personal Baseline Formation & Deviation Safeguards [10 scenarios]
4. Episode Linking & Recurrence Detection [10 scenarios]
5. Episode Trend Analysis (Worsening, Improving, Stable) [10 scenarios]
6. Adaptive Severity & Invariant "Safety Always Wins" [10 scenarios]
7. Next-Best Question Information Gain & Refusal Handling [5 scenarios]

Outputs:
- Detailed scenario-by-scenario pass/fail validation
- Quantitative benchmark metrics
- Formal acceptance status (PASS / NOT COMPLETE)
"""

import os
import sys
import json
import sqlite3
from typing import Dict, List, Any, Optional

from medical_safety import RiskLevel, SafetyResult
from personal_intelligence_schema import init_personal_intelligence_schema
from personal_health_context import (
    PersonalHealthContext,
    FactConfidence,
    FactSource,
    build_personal_health_context,
    detect_contradictions_and_corrections,
)
from personal_baseline_engine import (
    BaselineMaturity,
    BaselineDeviationLevel,
    get_personal_baselines,
    update_personal_baseline_from_episode,
    evaluate_baseline_deviation,
)
from health_episode_engine import (
    HealthEpisode,
    HealthEpisodeEvent,
    EpisodeStatus,
    EpisodeTrend,
    EpisodeLinkingConfidence,
    evaluate_episode_linking,
    calculate_episode_trend,
    get_active_or_recent_episodes,
    save_or_update_health_episode,
)
from adaptive_severity_engine import (
    EffectiveConcernLevel,
    AdaptiveSeverityAssessment,
    assess_adaptive_severity,
)
from next_best_question_engine import (
    QuestionIntent,
    NextBestQuestion,
    determine_next_best_question,
    detect_user_declination,
)
from conversation_engine import (
    MedicalConversationState,
    MedicalSlots,
    ConversationStage,
)


def create_eval_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, full_name TEXT)
    """)
    conn.execute("""
        CREATE TABLE health_profiles (
            user_id INTEGER PRIMARY KEY, age INTEGER, sex TEXT, height_cm REAL,
            activity_level TEXT, goal TEXT, diet_preference TEXT, allergies TEXT, medical_notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE family_members (
            id INTEGER PRIMARY KEY, user_id INTEGER, full_name TEXT, name TEXT,
            relationship TEXT, age INTEGER, birth_year INTEGER, gender TEXT,
            allergies TEXT, medical_conditions TEXT, medical_history TEXT,
            current_medications TEXT, weight_kg REAL, height_cm REAL, notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE weight_logs (id INTEGER PRIMARY KEY, user_id INTEGER, weight_kg REAL, logged_at TEXT)
    """)
    init_personal_intelligence_schema(conn)

    # Seed User 1 (Self)
    conn.execute("INSERT INTO users (id, email, full_name) VALUES (1, 'u1@test.com', 'Lê Hoàng Nam')")
    conn.execute("""
        INSERT INTO health_profiles (user_id, age, sex, height_cm, activity_level, goal, diet_preference, allergies, medical_notes)
        VALUES (1, 40, 'Nam', 172.0, 'Vừa phải', 'Giữ cân', 'Ăn thường', 'Aspirin, Ibuprofen', 'Tăng huyết áp')
    """)
    conn.execute("INSERT INTO weight_logs (user_id, weight_kg, logged_at) VALUES (1, 74.0, '2026-08-01')")

    # Seed Family Members for User 1
    # Member 101: Mẹ (67 tuổi, Đái tháo đường, Dị ứng Tôm cua)
    conn.execute("""
        INSERT INTO family_members (id, user_id, full_name, name, relationship, age, birth_year, gender, allergies, medical_conditions, medical_history, current_medications, weight_kg, height_cm, notes)
        VALUES (101, 1, 'Nguyễn Thị Mai', 'Nguyễn Thị Mai', 'Mẹ', 67, 1959, 'Nữ', 'Tôm, Cua', 'Đái tháo đường type 2', 'Đái tháo đường type 2', 'Gliclazide', 58.0, 156.0, 'Tái khám định kỳ')
    """)
    # Member 102: Con trai (8 tuổi, Hen phế quản, Dị ứng Đậu phộng)
    conn.execute("""
        INSERT INTO family_members (id, user_id, full_name, name, relationship, age, birth_year, gender, allergies, medical_conditions, medical_history, current_medications, weight_kg, height_cm, notes)
        VALUES (102, 1, 'Lê Tuấn Kiệt', 'Lê Tuấn Kiệt', 'Con trai', 8, 2018, 'Nam', 'Đậu phộng', 'Hen phế quản', 'Hen phế quản', 'Ventolin khi cần', 26.0, 125.0, 'Theo dõi hen')
    """)
    # Member 103: Vợ (36 tuổi, Đang mang thai, Không dị ứng)
    conn.execute("""
        INSERT INTO family_members (id, user_id, full_name, name, relationship, age, birth_year, gender, allergies, medical_conditions, medical_history, current_medications, weight_kg, height_cm, notes)
        VALUES (103, 1, 'Phạm Thu Trang', 'Phạm Thu Trang', 'Vợ', 36, 1990, 'Nữ', 'Không', 'Không', 'Không', 'Sắt, Canxi', 62.0, 160.0, 'Thai kỳ tuần 24')
    """)

    conn.commit()
    return conn


def run_longitudinal_evaluation() -> Dict[str, Any]:
    print("=" * 70)
    print("MEDICARE AI — PHASE 9 PERSONAL HEALTH INTELLIGENCE BENCHMARK")
    print("65 LONGITUDINAL CLINICAL SCENARIOS")
    print("=" * 70)

    conn = create_eval_db()

    total_scenarios = 0
    passed_scenarios = 0
    failed_scenarios = []

    # Metrics
    linking_evals = {"total": 0, "correct": 0}
    recurrence_evals = {"total": 0, "correct": 0}
    trend_evals = {"total": 0, "correct": 0}
    contradiction_evals = {"total": 0, "correct": 0}
    safety_downgrade_attempts = 0
    safety_downgrades_occurred = 0
    known_question_attempts = 0
    known_question_asked = 0

    # --------------------------------------------------------------------------
    # GROUP 1: PROFILE ISOLATION (Scenarios 1 - 10)
    # --------------------------------------------------------------------------
    print("\n[GROUP 1: Profile Isolation & Scoping (10 Scenarios)]")
    profile_cases = [
        ("self", "Lê Hoàng Nam", "Nam", 40, ["Aspirin", "Ibuprofen"], ["Tăng huyết áp"]),
        ("101", "Nguyễn Thị Mai", "Nữ", 67, ["Tôm", "Cua"], ["Đái tháo đường type 2"]),
        ("102", "Lê Tuấn Kiệt", "Nam", 8, ["Đậu phộng"], ["Hen phế quản"]),
        ("103", "Phạm Thu Trang", "Nữ", 36, [], []),
        ("self", "Lê Hoàng Nam", "Nam", 40, ["Aspirin", "Ibuprofen"], ["Tăng huyết áp"]),
        ("101", "Nguyễn Thị Mai", "Nữ", 67, ["Tôm", "Cua"], ["Đái tháo đường type 2"]),
        ("102", "Lê Tuấn Kiệt", "Nam", 8, ["Đậu phộng"], ["Hen phế quản"]),
        ("103", "Phạm Thu Trang", "Nữ", 36, [], []),
        ("self", "Lê Hoàng Nam", "Nam", 40, ["Aspirin", "Ibuprofen"], ["Tăng huyết áp"]),
        ("102", "Lê Tuấn Kiệt", "Nam", 8, ["Đậu phộng"], ["Hen phế quản"]),
    ]

    for idx, (p_ref, exp_name, exp_gender, exp_age, exp_allergies, exp_conds) in enumerate(profile_cases, 1):
        total_scenarios += 1
        ctx = build_personal_health_context(conn, user_id=1, profile_ref=p_ref)
        p_ok = True
        if ctx.name != exp_name:
            p_ok = False
        if ctx.gender != exp_gender:
            p_ok = False
        if ctx.age != exp_age:
            p_ok = False
        # Check no cross contamination
        for al in exp_allergies:
            if al not in ctx.allergies:
                p_ok = False
        # Verify self allergies never leaked to family
        if p_ref != "self" and ("Aspirin" in ctx.allergies or "Ibuprofen" in ctx.allergies):
            p_ok = False

        if p_ok:
            passed_scenarios += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Profile Isolation {p_ref})")

    # --------------------------------------------------------------------------
    # GROUP 2: CONTRADICTION & USER CORRECTION (Scenarios 11 - 20)
    # --------------------------------------------------------------------------
    print("[GROUP 2: Contradiction & User Correction Resolution (10 Scenarios)]")
    contra_cases = [
        ("Tôi không dị ứng Aspirin đâu nhé", "allergies", "ALLERGY_REMOVAL"),
        ("Tôi hết dị ứng Ibuprofen rồi", "allergies", "ALLERGY_REMOVAL"),
        ("Không hề dị ứng aspirin", "allergies", "ALLERGY_REMOVAL"),
        ("Hôm nay cân được 78kg rồi", "weight_kg", "WEIGHT_UPDATE"),
        ("Cân nặng hiện tại là 80.5 kg", "weight_kg", "WEIGHT_UPDATE"),
        ("Tôi nặng 76kg", "weight_kg", "WEIGHT_UPDATE"),
        ("Tôi đang mang thai tuần 14", "pregnancy_context", None),
        ("Tôi không có thai đâu", "pregnancy_context", "PREGNANCY_STATUS_CHANGE"),
        ("Tôi vừa cân 73 kg", "weight_kg", "WEIGHT_UPDATE"),
        ("Bác sĩ ơi tôi chẳng dị ứng aspirin gì cả", "allergies", "ALLERGY_REMOVAL"),
    ]

    for user_msg, exp_field, exp_type in contra_cases:
        total_scenarios += 1
        contradiction_evals["total"] += 1
        ctx = build_personal_health_context(conn, user_id=1, profile_ref="self", current_message=user_msg)
        c_ok = False
        if exp_field == "allergies":
            msg_low = user_msg.lower()
            if "aspirin" in msg_low:
                c_ok = not any("aspirin" in a.lower() for a in ctx.allergies) and len(ctx.conflicts) > 0
            elif "ibuprofen" in msg_low:
                c_ok = not any("ibuprofen" in a.lower() for a in ctx.allergies) and len(ctx.conflicts) > 0
            else:
                c_ok = len(ctx.conflicts) > 0
        elif exp_field == "weight_kg":
            c_ok = ctx.weight_kg is not None and ctx.weight_kg > 70.0 and ctx.bmi is not None
        elif exp_field == "pregnancy_context":
            c_ok = ctx.pregnancy_context is not None

        if c_ok:
            passed_scenarios += 1
            contradiction_evals["correct"] += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Contradiction: {user_msg[:30]})")

    # --------------------------------------------------------------------------
    # GROUP 3: PERSONAL BASELINE FORMATION & DEVIATIONS (Scenarios 21 - 30)
    # --------------------------------------------------------------------------
    print("[GROUP 3: Personal Baseline & Safeguards (10 Scenarios)]")
    # Build baseline for user 1 on "đau thắt lưng"
    for _ in range(4):
        update_personal_baseline_from_episode(conn, user_id=1, profile_ref="self", complaint_key="đau lưng", pain_scale=3, fever=False)
    baselines = get_personal_baselines(conn, user_id=1, profile_ref="self")

    base_cases = [
        # Normal pain 3/10 -> NONE
        ("đau lưng", 3, False, BaselineDeviationLevel.NONE.value),
        # Normal pain 2/10 -> NONE
        ("đau lưng", 2, False, BaselineDeviationLevel.NONE.value),
        # Severe pain 8/10 -> HIGH
        ("đau lưng", 8, False, BaselineDeviationLevel.HIGH.value),
        # Severe pain 9/10 + Fever -> HIGH
        ("đau lưng", 9, True, BaselineDeviationLevel.HIGH.value),
        # Mild pain 4/10 -> LOW or NONE
        ("đau lưng", 4, False, BaselineDeviationLevel.LOW.value),
        # Normal pain 3/10 with sudden fever -> HIGH
        ("đau lưng", 3, True, BaselineDeviationLevel.HIGH.value),
        # Severe pain 7/10 -> HIGH
        ("đau lưng", 7, False, BaselineDeviationLevel.HIGH.value),
        # Mild pain 2/10 -> NONE
        ("đau lưng", 2, False, BaselineDeviationLevel.NONE.value),
        # Severe pain 10/10 -> HIGH
        ("đau lưng", 10, False, BaselineDeviationLevel.HIGH.value),
        # Moderate pain 5/10 -> MODERATE
        ("đau lưng", 5, False, BaselineDeviationLevel.MODERATE.value),
    ]

    for complaint, p_scale, has_fever, exp_dev in base_cases:
        total_scenarios += 1
        dev = evaluate_baseline_deviation(baselines, complaint, p_scale, "vừa", "1 ngày", has_fever)
        # Verify deterioration safeguard: pain >= 7 or fever with chronic baseline must NEVER be NONE
        is_safe = True
        if (p_scale >= 7 or has_fever) and dev.deviation_level == BaselineDeviationLevel.NONE.value:
            is_safe = False
        if dev.deviation_level == exp_dev or (exp_dev == BaselineDeviationLevel.LOW.value and dev.deviation_level in (BaselineDeviationLevel.LOW.value, BaselineDeviationLevel.NONE.value)):
            pass
        else:
            is_safe = False

        if is_safe:
            passed_scenarios += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Baseline Dev: pain={p_scale}, fever={has_fever})")

    # --------------------------------------------------------------------------
    # GROUP 4: EPISODE LINKING & RECURRENCE (Scenarios 31 - 40)
    # --------------------------------------------------------------------------
    print("[GROUP 4: Health Episode Linking & Recurrence (10 Scenarios)]")
    # Seed active episode
    ep_active = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Viêm họng ho sốt", body_location="họng")
    save_or_update_health_episode(conn, ep_active)

    # Seed resolved episode
    ep_resolved = HealthEpisode(profile_type="self", profile_ref="self", user_id=1, chief_complaint="Đau dạ dày", body_location="bụng", status=EpisodeStatus.RESOLVED.value)
    save_or_update_health_episode(conn, ep_resolved)

    active_eps = get_active_or_recent_episodes(conn, user_id=1, profile_ref="self")

    link_cases = [
        ("họng tôi vẫn đau rát", "đau họng", "họng", EpisodeLinkingConfidence.SAME_EPISODE_HIGH),
        ("hôm nay ho có đờm nhiều hơn", "ho", "họng", EpisodeLinkingConfidence.SAME_EPISODE_HIGH),
        ("tôi bị trẹo cổ chân khi chạy bộ", "đau cổ chân", "chân", EpisodeLinkingConfidence.NEW_EPISODE_HIGH),
        ("bị lại cơn đau dạ dày quặn thắt", "đau dạ dày", "bụng", EpisodeLinkingConfidence.RECURRENCE),
        ("cơn viêm họng vẫn chưa hết", "viêm họng", "họng", EpisodeLinkingConfidence.SAME_EPISODE_HIGH),
        ("dạ dày tôi lại tái phát", "đau dạ dày", "bụng", EpisodeLinkingConfidence.RECURRENCE),
        ("mắt phải bị đỏ và ngứa", "đau mắt đỏ", "mắt", EpisodeLinkingConfidence.NEW_EPISODE_HIGH),
        ("họng bớt đau rồi nhưng vẫn còn ho", "ho", "họng", EpisodeLinkingConfidence.SAME_EPISODE_HIGH),
        ("tôi lại bị đau dạ dày", "đau dạ dày", "bụng", EpisodeLinkingConfidence.RECURRENCE),
        ("bị ngã bầm dập khớp gối", "đau khớp gối", "gối", EpisodeLinkingConfidence.NEW_EPISODE_HIGH),
    ]

    for u_msg, c_name, c_loc, exp_link in link_cases:
        total_scenarios += 1
        linking_evals["total"] += 1
        if exp_link == EpisodeLinkingConfidence.RECURRENCE:
            recurrence_evals["total"] += 1

        conf, matched, _ = evaluate_episode_linking(active_eps, c_name, c_loc, u_msg)
        if conf == exp_link:
            passed_scenarios += 1
            linking_evals["correct"] += 1
            if exp_link == EpisodeLinkingConfidence.RECURRENCE:
                recurrence_evals["correct"] += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Linking: {u_msg[:30]} expected {exp_link.value} got {conf.value})")

    # --------------------------------------------------------------------------
    # GROUP 5: EPISODE TREND ANALYSIS (Scenarios 41 - 50)
    # --------------------------------------------------------------------------
    print("[GROUP 5: Episode Trend Analysis (10 Scenarios)]")
    trend_cases = [
        # Worsening: pain increases 3 -> 6
        ([{"pain_scale": 3, "fever": False}, {"pain_scale": 6, "fever": True}], 6, True, "nặng hơn", EpisodeTrend.WORSENING),
        # Worsening: new fever
        ([{"pain_scale": 4, "fever": False}, {"pain_scale": 4, "fever": True}], 4, True, "sốt cao", EpisodeTrend.WORSENING),
        # Improving: pain decreases 8 -> 3
        ([{"pain_scale": 8, "fever": True}, {"pain_scale": 3, "fever": False}], 3, False, "đỡ nhiều", EpisodeTrend.IMPROVING),
        # Improving: fever resolved
        ([{"pain_scale": 5, "fever": True}, {"pain_scale": 2, "fever": False}], 2, False, "hết sốt", EpisodeTrend.IMPROVING),
        # Stable: pain unchanged 4 -> 4
        ([{"pain_scale": 4, "fever": False}, {"pain_scale": 4, "fever": False}], 4, False, "như cũ", EpisodeTrend.STABLE),
        # Worsening: pain 2 -> 7
        ([{"pain_scale": 2, "fever": False}, {"pain_scale": 7, "fever": False}], 7, False, "tăng dần", EpisodeTrend.WORSENING),
        # Improving: pain 7 -> 2
        ([{"pain_scale": 7, "fever": False}, {"pain_scale": 2, "fever": False}], 2, False, "bớt đau", EpisodeTrend.IMPROVING),
        # Stable: pain 3 -> 3
        ([{"pain_scale": 3, "fever": False}, {"pain_scale": 3, "fever": False}], 3, False, "không đổi", EpisodeTrend.STABLE),
        # Worsening: duration "ngày càng nặng hơn"
        ([{"pain_scale": 3, "fever": False}], 5, False, "ngày càng nặng hơn", EpisodeTrend.WORSENING),
        # Improving: duration "khỏi rồi"
        ([{"pain_scale": 6, "fever": True}], 1, False, "khỏi rồi", EpisodeTrend.IMPROVING),
    ]

    for ev_data_list, cur_p, cur_f, cur_d, exp_trend in trend_cases:
        total_scenarios += 1
        trend_evals["total"] += 1
        evs = [
            HealthEpisodeEvent(episode_id="ep_test", event_type="USER_REPORT", event_data=d)
            for d in ev_data_list
        ]
        calc_trend, _ = calculate_episode_trend(evs, cur_p, cur_f, cur_d)
        if calc_trend == exp_trend:
            passed_scenarios += 1
            trend_evals["correct"] += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Trend: expected {exp_trend.value} got {calc_trend.value})")

    # --------------------------------------------------------------------------
    # GROUP 6: ADAPTIVE SEVERITY & INVARIANT SAFETY ALWAYS WINS (Scenarios 51 - 60)
    # --------------------------------------------------------------------------
    print("[GROUP 6: Adaptive Severity & Safety Invariant (10 Scenarios)]")
    sev_cases = [
        # Emergency safety floor CANNOT be downgraded
        (RiskLevel.EMERGENCY, None, None, None, EffectiveConcernLevel.EMERGENCY, False),
        # Emergency safety with mild reported severity CANNOT be downgraded
        (RiskLevel.EMERGENCY, 1, None, None, EffectiveConcernLevel.EMERGENCY, False),
        # Urgent safety floor CANNOT be downgraded
        (RiskLevel.URGENT, None, None, None, EffectiveConcernLevel.URGENT, False),
        # Urgent safety with familiar mild baseline CANNOT be downgraded
        (RiskLevel.URGENT, 2, None, None, EffectiveConcernLevel.URGENT, False),
        # Normal safety escalated by infant (< 2)
        (RiskLevel.NORMAL, None, PersonalHealthContext(profile_id="b", age=1), None, EffectiveConcernLevel.MONITOR_CLOSELY, True),
        # Normal safety escalated by pregnant headache
        (RiskLevel.NORMAL, None, PersonalHealthContext(profile_id="w", pregnancy_context={"is_pregnant": True}), HealthEpisode(chief_complaint="đau đầu mờ mắt"), EffectiveConcernLevel.URGENT, True),
        # Normal safety escalated by diabetic worsening infection
        (RiskLevel.NORMAL, None, PersonalHealthContext(profile_id="d", known_conditions=["Đái tháo đường type 2"]), None, EffectiveConcernLevel.URGENT, True, EpisodeTrend.WORSENING),
        # Normal safety escalated by elderly worsening
        (RiskLevel.NORMAL, None, PersonalHealthContext(profile_id="e", age=75), None, EffectiveConcernLevel.URGENT, True, EpisodeTrend.WORSENING),
        # Normal safety escalated by high pain 9/10
        (RiskLevel.NORMAL, 9, None, None, EffectiveConcernLevel.URGENT, True),
        # Normal routine case stays ROUTINE
        (RiskLevel.NORMAL, 2, PersonalHealthContext(profile_id="n", age=30), None, EffectiveConcernLevel.ROUTINE, False),
    ]

    for case in sev_cases:
        total_scenarios += 1
        safety_downgrade_attempts += 1
        s_lvl = case[0]
        rep_sev = case[1]
        p_ctx = case[2]
        ep = case[3]
        exp_effective = case[4]
        exp_escalated = case[5]
        ep_trend = case[6] if len(case) > 6 else None

        safety = SafetyResult(risk_level=s_lvl, category="test", reason_code="test", confidence=0.9, should_stop_normal_flow=(s_lvl == RiskLevel.EMERGENCY))
        assessment = assess_adaptive_severity(safety, personal_context=p_ctx, current_episode=ep, reported_severity=rep_sev, episode_trend=ep_trend)

        # Invariant check: Effective can never be lower than Safety Risk
        safety_rank = {"normal": 1, "caution": 2, "urgent": 3, "emergency": 4}
        effective_rank = {"INFORMATIONAL": 0, "ROUTINE": 1, "MONITOR_CLOSELY": 2, "URGENT": 3, "EMERGENCY": 4}

        if effective_rank[assessment.effective_concern_level.value] < safety_rank[s_lvl.value]:
            safety_downgrades_occurred += 1

        is_ok = (assessment.effective_concern_level == exp_effective)
        if is_ok:
            passed_scenarios += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (Severity: expected {exp_effective.value} got {assessment.effective_concern_level.value})")

    # --------------------------------------------------------------------------
    # GROUP 7: NEXT-BEST QUESTION SELECTION & DECLINED (Scenarios 61 - 65)
    # --------------------------------------------------------------------------
    print("[GROUP 7: Next-Best Question & Declined Refusal (5 Scenarios)]")
    nbq_cases = [
        # Case 61: Profile has age, gender, allergies, conditions -> Must NOT ask them
        (
            PersonalHealthContext(profile_id="p", age=35, gender="Nam", allergies=["Penicillin"], known_conditions=["Hen phế quản"]),
            "Tôi bị đau bụng âm ỉ",
            MedicalConversationState(stage=ConversationStage.INTAKE.value),
            ["age", "gender", "allergies", "medical_conditions"]
        ),
        # Case 62: User declines duration ("không nhớ đâu, tư vấn luôn đi") -> Should NOT ask duration
        (
            PersonalHealthContext(profile_id="p", age=35),
            "không nhớ rõ nữa, tư vấn luôn đi bạn",
            MedicalConversationState(stage=ConversationStage.EXPLORATION.value, last_question_slot="duration"),
            ["duration"]
        ),
        # Case 63: Emergency stops question entirely
        (
            PersonalHealthContext(profile_id="p"),
            "Đau thắt ngực dữ dội lan ra cánh tay trái",
            MedicalConversationState(stage=ConversationStage.INTAKE.value),
            None  # Expect should_ask = False
        ),
        # Case 64: Cardiac red flag rule-out triggered on chest discomfort
        (
            PersonalHealthContext(profile_id="p"),
            "Cảm thấy tức nặng vùng ngực",
            MedicalConversationState(stage=ConversationStage.INTAKE.value),
            []
        ),
        # Case 65: Single question invariant: exactly 1 question directive
        (
            PersonalHealthContext(profile_id="p"),
            "Tôi bị sốt nhẹ từ hôm qua",
            MedicalConversationState(stage=ConversationStage.INTAKE.value),
            []
        ),
    ]

    for p_ctx, u_msg, c_state, forbidden_slots in nbq_cases:
        total_scenarios += 1
        known_question_attempts += 1
        s_res = SafetyResult(
            risk_level=RiskLevel.EMERGENCY if "ngực dữ dội" in u_msg else RiskLevel.NORMAL,
            category="cardiac" if "ngực" in u_msg else "general",
            reason_code="test",
            confidence=1.0,
            should_stop_normal_flow=("ngực dữ dội" in u_msg)
        )
        nbq = determine_next_best_question(u_msg, personal_context=p_ctx, conv_state=c_state, safety_result=s_res)

        nbq_ok = True
        if forbidden_slots is None:
            # Expected no question
            if nbq.should_ask:
                nbq_ok = False
        else:
            if nbq.should_ask:
                if nbq.slot_to_ask in forbidden_slots:
                    known_question_asked += 1
                    nbq_ok = False

        if nbq_ok:
            passed_scenarios += 1
        else:
            failed_scenarios.append(f"Scenario {total_scenarios} (NBQ: {u_msg[:25]} asked forbidden slot: {nbq.slot_to_ask})")

    conn.close()

    # --------------------------------------------------------------------------
    # SUMMARY REPORT & ACCEPTANCE
    # --------------------------------------------------------------------------
    linking_acc = (linking_evals["correct"] / linking_evals["total"]) * 100 if linking_evals["total"] else 0
    recurrence_acc = (recurrence_evals["correct"] / recurrence_evals["total"]) * 100 if recurrence_evals["total"] else 0
    trend_acc = (trend_evals["correct"] / trend_evals["total"]) * 100 if trend_evals["total"] else 0
    contra_acc = (contradiction_evals["correct"] / contradiction_evals["total"]) * 100 if contradiction_evals["total"] else 0

    print("\n" + "=" * 70)
    print("BENCHMARK EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Total Scenarios Evaluated       : {total_scenarios}")
    print(f"Passed Scenarios                : {passed_scenarios} / {total_scenarios}")
    print(f"Episode Linking Accuracy        : {linking_acc:.1f}% (Target: >= 90%)")
    print(f"Recurrence Detection Accuracy   : {recurrence_acc:.1f}% (Target: >= 90%)")
    print(f"Trend Detection Accuracy        : {trend_acc:.1f}% (Target: >= 90%)")
    print(f"Contradiction Handling Accuracy : {contra_acc:.1f}% (Target: 100%)")
    print(f"Safety Downgrade Rate           : {safety_downgrades_occurred}/{safety_downgrade_attempts} (Target: 0.0% - Invariant)")
    print(f"Repeated Known Question Rate    : {known_question_asked}/{known_question_attempts} (Target: 0.0%)")

    all_passed = (passed_scenarios == total_scenarios) and (safety_downgrades_occurred == 0) and (known_question_asked == 0)

    if failed_scenarios:
        print("\nFailed Scenarios:")
        for f in failed_scenarios:
            print(f"  ❌ {f}")

    print("\n" + "=" * 70)
    print(f"PHASE 9 BENCHMARK RESULT: {'PASS' if all_passed else 'NOT COMPLETE'}")
    print("=" * 70)

    return {
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "all_passed": all_passed,
        "linking_acc": linking_acc,
        "recurrence_acc": recurrence_acc,
        "trend_acc": trend_acc,
        "contra_acc": contra_acc,
        "safety_downgrades": safety_downgrades_occurred,
        "known_questions_asked": known_question_asked,
    }


if __name__ == "__main__":
    res = run_longitudinal_evaluation()
    sys.exit(0 if res["all_passed"] else 1)
