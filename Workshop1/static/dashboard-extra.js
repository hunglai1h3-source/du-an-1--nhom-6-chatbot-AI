"use strict";

(() => {
  const M = window.MediCare;
  if (!M) return;
  const $ = M.$;
  const $$ = M.$$;

  const NEWS = new Map();
  let activeNewsFilter = "all";

  function setText(selector, value) {
    const node = $(selector);
    if (node) node.textContent = value;
  }

  function formatToday() {
    return new Intl.DateTimeFormat("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date());
  }

  async function updateHomeSummary() {
    if (!$("#healthStatusText")) return;
    const profile = M.getProfiles().length ? M.getSelectedProfile() : null;
    setText("#dashboardTodayText", `Hôm nay là ${formatToday()}. Theo dõi sức khỏe và những thông tin cần chú ý trong ngày.`);
    setText("#healthStatusText", profile ? `Đang theo dõi ${profile.name}` : "Chưa có hồ sơ");

    const context = M.readJSON(M.KEYS.locationContext, null);
    const aqi = Number(context?.aqi);
    setText("#homeAqiText", Number.isFinite(aqi) ? `AQI ${Math.round(aqi)} · ${M.aqiLevel(aqi).text}` : "Chưa có dữ liệu");

    try {
      const auth = await M.currentUser();
      if (!auth.logged_in) {
        setText("#medicineSummaryText", "Đăng nhập để xem");
        return;
      }
      const response = await fetch("/api/reminders", { credentials: "same-origin", cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Không tải được lịch nhắc");
      const active = (data.items || []).filter((item) => item.is_active);
      setText("#medicineSummaryText", active.length ? `${active.length} lịch đang bật` : "Chưa có lịch nhắc");
    } catch (_) {
      setText("#medicineSummaryText", "Chưa tải được");
    }
  }

  function newsFallbackImage(category) {
    if (category === "nutrition") return "/static/images/news-nutrition.svg";
    if (category === "mental") return "/static/images/news-sleep.svg";
    if (category === "community") return "/static/images/news-doctor.svg";
    if (category === "disease") return "/static/images/news-air.svg";
    return "/static/images/news-medicine.svg";
  }

  function relativeNewsTime(value) {
    if (!value) return "Mới cập nhật";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Mới cập nhật";

    const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
    if (minutes < 60) return minutes <= 1 ? "Vừa cập nhật" : `${minutes} phút trước`;

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} giờ trước`;

    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} ngày trước`;

    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric"
    }).format(date);
  }

  function newsImage(article) {
    return article.image_url || newsFallbackImage(article.category);
  }

  function renderHealthNews(items) {
    const loading = $("#healthNewsLoading");
    const content = $("#healthNewsContent");
    const empty = $("#healthNewsEmpty");
    const featuredRoot = $("#healthNewsFeatured");
    const listRoot = $("#healthNewsList");

    if (loading) loading.classList.add("hidden");
    if (!featuredRoot || !listRoot || !content || !empty) return;

    const filtered = items.filter(
      (article) => activeNewsFilter === "all" || article.category === activeNewsFilter
    );

    if (!filtered.length) {
      content.classList.add("hidden");
      empty.classList.remove("hidden");
      return;
    }

    empty.classList.add("hidden");
    content.classList.remove("hidden");

    const featured = filtered.find((article) => article.is_featured) || filtered[0];
    const remaining = filtered.filter((article) => article.id !== featured.id).slice(0, 5);

    const fallback = newsFallbackImage(featured.category);
    featuredRoot.innerHTML = `
      <button class="news-featured" type="button" data-dynamic-news-id="${featured.id}">
        <img
          src="${M.escapeHTML(newsImage(featured))}"
          alt=""
          loading="lazy"
          referrerpolicy="no-referrer"
          data-news-fallback="${M.escapeHTML(fallback)}"
        >
        ${featured.is_featured ? '<span class="news-hot">NỔI BẬT</span>' : ""}
        <strong>${M.escapeHTML(featured.title)}</strong>
        <p>${M.escapeHTML(featured.summary)}</p>
        <small>${M.escapeHTML(featured.source_name)} · ${M.escapeHTML(relativeNewsTime(featured.published_at || featured.reviewed_at || featured.created_at))}</small>
      </button>
    `;

    listRoot.innerHTML = remaining.map((article) => {
      const itemFallback = newsFallbackImage(article.category);
      return `
        <button type="button" data-dynamic-news-id="${article.id}">
          <img
            src="${M.escapeHTML(newsImage(article))}"
            alt=""
            loading="lazy"
            referrerpolicy="no-referrer"
            data-news-fallback="${M.escapeHTML(itemFallback)}"
          >
          <span>
            <strong>${M.escapeHTML(article.title)}</strong>
            <small>${M.escapeHTML(article.source_name)} · ${M.escapeHTML(relativeNewsTime(article.published_at || article.reviewed_at || article.created_at))}</small>
          </span>
          <em>${M.escapeHTML(article.category_label || "Sức khỏe")}</em>
        </button>
      `;
    }).join("");

    $$("[data-news-fallback]", content).forEach((img) => {
      img.addEventListener("error", () => {
        const fallbackSrc = img.dataset.newsFallback;
        if (fallbackSrc && img.src !== fallbackSrc) img.src = fallbackSrc;
      }, { once: true });
    });
  }

  async function loadHealthNews() {
    const loading = $("#healthNewsLoading");
    const content = $("#healthNewsContent");
    const empty = $("#healthNewsEmpty");

    if (!loading || !content || !empty) return;

    loading.classList.remove("hidden");
    content.classList.add("hidden");
    empty.classList.add("hidden");

    try {
      const response = await fetch("/api/health-news?limit=12", {
        credentials: "same-origin",
        cache: "no-store"
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Không tải được bản tin.");

      NEWS.clear();
      (data.items || []).forEach((article) => NEWS.set(String(article.id), article));
      renderHealthNews([...NEWS.values()]);
    } catch (error) {
      loading.classList.add("hidden");
      empty.classList.remove("hidden");
      empty.innerHTML = `
        <strong>Chưa tải được bản tin.</strong>
        <span>${M.escapeHTML(error.message || "Vui lòng thử lại sau.")}</span>
      `;
    }
  }

  async function bindNews() {
    const modal = $("#homeNewsModal");
    if (!modal) return;

    const openArticle = (id) => {
      const article = NEWS.get(String(id));
      if (!article) return;

      setText("#homeNewsCategory", article.category_label || "Bản tin sức khỏe");
      setText("#homeNewsTitle", article.title);
      setText("#homeNewsLead", article.summary);

      const body = $("#homeNewsBody");
      if (body) {
        body.innerHTML = `
          <p>MediCare AI chỉ hiển thị mô tả ngắn và nguồn bài báo. Nội dung đầy đủ được đọc tại trang báo gốc.</p>
        `;
      }

      const source = $("#homeNewsSource");
      if (source) {
        source.textContent = `Nguồn: ${article.source_name} · ${relativeNewsTime(article.published_at || article.reviewed_at || article.created_at)}`;
      }

      const sourceLink = $("#homeNewsSourceLink");
      if (sourceLink) sourceLink.href = article.source_url;

      const ask = $("#homeNewsAskAI");
      if (ask) {
        const prompt = `Hãy giải thích chủ đề "${article.title}" theo hướng sức khỏe an toàn và dễ hiểu. Nguồn bài báo: ${article.source_name}. Không giả định rằng bạn đã đọc toàn bộ bài báo.`;
        ask.href = `/tu-van?prompt=${encodeURIComponent(prompt)}`;
      }

      modal.classList.remove("hidden");
    };

    document.addEventListener("click", (event) => {
      const button = event.target.closest("[data-dynamic-news-id]");
      if (button) openArticle(button.dataset.dynamicNewsId);
    });

    $("#closeHomeNewsModal")?.addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (event) => {
      if (event.target === modal) modal.classList.add("hidden");
    });

    $$("[data-news-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        $$("[data-news-filter]").forEach((item) => {
          item.classList.toggle("active", item === button);
        });
        activeNewsFilter = button.dataset.newsFilter || "all";
        renderHealthNews([...NEWS.values()]);
      });
    });

    await loadHealthNews();
  }

  function bmiInfo(profile) {
    const height = Number(profile?.height);
    const weight = Number(profile?.weight);
    if (!Number.isFinite(height) || height <= 0 || !Number.isFinite(weight) || weight <= 0) {
      return { value: null, status: "Chưa đủ dữ liệu" };
    }
    const bmi = weight / ((height / 100) ** 2);
    let status = "Trong khoảng tham khảo";
    if (bmi < 18.5) status = "Thấp hơn khoảng tham khảo";
    else if (bmi >= 25 && bmi < 30) status = "Cao hơn khoảng tham khảo";
    else if (bmi >= 30) status = "Cao đáng kể";
    return { value: Math.round(bmi * 10) / 10, status };
  }

  async function getActiveReminderCount() {
    try {
      const auth = await M.currentUser();
      if (!auth.logged_in) return null;
      const response = await fetch("/api/reminders", { credentials: "same-origin", cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) return null;
      return (data.items || []).filter((item) => item.is_active).length;
    } catch (_) { return null; }
  }

  function aqiSummary() {
    const context = M.readJSON(M.KEYS.locationContext, null);
    const aqi = Number(context?.aqi);
    if (!Number.isFinite(aqi)) return { value: null, text: "Chưa có dữ liệu" };
    return { value: Math.round(aqi), text: M.aqiLevel(aqi).text };
  }

  let lastReportText = "";

  async function refreshHealthReport() {
    if (!$("#health-report")) return;
    const profile = M.getProfiles().length ? M.getSelectedProfile() : null;
    const reminderCount = await getActiveReminderCount();
    const aqi = aqiSummary();
    const bmi = bmiInfo(profile);

    setText("#reportProfileAvatar", profile ? M.initials(profile.name) : "K");
    setText("#reportProfileName", profile?.name || "Chưa có hồ sơ");
    setText("#reportProfileMeta", profile ? `${profile.age} tuổi · ${profile.gender} · ${profile.relationship}` : "Chọn hồ sơ để xem báo cáo");
    setText("#reportWeight", profile?.weight ? `${profile.weight} kg` : "Chưa cập nhật");
    setText("#reportWeightTrend", profile?.relationship === "Bản thân" ? "Có thể theo dõi lịch sử" : "Theo hồ sơ hiện tại");
    setText("#reportBmi", bmi.value != null ? String(bmi.value) : "--");
    setText("#reportBmiStatus", bmi.status);
    setText("#reportReminder", reminderCount == null ? "--" : String(reminderCount));
    setText("#reportAqi", aqi.value == null ? "--" : `AQI ${aqi.value}`);
    setText("#reportAqiStatus", aqi.text);
    setText("#reportCondition", profile?.condition || "Chưa cập nhật");
    setText("#reportAllergy", profile?.allergies || "Chưa cập nhật");

    const dateText = new Intl.DateTimeFormat("vi-VN", { dateStyle: "long", timeStyle: "short" }).format(new Date());
    lastReportText = [
      "BÁO CÁO SỨC KHỎE - MEDICARE AI",
      `Cập nhật: ${dateText}`,
      "",
      `Hồ sơ: ${profile?.name || "Chưa có hồ sơ"}`,
      profile ? `Tuổi: ${profile.age} · Giới tính: ${profile.gender} · Quan hệ: ${profile.relationship}` : "",
      `Chiều cao: ${profile?.height ? profile.height + " cm" : "Chưa cập nhật"}`,
      `Cân nặng: ${profile?.weight ? profile.weight + " kg" : "Chưa cập nhật"}`,
      `BMI ước tính: ${bmi.value != null ? bmi.value + " - " + bmi.status : "Chưa đủ dữ liệu"}`,
      `Bệnh nền / ghi chú: ${profile?.condition || "Chưa cập nhật"}`,
      `Dị ứng: ${profile?.allergies || "Chưa cập nhật"}`,
      `Lịch nhắc đang bật (tài khoản): ${reminderCount == null ? "Chưa tải được" : reminderCount}`,
      `Chất lượng không khí: ${aqi.value == null ? "Chưa có dữ liệu" : "AQI " + aqi.value + " - " + aqi.text}`,
      "",
      "Lưu ý: Báo cáo này tổng hợp dữ liệu người dùng đã khai báo và dữ liệu theo dõi trong hệ thống; không phải chẩn đoán y khoa."
    ].filter(Boolean).join("\n");

    const printable = $("#healthReportPrintable");
    if (printable) printable.innerHTML = lastReportText.split("\n").map((line) => line ? `<p>${M.escapeHTML(line)}</p>` : '<hr>').join("");
  }


  function concatPdfBytes(chunks) {
    const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const output = new Uint8Array(total);
    let offset = 0;
    chunks.forEach((chunk) => {
      output.set(chunk, offset);
      offset += chunk.length;
    });
    return output;
  }

  function asciiPdfBytes(text) {
    return new TextEncoder().encode(text);
  }

  function dataUrlToBytes(dataUrl) {
    const base64 = String(dataUrl || "").split(",")[1] || "";
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  function buildJpegPdf(jpegBytes, imageWidth, imageHeight) {
    const chunks = [];
    const offsets = [0];
    let byteLength = 0;

    const push = (chunk) => {
      const bytes = typeof chunk === "string" ? asciiPdfBytes(chunk) : chunk;
      chunks.push(bytes);
      byteLength += bytes.length;
    };

    push(new Uint8Array([
      0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34, 0x0a,
      0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a
    ]));

    const addObject = (number, bodyChunks) => {
      offsets[number] = byteLength;
      push(`${number} 0 obj\n`);
      bodyChunks.forEach(push);
      push("\nendobj\n");
    };

    addObject(1, ["<< /Type /Catalog /Pages 2 0 R >>"]);
    addObject(2, ["<< /Type /Pages /Kids [3 0 R] /Count 1 >>"]);
    addObject(3, [
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] ",
      "/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>"
    ]);

    const content = asciiPdfBytes("q\n595 0 0 842 0 0 cm\n/Im0 Do\nQ\n");
    addObject(4, [
      `<< /Length ${content.length} >>\nstream\n`,
      content,
      "endstream"
    ]);

    addObject(5, [
      `<< /Type /XObject /Subtype /Image /Width ${imageWidth} /Height ${imageHeight} `,
      `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`,
      jpegBytes,
      "\nendstream"
    ]);

    const xrefOffset = byteLength;
    push("xref\n0 6\n");
    push("0000000000 65535 f \n");
    for (let number = 1; number <= 5; number += 1) {
      push(`${String(offsets[number]).padStart(10, "0")} 00000 n \n`);
    }
    push("trailer\n<< /Size 6 /Root 1 0 R >>\n");
    push(`startxref\n${xrefOffset}\n%%EOF`);

    return concatPdfBytes(chunks);
  }

  function drawWrappedText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = String(text || "").split(/\s+/);
    let line = "";
    let cursorY = y;

    words.forEach((word) => {
      const testLine = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(testLine).width > maxWidth) {
        ctx.fillText(line, x, cursorY);
        line = word;
        cursorY += lineHeight;
      } else {
        line = testLine;
      }
    });

    if (line) {
      ctx.fillText(line, x, cursorY);
      cursorY += lineHeight;
    }

    return cursorY;
  }

  function createHealthReportPdfBytes(reportText) {
    const canvas = document.createElement("canvas");
    canvas.width = 1240;
    canvas.height = 1754;

    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Trình duyệt không hỗ trợ tạo PDF.");

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#079455";
    ctx.font = "700 42px Arial, sans-serif";
    ctx.fillText("MediCare AI", 82, 105);

    ctx.fillStyle = "#17202d";
    ctx.font = "700 34px Arial, sans-serif";
    ctx.fillText("BÁO CÁO SỨC KHỎE", 82, 160);

    ctx.strokeStyle = "#d8e9df";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(82, 190);
    ctx.lineTo(1158, 190);
    ctx.stroke();

    let y = 245;
    const lines = String(reportText || "").split("\n");

    lines.forEach((rawLine) => {
      const line = rawLine.trim();

      if (!line) {
        y += 20;
        return;
      }

      const isTitle = line === "BÁO CÁO SỨC KHỎE - MEDICARE AI";
      if (isTitle) return;

      ctx.fillStyle = "#17202d";
      ctx.font = line.startsWith("Hồ sơ:")
        ? "700 26px Arial, sans-serif"
        : "400 23px Arial, sans-serif";

      y = drawWrappedText(ctx, line, 82, y, 1076, 38);
      y += 6;
    });

    ctx.strokeStyle = "#d8e9df";
    ctx.beginPath();
    ctx.moveTo(82, 1580);
    ctx.lineTo(1158, 1580);
    ctx.stroke();

    ctx.fillStyle = "#667085";
    ctx.font = "400 19px Arial, sans-serif";
    drawWrappedText(
      ctx,
      "Báo cáo được tổng hợp từ dữ liệu người dùng đã khai báo và dữ liệu theo dõi trong hệ thống. Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán hoặc điều trị.",
      82,
      1625,
      1076,
      30
    );

    const jpegBytes = dataUrlToBytes(canvas.toDataURL("image/jpeg", 0.94));
    return buildJpegPdf(jpegBytes, canvas.width, canvas.height);
  }

  function downloadHealthReportPdf(reportText) {
    const pdfBytes = createHealthReportPdfBytes(reportText);
    const blob = new Blob([pdfBytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `Bao-cao-suc-khoe-MediCare-${new Date().toISOString().slice(0, 10)}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  function bindHealthReport() {
    if (!$("#health-report")) return;
    $("#refreshHealthReport")?.addEventListener("click", async () => { await refreshHealthReport(); M.showToast("Đã làm mới báo cáo sức khỏe.", "success"); });
    const modal = $("#healthReportModal");
    $("#openHealthReport")?.addEventListener("click", async () => { await refreshHealthReport(); modal?.classList.remove("hidden"); });
    $("#closeHealthReportModal")?.addEventListener("click", () => modal?.classList.add("hidden"));
    modal?.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });
    $("#copyHealthReport")?.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(lastReportText); M.showToast("Đã sao chép báo cáo.", "success"); }
      catch (_) { M.showToast("Trình duyệt không cho phép sao chép tự động.", "error"); }
    });
    $("#printHealthReport")?.addEventListener("click", async () => {
      try {
        if (!lastReportText) await refreshHealthReport();
        downloadHealthReportPdf(lastReportText);
        M.showToast("Đã tạo file PDF báo cáo sức khỏe.", "success");
      } catch (error) {
        console.error("Không thể tạo PDF:", error);
        M.showToast("Không thể tạo file PDF. Vui lòng thử lại.", "error");
      }
    });
  }

  function openReminderCreate(type) {
    $("#showRemindersButton")?.click();
    window.setTimeout(() => {
      $("#addReminderButton")?.click();
      const select = $("#reminderForm select[name='reminder_type']");
      if (select && type) {
        select.value = type;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, 120);
  }

  function bindHealthActions() {
    $$('[data-health-action]').forEach((button) => button.addEventListener("click", async () => {
      const action = button.dataset.healthAction;
      if (action === "symptoms") window.location.assign("/tu-van?prompt=" + encodeURIComponent("Tôi muốn theo dõi triệu chứng hiện tại dựa trên hồ sơ sức khỏe đang chọn."));
      else if (action === "medicine") openReminderCreate("medicine");
      else if (action === "appointment") openReminderCreate("appointment");
      else if (action === "metrics" || action === "bmi") { await refreshHealthReport(); $("#health-report")?.scrollIntoView({ behavior: "smooth", block: "center" }); }
      else if (action === "lab") window.location.assign("/tu-van?prompt=" + encodeURIComponent("Tôi muốn phân tích kết quả xét nghiệm. Hãy hướng dẫn tôi tải ảnh kết quả lên và giải thích theo hướng tham khảo."));
      else if (action === "air") window.location.assign("/#utilities");
      else if (action === "documents") window.location.assign("/kien-thuc");
    }));

    $$('[data-section-target]').forEach((button) => button.addEventListener("click", () => {
      $$('[data-section-target]').forEach((item) => item.classList.toggle("active", item === button));
      document.getElementById(button.dataset.sectionTarget)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }

  function bindHomeShortcuts() {
    $("#homeOpenReminders")?.addEventListener("click", () => $("#showRemindersButton")?.click());
    $("#homeOpenPharmacy")?.addEventListener("click", () => {
      const context = M.readJSON(M.KEYS.locationContext, null);
      window.open(M.mapsSearchUrl(context), "_blank", "noopener,noreferrer");
    });
  }

  async function init() {
    await bindNews();
    bindHealthReport();
    bindHealthActions();
    bindHomeShortcuts();
    window.setTimeout(async () => {
      await updateHomeSummary();
      await refreshHealthReport();
    }, 350);
    window.addEventListener("medicare:profile-changed", async () => {
      await updateHomeSummary();
      await refreshHealthReport();
    });
    window.addEventListener("medicare:profiles-updated", async () => {
      await updateHomeSummary();
      await refreshHealthReport();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
