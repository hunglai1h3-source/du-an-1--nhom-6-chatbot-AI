# -*- coding: utf-8 -*-
"""
MediCare AI - Official Medical Knowledge V2 Retrieval & Ranking Engine (Phase 8).

Implements:
- Read-only connection to database/medical_v2.db
- Medical concept extraction with Vietnamese accent folding & synonyms
- Official-First Composite Ranking:
    final_score = bm25_relevance * tier_multiplier * status_multiplier * type_multiplier
- Strict validity filtering: Excludes REVOKED, EXPIRED, DRAFT; suppresses SUPERSEDED
- Conflict resolution: Higher trust-tier and active validity take precedence
- Authority-aware citation formatting: [BYT-xxxxx], [DAV-xxxxx], [WHO-xxxxx], [MED-xxxxx]
- Citation Validator V2: Strips fabricated citation IDs and maps valid citations
- Dual-tier fallback: Falls back to RAG V1 (medical.db) if V2 is unavailable, then to safe no-source mode
"""

import logging
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import source_registry
from source_registry import (
    DocumentStatus,
    DocumentType,
    STATUS_WEIGHTS,
    TIER_WEIGHTS,
    TYPE_WEIGHTS,
    TrustTier,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_V2_PATH = BASE_DIR / "database" / "medical_v2.db"
DATABASE_V1_PATH = BASE_DIR / "database" / "medical.db"

# Relevance threshold: BM25 relevance score (-raw_bm25) must exceed this
DEFAULT_MIN_RELEVANCE_SCORE = 18.0

CONVERSATIONAL_STOPWORDS = {
    "là", "của", "và", "có", "được", "trong", "cho", "với", "không", "thì",
    "mà", "ở", "này", "khi", "đã", "sẽ", "đang", "như", "những", "các",
    "đến", "từ", "về", "một", "bị", "bởi", "ra", "vào", "lại", "hay",
    "hoặc", "nếu", "ai", "gì", "nào", "sao", "bao", "nhiêu", "ngày", "mai",
    "hôm", "nay", "tôi", "em", "bác", "sĩ", "dạ", "vâng", "ạ", "xin", "hỏi",
    "thế", "nào", "làm", "sao", "giúp", "với", "cho", "mình", "ơi"
}

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
    "tiêm chủng": "vắc xin",
    "cúm": "cảm cúm",
    "nôn mửa": "buồn nôn",
    "nôn ói": "buồn nôn",
    "sốc thuốc": "phản vệ",
    "dị ứng thuốc": "phản vệ",
    "giật mình": "tay chân miệng",
    "co giật": "sốt co giật",
    "viêm gan virus b": "viêm gan b",
    "viêm gan siêu vi b": "viêm gan b",
    "viêm gan virus c": "viêm gan c",
    "viêm gan siêu vi c": "viêm gan c"
}

