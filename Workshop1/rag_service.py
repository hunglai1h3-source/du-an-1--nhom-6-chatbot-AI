"""
Medical RAG & Trusted Knowledge Base Service for MEDICARE AI (Phase 4).

Provides:
- SQLite FTS5 BM25 retrieval from database/medical.db
- Vietnamese accented and unaccented query normalization with accent folding
- Medical concept recognition and synonym expansion
- Relevance score calculation (higher = better) and threshold filtering
- Query construction integrating Phase 2 Medical State (chief_complaint, symptom_location)
- RAG activation policy (disables during EMERGENCY, INTAKE clarifying, chitchat)
- Citation formatting ([MED-XXXXX]) and post-generation Citation Validation
- Robust error handling: never crashes if medical.db is missing, corrupt, or locked.
"""

import logging
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "medical.db"

# Relevance threshold: BM25 relevance score (-raw_bm25) must exceed this to be included
DEFAULT_MIN_RELEVANCE_SCORE = 20.0

# Conversational noise words in Vietnamese
CONVERSATIONAL_STOPWORDS = {
    "là", "của", "và", "có", "được", "trong", "cho", "với", "không", "thì",
    "mà", "ở", "này", "khi", "đã", "sẽ", "đang", "như", "những", "các",
    "đến", "từ", "về", "một", "bị", "bởi", "ra", "vào", "lại", "hay",
    "hoặc", "nếu", "ai", "gì", "nào", "sao", "bao", "nhiêu", "ngày", "mai",
    "hôm", "nay", "tôi", "em", "bác", "sĩ", "dạ", "vâng", "ạ", "xin", "hỏi",
    "thế", "nào", "làm", "sao", "giúp", "với", "cho", "mình", "ơi"
}

# Medical synonyms mapping
SYNONYMS = {
    "bao tử": "dạ dày",
    "nhức đầu": "đau đầu",
    "đầy bụng": "khó tiêu",
    "khó tiêu": "đầy bụng",
    "đái tháo đường": "tiểu đường",
    "tiểu đường": "đái tháo đường",
    "cao huyết áp": "tăng huyết áp",
    "tăng huyết áp": "cao huyết áp",
    "tim đập nhanh": "hồi hộp",
    "nổi mề đay": "dị ứng",
    "mề đay": "dị ứng",
    "mẩn ngứa": "dị ứng",
    "tức ngực": "đau ngực",
    "đau thắt ngực": "đau ngực",
    "nhức khớp": "đau khớp",
    "khớp gối": "đau khớp",
    "tiêm ngừa": "tiêm phòng",
    "chích ngừa": "tiêm phòng",
    "cúm": "cảm cúm",
    "nôn mửa": "buồn nôn",
    "nôn ói": "buồn nôn"
}

# Key medical vocabulary for Vietnamese clinical domain
MEDICAL_VOCABULARY = [
    "dạ dày", "bao tử", "ợ chua", "ợ hơi", "trào ngược", "thực quản",
    "viêm gan", "viêm gan b", "viêm gan c", "men gan", "gan nhiễm mỡ",
    "sốt xuất huyết", "sốt cao", "sốt virus", "phát ban",
    "đau đầu", "nhức đầu", "chóng mặt", "buồn nôn", "nôn ói", "nôn mửa",
    "đau ngực", "tức ngực", "đau thắt ngực", "khó thở", "tim đập nhanh",
    "huyết áp", "tăng huyết áp", "cao huyết áp",
    "tiểu đường", "đái tháo đường", "tiêu chảy", "táo bón", "xuất huyết",
    "dị ứng", "mề đay", "mẩn ngứa", "nhiễm trùng", "viêm họng",
    "viêm amidan", "viêm xoang", "viêm phổi", "viêm phế quản",
    "tiêm phòng", "tiêm ngừa", "tiêm chủng", "vaccine", "vắc xin", "cúm",
    "cảm cúm", "nhiễm khuẩn", "đau bụng", "viêm ruột", "co thắt",
    "đau cơ", "đau khớp", "nhức khớp", "khớp gối",
    "mất ngủ", "suy nhược", "suy thận", "suy tim", "tai biến", "đột quỵ"
]

MED_VOCAB_MAP: Dict[str, str] = {}


def fold_vietnamese(text: str) -> str:
    """Normalize and strip diacritics + fold 'đ' to 'd' for unaccented search."""
    if not text:
        return ""
    text = str(text).lower()
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"\s+", " ", text).strip()


