"""
Independent Retrieval Evaluation Suite for MEDICARE AI (Phase 4).

Measures:
- Knowledge documents count & chunks count
- Retrieval Accuracy (Top-1, Top-3 on clinical queries)
- No-result accuracy on out-of-domain/irrelevant queries
- Latency metrics (Median latency, P95 latency)
- Average RAG context size (characters)
"""

import json
import statistics
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import rag_service

# Independent clinical evaluation dataset (not used for indexing definition)
CLINICAL_TEST_SET = [
    {"query": "Bị đau dạ dày và ợ chua nhiều", "topic": "dạ dày"},
    {"query": "dau da day va non mua", "topic": "dạ dày"},  # unaccented
    {"query": "Đau bao tử kèm nóng rát cổ họng", "topic": "dạ dày"},  # synonym
    {"query": "Bị viêm gan B có lây qua đường ăn uống không?", "topic": "viêm gan"},
    {"query": "viem gan b man tinh uong thuoc gi", "topic": "viêm gan"},  # unaccented
    {"query": "Dấu hiệu cảnh báo sốt xuất huyết ở trẻ", "topic": "sốt xuất huyết"},
    {"query": "sot xuat huyet ngay thu 4 bi phat ban", "topic": "sốt xuất huyết"},  # unaccented
    {"query": "Đau đầu dữ dội và chóng mặt buồn nôn", "topic": "đau đầu"},
    {"query": "nhuc dau chong mat mat ngu keo dai", "topic": "đau đầu"},  # unaccented & synonym
    {"query": "Khó thở đau thắt ngực khi gắng sức", "topic": "đau ngực"},
    {"query": "Tim đập nhanh hồi hộp đánh trống ngực", "topic": "tim đập nhanh"},
    {"query": "Chỉ số đường huyết của người bị tiểu đường", "topic": "tiểu đường"},
    {"query": "dai thao duong type 2 an gi", "topic": "tiểu đường"},  # unaccented & synonym
    {"query": "Huyết áp cao 160/100 có nguy hiểm không", "topic": "huyết áp"},
    {"query": "tang huyet ap dot ngot xu tri the nao", "topic": "huyết áp"},  # unaccented & synonym
    {"query": "Dị ứng nổi mề đay ngứa khắp người", "topic": "dị ứng"},
    {"query": "noi me day man ngua do thoi tiet", "topic": "dị ứng"},  # unaccented
    {"query": "Bé bị sốt cao co giật cần làm gì", "topic": "sốt cao"},
    {"query": "Viêm họng hạt nuốt vướng có mủ", "topic": "viêm họng"},
    {"query": "viem xoang man tinh gay nhuc dau", "topic": "viêm xoang"},  # unaccented
    {"query": "Viêm phổi ở người cao tuổi điều trị bao lâu", "topic": "viêm phổi"},
    {"query": "Tiêu chảy ra nước nhiều lần trong ngày", "topic": "tiêu chảy"},
    {"query": "Táo bón lâu ngày đi ngoài ra máu", "topic": "táo bón"},
    {"query": "Tiêm phòng vaccine sởi quai bị rubella", "topic": "vaccine"},
    {"query": "tiem ngua cum cho phu nu mang thai", "topic": "tiêm"},  # unaccented
    {"query": "Trào ngược dạ dày gây ho khan về đêm", "topic": "trào ngược"},
    {"query": "Men gan cao 150 có phải kiêng rượu bia không", "topic": "men gan"},
    {"query": "Sốt virus bao nhiêu ngày thì khỏi hoàn toàn", "topic": "sốt virus"},
    {"query": "Đau nhức khớp gối khi trời lạnh", "topic": "đau khớp"},
    {"query": "Chóng mặt khi thay đổi tư thế đột ngột", "topic": "chóng mặt"},
]

