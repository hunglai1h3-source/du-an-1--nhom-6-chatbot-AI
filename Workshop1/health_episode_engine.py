# -*- coding: utf-8 -*-
"""
Phase 9: Health Episode Engine & Event Timeline.

Implements:
- First-class HealthEpisode lifecycle entity
- Status progression: OPEN, MONITORING, IMPROVING, WORSENING, RESOLVED, ESCALATED
- Episode Event Timeline with idempotency via client_message_id
- Episode Linking Policy: SAME_EPISODE_HIGH, SAME_EPISODE_POSSIBLE, NEW_EPISODE_HIGH, RECURRENCE, UNCERTAIN
- Recurrence handling: links via recurrence_of_episode_id without reopening past resolved episodes
- Trend Detection Engine: NEW, STABLE, IMPROVING, WORSENING, FLUCTUATING, INSUFFICIENT_DATA
- Machine-readable trend reasons
- Profile-scoped persistence and prompt formatting
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. ENUMS & CONSTANTS
# ==============================================================================

class EpisodeStatus(str, Enum):
    OPEN = "OPEN"                  # Đang diễn ra đợt bệnh mới hoặc đang thu thập triệu chứng
    MONITORING = "MONITORING"      # Đang theo dõi tiến triển tại nhà
    IMPROVING = "IMPROVING"        # Triệu chứng đang thuyên giảm rõ rệt
    WORSENING = "WORSENING"        # Triệu chứng diễn tiến nặng lên hoặc xuất hiện dấu hiệu mới
    RESOLVED = "RESOLVED"          # Đã bình phục / khỏi bệnh hoàn toàn (người dùng xác nhận)
    ESCALATED = "ESCALATED"        # Đã chuyển tuyến đi khám chuyên khoa hoặc cấp cứu
    UNKNOWN = "UNKNOWN"


class EpisodeEventType(str, Enum):
    SYMPTOM_REPORTED = "SYMPTOM_REPORTED"
    SEVERITY_CHANGED = "SEVERITY_CHANGED"
    NEW_SYMPTOM = "NEW_SYMPTOM"
    SYMPTOM_RESOLVED = "SYMPTOM_RESOLVED"
    MEDICATION_REPORTED = "MEDICATION_REPORTED"
    USER_CORRECTION = "USER_CORRECTION"
    RISK_CHANGED = "RISK_CHANGED"
    ACTION_RECOMMENDED = "ACTION_RECOMMENDED"
    FOLLOWUP_UPDATE = "FOLLOWUP_UPDATE"
    USER_REPORT = "USER_REPORT"
    OTHER = "OTHER"


class EpisodeLinkingConfidence(str, Enum):
    SAME_EPISODE_HIGH = "SAME_EPISODE_HIGH"          # Tiếp tục cùng một đợt bệnh đang diễn ra
    SAME_EPISODE_POSSIBLE = "SAME_EPISODE_POSSIBLE"  # Khả năng cao là đợt bệnh cũ
    NEW_EPISODE_HIGH = "NEW_EPISODE_HIGH"            # Đợt bệnh hoàn toàn mới ở vị trí / triệu chứng khác
    RECURRENCE = "RECURRENCE"                        # Đợt tái phát của vấn đề sức khỏe trước đây
    UNCERTAIN = "UNCERTAIN"                          # Chưa chắc chắn, cần làm rõ nếu cần


class EpisodeTrend(str, Enum):
    NEW = "NEW"
    STABLE = "STABLE"
    IMPROVING = "IMPROVING"
    WORSENING = "WORSENING"
    FLUCTUATING = "FLUCTUATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ==============================================================================
# 2. DATA MODELS
# ==============================================================================

@dataclass
class HealthEpisode:
    episode_id: str = field(default_factory=lambda: f"ep_{uuid4().hex[:12]}")
    user_id: Optional[int] = None
    profile_type: str = "self"
    profile_ref: str = "self"
    chief_complaint: str = ""
    normalized_problem: Optional[str] = None
    body_location: Optional[str] = None
    onset_at: Optional[str] = None
    first_reported_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = EpisodeStatus.OPEN.value
    severity_current: int = 1
    severity_peak: int = 1
    pain_scale: Optional[int] = None
    fever: bool = False
    associated_symptoms: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    medications_taken: List[str] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)
    outcome: Optional[str] = None
    topic: Optional[str] = None
    conversation_ids: List[str] = field(default_factory=list)
    source_message_ids: List[int] = field(default_factory=list)
    safety_peak_level: str = "NORMAL"
    confidence: str = "CONFIRMED"
    recurrence_of_episode_id: Optional[str] = None
    trend: Optional[EpisodeTrend] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "user_id": self.user_id,
            "profile_type": self.profile_type,
            "profile_ref": self.profile_ref,
            "chief_complaint": self.chief_complaint,
            "normalized_problem": self.normalized_problem,
            "body_location": self.body_location,
            "onset_at": self.onset_at,
            "first_reported_at": self.first_reported_at,
            "last_updated_at": self.last_updated_at,
            "status": self.status,
            "severity_current": self.severity_current,
            "severity_peak": self.severity_peak,
            "pain_scale": self.pain_scale,
            "fever": self.fever,
            "associated_symptoms": list(self.associated_symptoms),
            "red_flags": list(self.red_flags),
            "medications_taken": list(self.medications_taken),
            "actions_taken": list(self.actions_taken),
            "outcome": self.outcome,
            "topic": self.topic,
            "conversation_ids": list(self.conversation_ids),
            "source_message_ids": list(self.source_message_ids),
            "safety_peak_level": self.safety_peak_level,
            "confidence": self.confidence,
            "recurrence_of_episode_id": self.recurrence_of_episode_id,
        }


@dataclass
class HealthEpisodeEvent:
    episode_id: str
    event_type: str
    event_data: Dict[str, Any]
    conversation_id: Optional[str] = None
    message_id: Optional[int] = None
    client_message_id: Optional[str] = None
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "event_type": self.event_type,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "client_message_id": self.client_message_id,
            "event_data": dict(self.event_data),
            "occurred_at": self.occurred_at,
        }


# ==============================================================================
# 3. EPISODE IDENTIFICATION & LINKING POLICY
# ==============================================================================

# Từ vựng ngôn ngữ chỉ sự tiếp diễn hoặc tái phát
CONTINUATION_SIGNALS = [
    "vẫn", "còn", "tiếp tục", "từ hôm qua", "mấy hôm nay", "đến nay",
    "đỡ hơn", "giảm rồi", "nặng hơn", "tăng lên", "uống thuốc rồi", "đau lại"
]

RECURRENCE_SIGNALS = [
    "lại bị", "bị lại", "tái phát", "đợt trước", "giống lần trước", "lại đau",
    "cơn đau cũ", "bệnh cũ", "tái lại", "tái đi tái lại"
]

RESOLUTION_SIGNALS = [
    "khỏi rồi", "hết đau", "đã khỏi", "bình phục", "hết sốt", "không còn đau"
]


def evaluate_episode_linking(
    active_episodes: List[HealthEpisode],
    new_complaint: Optional[str],
    body_location: Optional[str],
    user_message: str
) -> Tuple[EpisodeLinkingConfidence, Optional[HealthEpisode], List[str]]:
    """
    Đánh giá xem thông điệp hiện tại thuộc về đợt bệnh đang có, đợt mới hay tái phát.
    Trả về (Confidence, MatchedEpisode, Reasons).
    """
    if not new_complaint or not new_complaint.strip():
        if active_episodes:
            return EpisodeLinkingConfidence.SAME_EPISODE_HIGH, active_episodes[0], ["Không có triệu chứng mới, tiếp tục ngữ cảnh đợt hiện tại"]
        return EpisodeLinkingConfidence.UNCERTAIN, None, ["Chưa xác định được triệu chứng cụ thể"]

    text_lower = user_message.lower()
    c_lower = new_complaint.strip().lower()
    loc_lower = (body_location or "").strip().lower()

    # Kiểm tra dấu hiệu người dùng xác nhận khỏi bệnh
    if any(sig in text_lower for sig in RESOLUTION_SIGNALS):
        for ep in active_episodes:
            if ep.status not in (EpisodeStatus.RESOLVED.value, EpisodeStatus.ESCALATED.value):
                return EpisodeLinkingConfidence.SAME_EPISODE_HIGH, ep, ["Người dùng xác nhận đợt bệnh đã thuyên giảm/khỏi"]

    # Duyệt qua các đợt bệnh gần đây của đúng profile
    for ep in active_episodes:
        ep_c = ep.chief_complaint.lower()
        ep_loc = (ep.body_location or "").lower()

        # Kiểm tra trùng khớp triệu chứng hoặc vị trí
        same_complaint = (c_lower in ep_c or ep_c in c_lower)
        same_loc = bool(loc_lower and ep_loc and (loc_lower in ep_loc or ep_loc in loc_lower))

        # Kiểm tra tín hiệu ngôn ngữ
        has_continuation = any(sig in text_lower for sig in CONTINUATION_SIGNALS)
        has_recurrence = any(sig in text_lower for sig in RECURRENCE_SIGNALS)

        # Tính khoảng thời gian từ lần cập nhật gần nhất
        try:
            last_dt = datetime.fromisoformat(ep.last_updated_at.replace("Z", "+00:00"))
            time_gap_days = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
        except Exception:
            time_gap_days = 0.0

        if ep.status == EpisodeStatus.RESOLVED.value:
            # Đợt trước đã khỏi nhưng người dùng nói "lại bị" -> Đợt tái phát (RECURRENCE)
            if (same_complaint or same_loc) and (has_recurrence or time_gap_days >= 7.0):
                return EpisodeLinkingConfidence.RECURRENCE, ep, [
                    f"Triệu chứng '{new_complaint}' là đợt tái phát của đợt {ep.episode_id} đã kết thúc trước đó."
                ]
        else:
            # Đợt trước chưa đóng (OPEN / MONITORING / WORSENING / IMPROVING)
            if (same_complaint or same_loc):
                if time_gap_days <= 14.0 or has_continuation:
                    return EpisodeLinkingConfidence.SAME_EPISODE_HIGH, ep, [
                        f"Trùng khớp triệu chứng '{new_complaint}' và thời gian tiếp diễn ({time_gap_days:.1f} ngày)."
                    ]
                elif has_recurrence:
                    return EpisodeLinkingConfidence.RECURRENCE, ep, [
                        "Người dùng báo hiệu đợt tái phát mới sau khoảng thời gian gián đoạn."
                    ]
                else:
                    return EpisodeLinkingConfidence.SAME_EPISODE_POSSIBLE, ep, [
                        f"Triệu chứng tương tự đợt {ep.episode_id} nhưng khoảng cách thời gian ({time_gap_days:.1f} ngày)."
                    ]

    return EpisodeLinkingConfidence.NEW_EPISODE_HIGH, None, ["Triệu chứng và vị trí mới hoàn toàn, khởi tạo đợt bệnh mới."]


# ==============================================================================
# 4. TREND DETECTION ENGINE
# ==============================================================================

def calculate_episode_trend(
    events: List[HealthEpisodeEvent],
    current_pain: Optional[int],
    current_fever: Optional[bool],
    current_duration: Optional[str]
) -> Tuple[EpisodeTrend, List[str]]:
    """
    Phân tích diễn tiến (Trend) theo chuỗi sự kiện thời gian thực.
    Trả về (TrendEnum, Reasons).
    """
    reasons: List[str] = []
    if not events:
        return EpisodeTrend.NEW, ["Đợt bệnh mới được ghi nhận lượt đầu tiên."]

    # Trích xuất lịch sử thang điểm đau và triệu chứng
    pain_history = []
    fever_history = []
    for ev in events:
        data = ev.event_data or {}
        if data.get("pain_scale") is not None:
            pain_history.append(int(data["pain_scale"]))
        if "fever" in data:
            fever_history.append(bool(data["fever"]))

    if current_pain is not None:
        if not pain_history or pain_history[-1] != current_pain:
            pain_history.append(current_pain)
    if current_fever is not None:
        if not fever_history or fever_history[-1] != current_fever:
            fever_history.append(current_fever)

    # 1. Phát hiện tình trạng XẤU ĐI (WORSENING)
    is_worsening = False
    if len(pain_history) >= 2:
        if pain_history[-1] >= pain_history[-2] + 2:
            reasons.append(f"Mức độ đau tăng từ {pain_history[-2]}/10 lên {pain_history[-1]}/10")
            is_worsening = True

    if len(fever_history) >= 2:
        if not fever_history[-2] and fever_history[-1]:
            reasons.append("Xuất hiện sốt mới trong khi các lần trước không có")
            is_worsening = True

    if current_duration:
        dur_l = current_duration.lower()
        if any(w in dur_l for w in ["tăng dần", "nặng hơn", "dày hơn", "nhiều hơn"]):
            reasons.append("Người dùng mô tả triệu chứng ngày càng nặng hơn")
            is_worsening = True

    if is_worsening:
        return EpisodeTrend.WORSENING, reasons

    # 2. Phát hiện tình trạng THUYÊN GIẢM (IMPROVING)
    is_improving = False
    if len(pain_history) >= 2:
        if pain_history[-1] <= pain_history[-2] - 2 or (pain_history[-1] <= 3 and max(pain_history[:-1]) >= 5):
            reasons.append(f"Mức độ đau giảm rõ rệt từ {pain_history[-2]}/10 xuống {pain_history[-1]}/10")
            is_improving = True

    if len(fever_history) >= 2:
        if fever_history[-2] and not fever_history[-1]:
            reasons.append("Đã cắt sốt, nhiệt độ trở về bình thường")
            is_improving = True

    if current_duration:
        dur_l = current_duration.lower()
        if any(w in dur_l for w in ["đỡ", "giảm", "bớt", "hết", "khỏi"]):
            reasons.append("Người dùng xác nhận triệu chứng đã thuyên giảm/đỡ hơn")
            is_improving = True

    if is_improving:
        return EpisodeTrend.IMPROVING, reasons

    # 3. ỔN ĐỊNH hoặc KHÔNG ĐỔI (STABLE)
    if len(pain_history) >= 2 and abs(pain_history[-1] - pain_history[-2]) <= 1:
        return EpisodeTrend.STABLE, ["Mức độ đau và các triệu chứng giữ nguyên mức ổn định."]

    if len(events) == 1:
        return EpisodeTrend.NEW, ["Khởi đầu đợt bệnh, đang tiếp tục theo dõi."]

    return EpisodeTrend.INSUFFICIENT_DATA, ["Chưa đủ dữ liệu biến thiên để kết luận xu hướng rõ ràng."]


# ==============================================================================
# 5. REPOSITORY & LIFECYCLE MANAGEMENT
# ==============================================================================

def _row_dict(row, col_names: List[str]) -> Dict[str, Any]:
    """Helper chuyển đổi hàng sqlite3/DatabaseRow an toàn."""
    if not row:
        return {}
    res = {}
    for i, c in enumerate(col_names):
        try:
            res[c] = row[c]
        except (TypeError, KeyError, IndexError):
            try:
                res[c] = row[i]
            except (IndexError, TypeError):
                res[c] = None
    return res


def get_active_or_recent_episodes(
    connection,
    user_id: Optional[int],
    profile_ref: str = "self",
    limit: int = 5
) -> List[HealthEpisode]:
    """Lấy danh sách các đợt bệnh gần đây của đúng một hồ sơ (Profile Isolation)."""
    if not connection or user_id is None:
        return []

    prof_type = "self" if str(profile_ref).lower() in ("self", "", "me") else "family"
    prof_id = "self" if prof_type == "self" else str(profile_ref)

    cols = [
        "episode_id", "user_id", "profile_type", "profile_ref", "chief_complaint",
        "normalized_problem", "body_location", "onset_at", "first_reported_at",
        "last_updated_at", "status", "severity_current", "severity_peak", "pain_scale",
        "fever", "associated_symptoms_json", "red_flags_json", "medications_taken_json",
        "actions_taken_json", "outcome", "topic", "conversation_ids_json",
        "source_message_ids_json", "safety_peak_level", "confidence", "recurrence_of_episode_id"
    ]

    try:
        raw_rows = connection.execute(
            "SELECT episode_id, user_id, profile_type, profile_ref, chief_complaint, "
            "normalized_problem, body_location, onset_at, first_reported_at, "
            "last_updated_at, status, severity_current, severity_peak, pain_scale, "
            "fever, associated_symptoms_json, red_flags_json, medications_taken_json, "
            "actions_taken_json, outcome, topic, conversation_ids_json, "
            "source_message_ids_json, safety_peak_level, confidence, recurrence_of_episode_id "
            "FROM health_episodes "
            "WHERE user_id = ? AND profile_type = ? AND profile_ref = ? "
            "ORDER BY last_updated_at DESC LIMIT ?",
            (user_id, prof_type, prof_id, max(1, min(limit, 20)))
        ).fetchall()

        episodes: List[HealthEpisode] = []
        for raw in raw_rows:
            r = _row_dict(raw, cols)
            ep = HealthEpisode(
                episode_id=r["episode_id"],
                user_id=r["user_id"],
                profile_type=r["profile_type"],
                profile_ref=r["profile_ref"],
                chief_complaint=r["chief_complaint"],
                normalized_problem=r["normalized_problem"],
                body_location=r["body_location"],
                onset_at=str(r["onset_at"] or ""),
                first_reported_at=str(r["first_reported_at"] or ""),
                last_updated_at=str(r["last_updated_at"] or ""),
                status=r["status"] or EpisodeStatus.OPEN.value,
                severity_current=int(r["severity_current"] or 1),
                severity_peak=int(r["severity_peak"] or 1),
                pain_scale=int(r["pain_scale"]) if r["pain_scale"] is not None else None,
                fever=bool(r["fever"]),
                associated_symptoms=json.loads(r["associated_symptoms_json"] or "[]"),
                red_flags=json.loads(r["red_flags_json"] or "[]"),
                medications_taken=json.loads(r["medications_taken_json"] or "[]"),
                actions_taken=json.loads(r["actions_taken_json"] or "[]"),
                outcome=r["outcome"],
                topic=r["topic"],
                conversation_ids=json.loads(r["conversation_ids_json"] or "[]"),
                source_message_ids=json.loads(r["source_message_ids_json"] or "[]"),
                safety_peak_level=r["safety_peak_level"] or "NORMAL",
                confidence=r["confidence"] or "CONFIRMED",
                recurrence_of_episode_id=r["recurrence_of_episode_id"]
            )
            episodes.append(ep)
        return episodes
    except Exception as err:
        logger.warning(f"Lỗi tải active episodes: {err}")
        return []


def save_or_update_health_episode(
    connection,
    episode: HealthEpisode,
    event: Optional[HealthEpisodeEvent] = None
) -> None:
    """Lưu hoặc cập nhật đợt bệnh và ghi nhận sự kiện timeline (Idempotent)."""
    if not connection or not episode:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    episode.last_updated_at = now_iso

    try:
        existing = connection.execute(
            "SELECT id FROM health_episodes WHERE episode_id = ?",
            (episode.episode_id,)
        ).fetchone()

        if existing:
            connection.execute(
                "UPDATE health_episodes SET "
                "chief_complaint = ?, normalized_problem = ?, body_location = ?, "
                "last_updated_at = ?, status = ?, severity_current = ?, severity_peak = ?, "
                "pain_scale = ?, fever = ?, associated_symptoms_json = ?, red_flags_json = ?, "
                "medications_taken_json = ?, actions_taken_json = ?, outcome = ?, "
                "conversation_ids_json = ?, safety_peak_level = ?, confidence = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE episode_id = ?",
                (
                    episode.chief_complaint, episode.normalized_problem, episode.body_location,
                    now_iso, episode.status, episode.severity_current, episode.severity_peak,
                    episode.pain_scale, 1 if episode.fever else 0,
                    json.dumps(episode.associated_symptoms, ensure_ascii=False),
                    json.dumps(episode.red_flags, ensure_ascii=False),
                    json.dumps(episode.medications_taken, ensure_ascii=False),
                    json.dumps(episode.actions_taken, ensure_ascii=False),
                    episode.outcome,
                    json.dumps(episode.conversation_ids, ensure_ascii=False),
                    episode.safety_peak_level, episode.confidence,
                    episode.episode_id
                )
            )
        else:
            connection.execute(
                "INSERT INTO health_episodes ("
                "episode_id, user_id, profile_type, profile_ref, chief_complaint, "
                "normalized_problem, body_location, onset_at, first_reported_at, "
                "last_updated_at, status, severity_current, severity_peak, pain_scale, "
                "fever, associated_symptoms_json, red_flags_json, medications_taken_json, "
                "actions_taken_json, outcome, topic, conversation_ids_json, "
                "source_message_ids_json, safety_peak_level, confidence, "
                "recurrence_of_episode_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    episode.episode_id, episode.user_id, episode.profile_type, episode.profile_ref,
                    episode.chief_complaint, episode.normalized_problem, episode.body_location,
                    episode.onset_at, episode.first_reported_at, now_iso, episode.status,
                    episode.severity_current, episode.severity_peak, episode.pain_scale,
                    1 if episode.fever else 0,
                    json.dumps(episode.associated_symptoms, ensure_ascii=False),
                    json.dumps(episode.red_flags, ensure_ascii=False),
                    json.dumps(episode.medications_taken, ensure_ascii=False),
                    json.dumps(episode.actions_taken, ensure_ascii=False),
                    episode.outcome, episode.topic,
                    json.dumps(episode.conversation_ids, ensure_ascii=False),
                    json.dumps(episode.source_message_ids, ensure_ascii=False),
                    episode.safety_peak_level, episode.confidence,
                    episode.recurrence_of_episode_id
                )
            )

        # Ghi nhận sự kiện Timeline (Idempotency bảo vệ qua client_message_id)
        if event:
            if event.client_message_id:
                dup = connection.execute(
                    "SELECT id FROM health_episode_events "
                    "WHERE episode_id = ? AND client_message_id = ?",
                    (event.episode_id, event.client_message_id)
                ).fetchone()
                if dup:
                    connection.commit()
                    return

            connection.execute(
                "INSERT INTO health_episode_events ("
                "episode_id, event_type, conversation_id, message_id, "
                "client_message_id, event_data_json, occurred_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    event.episode_id, event.event_type, event.conversation_id,
                    event.message_id, event.client_message_id,
                    json.dumps(event.event_data, ensure_ascii=False),
                    event.occurred_at
                )
            )

        connection.commit()
    except Exception as err:
        logger.warning(f"Lỗi save_or_update_health_episode: {err}")


def get_episode_events(
    connection,
    episode_id: str
) -> List[HealthEpisodeEvent]:
    """Tải chuỗi sự kiện theo thứ tự thời gian của một episode."""
    if not connection or not episode_id:
        return []

    cols = ["episode_id", "event_type", "conversation_id", "message_id", "client_message_id", "event_data_json", "occurred_at"]
    try:
        raw_rows = connection.execute(
            "SELECT episode_id, event_type, conversation_id, message_id, client_message_id, "
            "event_data_json, occurred_at "
            "FROM health_episode_events "
            "WHERE episode_id = ? "
            "ORDER BY occurred_at ASC",
            (episode_id,)
        ).fetchall()

        events = []
        for raw in raw_rows:
            r = _row_dict(raw, cols)
            ev = HealthEpisodeEvent(
                episode_id=r["episode_id"],
                event_type=r["event_type"],
                conversation_id=r["conversation_id"],
                message_id=r["message_id"],
                client_message_id=r["client_message_id"],
                event_data=json.loads(r["event_data_json"] or "{}"),
                occurred_at=str(r["occurred_at"] or "")
            )
            events.append(ev)
        return events
    except Exception as err:
        logger.warning(f"Lỗi get_episode_events: {err}")
        return []


# ==============================================================================
# 6. COMPRESSED PROMPT FORMATTER
# ==============================================================================

def format_episode_for_prompt(
    episode: Optional[HealthEpisode],
    trend: Optional[EpisodeTrend] = None,
    trend_reasons: Optional[List[str]] = None,
    linking_decision: Optional[EpisodeLinkingConfidence] = None
) -> str:
    """Định dạng thông tin đợt bệnh và diễn tiến vào system prompt cho LLM."""
    if not episode:
        return ""

    lines = ["=== ĐỢT BỆNH ĐANG THEO DÕI (CURRENT HEALTH EPISODE) ==="]
    lines.append(f"• Mã đợt bệnh: {episode.episode_id} | Vấn đề chính: {episode.chief_complaint}")
    if episode.body_location:
        lines.append(f"• Vị trí triệu chứng: {episode.body_location}")
    if episode.status:
        lines.append(f"• Trạng thái đợt: {episode.status}")
    if episode.pain_scale is not None:
        lines.append(f"• Thang điểm đau: {episode.pain_scale}/10 (Mức cao nhất từng ghi nhận: {episode.severity_peak}/10)")

    if episode.fever:
        lines.append("• Tình trạng sốt: CÓ SỐT")
    if episode.associated_symptoms:
        lines.append(f"• Triệu chứng kèm theo: {', '.join(episode.associated_symptoms)}")

    if trend:
        lines.append(f"• XU HƯỚNG DIỄN TIẾN: {trend.value}")
        if trend_reasons:
            lines.append("  - Dấu hiệu phân tích: " + "; ".join(trend_reasons))

    if linking_decision == EpisodeLinkingConfidence.RECURRENCE:
        lines.append(f"• ĐÂY LÀ ĐỢT TÁI PHÁT (Recurrence) của vấn đề sức khỏe trước đây (Mã đợt gốc: {episode.recurrence_of_episode_id}).")

    lines.append(
        "QUY TẮC LÂM SÀNG:\n"
        "1. Dựa trên diễn tiến này để đánh giá xu hướng thuyên giảm hay xấu đi. KHÔNG tự bịa thêm các triệu chứng chưa có.\n"
        "2. Nếu xu hướng là WORSENING hoặc có triệu chứng nặng mới, phải nhấn mạnh sự thay đổi này và khuyên thăm khám trực tiếp."
    )

    return "\n".join(lines)[:1000]
