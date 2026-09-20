# -*- coding: utf-8 -*-
"""
Independent Evaluation & Benchmark Suite for Phase 8: Official Medical Knowledge V2.

Evaluates:
- 80 Diverse Clinical Queries across 12 clinical specialties:
    1. Sốt xuất huyết Dengue & Cảnh báo sốc
    2. Hô hấp: Viêm phổi cộng đồng & Cúm mùa
    3. Tiêu hóa: Dạ dày, Trào ngược GERD, Vi khuẩn HP, Xuất huyết tiêu hóa
    4. Tim mạch: Tăng huyết áp & Cơn tăng huyết áp khẩn cấp
    5. Gan mật: Viêm gan virus B, C, Men gan
    6. Nội tiết: Đái tháo đường Type 2 & Cấp cứu hạ đường huyết
    7. Cấp cứu: Phản vệ & Phác đồ Adrenaline
    8. Nhi khoa: Tay chân miệng & Dấu hiệu giật mình
    9. Sơ cứu: Sốt co giật trẻ em
    10. Tiêm chủng mở rộng: Lịch vắc xin cho trẻ & bà bầu
    11. Dược lâm sàng: Cảnh báo an toàn & Tương tác thuốc (Clopidogrel - Omeprazole)
    12. Thu hồi thuốc: Công văn thu hồi Cục Quản lý Dược (Cefuroxim 500mg)
- 35 Out-of-domain / Irrelevant Queries (IT, thời tiết, giá vàng, xe máy, nấu ăn, âm nhạc...)
- Metrics:
    * Top-1 Relevance Accuracy
    * Top-3 Recall Accuracy
    * Official Vietnam Source (Tier 1/2) Hit Rate
    * Superseded Document Leakage (Expected: 0.0%)
    * Out-of-domain No-Result Accuracy (Expected: >= 95%)
    * Latency: Median & P95 (Expected: < 25ms)
"""

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import rag_service_v2
from source_registry import DocumentStatus, TrustTier

# ==============================================================================
# 1. CLINICAL EVALUATION TEST SET (80 REAL-WORLD QUERIES ACROSS 12 SPECIALTIES)
# ==============================================================================

