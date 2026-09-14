"""
Repository layer for Phase 3: Conversation Persistence & Long-Term Context Memory.
Handles PostgreSQL persistence for conversations and messages with strict ownership verification
and idempotency protection.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _format_conversation_row(row) -> Dict[str, Any]:
    if not row:
        return {}
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    return {
        "id": str(row["id"]),
        "user_id": row["user_id"],
        "title": row["title"] or "Cuộc trò chuyện mới",
        "profile_id": row["profile_id"] or "",
        "summary": row["summary"] or "",
        "turn_count": int(row["turn_count"] or 0),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at or ""),
    }


def _format_message_row(row) -> Dict[str, Any]:
    if not row:
        return {}
    created_at = row["created_at"]
    metadata_json = row["metadata_json"]
    metadata = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            metadata = {}

    return {
        "id": row["id"],
        "conversation_id": str(row["conversation_id"]),
        "role": str(row["role"]),
        "content": str(row["content"]),
        "client_message_id": row["client_message_id"],
        "metadata": metadata,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
    }


def get_conversation(connection, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Lấy thông tin cuộc trò chuyện theo conversation_id."""
    if not conversation_id:
        return None
    try:
        row = connection.execute(
            "SELECT id, user_id, title, profile_id, summary, turn_count, created_at, updated_at "
            "FROM conversations WHERE id = ?",
            (str(conversation_id),),
        ).fetchone()
        if row:
            return _format_conversation_row(row)
    except Exception as err:
        logger.error("Lỗi get_conversation(%s): %s", conversation_id, err)
    return None


