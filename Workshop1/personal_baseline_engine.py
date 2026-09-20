# -*- coding: utf-8 -*-
"""
Phase 9: Personal Health Baseline Engine.

Implements:
- PersonalHealthBaseline data model & maturity progression:
    NONE -> LOW_CONFIDENCE -> EMERGING -> ESTABLISHED
- Baseline attributes: Usual symptom patterns, pain ranges, vitals, recurring complaints
- Evidence tracking: evidence_count, first_seen, last_seen, source_episode_ids
- Baseline Deviation Detection: NONE, LOW, MODERATE, HIGH
- Deterioration Safeguard: Never masks acute escalation under the guise of "habitual symptoms"
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. ENUMS & CONSTANTS
# ==============================================================================

class BaselineMaturity(str, Enum):
    NONE = "NONE"                      # 0 sự kiện, chưa có bất kỳ dữ liệu cơ bản nào
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # 1 sự kiện quan sát được
    EMERGING = "EMERGING"              # 2-3 sự kiện lặp lại tương tự nhau
    ESTABLISHED = "ESTABLISHED"        # >= 4 sự kiện ổn định xuyên suốt thời gian


class BaselineDeviationLevel(str, Enum):
    NONE = "NONE"          # Triệu chứng hoàn toàn trùng khớp với trạng thái thông thường
    LOW = "LOW"            # Chênh lệch nhẹ, không có dấu hiệu bất thường
    MODERATE = "MODERATE"  # Mức độ đau hoặc thời gian tăng rõ so với thường lệ
    HIGH = "HIGH"          # Vượt ngưỡng nghiêm trọng so với bình thường hoặc xuất hiện kèm dấu hiệu mới
    UNKNOWN = "UNKNOWN"    # Chưa có baseline để so sánh


# Ngưỡng phân loại độ thành thục
MATURITY_THRESHOLDS = {
    "LOW_CONFIDENCE": 1,
    "EMERGING": 2,
    "ESTABLISHED": 4,
}


# ==============================================================================
# 2. DATA MODELS
# ==============================================================================

@dataclass
class BaselineAttribute:
    attribute_name: str
    pattern_value: Dict[str, Any]
    evidence_count: int = 1
    maturity: str = BaselineMaturity.LOW_CONFIDENCE.value
    first_seen: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_seen: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence: str = "CONFIRMED"
    source_episode_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attribute_name": self.attribute_name,
            "pattern_value": dict(self.pattern_value),
            "evidence_count": self.evidence_count,
            "maturity": self.maturity,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "confidence": self.confidence,
            "source_episode_ids": list(self.source_episode_ids),
        }


@dataclass
class BaselineDeviation:
    deviation_level: str = BaselineDeviationLevel.UNKNOWN.value
    deviation_reasons: List[str] = field(default_factory=list)
    compared_attribute: Optional[str] = None
    baseline_value: Optional[Dict[str, Any]] = None
    current_value: Optional[Dict[str, Any]] = None
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deviation_level": self.deviation_level,
            "deviation_reasons": list(self.deviation_reasons),
            "compared_attribute": self.compared_attribute,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "explanation": self.explanation,
        }


# ==============================================================================
# 3. BASELINE DEVIATION EVALUATION
# ==============================================================================

def evaluate_baseline_deviation(
    baselines: Dict[str, BaselineAttribute],
    chief_complaint: Optional[str],
    current_pain_scale: Optional[int],
    current_severity: Optional[str],
    current_duration: Optional[str],
    fever: Optional[bool] = None,
    associated_symptoms: Optional[List[str]] = None
) -> BaselineDeviation:
    """
    So sánh tình trạng hiện tại với đường cơ sở cá nhân (Personal Baseline).
    BẢO VỆ AN TOÀN:
    Nếu người dùng có bệnh mạn tính (ví dụ thường đau đầu nhẹ), nhưng hiện tại
    đau dữ dội (pain scale 7/10) hoặc kèm sốt/nôn, hệ thống PHẢI đánh giá độ lệch HIGH
    để nâng mức cảnh báo, tuyệt đối không được coi là bình thường!
    """
    if not baselines or not chief_complaint:
        return BaselineDeviation(
            deviation_level=BaselineDeviationLevel.UNKNOWN.value,
            explanation="Chưa đủ dữ liệu baseline cá nhân để so sánh độ lệch."
        )

    complaint_folded = chief_complaint.strip().lower()
    associated = [s.strip().lower() for s in (associated_symptoms or [])]
    reasons: List[str] = []

    # Tìm baseline thuộc tính liên quan
    matched_attr: Optional[BaselineAttribute] = None
    for attr_name, attr in baselines.items():
        if any(term in complaint_folded for term in attr_name.lower().split("_")):
            matched_attr = attr
            break

    if not matched_attr:
        return BaselineDeviation(
            deviation_level=BaselineDeviationLevel.UNKNOWN.value,
            explanation=f"Chưa có baseline ghi nhận riêng cho triệu chứng '{chief_complaint}'."
        )

    pat = matched_attr.pattern_value
    usual_min_pain = pat.get("min_pain", 1)
    usual_max_pain = pat.get("max_pain", 3)
    usual_symptoms = [s.lower() for s in pat.get("usual_associated_symptoms", [])]

    is_high_deviation = False
    is_moderate_deviation = False

    # 1. So sánh thang điểm đau
    if current_pain_scale is not None:
        if current_pain_scale >= 7 and usual_max_pain <= 4:
            reasons.append(f"Điểm đau hiện tại ({current_pain_scale}/10) tăng vượt trội so với mức thường gặp ({usual_min_pain}-{usual_max_pain}/10)")
            is_high_deviation = True
        elif current_pain_scale > usual_max_pain + 1:
            reasons.append(f"Điểm đau ({current_pain_scale}/10) cao hơn mức thường lệ ({usual_max_pain}/10)")
            is_moderate_deviation = True

    # 2. Xuất hiện triệu chứng sốt bất thường
    if fever is True and not pat.get("usual_fever", False):
        reasons.append("Xuất hiện sốt mới đi kèm — không có trong đợt đau thông thường")
        is_high_deviation = True

    # 3. Xuất hiện triệu chứng đi kèm nguy cơ cao mới
    new_concerning_symptoms = []
    for s in associated:
        if any(danger in s for danger in ["nôn", "chóng mặt", "khó thở", "nhìn mờ", "co giật", "tê bì"]):
            if s not in usual_symptoms:
                new_concerning_symptoms.append(s)

    if new_concerning_symptoms:
        reasons.append(f"Xuất hiện triệu chứng nguy cơ mới chưa từng có ở baseline: {', '.join(new_concerning_symptoms)}")
        is_high_deviation = True

    # 4. Thời gian kéo dài bất thường
    if current_duration:
        dur_lower = current_duration.lower()
        if any(long_k in dur_lower for long_k in ["tuần", "tháng", "nhiều ngày", "5 ngày", "1 tuần"]) and pat.get("usual_duration_hours", 24) < 12:
            reasons.append("Thời gian diễn tiến đợt này kéo dài hơn hẳn các lần trước")
            is_moderate_deviation = True

    # Tổng hợp mức độ lệch
    if is_high_deviation:
        dev_level = BaselineDeviationLevel.HIGH.value
        explanation = "Tình trạng đợt này có sự THAY ĐỔI ĐỘT BIẾN / NẶNG HƠN ĐÁNG KỂ so với các đợt bệnh trước đó của người dùng."
    elif is_moderate_deviation:
        dev_level = BaselineDeviationLevel.MODERATE.value
        explanation = "Tình trạng hiện tại cao hơn mức thường thấy nhưng chưa có dấu hiệu nguy hiểm đột biến."
    elif reasons:
        dev_level = BaselineDeviationLevel.LOW.value
        explanation = "Có sự khác biệt nhỏ so với đợt thường lệ."
    else:
        dev_level = BaselineDeviationLevel.NONE.value
        explanation = "Tình trạng hiện tại tương đồng với mức độ thường gặp của người dùng."

    return BaselineDeviation(
        deviation_level=dev_level,
        deviation_reasons=reasons,
        compared_attribute=matched_attr.attribute_name,
        baseline_value=pat,
        current_value={
            "pain_scale": current_pain_scale,
            "fever": fever,
            "duration": current_duration,
            "associated_symptoms": associated,
        },
        explanation=explanation
    )


# ==============================================================================
# 4. REPOSITORY & LIFECYCLE MANAGEMENT
# ==============================================================================

def _to_row_dict(row, col_names: List[str]) -> Dict[str, Any]:
    """Chuyển đổi an toàn sqlite3.Row, DatabaseRow hoặc tuple sang dict."""
    if row is None:
        return {}
    res = {}
    for i, col in enumerate(col_names):
        try:
            res[col] = row[col]
        except (TypeError, KeyError, IndexError):
            try:
                res[col] = row[i]
            except (IndexError, TypeError):
                res[col] = None
    return res


def get_personal_baselines(
    connection,
    user_id: Optional[int],
    profile_ref: str = "self"
) -> Dict[str, BaselineAttribute]:
    """Tải toàn bộ thuộc tính baseline của một hồ sơ cụ thể."""
    if not connection or user_id is None:
        return {}

    prof_type = "self" if str(profile_ref).lower() in ("self", "", "me") else "family"
    prof_id = "self" if prof_type == "self" else str(profile_ref)

    cols = ["attribute_name", "pattern_value_json", "evidence_count", "maturity", "first_seen", "last_seen", "confidence"]

    try:
        raw_rows = connection.execute(
            "SELECT attribute_name, pattern_value_json, evidence_count, maturity, "
            "first_seen, last_seen, confidence "
            "FROM personal_baselines "
            "WHERE user_id = ? AND profile_type = ? AND profile_ref = ?",
            (user_id, prof_type, prof_id)
        ).fetchall()

        baselines: Dict[str, BaselineAttribute] = {}
        for raw in raw_rows:
            r = _to_row_dict(raw, cols)
            attr_name = r["attribute_name"]
            pat = json.loads(r["pattern_value_json"])
            baselines[attr_name] = BaselineAttribute(
                attribute_name=attr_name,
                pattern_value=pat,
                evidence_count=int(r["evidence_count"] or 1),
                maturity=r["maturity"] or BaselineMaturity.NONE.value,
                first_seen=str(r["first_seen"] or ""),
                last_seen=str(r["last_seen"] or ""),
                confidence=r["confidence"] or "CONFIRMED"
            )
        return baselines
    except Exception as err:
        logger.warning(f"Lỗi tải personal_baselines: {err}")
        return {}


def update_personal_baseline_from_episode(
    connection,
    user_id: Optional[int],
    profile_ref: str,
    complaint_key: str,
    pain_scale: Optional[int] = None,
    duration: Optional[str] = None,
    fever: Optional[bool] = None,
    associated_symptoms: Optional[List[str]] = None,
    episode_id: Optional[str] = None
) -> None:
    """
    Cập nhật hoặc hình thành đường cơ sở sau mỗi đợt bệnh (Episode) được xác nhận.
    Tự động nâng cấp mức độ thành thục (Maturity):
    1 lần -> LOW_CONFIDENCE, 2-3 lần -> EMERGING, >= 4 lần -> ESTABLISHED.
    """
    if not connection or user_id is None or not complaint_key:
        return

    prof_type = "self" if str(profile_ref).lower() in ("self", "", "me") else "family"
    prof_id = "self" if prof_type == "self" else str(profile_ref)
    attr_name = f"usual_{complaint_key.strip().lower().replace(' ', '_')}"

    now_iso = datetime.now(timezone.utc).isoformat()
    sel_cols = ["id", "pattern_value_json", "evidence_count", "first_seen"]

    try:
        raw_existing = connection.execute(
            "SELECT id, pattern_value_json, evidence_count, first_seen "
            "FROM personal_baselines "
            "WHERE user_id = ? AND profile_type = ? AND profile_ref = ? AND attribute_name = ?",
            (user_id, prof_type, prof_id, attr_name)
        ).fetchone()

        existing = _to_row_dict(raw_existing, sel_cols) if raw_existing else None

        if existing and existing.get("id"):
            prev_pat = json.loads(existing["pattern_value_json"])
            new_count = int(existing["evidence_count"] or 1) + 1

            # Nâng cấp mức trưởng thành
            if new_count >= MATURITY_THRESHOLDS["ESTABLISHED"]:
                new_maturity = BaselineMaturity.ESTABLISHED.value
            elif new_count >= MATURITY_THRESHOLDS["EMERGING"]:
                new_maturity = BaselineMaturity.EMERGING.value
            else:
                new_maturity = BaselineMaturity.LOW_CONFIDENCE.value

            # Tính lại khoảng đau trung bình
            if pain_scale is not None:
                prev_min = prev_pat.get("min_pain", pain_scale)
                prev_max = prev_pat.get("max_pain", pain_scale)
                prev_pat["min_pain"] = min(prev_min, pain_scale)
                prev_pat["max_pain"] = max(prev_max, pain_scale)

            # Cập nhật danh sách triệu chứng kèm
            if associated_symptoms:
                cur_assoc = set(prev_pat.get("usual_associated_symptoms", []))
                cur_assoc.update([s.lower() for s in associated_symptoms[:4]])
                prev_pat["usual_associated_symptoms"] = list(cur_assoc)

            if fever is not None:
                prev_pat["usual_fever"] = bool(fever)

            if episode_id and episode_id not in prev_pat.get("source_episodes", []):
                eps = prev_pat.get("source_episodes", [])
                eps.append(episode_id)
                prev_pat["source_episodes"] = eps[-10:]

            connection.execute(
                "UPDATE personal_baselines "
                "SET pattern_value_json = ?, evidence_count = ?, maturity = ?, "
                "last_seen = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (json.dumps(prev_pat, ensure_ascii=False), new_count, new_maturity, now_iso, existing["id"])
            )
        else:
            # Tạo mới baseline với maturity = LOW_CONFIDENCE
            initial_pat = {
                "min_pain": pain_scale if pain_scale is not None else 1,
                "max_pain": pain_scale if pain_scale is not None else 3,
                "usual_associated_symptoms": [s.lower() for s in (associated_symptoms or [])[:4]],
                "usual_fever": bool(fever) if fever is not None else False,
                "source_episodes": [episode_id] if episode_id else []
            }
            connection.execute(
                "INSERT INTO personal_baselines "
                "(user_id, profile_type, profile_ref, attribute_name, pattern_value_json, "
                "evidence_count, maturity, first_seen, last_seen, confidence, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'CONFIRMED', CURRENT_TIMESTAMP)",
                (
                    user_id, prof_type, prof_id, attr_name,
                    json.dumps(initial_pat, ensure_ascii=False),
                    BaselineMaturity.LOW_CONFIDENCE.value,
                    now_iso, now_iso
                )
            )
        connection.commit()
    except Exception as err:
        logger.warning(f"Lỗi ghi nhận personal_baseline: {err}")


# ==============================================================================
# 5. COMPRESSED PROMPT FORMATTER
# ==============================================================================

def format_baseline_for_prompt(
    baselines: Dict[str, BaselineAttribute],
    deviation: Optional[BaselineDeviation] = None
) -> str:
    """Định dạng đường cơ sở và độ lệch vào system prompt cho LLM."""
    if not baselines and (not deviation or deviation.deviation_level == BaselineDeviationLevel.UNKNOWN.value):
        return ""

    lines = ["=== ĐƯỜNG CƠ SỞ SỨC KHỎE CỦA NGƯỜI DÙNG (PERSONAL BASELINE) ==="]

    for attr_name, attr in baselines.items():
        pat = attr.pattern_value
        p_min = pat.get("min_pain")
        p_max = pat.get("max_pain")
        pain_str = f"đau thường ở mức {p_min}-{p_max}/10" if p_min is not None else ""
        assoc_str = f", kèm theo: {', '.join(pat.get('usual_associated_symptoms', []))}" if pat.get("usual_associated_symptoms") else ""
        lines.append(f"• Thuộc tính {attr_name} [Độ tin cậy: {attr.maturity}]: {pain_str}{assoc_str} (dựa trên {attr.evidence_count} lần ghi nhận).")

    if deviation and deviation.deviation_level in (BaselineDeviationLevel.MODERATE.value, BaselineDeviationLevel.HIGH.value):
        lines.append(f"• ĐÁNH GIÁ ĐỘ LỆCH HIỆN TẠI [{deviation.deviation_level}]: {deviation.explanation}")
        for r in deviation.deviation_reasons:
            lines.append(f"  - Chi tiết: {r}")
        lines.append("LƯU Ý: Tình trạng này bất thường/nặng hơn bình thường của người dùng -> NÂNG CAO CẢNH BÁO, KHÔNG xem là đợt bệnh nhẹ thông thường!")

    return "\n".join(lines)[:1000]
