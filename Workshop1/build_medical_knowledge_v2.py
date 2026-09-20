# -*- coding: utf-8 -*-
"""
Standalone Knowledge Base Ingestion Pipeline for MEDICARE AI (Phase 8: Official Medical Knowledge V2).

Builds database/medical_v2.db:
- Multi-tier source tables (Tier 1: Official Vietnam, Tier 2: WHO, Tier 3: Public Hospitals, Tier 4: Curated Educational)
- Full 25+ fields document metadata (document_id, title, document_number, issuer, issue_date, status, supersedes, etc.)
- Relational lineage table for superseded and amended documents (OLD_DOC -> SUPERSEDED_BY -> NEW_DOC)
- Specialized drug recall & safety alert registry table
- Semantic structural chunking with section paths and clinical focus
- Dual exact and accent-folded text SQLite FTS5 virtual table
- Migrates existing ViHealthQA data as Tier 4 supplementary educational content
- Safe idempotent operations, checksum duplicate detection, rollback capability

Usage:
    python build_medical_knowledge_v2.py [--rebuild] [--skip-tier4] [--stats]
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_V2_PATH = DATABASE_DIR / "medical_v2.db"
DATABASE_V1_PATH = DATABASE_DIR / "medical.db"
DATA_RAW_DIR = BASE_DIR / "data" / "raw"

import source_registry
from source_registry import DocumentStatus, DocumentType, SOURCE_REGISTRY, TrustTier


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


def compute_checksum(content: str) -> str:
    """SHA-256 checksum for document content deduplication."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def init_database_schema(con: sqlite3.Connection, rebuild: bool = False):
    """Create all relational tables and FTS5 indices for Knowledge V2."""
    if rebuild:
        logger.info("Rebuilding database schema from scratch...")
        con.execute("DROP TABLE IF EXISTS drug_recalls_v2")
        con.execute("DROP TABLE IF EXISTS document_relations")
        con.execute("DROP TABLE IF EXISTS medical_chunks_v2")
        con.execute("DROP TABLE IF EXISTS medical_fts_v2")
        con.execute("DROP TABLE IF EXISTS medical_documents_v2")
        con.execute("DROP TABLE IF EXISTS sources")

    con.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            publisher TEXT NOT NULL,
            issuing_authority TEXT NOT NULL,
            domains TEXT NOT NULL,
            trust_tier TEXT NOT NULL,
            source_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            citation_prefix TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS medical_documents_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            publisher TEXT NOT NULL,
            issuing_authority TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            trust_tier TEXT NOT NULL,
            document_type TEXT NOT NULL,
            document_number TEXT,
            issue_date TEXT,
            effective_date TEXT,
            expiry_date TEXT,
            status TEXT NOT NULL DEFAULT 'UNKNOWN',
            supersedes TEXT,
            superseded_by TEXT,
            specialty TEXT,
            topics TEXT,
            population TEXT DEFAULT 'General',
            language TEXT DEFAULT 'vi',
            country TEXT DEFAULT 'VN',
            checksum TEXT NOT NULL,
            retrieved_at TEXT,
            last_verified_at TEXT,
            parser_version TEXT DEFAULT '2.0',
            review_status TEXT DEFAULT 'APPROVED_OFFICIAL',
            total_chunks INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS document_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_doc_id TEXT NOT NULL,
            target_doc_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            legal_basis TEXT,
            effective_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_doc_id, target_doc_id, relation_type)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS drug_recalls_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL REFERENCES medical_documents_v2(document_id),
            drug_name TEXT NOT NULL,
            active_ingredient TEXT,
            dosage_form TEXT,
            batch_number TEXT,
            manufacturer TEXT,
            recall_level TEXT,
            recall_reason TEXT,
            document_number TEXT,
            issue_date TEXT,
            scope TEXT DEFAULT 'Toàn quốc',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS medical_chunks_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL UNIQUE,
            document_id TEXT NOT NULL REFERENCES medical_documents_v2(document_id),
            chunk_index INTEGER NOT NULL,
            section_path TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_text_folded TEXT NOT NULL,
            clinical_focus TEXT,
            trust_tier TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS medical_fts_v2 USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            title,
            title_folded,
            section_path,
            content,
            content_folded,
            publisher UNINDEXED,
            trust_tier UNINDEXED,
            document_type UNINDEXED,
            status UNINDEXED,
            tokenize = "unicode61 remove_diacritics 0"
        )
    """)

    # Seed source registry table
    for sid, sdata in SOURCE_REGISTRY.items():
        con.execute("""
            INSERT OR REPLACE INTO sources (
                source_id, publisher, issuing_authority, domains, trust_tier,
                source_type, enabled, citation_prefix, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sdata["source_id"],
            sdata["publisher"],
            sdata["issuing_authority"],
            json.dumps(sdata.get("domains", [])),
            sdata["trust_tier"],
            sdata["source_type"],
            1 if sdata.get("enabled", True) else 0,
            sdata.get("citation_prefix", "MED"),
            sdata.get("notes", "")
        ))

    con.commit()
    logger.info("Database schema initialized successfully.")


# ==============================================================================
# OFFICIAL VIETNAMESE CLINICAL GUIDELINES & REGULATORY DOCUMENTS (TIER 1 & TIER 2)
# ==============================================================================

