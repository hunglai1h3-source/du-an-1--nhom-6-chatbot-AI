"""
Long-Term Context Memory module for Phase 3.
Provides balanced context orchestration:
- Structured Medical State (from Phase 2 Conversation State Engine)
- Rolling Structured Summary of older turns
- Recent verbatim messages (last 8-10 turns)
Ensures Gemini never gets overloaded with 30-100 raw messages while preserving full medical continuity.
"""
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ngưỡng kích hoạt cập nhật rolling summary
SUMMARY_TRIGGER_MESSAGE_THRESHOLD = 10
SUMMARY_UPDATE_TURN_INTERVAL = 6
MAX_RECENT_MESSAGES_FOR_PROMPT = 10


def should_update_summary(turn_count: int, total_message_count: int, has_summary: bool = False) -> bool:
    """Xác định khi nào cần cập nhật rolling summary."""
    if total_message_count < SUMMARY_TRIGGER_MESSAGE_THRESHOLD:
        return False
    if not has_summary:
        return True
    return (turn_count > 0) and (turn_count % SUMMARY_UPDATE_TURN_INTERVAL == 0)


def generate_structured_summary(
    messages_to_summarize: List[Dict[str, Any]],
    existing_summary: Optional[str] = None,
) -> str:
    """
    Sinh bản tóm tắt có cấu trúc từ các tin nhắn cũ.
    Phương pháp deterministic bảo đảm an toàn, không tốn token gọi AI riêng,
    hoạt động tin cậy trong môi trường test cũng như production.
    """
    if not messages_to_summarize:
        return existing_summary or ""

    user_symptoms = []
    user_details = []
    assistant_advice = []

    for msg in messages_to_summarize:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            lower = content.lower()
            # Trích xuất các ý chính của người dùng
            if any(k in lower for k in ["đau", "sốt", "mệt", "ho", "khó thở", "chóng mặt", "buồn nôn", "ngứa", "viêm"]):
                # Tóm tắt câu ngắn gọn (tối đa 120 ký tự)
                snippet = content.replace("\n", " ")[:120].strip()
                if snippet and snippet not in user_symptoms:
                    user_symptoms.append(snippet)
            elif any(k in lower for k in ["ngày", "tuần", "tháng", "hôm", "mức", "/10", "độ"]):
                snippet = content.replace("\n", " ")[:100].strip()
                if snippet and snippet not in user_details:
                    user_details.append(snippet)
            else:
                snippet = content.replace("\n", " ")[:90].strip()
                if snippet and snippet not in user_details:
                    user_details.append(snippet)

        elif role == "assistant":
            # Trích xuất dòng chẩn đoán sơ bộ hoặc hướng dẫn quan trọng
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            for line in lines:
                if any(k in line.lower() for k in ["lưu ý", "khuyên", "theo dõi", "uống", "khám", "chế độ", "nguy cơ", "sơ bộ"]):
                    clean_line = re.sub(r"^[*•\-\d\.]+\s*", "", line)[:120].strip()
                    if clean_line and clean_line not in assistant_advice:
                        assistant_advice.append(clean_line)
                        if len(assistant_advice) >= 3:
                            break

    summary_parts = []
    if existing_summary and existing_summary.strip():
        # Giữ lại nền tảng cũ nhưng rút gọn
        prev = existing_summary.strip()
        if len(prev) > 300:
            prev = prev[:300] + "..."
        summary_parts.append(f"- Giai đoạn trước: {prev}")

    if user_symptoms:
        summary_parts.append("- Vấn đề/triệu chứng đã nêu: " + "; ".join(user_symptoms[:4]))
    if user_details:
        summary_parts.append("- Chi tiết bệnh sử/thời gian: " + "; ".join(user_details[:3]))
    if assistant_advice:
        summary_parts.append("- Khuyến nghị/hướng dẫn đã cung cấp: " + "; ".join(assistant_advice[:3]))

    return "\n".join(summary_parts) if summary_parts else (existing_summary or "")


def build_conversation_context(
    state: Optional[Any] = None,
    summary: Optional[str] = None,
    recent_messages: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """
    Xây dựng danh sách tin nhắn ngữ cảnh cân bằng cho Gemini:
    1. System prompt chứa Structured Medical State (Phase 2)
    2. System prompt chứa Conversation Summary (các lượt cũ)
    3. Các tin nhắn gần nhất dạng role: user/assistant (8-10 tin gần nhất)
    """
    context_prompts = []

    # 1. Structured Medical State từ Phase 2
    if state is not None and hasattr(state, "slots"):
        from conversation_engine import format_conversation_state_for_prompt
        state_prompt = format_conversation_state_for_prompt(state)
        if state_prompt:
            context_prompts.append({
                "role": "system",
                "content": state_prompt,
            })

    # 2. Rolling Summary của các lượt cũ
    if summary and summary.strip():
        context_prompts.append({
            "role": "system",
            "content": (
                "TÓM TẮT DIỄN BIẾN TRƯỚC ĐÓ CỦA CUỘC TRÒ CHUYỆN (CÁC LƯỢT TRƯỚC):\n"
                f"{summary.strip()}\n\n"
                "QUY TẮC:\n"
                "- Đã nắm rõ các thông tin trên, không hỏi lại những gì đã được ghi nhận trong tóm tắt.\n"
                "- Duy trì tính liền mạch với các lời khuyên trước đó."
            ),
        })

    # 3. Các tin nhắn gần nhất (Recent verbatim messages)
    if recent_messages:
        # Lấy tối đa MAX_RECENT_MESSAGES_FOR_PROMPT
        selected = recent_messages[-MAX_RECENT_MESSAGES_FOR_PROMPT:]
        for msg in selected:
            role = str(msg.get("role", "user")).lower()
            if role not in ("user", "assistant", "system"):
                role = "user"
            content = str(msg.get("content", ""))
            if content:
                context_prompts.append({
                    "role": role,
                    "content": content,
                })

    return context_prompts