MEDICAL_VOCABULARY = [
    "sốt xuất huyết", "dengue", "dấu hiệu cảnh báo", "thoát huyết tương", "tiểu cầu",
    "cúm", "cảm cúm", "cúm a", "cúm b", "tamiflu", "oseltamivir",
    "viêm phổi", "viêm phổi cộng đồng", "crb-65", "suy hô hấp",
    "dạ dày", "bao tử", "trào ngược", "gerd", "ợ chua", "ợ nóng", "vi khuẩn hp", "viêm loét", "xuất huyết tiêu hóa",
    "viêm gan", "viêm gan b", "viêm gan c", "viêm gan virus b", "viêm gan siêu vi b", "viêm gan virus c", "viêm gan siêu vi c", "hbv", "hcv", "men gan", "alt", "ast", "tenofovir", "entecavir",
    "huyết áp", "tăng huyết áp", "cao huyết áp", "cơn tăng huyết áp", "đột quỵ", "tai biến",
    "tiểu đường", "đái tháo đường", "đường huyết", "hba1c", "metformin", "hạ đường huyết",
    "phản vệ", "sốc phản vệ", "dị ứng", "dị ứng thuốc", "mề đay", "adrenaline", "khó thở", "phù mạch",
    "tay chân miệng", "giật mình", "loét miệng", "bọng nước", "sốt co giật", "co giật trẻ em",
    "tiêm chủng", "tiêm phòng", "tiêm ngừa", "vắc xin", "vaccine", "lao", "5 trong 1", "sởi",
    "thu hồi thuốc", "cefuroxim", "kém chất lượng", "độ hòa tan", "tương tác thuốc", "clopidogrel", "omeprazole"
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


for term in MEDICAL_VOCABULARY:
    MED_VOCAB_MAP[term] = term
    MED_VOCAB_MAP[fold_vietnamese(term)] = term


def is_knowledge_v2_available(db_path: Optional[Path] = None) -> bool:
    """Check if medical_v2.db exists and has initialized V2 tables."""
    target = db_path or DATABASE_V2_PATH
    if not target.is_file():
        return False
    try:
        con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        cur = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='medical_documents_v2'")
        has_table = (cur.fetchone() or [0])[0] > 0
        con.close()
        return has_table
    except Exception as e:
        logger.warning(f"Knowledge V2 check failed: {e}")
        return False


# Aliases for consistent naming
is_rag_v2_available = is_knowledge_v2_available


def get_v2_db_connection(db_path: Optional[Path] = None) -> Optional[sqlite3.Connection]:
    """Safe read-only SQLite connection to medical_v2.db."""
    target = db_path or DATABASE_V2_PATH
    if not target.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con
    except Exception as e:
        logger.warning(f"Failed to connect to medical_v2.db: {e}")
        return None


# Aliases for consistent naming
get_v2_connection = get_v2_db_connection


def get_official_badge(tier: str) -> str:
    """Return Vietnamese UI badge for authority tier."""
    t = str(tier or "").upper()
    if "TIER_1" in t or "MOH" in t or "DAV" in t:
        return "★ Chính thức Bộ Y tế"
    elif "TIER_2" in t or "WHO" in t:
        return "★ Quốc tế WHO"
    elif "TIER_3" in t or "HOSPITAL" in t:
        return "BV Tuyến cuối"
    else:
        return "Tham khảo"


def extract_medical_concepts_v2(
    text: str,
    medical_state: Optional[Dict[str, Any]] = None
) -> Tuple[Set[str], List[str]]:
    """Extract canonical medical concepts and keywords from user query & state."""
    clean = re.sub(r"[^0-9a-zA-Zà-ỹÀ-ỸđĐ\s]", " ", text.lower()).strip()
    clean_folded = fold_vietnamese(clean)

    state_terms = []
    if medical_state:
        if medical_state.get("chief_complaint"):
            state_terms.append(str(medical_state["chief_complaint"]).lower())
        if medical_state.get("symptom_location"):
            state_terms.append(str(medical_state["symptom_location"]).lower())

    all_folded = f"{clean_folded} {' '.join(fold_vietnamese(t) for t in state_terms)}"
    padded_folded = f" {all_folded} "

    matched = set()
    for k_folded, canonical in sorted(MED_VOCAB_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        # Match as whole word or phrase, avoiding substring collisions (e.g. 'vinfast' matching 'ast')
        pattern = rf"(?:^|[\s,.\-!?;:\(\)\[\]]){re.escape(k_folded)}(?:$|[\s,.\-!?;:\(\)\[\]])"
        if re.search(pattern, padded_folded):
            matched.add(canonical)
            if canonical in SYNONYMS:
                matched.add(SYNONYMS[canonical])

    words = [w for w in clean.split() if w not in CONVERSATIONAL_STOPWORDS and len(w) >= 3]
    return matched, words


def build_v2_fts_query(
    user_message: str,
    medical_state: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[str], bool]:
    """
    Construct high-precision FTS5 MATCH query for medical_fts_v2.
    Returns (fts_query, has_medical_intent).
    """
    clean = re.sub(r"[^0-9a-zA-Zà-ỹÀ-ỸđĐ\s]", " ", user_message.lower()).strip()
    clean_folded = fold_vietnamese(clean)

    matched_concepts, words = extract_medical_concepts_v2(user_message, medical_state)

    medical_intent_words = {
        "bệnh", "thuốc", "khám", "chữa", "triệu chứng", "nguyên nhân",
        "uống", "tiêm", "vắc", "viêm", "đau", "sốt", "dị ứng", "điều trị",
        "xét nghiệm", "chẩn đoán", "nguy hiểm", "lây", "phòng ngừa", "thu hồi",
        "tương tác", "phác đồ", "hướng dẫn", "bộ y tế"
    }
    has_medical_words = any(w in clean for w in medical_intent_words)
    has_medical_intent = bool(matched_concepts) or has_medical_words

    if not has_medical_intent and len(words) < 2:
        return None, False

    clauses = []

    # 1. Exact phrase on title or content
    if len(words) >= 2:
        clauses.append(f'title: "{clean}"')
        clauses.append(f'title_folded: "{clean_folded}"')

    # 2. Multi-concept AND for tight precision
    if len(matched_concepts) >= 2:
        concept_list = list(matched_concepts)
        and_clause = " AND ".join(f'"{c}"' for c in concept_list[:3])
        clauses.append(f'title: ({and_clause})')
        clauses.append(f'content: ({and_clause})')

    # 3. Individual concepts
    for c in matched_concepts:
        c_folded = fold_vietnamese(c)
        clauses.append(f'title: "{c}"')
        clauses.append(f'title_folded: "{c_folded}"')
        clauses.append(f'content: "{c}"')

    # 4. State chief complaint
    if medical_state and medical_state.get("chief_complaint"):
        cc = str(medical_state["chief_complaint"]).strip().lower()
        cc_folded = fold_vietnamese(cc)
        clauses.append(f'title: "{cc}"')
        clauses.append(f'title_folded: "{cc_folded}"')

    # 5. Fallback OR terms
    if has_medical_intent and words:
        safe_words = [w for w in words[:4] if w not in CONVERSATIONAL_STOPWORDS]
        if safe_words:
            clauses.append("title: (" + " OR ".join(f'"{w}"' for w in safe_words) + ")")

    if not clauses:
        return None, False

    fts_query = " OR ".join(f"({c})" for c in clauses)
    return fts_query, has_medical_intent


def search_official_medical_knowledge(
    user_message: str,
    limit: int = 4,
    min_score: float = DEFAULT_MIN_RELEVANCE_SCORE,
    include_superseded: bool = False,
    medical_state: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Official-First Medical Knowledge Search (V2).
    - Excludes REVOKED, EXPIRED, DRAFT; suppresses SUPERSEDED unless requested.
    - Applies composite ranking formula:
        final_score = bm25_relevance * tier_multiplier * status_multiplier * type_multiplier
    - Returns structured list of citations with full official metadata.
    """
    target_limit = max(1, min(int(limit), 6))

    fts_query, has_intent = build_v2_fts_query(user_message, medical_state)
    if not fts_query or not has_intent:
        return []

    con = get_v2_db_connection(db_path)
    if not con:
        if db_path is not None:
            return []
        # Graceful fallback to RAG V1 if V2 connection unavailable
        logger.info("Knowledge V2 not available, falling back to RAG V1...")
        import rag_service
        return rag_service.search_medical_knowledge(user_message, limit=limit, medical_state=medical_state)

    try:
        # FTS5 search with BM25 weights: title(5.0), title_folded(3.0), section_path(3.0), content(2.0), content_folded(1.0)
        sql = """
            SELECT 
                f.chunk_id,
                f.document_id,
                f.title,
                f.section_path,
                f.content,
                f.publisher,
                f.trust_tier,
                f.document_type,
                f.status,
                d.issuing_authority,
                d.document_number,
                d.issue_date,
                d.source_url,
                d.superseded_by,
                bm25(medical_fts_v2, 5.0, 3.0, 3.0, 2.0, 1.0) AS raw_bm25
            FROM medical_fts_v2 f
            JOIN medical_documents_v2 d ON f.document_id = d.document_id
            WHERE medical_fts_v2 MATCH ?
            ORDER BY raw_bm25 ASC
            LIMIT ?
        """
        rows = con.execute(sql, (fts_query, max(60, target_limit * 15))).fetchall()

        candidates = []
        seen_chunks = set()
        seen_doc_ids = set()

        for row in rows:
            chunk_id = row["chunk_id"]
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            status = row["status"]
            # Exclude REVOKED / EXPIRED / DRAFT
            if status in (DocumentStatus.REVOKED.value, DocumentStatus.EXPIRED.value, DocumentStatus.DRAFT.value):
                continue

            # Unless explicitly asked, exclude SUPERSEDED documents
            if status == DocumentStatus.SUPERSEDED.value and not include_superseded:
                continue

            raw_bm25 = row["raw_bm25"]
            bm25_score = -raw_bm25
            if bm25_score < min_score:
                continue

            trust_tier = row["trust_tier"]
            doc_type = row["document_type"]

            # Multi-tier ranking multipliers
            w_tier = TIER_WEIGHTS.get(trust_tier, 0.85)
            w_status = STATUS_WEIGHTS.get(status, 0.70)
            w_type = TYPE_WEIGHTS.get(doc_type, 0.90)

            # Recency tie-breaker
            issue_date = row["issue_date"] or ""
            w_recency = 1.0
            if issue_date and issue_date >= "2020-01-01":
                w_recency = 1.05

            final_score = round(bm25_score * w_tier * w_status * w_type * w_recency, 2)

            candidates.append({
                "chunk_id": chunk_id,
                "document_id": row["document_id"],
                "title": row["title"],
                "section_path": row["section_path"],
                "content": row["content"],
                "publisher": row["publisher"],
                "issuing_authority": row["issuing_authority"],
                "document_number": row["document_number"] or "",
                "issue_date": issue_date,
                "trust_tier": trust_tier,
                "authority_tier": trust_tier,
                "official_badge": get_official_badge(trust_tier),
                "document_type": doc_type,
                "status": status,
                "source_url": row["source_url"] or "",
                "superseded_by": row["superseded_by"] or "",
                "bm25_score": round(bm25_score, 2),
                "final_score": final_score,
                # UI compatibility mapping
                "source": row["publisher"],
                "trust_level": trust_tier,
                "relevance_score": final_score
            })

        # Sort candidates by final_score descending (Official-First Priority)
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # Diverse document selection (max 2 chunks from same document unless necessary)
        results = []
        doc_count_map: Dict[str, int] = {}
        for c in candidates:
            did = c["document_id"]
            if doc_count_map.get(did, 0) >= 2 and len(candidates) > target_limit:
                continue
            doc_count_map[did] = doc_count_map.get(did, 0) + 1
            results.append(c)
            if len(results) >= target_limit:
                break

        return results

    except Exception as e:
        logger.warning(f"Knowledge V2 search exception: {e}")
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass


def format_rag_context_v2(retrieved_docs: List[Dict[str, Any]]) -> str:
    """
    Format Knowledge V2 retrieved documents into grounded system prompt context.
    Separates Official Guidelines (Tier 1 & 2) from Supplementary Knowledge (Tier 4).
    """
    if not retrieved_docs:
        return (
            "THÔNG BÁO TỪ HỆ THỐNG TRI THỨC Y TẾ:\n"
            "Hiện không tìm thấy tài liệu hướng dẫn chuyên môn hoặc bằng chứng y khoa trực tiếp nào trong kho dữ liệu đã xác thực.\n\n"
            "QUY TẮC BẮT BUỘC KHI PHẢN HỒI:\n"
            "1. Nói rõ: 'Hiện tôi chưa tìm thấy tài liệu phù hợp trong kho kiến thức y tế đã xác minh của hệ thống.'\n"
            "2. Trả lời thận trọng dựa trên kiến thức y khoa đại cương phổ quát và không khẳng định tuyệt đối.\n"
            "3. TUYỆT ĐỐI KHÔNG tự bịa đặt mã trích dẫn [BYT-...] hay [MED-...].\n"
            "4. Khuyên người dùng thăm khám tại cơ sở y tế nếu có dấu hiệu kéo dài hoặc bất thường."
        )

    official_docs = [
        d for d in retrieved_docs 
        if any(t in str(d.get("trust_tier") or d.get("authority_tier") or "").upper() for t in ("TIER_1", "TIER_2", "TIER_3", "MOH", "DAV", "WHO", "HOSPITAL"))
    ]
    supplementary_docs = [d for d in retrieved_docs if d not in official_docs]

    sections = []

    if official_docs:
        sections.append("=== NGUỒN TRI THỨC Y KHOA CHÍNH THỨC: BỘ Y TẾ VIỆT NAM & CƠ QUAN Y TẾ ĐƯỢC ỦY QUYỀN ===")
        for d in official_docs:
            cid = d["chunk_id"]
            title = d["title"]
            issuer = d.get("issuing_authority") or d.get("publisher")
            doc_num = f" (Văn bản số: {d['document_number']})" if d.get("document_number") else ""
            date_str = f" [Ban hành: {d['issue_date']}]" if d.get("issue_date") else ""
            section_path = f" — Phần: {d['section_path']}" if d.get("section_path") else ""
            url = f"URL: {d['source_url']}\n" if d.get("source_url") else ""

            sections.append(
                f"[{cid}] Tiêu đề: {title}{doc_num}{date_str}\n"
                f"Cơ quan ban hành: {issuer}{section_path}\n"
                f"{url}"
                f"Nội dung chuyên môn: {d['content']}\n"
            )

    if supplementary_docs:
        sections.append("=== NGUỒN THAM KHẢO BỔ TRỢ: TRI THỨC Y TẾ ĐẠI CHÚNG ĐÃ CHỌN LỌC ===")
        for d in supplementary_docs:
            cid = d["chunk_id"]
            title = d["title"]
            source = d.get("publisher", "Nguồn Y tế")
            url = f"URL: {d['source_url']}\n" if d.get("source_url") else ""

            sections.append(
                f"[{cid}] Tiêu đề: {title}\n"
                f"Nguồn: {source}\n"
                f"{url}"
                f"Nội dung tham khảo: {d['content']}\n"
            )

    sections.append(
        "QUY TẮC CĂN CỨ VÀ TRÍCH DẪN TRI THỨC Y KHOA:\n"
        "1. ƯU TIÊN TUYỆT ĐỐI các hướng dẫn chính thức từ Bộ Y tế Việt Nam [BYT-...] hoặc Cục Quản lý Dược [DAV-...].\n"
        "2. Nếu sử dụng nguồn tham khảo bổ trợ [MED-...], hãy giải thích rõ đó là kiến thức tham khảo chung, không tự nhận là quy chuẩn Bộ Y tế.\n"
        "3. Gắn mã trích dẫn ngay sau câu hoặc lời khuyên được lấy từ tài liệu (Ví dụ: [BYT-0101]).\n"
        "4. TUYỆT ĐỐI CHỈ trích dẫn các mã ID có trong danh sách trên. Không tự bịa bất kỳ mã nào khác.\n"
        "5. Không tự biến mình thành bác sĩ chẩn đoán tự động hay kê đơn thuốc đặc trị; luôn nhắc người dùng thăm khám chuyên khoa."
    )

    return "\n\n".join(sections)


def validate_and_extract_citations_v2(
    reply_text: str,
    retrieved_docs: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Post-generation Citation Validator V2.
    - Scans for all valid authority tags: [BYT-...], [DAV-...], [WHO-...], [MED-...], [CRH-...], [BMB-...], [NHTU-...]
    - Validates cited IDs against provided retrieved_docs.
    - Strips fabricated or hallucinated IDs.
    - Returns sanitized response text and list of actually used sources with full official metadata.
    """
    reply_text = str(reply_text or "")
    if not retrieved_docs:
        sanitized = re.sub(r"\[(BYT|DAV|WHO|MED|KCB|YTDP|BMB|CRH|NHTU)-[A-Za-z0-9]+\]", "", reply_text)
        sanitized = re.sub(r" {2,}", " ", sanitized)
        return sanitized.strip(), []

    retrieved_map = {doc["chunk_id"]: doc for doc in retrieved_docs}
    raw_cited_ids = re.findall(r"\[((?:BYT|DAV|WHO|MED|KCB|YTDP|BMB|CRH|NHTU)-[A-Za-z0-9]+)\]", reply_text)
    cited_ids = set(raw_cited_ids)

    valid_sources = []
    seen_ids = set()

    invalid_ids = cited_ids - set(retrieved_map.keys())

    sanitized_text = reply_text
    for fake_id in invalid_ids:
        sanitized_text = sanitized_text.replace(f"[{fake_id}]", "")
    sanitized_text = re.sub(r" {2,}", " ", sanitized_text).strip()

    for cid in raw_cited_ids:
        if cid in retrieved_map and cid not in seen_ids:
            seen_ids.add(cid)
            valid_sources.append(retrieved_map[cid])

    return sanitized_text, valid_sources