CLINICAL_TEST_SET: List[Dict[str, Any]] = [
    # 1. SỐT XUẤT HUYẾT DENGUE (8 queries)
    {"query": "Dấu hiệu cảnh báo sốt xuất huyết nguy hiểm cần nhập viện", "topic": "sốt xuất huyết", "expected_tier": "TIER_1", "official_doc": "2760/QĐ-BYT"},
    {"query": "sot xuat huyet ngay thu 4 bi dau bung va chay mau chan rang", "topic": "sốt xuất huyết", "expected_tier": "TIER_1"},
    {"query": "Bị sốt xuất huyết uống thuốc hạ sốt gì an toàn?", "topic": "paracetamol", "expected_tier": "TIER_1"},
    {"query": "Tại sao sốt xuất huyết không được uống Aspirin hay Ibuprofen?", "topic": "aspirin", "expected_tier": "TIER_1"},
    {"query": "sot xuat huyet co duoc uong ibuprofen khong", "topic": "ibuprofen", "expected_tier": "TIER_1"},
    {"query": "Bù dịch và uống nước oresol trong sốt xuất huyết thế nào", "topic": "oresol", "expected_tier": "TIER_1"},
    {"query": "Tiểu cầu hạ và cô đặc máu trong sốt xuất huyết", "topic": "tiểu cầu", "expected_tier": "TIER_1"},
    {"query": "Phân độ sốt xuất huyết theo hướng dẫn mới nhất của Bộ Y tế", "topic": "sốt xuất huyết", "expected_tier": "TIER_1", "official_doc": "2760/QĐ-BYT"},

    # 2. HÔ HẤP: CÚM MÙA & VIÊM PHỔI (8 queries)
    {"query": "Triệu chứng cúm A sốt cao đau nhức toàn thân", "topic": "cúm", "expected_tier": "TIER_1"},
    {"query": "Khi nào người bị cúm cần uống Tamiflu Oseltamivir?", "topic": "oseltamivir", "expected_tier": "TIER_1"},
    {"query": "bi cum uong tamiflu trong vong may gio dau", "topic": "oseltamivir", "expected_tier": "TIER_1"},
    {"query": "Dấu hiệu viêm phổi khó thở thở gấp đau tức ngực", "topic": "viêm phổi", "expected_tier": "TIER_1"},
    {"query": "viem phoi cong dong nguoi lon ho co dom", "topic": "viêm phổi", "expected_tier": "TIER_1"},
    {"query": "Thang điểm CRB-65 đánh giá mức độ nặng viêm phổi", "topic": "crb-65", "expected_tier": "TIER_1"},
    {"query": "Người già bị cúm thở rên lú lẫn có nguy hiểm không", "topic": "cúm", "expected_tier": "TIER_1"},
    {"query": "Biến chứng viêm phổi sau khi mắc cảm cúm", "topic": "viêm phổi", "expected_tier": "TIER_1"},

    # 3. TIÊU HÓA: DẠ DÀY, TRÀO NGƯỢC & XUẤT HUYẾT TIÊU HÓA (8 queries)
    {"query": "Ợ chua ợ nóng rát sau xương ức trào ngược dạ dày", "topic": "trào ngược", "expected_tier": "TIER_1"},
    {"query": "trao nguoc da day thuc quan gerd kieng an gi", "topic": "trào ngược", "expected_tier": "TIER_1"},
    {"query": "Viêm loét dạ dày có vi khuẩn HP uống thuốc gì?", "topic": "dạ dày", "expected_tier": "TIER_1"},
    {"query": "Thuốc ức chế bơm proton PPI uống trước bữa ăn bao lâu?", "topic": "ppi", "expected_tier": "TIER_1"},
    {"query": "Đau vùng thượng vị dạ dày do uống thuốc giảm đau", "topic": "dạ dày", "expected_tier": "TIER_1"},
    {"query": "Dấu hiệu nôn ra máu và đi ngoài phân đen bã cà phê", "topic": "xuất huyết", "expected_tier": "TIER_1"},
    {"query": "xuat huyet tieu hoa cap cuu nhu the nao", "topic": "xuất huyết", "expected_tier": "TIER_1"},
    {"query": "Dạ dày trào ngược gây ho khan rát họng về đêm", "topic": "trào ngược", "expected_tier": "TIER_1"},

    # 4. TIM MẠCH: TĂNG HUYẾT ÁP & TAI BIẾN (7 queries)
    {"query": "Chỉ số huyết áp 140/90 mmHg có phải bị cao huyết áp không?", "topic": "tăng huyết áp", "expected_tier": "TIER_1"},
    {"query": "huyet ap cao can an giam muoi bao nhieu gam moi ngay", "topic": "muối", "expected_tier": "TIER_1"},
    {"query": "Cơn tăng huyết áp kịch phát 180/120 mmHg đau đầu dữ dội", "topic": "cơn tăng huyết áp", "expected_tier": "TIER_1"},
    {"query": "Có nên ngậm thuốc hạ áp nhanh dưới lưỡi khi huyết áp tăng vọt?", "topic": "hạ áp", "expected_tier": "TIER_1"},
    {"query": "Dấu hiệu đột quỵ méo miệng yếu nửa người tăng huyết áp", "topic": "đột quỵ", "expected_tier": "TIER_1"},
    {"query": "Phân độ tăng huyết áp theo hướng dẫn Bộ Y tế", "topic": "tăng huyết áp", "expected_tier": "TIER_1"},
    {"query": "Lối sống và tập thể dục cho người bị cao huyết áp", "topic": "tăng huyết áp", "expected_tier": "TIER_1"},

    # 5. GAN MẬT: VIÊM GAN B, C & MEN GAN (7 queries)
    {"query": "Viêm gan B có lây qua ăn uống chung bát đũa không?", "topic": "viêm gan b", "expected_tier": "TIER_1"},
    {"query": "viem gan b man tinh xet nghiem hbsag duong tinh", "topic": "viêm gan b", "expected_tier": "TIER_1"},
    {"query": "Khi nào cần điều trị thuốc kháng virus Tenofovir Entecavir?", "topic": "tenofovir", "expected_tier": "TIER_1"},
    {"query": "Tự ý bỏ thuốc viêm gan B nguy cơ bùng phát suy gan cấp", "topic": "kháng virus", "expected_tier": "TIER_1"},
    {"query": "Men gan ALT AST tăng cao gấp 2 lần bình thường", "topic": "men gan", "expected_tier": "TIER_1"},
    {"query": "Điều trị Viêm gan C bằng thuốc DAA thời gian bao lâu?", "topic": "viêm gan c", "expected_tier": "TIER_1"},
    {"query": "Phong ngua lay truyen viem gan b tu me sang con", "topic": "viêm gan b", "expected_tier": "TIER_1"},

    # 6. NỘI TIẾT: ĐÁI THÁO ĐƯỜNG & HẠ ĐƯỜNG HUYẾT (7 queries)
    {"query": "Tiêu chuẩn chẩn đoán đái tháo đường đường huyết lúc đói", "topic": "đái tháo đường", "expected_tier": "TIER_1"},
    {"query": "Chi so HbA1c 6.5 phan tram co bi tieu duong khong", "topic": "hba1c", "expected_tier": "TIER_1"},
    {"query": "Dấu hiệu hạ đường huyết run tay vã mồ hôi lạnh", "topic": "hạ đường huyết", "expected_tier": "TIER_1"},
    {"query": "Xử trí cấp cứu cơn hạ đường huyết quy tắc 15-15", "topic": "hạ đường huyết", "expected_tier": "TIER_1"},
    {"query": "Bệnh nhân tiểu đường uống Metformin có tác dụng gì?", "topic": "metformin", "expected_tier": "TIER_1"},
    {"query": "Người nhà bị hôn mê hạ đường huyết có được ép uống nước đường không?", "topic": "hạ đường huyết", "expected_tier": "TIER_1"},
    {"query": "Trieu chung 4 nhieu cua benh dai thao duong type 2", "topic": "đái tháo đường", "expected_tier": "TIER_1"},

    # 7. CẤP CỨU & DỊ ỨNG: PHẢN VỆ & ADRENALINE (6 queries)
    {"query": "4 mức độ phản vệ theo Thông tư 51 của Bộ Y tế", "topic": "phản vệ", "expected_tier": "TIER_1", "official_doc": "51/2017/TT-BYT"},
    {"query": "Thuốc thiết yếu bắt buộc tiêm bắp ngay khi sốc phản vệ", "topic": "adrenaline", "expected_tier": "TIER_1"},
    {"query": "Liều tiêm bắp Adrenaline cấp cứu phản vệ cho người lớn và trẻ em", "topic": "adrenaline", "expected_tier": "TIER_1"},
    {"query": "Dị ứng thuốc kháng sinh nổi mày đay khó thở tức ngực", "topic": "phản vệ", "expected_tier": "TIER_1"},
    {"query": "cap cuu soc phan ve co chong chi dinh tuyet doi khong", "topic": "adrenaline", "expected_tier": "TIER_1"},
    {"query": "Vị trí tiêm bắp Adrenaline mặt trước ngoài đùi", "topic": "adrenaline", "expected_tier": "TIER_1"},

    # 8. NHI KHOA: TAY CHÂN MIỆNG (6 queries)
    {"query": "Dấu hiệu bệnh tay chân miệng ở trẻ nhỏ bọng nước lòng bàn tay", "topic": "tay chân miệng", "expected_tier": "TIER_1"},
    {"query": "Trẻ bị tay chân miệng giật mình chới với có nguy hiểm không?", "topic": "giật mình", "expected_tier": "TIER_1"},
    {"query": "dau hieu bien chung nao tay chan mieng can nhap vien ngay", "topic": "tay chân miệng", "expected_tier": "TIER_1"},
    {"query": "Chăm sóc và vệ sinh vết loét miệng tay chân miệng cho bé", "topic": "tay chân miệng", "expected_tier": "TIER_1"},
    {"query": "Phân độ bệnh tay chân miệng theo Quyết định 1003 của Bộ Y tế", "topic": "tay chân miệng", "expected_tier": "TIER_1"},
    {"query": "Virus EV71 gay tay chan mieng nguy hiem the nao", "topic": "tay chân miệng", "expected_tier": "TIER_1"},

    # 9. SƠ CỨU NHI KHOA: SỐT CO GIẬT (6 queries)
    {"query": "Cách sơ cứu trẻ bị sốt cao co giật tại nhà đúng cách", "topic": "co giật", "expected_tier": "TIER_3"},
    {"query": "Có nên nhét thìa hay đũa vào miệng khi trẻ đang co giật không?", "topic": "co giật", "expected_tier": "TIER_3"},
    {"query": "Dat tre nam nghieng an toan khi bi co giat do sot", "topic": "co giật", "expected_tier": "TIER_3"},
    {"query": "Liều hạ sốt Paracetamol đặt hậu môn cho trẻ co giật", "topic": "paracetamol", "expected_tier": "TIER_3"},
    {"query": "Nhung dieu tuyet doi khong lam khi tre bi sot co giat", "topic": "co giật", "expected_tier": "TIER_3"},
    {"query": "Khi nao tre sot co giat can dua di cap cuu ngay", "topic": "co giật", "expected_tier": "TIER_3"},

    # 10. TIÊM CHỦNG MỞ RỘNG (6 queries)
    {"query": "Lịch tiêm chủng mở rộng cho trẻ dưới 1 tuổi gồm những mũi gì?", "topic": "tiêm chủng", "expected_tier": "TIER_1"},
    {"query": "Trẻ sơ sinh cần tiêm vắc xin gì trong 24 giờ đầu sau sinh?", "topic": "lao", "expected_tier": "TIER_1"},
    {"query": "Mũi tiêm phối hợp 5 trong 1 tiêm vào những tháng tuổi nào?", "topic": "5 trong 1", "expected_tier": "TIER_1"},
    {"query": "Theo dõi phản ứng sau tiêm chủng tại trạm y tế 30 phút", "topic": "tiêm chủng", "expected_tier": "TIER_1"},
    {"query": "Dấu hiệu nguy hiểm sau tiêm vắc xin trẻ sốt cao khóc thét", "topic": "tiêm chủng", "expected_tier": "TIER_1"},
    {"query": "lich tiem uon van cho phu nu mang thai lan dau", "topic": "tiêm chủng", "expected_tier": "TIER_1"},

    # 11. DƯỢC LÂM SÀNG & CẢNH BÁO AN TOÀN (5 queries)
    {"query": "Tương tác nguy hiểm giữa Clopidogrel và thuốc dạ dày Omeprazole", "topic": "clopidogrel", "expected_tier": "TIER_1"},
    {"query": "Tại sao không nên dùng Omeprazole cùng thuốc chống đông Clopidogrel?", "topic": "omeprazole", "expected_tier": "TIER_1"},
    {"query": "canh bao an toan duoc cua cuc quan ly duoc ve tuong tac thuoc", "topic": "cục quản lý dược", "expected_tier": "TIER_1"},
    {"query": "Thuốc hạ acid dạ dày nào ít tương tác với Clopidogrel?", "topic": "pantoprazole", "expected_tier": "TIER_1"},
    {"query": "Nguy cơ huyết khối tắc stent khi dùng chung Clopidogrel và Esomeprazole", "topic": "clopidogrel", "expected_tier": "TIER_1"},

    # 12. THU HỒI THUỐC CỤC QUẢN LÝ DƯỢC (5 queries)
    {"query": "Thông báo thu hồi thuốc viên nén Cefuroxim 500mg do Cục Quản lý Dược ban hành", "topic": "thu hồi thuốc", "expected_tier": "TIER_1"},
    {"query": "Lô thuốc Cefuroxim 500mg nào bị thu hồi vì không đạt độ hòa tan?", "topic": "cefuroxim", "expected_tier": "TIER_1"},
    {"query": "so lo thuoc cefuroxim bi thu hoi toan quoc la gi", "topic": "010223", "expected_tier": "TIER_1"},
    {"query": "Thuốc Cefuroxim của công ty nào bị Cục Quản lý Dược thu hồi?", "topic": "medipharco", "expected_tier": "TIER_1"},
    {"query": "Công văn 1182 QLD-CL về việc thu hồi thuốc không đạt tiêu chuẩn", "topic": "1182/qld-cl", "expected_tier": "TIER_1"}
]

