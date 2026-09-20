# -*- coding: utf-8 -*-
"""
MediCare AI - Source Registry & Trust Model (Phase 8: Official Medical Knowledge V2).

Defines:
- 4-Tier Source Trust Hierarchy (Official Vietnam, International Official, Clinical Institutions, Curated Educational)
- Document Validity Statuses (ACTIVE, SUPERSEDED, REVOKED, EXPIRED, DRAFT, UNKNOWN)
- Document Types (CLINICAL_GUIDELINE, MINISTRY_DECISION, CIRCULAR, DRUG_SAFETY_ALERT, DRUG_RECALL, etc.)
- Domain Allowlists & Strict Security Controls (Prevents SEO spam, unverified blogs, forum crawls)
- Scoring Weights for Official-First Ranking Policy
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class TrustTier(str, Enum):
    TIER_1 = "TIER_1"  # Cơ quan quản lý Y tế Việt Nam chính thức (Bộ Y tế, Cục QLKCB, Cục QL Dược, Cục YTDP)
    TIER_2 = "TIER_2"  # Tổ chức y tế quốc tế chính thống (WHO, WHO Viet Nam)
    TIER_3 = "TIER_3"  # Bệnh viện công lập tuyến cuối, Viện nghiên cứu, Trường Y khoa đầu ngành
    TIER_4 = "TIER_4"  # Tri thức y khoa đại chúng đã chọn lọc (ViHealthQA, Vinmec, VnExpress Sức Khỏe)


class DocumentStatus(str, Enum):
    ACTIVE = "ACTIVE"          # Đang có hiệu lực chính thức
    SUPERSEDED = "SUPERSEDED"  # Đã bị văn bản mới hơn thay thế (vẫn lưu vết, không đưa vào kết quả active)
    REVOKED = "REVOKED"        # Đã bị bãi bỏ / hủy bỏ
    EXPIRED = "EXPIRED"        # Đã hết hiệu lực thi hành
    DRAFT = "DRAFT"            # Dự thảo / Chưa ban hành chính thức
    UNKNOWN = "UNKNOWN"        # Chưa xác định rõ tình trạng pháp lý / hiệu lực


class DocumentType(str, Enum):
    CLINICAL_GUIDELINE = "CLINICAL_GUIDELINE"          # Hướng dẫn chẩn đoán và điều trị lâm sàng
    MINISTRY_DECISION = "MINISTRY_DECISION"            # Quyết định ban hành của Bộ trưởng / Thứ trưởng Bộ Y tế
    CIRCULAR = "CIRCULAR"                              # Thông tư pháp quy y tế
    DRUG_SAFETY_ALERT = "DRUG_SAFETY_ALERT"            # Cảnh báo an toàn Dược lâm sàng
    DRUG_RECALL = "DRUG_RECALL"                        # Thông báo / Quyết định thu hồi thuốc (Cục Quản lý Dược)
    PUBLIC_HEALTH_GUIDANCE = "PUBLIC_HEALTH_GUIDANCE"  # Hướng dẫn phòng chống dịch bệnh y tế công cộng
    PATIENT_EDUCATION = "PATIENT_EDUCATION"            # Hướng dẫn chăm sóc sức khỏe & phổ biến kiến thức
    TECHNICAL_GUIDANCE = "TECHNICAL_GUIDANCE"          # Quy trình kỹ thuật chuyên môn
    FAQ = "FAQ"                                        # Câu hỏi đáp y tế đã thẩm định
    NEWS = "NEWS"                                      # Bản tin y khoa cập nhật
    OTHER = "OTHER"                                    # Tài liệu chuyên môn khác


# Verified Issuing Authorities & Publishers
SOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "MOH_VN": {
        "source_id": "MOH_VN",
        "publisher": "Bộ Y tế Việt Nam",
        "issuing_authority": "Bộ Y tế",
        "domains": ["moh.gov.vn", "kcb.vn", "dav.gov.vn", "vncdc.gov.vn", "vfa.gov.vn"],
        "trust_tier": TrustTier.TIER_1.value,
        "source_type": "GOVERNMENT_HEALTH_MINISTRY",
        "enabled": True,
        "citation_prefix": "BYT",
        "notes": "Văn bản quy phạm pháp luật, quyết định chuyên môn và phác đồ điều trị quốc gia."
    },
    "KCB_VN": {
        "source_id": "KCB_VN",
        "publisher": "Cục Quản lý Khám, chữa bệnh — Bộ Y tế",
        "issuing_authority": "Cục Quản lý Khám, chữa bệnh",
        "domains": ["kcb.vn", "moh.gov.vn"],
        "trust_tier": TrustTier.TIER_1.value,
        "source_type": "REGULATORY_CLINICAL_AUTHORITY",
        "enabled": True,
        "citation_prefix": "KCB",
        "notes": "Đầu mối ban hành các hướng dẫn chẩn đoán, điều trị chuyên khoa và quy trình kỹ thuật lâm sàng."
    },
    "DAV_VN": {
        "source_id": "DAV_VN",
        "publisher": "Cục Quản lý Dược — Bộ Y tế",
        "issuing_authority": "Cục Quản lý Dược",
        "domains": ["dav.gov.vn", "moh.gov.vn"],
        "trust_tier": TrustTier.TIER_1.value,
        "source_type": "DRUG_REGULATORY_AUTHORITY",
        "enabled": True,
        "citation_prefix": "DAV",
        "notes": "Cơ quan quản lý dược phẩm, cấp phép, thông báo thu hồi thuốc và cảnh báo tương tác thuốc nguy hiểm."
    },
    "GDPM_VN": {
        "source_id": "GDPM_VN",
        "publisher": "Cục Y tế dự phòng — Bộ Y tế",
        "issuing_authority": "Cục Y tế dự phòng",
        "domains": ["vncdc.gov.vn", "moh.gov.vn"],
        "trust_tier": TrustTier.TIER_1.value,
        "source_type": "PREVENTIVE_HEALTH_AUTHORITY",
        "enabled": True,
        "citation_prefix": "YTDP",
        "notes": "Hướng dẫn dịch bệnh truyền nhiễm, vắc xin và Chương trình Tiêm chủng Mở rộng quốc gia."
    },
    "WHO_GLOBAL": {
        "source_id": "WHO_GLOBAL",
        "publisher": "World Health Organization (WHO)",
        "issuing_authority": "Tổ chức Y tế Thế giới (WHO)",
        "domains": ["who.int"],
        "trust_tier": TrustTier.TIER_2.value,
        "source_type": "INTERNATIONAL_HEALTH_ORGANIZATION",
        "enabled": True,
        "citation_prefix": "WHO",
        "notes": "Khuyến nghị dịch tễ toàn cầu và hướng dẫn y tế quốc tế."
    },
    "WHO_VN": {
        "source_id": "WHO_VN",
        "publisher": "WHO Viet Nam Office",
        "issuing_authority": "Văn phòng WHO tại Việt Nam",
        "domains": ["who.int"],
        "trust_tier": TrustTier.TIER_2.value,
        "source_type": "INTERNATIONAL_HEALTH_OFFICE",
        "enabled": True,
        "citation_prefix": "WHO-VN",
        "notes": "Tài liệu WHO phối hợp với Bộ Y tế Việt Nam trong các chương trình sức khỏe cộng đồng."
    },
    "BACH_MAI_HOSP": {
        "source_id": "BACH_MAI_HOSP",
        "publisher": "Bệnh viện Bạch Mai",
        "issuing_authority": "Bệnh viện Bạch Mai (Hà Nội)",
        "domains": ["bachmai.gov.vn"],
        "trust_tier": TrustTier.TIER_3.value,
        "source_type": "TERTIARY_PUBLIC_HOSPITAL",
        "enabled": True,
        "citation_prefix": "BMB",
        "notes": "Bệnh viện đa khoa tuyến cuối đặc biệt phía Bắc; trung tâm chống độc và hồi sức tích cực."
    },
    "CHO_RAY_HOSP": {
        "source_id": "CHO_RAY_HOSP",
        "publisher": "Bệnh viện Chợ Rẫy",
        "issuing_authority": "Bệnh viện Chợ Rẫy (TP.HCM)",
        "domains": ["choray.vn"],
        "trust_tier": TrustTier.TIER_3.value,
        "source_type": "TERTIARY_PUBLIC_HOSPITAL",
        "enabled": True,
        "citation_prefix": "CRH",
        "notes": "Bệnh viện đa khoa tuyến cuối đặc biệt phía Nam."
    },
    "NHI_TU_HOSP": {
        "source_id": "NHI_TU_HOSP",
        "publisher": "Bệnh viện Nhi Trung ương",
        "issuing_authority": "Bệnh viện Nhi Trung ương",
        "domains": ["benhviennhitrunguong.gov.vn", "nhitrunguong.org.vn"],
        "trust_tier": TrustTier.TIER_3.value,
        "source_type": "PEDIATRIC_TERTIARY_HOSPITAL",
        "enabled": True,
        "citation_prefix": "NHTU",
        "notes": "Đơn vị đầu ngành Nhi khoa toàn quốc; phác đồ điều trị nhi đồng."
    },
    "VIHEALTHQA": {
        "source_id": "VIHEALTHQA",
        "publisher": "Bộ dữ liệu ViHealthQA & Nguồn Y tế Chọn lọc",
        "issuing_authority": "ViHealthQA Benchmark / Ban biên tập chuyên môn",
        "domains": ["vinmec.com", "vnexpress.net"],
        "trust_tier": TrustTier.TIER_4.value,
        "source_type": "CURATED_EDUCATIONAL_DATASET",
        "enabled": True,
        "citation_prefix": "MED",
        "notes": "Nguồn bổ trợ giáo dục sức khỏe đại chúng; không thay thế văn bản quy phạm Bộ Y tế."
    },
    "VINMEC_CURATED": {
        "source_id": "VINMEC_CURATED",
        "publisher": "Hệ thống Y tế Vinmec",
        "issuing_authority": "Ban biên tập Y khoa Vinmec",
        "domains": ["vinmec.com"],
        "trust_tier": TrustTier.TIER_4.value,
        "source_type": "PRIVATE_HEALTHCARE_EDUCATION",
        "enabled": True,
        "citation_prefix": "MED",
        "notes": "Kiến thức y học thường thức bổ sung đã chọn lọc."
    },
    "VNEXPRESS_HEALTH": {
        "source_id": "VNEXPRESS_HEALTH",
        "publisher": "VnExpress Sức Khỏe",
        "issuing_authority": "Báo điện tử VnExpress — Chuyên mục Sức Khỏe",
        "domains": ["vnexpress.net"],
        "trust_tier": TrustTier.TIER_4.value,
        "source_type": "NEWS_HEALTH_EDITORIAL",
        "enabled": True,
        "citation_prefix": "MED",
        "notes": "Bản tin y tế đại chúng đã qua biên tập."
    }
}

# Domain allowlist compiled from all registered sources
ALLOWED_DOMAINS: set = set()
for s in SOURCE_REGISTRY.values():
    if s.get("enabled"):
        ALLOWED_DOMAINS.update(s.get("domains", []))

# Disallowed domains (Strictly blocked from indexing)
BLOCKED_DOMAINS = {
    "facebook.com", "tiktok.com", "youtube.com", "instagram.com",
    "webtretho.com", "tinhte.vn", "voz.vn", "reddit.com", "quora.com",
    "medium.com", "wordpress.com", "blogspot.com"
}


# Ranking weights for composite Official-First ranking
TIER_WEIGHTS = {
    TrustTier.TIER_1.value: 1.50,
    TrustTier.TIER_2.value: 1.25,
    TrustTier.TIER_3.value: 1.10,
    TrustTier.TIER_4.value: 0.85
}

STATUS_WEIGHTS = {
    DocumentStatus.ACTIVE.value: 1.00,
    DocumentStatus.UNKNOWN.value: 0.70,
    DocumentStatus.SUPERSEDED.value: 0.05,  # Bị phạt nặng để không lấn át active document
    DocumentStatus.EXPIRED.value: 0.00,     # Loại bỏ
    DocumentStatus.REVOKED.value: 0.00,     # Loại bỏ
    DocumentStatus.DRAFT.value: 0.00        # Loại bỏ
}

TYPE_WEIGHTS = {
    DocumentType.CLINICAL_GUIDELINE.value: 1.25,
    DocumentType.MINISTRY_DECISION.value: 1.20,
    DocumentType.CIRCULAR.value: 1.20,
    DocumentType.DRUG_SAFETY_ALERT.value: 1.30,
    DocumentType.DRUG_RECALL.value: 1.35,
    DocumentType.PUBLIC_HEALTH_GUIDANCE.value: 1.15,
    DocumentType.TECHNICAL_GUIDANCE.value: 1.10,
    DocumentType.PATIENT_EDUCATION.value: 0.90,
    DocumentType.FAQ.value: 0.90,
    DocumentType.NEWS.value: 0.60,
    DocumentType.OTHER.value: 0.80
}


def is_domain_allowed(url_or_domain: str) -> bool:
    """Verify if a given URL or domain is strictly inside the approved registry allowlist."""
    if not url_or_domain:
        return False
    raw = str(url_or_domain).strip().lower()
    if "://" in raw:
        try:
            domain = urlparse(raw).netloc.lower()
        except Exception:
            return False
    else:
        domain = raw

    # Strip port if present
    domain = domain.split(":")[0]

    # Blocked domains
    for b in BLOCKED_DOMAINS:
        if domain == b or domain.endswith("." + b):
            return False

    # Allowed domains check
    for a in ALLOWED_DOMAINS:
        if domain == a or domain.endswith("." + a):
            return True
    return False


def get_source_config(source_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve verified metadata configuration for a source."""
    return SOURCE_REGISTRY.get(str(source_id).strip().upper())