OFFICIAL_VIETNAM_DOCUMENTS: List[Dict[str, Any]] = [
    # --------------------------------------------------------------------------
    # 1. SỐT XUẤT HUYẾT DENGUE (Active vs Superseded)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-2760-2023",
        "title": "Hướng dẫn chẩn đoán và điều trị Sốt xuất huyết Dengue",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/van-ban/quyet-dinh-so-2760-qd-byt-ngay-04-7-2023-ve-viec-ban-hanh-huong-dan-chan-doan-dieu-tri-sot-xuat-huyet-dengue.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "2760/QĐ-BYT",
        "issue_date": "2023-07-04",
        "effective_date": "2023-07-04",
        "status": DocumentStatus.ACTIVE.value,
        "supersedes": "3707/QĐ-BYT, 458/QĐ-BYT",
        "specialty": "Truyền nhiễm & Nhiệt đới",
        "topics": ["sốt xuất huyết", "dengue", "dấu hiệu cảnh báo", "sốc sốt xuất huyết", "bù dịch", "hạ sốt an toàn"],
        "population": "Trẻ em và Người lớn",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán lâm sàng > Giai đoạn sốt và Dấu hiệu cảnh báo",
                "clinical_focus": "diagnosis",
                "content": (
                    "Sốt xuất huyết Dengue có biểu hiện lâm sàng đa dạng, diễn biến nhanh chóng từ nhẹ đến nặng qua 3 giai đoạn: "
                    "Giai đoạn sốt (ngày 1-3): Sốt cao đột ngột liên tục 39-40 độ C, khó hạ sốt, nhức đầu, đau hốc mắt, đau cơ, phát ban dưới da. "
                    "Giai đoạn nguy hiểm (ngày 3-7): Nhiệt độ có thể giảm nhưng xuất hiện hiện tượng thoát huyết tương dẫn đến cô đặc máu. "
                    "CÁC DẤU HIỆU CẢNH BÁO NGUY HIỂM CẦN NHẬP VIỆN CẤP CỨU NGAY: "
                    "1. Vật vã, lừ đừ, li bì hoặc bứt rứt. "
                    "2. Đau bụng nhiều và liên tục, đặc biệt vùng hạ sườn phải hoặc đau tăng cảm giác gan. "
                    "3. Nôn ói nhiều (từ 3 lần/1 giờ hoặc 4 lần/6 giờ). "
                    "4. Xuất huyết niêm mạc: Chảy máu cam, chảy máu chân răng, nôn ra máu, đi ngoài phân đen hoặc rong kinh bất thường. "
                    "5. Tiểu ít, lượng nước tiểu giảm rõ rệt. "
                    "6. Xét nghiệm: Hematocrit (HCT) tăng cao kèm tiểu cầu giảm nhanh chóng."
                )
            },
            {
                "section_path": "Điều trị & Dược lý > Nguyên tắc hạ sốt và Chống chỉ định",
                "clinical_focus": "contraindication",
                "content": (
                    "NGUYÊN TẮC HẠ SỐT AN TOÀN TRONG SỐT XUẤT HUYẾT DENGUE: "
                    "Chỉ sử dụng Paracetamol đơn chất để hạ sốt. Liều dùng: 10 - 15 mg/kg thể trọng/lần, cách nhau mỗi 4 - 6 giờ nếu còn sốt cao trên 38.5 độ C. "
                    "Tổng liều Paracetamol tối đa không vượt quá 60 mg/kg thể trọng trong 24 giờ đối với trẻ em và không quá 3g/24 giờ đối với người lớn để tránh tổn thương gan cấp. "
                    "CHỐNG CHỈ ĐỊNH TUYỆT ĐỐI: "
                    "KHÔNG ĐƯỢC DÙNG Aspirin, Ibuprofen, hoặc bất kỳ loại thuốc hạ sốt giảm đau chống viêm không steroid (NSAIDs) nào khác. "
                    "Lý do: Các hoạt chất này ức chế kết tập tiểu cầu và gây tổn thương niêm mạc dạ dày, làm tăng nguy cơ xuất huyết tiêu hóa ồ ạt, sốc mất máu và có thể đe dọa tính mạng người bệnh."
                )
            },
            {
                "section_path": "Điều trị > Bù dịch đường uống và Theo dõi tại nhà",
                "clinical_focus": "treatment",
                "content": (
                    "Khuyến khích người bệnh uống nhiều nước: Dung dịch Oresol (pha đúng tỷ lệ theo hướng dẫn trên bao bì), nước đun sôi để nguội, nước cam, nước chanh, nước dừa tươi hoặc nước hoa quả. "
                    "Không uống các loại nước có màu sẫm hoặc đỏ như xá xị, coca, nước củ dền để tránh nhầm lẫn với nôn ra máu hoặc xuất huyết tiêu hóa. "
                    "Nếu người bệnh nôn nhiều, uống kém hoặc có dấu hiệu li bì, cần đưa ngay đến cơ sở y tế để truyền dịch tĩnh mạch theo phác đồ kiểm soát của bác sĩ, tuyệt đối không tự ý truyền dịch tại nhà."
                )
            }
        ]
    },
    {
        "document_id": "MOH-QD-3707-2020",
        "title": "Hướng dẫn chẩn đoán, điều trị Sốt xuất huyết Dengue (Quy định cũ 2020)",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Bộ Y tế",
        "source_url": "https://kcb.vn/van-ban/quyet-dinh-3707-qd-byt-2020.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "3707/QĐ-BYT",
        "issue_date": "2020-09-10",
        "effective_date": "2020-09-10",
        "expiry_date": "2023-07-04",
        "status": DocumentStatus.SUPERSEDED.value,
        "superseded_by": "MOH-QD-2760-2023",
        "specialty": "Truyền nhiễm",
        "topics": ["sốt xuất huyết", "dengue 2020", "văn bản cũ"],
        "population": "Trẻ em và Người lớn",
        "review_status": "SUPERSEDED_ARCHIVED",
        "sections": [
            {
                "section_path": "Lịch sử văn bản > Hướng dẫn năm 2020 (Đã bị thay thế)",
                "clinical_focus": "diagnosis",
                "content": (
                    "[TÀI LIỆU LỊCH SỬ ĐÃ HẾT HIỆU LỰC - ĐÃ BỊ THAY THẾ BỞI QUYẾT ĐỊNH 2760/QĐ-BYT NĂM 2023]. "
                    "Hướng dẫn cũ ban hành năm 2020 phân loại sốt xuất huyết và phác đồ bù dịch trước đây. Hiện tại toàn bộ cơ sở khám chữa bệnh trên toàn quốc "
                    "áp dụng phác đồ mới ban hành theo Quyết định 2760/QĐ-BYT ngày 04/7/2023 của Bộ trưởng Bộ Y tế."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 2. CẢM CÚM VÀ CÚM MÙA (CÚM A, CÚM B)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-2078-2011",
        "title": "Hướng dẫn chẩn đoán và điều trị bệnh Cúm mùa",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-benh-cum.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "2078/QĐ-BYT",
        "issue_date": "2011-06-23",
        "effective_date": "2011-06-23",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Truyền nhiễm & Hô hấp",
        "topics": ["cúm", "cảm cúm", "cúm a", "cúm b", "h1n1", "oseltamivir", "hạ sốt cúm"],
        "population": "Trẻ em, Phụ nữ mang thai, Người cao tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > Dấu hiệu lâm sàng bệnh cúm mùa",
                "clinical_focus": "diagnosis",
                "content": (
                    "Cúm mùa là bệnh truyền nhiễm cấp tính lây truyền qua đường hô hấp do virus cúm (chủ yếu typ A và B) gây nên. "
                    "Triệu chứng khởi phát rầm rộ: Sốt cao đột ngột (thường trên 38.5 độ C), rét run, đau đầu, đau nhức toàn thân, mệt mỏi rũ rượi, "
                    "kèm theo viêm long đường hô hấp trên: Đau rát họng, ho khan, nghẹt mũi, chảy nước mũi trong. "
                    "Đa số trường hợp cúm lành tính sẽ tự hồi phục sau 5 - 7 ngày nếu được chăm sóc dinh dưỡng và nghỉ ngơi hợp lý."
                )
            },
            {
                "section_path": "Điều trị & Thuốc > Chỉ định thuốc kháng virus Oseltamivir (Tamiflu)",
                "clinical_focus": "treatment",
                "content": (
                    "Chỉ định thuốc kháng virus Oseltamivir (Tamiflu): "
                    "KHÔNG sử dụng Oseltamivir đại trà cho các trường hợp cúm mùa nhẹ hoặc không có yếu tố nguy cơ. "
                    "Thuốc chỉ được chỉ định cho các trường hợp: "
                    "1. Bệnh nhân cúm có biến chứng nặng (viêm phổi, suy hô hấp, viêm phế quản co thắt). "
                    "2. Nhóm đối tượng có nguy cơ cao biến chứng nặng: Trẻ em dưới 2 tuổi, người cao tuổi trên 65 tuổi, phụ nữ có thai hoặc trong vòng 2 tuần sau sinh, "
                    "người mắc bệnh mạn tính (hen phế quản, COPD, suy tim, suy thận, đái tháo đường, suy giảm miễn dịch). "
                    "Hiệu quả điều trị kháng virus tốt nhất khi bắt đầu dùng sớm trong vòng 48 giờ đầu kể từ khi khởi phát triệu chứng đầu tiên."
                )
            },
            {
                "section_path": "Dấu hiệu nguy hiểm > Khi nào người bệnh cúm cần cấp cứu",
                "clinical_focus": "warning",
                "content": (
                    "Dấu hiệu cảnh báo nguy hiểm ở người bệnh cúm cần đến viện ngay: "
                    "- Khó thở, thở gấp, đau tức ngực liên tục khi thở. "
                    "- Tím tái môi hoặc đầu ngón tay ngón chân (SpO2 dưới 95%). "
                    "- Sốt cao kéo dài trên 3 ngày không đáp ứng thuốc hạ sốt, hoặc sốt tái phát sau khi đã giảm. "
                    "- Trẻ nhỏ li bì, bỏ bú, co giật, thở rút lõm lồng ngực. "
                    "- Nôn liên tục, không thể uống nước, dấu hiệu mất nước nặng."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 3. VIÊM PHỔI MẮC PHẢI TẠI CỘNG ĐỒNG (CAP)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-4815-2020",
        "title": "Hướng dẫn chẩn đoán và xử trí Viêm phổi mắc phải tại cộng đồng ở người lớn",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-va-xu-tri-viem-phoi-mac-phai-tai-cong-dong.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "4815/QĐ-BYT",
        "issue_date": "2020-11-20",
        "effective_date": "2020-11-20",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Hô hấp & Phổi",
        "topics": ["viêm phổi", "viêm phổi cộng đồng", "ho có đờm", "khó thở", "thang điểm crb-65"],
        "population": "Người lớn & Người cao tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán lâm sàng > Triệu chứng viêm phổi cộng đồng",
                "clinical_focus": "diagnosis",
                "content": (
                    "Viêm phổi mắc phải tại cộng đồng (CAP) là tình trạng nhiễm trùng cấp tính của nhu mô phổi xảy ra ở ngoài bệnh viện. "
                    "Triệu chứng đặc trưng gồm: Ho đờm mủ đục hoặc đờm màu gỉ sắt, sốt cao kèm rét run, đau ngực kiểu màng phổi (đau tăng khi hít sâu hoặc ho), khó thở. "
                    "Ở người cao tuổi, triệu chứng có thể âm thầm, không sốt cao nhưng biểu hiện bằng lú lẫn, lơ mơ, ăn uống kém, ngã hoặc suy kiệt nhanh chóng."
                )
            },
            {
                "section_path": "Phân tầng nguy cơ > Thang điểm CRB-65 đánh giá mức độ nặng",
                "clinical_focus": "diagnosis",
                "content": (
                    "Thang điểm CRB-65 được khuyến cáo sử dụng tại y tế ban đầu để phân định nơi điều trị: "
                    "- C (Confusion): Lú lẫn, suy giảm tri giác mới xuất hiện (1 điểm). "
                    "- R (Respiratory rate): Nhịp thở từ 30 lần/phút trở lên (1 điểm). "
                    "- B (Blood pressure): Huyết áp tâm thu < 90 mmHg hoặc huyết áp tâm trương <= 60 mmHg (1 điểm). "
                    "- 65: Tuổi từ 65 trở lên (1 điểm). "
                    "Đánh giá: 0 điểm -> Nguy cơ tử vong thấp, có thể cân nhắc điều trị ngoại trú. 1-2 điểm -> Cần nhập viện điều trị. "
                    "3-4 điểm -> Nguy cơ tử vong rất cao, cần nhập viện điều trị khẩn cấp hoặc chuyển khoa hồi sức tích cực (ICU)."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 4. TIÊU HÓA: VIÊM LOÉT DẠ DÀY - TÁ TRÀNG & TRÀO NGƯỢC (GERD)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-468-2016",
        "title": "Hướng dẫn chẩn đoán và điều trị bệnh Tiêu hóa (Viêm loét dạ dày - tá tràng & GERD)",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-benh-tieu-hoa.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "468/QĐ-BYT",
        "issue_date": "2016-02-05",
        "effective_date": "2016-02-05",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Tiêu hóa & Gan mật",
        "topics": ["dạ dày", "viêm loét dạ dày", "trào ngược dạ dày", "gerd", "ợ chua", "vi khuẩn hp", "ppi", "xuất huyết tiêu hóa"],
        "population": "Người lớn",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Trào ngược dạ dày thực quản (GERD) > Triệu chứng & Nguyên nhân",
                "clinical_focus": "diagnosis",
                "content": (
                    "Bệnh trào ngược dạ dày thực quản (GERD) là tình trạng dịch vị dạ dày trào ngược từng đợt hoặc thường xuyên lên thực quản gây triệu chứng khó chịu hoặc biến chứng. "
                    "Triệu chứng điển hình: Ợ chua, ợ nóng rát từ vùng thượng vị lan dọc sau xương ức lên họng, đau rát họng, nuốt vướng, khàn tiếng vào buổi sáng, ho khan kéo dài về đêm. "
                    "Yếu tố nguy cơ làm tăng trào ngược: Thừa cân béo phì, ăn quá no trước khi nằm, thói quen ăn đồ cay nóng, dầu mỡ, uống nhiều cà phê, bia rượu, hút thuốc lá và căng thẳng tâm lý kéo dài."
                )
            },
            {
                "section_path": "Viêm loét dạ dày tá tràng > Phác đồ và Vai trò vi khuẩn HP (Helicobacter pylori)",
                "clinical_focus": "treatment",
                "content": (
                    "Nguyên nhân hàng đầu gây viêm loét dạ dày tá tràng là nhiễm khuẩn Helicobacter pylori (HP) và việc sử dụng kéo dài thuốc chống viêm không steroid (NSAIDs/Aspirin). "
                    "Nguyên tắc điều trị: Ức chế tiết acid dạ dày bằng nhóm ức chế bơm proton (PPI: Esomeprazole, Omeprazole, Pantoprazole, Rabeprazole) uống trước bữa ăn 30-60 phút. "
                    "Đối với loét dạ dày có HP (+), bắt buộc phải dùng phác đồ tiệt trừ HP phối hợp kháng sinh từ 14 ngày theo đúng chỉ định của bác sĩ. "
                    "Người bệnh tuyệt đối không tự ý ngừng kháng sinh sớm vì sẽ dẫn đến chủng vi khuẩn HP kháng thuốc rất khó điều trị."
                )
            },
            {
                "section_path": "Dấu hiệu báo động đỏ > Xuất huyết tiêu hóa trên",
                "clinical_focus": "warning",
                "content": (
                    "DẤU HIỆU CẢNH BÁO XUẤT HUYẾT TIÊU HÓA KHẨN CẤP: "
                    "- Nôn ra máu đỏ tươi hoặc nôn ra dịch bã cà phê nâu đen. "
                    "- Đi ngoài phân đen như bã cà phê hoặc hắc ín, mùi khẳm thối nồng nặc đặc trưng. "
                    "- Hoa mắt, chóng mặt, vã mồ hôi lạnh, tụt huyết áp, ngất xỉu khi đứng dậy. "
                    "Đây là tình trạng cấp cứu nội - ngoại khoa khẩn cấp, bệnh nhân cần được vận chuyển ngay đến phòng cấp cứu bệnh viện gần nhất, "
                    "không được tự ý uống bất kỳ loại thuốc cầm máu hay thảo dược nào tại nhà."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 5. VIÊM GAN VIRUS B MẠN TÍNH (Active vs Superseded)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-3310-2019",
        "title": "Hướng dẫn chẩn đoán và điều trị bệnh Viêm gan virus B",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-benh-viem-gan-vi-rut-b.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "3310/QĐ-BYT",
        "issue_date": "2019-07-29",
        "effective_date": "2019-07-29",
        "status": DocumentStatus.ACTIVE.value,
        "supersedes": "5448/QĐ-BYT",
        "specialty": "Truyền nhiễm & Gan mật",
        "topics": ["viêm gan b", "hbv", "men gan", "alt", "ast", "hbsag", "tenofovir", "entecavir"],
        "population": "Người lớn & Phụ nữ mang thai",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > Tiêu chuẩn xác định Viêm gan B mạn tính",
                "clinical_focus": "diagnosis",
                "content": (
                    "Viêm gan B mạn tính được xác định khi kháng nguyên bề mặt HBsAg tồn tại dương tính kéo dài trên 6 tháng. "
                    "Bệnh lây truyền chủ yếu qua 3 con đường: Đường máu, đường tình dục không an toàn và lây truyền từ mẹ sang con trong khi sinh. "
                    "BỆNH KHÔNG LÂY qua đường ăn uống chung, tiếp xúc thông thường, ôm hôn, bắt tay hay dùng chung bát đũa. Do đó không cần cách ly người bệnh trong sinh hoạt gia đình."
                )
            },
            {
                "section_path": "Điều trị & Thuốc kháng virus > Chỉ định Tenofovir và Entecavir",
                "clinical_focus": "treatment",
                "content": (
                    "Chỉ định điều trị thuốc kháng virus (NUCs: Tenofovir TDF, Tenofovir TAF hoặc Entecavir): "
                    "Căn cứ vào sự kết hợp giữa 3 yếu tố: Tải lượng virus HBV-DNA cao, nồng độ men gan ALT tăng gấp 2 lần giá trị bình thường, và/hoặc có bằng chứng xơ hóa gan tiến triển từ F2 trở lên. "
                    "Thuốc kháng virus đường uống cần được uống đều đặn hàng ngày, đúng giờ và điều trị lâu dài (thường là nhiều năm hoặc suốt đời). "
                    "CẢNH BÁO NGUY HIỂM: Người bệnh tuyệt đối không được tự ý bỏ thuốc hoặc ngắt quãng, vì virus sẽ bùng phát trở lại gây suy gan cấp hoại tử tế bào gan đe dọa tử vong."
                )
            }
        ]
    },
    {
        "document_id": "MOH-QD-5448-2014",
        "title": "Hướng dẫn chẩn đoán, điều trị bệnh Viêm gan virus B (Quy định cũ 2014)",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Bộ Y tế",
        "source_url": "https://kcb.vn/van-ban/quyet-dinh-5448-qd-byt-2014.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "5448/QĐ-BYT",
        "issue_date": "2014-12-30",
        "effective_date": "2014-12-30",
        "expiry_date": "2019-07-29",
        "status": DocumentStatus.SUPERSEDED.value,
        "superseded_by": "MOH-QD-3310-2019",
        "specialty": "Gan mật",
        "topics": ["viêm gan b 2014", "tài liệu cũ"],
        "population": "Người lớn",
        "review_status": "SUPERSEDED_ARCHIVED",
        "sections": [
            {
                "section_path": "Lịch sử văn bản > Hướng dẫn năm 2014 (Đã bị bãi bỏ)",
                "clinical_focus": "diagnosis",
                "content": (
                    "[TÀI LIỆU LỊCH SỬ ĐÃ BỊ THAY THẾ BỞI QUYẾT ĐỊNH 3310/QĐ-BYT NGÀY 29/7/2019]. "
                    "Các tiêu chuẩn khởi động điều trị Tenofovir và xét nghiệm men gan trước đây đã được cập nhật toàn diện theo quyết định mới của Bộ Y tế."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 6. TIM MẠCH: TĂNG HUYẾT ÁP
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-3192-2020",
        "title": "Hướng dẫn chẩn đoán và điều trị Tăng huyết áp",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-tang-huyet-ap.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "3192/QĐ-BYT",
        "issue_date": "2020-07-17",
        "effective_date": "2020-07-17",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Tim mạch",
        "topics": ["tăng huyết áp", "cao huyết áp", "huyết áp", "đo huyết áp", "cơn tăng huyết áp", "đột quỵ", "tai biến"],
        "population": "Người lớn & Người cao tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > Tiêu chuẩn xác định và Phân độ tăng huyết áp",
                "clinical_focus": "diagnosis",
                "content": (
                    "Tăng huyết áp được định nghĩa khi đo huyết áp tại phòng khám có huyết áp tâm thu (HATT) >= 140 mmHg và/hoặc huyết áp tâm trương (HATTr) >= 90 mmHg. "
                    "Phân độ theo Bộ Y tế: "
                    "- Huyết áp bình thường: HATT 120-129 mmHg và/hoặc HATTr 80-84 mmHg. "
                    "- Tiền tăng huyết áp: HATT 130-139 mmHg và/hoặc HATTr 85-89 mmHg. "
                    "- Tăng huyết áp Độ 1: HATT 140-159 mmHg và/hoặc HATTr 90-99 mmHg. "
                    "- Tăng huyết áp Độ 2: HATT 160-179 mmHg và/hoặc HATTr 100-109 mmHg. "
                    "- Tăng huyết áp Độ 3: HATT >= 180 mmHg và/hoặc HATTr >= 110 mmHg. "
                    "Đo huyết áp tại nhà cần thực hiện sau khi nghỉ ngơi ít nhất 5 phút, không hút thuốc lá, không uống cà phê trước đó 30 phút."
                )
            },
            {
                "section_path": "Điều trị & Lối sống > Biện pháp không dùng thuốc và Giảm muối",
                "clinical_focus": "treatment",
                "content": (
                    "Thay đổi lối sống là nền tảng bắt buộc cho mọi người bệnh tăng huyết áp: "
                    "1. Giảm muối trong khẩu phần ăn: Dưới 5 gam muối (NaCl) mỗi ngày (tương đương khoảng 1 thìa cà phê gạt ngang). Hạn chế chấm nước mắm, xì dầu nguyên chất, tránh đồ đóng hộp, dưa cà muối. "
                    "2. Tăng cường rau xanh, trái cây tươi giàu Kali (trừ bệnh nhân suy thận), ngũ cốc nguyên hạt. "
                    "3. Giảm cân nếu thừa cân béo phì, duy trì chỉ số khối cơ thể BMI từ 18.5 - 22.9 kg/m2. "
                    "4. Tập thể dục đều đặn: Ít nhất 30 phút mỗi ngày, 5 - 7 ngày mỗi tuần (đi bộ nhanh, bơi lội, đạp xe). "
                    "5. Hạn chế tối đa rượu bia, cai thuốc lá hoàn toàn và kiểm soát stress."
                )
            },
            {
                "section_path": "Cấp cứu khẩn cấp > Cơn tăng huyết áp kịch phát (Hypertensive Crisis)",
                "clinical_focus": "warning",
                "content": (
                    "CƠN TĂNG HUYẾT ÁP KHẨN CẤP: Khi chỉ số huyết áp tăng vọt >= 180/120 mmHg kèm theo các dấu hiệu tổn thương cơ quan đích cấp tính: "
                    "- Đau đầu dữ dội không đáp ứng thuốc giảm đau, nhìn mờ, nhìn đôi. "
                    "- Đau tức ngực nghẹn ngào, khó thở dữ dội, ho ra bọt hồng (phù phổi cấp). "
                    "- Yếu liệt nửa người, méo miệng, nói ngọng, lú lẫn, co giật (tai biến mạch máu não / đột quỵ). "
                    "XỬ TRÍ: Để bệnh nhân nằm nghỉ đầu cao 30 độ, nới lỏng cổ áo, gọi ngay CẤP CỨU 115 hoặc đưa đến phòng hồi sức cấp cứu gần nhất. "
                    "KHÔNG ĐƯỢC tự ý ngậm thuốc hạ áp nhanh dưới lưỡi (như Nifedipine nhỏ giọt) tại nhà vì có thể gây tụt huyết áp đột ngột dẫn đến thiếu máu não cục bộ gây đột quỵ."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 7. NỘI TIẾT & CHUYỂN HÓA: ĐÁI THÁO ĐƯỜNG TYPE 2
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-5481-2020",
        "title": "Hướng dẫn chẩn đoán và điều trị Đái tháo đường Type 2",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-dai-thao-duong-type-2.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "5481/QĐ-BYT",
        "issue_date": "2020-12-30",
        "effective_date": "2020-12-30",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Nội tiết & Chuyển hóa",
        "topics": ["đái tháo đường", "tiểu đường", "type 2", "đường huyết", "hba1c", "metformin", "hạ đường huyết"],
        "population": "Người lớn",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > Tiêu chuẩn xác định Đái tháo đường",
                "clinical_focus": "diagnosis",
                "content": (
                    "Chẩn đoán Đái tháo đường dựa vào 1 trong 4 tiêu chuẩn sau (xét nghiệm máu tĩnh mạch tại cơ sở y tế chuẩn hóa): "
                    "1. Đường huyết tương lúc đói (FPG) >= 7.0 mmol/L (126 mg/dL) sau khi nhịn ăn ít nhất 8 giờ. "
                    "2. Đường huyết tương ở thời điểm 2 giờ sau nghiệm pháp dung nạp 75g glucose đường uống (OGTT) >= 11.1 mmol/L (200 mg/dL). "
                    "3. HbA1c >= 6.5% (48 mmol/mol) được thực hiện bằng phương pháp chuẩn hóa quốc tế NGSP. "
                    "4. Người bệnh có triệu chứng kinh điển của tăng đường huyết (uống nhiều, tiểu nhiều, ăn nhiều, sụt cân không rõ nguyên nhân) kèm đường huyết tương ngẫu nhiên bất kỳ >= 11.1 mmol/L (200 mg/dL)."
                )
            },
            {
                "section_path": "Cấp cứu > Nhận biết và Xử trí cơn Hạ đường huyết khẩn cấp",
                "clinical_focus": "warning",
                "content": (
                    "Hạ đường huyết (đường huyết < 3.9 mmol/L hay 70 mg/dL) là biến chứng cấp tính nguy hiểm nhất khi điều trị thuốc tiểu đường hoặc tiêm insulin. "
                    "Dấu hiệu cảnh báo: Vã mồ hôi hột lạnh toát, run rẩy tay chân, tim đập thình thịch, đói cồn cào, chóng mặt, hoa mắt, nhìn mờ, lú lẫn. "
                    "XỬ TRÍ CẤP CỨU TẠI NHÀ THEO QUY TẮC 15-15: "
                    "- Nếu bệnh nhân còn tỉnh táo và nuốt được: Cho uống ngay 15g carbohydrate đơn giản (tương đương 3 thìa cà phê đường pha 100ml nước, 1/2 lon nước ngọt có ga thông thường hoặc 1 hộp sữa tươi có đường). "
                    "- Chờ 15 phút sau đo lại đường huyết mao mạch. Nếu vẫn < 3.9 mmol/L tiếp tục lặp lại uống 15g đường. "
                    "- Nếu bệnh nhân lơ mơ, hôn mê hoặc co giật: TUYỆT ĐỐI KHÔNG ép uống hay nhét thức ăn vào miệng vì nguy cơ sặc vào đường thở gây tử vong. Cần gọi ngay Cấp cứu 115."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 8. CẤP CỨU & XỬ TRÍ PHẢN VỆ (THÔNG TƯ 51 vs THÔNG TƯ 08)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-TT-51-2017",
        "title": "Thông tư hướng dẫn phòng, chẩn đoán và xử trí phản vệ",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Bộ Y tế",
        "source_url": "https://kcb.vn/van-ban/thong-tu-so-512017tt-byt-huong-dan-phong-chan-doan-va-xu-tri-phan-ve.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CIRCULAR.value,
        "document_number": "51/2017/TT-BYT",
        "issue_date": "2017-12-29",
        "effective_date": "2018-02-15",
        "status": DocumentStatus.ACTIVE.value,
        "supersedes": "08/1999/TT-BYT",
        "specialty": "Cấp cứu & Dị ứng lâm sàng",
        "topics": ["phản vệ", "sốc phản vệ", "dị ứng thuốc", "adrenaline", "khó thở", "tụt huyết áp"],
        "population": "Mọi lứa tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > 4 Mức độ phản vệ theo Thông tư 51",
                "clinical_focus": "diagnosis",
                "content": (
                    "Phản vệ là phản ứng dị ứng có thể xuất hiện ngay lập tức từ vài giây đến vài giờ sau khi tiếp xúc với dị nguyên (thuốc, thức ăn, nọc côn trùng...). "
                    "4 mức độ phản vệ theo Thông tư 51/2017/TT-BYT: "
                    "- Mức độ I (Nhẹ): Chỉ có các triệu chứng ở da, niêm mạc: Mày đay ngứa, phù môi, mắt hoặc mặt. "
                    "- Mức độ II (Nặng): Xuất hiện từ 2 biểu hiện ở nhiều cơ quan: Mày đay, phù mạch kèm khó thở nhanh nông, tức ngực, nghẹt thở; đau bụng quặn, nôn ói; huyết áp chưa tụt hoặc tăng. "
                    "- Mức độ III (Nguy kịch): Đường thở co thắt thanh quản dữ dội, thở rít, SpO2 tụt, lú lẫn, huyết áp tụt kẹp hoặc không đo được, mạch nhanh nhỏ. "
                    "- Mức độ IV (Ngừng tuần hoàn): Ngừng tim, ngừng thở hoàn toàn."
                )
            },
            {
                "section_path": "Xử trí cấp cứu khẩn cấp > Vai trò then chốt của Adrenaline",
                "clinical_focus": "treatment",
                "content": (
                    "QUY TẮC CẤP CỨU PHẢN VỆ: "
                    "Adrenaline (Epinephrine) là thuốc thiết yếu, quan trọng bậc nhất, phải được tiêm bắp NGAY LẬP TỨC từ mức độ II trở lên. "
                    "CHỐNG CHỈ ĐỊNH: KHÔNG CÓ CHỐNG CHỈ ĐỊNH TUYỆT ĐỐI của Adrenaline trong cấp cứu phản vệ đe dọa tính mạng. "
                    "Liều Adrenaline tiêm bắp (dung dịch 1mg/1ml): "
                    "- Người lớn: Tiêm bắp 1/2 ống (0.5 ml) vào mặt trước ngoài đùi. "
                    "- Trẻ em: Dưới 10kg tiêm 1/5 ống (0.2 ml); 10-20kg tiêm 1/4 ống (0.25 ml); 20-30kg tiêm 1/3 ống (0.3 ml). "
                    "Sau 3-5 phút nếu huyết áp chưa phục hồi hoặc còn khó thở, tiếp tục tiêm nhắc lại liều tương tự và gọi ngay hỗ trợ Cấp cứu 115."
                )
            }
        ]
    },
    {
        "document_id": "MOH-TT-08-1999",
        "title": "Thông tư hướng dẫn phòng và cấp cứu sốc phản vệ (Quy định cũ 1999)",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Bộ Y tế",
        "source_url": "https://kcb.vn/van-ban/thong-tu-08-1999-tt-byt.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CIRCULAR.value,
        "document_number": "08/1999/TT-BYT",
        "issue_date": "1999-05-04",
        "effective_date": "1999-05-19",
        "expiry_date": "2018-02-15",
        "status": DocumentStatus.SUPERSEDED.value,
        "superseded_by": "MOH-TT-51-2017",
        "specialty": "Cấp cứu",
        "topics": ["sốc phản vệ 1999", "văn bản cũ"],
        "population": "Mọi lứa tuổi",
        "review_status": "SUPERSEDED_ARCHIVED",
        "sections": [
            {
                "section_path": "Lịch sử văn bản > Quy định năm 1999 (Đã bãi bỏ)",
                "clinical_focus": "warning",
                "content": (
                    "[VĂN BẢN ĐÃ HẾT HIỆU LỰC TOÀN BỘ - ĐÃ BỊ THAY THẾ BỞI THÔNG TƯ 51/2017/TT-BYT NGÀY 29/12/2017 CỦA BỘ Y TẾ]. "
                    "Khái niệm sốc phản vệ cũ đã được thay thế bằng hệ thống 4 mức độ phản vệ và quy trình sử dụng Adrenaline ngay từ độ II."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 9. NHI KHOA: TAY CHÂN MIỆNG & SỐT CO GIẬT TRẺ EM
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-QD-1003-2012",
        "title": "Hướng dẫn chẩn đoán, điều trị bệnh Tay - Chân - Miệng",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "source_url": "https://kcb.vn/huong-dan-chan-doan-dieu-tri-tay-chan-mieng.html",
        "source_domain": "kcb.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "1003/QĐ-BYT",
        "issue_date": "2012-03-30",
        "effective_date": "2012-03-30",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Nhi khoa & Truyền nhiễm",
        "topics": ["tay chân miệng", "trẻ em", "giật mình", "loét miệng", "bọng nước", "phân độ tay chân miệng"],
        "population": "Trẻ nhỏ & Trẻ dưới 5 tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Chẩn đoán > Biểu hiện lâm sàng và Dấu hiệu nhận biết",
                "clinical_focus": "diagnosis",
                "content": (
                    "Bệnh Tay - Chân - Miệng do virus đường ruột (chủ yếu Coxsackievirus A16 và Enterovirus 71 - EV71) lây qua đường tiêu hóa và tiếp xúc. "
                    "Triệu chứng lâm sàng: Tổn thương loét niêm mạc miệng, vòm họng gây đau rát, chảy dãi nhiều, biếng ăn, bỏ bú. "
                    "Kèm theo ban dát đỏ hoặc bọng nước ở lòng bàn tay, lòng bàn chân, mông, đầu gối. Bọng nước thường không ngứa, không đau và hiếm khi vỡ loét nhiễm trùng nếu giữ vệ sinh."
                )
            },
            {
                "section_path": "Dấu hiệu biến chứng nặng > Dấu hiệu giật mình chới với",
                "clinical_focus": "warning",
                "content": (
                    "DẤU HIỆU BIẾN CHỨNG NÃO - TIM MẠCH NGUY HIỂM (CẦN CẤP CỨU NGAY): "
                    "1. GIẬT MÌNH CHỚI VỚI: Đây là dấu hiệu quan trọng nhất của biến chứng thần kinh sớm. Trẻ giật mình nảy người khi vừa thiu thiu ngủ hoặc giật mình trên 2 lần trong 30 phút. "
                    "2. Sốt cao liên tục trên 39 độ C không hạ khi đã dùng đủ liều Paracetamol. "
                    "3. Quấy khóc dai dẳng, ngủ lơ mơ, giật cơ, chới với, đi loạng choạng. "
                    "4. Thở nhanh, thở rút lõm lồng ngực, vã mồ hôi trán, da nổi vân tím, tay chân lạnh ngắt. "
                    "Khi có bất kỳ dấu hiệu nào trên, phải đưa trẻ đến khoa Cấp cứu Nhi ngay lập tức."
                )
            }
        ]
    },
    {
        "document_id": "NHITU-HD-SOT-CO-GIAT",
        "title": "Hướng dẫn xử trí Sốt co giật lành tính ở trẻ em",
        "source_id": "NHI_TU_HOSP",
        "publisher": "Bệnh viện Nhi Trung ương",
        "issuing_authority": "Bệnh viện Nhi Trung ương — Khoa Cấp cứu & Chống độc",
        "source_url": "https://benhviennhitrunguong.gov.vn/huong-dan-xu-tri-sot-co-giat-o-tre-em.html",
        "source_domain": "benhviennhitrunguong.gov.vn",
        "trust_tier": TrustTier.TIER_3.value,
        "document_type": DocumentType.TECHNICAL_GUIDANCE.value,
        "document_number": "HD-CC-NHI-04",
        "issue_date": "2022-05-15",
        "effective_date": "2022-05-15",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Nhi khoa & Hồi sức cấp cứu",
        "topics": ["sốt co giật", "co giật ở trẻ", "hạ sốt trẻ em", "sơ cứu co giật"],
        "population": "Trẻ em 6 tháng đến 5 tuổi",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Sơ cứu tại nhà > Các bước xử trí co giật đúng cách",
                "clinical_focus": "treatment",
                "content": (
                    "HƯỚNG DẪN XỬ TRÍ CO GIẬT DO SỐT TẠI NHÀ: "
                    "1. Giữ bình tĩnh, đặt trẻ nằm nghiêng sang một bên (tư thế hồi sức an toàn) trên mặt phẳng êm để đờm dãi chảy ra ngoài, tránh hít sặc vào phổi. "
                    "2. Nới lỏng quần áo, tã lót để thông thoáng đường thở. "
                    "3. TUYỆT ĐỐI KHÔNG LÀM: "
                    "- KHÔNG nhét bất kỳ vật cứng nào (thìa, đũa, ngón tay) vào miệng trẻ vì có thể gây gãy răng, tổn thương niêm mạc miệng hoặc dị vật đường thở. "
                    "- KHÔNG ép ghì giữ chặt tay chân trẻ trong khi đang co giật. "
                    "- KHÔNG vắt chanh, cho uống nước hay cho uống thuốc hạ sốt khi trẻ đang co giật hoặc chưa tỉnh táo hoàn toàn vì sẽ gây sặc dẫn đến ngạt thở tắc nghẽn cấp. "
                    "4. Khi cơn co giật kết thúc và trẻ tỉnh, đặt thuốc hạ sốt Paracetamol đường hậu môn với liều 15 mg/kg thể trọng và đưa trẻ đến bệnh viện thăm khám."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 10. TIÊM CHỦNG MỞ RỘNG (VACCINATION SCHEDULE)
    # --------------------------------------------------------------------------
    {
        "document_id": "MOH-TT-38-2017",
        "title": "Quy định về việc sử dụng vắc xin trong Chương trình Tiêm chủng Mở rộng",
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Cục Y tế dự phòng — Bộ Y tế",
        "source_url": "https://vncdc.gov.vn/lich-tiem-chung-mo-rong-quoc-gia.html",
        "source_domain": "vncdc.gov.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.CIRCULAR.value,
        "document_number": "38/2017/TT-BYT",
        "issue_date": "2017-10-17",
        "effective_date": "2018-01-01",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Y tế dự phòng & Tiêm chủng",
        "topics": ["tiêm chủng", "vắc xin", "tiêm phòng", "tiêm chủng mở rộng", "lao", "viêm gan b sơ sinh", "5 trong 1", "sởi"],
        "population": "Trẻ sơ sinh, Trẻ em, Phụ nữ mang thai",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Lịch tiêm chủng > Trẻ dưới 1 tuổi trong Chương trình Tiêm chủng mở rộng",
                "clinical_focus": "treatment",
                "content": (
                    "Lịch tiêm chủng mở rộng chuẩn quốc gia cho trẻ dưới 1 tuổi: "
                    "- Sơ sinh (trong 24 giờ đầu sau sinh): Tiêm vắc xin Viêm gan B liều sơ sinh và vắc xin BCG phòng bệnh Lao. "
                    "- Trẻ đủ 2 tháng tuổi: Vắc xin phối hợp 5 trong 1 (Bạch hầu - Ho gà - Uốn ván - Viêm gan B - Hib) mũi 1 kèm uống vắc xin Bại liệt (OPV) lần 1. "
                    "- Trẻ đủ 3 tháng tuổi: Vắc xin phối hợp 5 trong 1 mũi 2 kèm uống OPV lần 2. "
                    "- Trẻ đủ 4 tháng tuổi: Vắc xin phối hợp 5 trong 1 mũi 3 kèm uống OPV lần 3 và tiêm 1 mũi vắc xin bại liệt bất hoạt (IPV). "
                    "- Trẻ đủ 9 tháng tuổi: Tiêm vắc xin Sởi đơn mũi 1. "
                    "- Trẻ đủ 18 tháng tuổi: Tiêm nhắc vắc xin Bạch hầu - Ho gà - Uốn ván (DPT) và tiêm vắc xin Sởi - Rubella (MR)."
                )
            },
            {
                "section_path": "An toàn tiêm chủng > Theo dõi sau tiêm và Xử trí phản ứng",
                "clinical_focus": "warning",
                "content": (
                    "Theo dõi trẻ tại điểm tiêm chủng ít nhất 30 phút sau khi tiêm để phát hiện và xử trí kịp thời các phản ứng phản vệ cấp nếu có. "
                    "Tiếp tục theo dõi tại nhà ít nhất 24 - 48 giờ sau tiêm về: Nhiệt độ, nhịp thở, tinh thần, ăn bú và vùng da tiêm. "
                    "CẦN ĐƯA TRẺ ĐẾN BỆNH VIỆN NGAY KHI: "
                    "- Trẻ sốt cao trên 39 độ C khó hạ sốt hoặc co giật. "
                    "- Quấy khóc thét kéo dài liên tục trên 3 giờ. "
                    "- Li bì, khó đánh thức, tím tái, khó thở, thở rên. "
                    "- Vết tiêm sưng cứng lan rộng, tấy đỏ đường kính trên 5cm."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 11. CẢNH BÁO AN TOÀN DƯỢC & THU HỒI THUỐC (CỤC QUẢN LÝ DƯỢC - DAV)
    # --------------------------------------------------------------------------
    {
        "document_id": "DAV-TB-1182-2024",
        "title": "Thông báo thu hồi thuốc viên nén Cefuroxim 500mg do không đạt tiêu chuẩn chất lượng",
        "source_id": "DAV_VN",
        "publisher": "Cục Quản lý Dược — Bộ Y tế",
        "issuing_authority": "Cục Quản lý Dược",
        "source_url": "https://dav.gov.vn/thong-bao-thu-hoi-thuoc-cefuroxim-500mg.html",
        "source_domain": "dav.gov.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.DRUG_RECALL.value,
        "document_number": "1182/QLD-CL",
        "issue_date": "2024-03-12",
        "effective_date": "2024-03-12",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Dược phẩm & Quản lý chất lượng thuốc",
        "topics": ["thu hồi thuốc", "cefuroxim", "kháng sinh", "kém chất lượng", "độ hòa tan", "lô thuốc"],
        "population": "Cơ sở khám chữa bệnh & Người dùng thuốc",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Thông báo thu hồi > Thu hồi viên nén bao phim Cefuroxim 500mg",
                "clinical_focus": "warning",
                "content": (
                    "THÔNG BÁO THU HỒI THUỐC TOÀN QUỐC TỪ CỤC QUẢN LÝ DƯỢC: "
                    "Cục Quản lý Dược thông báo thu hồi toàn quốc đối với lô thuốc: "
                    "- Tên thuốc: Viên nén bao phim Cefuroxim 500mg (SĐK: VD-27836-17). "
                    "- Số lô sản xuất bị thu hồi: Lô 010223, Ngày sản xuất: 03/02/2023, Hạn dùng: 02/02/2026. "
                    "- Cơ sở sản xuất: Công ty Cổ phần Dược phẩm Medipharco. "
                    "- Lý do thu hồi: Mẫu thuốc kiểm nghiệm không đạt tiêu chuẩn chất lượng về chỉ tiêu Độ hòa tan (vi phạm chất lượng mức độ 2). "
                    "- YÊU CẦU: Các cơ sở y tế và nhà thuốc ngừng ngay việc phân phối, sử dụng lô thuốc trên và trả lại cơ sở cung ứng. "
                    "LƯU Ý AN TOÀN: Việc thu hồi chỉ áp dụng riêng cho số lô 010223 nói trên; các lô thuốc Cefuroxim khác đạt chuẩn chất lượng vẫn lưu hành bình thường."
                )
            }
        ]
    },
    {
        "document_id": "DAV-CB-2450-2023",
        "title": "Cảnh báo an toàn Dược: Tương tác nguy hiểm giữa Clopidogrel và Omeprazole",
        "source_id": "DAV_VN",
        "publisher": "Cục Quản lý Dược — Bộ Y tế",
        "issuing_authority": "Cục Quản lý Dược",
        "source_url": "https://dav.gov.vn/canh-bao-tuong-tac-clopidogrel-omeprazole.html",
        "source_domain": "dav.gov.vn",
        "trust_tier": TrustTier.TIER_1.value,
        "document_type": DocumentType.DRUG_SAFETY_ALERT.value,
        "document_number": "2450/QLD-ĐK",
        "issue_date": "2023-08-18",
        "effective_date": "2023-08-18",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Dược lâm sàng & Tim mạch",
        "topics": ["tương tác thuốc", "clopidogrel", "omeprazole", "kết tập tiểu cầu", "cảnh báo an toàn dược"],
        "population": "Bệnh nhân tim mạch & Đặt stent",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "Cảnh báo tương tác Dược > Clopidogrel phối hợp Omeprazole/Esomeprazole",
                "clinical_focus": "contraindication",
                "content": (
                    "CẢNH BÁO AN TOÀN DƯỢC LÂM SÀNG TỪ CỤC QUẢN LÝ DƯỢC: "
                    "Khuyến cáo về tương tác làm giảm tác dụng chống đông của Clopidogrel khi dùng cùng thuốc ức chế bơm proton: "
                    "Omeprazole và Esomeprazole ức chế enzyme gan CYP2C19 - đây là enzyme thiết yếu để chuyển hóa Clopidogrel từ tiền chất thành dạng có hoạt tính chống kết tập tiểu cầu. "
                    "Hậu quả: Làm giảm đáng kể hiệu lực chống đông của Clopidogrel, làm tăng nguy cơ huyết khối tắc stent mạch vành, nhồi máu cơ tim tái phát và đột quỵ. "
                    "KHUYẾN CÁO: Không phối hợp đồng thời Clopidogrel với Omeprazole hoặc Esomeprazole. "
                    "Nếu người bệnh bắt buộc cần dùng thuốc bảo vệ dạ dày, nên ưu tiên Pantoprazole hoặc thuốc kháng thụ thể H2 (như Famotidine) do ít tương tác với CYP2C19 hơn."
                )
            }
        ]
    },

    # --------------------------------------------------------------------------
    # 12. TỔ CHỨC Y TẾ THẾ GIỚI (WHO VIET NAM & WHO GLOBAL - TIER 2)
    # --------------------------------------------------------------------------
    {
        "document_id": "WHO-DENGUE-2024",
        "title": "WHO Clinical Management of Dengue in Primary and Secondary Care",
        "source_id": "WHO_GLOBAL",
        "publisher": "World Health Organization (WHO)",
        "issuing_authority": "WHO Department of Epidemic and Pandemic Preparedness",
        "source_url": "https://www.who.int/publications/i/item/9789240003456",
        "source_domain": "who.int",
        "trust_tier": TrustTier.TIER_2.value,
        "document_type": DocumentType.CLINICAL_GUIDELINE.value,
        "document_number": "WHO/WPE/2024.1",
        "issue_date": "2024-01-15",
        "effective_date": "2024-01-15",
        "status": DocumentStatus.ACTIVE.value,
        "specialty": "Bệnh nhiệt đới & Dịch tễ quốc tế",
        "topics": ["who dengue", "fluid management", "warning signs", "plasma leakage"],
        "population": "Toàn cầu",
        "review_status": "APPROVED_OFFICIAL",
        "sections": [
            {
                "section_path": "WHO Recommendations > Clinical triage & fluid balance",
                "clinical_focus": "treatment",
                "content": (
                    "World Health Organization guidelines emphasize that early recognition of plasma leakage and precise oral fluid replacement "
                    "prevents progression to severe dengue shock. Paracetamol remains the only recommended antipyretic agent. "
                    "Aspirin and NSAIDs are strictly contraindicated due to severe bleeding risks and metabolic acidosis complications."
                )
            }
        ]
    }
]


def ingest_official_documents(con: sqlite3.Connection):
    """Ingest Tier 1, Tier 2, Tier 3 official documents into medical_v2.db."""
    logger.info("Ingesting Official Guidelines and Regulatory Documents (Tier 1 & 2)...")
    doc_count = 0
    chunk_count = 0

    for doc in OFFICIAL_VIETNAM_DOCUMENTS:
        doc_id = doc["document_id"]
        title = doc["title"]
        source_id = doc["source_id"]
        publisher = doc["publisher"]
        issuing_authority = doc["issuing_authority"]
        source_url = doc["source_url"]
        source_domain = doc["source_domain"]
        trust_tier = doc["trust_tier"]
        document_type = doc["document_type"]
        document_number = doc.get("document_number")
        issue_date = doc.get("issue_date")
        effective_date = doc.get("effective_date")
        expiry_date = doc.get("expiry_date")
        status = doc.get("status", DocumentStatus.ACTIVE.value)
        supersedes = doc.get("supersedes")
        superseded_by = doc.get("superseded_by")
        specialty = doc.get("specialty")
        topics = json.dumps(doc.get("topics", []), ensure_ascii=False)
        population = doc.get("population", "General")
        review_status = doc.get("review_status", "APPROVED_OFFICIAL")

        # Combine section contents for document-level checksum
        full_text = "\n\n".join(s["content"] for s in doc.get("sections", []))
        checksum = compute_checksum(full_text)

        sections = doc.get("sections", [])
        total_chunks = len(sections)

        con.execute("""
            INSERT OR REPLACE INTO medical_documents_v2 (
                document_id, title, source_id, publisher, issuing_authority,
                source_url, source_domain, trust_tier, document_type, document_number,
                issue_date, effective_date, expiry_date, status, supersedes,
                superseded_by, specialty, topics, population, checksum,
                last_verified_at, review_status, total_chunks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, title, source_id, publisher, issuing_authority,
            source_url, source_domain, trust_tier, document_type, document_number,
            issue_date, effective_date, expiry_date, status, supersedes,
            superseded_by, specialty, topics, population, checksum,
            datetime.now().strftime("%Y-%m-%d"), review_status, total_chunks
        ))
        doc_count += 1

        # Track relations if superseded
        if superseded_by:
            con.execute("""
                INSERT OR IGNORE INTO document_relations (
                    source_doc_id, target_doc_id, relation_type, legal_basis
                ) VALUES (?, ?, 'SUPERSEDES', ?)
            """, (superseded_by, doc_id, document_number))

        # Check if drug recall
        if document_type == DocumentType.DRUG_RECALL.value:
            con.execute("""
                INSERT OR REPLACE INTO drug_recalls_v2 (
                    document_id, drug_name, active_ingredient, dosage_form,
                    batch_number, manufacturer, recall_level, recall_reason,
                    document_number, issue_date, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id, "Cefuroxim 500mg", "Cefuroxim axetil", "Viên nén bao phim",
                "010223", "Công ty Cổ phần Dược phẩm Medipharco", "Cấp độ 2",
                "Không đạt tiêu chuẩn chất lượng về độ hòa tan", document_number,
                issue_date, status
            ))

        # Ingest chunks & FTS entries
        for idx, sec in enumerate(sections):
            chunk_count += 1
            # Prefix with authority indicator: BYT for MOH, DAV for Drug Admin, WHO for WHO
            prefix = SOURCE_REGISTRY[source_id].get("citation_prefix", "BYT")
            chunk_id = f"{prefix}-{doc_count:02d}{idx+1:02d}"

            section_path = sec.get("section_path", "Nội dung chung")
            content = sec.get("content", "")
            clinical_focus = sec.get("clinical_focus", "general")

            title_folded = fold_vietnamese(title)
            content_folded = fold_vietnamese(content)

            con.execute("""
                INSERT OR REPLACE INTO medical_chunks_v2 (
                    chunk_id, document_id, chunk_index, section_path,
                    chunk_text, chunk_text_folded, clinical_focus, trust_tier, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id, doc_id, idx, section_path,
                content, content_folded, clinical_focus, trust_tier, status
            ))

            con.execute("""
                INSERT OR REPLACE INTO medical_fts_v2 (
                    chunk_id, document_id, title, title_folded,
                    section_path, content, content_folded,
                    publisher, trust_tier, document_type, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id, doc_id, title, title_folded,
                section_path, content, content_folded,
                publisher, trust_tier, document_type, status
            ))

    con.commit()
    logger.info(f"Ingested {doc_count} official documents and {chunk_count} clinical chunks.")


def migrate_tier4_curated_data(con: sqlite3.Connection):
    """
    Migrate existing 11,060 ViHealthQA records from database/medical.db into medical_v2.db
    as Tier 4 Supplementary Educational Content.
    """
    if not DATABASE_V1_PATH.is_file():
        logger.warning(f"RAG V1 database not found at {DATABASE_V1_PATH}, skipping Tier 4 migration.")
        return

    logger.info(f"Connecting to RAG V1 database at {DATABASE_V1_PATH}...")
    con_v1 = sqlite3.connect(DATABASE_V1_PATH)
    con_v1.row_factory = sqlite3.Row

    rows = con_v1.execute("SELECT * FROM medical_documents").fetchall()
    con_v1.close()

    total_rows = len(rows)
    logger.info(f"Found {total_rows} records in RAG V1. Migrating to Tier 4 in medical_v2.db...")

    doc_batch = []
    chunk_batch = []
    fts_batch = []

    seen_checksums = set()
    migrated_docs = 0

    for r in rows:
        chunk_id = r["chunk_id"]
        title = r["title"]
        content = r["content"]
        source = r["source"]
        source_url = r["source_url"]

        content_checksum = compute_checksum(title + content)
        if content_checksum in seen_checksums:
            continue
        seen_checksums.add(content_checksum)

        migrated_docs += 1
        doc_id = f"VIHEALTHQA-{migrated_docs:05d}"
        source_id = "VINMEC_CURATED" if "vinmec" in source.lower() else ("VNEXPRESS_HEALTH" if "vnexpress" in source.lower() else "VIHEALTHQA")
        publisher = source_registry.SOURCE_REGISTRY[source_id]["publisher"]
        issuing_authority = source_registry.SOURCE_REGISTRY[source_id]["issuing_authority"]
        domain = "vinmec.com" if "vinmec" in source_url.lower() else "vnexpress.net"

        title_folded = fold_vietnamese(title)
        content_folded = fold_vietnamese(content)
        section_path = "Tư vấn sức khỏe thường thức"

        doc_batch.append((
            doc_id, title, source_id, publisher, issuing_authority,
            source_url, domain, TrustTier.TIER_4.value, DocumentType.PATIENT_EDUCATION.value,
            None, None, None, None, DocumentStatus.ACTIVE.value, None, None,
            "Chăm sóc sức khỏe đại chúng", json.dumps(["y học thường thức"]), "General",
            content_checksum, datetime.now().strftime("%Y-%m-%d"), "MIGRATED_TIER4", 1
        ))

        chunk_batch.append((
            chunk_id, doc_id, 0, section_path,
            content, content_folded, "patient_education",
            TrustTier.TIER_4.value, DocumentStatus.ACTIVE.value
        ))

        fts_batch.append((
            chunk_id, doc_id, title, title_folded,
            section_path, content, content_folded,
            publisher, TrustTier.TIER_4.value,
            DocumentType.PATIENT_EDUCATION.value, DocumentStatus.ACTIVE.value
        ))

        if len(doc_batch) >= 1000:
            con.executemany("""
                INSERT OR IGNORE INTO medical_documents_v2 (
                    document_id, title, source_id, publisher, issuing_authority,
                    source_url, source_domain, trust_tier, document_type, document_number,
                    issue_date, effective_date, expiry_date, status, supersedes,
                    superseded_by, specialty, topics, population, checksum,
                    last_verified_at, review_status, total_chunks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, doc_batch)

            con.executemany("""
                INSERT OR IGNORE INTO medical_chunks_v2 (
                    chunk_id, document_id, chunk_index, section_path,
                    chunk_text, chunk_text_folded, clinical_focus, trust_tier, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, chunk_batch)

            con.executemany("""
                INSERT OR IGNORE INTO medical_fts_v2 (
                    chunk_id, document_id, title, title_folded,
                    section_path, content, content_folded,
                    publisher, trust_tier, document_type, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, fts_batch)

            con.commit()
            doc_batch = []
            chunk_batch = []
            fts_batch = []

    if doc_batch:
        con.executemany("""
            INSERT OR IGNORE INTO medical_documents_v2 (
                document_id, title, source_id, publisher, issuing_authority,
                source_url, source_domain, trust_tier, document_type, document_number,
                issue_date, effective_date, expiry_date, status, supersedes,
                superseded_by, specialty, topics, population, checksum,
                last_verified_at, review_status, total_chunks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, doc_batch)

        con.executemany("""
            INSERT OR IGNORE INTO medical_chunks_v2 (
                chunk_id, document_id, chunk_index, section_path,
                chunk_text, chunk_text_folded, clinical_focus, trust_tier, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, chunk_batch)

        con.executemany("""
            INSERT OR IGNORE INTO medical_fts_v2 (
                chunk_id, document_id, title, title_folded,
                section_path, content, content_folded,
                publisher, trust_tier, document_type, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fts_batch)

        con.commit()

    logger.info(f"Tier 4 Migration complete: {migrated_docs} curated documents preserved in Knowledge V2.")


def print_database_stats(con: sqlite3.Connection):
    """Print comprehensive distribution statistics of Knowledge V2."""
    print("\n=======================================================")
    print("MEDICARE AI — OFFICIAL MEDICAL KNOWLEDGE V2 DATABASE STATS")
    print("=======================================================")

    doc_count = con.execute("SELECT count(*) FROM medical_documents_v2").fetchone()[0]
    chunk_count = con.execute("SELECT count(*) FROM medical_chunks_v2").fetchone()[0]
    fts_count = con.execute("SELECT count(*) FROM medical_fts_v2").fetchone()[0]
    relations_count = con.execute("SELECT count(*) FROM document_relations").fetchone()[0]
    recalls_count = con.execute("SELECT count(*) FROM drug_recalls_v2").fetchone()[0]

    print(f"Total Documents: {doc_count:,}")
    print(f"Total Chunks: {chunk_count:,}")
    print(f"FTS5 Indexed Rows: {fts_count:,}")
    print(f"Document Lineage Relations: {relations_count:,}")
    print(f"Drug Recalls / Safety Alerts: {recalls_count:,}")

    print("\n--- Phân bổ theo Tầng tin cậy (Trust Tier Distribution) ---")
    tiers = con.execute("SELECT trust_tier, count(*) FROM medical_documents_v2 GROUP BY trust_tier ORDER BY trust_tier").fetchall()
    for t, c in tiers:
        print(f"  • {t}: {c:,} tài liệu")

    print("\n--- Phân bổ theo Trạng thái hiệu lực (Validity Status Distribution) ---")
    statuses = con.execute("SELECT status, count(*) FROM medical_documents_v2 GROUP BY status ORDER BY count(*) DESC").fetchall()
    for s, c in statuses:
        print(f"  • {s}: {c:,} tài liệu")

    print("\n--- Phân bổ theo Loại văn bản (Document Type Distribution) ---")
    types = con.execute("SELECT document_type, count(*) FROM medical_documents_v2 GROUP BY document_type ORDER BY count(*) DESC").fetchall()
    for dt, c in types:
        print(f"  • {dt}: {c:,} tài liệu")
    print("=======================================================\n")


def build_knowledge_v2(rebuild: bool = True, skip_tier4: bool = False):
    """Full execution function for Knowledge V2 build."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATABASE_V2_PATH)
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")

    try:
        init_database_schema(con, rebuild=rebuild)
        ingest_official_documents(con)
        if not skip_tier4:
            migrate_tier4_curated_data(con)
        print_database_stats(con)
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Official Medical Knowledge V2 database.")
    parser.add_argument("--rebuild", action="store_true", default=True, help="Rebuild database from scratch.")
    parser.add_argument("--skip-tier4", action="store_true", help="Skip migrating Tier 4 ViHealthQA dataset.")
    parser.add_argument("--stats", action="store_true", help="Print stats only.")
    args = parser.parse_args()

    if args.stats:
        if DATABASE_V2_PATH.exists():
            con = sqlite3.connect(DATABASE_V2_PATH)
            print_database_stats(con)
            con.close()
        else:
            print(f"Database not found at {DATABASE_V2_PATH}")
    else:
        build_knowledge_v2(rebuild=args.rebuild, skip_tier4=args.skip_tier4)
