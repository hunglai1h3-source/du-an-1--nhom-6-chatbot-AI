"""
Module: conversation_engine.py
Mô-đun quản trị trạng thái hội thoại y tế (Medical Conversation State Engine).
Đảm bảo:
- Theo dõi ngữ cảnh y tế có cấu trúc (Structured Medical State & Slot Tracking).
- Nhận biết đa thông tin trong một câu, xử lý đính chính (User Correction).
- Phát hiện đổi chủ đề (Topic Change) mà không làm mất thông tin nhân khẩu học.
- Mỗi lượt chỉ hỏi đúng 1 câu trọng tâm theo thứ tự ưu tiên lâm sàng.
- Không hỏi lại các thông tin đã thu thập hoặc đã có trong hồ sơ bệnh án.
- Xác định thời điểm đủ thông tin (Assessment Ready) để chuyển sang đánh giá sơ bộ.
- Phối hợp tuyệt đối với Medical Safety V2 (Safety V2 luôn đứng trước).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from medical_safety import normalize_vietnamese_advanced


# ==============================================================================
# 1. ENUMS & CONSTANTS
# ==============================================================================

class ConversationStage(str, Enum):
    INITIAL = "INITIAL"          # Người dùng mới bắt đầu hội thoại / chào hỏi
    INTAKE = "INTAKE"            # Thu thập triệu chứng hoặc vấn đề chính
    EXPLORATION = "EXPLORATION"  # Khai thác thông tin chi tiết còn thiếu
    TRIAGE = "TRIAGE"            # Phân loại mức độ chăm sóc y tế
    ASSESSMENT = "ASSESSMENT"    # Đã đủ thông tin để đưa ra định hướng sơ bộ
    FOLLOW_UP = "FOLLOW_UP"      # Người dùng trao đổi tiếp sau khi đánh giá


class NextAction(str, Enum):
    ASK_QUESTION = "ASK_QUESTION"                      # Đặt 1 câu hỏi trọng tâm duy nhất
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"    # Làm rõ thông tin mâu thuẫn
    ASSESS = "ASSESS"                                  # Tổng hợp đánh giá và định hướng
    FOLLOW_UP = "FOLLOW_UP"                            # Trả lời thắc mắc tiếp theo
    TOPIC_CHANGE = "TOPIC_CHANGE"                      # Chuyển chủ đề bệnh mới
    SAFETY_ESCALATION = "SAFETY_ESCALATION"            # Chuyển tuyến cấp cứu (Safety Gate)


# Nhãn tiếng Việt thân thiện cho từng slot khi sinh prompt hoặc kiểm tra
SLOT_DESCRIPTIONS = {
    "chief_complaint": "Triệu chứng chính hoặc vấn đề sức khỏe cần tư vấn",
    "symptom_location": "Vị trí cụ thể của triệu chứng trên cơ thể",
    "duration": "Thời gian xuất hiện hoặc diễn tiến của triệu chứng",
    "onset": "Thời điểm hoặc hoàn cảnh khởi phát (đột ngột hay từ từ)",
    "severity": "Mức độ đau hoặc cảm giác khó chịu",
    "pain_scale": "Thang điểm đau từ 1 đến 10",
    "fever": "Tình trạng sốt (có sốt hay không sốt, nhiệt độ)",
    "associated_symptoms": "Các triệu chứng khác đi kèm",
    "age": "Tuổi của người được tư vấn",
    "gender": "Giới tính sinh học",
    "medical_conditions": "Bệnh lý nền hoặc tiền sử bệnh",
    "current_medications": "Các thuốc đang sử dụng",
    "allergies": "Dị ứng thuốc hoặc thực phẩm",
    "pregnancy_status": "Tình trạng thai kỳ (nếu là nữ độ tuổi sinh sản)",
}


# ==============================================================================
# 2. DATA STRUCTURES (STRUCTURED MEDICAL STATE)
# ==============================================================================

@dataclass
class MedicalSlots:
    chief_complaint: Optional[str] = None
    symptom_location: Optional[str] = None
    onset: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[str] = None
    pain_scale: Optional[int] = None
    fever: Optional[bool] = None
    associated_symptoms: List[str] = field(default_factory=list)
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_conditions: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    pregnancy_status: Optional[str] = None
    relevant_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chief_complaint": self.chief_complaint,
            "symptom_location": self.symptom_location,
            "onset": self.onset,
            "duration": self.duration,
            "severity": self.severity,
            "pain_scale": self.pain_scale,
            "fever": self.fever,
            "associated_symptoms": list(self.associated_symptoms),
            "age": self.age,
            "gender": self.gender,
            "medical_conditions": list(self.medical_conditions),
            "current_medications": list(self.current_medications),
            "allergies": list(self.allergies),
            "pregnancy_status": self.pregnancy_status,
            "relevant_context": dict(self.relevant_context),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MedicalSlots":
        if not isinstance(data, dict):
            return cls()
        return cls(
            chief_complaint=data.get("chief_complaint"),
            symptom_location=data.get("symptom_location"),
            onset=data.get("onset"),
            duration=data.get("duration"),
            severity=data.get("severity"),
            pain_scale=data.get("pain_scale"),
            fever=data.get("fever"),
            associated_symptoms=list(data.get("associated_symptoms") or []),
            age=data.get("age"),
            gender=data.get("gender"),
            medical_conditions=list(data.get("medical_conditions") or []),
            current_medications=list(data.get("current_medications") or []),
            allergies=list(data.get("allergies") or []),
            pregnancy_status=data.get("pregnancy_status"),
            relevant_context=dict(data.get("relevant_context") or {}),
        )


@dataclass
class MedicalConversationState:
    conversation_id: str = ""
    user_id: Optional[int] = None
    stage: str = ConversationStage.INITIAL.value
    slots: MedicalSlots = field(default_factory=MedicalSlots)
    asked_slots: List[str] = field(default_factory=list)
    collected_slots: List[str] = field(default_factory=list)
    missing_slots: List[str] = field(default_factory=list)
    current_topic: Optional[str] = None
    previous_topics: List[str] = field(default_factory=list)
    last_question_slot: Optional[str] = None
    assessment_ready: bool = False
    next_action: str = NextAction.ASK_QUESTION.value
    turn_count: int = 0
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "stage": self.stage,
            "slots": self.slots.to_dict(),
            "asked_slots": list(self.asked_slots),
            "collected_slots": list(self.collected_slots),
            "missing_slots": list(self.missing_slots),
            "current_topic": self.current_topic,
            "previous_topics": list(self.previous_topics),
            "last_question_slot": self.last_question_slot,
            "assessment_ready": self.assessment_ready,
            "next_action": self.next_action,
            "turn_count": self.turn_count,
            "updated_at": self.updated_at or datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MedicalConversationState":
        if not isinstance(data, dict):
            return cls()
        slots_data = data.get("slots")
        slots = MedicalSlots.from_dict(slots_data) if isinstance(slots_data, dict) else MedicalSlots()
        return cls(
            conversation_id=str(data.get("conversation_id") or ""),
            user_id=data.get("user_id"),
            stage=str(data.get("stage") or ConversationStage.INITIAL.value),
            slots=slots,
            asked_slots=list(data.get("asked_slots") or []),
            collected_slots=list(data.get("collected_slots") or []),
            missing_slots=list(data.get("missing_slots") or []),
            current_topic=data.get("current_topic"),
            previous_topics=list(data.get("previous_topics") or []),
            last_question_slot=data.get("last_question_slot"),
            assessment_ready=bool(data.get("assessment_ready", False)),
            next_action=str(data.get("next_action") or NextAction.ASK_QUESTION.value),
            turn_count=int(data.get("turn_count") or 0),
            updated_at=str(data.get("updated_at") or ""),
        )

    def reset_for_topic_change(self, new_topic: str) -> None:
        """Đổi chủ đề khám: Lưu chủ đề cũ, làm sạch triệu chứng, giữ nguyên hồ sơ nhân khẩu."""
        if self.current_topic and self.current_topic not in self.previous_topics:
            self.previous_topics.append(self.current_topic)
        self.current_topic = new_topic
        
        # Giữ lại thông tin nhân thân/hồ sơ đã có
        preserved_age = self.slots.age
        preserved_gender = self.slots.gender
        preserved_allergies = list(self.slots.allergies)
        preserved_conditions = list(self.slots.medical_conditions)
        preserved_meds = list(self.slots.current_medications)

        # Khởi tạo lại slots triệu chứng
        self.slots = MedicalSlots(
            chief_complaint=new_topic,
            age=preserved_age,
            gender=preserved_gender,
            allergies=preserved_allergies,
            medical_conditions=preserved_conditions,
            current_medications=preserved_meds,
        )
        self.asked_slots = [s for s in ["age", "gender"] if getattr(self.slots, s, None) is not None]
        self.collected_slots = [s for s in ["chief_complaint", "age", "gender"] if getattr(self.slots, s, None) is not None]
        self.missing_slots = []
        self.last_question_slot = None
        self.assessment_ready = False
        self.stage = ConversationStage.EXPLORATION.value
        self.next_action = NextAction.ASK_QUESTION.value


# ==============================================================================
# 3. DETERMINISTIC SLOT EXTRACTION & CORRECTION
# ==============================================================================

COMMON_SYMPTOM_COMPLAINTS = [
    ("đau bụng dưới bên phải", "đau bụng dưới bên phải"),
    ("đau bụng dưới bên trái", "đau bụng dưới bên trái"),
    ("đau bụng dưới", "đau bụng dưới"),
    ("đau bụng trên", "đau bụng trên"),
    ("đau dạ dày", "đau dạ dày"),
    ("đau bụng", "đau bụng"),
    ("đau đầu nửa đầu", "đau nửa đầu"),
    ("đau đầu", "đau đầu"),
    ("đau ngực", "đau ngực"),
    ("đau lưng", "đau lưng"),
    ("đau vai gáy", "đau vai gáy"),
    ("đau họng", "đau họng"),
    ("chóng mặt", "chóng mặt"),
    ("buồn nôn", "buồn nôn"),
    ("tiêu chảy", "tiêu chảy"),
    ("sốt cao", "sốt"),
    ("sốt", "sốt"),
    ("ho có đờm", "ho"),
    ("ho khan", "ho"),
    ("ho", "ho"),
    ("khó ngủ", "mất ngủ"),
    ("mất ngủ", "mất ngủ"),
    ("mệt mỏi", "mệt mỏi"),
    ("phát ban", "phát ban"),
    ("nổi mề đay", "dị ứng da"),
]

COMMON_LOCATIONS = [
    ("bung duoi ben phai", "bụng dưới bên phải"),
    ("bung duoi ben trai", "bụng dưới bên trái"),
    ("bung duoi", "bụng dưới"),
    ("bung tren", "bụng trên"),
    ("vung thuong vi", "thượng vị"),
    ("quanh ron", "quanh rốn"),
    ("man suon", "mạn sườn"),
    ("nua dau ben phai", "nửa đầu bên phải"),
    ("nua dau ben trai", "nửa đầu bên trái"),
    ("vung tran", "vùng trán"),
    ("sau gay", "sau gáy"),
    ("that lung", "thắt lưng"),
    ("khop goi", "khớp gối"),
    ("co hong", "cổ họng"),
    ("nguc trai", "ngực trái"),
    ("giua nguc", "giữa ngực"),
]

NUMBER_WORD_MAP = {
    "mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5,
    "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10
}


def extract_duration(text: str) -> Optional[str]:
    """Trích xuất thời gian kéo dài triệu chứng."""
    norm = normalize_vietnamese_advanced(text)
    
    # 1. Dạng: 3 ngày, 2 tuần, 5 tiếng, 4 giờ, 1 tháng
    match = re.search(r"\b([0-9]{1,3}|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\s*(ngay|tuan|thang|gio|tieng|hom)\b", norm)
    if match:
        val_str = match.group(1)
        unit = match.group(2)
        val = NUMBER_WORD_MAP.get(val_str, val_str)
        unit_vi = "ngày" if unit in {"ngay", "hom"} else "tuần" if unit == "tuan" else "tháng" if unit == "thang" else "giờ"
        return f"{val} {unit_vi}"

    # 2. Dạng: từ hôm qua, từ sáng nay, từ tối qua
    if re.search(r"\b(?:tu\s+)?hom qua\b", norm):
        return "1 ngày (từ hôm qua)"
    if re.search(r"\b(?:tu\s+)?sang nay\b", norm):
        return "từ sáng nay"
    if re.search(r"\b(?:tu\s+)?toi qua\b", norm):
        return "từ tối qua"
    if re.search(r"\b(?:tu\s+)?tuan truoc\b", norm):
        return "khoảng 1 tuần"
        
    return None


def extract_pain_scale(text: str) -> Optional[int]:
    """Trích xuất thang điểm đau từ 1 đến 10."""
    norm = normalize_vietnamese_advanced(text)

    # Dạng: 7/10, 8 trên 10, tầm 7/10
    match = re.search(r"\b([1-9]|10)\s*(?:/|\s*tren\s*|\s*phan\s*)\s*10\b", norm)
    if match:
        return int(match.group(1))

    # Dạng: đau 7 điểm, tầm 8 điểm
    match_point = re.search(r"\b(?:dau|muc do|thang diem)\s*(?:khoang|tam|la)?\s*([1-9]|10)\s*(?:diem)?\b", norm)
    if match_point:
        return int(match_point.group(1))

    return None


def extract_fever(text: str) -> Optional[bool]:
    """Trích xuất trạng thái sốt có hay không."""
    norm = normalize_vietnamese_advanced(text)

    # Phủ định: không sốt, ko sốt, chưa thấy sốt
    if re.search(r"\b(?:khong|ko|chua|khong bi|khong he)\s+(?:bi\s+)?sot\b", norm):
        return False

    # Khẳng định: có sốt, hơi sốt, sốt cao, sốt 39 độ
    if re.search(r"\b(?:co sot|bi sot|hoi sot|sot cao|nong sot|sot (?:3[7-9]|4[0-1]))\b", norm):
        return True

    return None


def extract_location(text: str) -> Optional[str]:
    """Trích xuất vị trí triệu chứng cụ thể."""
    norm = normalize_vietnamese_advanced(text)
    for p_norm, p_vi in COMMON_LOCATIONS:
        if p_norm in norm:
            return p_vi
    return None


def extract_chief_complaint(text: str) -> Optional[str]:
    """Trích xuất triệu chứng chính từ câu nói."""
    norm = normalize_vietnamese_advanced(text)
    for c_vi, c_label in COMMON_SYMPTOM_COMPLAINTS:
        c_norm = normalize_vietnamese_advanced(c_vi)
        if c_norm in norm:
            return c_label
    return None


def detect_explicit_topic_change(text: str) -> Optional[str]:
    """
    Phát hiện người dùng chuyển đổi chủ đề khám bệnh rõ ràng:
    Ví dụ: 'Thôi bỏ chuyện đau bụng đi, giờ tôi muốn hỏi về đau đầu'
    'Bỏ qua đau lưng đi, tôi bị đau họng'
    """
    norm = normalize_vietnamese_advanced(text)
    # Bắt cụm 'thoi bo ... di/nhe ... gio toi muon hoi/bi ...'
    patterns = [
        r"(?:thoi bo|bo qua|khong ban ve|khong hoi ve)\s+([^,.;!?]+?)\s+(?:di|nhe|nua)?.*?(?:chuyen sang|muon hoi|toi muon hoi|hoi ve|bi|dau)\s+([^,.;!?]+)",
        r"(?:khong phai|thoi khong hoi)\s+([^,.;!?]+?)\s+(?:nua|nhe).*?(?:ma la|chuyen qua|sang)\s+([^,.;!?]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, norm)
        if m:
            target_phrase = m.group(2).strip()
            # Tìm xem target_phrase có chứa triệu chứng nào hợp lệ
            found = extract_chief_complaint(target_phrase)
            if found:
                return found
            return target_phrase
    return None


def detect_user_correction(text: str, current_slots: MedicalSlots) -> Dict[str, Any]:
    """
    Phát hiện người dùng đính chính lại thông tin đã cung cấp trước đó:
    Ví dụ: 'À không, mới 2 ngày thôi' hoặc 'Không phải, đau 3/10 thôi'
    """
    norm = normalize_vietnamese_advanced(text)
    corrections: Dict[str, Any] = {}

    is_correction_intent = bool(
        re.search(r"\b(?:a khong|khong phai|nham|dung hon la|chinh xac la|that ra la|thuc ra)\b", norm)
    )

    if is_correction_intent:
        # Kiểm tra đính chính duration
        new_dur = extract_duration(text)
        if new_dur and new_dur != current_slots.duration:
            corrections["duration"] = new_dur

        # Kiểm tra đính chính pain scale
        new_pain = extract_pain_scale(text)
        if new_pain is not None and new_pain != current_slots.pain_scale:
            corrections["pain_scale"] = new_pain

        # Kiểm tra đính chính fever
        new_fever = extract_fever(text)
        if new_fever is not None and new_fever != current_slots.fever:
            corrections["fever"] = new_fever

        # Kiểm tra đính chính location
        new_loc = extract_location(text)
        if new_loc and new_loc != current_slots.symptom_location:
            corrections["symptom_location"] = new_loc

    return corrections


# ==============================================================================
# 4. SLOT TRACKER & STAGE MANAGEMENT
# ==============================================================================

def sync_profile_into_slots(slots: MedicalSlots, profile: Optional[Dict[str, Any]]) -> None:
    """Nạp các trường thông tin đã có từ hồ sơ sức khỏe mà không ghi đè dữ liệu người dùng vừa khai."""
    if not profile or not isinstance(profile, dict):
        return

    if slots.age is None and profile.get("age"):
        try:
            slots.age = int(profile["age"])
        except (ValueError, TypeError):
            pass

    if slots.gender is None and profile.get("sex"):
        slots.gender = str(profile["sex"])

    if not slots.allergies and profile.get("allergies"):
        raw_allergies = str(profile["allergies"]).strip()
        if raw_allergies and raw_allergies.lower() not in {"không", "khong", "none", "không có"}:
            slots.allergies = [a.strip() for a in raw_allergies.split(",") if a.strip()]

    if not slots.medical_conditions and profile.get("medical_notes"):
        raw_notes = str(profile["medical_notes"]).strip()
        if raw_notes and raw_notes.lower() not in {"không", "khong", "none", "bình thường"}:
            slots.medical_conditions = [n.strip() for n in raw_notes.split(",") if n.strip()]


def update_collected_and_missing_slots(state: MedicalConversationState) -> None:
    """Cập nhật danh sách slots đã có (collected_slots) và còn thiếu (missing_slots)."""
    collected: List[str] = []
    s = state.slots

    if s.chief_complaint: collected.append("chief_complaint")
    if s.symptom_location: collected.append("symptom_location")
    if s.duration: collected.append("duration")
    if s.onset: collected.append("onset")
    if s.severity or s.pain_scale is not None: collected.append("severity")
    if s.pain_scale is not None: collected.append("pain_scale")
    if s.fever is not None: collected.append("fever")
    if s.associated_symptoms: collected.append("associated_symptoms")
    if s.age is not None: collected.append("age")
    if s.gender: collected.append("gender")
    if s.medical_conditions: collected.append("medical_conditions")
    if s.current_medications: collected.append("current_medications")
    if s.allergies: collected.append("allergies")

    state.collected_slots = collected

    # Xác định các slot quan trọng còn thiếu tùy theo triệu chứng chính
    missing: List[str] = []
    complaint = (s.chief_complaint or "").lower()

    if not s.chief_complaint:
        missing.append("chief_complaint")
    else:
        # Nếu là nhóm đau (bụng, đầu, ngực, lưng): vị trí + thời gian + mức độ là cốt lõi
        if any(w in complaint for w in ["đau", "nhức", "mỏi", "bụng", "ngực", "lưng", "đầu"]):
            if "symptom_location" not in collected and not any(loc in complaint for loc in ["đầu", "lưng", "họng"]):
                missing.append("symptom_location")
            if "duration" not in collected:
                missing.append("duration")
            if "severity" not in collected and "pain_scale" not in collected:
                missing.append("severity")
            if "associated_symptoms" not in collected:
                missing.append("associated_symptoms")
        elif "sốt" in complaint:
            if "duration" not in collected:
                missing.append("duration")
            if "fever" not in collected:
                missing.append("fever")
            if "associated_symptoms" not in collected:
                missing.append("associated_symptoms")
        else:
            # Nhóm tổng quát khác
            if "duration" not in collected:
                missing.append("duration")
            if "severity" not in collected:
                missing.append("severity")
            if "associated_symptoms" not in collected:
                missing.append("associated_symptoms")

    state.missing_slots = [m for m in missing if m not in collected]


def evaluate_assessment_readiness(state: MedicalConversationState) -> bool:
    """
    Xác định khi nào đã đủ dữ liệu để đưa ra nhận định y tế sơ bộ:
    - Phải có triệu chứng chính (chief_complaint).
    - Có ít nhất thông tin về thời gian (duration) hoặc mức độ/vị trí.
    - Đã thu thập ít nhất 2-3 thông tin lâm sàng cơ bản.
    - Hoặc người dùng đã tương tác qua nhiều lượt và không còn thông tin then chốt nào bị thiếu.
    """
    s = state.slots
    if not s.chief_complaint:
        return False

    has_duration = bool(s.duration)
    has_location_or_severity = bool(s.symptom_location or s.severity or s.pain_scale is not None)
    has_associated = len(s.associated_symptoms) > 0 or "associated_symptoms" in state.asked_slots

    # Đủ điều kiện khi có triệu chứng chính + thời gian + (vị trí hoặc mức độ)
    if has_duration and has_location_or_severity:
        return True

    # Nếu đã hỏi 3 lượt trở lên và đã có triệu chứng chính + thời gian
    if state.turn_count >= 3 and has_duration:
        return True

    return False


def select_next_question_slot(state: MedicalConversationState) -> Optional[str]:
    """
    Chọn đúng 1 slot mục tiêu có giá trị y tế cao nhất để hỏi tiếp theo.
    Quy tắc nghiêm ngặt:
    - Tuyệt đối không chọn slot đã có trong collected_slots.
    - Tuyệt đối không chọn slot đã hỏi trong asked_slots nếu người dùng đã bỏ qua.
    """
    candidate_slots = [s for s in state.missing_slots if s not in state.collected_slots and s not in state.asked_slots]
    if candidate_slots:
        return candidate_slots[0]

    # Nếu không còn trong missing_slots dự kiến nhưng chưa sẵn sàng đánh giá:
    fallbacks = ["duration", "symptom_location", "severity", "associated_symptoms"]
    for slot in fallbacks:
        if slot not in state.collected_slots and slot not in state.asked_slots:
            return slot

    return None


# ==============================================================================
# 5. MAIN TURN PROCESSOR (ENGINE COORDINATOR)
# ==============================================================================

def process_conversation_turn(
    user_message: str,
    state: MedicalConversationState,
    history: Optional[List[Dict[str, Any]]] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> MedicalConversationState:
    """
    Xử lý một lượt hội thoại từ người dùng và cập nhật MedicalConversationState:
    1. Đồng bộ dữ liệu hồ sơ bệnh án (nếu có).
    2. Phát hiện đổi chủ đề khám bệnh.
    3. Phát hiện đính chính dữ liệu từ người dùng.
    4. Trích xuất đa thông tin (multi-slot) từ tin nhắn.
    5. Cập nhật trạng thái slot & kiểm tra điều kiện đánh giá.
    6. Chọn đúng 1 hành động tiếp theo và 1 target_slot (nếu cần hỏi).
    """
    state.turn_count += 1
    state.updated_at = datetime.now().isoformat()

    # 1. Đồng bộ profile
    sync_profile_into_slots(state.slots, profile)

    # 2. Phát hiện Explicit Topic Change
    new_topic = detect_explicit_topic_change(user_message)
    if new_topic:
        state.reset_for_topic_change(new_topic)
        update_collected_and_missing_slots(state)
        target = select_next_question_slot(state)
        state.last_question_slot = target
        if target:
            state.asked_slots.append(target)
            state.next_action = NextAction.ASK_QUESTION.value
        else:
            state.next_action = NextAction.ASSESS.value
        return state

    # 3. Kiểm tra đính chính từ người dùng
    corrections = detect_user_correction(user_message, state.slots)
    for field_name, value in corrections.items():
        setattr(state.slots, field_name, value)
        if field_name not in state.collected_slots:
            state.collected_slots.append(field_name)

    # 4. Trích xuất thông tin mới (Multi-slot extraction)
    # 4a. Triệu chứng chính
    if not state.slots.chief_complaint:
        complaint = extract_chief_complaint(user_message)
        if complaint:
            state.slots.chief_complaint = complaint
            state.current_topic = complaint

    # 4b. Vị trí
    loc = extract_location(user_message)
    if loc and not state.slots.symptom_location:
        state.slots.symptom_location = loc

    # 4c. Thời gian
    dur = extract_duration(user_message)
    if dur and not state.slots.duration:
        state.slots.duration = dur

    # 4d. Thang điểm đau / Mức độ
    pain = extract_pain_scale(user_message)
    if pain is not None:
        state.slots.pain_scale = pain
        state.slots.severity = f"{pain}/10"

    # 4e. Sốt
    fever_val = extract_fever(user_message)
    if fever_val is not None:
        state.slots.fever = fever_val

    # 5. Cập nhật danh sách slots
    update_collected_and_missing_slots(state)

    # 6. Đánh giá tính sẵn sàng (Assessment Ready)
    is_ready = evaluate_assessment_readiness(state)
    state.assessment_ready = is_ready

    # 7. Quyết định Stage và Next Action
    if is_ready:
        state.stage = ConversationStage.ASSESSMENT.value
        state.next_action = NextAction.ASSESS.value
        state.last_question_slot = None
    else:
        state.stage = ConversationStage.EXPLORATION.value
        state.next_action = NextAction.ASK_QUESTION.value
        target_slot = select_next_question_slot(state)
        state.last_question_slot = target_slot
        if target_slot and target_slot not in state.asked_slots:
            state.asked_slots.append(target_slot)

    return state


# ==============================================================================
# 6. PROMPT CONTEXT INJECTION & OUTPUT GUARD
# ==============================================================================

def format_conversation_state_for_prompt(state: MedicalConversationState) -> str:
    """Định dạng trạng thái hội thoại y tế có cấu trúc thành đoạn chỉ dẫn tiêm vào Gemini prompt."""
    s = state.slots
    lines = [
        "=========================================================",
        "TRẠNG THÁI HỘI THOẠI Y TẾ (CONVERSATION STATE ENGINE):",
        "=========================================================",
        f"- Triệu chứng chính: {s.chief_complaint or 'Chưa xác định'}",
        f"- Vị trí: {s.symptom_location or 'Chưa rõ'}",
        f"- Thời gian kéo dài: {s.duration or 'Chưa rõ'}",
        f"- Mức độ đau: {s.pain_scale or s.severity or 'Chưa rõ'}",
        f"- Sốt: {'Có sốt' if s.fever is True else 'Không sốt' if s.fever is False else 'Chưa rõ'}",
        f"- Giai đoạn hiện tại: {state.stage}",
        f"- Hành động tiếp theo: {state.next_action}",
        f"- Đã thu thập: {', '.join(state.collected_slots) if state.collected_slots else 'Chưa có'}",
    ]

    if state.next_action == NextAction.ASK_QUESTION.value and state.last_question_slot:
        slot_desc = SLOT_DESCRIPTIONS.get(state.last_question_slot, state.last_question_slot)
        lines.extend([
            f"- MỤC TIÊU DUY NHẤT LƯỢT NÀY: Thu thập thông tin về [{slot_desc}]",
            "QUY TẮC BẮT BUỘC:",
            "1. TUYỆT ĐỐI KHÔNG hỏi lại bất kỳ thông tin nào đã có ở trên.",
            "2. Trong câu trả lời, chỉ được đặt ĐÚNG 1 CÂU HỎI TRỌNG TÂM DUY NHẤT về mục tiêu trên.",
            "3. Không đưa ra danh sách nhiều câu hỏi đánh số.",
            "4. CHƯA đưa ra kết luận chẩn đoán khẳng định chắc chắn (chưa đủ dữ liệu).",
        ])
    elif state.assessment_ready or state.next_action == NextAction.ASSESS.value:
        lines.extend([
            "- MỤC TIÊU LƯỢT NÀY: Đã đủ thông tin sơ bộ để đưa ra nhận định/định hướng y tế.",
            "QUY TẮC BẮT BUỘC:",
            "1. KHÔNG hỏi thêm câu hỏi khai thác triệu chứng dồn dập nữa.",
            "2. Tổng hợp ngắn gọn tình trạng của người dùng.",
            "3. Nêu các khả năng có thể nghĩ đến và hướng xử trí/chăm sóc hoặc khi nào cần đi khám.",
            "4. Luôn kèm lời khuyên đến cơ sở y tế khi cần thiết.",
        ])

    return "\n".join(lines)


def enforce_single_question_output(reply: str, next_action: str) -> str:
    """
    Output Guard: Nếu next_action là ASK_QUESTION, đảm bảo phản hồi của AI
    chỉ chứa tối đa 1 câu hỏi chính duy nhất, loại bỏ tình trạng hỏi dồn nhiều câu.
    """
    if next_action != NextAction.ASK_QUESTION.value:
        return reply

    text = str(reply or "").strip()
    if not text:
        return text

    # Tách các câu dựa trên dấu chấm, hỏi, than, hoặc xuống dòng
    # Giữ lại các khối phân tách
    sentences = re.split(r"(?<=[.?!])\s+|\n+", text)
    if len(sentences) <= 1:
        return text

    non_question_sentences: List[str] = []
    question_sentences: List[str] = []

    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        # Dấu hiệu nhận biết câu hỏi y tế: kết thúc bằng ? hoặc có từ để hỏi ở cuối
        norm_s = normalize_vietnamese_advanced(s_clean)
        is_q = s_clean.endswith("?") or bool(
            re.search(r"\b(?:o dau|bao lau|the nao|bao nhieu|phai khong|dung khong|sot khong)\s*[.?!]?$", norm_s)
        )
        if is_q:
            question_sentences.append(s_clean)
        else:
            non_question_sentences.append(s_clean)

    # Nếu AI hỏi từ 2 câu trở lên, chỉ giữ lại câu hỏi đầu tiên
    if len(question_sentences) > 1:
        selected_question = question_sentences[0]
        # Kết hợp các câu chào/thấu cảm phía trước với đúng 1 câu hỏi được chọn
        combined_text = " ".join(non_question_sentences) + " " + selected_question
        return combined_text.strip()

    return text