def resolve_source_by_url(url: str) -> Dict[str, Any]:
    """Identify matching source from URL domain."""
    if not url:
        return SOURCE_REGISTRY["VIHEALTHQA"]
    domain = urlparse(url).netloc.lower().split(":")[0]

    if "moh.gov.vn" in domain or "kcb.vn" in domain:
        return SOURCE_REGISTRY["MOH_VN"]
    elif "dav.gov.vn" in domain:
        return SOURCE_REGISTRY["DAV_VN"]
    elif "vncdc.gov.vn" in domain:
        return SOURCE_REGISTRY["GDPM_VN"]
    elif "who.int" in domain:
        return SOURCE_REGISTRY["WHO_VN"] if "vietnam" in url.lower() else SOURCE_REGISTRY["WHO_GLOBAL"]
    elif "bachmai.gov.vn" in domain:
        return SOURCE_REGISTRY["BACH_MAI_HOSP"]
    elif "choray.vn" in domain:
        return SOURCE_REGISTRY["CHO_RAY_HOSP"]
    elif "vinmec.com" in domain:
        return SOURCE_REGISTRY["VINMEC_CURATED"]
    elif "vnexpress.net" in domain:
        return SOURCE_REGISTRY["VNEXPRESS_HEALTH"]

    return SOURCE_REGISTRY["VIHEALTHQA"]


def get_trust_label_vi(trust_tier: str) -> str:
    """Provide user-facing Vietnamese description of trust tier."""
    tier = str(trust_tier).upper()
    if tier == TrustTier.TIER_1.value:
        return "Nguồn chính thức Bộ Y tế Việt Nam"
    elif tier == TrustTier.TIER_2.value:
        return "Tổ chức Y tế Quốc tế (WHO)"
    elif tier == TrustTier.TIER_3.value:
        return "Bệnh viện công lập tuyến cuối"
    return "Nguồn tri thức y tế tham khảo bổ sung"
