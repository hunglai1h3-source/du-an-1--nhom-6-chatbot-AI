# -*- coding: utf-8 -*-
"""
Phase 9: Personal Health Context Model, Provenance & Contradiction Engine.

Implements:
- Canonical PersonalHealthContext dataclass
- Fact Provenance & Source Map (PROFILE, USER_CONFIRMED, CURRENT_CONVERSATION, etc.)
- Fact Confidence (CONFIRMED, LIKELY, UNVERIFIED, CONFLICTED, UNKNOWN)
- Priority Hierarchy:
    CURRENT_USER_CORRECTION > CURRENT_USER_MESSAGE > CONFIRMED_PROFILE_DATA >
    CURRENT_EPISODE_STATE > RECENT_USER_CONFIRMED_HISTORY > LONG_TERM_SUMMARY
- Contradiction & User Correction Engine
- Strict Profile Scoping & Family Profile Isolation
- Compressed prompt formatting with strict token/character budget
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. ENUMS & CONSTANTS
# ==============================================================================

class FactSource(str, Enum):
    CURRENT_USER_CORRECTION = "CURRENT_USER_CORRECTION"
    CURRENT_USER_MESSAGE = "CURRENT_USER_MESSAGE"
    CONFIRMED_PROFILE_DATA = "CONFIRMED_PROFILE_DATA"
    CURRENT_EPISODE_STATE = "CURRENT_EPISODE_STATE"
    RECENT_USER_CONFIRMED_HISTORY = "RECENT_USER_CONFIRMED_HISTORY"
    LONG_TERM_SUMMARY = "LONG_TERM_SUMMARY"
    CALCULATED = "CALCULATED"
    UNKNOWN = "UNKNOWN"


# Priority weight (Higher number = Higher precedence)
SOURCE_PRIORITY: Dict[str, int] = {
    FactSource.CURRENT_USER_CORRECTION.value: 100,
    FactSource.CURRENT_USER_MESSAGE.value: 80,
    FactSource.CONFIRMED_PROFILE_DATA.value: 60,
    FactSource.CURRENT_EPISODE_STATE.value: 50,
    FactSource.RECENT_USER_CONFIRMED_HISTORY.value: 40,
    FactSource.LONG_TERM_SUMMARY.value: 20,
    FactSource.CALCULATED.value: 15,
    FactSource.UNKNOWN.value: 0,
}


class FactConfidence(str, Enum):
    CONFIRMED = "CONFIRMED"      # Người dùng xác nhận rõ ràng hoặc có trong hồ sơ chính thức
    LIKELY = "LIKELY"            # Suy ra từ ngữ cảnh rõ ràng nhưng chưa khẳng định trực tiếp
    UNVERIFIED = "UNVERIFIED"    # Người dùng nhắc đến thoáng qua, chưa làm rõ
    CONFLICTED = "CONFLICTED"    # Có sự mâu thuẫn giữa hồ sơ và lời nói hiện tại
    UNKNOWN = "UNKNOWN"          # Không có dữ liệu, tuyệt đối không đoán mò


# ==============================================================================
# 2. CANONICAL PERSONAL HEALTH CONTEXT
# ==============================================================================

@dataclass
class PersonalHealthContext:
    profile_id: str
    user_id: Optional[int] = None
    profile_type: str = "self"  # "self" hoặc "family"
    name: Optional[str] = None
    relationship: str = "Bản thân"
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    activity_level: Optional[str] = None
    diet_preference: Optional[str] = None
    health_goals: Optional[str] = None
    known_conditions: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    pregnancy_context: Optional[Dict[str, Any]] = None
    baseline_signals: Dict[str, Any] = field(default_factory=dict)
    recent_episodes: List[Dict[str, Any]] = field(default_factory=list)
    current_episode: Optional[Dict[str, Any]] = None
    confidence: Dict[str, str] = field(default_factory=dict)
    source_map: Dict[str, str] = field(default_factory=dict)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    last_updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def calculate_bmi(self) -> Optional[float]:
        """Tính chỉ số BMI an toàn nếu chiều cao và cân nặng hợp lệ."""
        if (
            self.height_cm is not None
            and self.weight_kg is not None
            and self.height_cm >= 50.0
            and self.weight_kg >= 2.0
        ):
            h_m = self.height_cm / 100.0
            computed = round(self.weight_kg / (h_m * h_m), 1)
            self.bmi = computed
            self.source_map["bmi"] = FactSource.CALCULATED.value
            self.confidence["bmi"] = (
                self.confidence.get("weight_kg", FactConfidence.CONFIRMED.value)
            )
            return computed
        self.bmi = None
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "user_id": self.user_id,
            "profile_type": self.profile_type,
            "name": self.name,
            "relationship": self.relationship,
            "age": self.age,
            "gender": self.gender,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "bmi": self.bmi,
            "activity_level": self.activity_level,
            "diet_preference": self.diet_preference,
            "health_goals": self.health_goals,
            "known_conditions": list(self.known_conditions),
            "allergies": list(self.allergies),
            "current_medications": list(self.current_medications),
            "pregnancy_context": dict(self.pregnancy_context or {}),
            "baseline_signals": dict(self.baseline_signals),
            "recent_episodes": list(self.recent_episodes),
            "current_episode": dict(self.current_episode or {}),
            "confidence": dict(self.confidence),
            "source_map": dict(self.source_map),
            "conflicts": list(self.conflicts),
            "last_updated_at": self.last_updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonalHealthContext":
        if not data:
            return cls(profile_id="self")
        return cls(
            profile_id=str(data.get("profile_id", "self")),
            user_id=data.get("user_id"),
            profile_type=str(data.get("profile_type", "self")),
            name=data.get("name"),
            relationship=str(data.get("relationship", "Bản thân")),
            age=data.get("age"),
            gender=data.get("gender"),
            height_cm=data.get("height_cm"),
            weight_kg=data.get("weight_kg"),
            bmi=data.get("bmi"),
            activity_level=data.get("activity_level"),
            diet_preference=data.get("diet_preference"),
            health_goals=data.get("health_goals"),
            known_conditions=list(data.get("known_conditions") or []),
            allergies=list(data.get("allergies") or []),
            current_medications=list(data.get("current_medications") or []),
            pregnancy_context=data.get("pregnancy_context"),
            baseline_signals=dict(data.get("baseline_signals") or {}),
            recent_episodes=list(data.get("recent_episodes") or []),
            current_episode=data.get("current_episode"),
            confidence=dict(data.get("confidence") or {}),
            source_map=dict(data.get("source_map") or {}),
            conflicts=list(data.get("conflicts") or []),
            last_updated_at=str(
                data.get("last_updated_at") or datetime.now(timezone.utc).isoformat()
            ),
        )


# ==============================================================================
# 3. CONTRADICTION & USER CORRECTION ENGINE
# ==============================================================================

def detect_contradictions_and_corrections(
    context: PersonalHealthContext,
    user_message: str
) -> Tuple[PersonalHealthContext, List[Dict[str, Any]]]:
    """
    Phát hiện sự mâu thuẫn hoặc đính chính giữa thông điệp hiện tại và hồ sơ đã lưu.
    Ví dụ:
    - Hồ sơ có 'Dị ứng penicillin', nhưng user nói: 'Không, tôi không dị ứng penicillin'
    - Hồ sơ ghi cân nặng 60kg, user nói: 'Tôi vừa tăng lên 68kg'
    - Hồ sơ ghi không có thai, user nói: 'Tôi đang mang thai tuần thứ 12'
    """
    if not user_message or not user_message.strip():
        return context, []

    text_lower = user_message.strip().lower()
    conflicts: List[Dict[str, Any]] = []

    # 1. Kiểm tra đính chính / mâu thuẫn về Dị ứng (Allergies)
    # Phát hiện mẫu phủ định dị ứng: "không bị dị ứng", "không hề dị ứng", "không dị ứng với", "hết dị ứng", "chưa từng dị ứng"
    has_negation = bool(re.search(r"\b(không|chưa từng|chưa|hết|không còn|không hề|chẳng|chẳng hề|chả|chả hề|ko|k)\s+(?:hề\s+)?(?:bị\s+)?dị ứng", text_lower))
    allergy_denial_pattern = r"(?:không|chưa từng|chưa|hết|không còn|không hề|chẳng|chẳng hề|chả|chả hề|ko|k)\s+(?:hề\s+)?(?:bị\s+)?dị ứng\s+(?:với\s+|thuốc\s+)?([a-zA-Z0-9à-ỹÀ-Ỹ\s]+)"
    denial_match = re.search(allergy_denial_pattern, text_lower)
    if denial_match:
        denied_raw = denial_match.group(1).strip()
        denied_item = re.split(r"[,.;!?]|\bnhé\b|\bđâu\b|\bvì\b|\bđấy\b|\bạ\b", denied_raw)[0].strip()
        for existing in list(context.allergies):
            if existing.lower() in denied_item.lower() or denied_item.lower() in existing.lower():
                conflict_obj = {
                    "field": "allergies",
                    "existing_value": existing,
                    "stated_value": f"Không dị ứng {existing}",
                    "conflict_type": "ALLERGY_REMOVAL",
                    "action": "USER_CORRECTION_OVERRIDE",
                    "explanation": f"Người dùng đính chính không dị ứng với {existing} (trước đó hồ sơ có ghi nhận).",
                }
                conflicts.append(conflict_obj)
                # Áp dụng đính chính: gỡ khỏi danh sách dị ứng hiện thời và lưu cờ mâu thuẫn
                context.allergies.remove(existing)
                context.confidence["allergies"] = FactConfidence.CONFIRMED.value
                context.source_map["allergies"] = FactSource.CURRENT_USER_CORRECTION.value

    # Phát hiện khai báo dị ứng mới: "tôi bị dị ứng với X", "dị ứng thuốc X" (chỉ chạy khi KHÔNG có từ phủ định)
    allergy_affirm_pattern = r"(?:tôi\s+)?(?:bị\s+)?dị ứng\s+(?:với\s+|thuốc\s+)?([a-zA-Z0-9à-ỹÀ-Ỹ\s,]+)"
    if not has_negation:
        affirm_match = re.search(allergy_affirm_pattern, text_lower)
        if affirm_match:
            new_item = affirm_match.group(1).strip().split(".")[0].split(";")[0]
            # Loại trừ từ rác
            if len(new_item) >= 3 and not any(k in new_item for k in ["không", "chưa", "gì"]):
                clean_allergy = new_item.strip()
                if clean_allergy and clean_allergy not in [a.lower() for a in context.allergies]:
                    context.allergies.append(clean_allergy)
                    context.confidence["allergies"] = FactConfidence.CONFIRMED.value
                    context.source_map["allergies"] = FactSource.CURRENT_USER_MESSAGE.value

    # 2. Kiểm tra đính chính cân nặng: "tôi nặng X kg", "vừa cân được X kg", "cân được X kg", "cân nặng hiện tại là X"
    weight_match = re.search(r"(?:nặng|cân nặng|(?:vừa\s+)?cân(?:\s*được)?)\s*(?:khoảng|là|được)?\s*(\d{2,3}(?:[.,]\d)?)\s*(?:kg|kí|cân|\b)", text_lower)
    if weight_match:
        try:
            val_str = weight_match.group(1).replace(",", ".")
            new_weight = float(val_str)
            if 20.0 <= new_weight <= 300.0:
                if context.weight_kg is not None and abs(context.weight_kg - new_weight) >= 2.0:
                    conflicts.append({
                        "field": "weight_kg",
                        "existing_value": context.weight_kg,
                        "stated_value": new_weight,
                        "conflict_type": "WEIGHT_UPDATE",
                        "action": "USER_CORRECTION_OVERRIDE",
                        "explanation": f"Cập nhật cân nặng mới {new_weight} kg (trước đó là {context.weight_kg} kg).",
                    })
                context.weight_kg = new_weight
                context.confidence["weight_kg"] = FactConfidence.CONFIRMED.value
                context.source_map["weight_kg"] = FactSource.CURRENT_USER_MESSAGE.value
                context.calculate_bmi()
        except (ValueError, TypeError):
            pass

    # 3. Kiểm tra đính chính thai kỳ
    if any(k in text_lower for k in ["đang mang thai", "có bầu", "có thai", "mang bầu"]):
        preg_weeks_match = re.search(r"(?:tuần\s+thứ\s*|tuần\s*)(\d{1,2})", text_lower)
        weeks = int(preg_weeks_match.group(1)) if preg_weeks_match else None
        context.pregnancy_context = {
            "is_pregnant": True,
            "gestational_weeks": weeks,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        context.confidence["pregnancy_context"] = FactConfidence.CONFIRMED.value
        context.source_map["pregnancy_context"] = FactSource.CURRENT_USER_MESSAGE.value
    elif any(k in text_lower for k in ["không có thai", "không mang thai", "không có bầu", "vừa sinh xong"]):
        if context.pregnancy_context and context.pregnancy_context.get("is_pregnant"):
            conflicts.append({
                "field": "pregnancy_context",
                "existing_value": context.pregnancy_context,
                "stated_value": "Không mang thai",
                "conflict_type": "PREGNANCY_STATUS_CHANGE",
                "action": "USER_CORRECTION_OVERRIDE",
                "explanation": "Người dùng xác nhận hiện không mang thai.",
            })
        context.pregnancy_context = {"is_pregnant": False}
        context.confidence["pregnancy_context"] = FactConfidence.CONFIRMED.value
        context.source_map["pregnancy_context"] = FactSource.CURRENT_USER_MESSAGE.value

    # Gắn danh sách mâu thuẫn vào context
    context.conflicts.extend(conflicts)
    return context, conflicts


# ==============================================================================
# 4. CANONICAL CONTEXT BUILDER SERVICE
# ==============================================================================

def build_personal_health_context(
    connection,
    user_id: Optional[int],
    profile_ref: Optional[Any] = "self",
    current_message: Optional[str] = None,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    conv_slots: Optional[Dict[str, Any]] = None,
    client_profile_override: Optional[Dict[str, Any]] = None
) -> PersonalHealthContext:
    """
    Hàm dịch vụ chuẩn hóa duy nhất xây dựng PersonalHealthContext.
    - Đảm bảo cách ly nghiêm ngặt giữa hồ sơ Bản thân và hồ sơ Thành viên gia đình.
    - Tải dữ liệu từ database (health_profiles hoặc family_members).
    - Tích hợp các fact states đã lưu.
    - So sánh với thông điệp hiện tại để phát hiện mâu thuẫn / đính chính.
    """
    raw_ref = str(profile_ref or "self").strip().lower()
    is_self = raw_ref in ("", "self", "me") or raw_ref.startswith(("self-", "user-"))

    prof_type = "self" if is_self else "family"
    prof_id = "self"

    if not is_self:
        # Trích xuất ID thành viên gia đình
        match = re.search(r"\d+", raw_ref)
        if match:
            prof_id = match.group(0)
        else:
            prof_id = raw_ref

    context = PersonalHealthContext(
        profile_id=str(prof_id),
        user_id=user_id,
        profile_type=prof_type
    )

    # 1. Tải dữ liệu hồ sơ từ Database
    if connection and user_id is not None:
        try:
            if is_self:
                row = connection.execute(
                    "SELECT * FROM health_profiles WHERE user_id = ?", (user_id,)
                ).fetchone()
                user_row = connection.execute(
                    "SELECT full_name FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if row:
                    context.name = user_row["full_name"] if user_row else "Bản thân"
                    context.relationship = "Bản thân"
                    context.gender = row["sex"]
                    context.height_cm = float(row["height_cm"]) if row["height_cm"] is not None else None
                    context.activity_level = row["activity_level"]
                    context.diet_preference = row["diet_preference"]
                    context.health_goals = row["goal"]

                    # Tuổi
                    if row["age"]:
                        try:
                            context.age = int(row["age"])
                        except (ValueError, TypeError):
                            pass

                    # Dị ứng & Bệnh nền
                    if row["allergies"] and str(row["allergies"]).strip() not in ("--", "Không", "None", ""):
                        context.allergies = [a.strip() for a in str(row["allergies"]).split(",") if a.strip()]
                    if row["medical_notes"] and str(row["medical_notes"]).strip() not in ("--", "Không", "None", ""):
                        context.known_conditions = [c.strip() for c in str(row["medical_notes"]).split(",") if c.strip()]

                    # Nguồn & Độ tin cậy mặc định từ Profile
                    for f in ["gender", "height_cm", "age", "activity_level", "allergies", "known_conditions"]:
                        if getattr(context, f, None):
                            context.confidence[f] = FactConfidence.CONFIRMED.value
                            context.source_map[f] = FactSource.CONFIRMED_PROFILE_DATA.value

                # Lấy cân nặng mới nhất từ weight_logs
                try:
                    w_row = connection.execute(
                        "SELECT weight_kg FROM weight_logs WHERE user_id = ? ORDER BY logged_at DESC LIMIT 1",
                        (user_id,)
                    ).fetchone()
                    if w_row and w_row["weight_kg"]:
                        context.weight_kg = float(w_row["weight_kg"])
                        context.confidence["weight_kg"] = FactConfidence.CONFIRMED.value
                        context.source_map["weight_kg"] = FactSource.CONFIRMED_PROFILE_DATA.value
                except Exception:
                    pass

            else:
                # Family profile
                member_id = int(prof_id) if prof_id.isdigit() else None
                if member_id:
                    row = connection.execute(
                        "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
                        (member_id, user_id)
                    ).fetchone()
                    if row:
                        def _get_val(k_list):
                            for k in k_list:
                                try:
                                    v = row[k]
                                    if v is not None:
                                        return v
                                except (KeyError, IndexError, TypeError):
                                    pass
                            return None

                        context.name = _get_val(["full_name", "name"])
                        context.relationship = _get_val(["relationship"]) or "Thành viên gia đình"
                        context.gender = _get_val(["gender", "sex"])
                        age_val = _get_val(["age"])
                        if age_val:
                            context.age = int(age_val)
                        else:
                            by_val = _get_val(["birth_year"])
                            if by_val:
                                context.age = datetime.now().year - int(by_val)

                        h_val = _get_val(["height_cm"])
                        context.height_cm = float(h_val) if h_val else None
                        w_val = _get_val(["weight_kg"])
                        context.weight_kg = float(w_val) if w_val else None

                        al_val = _get_val(["allergies"])
                        if al_val and str(al_val).strip() not in ("--", "Không", "None", ""):
                            context.allergies = [a.strip() for a in str(al_val).split(",") if a.strip()]

                        mc_val = _get_val(["medical_conditions", "medical_history", "medical_notes"])
                        if mc_val and str(mc_val).strip() not in ("--", "Không", "None", ""):
                            context.known_conditions = [c.strip() for c in str(mc_val).split(",") if c.strip()]

                        for f in ["gender", "age", "height_cm", "weight_kg", "allergies", "known_conditions"]:
                            if getattr(context, f, None):
                                context.confidence[f] = FactConfidence.CONFIRMED.value
                                context.source_map[f] = FactSource.CONFIRMED_PROFILE_DATA.value
        except Exception as db_err:
            logger.warning(f"Lỗi truy vấn database khi build PersonalHealthContext: {db_err}")

    # 2. Bổ sung dữ liệu từ client_profile_override (nếu có trường hợp khách / demo)
    if client_profile_override and isinstance(client_profile_override, dict):
        for field_name in ["age", "gender", "height_cm", "weight_kg", "relationship", "name"]:
            if getattr(context, field_name) is None and client_profile_override.get(field_name):
                setattr(context, field_name, client_profile_override.get(field_name))
                context.confidence[field_name] = FactConfidence.LIKELY.value
                context.source_map[field_name] = FactSource.CONFIRMED_PROFILE_DATA.value

    # 3. Tính toán BMI tự động
    context.calculate_bmi()

    # 4. Tải các fact states đã lưu từ bảng personal_fact_states (nếu có)
    if connection and user_id is not None:
        try:
            facts = connection.execute(
                "SELECT fact_category, fact_key, fact_value_json, source, confidence "
                "FROM personal_fact_states "
                "WHERE user_id = ? AND profile_type = ? AND profile_ref = ? AND is_active = 1",
                (user_id, prof_type, str(prof_id))
            ).fetchall()
            for fact in facts:
                cat = fact["fact_category"]
                val = json.loads(fact["fact_value_json"])
                conf = fact["confidence"]
                src = fact["source"]

                if cat == "allergy" and val not in context.allergies:
                    context.allergies.append(val)
                elif cat == "condition" and val not in context.known_conditions:
                    context.known_conditions.append(val)
                elif cat == "medication" and val not in context.current_medications:
                    context.current_medications.append(val)
        except Exception:
            pass

    # 5. Tích hợp các slot từ Phase 2 (nếu có và đáng tin cậy hơn)
    if conv_slots and isinstance(conv_slots, dict):
        if conv_slots.get("current_medications"):
            for med in conv_slots["current_medications"]:
                if med and med not in context.current_medications:
                    context.current_medications.append(med)
                    context.confidence["current_medications"] = FactConfidence.CONFIRMED.value
                    context.source_map["current_medications"] = FactSource.CURRENT_CONVERSATION.value

    # 6. Chạy bộ kiểm tra đính chính & mâu thuẫn trên câu hỏi hiện tại của người dùng
    if current_message:
        context, _ = detect_contradictions_and_corrections(context, current_message)

    return context


# ==============================================================================
# 5. COMPRESSED PROMPT FORMATTER (TOKEN BUDGET COMPLIANT)
# ==============================================================================

def format_personal_health_context_for_prompt(context: PersonalHealthContext) -> str:
    """
    Định dạng PersonalHealthContext thành chuỗi ngữ cảnh súc tích cho LLM.
    - Giới hạn ngân sách ký tự (< 1,200 ký tự) để không gây tràn token.
    - Nêu rõ danh tính, độ tin cậy và các lưu ý mâu thuẫn nếu có.
    """
    if not context:
        return ""

    lines = []
    lines.append("=== HỒ SƠ SỨC KHỎE CÁ NHÂN / THÔNG TIN ĐỐI TƯỢNG ĐANG ĐƯỢC TƯ VẤN (CÁ NHÂN HÓA LÂM SÀNG) ===")
    
    # 1. Định danh & Nhân khẩu học
    ident_parts = []
    if context.name:
        ident_parts.append(f"Tên: {context.name}")
    if context.relationship and context.relationship != "Bản thân":
        ident_parts.append(f"Quan hệ: {context.relationship}")
    if context.gender:
        ident_parts.append(f"Giới tính: {context.gender}")
    if context.age is not None:
        ident_parts.append(f"Tuổi: {context.age}")
    if ident_parts:
        lines.append("• " + " | ".join(ident_parts))

    # 2. Thể trạng
    anthro_parts = []
    if context.height_cm:
        anthro_parts.append(f"Chiều cao: {context.height_cm} cm")
    if context.weight_kg:
        anthro_parts.append(f"Cân nặng: {context.weight_kg} kg")
    if context.bmi:
        anthro_parts.append(f"BMI: {context.bmi}")
    if anthro_parts:
        lines.append("• Thể trạng: " + " | ".join(anthro_parts))

    # 3. Thai kỳ (nếu có)
    if context.pregnancy_context and context.pregnancy_context.get("is_pregnant"):
        weeks = context.pregnancy_context.get("gestational_weeks")
        w_str = f" ({weeks} tuần)" if weeks else ""
        lines.append(f"• TÌNH TRẠNG THAI KỲ: Đang mang thai{w_str} [LƯU Ý ĐẶC BIỆT KHI DÙNG THUỐC]")

    # 4. Bệnh nền & Dị ứng & Thuốc đang dùng
    if context.known_conditions:
        lines.append(f"• Bệnh nền đã biết: {', '.join(context.known_conditions)}")
    if context.allergies:
        lines.append(f"• DỊ ỨNG ĐÃ XÁC NHẬN: {', '.join(context.allergies)} [CHỐNG CHỈ ĐỊNH LIÊN QUAN]")
    if context.current_medications:
        lines.append(f"• Thuốc đang sử dụng: {', '.join(context.current_medications)}")

    # 5. Cảnh báo mâu thuẫn / đính chính vừa xảy ra
    if context.conflicts:
        for c in context.conflicts[-2:]:
            lines.append(f"• LƯU Ý ĐÍNH CHÍNH VỪA NÊU: {c['explanation']}")

    lines.append(
        "QUY TẮC LÂM SÀNG CỦA HỒ SƠ:\n"
        "1. Đây là dữ liệu ĐÃ BIẾT. KHÔNG hỏi lại tuổi, giới tính, cân nặng, chiều cao, dị ứng hoặc bệnh nền đã có.\n"
        "2. Không tự chẩn đoán bệnh mới chỉ vì có dữ liệu nền. Dữ liệu này dùng để điều chỉnh liều, chống chỉ định và định hướng chuyên khoa.\n"
        "3. Tuyệt đối không để lộ các tên trường kỹ thuật như 'profile_id', 'source_map', 'confidence' trong câu trả lời."
    )

    formatted = "\n".join(lines)
    # Giới hạn an toàn 1,200 ký tự
    return formatted[:1200]