def verify_conversation_ownership(
    connection, conversation_id: str, user_id: Optional[int]
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Xác minh quyền sở hữu cuộc trò chuyện:
    - Nếu không tồn tại: trả về (False, None)
    - Nếu là của guest (user_id IS NULL): trả về (True, conv)
    - Nếu user_id khớp với người sở hữu: trả về (True, conv)
    - Nếu user_id không khớp: trả về (False, conv) -> 403 Forbidden
    """
    conv = get_conversation(connection, conversation_id)
    if not conv:
        return False, None

    owner_id = conv.get("user_id")
    if owner_id is None:
        # Cuộc trò chuyện của khách / anonymous
        return True, conv

    if user_id is not None and int(owner_id) == int(user_id):
        return True, conv

    return False, conv


def create_conversation(
    connection,
    conversation_id: str,
    user_id: Optional[int] = None,
    title: str = "Cuộc trò chuyện mới",
    profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo mới hoặc cập nhật thông tin cuộc trò chuyện."""
    cid = str(conversation_id).strip()
    safe_title = (str(title).strip() or "Cuộc trò chuyện mới")[:200]
    safe_profile = str(profile_id or "").strip()[:100]

    existing = get_conversation(connection, cid)
    if existing:
        if user_id and not existing.get("user_id"):
            connection.execute(
                "UPDATE conversations SET user_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id, cid),
            )
            existing["user_id"] = user_id
        return existing

    connection.execute(
        "INSERT INTO conversations (id, user_id, title, profile_id, summary, turn_count) "
        "VALUES (?, ?, ?, ?, NULL, 0)",
        (cid, user_id, safe_title, safe_profile),
    )
    return {
        "id": cid,
        "user_id": user_id,
        "title": safe_title,
        "profile_id": safe_profile,
        "summary": "",
        "turn_count": 0,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


def list_conversations(
    connection, user_id: Optional[int], limit: int = 50
) -> List[Dict[str, Any]]:
    """Lấy danh sách các cuộc trò chuyện của user theo thứ tự mới nhất."""
    if not user_id:
        return []
    try:
        rows = connection.execute(
            "SELECT c.id, c.user_id, c.title, c.profile_id, c.summary, c.turn_count, c.created_at, c.updated_at, "
            "(SELECT m.content FROM conversation_messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) as last_message "
            "FROM conversations c "
            "WHERE c.user_id = ? "
            "ORDER BY c.updated_at DESC "
            "LIMIT ?",
            (user_id, max(1, min(limit, 100))),
        ).fetchall()

        conversations = []
        for r in rows:
            conv = _format_conversation_row(r)
            conv["last_message"] = r["last_message"] or ""
            conversations.append(conv)
        return conversations
    except Exception as err:
        logger.error("Lỗi list_conversations(user_id=%s): %s", user_id, err)
        return []


def update_conversation_title(connection, conversation_id: str, title: str) -> bool:
    """Cập nhật tiêu đề cuộc trò chuyện."""
    if not conversation_id or not title:
        return False
    try:
        clean_title = str(title).strip()[:200]
        connection.execute(
            "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (clean_title, str(conversation_id)),
        )
        return True
    except Exception as err:
        logger.error("Lỗi update_conversation_title(%s): %s", conversation_id, err)
        return False


def update_conversation_summary(connection, conversation_id: str, summary: str) -> bool:
    """Cập nhật bản tóm tắt rolling summary của cuộc trò chuyện."""
    if not conversation_id:
        return False
    try:
        connection.execute(
            "UPDATE conversations SET summary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (summary, str(conversation_id)),
        )
        return True
    except Exception as err:
        logger.error("Lỗi update_conversation_summary(%s): %s", conversation_id, err)
        return False


def get_conversation_summary(connection, conversation_id: str) -> Optional[str]:
    """Lấy nội dung tóm tắt cũ của cuộc trò chuyện."""
    conv = get_conversation(connection, conversation_id)
    return conv.get("summary") if conv else None


def update_conversation_activity(
    connection,
    conversation_id: str,
    title: Optional[str] = None,
    turn_increment: int = 1,
) -> bool:
    """Tăng turn_count và cập nhật thời gian hoạt động mới nhất."""
    if not conversation_id:
        return False
    try:
        if title:
            clean_title = str(title).strip()[:200]
            connection.execute(
                "UPDATE conversations SET turn_count = turn_count + ?, title = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (turn_increment, clean_title, str(conversation_id)),
            )
        else:
            connection.execute(
                "UPDATE conversations SET turn_count = turn_count + ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (turn_increment, str(conversation_id)),
            )
        return True
    except Exception as err:
        logger.error("Lỗi update_conversation_activity(%s): %s", conversation_id, err)
        return False


def delete_conversation(
    connection, conversation_id: str, user_id: Optional[int] = None
) -> bool:
    """Xóa cuộc trò chuyện và toàn bộ tin nhắn, trạng thái kèm theo."""
    if not conversation_id:
        return False
    try:
        if user_id:
            row = connection.execute(
                "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
                (str(conversation_id), user_id),
            ).fetchone()
            if not row:
                return False

        connection.execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        connection.execute(
            "DELETE FROM conversation_states WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (str(conversation_id),),
        )
        return True
    except Exception as err:
        logger.error("Lỗi delete_conversation(%s): %s", conversation_id, err)
        return False


def clear_conversation_messages(
    connection, conversation_id: str, user_id: Optional[int] = None
) -> bool:
    """Xóa toàn bộ tin nhắn và reset state nhưng giữ lại bản ghi conversation."""
    if not conversation_id:
        return False
    try:
        if user_id:
            row = connection.execute(
                "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
                (str(conversation_id), user_id),
            ).fetchone()
            if not row:
                return False

        connection.execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        connection.execute(
            "DELETE FROM conversation_states WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        connection.execute(
            "UPDATE conversations SET summary = NULL, turn_count = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(conversation_id),),
        )
        return True
    except Exception as err:
        logger.error("Lỗi clear_conversation_messages(%s): %s", conversation_id, err)
        return False


def save_message(
    connection,
    conversation_id: str,
    role: str,
    content: str,
    client_message_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Lưu tin nhắn vào PostgreSQL với cơ chế chống trùng lặp (idempotency via client_message_id).
    """
    cid = str(conversation_id).strip()
    safe_role = str(role).strip().lower()
    safe_content = str(content or "")
    safe_client_mid = str(client_message_id).strip()[:120] if client_message_id else None
    meta_json = json.dumps(metadata or {}, ensure_ascii=False) if metadata else None

    # Idempotency check
    if safe_client_mid:
        existing = connection.execute(
            "SELECT id, conversation_id, role, content, client_message_id, metadata_json, created_at "
            "FROM conversation_messages WHERE conversation_id = ? AND client_message_id = ?",
            (cid, safe_client_mid),
        ).fetchone()
        if existing:
            return _format_message_row(existing)

    cursor = connection.execute(
        "INSERT INTO conversation_messages (conversation_id, role, content, client_message_id, metadata_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (cid, safe_role, safe_content, safe_client_mid, meta_json),
    )

    msg_id = getattr(cursor, "lastrowid", None)
    return {
        "id": msg_id,
        "conversation_id": cid,
        "role": safe_role,
        "content": safe_content,
        "client_message_id": safe_client_mid,
        "metadata": metadata or {},
        "created_at": datetime.utcnow().isoformat(),
    }


def get_conversation_messages(
    connection, conversation_id: str, limit: int = 100, before_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Lấy danh sách tin nhắn của cuộc trò chuyện theo thứ tự thời gian tăng dần."""
    if not conversation_id:
        return []
    try:
        if before_id:
            rows = connection.execute(
                "SELECT id, conversation_id, role, content, client_message_id, metadata_json, created_at "
                "FROM conversation_messages "
                "WHERE conversation_id = ? AND id < ? "
                "ORDER BY id DESC "
                "LIMIT ?",
                (str(conversation_id), int(before_id), max(1, min(limit, 200))),
            ).fetchall()
            rows.reverse()
        else:
            rows = connection.execute(
                "SELECT id, conversation_id, role, content, client_message_id, metadata_json, created_at "
                "FROM conversation_messages "
                "WHERE conversation_id = ? "
                "ORDER BY id ASC "
                "LIMIT ?",
                (str(conversation_id), max(1, min(limit, 200))),
            ).fetchall()

        return [_format_message_row(r) for r in rows]
    except Exception as err:
        logger.error("Lỗi get_conversation_messages(%s): %s", conversation_id, err)
        return []


def get_recent_messages(
    connection, conversation_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """Lấy N tin nhắn gần nhất theo thứ tự thời gian để đưa vào ngữ cảnh Gemini."""
    if not conversation_id:
        return []
    try:
        rows = connection.execute(
            "SELECT id, conversation_id, role, content, client_message_id, metadata_json, created_at "
            "FROM conversation_messages "
            "WHERE conversation_id = ? "
            "ORDER BY id DESC "
            "LIMIT ?",
            (str(conversation_id), max(1, min(limit, 30))),
        ).fetchall()

        rows.reverse()
        return [_format_message_row(r) for r in rows]
    except Exception as err:
        logger.error("Lỗi get_recent_messages(%s): %s", conversation_id, err)
        return []