# Out-of-domain / Irrelevant queries (must return 0 results or be skipped)
IRRELEVANT_TEST_SET = [
    "Thời tiết ngày mai tại Hà Nội nắng hay mưa",
    "thoi tiet hom nay the nao",
    "Giá vàng miếng SJC 9999 hôm nay bao nhiêu tiền",
    "Tỷ giá đồng đô la Mỹ USD sang VND",
    "Lập trình Python backend với Flask framework",
    "Cách viết function trong JavaScript",
    "Cách sửa xe máy bị thủng lốp dọc đường",
    "Hướng dẫn thay nhớt xe máy Honda",
    "Địa chỉ quán bún chả ngon nhất phố cổ",
    "Cách làm món thịt kho tàu đậm đà",
    "Tin tức bóng đá Ngoại hạng Anh đêm qua",
    "Kết quả xổ số miền Bắc hôm nay",
    "Review phim chiếu rạp mới ra mắt cuối tuần",
    "Bài thơ tình hay về mùa thu Hà Nội",
    "Mua vé máy bay đi Đà Nẵng giá rẻ",
    "Cách đăng ký tài khoản ngân hàng online",
    "Tìm phòng trọ sinh viên giá rẻ gần đại học",
    "Thời gian mở cửa trung tâm thương mại",
    "Hướng dẫn cài đặt Windows 11 chi tiết",
    "Làm sao để kiếm tiền thụ động trên mạng",
]


def run_evaluation():
    print("==================================================")
    print("PHASE 4: RETRIEVAL EVALUATION & BENCHMARK REPORT")
    print("==================================================")

    # 1. Inspect DB stats
    con = rag_service.get_db_connection()
    if not con:
        print("[LỖI] Không thể mở kết nối tới database/medical.db!")
        return

    doc_count = con.execute("SELECT count(*) FROM medical_documents").fetchone()[0]
    chunk_count = con.execute("SELECT count(*) FROM medical_fts").fetchone()[0]
    con.close()

    print(f"Knowledge Documents: {doc_count:,}")
    print(f"Knowledge Chunks: {chunk_count:,}")

    # 2. Benchmark Clinical Queries
    latencies = []
    top1_correct = 0
    top3_correct = 0
    context_sizes = []

    for item in CLINICAL_TEST_SET:
        q = item["query"]
        expected_topic = rag_service.fold_vietnamese(item["topic"])

        t0 = time.perf_counter()
        results = rag_service.search_medical_knowledge(q, limit=3)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        if results:
            ctx = rag_service.format_rag_context(results)
            context_sizes.append(len(ctx))

            # Check top-1
            r0_text = rag_service.fold_vietnamese(results[0]["title"] + " " + results[0]["content"])
            if expected_topic in r0_text:
                top1_correct += 1

            # Check top-3
            any_top3 = any(
                expected_topic in rag_service.fold_vietnamese(r["title"] + " " + r["content"])
                for r in results
            )
            if any_top3:
                top3_correct += 1

    total_clinical = len(CLINICAL_TEST_SET)
    top1_acc = (top1_correct / total_clinical) * 100
    top3_acc = (top3_correct / total_clinical) * 100

    # 3. Benchmark Irrelevant Queries
    no_result_correct = 0
    for q in IRRELEVANT_TEST_SET:
        t0 = time.perf_counter()
        results = rag_service.search_medical_knowledge(q, limit=3)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        if len(results) == 0:
            no_result_correct += 1

    total_irrelevant = len(IRRELEVANT_TEST_SET)
    no_result_acc = (no_result_correct / total_irrelevant) * 100

    # 4. Compute Latency Metrics
    latencies.sort()
    med_latency = statistics.median(latencies)
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[min(p95_idx, len(latencies) - 1)]
    avg_context_size = sum(context_sizes) / len(context_sizes) if context_sizes else 0

    print("\n--- KẾT QUẢ RETRIEVAL EVALUATION ---")
    print(f"Clinical Queries Tested: {total_clinical}")
    print(f"Top-1 Accuracy: {top1_acc:.2f}% ({top1_correct}/{total_clinical})")
    print(f"Top-3 Accuracy: {top3_acc:.2f}% ({top3_correct}/{total_clinical})")
    print(f"Irrelevant Queries Tested: {total_irrelevant}")
    print(f"No-Result Accuracy: {no_result_acc:.2f}% ({no_result_correct}/{total_irrelevant})")
    print("\n--- HIỆU NĂNG & ĐỘ TRỄ (LATENCY) ---")
    print(f"Median Retrieval Latency: {med_latency:.2f} ms")
    print(f"P95 Retrieval Latency: {p95_latency:.2f} ms")
    print(f"Average RAG Context Size: {avg_context_size:.0f} ký tự")

    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "top1_acc": top1_acc,
        "top3_acc": top3_acc,
        "no_result_acc": no_result_acc,
        "med_latency": med_latency,
        "p95_latency": p95_latency,
        "avg_context_size": avg_context_size
    }


if __name__ == "__main__":
    run_evaluation()