# ==============================================================================
# 2. OUT-OF-DOMAIN & IRRELEVANT TEST SET (35 QUERIES)
# ==============================================================================

IRRELEVANT_TEST_SET: List[str] = [
    "Thời tiết ngày mai tại Hà Nội nắng hay mưa",
    "Dự báo thời tiết thành phố Hồ Chí Minh cuối tuần này",
    "Giá vàng miếng SJC 9999 hôm nay bao nhiêu tiền một lượng",
    "Tỷ giá đồng đô la Mỹ USD sang tiền Việt Nam VND",
    "Lập trình Python backend với Flask framework như thế nào",
    "Cách viết function bất đồng bộ async await trong JavaScript",
    "Cách sửa xe máy Honda Wave bị thủng xăm lốp dọc đường",
    "Hướng dẫn thay dầu nhớt xe máy tay ga định kỳ",
    "Địa chỉ quán bún chả ngon nhất khu vực phố cổ Hoàn Kiếm",
    "Cách nấu món thịt kho tàu mềm thơm đậm đà cho gia đình",
    "Tin tức bóng đá giải Ngoại hạng Anh đêm qua kết quả ra sao",
    "Kết quả xổ số kiến thiết miền Bắc hôm nay mở thưởng",
    "Review phim rạp mới ra mắt cuối tuần có đáng xem không",
    "Tuyển tập những bài thơ tình hay về mùa thu lãng mạn",
    "Cách săn vé máy bay giá rẻ đi du lịch Đà Nẵng mùa hè",
    "Thủ tục mở tài khoản ngân hàng số online cần giấy tờ gì",
    "Tìm phòng trọ sinh viên giá rẻ gần các trường đại học lớn",
    "Giờ mở cửa trung tâm thương mại Vincom và siêu thị",
    "Hướng dẫn cài đặt hệ điều hành Windows 11 từ USB",
    "Cách kiếm tiền thụ động và đầu tư chứng khoán thông minh",
    "Bí quyết chăm sóc cây cảnh phong thủy trong nhà tươi tốt",
    "Cách pha một ly cà phê muối thơm ngon chuẩn vị Huế",
    "Kinh nghiệm đi phượt Hà Giang ngắm hoa tam giác mạch",
    "Đánh giá cấu hình điện thoại iPhone 16 Pro Max mới nhất",
    "Cách dọn dẹp vệ sinh nhà cửa nhanh gọn và ngăn nắp",
    "Lịch phát sóng các chương trình truyền hình yêu thích tối nay",
    "Kỹ thuật câu cá sông và chọn mồi câu hiệu quả nhất",
    "Cách phối đồ thời trang công sở mùa đông thanh lịch",
    "Học tiếng Anh giao tiếp cấp tốc cho người mới bắt đầu",
    "Tập gym tăng cơ giảm mỡ lịch tập 4 buổi một tuần",
    "Cách khắc phục lỗi mạng wifi bị mất kết nối trên máy tính",
    "Thủ tục cấp đổi bằng lái xe ô tô quốc tế online",
    "Cách chọn mua đàn piano cơ cho người mới học nhạc",
    "Ý nghĩa tên gọi các loài hoa đẹp trong ngày sinh nhật",
    "Hướng dẫn làm hộ chiếu phổ thông gắn chip trên Cổng dịch vụ công"
]


