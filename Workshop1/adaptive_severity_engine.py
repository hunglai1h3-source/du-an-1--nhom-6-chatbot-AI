"""
Module Adaptive Severity Engine cho MediCare AI (Phase 9 - Checkpoint E).
Kết hợp kết quả từ Medical Safety V2, Personal Baseline Deviation, Episode Trend,
và Bối cảnh bệnh nhân (Tuổi, Thai kỳ, Bệnh mạn tính) để xác định mức độ quan ngại lâm sàng.

BẤT BIẾN CỐT LÕI (INVIOLABLE): SAFETY ALWAYS WINS.
Mức độ an toàn từ Medical Safety V2 luôn là sàn (floor). Cá nhân hóa KHÔNG BAO GIỜ
được phép hạ cấp (downgrade) cấp độ rủi ro từ Safety V2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from medical_safety import RiskLevel, SafetyResult
from personal_health_context import PersonalHealthContext
from personal_baseline_engine import BaselineDeviationLevel, BaselineDeviation
from health_episode_engine import EpisodeTrend, HealthEpisode


class EffectiveConcernLevel(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    ROUTINE = "ROUTINE"
    MONITOR_CLOSELY = "MONITOR_CLOSELY"
    URGENT = "URGENT"
    EMERGENCY = "EMERGENCY"


CONCERN_RANK: Dict[EffectiveConcernLevel, int] = {
    EffectiveConcernLevel.INFORMATIONAL: 0,
    EffectiveConcernLevel.ROUTINE: 1,
    EffectiveConcernLevel.MONITOR_CLOSELY: 2,
    EffectiveConcernLevel.URGENT: 3,
    EffectiveConcernLevel.EMERGENCY: 4,
}

SAFETY_RISK_TO_CONCERN: Dict[RiskLevel, EffectiveConcernLevel] = {
    RiskLevel.NORMAL: EffectiveConcernLevel.ROUTINE,
    RiskLevel.CAUTION: EffectiveConcernLevel.MONITOR_CLOSELY,
    RiskLevel.URGENT: EffectiveConcernLevel.URGENT,
    RiskLevel.EMERGENCY: EffectiveConcernLevel.EMERGENCY,
}


@dataclass
class AdaptiveSeverityAssessment:
    effective_concern_level: EffectiveConcernLevel
    base_safety_level: str
    adaptive_escalation_applied: bool
    escalation_reasons: List[str] = field(default_factory=list)
    downgrade_prevented: bool = False
    clinical_rationale: str = ""
    monitoring_interval_hours: Optional[int] = None
    red_flag_triggers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effective_concern_level": self.effective_concern_level.value,
            "base_safety_level": self.base_safety_level,
            "adaptive_escalation_applied": self.adaptive_escalation_applied,
            "escalation_reasons": self.escalation_reasons,
            "downgrade_prevented": self.downgrade_prevented,
            "clinical_rationale": self.clinical_rationale,
            "monitoring_interval_hours": self.monitoring_interval_hours,
            "red_flag_triggers": self.red_flag_triggers,
        }


def assess_adaptive_severity(
    safety_result: Optional[SafetyResult],
    personal_context: Optional[PersonalHealthContext] = None,
    baseline_deviation: Optional[BaselineDeviation] = None,
    current_episode: Optional[HealthEpisode] = None,
    episode_trend: Optional[EpisodeTrend] = None,
    reported_severity: Optional[int] = None,
    duration_days: Optional[float] = None,
) -> AdaptiveSeverityAssessment:
    """
    Đánh giá mức độ quan ngại lâm sàng kết hợp ngữ cảnh cá nhân hóa.
    Đảm bảo tuyệt đối: SAFETY ALWAYS WINS.
    """
    # 1. Xác định mức sàn an toàn từ Safety V2
    if safety_result is not None and hasattr(safety_result, "risk_level"):
        base_risk_level = safety_result.risk_level
        if isinstance(base_risk_level, str):
            try:
                base_risk_level = RiskLevel(base_risk_level)
            except ValueError:
                base_risk_level = RiskLevel.NORMAL
    else:
        base_risk_level = RiskLevel.NORMAL

    safety_floor_concern = SAFETY_RISK_TO_CONCERN.get(
        base_risk_level, EffectiveConcernLevel.ROUTINE
    )

    escalation_reasons: List[str] = []
    red_flags: List[str] = []
    candidate_level = safety_floor_concern
    downgrade_prevented = False

    # 2. Khảo sát yếu tố tổn thương từ bối cảnh người bệnh (Vulnerability Factors)
    is_infant = False
    is_elderly = False
    is_pregnant = False
    has_diabetes = False
    has_cardiovascular = False
    has_immunocompromised = False

    if personal_context:
        # Tuổi
        age = personal_context.age
        if age is not None:
            if age < 2:
                is_infant = True
            elif age >= 65:
                is_elderly = True

        # Thai kỳ
        if personal_context.pregnancy_context:
            is_preg = personal_context.pregnancy_context.get("is_pregnant")
            if is_preg is True:
                is_pregnant = True
            elif isinstance(is_preg, str) and is_preg.lower() not in ("không mang thai", "false", "no", "chưa từng", "không"):
                is_pregnant = True

        # Bệnh mạn tính
        conditions = personal_context.known_conditions or []
        cond_text = " ".join([str(c).lower() for c in conditions])
        if "đái tháo đường" in cond_text or "tiểu đường" in cond_text or "diabetes" in cond_text:
            has_diabetes = True
        if any(w in cond_text for w in ("tăng huyết áp", "tim mạch", "suy tim", "hypertension", "mạch vành")):
            has_cardiovascular = True
        if any(w in cond_text for w in ("suy giảm miễn dịch", "ghép tạng", "ung thư", "corticoid", "hiv")):
            has_immunocompromised = True

    # 3. Đánh giá độ lệch nền (Baseline Deviation)
    dev_level = baseline_deviation.deviation_level if baseline_deviation else BaselineDeviationLevel.NONE
    if dev_level == BaselineDeviationLevel.HIGH:
        escalation_reasons.append("Độ lệch rất lớn so với đường nền quen thuộc của người bệnh (đau dữ dội hoặc triệu chứng cấp bất thường)")
        if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.URGENT]:
            candidate_level = EffectiveConcernLevel.URGENT
    elif dev_level == BaselineDeviationLevel.MODERATE:
        escalation_reasons.append("Triệu chứng vượt ngưỡng dao động bình thường của bệnh nhân")
        if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.MONITOR_CLOSELY]:
            candidate_level = EffectiveConcernLevel.MONITOR_CLOSELY

    # 4. Đánh giá diễn tiến đợt bệnh (Episode Trend)
    effective_trend = episode_trend or getattr(current_episode, "trend", None) or EpisodeTrend.NEW
    if effective_trend == EpisodeTrend.WORSENING:
        escalation_reasons.append("Diễn tiến triệu chứng đang xấu đi rõ rệt qua các lần ghi nhận")
        if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.MONITOR_CLOSELY]:
            candidate_level = EffectiveConcernLevel.MONITOR_CLOSELY
        # Nếu đang xấu đi kèm độ lệch cao hoặc người bệnh nhóm nguy cơ
        if (is_infant or is_elderly or is_pregnant or has_immunocompromised) and CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.URGENT]:
            candidate_level = EffectiveConcernLevel.URGENT
            escalation_reasons.append("Diễn tiến xấu đi trên nhóm đối tượng dễ tổn thương (trẻ nhỏ / người cao tuổi / phụ nữ mang thai)")

    # 5. Thời gian kéo dài (Duration)
    if duration_days is not None and duration_days >= 7:
        if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.MONITOR_CLOSELY]:
            candidate_level = EffectiveConcernLevel.MONITOR_CLOSELY
            escalation_reasons.append(f"Triệu chứng kéo dài dai dẳng ({duration_days:.0f} ngày) cần đánh giá y tế trực tiếp")

    # 6. Mức độ đau / khó chịu tự báo cáo
    if reported_severity is not None:
        if reported_severity >= 8:
            escalation_reasons.append(f"Điểm đau/mức độ tự báo cáo rất cao ({reported_severity}/10)")
            if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.URGENT]:
                candidate_level = EffectiveConcernLevel.URGENT
        elif reported_severity >= 6:
            if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.MONITOR_CLOSELY]:
                candidate_level = EffectiveConcernLevel.MONITOR_CLOSELY
                escalation_reasons.append(f"Điểm khó chịu mức độ trung bình-nặng ({reported_severity}/10)")

    # 7. Đối tượng đặc thù (Nhũ nhi, Thai kỳ, Bệnh mạn tính nặng)
    if is_infant:
        if candidate_level == EffectiveConcernLevel.ROUTINE:
            candidate_level = EffectiveConcernLevel.MONITOR_CLOSELY
            escalation_reasons.append("Bệnh nhân là trẻ sơ sinh/nhũ nhi (< 2 tuổi), diễn tiến bệnh có thể chuyển biến rất nhanh")

    if is_pregnant:
        # Nếu thai kỳ có đau đầu hoặc phù hoặc đau bụng
        if current_episode and any(w in (current_episode.chief_complaint or "").lower() for w in ("đầu", "bụng", "phù", "mắt", "mờ", "chóng mặt")):
            if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.URGENT]:
                candidate_level = EffectiveConcernLevel.URGENT
                escalation_reasons.append("Phụ nữ có thai xuất hiện triệu chứng liên quan đau đầu/đau bụng/phù (nguy cơ tiền sản giật/sản khoa)")

    if (has_diabetes or has_immunocompromised) and effective_trend == EpisodeTrend.WORSENING:
        if CONCERN_RANK[candidate_level] < CONCERN_RANK[EffectiveConcernLevel.URGENT]:
            candidate_level = EffectiveConcernLevel.URGENT
            escalation_reasons.append("Bệnh nhân đái tháo đường / suy giảm miễn dịch có diễn biến nhiễm trùng hoặc triệu chứng xấu đi")

    # 8. BẤT BIẾN CỐT LÕI: SAFETY ALWAYS WINS
    final_effective_level = candidate_level
    if CONCERN_RANK[final_effective_level] < CONCERN_RANK[safety_floor_concern]:
        # Cá nhân hóa đưa ra mức thấp hơn an toàn -> ngăn chặn hạ cấp
        final_effective_level = safety_floor_concern
        downgrade_prevented = True

    adaptive_escalation_applied = (
        CONCERN_RANK[final_effective_level] > CONCERN_RANK[safety_floor_concern]
    )

    # 9. Xác định khoảng thời gian theo dõi khuyến nghị (Monitoring Interval)
    monitoring_interval_hours: Optional[int] = None
    if final_effective_level == EffectiveConcernLevel.EMERGENCY:
        monitoring_interval_hours = 0  # Cấp cứu ngay lập tức
    elif final_effective_level == EffectiveConcernLevel.URGENT:
        monitoring_interval_hours = 2  # Thăm khám trong vòng vài giờ
    elif final_effective_level == EffectiveConcernLevel.MONITOR_CLOSELY:
        monitoring_interval_hours = 6  # Đánh giá lại trong 4 - 6 giờ
    elif final_effective_level == EffectiveConcernLevel.ROUTINE:
        monitoring_interval_hours = 24  # Theo dõi thông thường 24 giờ

    # 10. Rationale tóm tắt
    rationale_parts = []
    rationale_parts.append(f"Mức an toàn Safety V2: {base_risk_level.value.upper()}.")
    if adaptive_escalation_applied:
        rationale_parts.append(f"Đã nâng lên {final_effective_level.value} do: {'; '.join(escalation_reasons)}.")
    elif downgrade_prevented:
        rationale_parts.append(f"Giữ nguyên mức {final_effective_level.value} (Nguyên tắc Safety Always Wins ngăn hạ cấp).")
    else:
        rationale_parts.append(f"Mức quan ngại cuối: {final_effective_level.value}.")

    return AdaptiveSeverityAssessment(
        effective_concern_level=final_effective_level,
        base_safety_level=base_risk_level.value,
        adaptive_escalation_applied=adaptive_escalation_applied,
        escalation_reasons=escalation_reasons,
        downgrade_prevented=downgrade_prevented,
        clinical_rationale=" ".join(rationale_parts),
        monitoring_interval_hours=monitoring_interval_hours,
        red_flag_triggers=red_flags,
    )


def format_adaptive_severity_for_prompt(assessment: AdaptiveSeverityAssessment) -> str:
    """
    Định dạng kết quả đánh giá Adaptive Severity thành chỉ thị lâm sàng cho LLM.
    """
    lines = [
        "ĐÁNH GIÁ MỨC ĐỘ QUAN NGẠI LÂM SÀNG (ADAPTIVE SEVERITY ENGINE):",
        f"- Cấp độ thực tế: {assessment.effective_concern_level.value}",
        f"- Căn cứ Safety V2: {assessment.base_safety_level.upper()}",
    ]

    if assessment.adaptive_escalation_applied:
        lines.append(f"- Nâng mức cảnh báo do: {', '.join(assessment.escalation_reasons)}")

    if assessment.monitoring_interval_hours is not None:
        if assessment.monitoring_interval_hours == 0:
            lines.append("- Khuyến nghị: CẦN TIẾP CẬN Y TẾ KHẨN CẤP / CẤP CỨU NGAY.")
        elif assessment.monitoring_interval_hours <= 2:
            lines.append("- Khuyến nghị: Cần thăm khám y tế sớm trong vòng vài giờ.")
        elif assessment.monitoring_interval_hours <= 6:
            lines.append(f"- Khuyến nghị: Theo dõi sát diễn biến trong {assessment.monitoring_interval_hours} giờ tới.")
        else:
            lines.append("- Khuyến nghị: Chăm sóc và theo dõi thông thường tại nhà.")

    lines.append(
        "- QUY TẮC BẮT BUỘC: Không tự khẳng định chẩn đoán bệnh cụ thể. "
        "Nêu rõ các dấu hiệu cảnh báo cần theo dõi hoặc khuyến nghị người dùng đi khám phù hợp với mức độ trên."
    )

    return "\n".join(lines)


def log_adaptive_severity_assessment(
    connection: Any,
    user_id: Optional[int],
    profile_id: Optional[str],
    conversation_id: Optional[str],
    assessment: AdaptiveSeverityAssessment,
    client_message_id: Optional[str] = None,
) -> None:
    """
    Lưu nhật ký kiểm toán đánh giá Adaptive Severity vào bảng adaptive_severity_logs.
    Hỗ trợ cả PostgreSQL và SQLite.
    """
    if connection is None:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        is_postgres = hasattr(connection, "pgconn") or "psycopg" in str(type(connection)).lower()
        ph = "%s" if is_postgres else "?"

        assessment_id = f"as_{uuid4().hex[:16]}"
        query = f"""
            INSERT INTO adaptive_severity_logs (
                assessment_id, user_id, profile_ref, episode_id, conversation_id,
                safety_level, adaptive_level, final_level, reason_codes_json, engine_version, created_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """

        params = (
            assessment_id,
            user_id,
            profile_id or "self",
            "",
            conversation_id or "",
            assessment.base_safety_level,
            assessment.effective_concern_level.value,
            assessment.effective_concern_level.value,
            json.dumps(assessment.escalation_reasons, ensure_ascii=False),
            "1.0",
            now_iso,
        )

        cursor = connection.cursor()
        cursor.execute(query, params)
        if not is_postgres:
            connection.commit()
    except Exception as err:
        # Không làm sập ứng dụng nếu ghi log thất bại
        print(f"[AdaptiveSeverity] Không thể ghi log đánh giá: {err}")
