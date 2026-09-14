"""
Standalone Knowledge Base Ingestion Script for MEDICARE AI (Phase 4).

Reads curated Vietnamese medical consultations (ViHealthQA) from data/raw/,
cleans and deduplicates records, chunks lengthy answers at sentence boundaries,
and builds an SQLite FTS5 database at database/medical.db with dual exact
and accent-folded text for high-precision clinical retrieval.

Usage:
    python build_medical_knowledge.py [--rebuild]
"""

import csv
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

# Ensure utf-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "medical.db"

# Max answer length before chunking (characters)
CHUNK_THRESHOLD = 1200
CHUNK_TARGET_SIZE = 800
CHUNK_OVERLAP = 150


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


def normalize_text_key(text: str) -> str:
    """Normalized key for deduplication."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def extract_publisher(url: str) -> str:
    """Strictly derive publisher from URL domain, no synthetic doctor/author names."""
    if not url:
        return "Nguồn Y tế Chọn lọc"
    try:
        domain = urlparse(url).netloc.lower()
        if "vinmec" in domain:
            return "Bệnh viện Đa khoa Quốc tế Vinmec"
        elif "vnexpress" in domain:
            return "VnExpress Sức Khỏe"
        elif domain:
            return domain
    except Exception:
        pass
    return "Nguồn Y tế Chọn lọc"


def validate_source_url(url: str) -> str:
    """Return URL only if it has valid http/https scheme and netloc."""
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return url
    except Exception:
        pass
    return ""


def split_answer_into_chunks(answer: str) -> list[str]:
    """
    Split long answer into overlapping chunks at paragraph or sentence boundaries.
    If answer <= CHUNK_THRESHOLD, returns [answer] without modification.
    """
    answer = answer.strip()
    if len(answer) <= CHUNK_THRESHOLD:
        return [answer]

    # Split by paragraphs first
    paragraphs = [p.strip() for p in answer.split("\n") if p.strip()]
    if len(paragraphs) > 1 and all(len(p) <= CHUNK_TARGET_SIZE for p in paragraphs):
        chunks = []
        current = []
        current_len = 0
        for p in paragraphs:
            if current_len + len(p) > CHUNK_TARGET_SIZE and current:
                chunks.append("\n\n".join(current))
                current = [p]
                current_len = len(p)
            else:
                current.append(p)
                current_len += len(p)
        if current:
            chunks.append("\n\n".join(current))
        if chunks:
            return chunks

    # Fallback to sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        s_len = len(sentence)
        if current_len + s_len > CHUNK_TARGET_SIZE and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            # Retain overlap sentences
            overlap_chunk = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) <= CHUNK_OVERLAP:
                    overlap_chunk.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current_chunk = overlap_chunk + [sentence]
            current_len = sum(len(s) for s in current_chunk)
        else:
            current_chunk.append(sentence)
            current_len += s_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks or [answer]


def build_knowledge_base(rebuild: bool = True):
    """Build SQLite FTS5 database from raw datasets."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    print("=== XÂY DỰNG KHO TRI THỨC Y TẾ (PHASE 4) ===")
    print(f"Đích cơ sở dữ liệu: {DATABASE_PATH}")

    # Connect to SQLite
    con = sqlite3.connect(DATABASE_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")

    if rebuild:
        con.execute("DROP TABLE IF EXISTS medical_documents")
        con.execute("DROP TABLE IF EXISTS medical_fts")

    con.execute("""
        CREATE TABLE IF NOT EXISTS medical_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            chunk_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            trust_level TEXT NOT NULL DEFAULT 'CURATED_MEDICAL_CONTENT',
            chunk_index INTEGER NOT NULL DEFAULT 0,
            total_chunks INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS medical_fts USING fts5(
            chunk_id UNINDEXED,
            title,
            content,
            title_folded,
            content_folded,
            source UNINDEXED,
            source_url UNINDEXED,
            tokenize = "unicode61 remove_diacritics 0"
        )
    """)

    # Check existing count to avoid duplicate rebuild if rebuild=False
    existing = con.execute("SELECT COUNT(*) FROM medical_documents").fetchone()[0]
    if existing > 0 and not rebuild:
        print(f"Database đã có {existing} tài liệu. Bỏ qua rebuild vì cờ rebuild=False.")
        con.close()
        return

    # Files to ingest: ViHealthQA splits
    source_files = ["train.csv", "val.csv", "test.csv"]
    seen_pairs = set()
    total_raw_rows = 0
    duplicates_skipped = 0
    doc_counter = 0
    chunk_counter = 0

    doc_batch = []
    fts_batch = []

    for filename in source_files:
        filepath = DATA_RAW_DIR / filename
        if not filepath.exists():
            print(f"[CẢNH BÁO] Không tìm thấy file {filepath}, bỏ qua.")
            continue

        print(f"Đang đọc dữ liệu từ {filename}...")
        with open(filepath, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_raw_rows += 1
                q = str(row.get("question") or "").strip()
                a = str(row.get("answer") or "").strip()
                link = validate_source_url(row.get("link") or "")

                if not q or not a:
                    continue

                # Deduplication key
                q_key = normalize_text_key(q)
                a_key = normalize_text_key(a)
                pair_key = (q_key, a_key)

                if pair_key in seen_pairs:
                    duplicates_skipped += 1
                    continue
                seen_pairs.add(pair_key)

                doc_counter += 1
                doc_id = doc_counter
                source = extract_publisher(link)
                trust_level = "CURATED_MEDICAL_CONTENT"

                chunks = split_answer_into_chunks(a)
                total_chunks = len(chunks)

                for chunk_idx, chunk_text in enumerate(chunks):
                    chunk_counter += 1
                    chunk_id = f"MED-{chunk_counter:05d}"
                    title_folded = fold_vietnamese(q)
                    content_folded = fold_vietnamese(chunk_text)

                    doc_batch.append((
                        doc_id,
                        chunk_id,
                        q,
                        chunk_text,
                        source,
                        link,
                        trust_level,
                        chunk_idx,
                        total_chunks,
                    ))

                    fts_batch.append((
                        chunk_id,
                        q,
                        chunk_text,
                        title_folded,
                        content_folded,
                        source,
                        link,
                    ))

                    if len(doc_batch) >= 1000:
                        con.executemany("""
                            INSERT INTO medical_documents(
                                doc_id, chunk_id, title, content, source,
                                source_url, trust_level, chunk_index, total_chunks
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, doc_batch)
                        con.executemany("""
                            INSERT INTO medical_fts(
                                chunk_id, title, content, title_folded,
                                content_folded, source, source_url
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, fts_batch)
                        con.commit()
                        doc_batch = []
                        fts_batch = []

    if doc_batch:
        con.executemany("""
            INSERT INTO medical_documents(
                doc_id, chunk_id, title, content, source,
                source_url, trust_level, chunk_index, total_chunks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, doc_batch)
        con.executemany("""
            INSERT INTO medical_fts(
                chunk_id, title, content, title_folded,
                content_folded, source, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, fts_batch)
        con.commit()

    # Create index on chunk_id and doc_id
    con.execute("CREATE INDEX IF NOT EXISTS idx_med_chunk_id ON medical_documents(chunk_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_med_doc_id ON medical_documents(doc_id)")
    con.commit()

    db_size_bytes = DATABASE_PATH.stat().st_size
    db_size_mb = db_size_bytes / (1024 * 1024)

    print("\n--- HOÀN TẤT XÂY DỰNG KHO TRI THỨC Y TẾ ---")
    print(f"Tổng số hàng thô đọc được: {total_raw_rows}")
    print(f"Số bản ghi trùng lặp đã loại: {duplicates_skipped}")
    print(f"Số tài liệu y tế (documents): {doc_counter}")
    print(f"Số phân đoạn (chunks): {chunk_counter}")
    print(f"Kích thước file medical.db: {db_size_mb:.2f} MB")
    con.close()


if __name__ == "__main__":
    rebuild_flag = "--rebuild" in sys.argv or "-r" in sys.argv or True
    build_knowledge_base(rebuild=rebuild_flag)