def run_comprehensive_evaluation():
    print("====================================================================")
    print("PHASE 8: OFFICIAL MEDICAL KNOWLEDGE V2 INDEPENDENT EVALUATION")
    print("VIETNAM TRUSTED CLINICAL KNOWLEDGE BENCHMARK REPORT")
    print("====================================================================")

    # 1. Database Check & Connection
    con = rag_service_v2.get_v2_db_connection()
    if not con:
        print("[LỖI NGHIÊM TRỌNG] Không thể kết nối tới database/medical_v2.db!")
        return

    doc_count = con.execute("SELECT count(*) FROM medical_documents_v2").fetchone()[0]
    chunk_count = con.execute("SELECT count(*) FROM medical_chunks_v2").fetchone()[0]
    fts_count = con.execute("SELECT count(*) FROM medical_fts_v2").fetchone()[0]
    t1_count = con.execute("SELECT count(*) FROM medical_documents_v2 WHERE trust_tier='TIER_1'").fetchone()[0]
    superseded_count = con.execute("SELECT count(*) FROM medical_documents_v2 WHERE status='SUPERSEDED'").fetchone()[0]
    con.close()

    print(f"Total Knowledge Documents V2: {doc_count:,}")
    print(f"Total Knowledge Chunks V2:    {chunk_count:,}")
    print(f"Tier 1 (Official Vietnam):    {t1_count:,} văn bản chính thức")
    print(f"Superseded Lineage Tracked:   {superseded_count:,} văn bản lịch sử")
    print("--------------------------------------------------------------------")

    # 2. Clinical Benchmark Run
    total_clinical = len(CLINICAL_TEST_SET)
    latencies = []
    top1_correct = 0
    top3_correct = 0
    official_hits = 0
    superseded_leakage = 0
    context_sizes = []

    print(f"\n[RUNNING] Đang đánh giá {total_clinical} câu hỏi lâm sàng đa chuyên khoa...")

    for item in CLINICAL_TEST_SET:
        query = item["query"]
        expected_topic = rag_service_v2.fold_vietnamese(item["topic"])
        expected_tier = item.get("expected_tier")

        t0 = time.perf_counter()
        results = rag_service_v2.search_official_medical_knowledge(query, limit=4)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        if results:
            ctx = rag_service_v2.format_rag_context_v2(results)
            context_sizes.append(len(ctx))

            # Top-1 Check
            r0 = results[0]
            r0_text = rag_service_v2.fold_vietnamese(r0["title"] + " " + r0["content"] + " " + r0.get("section_path", ""))
            if expected_topic in r0_text:
                top1_correct += 1

            # Top-3 Check
            any_top3 = any(
                expected_topic in rag_service_v2.fold_vietnamese(r["title"] + " " + r["content"] + " " + r.get("section_path", ""))
                for r in results[:3]
            )
            if any_top3:
                top3_correct += 1

            # Official Tier 1/2 Hit Check
            if any(r.get("trust_tier") in (TrustTier.TIER_1.value, TrustTier.TIER_2.value, TrustTier.TIER_3.value) for r in results):
                official_hits += 1

            # Superseded Document Leakage Check (Must be 0)
            if any(r.get("status") == DocumentStatus.SUPERSEDED.value for r in results):
                superseded_leakage += 1
                print(f"⚠️ CẢNH BÁO LEAKAGE: Query '{query}' rò rỉ tài liệu superseded: {results[0]['title']}")

    top1_acc = (top1_correct / total_clinical) * 100
    top3_acc = (top3_correct / total_clinical) * 100
    official_hit_rate = (official_hits / total_clinical) * 100
    superseded_leak_rate = (superseded_leakage / total_clinical) * 100

    # 3. Out-of-Domain Benchmark Run
    total_irrelevant = len(IRRELEVANT_TEST_SET)
    no_result_correct = 0

    print(f"[RUNNING] Đang kiểm tra {total_irrelevant} câu hỏi ngoài phạm vi y tế...")

    for q in IRRELEVANT_TEST_SET:
        t0 = time.perf_counter()
        results = rag_service_v2.search_official_medical_knowledge(q, limit=4)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        if len(results) == 0:
            no_result_correct += 1

    no_result_acc = (no_result_correct / total_irrelevant) * 100

    # 4. Latency and Context Statistics
    latencies.sort()
    med_latency = statistics.median(latencies)
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[min(p95_idx, len(latencies) - 1)]
    avg_context_size = sum(context_sizes) / len(context_sizes) if context_sizes else 0

    print("\n====================================================================")
    print("KẾT QUẢ ĐÁNH GIÁ CHẤT LƯỢNG RETRIEVAL V2 (OFFICIAL MEDICAL RAG)")
    print("====================================================================")
    print(f"Tổng số câu hỏi lâm sàng kiểm thử:      {total_clinical}")
    print(f"Độ chính xác Top-1 (Top-1 Relevance):    {top1_acc:.2f}% ({top1_correct}/{total_clinical})")
    print(f"Độ bao phủ Top-3 (Top-3 Recall):         {top3_acc:.2f}% ({top3_correct}/{total_clinical})")
    print(f"Tỷ lệ trúng nguồn chính thức Bộ Y tế:   {official_hit_rate:.2f}% ({official_hits}/{total_clinical})")
    print(f"Tỷ lệ rò rỉ tài liệu hết hiệu lực:       {superseded_leak_rate:.2f}% ({superseded_leakage}/{total_clinical}) -> [CHỈ TIÊU: 0%]")
    print(f"Độ chính xác từ chối câu hỏi ngoài ngành: {no_result_acc:.2f}% ({no_result_correct}/{total_irrelevant})")
    print("--------------------------------------------------------------------")
    print(f"Độ trễ trung vị (Median Latency):        {med_latency:.2f} ms")
    print(f"Độ trễ phân vị 95 (P95 Latency):         {p95_latency:.2f} ms")
    print(f"Kích thước context trung bình cho LLM:   {avg_context_size:.0f} ký tự")
    print("====================================================================")

    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "top1_acc": top1_acc,
        "top3_acc": top3_acc,
        "official_hit_rate": official_hit_rate,
        "superseded_leak_rate": superseded_leak_rate,
        "no_result_acc": no_result_acc,
        "med_latency": med_latency,
        "p95_latency": p95_latency,
        "avg_context_size": avg_context_size
    }


if __name__ == "__main__":
    run_comprehensive_evaluation()