# Pre-compute vocab mapping
for term in MEDICAL_VOCABULARY:
    MED_VOCAB_MAP[term] = term
    MED_VOCAB_MAP[fold_vietnamese(term)] = term


def is_rag_available(db_path: Optional[Path] = None) -> bool:
    """Check if the SQLite medical database exists and has readable tables."""
    target_path = db_path or DATABASE_PATH
    if not target_path.is_file():
        return False
    try:
        con = sqlite3.connect(f"file:{target_path}?mode=ro", uri=True)
        cur = con.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='medical_documents'"
        )
        has_table = (cur.fetchone() or [0])[0] > 0
        con.close()
        return has_table
    except Exception as e:
        logger.warning(f"RAG DB check failed: {e}")
        return False


def get_db_connection(db_path: Optional[Path] = None) -> Optional[sqlite3.Connection]:
    """Open read-only SQLite connection safely."""
    target_path = db_path or DATABASE_PATH
    if not target_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{target_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con
    except Exception as e:
        logger.warning(f"Failed to connect to medical.db: {e}")
        return None


def extract_medical_concepts(
    text: str,
    medical_state: Optional[Dict[str, Any]] = None
) -> Tuple[Set[str], List[str]]:
    """
    Extract canonical medical concepts and non-stopword tokens from query and Phase 2 state.
    """
    clean = re.sub(r"[^0-9a-zA-Zà-ỹÀ-ỸđĐ\s]", " ", text.lower()).strip()
    clean_folded = fold_vietnamese(clean)

    state_terms = []
    if medical_state:
        if medical_state.get("chief_complaint"):
            state_terms.append(str(medical_state["chief_complaint"]).lower())
        if medical_state.get("symptom_location"):
            state_terms.append(str(medical_state["symptom_location"]).lower())

    all_folded = f"{clean_folded} {' '.join(fold_vietnamese(t) for t in state_terms)}"

    matched_concepts = set()
    for k_folded, canonical in sorted(MED_VOCAB_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if k_folded in all_folded:
            matched_concepts.add(canonical)
            if canonical in SYNONYMS:
                matched_concepts.add(SYNONYMS[canonical])

    # Remaining significant tokens
    words = [w for w in clean.split() if w not in CONVERSATIONAL_STOPWORDS and len(w) >= 3]
    return matched_concepts, words


def build_rag_query(
    user_message: str,
    medical_state: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[str], bool]:
    """
    Build FTS5 search query combining user message and Phase 2 Medical State.
    Returns (fts_query_string, has_medical_intent).
    """
    clean = re.sub(r"[^0-9a-zA-Zà-ỹÀ-ỸđĐ\s]", " ", user_message.lower()).strip()
    clean_folded = fold_vietnamese(clean)

    matched_concepts, words = extract_medical_concepts(user_message, medical_state)

    # Check for general question keywords indicating medical intent
    medical_intent_words = {
        "bệnh", "thuốc", "khám", "chữa", "triệu chứng", "nguyên nhân",
        "uống", "tiêm", "vắc", "viêm", "đau", "sốt", "dị ứng", "điều trị",
        "xét nghiệm", "siêu âm", "chẩn đoán", "nguy hiểm", "lây", "phòng ngừa"
    }
    has_medical_words = any(w in clean for w in medical_intent_words)
    has_medical_intent = bool(matched_concepts) or has_medical_words

    if not has_medical_intent and len(words) < 2:
        return None, False

    clauses = []

    # 1. Exact phrase of user message on title and content
    if len(words) >= 2:
        clauses.append(f'title: "{clean}"')
        clauses.append(f'title_folded: "{clean_folded}"')

    # 2. Matched medical concepts (AND combination for high precision)
    if len(matched_concepts) >= 2:
        concept_list = list(matched_concepts)
        and_clause = " AND ".join(f'"{c}"' for c in concept_list[:3])
        clauses.append(f'title: ({and_clause})')
        clauses.append(f'content: ({and_clause})')

    for c in matched_concepts:
        c_folded = fold_vietnamese(c)
        clauses.append(f'title: "{c}"')
        clauses.append(f'title_folded: "{c_folded}"')
        clauses.append(f'content: "{c}"')

    # 3. Add chief complaint from state if available
    if medical_state and medical_state.get("chief_complaint"):
        cc = str(medical_state["chief_complaint"]).strip().lower()
        cc_folded = fold_vietnamese(cc)
        clauses.append(f'title: "{cc}"')
        clauses.append(f'title_folded: "{cc_folded}"')

    # 4. Fallback term OR only if medical intent exists
    if has_medical_intent and words:
        safe_words = [w for w in words[:4] if w not in CONVERSATIONAL_STOPWORDS]
        if safe_words:
            clauses.append("title: (" + " OR ".join(f'"{w}"' for w in safe_words) + ")")

    if not clauses:
        return None, False

    fts_query = " OR ".join(f"({c})" for c in clauses)
    return fts_query, has_medical_intent


def should_activate_rag(
    user_message: str,
    conversation_state: Optional[Dict[str, Any]] = None,
    safety_risk_level: str = "NORMAL"
) -> bool:
    """
    RAG Activation Policy:
    1. EMERGENCY: NEVER call RAG.
    2. INTAKE: RAG = OFF (bot is collecting patient complaint).
    3. EXPLORATION: Only if patient asks a direct factual/medical question.
    4. ASSESSMENT / medical question: RAG = ON.
    """
    # 1. Emergency check (Strict Safety Priority)
    if str(safety_risk_level).upper() == "EMERGENCY":
        return False

    msg_clean = str(user_message or "").strip().lower()
    if not msg_clean:
        return False

    # Short greetings or acknowledgments -> OFF
    greetings = {"chào", "xin chào", "hello", "hi", "cảm ơn", "tạm biệt", "ok", "được", "vâng", "dạ"}
    if msg_clean in greetings:
        return False

    # Check conversation stage if provided
    stage = "INITIAL"
    if conversation_state:
        stage = str(conversation_state.get("stage", "INITIAL")).upper()

    if stage == "INTAKE":
        # Bot is gathering basic info; do not pollute prompt with medical articles
        return False

    if stage == "EXPLORATION":
        # If user is just answering a slot (e.g. "3 ngày", "bên trái", "38.5 độ"), skip RAG
        # Only activate if the user query contains a question
        question_markers = {"không", "gì", "sao", "thế nào", "phải làm", "nguy hiểm", "chữa", "thuốc"}
        is_question = any(marker in msg_clean for marker in question_markers) or "?" in user_message
        if not is_question:
            return False

    # Check if there is medical intent
    _, has_medical_intent = build_rag_query(user_message, conversation_state)
    return has_medical_intent


def search_medical_knowledge(
    user_message: str,
    limit: int = 3,
    min_score: float = DEFAULT_MIN_RELEVANCE_SCORE,
    medical_state: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant medical chunks using SQLite FTS5 BM25.
    Returns list of dicts with chunk_id, title, content, source, source_url, trust_level, relevance_score.
    Never raises an unhandled exception.
    """
    target_limit = max(1, min(int(limit), 5))

    fts_query, has_intent = build_rag_query(user_message, medical_state)
    if not fts_query or not has_intent:
        return []

    con = get_db_connection(db_path)
    if not con:
        return []

    try:
        # SQLite FTS5 bm25 weights: title(5.0), content(2.0), title_folded(3.0), content_folded(1.0)
        # raw_bm25 is negative; lower raw_bm25 means better match.
        # relevance_score = -raw_bm25 (positive, higher is better).
        sql = """
            SELECT 
                f.chunk_id,
                f.title,
                f.content,
                f.source,
                f.source_url,
                bm25(medical_fts, 5.0, 2.0, 3.0, 1.0) AS raw_bm25
            FROM medical_fts f
            WHERE medical_fts MATCH ?
            ORDER BY raw_bm25 ASC
            LIMIT ?
        """
        rows = con.execute(sql, (fts_query, target_limit * 2)).fetchall()

        results = []
        seen_docs = set()

        for row in rows:
            raw_bm25 = row["raw_bm25"]
            relevance_score = -raw_bm25

            if relevance_score < min_score:
                continue

            chunk_id = row["chunk_id"]
            if chunk_id in seen_docs:
                continue
            seen_docs.add(chunk_id)

            results.append({
                "chunk_id": chunk_id,
                "title": row["title"],
                "content": row["content"],
                "source": row["source"],
                "source_url": row["source_url"],
                "trust_level": "CURATED_MEDICAL_CONTENT",
                "relevance_score": round(relevance_score, 2),
            })

            if len(results) >= target_limit:
                break

        return results

    except Exception as e:
        logger.warning(f"RAG search exception: {e}")
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass


def format_rag_context(retrieved_docs: List[Dict[str, Any]]) -> str:
    """
    Format retrieved documents into a grounded context block for Gemini.
    Embeds clear instructions on [MED-XXXXX] citation and no-hallucination rules.
    """
    if not retrieved_docs:
        return (
            "THÔNG BÁO TỪ HỆ THỐNG TRI THỨC:\n"
            "Không tìm thấy tài liệu tham khảo trực tiếp nào đủ độ liên quan trong kho tri thức y tế nội bộ.\n\n"
            "QUY TẮC BẮT BUỘC KHI PHẢN HỒI:\n"
            "1. Trả lời thận trọng dựa trên kiến thức y khoa đại cương phổ quát.\n"
            "2. TUYỆT ĐỐI KHÔNG tự bịa đặt mã trích dẫn [MED-XXXXX].\n"
            "3. KHÔNG tuyên bố 'theo dữ liệu y tế của hệ thống' khi không có tài liệu được cấp.\n"
            "4. Nhắc nhở người dùng tham khảo ý kiến bác sĩ chuyên khoa hoặc đến cơ sở y tế khi có dấu hiệu bất thường."
        )

    sections = [
        "DỮ LIỆU THAM KHẢO TRUY XUẤT TỪ KHO Y TẾ CHỌN LỌC [CURATED_MEDICAL_CONTENT]:\n"
    ]

    for doc in retrieved_docs:
        chunk_id = doc.get("chunk_id", "MED-00000")
        title = doc.get("title", "")
        content = doc.get("content", "")
        source = doc.get("source", "Nguồn Y tế")
        source_url = doc.get("source_url", "")

        url_line = f"Đường dẫn tham khảo: {source_url}\n" if source_url else ""
        sections.append(
            f"[{chunk_id}] Tiêu đề: {title}\n"
            f"Nguồn: {source}\n"
            f"{url_line}"
            f"Nội dung tư vấn: {content}\n"
        )

    sections.append(
        "QUY TẮC BẮT BUỘC KHI SỬ DỤNG TÀI LIỆU:\n"
        "1. Hãy căn cứ vào thông tin y tế trên để trả lời và giải thích cho người dùng.\n"
        "2. Khi đưa ra thông tin hoặc lời khuyên từ tài liệu, BẮT BUỘC gắn mã trích dẫn [MED-XXXXX] ngay sau câu đó.\n"
        "3. TUYỆT ĐỐI CHỈ trích dẫn các mã ID có trong khối tài liệu trên. Không tự bịa bất kỳ mã nào khác.\n"
        "4. Duy trì vai trò trợ lý y tế: không đưa ra chẩn đoán khẳng định tuyệt đối hay kê đơn thuốc đặc trị, luôn khuyên thăm khám bác sĩ khi cần."
    )

    return "\n".join(sections)


def validate_and_extract_citations(
    reply_text: str,
    retrieved_docs: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Inspect model reply for citations [MED-XXXXX].
    - Validates cited IDs against retrieved_docs.
    - Strips any hallucinated IDs (e.g. [MED-99999] that were not retrieved).
    - Returns sanitized reply text and list of actually used sources.
    """
    reply_text = str(reply_text or "")
    if not retrieved_docs:
        # If no docs were retrieved, strip any invented citations
        sanitized = re.sub(r"\[MED-\d+\]", "", reply_text)
        # Clean up double spaces left behind
        sanitized = re.sub(r" {2,}", " ", sanitized)
        return sanitized.strip(), []

    retrieved_map = {doc["chunk_id"]: doc for doc in retrieved_docs}
    cited_ids = set(re.findall(r"\[(MED-\d+)\]", reply_text))

    valid_sources = []
    seen_source_ids = set()

    # Identify valid vs invalid
    invalid_ids = cited_ids - set(retrieved_map.keys())

    # Strip invalid / hallucinated citations from reply text
    sanitized_text = reply_text
    for fake_id in invalid_ids:
        sanitized_text = sanitized_text.replace(f"[{fake_id}]", "")
    sanitized_text = re.sub(r" {2,}", " ", sanitized_text).strip()

    # Collect valid sources
    for cid in cited_ids:
        if cid in retrieved_map and cid not in seen_source_ids:
            seen_source_ids.add(cid)
            valid_sources.append(retrieved_map[cid])

    # If the model didn't explicitly cite the tag, but retrieved docs were provided
    # we return empty cited sources or only cited sources per requirement:
    # "sources chỉ gồm các tài liệu: thực sự retrieved và thực sự được sử dụng / cited nếu có thể xác định. Không trả toàn bộ top-k như thể tất cả đều hỗ trợ câu trả lời."
    return sanitized_text, valid_sources
