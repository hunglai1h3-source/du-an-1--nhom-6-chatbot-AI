"""
Module Next-Best Question Engine cho MediCare AI (Phase 9 - Checkpoint F).
Xác định câu hỏi lâm sàng có giá trị thông tin cao nhất (Highest Information Gain),
hoặc quyết định KHÔNG hỏi nếu đã đủ thông tin hoặc tình huống khẩn cấp.

CÁC NGUYÊN TẮC BẮT BUỘC:
1. Không bao giờ hỏi lại thông tin đã có trong hồ sơ (PersonalHealthContext / Profile).
2. Không hỏi lại câu hỏi thuộc slot người dùng đã từ chối trả lời (Declined Slots).
3. Không hỏi lại câu hỏi cùng một slot đã hỏi trong cùng cuộc trò chuyện (Asked Slots).
4. Mỗi lượt chỉ đưa ra DUY NHẤT một câu hỏi trọng tâm (Single Question Invariant).
5. Khi khẩn cấp (EMERGENCY) hoặc khi người dùng yêu cầu tư vấn ngay, KHÔNG hỏi thêm.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from conversation_engine import (
    ConversationStage,
    MedicalConversationState,
    NextAction,
)
from medical_safety import RiskLevel, SafetyResult
from personal_health_context import PersonalHealthContext
from adaptive_severity_engine import AdaptiveSeverityAssessment, EffectiveConcernLevel


class QuestionIntent(str, Enum):
    CONTRADICTION_RESOLUTION = "CONTRADICTION_RESOLUTION"
    RED_FLAG_RULE_OUT = "RED_FLAG_RULE_OUT"
    CHIEF_COMPLAINT = "CHIEF_COMPLAINT"
    SYMPTOM_LOCATION = "SYMPTOM_LOCATION"
    ONSET_DURATION = "ONSET_DURATION"
    SEVERITY_IMPACT = "SEVERITY_IMPACT"
    ASSOCIATED_SYMPTOMS = "ASSOCIATED_SYMPTOMS"
    TRIGGER_RELIEF = "TRIGGER_RELIEF"
    MEDICATIONS_TAKEN = "MEDICATIONS_TAKEN"
    NONE = "NONE"


@dataclass
class NextBestQuestion:
    slot_to_ask: Optional[str]
    question_text: Optional[str]
    intent: QuestionIntent
    information_gain_score: float
    should_ask: bool
    skip_reason: Optional[str] = None
    declined_detected: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_to_ask": self.slot_to_ask,
            "question_text": self.question_text,
            "intent": self.intent.value,
            "information_gain_score": self.information_gain_score,
            "should_ask": self.should_ask,
            "skip_reason": self.skip_reason,
            "declined_detected": self.declined_detected,
        }


# Mẫu từ khóa phát hiện người dùng từ chối / không muốn trả lời câu hỏi
DECLINE_PATTERNS = [
    r"\b(không|chẳng|ko|k)\s+(rõ|biết|nhớ|chắc|để ý|quan tâm)\b",
    r"\b(bỏ qua|thôi|đừng hỏi|mệt quá|tư vấn luôn|trả lời luôn|nói luôn|kết luận luôn)\b",
    r"\b(không muốn|không cần|chưa muốn)\s+(nói|trả lời|chia sẻ)\b",
]


def detect_user_declination(user_message: str) -> bool:
    """Kiểm tra xem người dùng có đang từ chối trả lời câu hỏi vừa rồi không."""
    if not user_message:
        return False
    norm = unicodedata.normalize("NFD", user_message.lower())
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    for pat in DECLINE_PATTERNS:
        pat_norm = unicodedata.normalize("NFD", pat)
        pat_norm = "".join(c for c in pat_norm if unicodedata.category(c) != "Mn")
        if re.search(pat_norm, norm):
            return True
    return False


def determine_next_best_question(
    user_message: str,
    personal_context: Optional[PersonalHealthContext] = None,
    conv_state: Optional[MedicalConversationState] = None,
    safety_result: Optional[SafetyResult] = None,
    adaptive_assessment: Optional[AdaptiveSeverityAssessment] = None,
    declined_slots: Optional[Set[str]] = None,
) -> NextBestQuestion:
    """
    Xác định câu hỏi lâm sàng đơn lẻ có giá trị thông tin cao nhất.
    """
    declined_slots = set(declined_slots or set())
    last_asked = conv_state.last_question_slot if conv_state else None

    # 1. Phát hiện người dùng từ chối trả lời câu hỏi trước đó
    declined_slot_found: Optional[str] = None
    if last_asked and detect_user_declination(user_message):
        declined_slots.add(last_asked)
        declined_slot_found = last_asked

    # 2. Kiểm tra các điều kiện tiên quyết: KHÔNG HỎI nếu:
    # 2a. Tình huống cấp cứu (EMERGENCY)
    if safety_result and safety_result.risk_level == RiskLevel.EMERGENCY:
        return NextBestQuestion(
            slot_to_ask=None,
            question_text=None,
            intent=QuestionIntent.NONE,
            information_gain_score=0.0,
            should_ask=False,
            skip_reason="Tình huống cấp cứu khẩn cấp - dừng hỏi để hướng dẫn xử trí ngay",
            declined_detected=declined_slot_found,
        )

    if adaptive_assessment and adaptive_assessment.effective_concern_level == EffectiveConcernLevel.EMERGENCY:
        return NextBestQuestion(
            slot_to_ask=None,
            question_text=None,
            intent=QuestionIntent.NONE,
            information_gain_score=0.0,
            should_ask=False,
            skip_reason="Đánh giá quan ngại cấp cứu (EMERGENCY) - dừng hỏi",
            declined_detected=declined_slot_found,
        )

    # 2b. Người dùng yêu cầu tư vấn ngay mà không muốn hỏi thêm
    if any(kw in user_message.lower() for kw in ("tư vấn luôn", "trả lời luôn", "nói luôn đi", "đừng hỏi nữa")):
        return NextBestQuestion(
            slot_to_ask=None,
            question_text=None,
            intent=QuestionIntent.NONE,
            information_gain_score=0.0,
            should_ask=False,
            skip_reason="Người dùng yêu cầu đưa ra tư vấn trực tiếp, không hỏi thêm",
            declined_detected=declined_slot_found,
        )

    # 2c. Giai đoạn đã đủ thông tin (ASSESSMENT hoặc số lượt hỏi >= 4)
    turn_count = conv_state.turn_count if conv_state else 0
    asked_slots = set(conv_state.asked_slots if conv_state else [])
    if conv_state and conv_state.stage in (ConversationStage.ASSESSMENT.value, ConversationStage.FOLLOW_UP.value):
        if len(asked_slots) >= 2 or turn_count >= 3:
            return NextBestQuestion(
                slot_to_ask=None,
                question_text=None,
                intent=QuestionIntent.NONE,
                information_gain_score=0.0,
                should_ask=False,
                skip_reason="Đã đủ thông tin để định hướng sơ bộ",
                declined_detected=declined_slot_found,
            )

    # 3. Thu thập thông tin đã biết để TUYỆT ĐỐI KHÔNG HỎI LẠI
    known_slots: Set[str] = set()

    # Từ PersonalHealthContext (Hồ sơ bệnh nhân)
    if personal_context:
        if personal_context.age is not None:
            known_slots.add("age")
        if personal_context.gender:
            known_slots.add("gender")
        if personal_context.weight_kg is not None:
            known_slots.add("weight_kg")
        if personal_context.height_cm is not None:
            known_slots.add("height_cm")
        if personal_context.known_conditions:
            known_slots.add("medical_conditions")
        if personal_context.allergies:
            known_slots.add("allergies")
        if personal_context.current_medications:
            known_slots.add("current_medications")
        if personal_context.pregnancy_context:
            known_slots.add("pregnancy_status")

    # Từ Conversation State Slots
    if conv_state and conv_state.slots:
        slots = conv_state.slots
        if slots.chief_complaint:
            known_slots.add("chief_complaint")
        if slots.symptom_location:
            known_slots.add("symptom_location")
        if slots.onset:
            known_slots.add("onset")
        if slots.duration:
            known_slots.add("duration")
        if slots.severity or slots.pain_scale is not None:
            known_slots.add("severity")
            known_slots.add("pain_scale")
        if slots.fever is not None:
            known_slots.add("fever")
        if slots.associated_symptoms:
            known_slots.add("associated_symptoms")

    # 4. Lập danh sách ứng viên câu hỏi theo Information Gain
    candidates: List[Tuple[float, str, QuestionIntent, str]] = []

    # Ứng viên 1: Làm rõ mâu thuẫn dữ liệu (Contradiction Resolution) - Ưu tiên 95
    if personal_context and personal_context.conflicts:
        unresolved_conflict = personal_context.conflicts[0]
        field_name = unresolved_conflict.get("field", "thông tin")
        if field_name not in asked_slots and field_name not in declined_slots:
            candidates.append((
                95.0,
                f"conflict_{field_name}",
                QuestionIntent.CONTRADICTION_RESOLUTION,
                f"Để tư vấn chính xác nhất, bạn có thể xác nhận lại giúp tôi về {field_name} hiện tại của bạn không?"
            ))

    # Ứng viên 2: Khảo sát dấu hiệu cờ đỏ nguy hiểm (Red Flag Rule-Out) - Ưu tiên 90
    # Nếu triệu chứng liên quan đến ngực, đầu dữ dội, khó thở, co giật
    msg_low = user_message.lower()
    complaint_low = (conv_state.slots.chief_complaint or "").lower() if conv_state and conv_state.slots else ""
    combined_symptom_text = f"{msg_low} {complaint_low}"

    if any(w in combined_symptom_text for w in ("ngực", "tim", "khó thở", "hụt hơi", "thở dốc")):
        if "red_flag_cardiac" not in asked_slots and "red_flag_cardiac" not in declined_slots:
            candidates.append((
                90.0,
                "red_flag_cardiac",
                QuestionIntent.RED_FLAG_RULE_OUT,
                "Cơn đau tức ngực có lan lên cổ, cằm, vai hay cánh tay trái không, và bạn có cảm giác vã mồ hôi hay khó thở kèm theo không?"
            ))
    elif any(w in combined_symptom_text for w in ("đau đầu", "nhức đầu", "chóng mặt", "choáng")):
        if "red_flag_neuro" not in asked_slots and "red_flag_neuro" not in declined_slots:
            candidates.append((
                88.0,
                "red_flag_neuro",
                QuestionIntent.RED_FLAG_RULE_OUT,
                "Cơn đau đầu xuất hiện đột ngột dữ dội (như sét đánh), hay có kèm theo yếu liệt tay chân, mờ mắt hoặc cứng cổ không?"
            ))

    # Ứng viên 3: Triệu chứng chính / Vị trí cụ thể (Chief Complaint & Location) - Ưu tiên 80
    if "chief_complaint" not in known_slots and "chief_complaint" not in asked_slots and "chief_complaint" not in declined_slots:
        candidates.append((
            80.0,
            "chief_complaint",
            QuestionIntent.CHIEF_COMPLAINT,
            "Bạn đang cảm thấy khó chịu nhất ở vị trí nào và triệu chứng cụ thể là gì?"
        ))
    elif "symptom_location" not in known_slots and "symptom_location" not in asked_slots and "symptom_location" not in declined_slots:
        # Nếu đã có triệu chứng nhưng chưa rõ vị trí
        if any(w in combined_symptom_text for w in ("đau", "ngứa", "phát ban", "sưng", "nổi mẩn", "mỏi")):
            candidates.append((
                75.0,
                "symptom_location",
                QuestionIntent.SYMPTOM_LOCATION,
                "Cảm giác khó chịu này xuất hiện cụ thể ở vị trí nào trên cơ thể bạn?"
            ))

    # Ứng viên 4: Thời gian khởi phát & Diễn tiến (Onset & Duration) - Ưu tiên 70
    if "duration" not in known_slots and "duration" not in asked_slots and "duration" not in declined_slots:
        candidates.append((
            70.0,
            "duration",
            QuestionIntent.ONSET_DURATION,
            "Triệu chứng này bắt đầu từ khi nào và diễn ra liên tục hay từng cơn ngắt quãng?"
        ))

    # Ứng viên 5: Mức độ nghiêm trọng / Điểm đau (Severity & Impact) - Ưu tiên 60
    if "severity" not in known_slots and "severity" not in asked_slots and "severity" not in declined_slots:
        candidates.append((
            60.0,
            "severity",
            QuestionIntent.SEVERITY_IMPACT,
            "Nếu đánh giá trên thang điểm từ 1 đến 10 (1 là rất nhẹ, 10 là dữ dội), mức độ khó chịu hiện tại của bạn khoảng bao nhiêu điểm?"
        ))

    # Ứng viên 6: Triệu chứng đi kèm (Associated Symptoms) - Ưu tiên 50
    if "associated_symptoms" not in known_slots and "associated_symptoms" not in asked_slots and "associated_symptoms" not in declined_slots:
        candidates.append((
            50.0,
            "associated_symptoms",
            QuestionIntent.ASSOCIATED_SYMPTOMS,
            "Ngoài biểu hiện trên, bạn có bị sốt, buồn nôn, mệt mỏi hay có dấu hiệu bất thường nào khác đi kèm không?"
        ))

    # Ứng viên 7: Yếu tố tăng giảm (Trigger & Relieving) - Ưu tiên 40
    if "trigger_relief" not in asked_slots and "trigger_relief" not in declined_slots:
        candidates.append((
            40.0,
            "trigger_relief",
            QuestionIntent.TRIGGER_RELIEF,
            "Bạn có nhận thấy điều gì làm triệu chứng tăng lên (như khi vận động, ăn uống) hoặc giảm bớt đi không?"
        ))

    # Ứng viên 8: Thuốc hoặc biện pháp đã dùng (Medications Taken) - Ưu tiên 30
    if "medications_taken" not in asked_slots and "medications_taken" not in declined_slots:
        candidates.append((
            30.0,
            "medications_taken",
            QuestionIntent.MEDICATIONS_TAKEN,
            "Từ khi xuất hiện triệu chứng, bạn đã uống thuốc gì hoặc áp dụng biện pháp xử trí nào chưa?"
        ))

    # 5. Lọc các ứng viên không hợp lệ (đã có trong known_slots, đã hỏi, hoặc đã từ chối)
    valid_candidates = []
    for score, slot, intent, q_text in candidates:
        if slot in known_slots:
            continue
        if slot in asked_slots:
            continue
        if slot in declined_slots:
            continue
        valid_candidates.append((score, slot, intent, q_text))

    if not valid_candidates:
        return NextBestQuestion(
            slot_to_ask=None,
            question_text=None,
            intent=QuestionIntent.NONE,
            information_gain_score=0.0,
            should_ask=False,
            skip_reason="Tất cả các thông tin cần thiết đã được thu thập hoặc người dùng đã từ chối",
            declined_detected=declined_slot_found,
        )

    # 6. Chọn câu hỏi có Information Gain cao nhất (DUY NHẤT 1 CÂU)
    valid_candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_slot, best_intent, best_text = valid_candidates[0]

    return NextBestQuestion(
        slot_to_ask=best_slot,
        question_text=best_text,
        intent=best_intent,
        information_gain_score=best_score,
        should_ask=True,
        skip_reason=None,
        declined_detected=declined_slot_found,
    )


def format_next_best_question_directive_for_prompt(nbq: NextBestQuestion) -> str:
    """
    Tạo chỉ thị điều hướng câu hỏi duy nhất cho System Prompt của LLM.
    """
    lines = [
        "CHỈ THỊ CÂU HỎI LÂM SÀNG TRỌNG TÂM (NEXT-BEST QUESTION ENGINE):",
    ]

    if nbq.should_ask and nbq.question_text:
        lines.append(f"- Mục tiêu khai thác: {nbq.intent.value} (slot: {nbq.slot_to_ask})")
        lines.append(
            f"- QUY TẮC BẮT BUỘC: Bạn CHỈ ĐƯỢC PHÉP hỏi DUY NHẤT MỘT CÂU HỎI ở cuối phản hồi. "
            f"Hãy tích hợp câu hỏi sau bằng giọng điệu ân cần, tự nhiên: \"{nbq.question_text}\""
        )
        lines.append("- Tuyệt đối KHÔNG hỏi thêm câu thứ hai hoặc tạo danh sách câu hỏi khảo sát.")
    else:
        lines.append("- HỆ THỐNG YÊU CẦU: KHÔNG ĐƯỢC HỎI THÊM BẤT KỲ CÂU HỎI NÀO.")
        lines.append(f"- Lý do: {nbq.skip_reason or 'Đã đủ thông tin hoặc tình huống khẩn cấp'}.")
        lines.append(
            "- Hãy tập trung toàn bộ phản hồi vào phân tích y tế sơ bộ, "
            "hướng dẫn chăm sóc và các dấu hiệu cảnh báo cần đi khám ngay."
        )

    return "\n".join(lines)
