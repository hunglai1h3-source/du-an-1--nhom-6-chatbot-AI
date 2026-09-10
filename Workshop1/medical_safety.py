"""
Module Medical Safety V2 cho MediCare AI.
Cung cấp Safety Gate nhiều tầng, phân loại RiskLevel, Deterministic Red Flags,
Context-Aware Safety đa lượt, Self-Harm Safety Flow và Fail-Safe handling.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RiskLevel(str, Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class SafetyCategory(str, Enum):
    BREATHING = "breathing"
    CHEST_CARDIAC = "chest_cardiac"
    STROKE_NEURO = "stroke_neuro"
    SEVERE_BLEEDING = "severe_bleeding"
    ANAPHYLAXIS = "anaphylaxis"
    POISONING_OVERDOSE = "poisoning_overdose"
    TRAUMA = "trauma"
    SELF_HARM_IMMEDIATE = "self_harm_immediate"
    SELF_HARM_CONCERN = "self_harm_concern"
    MENTAL_HEALTH_DISTRESS = "mental_health_distress"
    GENERAL_CAUTION = "general_caution"
    GENERAL = "general"


@dataclass
class SafetyResult:
    risk_level: RiskLevel
    category: str
    reason_code: str
    confidence: float
    should_stop_normal_flow: bool
    emergency_data: Optional[Dict[str, Any]] = None
    reply: Optional[str] = None
    safety_unknown: bool = False

    @property
    def is_emergency(self) -> bool:
        return self.risk_level == RiskLevel.EMERGENCY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "category": self.category,
            "reason_code": self.reason_code,
            "confidence": self.confidence,
            "should_stop_normal_flow": self.should_stop_normal_flow,
            "is_emergency": self.is_emergency,
            "safety_unknown": self.safety_unknown,
        }


@dataclass
class SafetyState:
    highest_risk_level: str = "normal"
    active_flags: List[str] = field(default_factory=list)
    last_checked_at: str = ""
    last_category: Optional[str] = None
    safety_unknown: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "highest_risk_level": self.highest_risk_level,
            "active_flags": list(self.active_flags),
            "last_checked_at": self.last_checked_at,
            "last_category": self.last_category,
            "safety_unknown": self.safety_unknown,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SafetyState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            highest_risk_level=str(data.get("highest_risk_level", "normal")),
            active_flags=list(data.get("active_flags") or []),
            last_checked_at=str(data.get("last_checked_at", "")),
            last_category=data.get("last_category"),
            safety_unknown=bool(data.get("safety_unknown", False)),
        )


# ==============================================================================
# 1. CHUẨN HÓA TIẾNG VIỆT & XỬ LÝ VIẾT TẮT / SLANG
# ==============================================================================

VIETNAMESE_SLANG_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:ko|k|hem|hong|khg|kh)\b", re.IGNORECASE), "khong"),
    (re.compile(r"\btui\b", re.IGNORECASE), "toi"),
    (re.compile(r"\bmk\b", re.IGNORECASE), "minh"),
    (re.compile(r"\bng\b", re.IGNORECASE), "nguoi"),
    (re.compile(r"\bbv\b", re.IGNORECASE), "benh vien"),
    (re.compile(r"\bbs\b", re.IGNORECASE), "bac si"),
    (re.compile(r"\bdc\b", re.IGNORECASE), "duoc"),
    (re.compile(r"\bnhiu\b", re.IGNORECASE), "nhieu"),
    (re.compile(r"\btho (?:ko|k) noi\b", re.IGNORECASE), "tho khong noi"),
    (re.compile(r"\bko tho (?:dc|duoc)\b", re.IGNORECASE), "khong tho duoc"),
    (re.compile(r"\bko danh thuc dc\b", re.IGNORECASE), "khong danh thuc duoc"),
    (re.compile(r"\bchay mau nhiu\b", re.IGNORECASE), "chay mau nhieu"),
]


def normalize_vietnamese_advanced(value: str) -> str:
    """
    Chuẩn hóa tiếng Việt:
    - Bỏ dấu NFD
    - Thay 'đ' -> 'd'
    - Chuẩn hóa viết tắt phổ biến
    - Xóa ký tự lạ, giữ khoảng trắng đơn
    """
    value = str(value or "").strip().lower()
    if not value:
        return ""

    # Thay các từ viết tắt trước khi chuẩn hóa NFD
    for pattern, replacement in VIETNAMESE_SLANG_MAP:
        value = pattern.sub(replacement, value)

    # NFD normalization
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "d")

    # Xóa ký tự lạ
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# ==============================================================================
# 2. DETERMINISTIC RED FLAGS & NEGATIONS (LAYER 1)
# ==============================================================================

EMERGENCY_NEGATIONS = (
    "khong kho tho",
    "khong con kho tho",
    "het kho tho",
    "khong dau nguc",
    "het dau nguc",
    "khong bat tinh",
    "khong co giat",
    "khong chay mau",
    "khong sot",
    "het sot",
    "khong tu tu",
    "khong co y dinh tu sat",
    "khong muon chet",
    "khong phai tu tu",
)

MILD_OR_NON_EMERGENCY_QUALIFIERS = [
    re.compile(r"\bdau nguc nhe\b"),
    re.compile(r"\bhoi dau nguc\b"),
    re.compile(r"\bdau nguc.*(?:khi ho|moi khi ho|khi hat hoi|luc ho)\b"),
    re.compile(r"\bdau co nguc\b"),
    re.compile(r"\bhoi kho tho khi di bo\b"),
    re.compile(r"\bkho tho nhe\b"),
    re.compile(r"\bhoi chong mat\b.*(?:chua an|doi|sang chua an)"),
    re.compile(r"\bchong mat vi (?:sang )?chua an\b"),
    re.compile(r"\bhoi dau bung\b"),
    re.compile(r"\bdau bung nhe\b"),
]

# Các mẫu cấp cứu xác định (EMERGENCY RED FLAGS)
DETERMINISTIC_EMERGENCY_PATTERNS: Dict[str, Tuple[str, ...]] = {
    SafetyCategory.ANAPHYLAXIS.value: (
        r"\bsoc phan ve\b",
        r"\bsung moi.*kho tho\b",
        r"\bsung luoi\b",
        r"\bsung hong.*kho tho\b",
        r"\bsung hong\b",
        r"\bdi ung.*kho tho\b",
        r"\bnoi me day.*kho tho\b",
    ),
    SafetyCategory.POISONING_OVERDOSE.value: (
        r"\buong qua lieu\b",
        r"\buong nham hoa chat\b",
        r"\buong nham thuoc\b",
        r"\bngo doc nghiem trong\b",
        r"\buong rat nhieu thuoc\b",
        r"\buong nham rat nhieu thuoc\b",
        r"\buong (?:[0-9]{2,}|hang chuc|ca vi|ca lo) vien thuoc\b",
    ),
    SafetyCategory.STROKE_NEURO.value: (
        r"\bmeo mieng\b",
        r"\bye[u]? liet\b",
        r"\bye[u]? mot ben\b",
        r"\bliet mot ben\b",
        r"\bnoi kho dot ngot\b",
        r"\bbat tinh\b",
        r"\bkhong danh thuc duoc\b",
        r"\blu lan nghiem trong\b",
        r"\bmat y thuc\b",
        r"\bco giat\b",
        r"\bdau dau du doi dot ngot\b",
        r"\bdau dau set danh\b",
    ),
    SafetyCategory.CHEST_CARDIAC.value: (
        r"\bdau nguc du doi\b",
        r"\bdau that nguc\b",
        r"\bdau nguc lan\b",
        r"\bbop nghet nguc\b",
        r"\bdau nguc.*(?:khong tho|kho tho|va mo hoi|ngat|bat tinh)\b",
    ),
    SafetyCategory.SEVERE_BLEEDING.value: (
        r"\bchay mau nhieu\b",
        r"\bchay mau khong cam\b",
        r"\bmat mau nhieu\b",
        r"\bnon ra mau\b",
        r"\bnon ra rat nhieu mau\b",
        r"\bho ra mau\b",
        r"\bho ra rat nhieu mau\b",
        r"\bdi ngoai phan den.*(?:chong mat|ngat|choang|yeu)\b",
    ),
    SafetyCategory.TRAUMA.value: (
        r"\bchan thuong dau nang\b",
        r"\bbat tinh sau tai nan\b",
        r"\btai nan.*(?:bat tinh|khong tho|chay mau khong cam)\b",
        r"\bchan thuong.*chay mau nhieu\b",
    ),
    SafetyCategory.BREATHING.value: (
        r"\bkhong tho duoc\b",
        r"\bnghet tho\b",
        r"\bthieu hoi\b",
        r"\btim moi\b",
        r"\btim tai\b",
        r"\bkho tho du doi\b",
        r"\bkho tho qua\b",
        r"\bkho tho nang\b",
        r"\bkho tho nghiem trong\b",
        r"\btho khong noi\b",
        r"\btho rat kho\b",
        r"\btho hon hen\b",
        r"\btho gap\b",
        r"\bkho tho\b",
    ),
}

# Thứ tự ưu tiên phân loại (Specificity priority)
CATEGORY_PRIORITY: List[str] = [
    SafetyCategory.ANAPHYLAXIS.value,
    SafetyCategory.POISONING_OVERDOSE.value,
    SafetyCategory.STROKE_NEURO.value,
    SafetyCategory.CHEST_CARDIAC.value,
    SafetyCategory.SEVERE_BLEEDING.value,
    SafetyCategory.TRAUMA.value,
    SafetyCategory.BREATHING.value,
]

SELF_HARM_PATTERNS = (
    r"\btu tu\b",
    r"\btu sat\b",
    r"\bmuon chet\b",
    r"\bdinh tu lam hai\b",
    r"\btu lam minh bi thuong\b",
    r"\by dinh tu sat\b",
    r"\buong thuoc tu tu\b",
    r"\buong thuoc tu sat\b",
    r"\buong thuoc de chet\b",
    r"\bcat co tay\b",
    r"\bkhong muon song nua\b",
)


# ==============================================================================
# 3. NỘI DUNG PHẢN HỒI AN TOÀN CHUẨN MỰC
# ==============================================================================

EMERGENCY_MEDICAL_REPLY = (
    "Bạn đang mô tả một dấu hiệu sức khỏe có thể NGUY HIỂM ĐẾN TÍNH MẠNG.\n\n"
    "HÃY GỌI 115 NGAY LẬP TỨC hoặc đến phòng cấp cứu gần nhất:\n\n"
    "- Ngồi hoặc nằm ở tư thế dễ thở, nới lỏng quần áo chật.\n"
    "- KHÔNG tự lái xe đến bệnh viện nếu đang choáng, khó thở hoặc mất thăng bằng.\n"
    "- Nhờ người thân hoặc người ở gần bên cạnh hỗ trợ và mở sẵn cửa cho nhân viên y tế.\n"
    "- Báo rõ tình trạng và các dấu hiệu nguy hiểm với tổng đài cấp cứu 115.\n\n"
    "Đây là tình huống khẩn cấp, bạn không nên chờ chatbot tư vấn trực tuyến."
)

SELF_HARM_EMERGENCY_REPLY = (
    "Tôi rất quan tâm đến sự an toàn và tính mạng của bạn lúc này. "
    "Bạn không phải chịu đựng điều này một mình, luôn có sự hỗ trợ sẵn sàng dành cho bạn.\n\n"
    "HÃY LIÊN HỆ HỖ TRỢ KHẨN CẤP NGAY BÂY GIỜ:\n\n"
    "- Gọi cấp cứu 115 hoặc đến ngay cơ sở y tế gần nhất nếu bạn đã uống thuốc hoặc tự làm tổn thương mình.\n"
    "- Hãy ở cạnh một người bạn, người thân trong gia đình hoặc người đáng tin cậy.\n"
    "- Tổng đài hỗ trợ tâm lý & phòng ngừa khủng hoảng (Đường dây nóng Ngày Mai): 096 306 1414\n"
    "- Viện Sức khỏe Tâm thần - Bệnh viện Bạch Mai: 024 3869 3731\n\n"
    "Xin hãy giữ an toàn cho bản thân và để những người xung quanh cũng như chuyên gia hỗ trợ bạn vượt qua thời khắc này."
)


def build_emergency_data_payload(result: SafetyResult) -> Dict[str, Any]:
    """Tạo cấu trúc JSON tương thích 100% với giao diện chat.js của Frontend."""
    is_self_harm = "self_harm" in result.category or result.category == SafetyCategory.MENTAL_HEALTH_DISTRESS.value
    title = "HỖ TRỢ KHẨN CẤP & BẢO VỆ AN TOÀN" if is_self_harm else "DẤU HIỆU CÓ THỂ CẦN CẤP CỨU"
    primary_action = "Gọi 115 hoặc trợ giúp ngay" if is_self_harm else "Gọi 115 ngay"
    secondary_action = "Nhờ người bên cạnh hỗ trợ"

    return {
        "active": True,
        "type": result.category,
        "title": title,
        "severity": "critical",
        "phone": "115",
        "phone_uri": "tel:115",
        "primary_action": primary_action,
        "secondary_action": secondary_action,
        "reason_code": result.reason_code,
    }


# ==============================================================================
# 4. DETERMINISTIC SAFETY (LAYER 1)
# ==============================================================================

def evaluate_deterministic_safety(message: str) -> SafetyResult:
    """
    Kiểm tra deterministic không phụ thuộc AI:
    - Bắt Red Flags cấp cứu rõ ràng
    - Bắt Self-Harm Flow
    - Loại trừ các trường hợp nhẹ / ngữ cảnh lành tính
    """
    normalized = normalize_vietnamese_advanced(message)
    if not normalized:
        return SafetyResult(
            risk_level=RiskLevel.NORMAL,
            category=SafetyCategory.GENERAL.value,
            reason_code="EMPTY_INPUT",
            confidence=1.0,
            should_stop_normal_flow=False,
        )

    # 1. Kiểm tra phủ định rõ ràng (ví dụ "không đau ngực", "không tự tử")
    if any(phrase in normalized for phrase in EMERGENCY_NEGATIONS):
        return SafetyResult(
            risk_level=RiskLevel.NORMAL,
            category=SafetyCategory.GENERAL.value,
            reason_code="EXPLICIT_NEGATION",
            confidence=0.9,
            should_stop_normal_flow=False,
        )

    # 2. Kiểm tra Self-Harm / Suicide (Ưu tiên số 1)
    for pattern in SELF_HARM_PATTERNS:
        if re.search(pattern, normalized):
            res = SafetyResult(
                risk_level=RiskLevel.EMERGENCY,
                category=SafetyCategory.SELF_HARM_IMMEDIATE.value,
                reason_code="SELF_HARM_TRIGGER",
                confidence=0.99,
                should_stop_normal_flow=True,
                reply=SELF_HARM_EMERGENCY_REPLY,
            )
            res.emergency_data = build_emergency_data_payload(res)
            return res

    # 3. Kiểm tra các điều kiện nhẹ / không cấp cứu (ví dụ "đau ngực nhẹ khi ho")
    is_mild = any(p.search(normalized) for p in MILD_OR_NON_EMERGENCY_QUALIFIERS)

    # 4. Kiểm tra 7 nhóm Red Flags y tế theo thứ tự ưu tiên độ đặc hiệu
    for category in CATEGORY_PRIORITY:
        patterns = DETERMINISTIC_EMERGENCY_PATTERNS.get(category, ())
        for pattern in patterns:
            if re.search(pattern, normalized):
                # Nếu là mẫu chung như 'kho tho' hoặc 'dau nguc' nhưng có qualifier nhẹ
                if is_mild:
                    return SafetyResult(
                        risk_level=RiskLevel.CAUTION,
                        category=category,
                        reason_code="MILD_SYMPTOM_QUALIFIED",
                        confidence=0.85,
                        should_stop_normal_flow=False,
                    )

                # Trường hợp Red Flag cấp cứu thật
                res = SafetyResult(
                    risk_level=RiskLevel.EMERGENCY,
                    category=category,
                    reason_code=f"RED_FLAG_{category.upper()}",
                    confidence=0.98,
                    should_stop_normal_flow=True,
                    reply=EMERGENCY_MEDICAL_REPLY,
                )
                res.emergency_data = build_emergency_data_payload(res)
                return res

    # 5. Kiểm tra tình trạng cấp thiết cần khám trong ngày (URGENT)
    urgent_patterns = [
        r"\bsot cao\b", r"\bsot (?:39|40|41)\b", r"\bsot li bi\b",
        r"\bdau bung du doi\b", r"\bdau bung quan quai\b",
        r"\bnon lien tuc\b", r"\bnon khong dung\b",
        r"\bvet thuong sau\b", r"\brach da chay mau\b",
    ]
    if any(re.search(p, normalized) for p in urgent_patterns):
        return SafetyResult(
            risk_level=RiskLevel.URGENT,
            category=SafetyCategory.GENERAL_CAUTION.value,
            reason_code="URGENT_EVALUATION_NEEDED",
            confidence=0.88,
            should_stop_normal_flow=False,
        )

    # 6. Kiểm tra tình trạng đau/khó chịu thông thường (CAUTION)
    caution_patterns = [
        r"\bdau bung\b", r"\bchong mat\b", r"\bbuon non\b", r"\bsot\b",
        r"\bdi ngoai\b", r"\bho keo dai\b", r"\bphat ban\b"
    ]
    if any(re.search(p, normalized) for p in caution_patterns):
        return SafetyResult(
            risk_level=RiskLevel.CAUTION,
            category=SafetyCategory.GENERAL_CAUTION.value,
            reason_code="GENERAL_SYMPTOMS_PRESENT",
            confidence=0.8,
            should_stop_normal_flow=False,
        )

    return SafetyResult(
        risk_level=RiskLevel.NORMAL,
        category=SafetyCategory.GENERAL.value,
        reason_code="NO_CONCERN_DETECTED",
        confidence=0.95,
        should_stop_normal_flow=False,
    )


# ==============================================================================
# 5. CONTEXT-AWARE SAFETY (LAYER 2)
# ==============================================================================

def evaluate_contextual_safety(
    current_message: str,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    previous_safety_state: Optional[SafetyState] = None,
) -> SafetyResult:
    """
    Kiểm tra nhận thức ngữ cảnh đa lượt:
    - Quét các tin nhắn trước của user
    - Phát hiện tình huống leo thang rủi ro:
      Ví dụ: Tin 1 ("uống 30 viên thuốc") + Tin 2 ("giờ tôi nhìn mờ và buồn ngủ")
      -> Layer 1 của Tin 2 có thể không có từ 'quá liều', nhưng kết hợp với Tin 1 sẽ trigger EMERGENCY!
    """
    history_user_messages: List[str] = []
    if recent_history and isinstance(recent_history, list):
        for item in recent_history:
            if isinstance(item, dict) and item.get("role") == "user":
                content = str(item.get("content") or "").strip()
                if content:
                    history_user_messages.append(content)

    if not history_user_messages:
        return evaluate_deterministic_safety(current_message)

    current_norm = normalize_vietnamese_advanced(current_message)
    past_texts_combined = " ".join(normalize_vietnamese_advanced(m) for m in history_user_messages[-3:])

    # Kịch bản 1: Quá liều thuốc / uống thuốc tích lũy + triệu chứng ngộ độc
    has_prior_overdose_mention = bool(
        re.search(r"(?:uong|dung|nuot|uong nham).*(?:[0-9]{2,}|hang chuc|ca vi|ca lo|nhieu|qua lieu).*(?:vien|lo|thuoc)", past_texts_combined)
        or re.search(r"[0-9]{2,}\s*vien\s*thuoc", past_texts_combined)
        or "uong thuoc ngu" in past_texts_combined
        or "uong nham thuoc" in past_texts_combined
        or "ngo doc" in past_texts_combined
    )
    has_escalating_symptoms = bool(
        re.search(r"\b(?:buon ngu|nhin mo|mat mo|choang|ngat|kho tho|dau bung du|non|kho chiu|me man)\b", current_norm)
    )

    if has_prior_overdose_mention and has_escalating_symptoms:
        res = SafetyResult(
            risk_level=RiskLevel.EMERGENCY,
            category=SafetyCategory.POISONING_OVERDOSE.value,
            reason_code="CONTEXTUAL_OVERDOSE_ESCALATION",
            confidence=0.95,
            should_stop_normal_flow=True,
            reply=EMERGENCY_MEDICAL_REPLY,
        )
        res.emergency_data = build_emergency_data_payload(res)
        return res

    # Kịch bản 2: Ý định tự hại ở lượt trước + bất kỳ hành động/triệu chứng nào ở lượt này
    has_prior_self_harm = any(re.search(p, past_texts_combined) for p in SELF_HARM_PATTERNS)
    if has_prior_self_harm:
        res = SafetyResult(
            risk_level=RiskLevel.EMERGENCY,
            category=SafetyCategory.SELF_HARM_IMMEDIATE.value,
            reason_code="CONTEXTUAL_SELF_HARM_PERSISTENCE",
            confidence=0.96,
            should_stop_normal_flow=True,
            reply=SELF_HARM_EMERGENCY_REPLY,
        )
        res.emergency_data = build_emergency_data_payload(res)
        return res

    # Kịch bản 3: Đau ngực ở lượt trước + khó thở / choáng ở lượt này
    if "dau nguc" in past_texts_combined and re.search(r"\b(?:kho tho|choang|ngat|bat tinh)\b", current_norm):
        res = SafetyResult(
            risk_level=RiskLevel.EMERGENCY,
            category=SafetyCategory.CHEST_CARDIAC.value,
            reason_code="CONTEXTUAL_CARDIAC_ESCALATION",
            confidence=0.95,
            should_stop_normal_flow=True,
            reply=EMERGENCY_MEDICAL_REPLY,
        )
        res.emergency_data = build_emergency_data_payload(res)
        return res

    # Nếu không có tích lũy đặc biệt, trả về kết quả deterministic của câu hiện tại
    return evaluate_deterministic_safety(current_message)


# ==============================================================================
# 6. IMAGE-ONLY SAFETY EVALUATION
# ==============================================================================

def evaluate_image_safety(image_file: Any = None) -> SafetyResult:
    """
    Quy trình kiểm tra an toàn khi request CHỈ CÓ ẢNH (không có text):
    - Không bypass safety pipeline.
    - Đặt trạng thái thận trọng CAUTION và safety_unknown = True để luồng downstream
      áp dụng prompt phân tích an toàn nghiêm ngặt.
    """
    return SafetyResult(
        risk_level=RiskLevel.CAUTION,
        category="image_only_intake",
        reason_code="IMAGE_REQUIRES_STRUCTURED_SAFETY",
        confidence=0.7,
        should_stop_normal_flow=False,
        safety_unknown=True,
    )


# ==============================================================================
# 7. SAFETY GATE CHÍNH (ORCHESTRATOR & FAIL-SAFE)
# ==============================================================================

def check_medical_safety(
    message: Any,
    recent_history: Optional[List[Dict[str, Any]]] = None,
    previous_safety_state: Any = None,
    has_image: bool = False,
) -> SafetyResult:
    """
    Điểm vào chính của Safety Gate:
    1. Text safety LUÔN LUÔN ĐƯỢC CHẠY nếu có text (bất kể has_image là True hay False).
    2. Nếu chỉ có ảnh: Chạy qua evaluate_image_safety.
    3. Fail-safe: Nếu gặp lỗi exception ngoài ý muốn, không bao giờ làm crash server;
       trả về trạng thái CAUTION an toàn kèm cờ safety_unknown.
    """
    try:
        user_text = str(message or "").strip()

        # Trường hợp 1: Có text (có thể kèm hoặc không kèm ảnh)
        if user_text:
            # Chạy Layer 1 + Layer 2 Contextual
            result = evaluate_contextual_safety(
                current_message=user_text,
                recent_history=recent_history,
                previous_safety_state=previous_safety_state,
            )
            return result

        # Trường hợp 2: Chỉ có ảnh (không có text)
        if has_image:
            return evaluate_image_safety()

        # Trường hợp 3: Không có cả text lẫn ảnh
        return SafetyResult(
            risk_level=RiskLevel.NORMAL,
            category=SafetyCategory.GENERAL.value,
            reason_code="EMPTY_REQUEST",
            confidence=1.0,
            should_stop_normal_flow=False,
        )

    except Exception as error:
        # FAIL-SAFE: Không để lỗi trong module an toàn làm sập ứng dụng (dùng ASCII trong print để tránh lỗi encoding console)
        try:
            print(f"[FAIL-SAFE] Error in check_medical_safety: {type(error).__name__}")
        except Exception:
            pass
        return SafetyResult(
            risk_level=RiskLevel.CAUTION,
            category=SafetyCategory.GENERAL_CAUTION.value,
            reason_code="SAFETY_SUBSYSTEM_FAILSAFE",
            confidence=0.5,
            should_stop_normal_flow=False,
            safety_unknown=True,
        )


def create_updated_safety_state(
    safety_result: SafetyResult,
    previous_safety_state: Any = None,
) -> SafetyState:
    """Tạo hoặc cập nhật SafetyState, bảo đảm nguyên tắc 'highest validated risk wins'."""
    prev = SafetyState.from_dict(previous_safety_state) if previous_safety_state else SafetyState()

    risk_order = {
        RiskLevel.NORMAL.value: 0,
        RiskLevel.CAUTION.value: 1,
        RiskLevel.URGENT.value: 2,
        RiskLevel.EMERGENCY.value: 3,
    }
    prev_score = risk_order.get(prev.highest_risk_level, 0)
    curr_score = risk_order.get(safety_result.risk_level.value, 0)

    highest = safety_result.risk_level.value if curr_score >= prev_score else prev.highest_risk_level
    new_flags = list(prev.active_flags)
    if safety_result.risk_level != RiskLevel.NORMAL and safety_result.category not in new_flags:
        new_flags.append(safety_result.category)

    return SafetyState(
        highest_risk_level=highest,
        active_flags=new_flags,
        last_checked_at=datetime.now(timezone.utc).isoformat(),
        last_category=safety_result.category,
        safety_unknown=safety_result.safety_unknown,
    )



# ==============================================================================
# 8. OUTPUT GUARD (KIỂM TRA ĐẦU RA CỦA AI)
# ==============================================================================

OUTPUT_FORBIDDEN_DIAGNOSES = [
    re.compile(r"\b(?:toi chan doan|chung toi chan doan|khang dinh ban|ban chac chan bi|ban chac chan mac)\b", re.IGNORECASE),
]

MEDICAL_DISCLAIMER_SUFFIX = (
    "\n\n*Lưu ý an toàn: Thông tin trên chỉ mang tính tham khảo ban đầu, không thay thế chẩn đoán "
    "và chỉ định chuyên môn từ bác sĩ. Khi triệu chứng kéo dài hoặc trở nặng, hãy đi khám tại cơ sở y tế.*"
)


def lightweight_output_guard(reply: str) -> str:
    """
    Kiểm tra nhẹ đầu ra AI:
    - Nếu câu trả lời có từ ngữ khẳng định chẩn đoán tuyệt đối -> làm mềm lại và bổ sung disclaimer.
    """
    if not reply or not isinstance(reply, str):
        return reply

    text = reply.strip()
    normalized_reply = normalize_vietnamese_advanced(text)
    needs_disclaimer = False

    for pattern in OUTPUT_FORBIDDEN_DIAGNOSES:
        if pattern.search(normalized_reply):
            needs_disclaimer = True
            break

    if needs_disclaimer and "Lưu ý an toàn" not in text:
        text += MEDICAL_DISCLAIMER_SUFFIX

    return text


# ==============================================================================
# 9. COMPATIBILITY ALIASES (CHO HỆ THỐNG CŨ)
# ==============================================================================

def detect_emergency_message(message: str) -> Optional[Dict[str, Any]]:
    """Hàm tương thích cho code cũ gọi detect_emergency_message()."""
    result = evaluate_deterministic_safety(message)
    if result.risk_level == RiskLevel.EMERGENCY and result.emergency_data:
        return {
            "type": result.category,
            "title": result.emergency_data.get("title", "DẤU HIỆU CÓ THỂ CẦN CẤP CỨU"),
            "phone": result.emergency_data.get("phone", "115"),
            "phone_uri": result.emergency_data.get("phone_uri", "tel:115"),
            "severity": "critical",
            "reply": result.reply or EMERGENCY_MEDICAL_REPLY,
            "primary_action": result.emergency_data.get("primary_action", "Gọi 115 ngay"),
            "secondary_action": result.emergency_data.get("secondary_action", "Nhờ người bên cạnh hỗ trợ"),
        }
    return None
