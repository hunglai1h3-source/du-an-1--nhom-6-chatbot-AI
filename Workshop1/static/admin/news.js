"use strict";

(() => {
  if (window.AdminPage !== "news") return;

  const $ = (selector, root = document) => root.querySelector(selector);

  const escapeHTML = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);

  const numberFormat = (value) =>
    new Intl.NumberFormat("vi-VN").format(Number(value || 0));

  const toast = (message, kind = "success") => {
    const element = $("#toast");
    if (!element) return;

    element.textContent = message;
    element.dataset.kind = kind;
    element.classList.add("show");

    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => {
      element.classList.remove("show");
    }, 2600);
  };

  async function requestJSON(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      ...options
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || `Yêu cầu thất bại (${response.status}).`);
    }

    return data;
  }

  let newsItems = [];
  let currentImageObjectUrl = "";

  const statusLabel = (status) => ({
    pending: "Chờ duyệt",
    approved: "Đã duyệt",
    draft: "Đã ẩn",
    rejected: "Từ chối"
  })[status] || status || "Không rõ";

  const statusClass = (status) => ({
    approved: "success",
    pending: "warning",
    rejected: "danger",
    draft: "muted"
  })[status] || "";

  function clearObjectUrl() {
    if (currentImageObjectUrl) {
      URL.revokeObjectURL(currentImageObjectUrl);
      currentImageObjectUrl = "";
    }
  }

  function setImagePreview(url = "", label = "") {
    const box = $("#newsImagePreviewBox");
    const image = $("#newsImagePreview");
    const fileName = $("#newsImageFileName");

    if (!box || !image || !fileName) return;

    if (!url) {
      image.removeAttribute("src");
      fileName.textContent = "Ảnh đại diện";
      box.classList.add("hidden");
      return;
    }

    image.src = url;
    fileName.textContent = label || "Ảnh đại diện";
    box.classList.remove("hidden");
  }

  function resetForm() {
    clearObjectUrl();

    $("#newsForm")?.reset();

    if ($("#newsId")) $("#newsId").value = "";
    if ($("#newsImageUrl")) $("#newsImageUrl").value = "";
    if ($("#newsImageFile")) $("#newsImageFile").value = "";

    setImagePreview();

    if ($("#newsFormTitle")) $("#newsFormTitle").textContent = "Thêm bài báo";
    if ($("#saveNewsButton")) {
      $("#saveNewsButton").textContent = "Tạo bài chờ duyệt";
      $("#saveNewsButton").disabled = false;
    }

    $("#cancelNewsEdit")?.classList.add("hidden");
  }

  function fillForm(item) {
    clearObjectUrl();

    $("#newsId").value = item.id ?? "";
    $("#newsTitle").value = item.title || "";
    $("#newsSourceName").value = item.source_name || "";
    $("#newsCategory").value = item.category || "general";
    $("#newsSourceUrl").value = item.source_url || "";
    $("#newsSummary").value = item.summary || "";
    $("#newsImageUrl").value = item.image_url || "";
    $("#newsImageFile").value = "";

    setImagePreview(
      item.image_url || "",
      item.image_url ? "Ảnh đại diện hiện tại" : ""
    );

    $("#newsFormTitle").textContent = `Sửa bài #${item.id}`;
    $("#saveNewsButton").textContent = "Lưu thay đổi";
    $("#cancelNewsEdit")?.classList.remove("hidden");

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function updateCounts(counts = {}) {
    if ($("#newsCountAll")) $("#newsCountAll").textContent = numberFormat(counts.all);
    if ($("#newsCountPending")) $("#newsCountPending").textContent = numberFormat(counts.pending);
    if ($("#newsCountApproved")) $("#newsCountApproved").textContent = numberFormat(counts.approved);
    if ($("#newsCountRejected")) $("#newsCountRejected").textContent = numberFormat(counts.rejected);
  }

  function renderTable() {
    const body = $("#newsTableBody");
    if (!body) return;

    if (!newsItems.length) {
      body.innerHTML = `
        <tr>
          <td colspan="6" class="empty">Chưa có bài báo phù hợp với bộ lọc.</td>
        </tr>
      `;
      return;
    }

    body.innerHTML = newsItems.map((item) => {
      const imageUrl = item.image_url || "/static/images/news-doctor.svg";
      const summary = String(item.summary || "");
      const summaryText = summary.length > 145
        ? `${summary.slice(0, 145)}…`
        : summary;

      const approveButton = item.status !== "approved"
        ? `<button class="btn primary" type="button" data-news-action="approve" data-news-id="${item.id}">Duyệt</button>`
        : "";

      const featureButton = item.status === "approved" && !item.is_featured
        ? `<button class="btn" type="button" data-news-action="feature" data-news-id="${item.id}">Nổi bật</button>`
        : "";

      const hideButton = item.status === "approved"
        ? `<button class="btn" type="button" data-news-action="hide" data-news-id="${item.id}">Ẩn</button>`
        : "";

      const rejectButton = item.status !== "rejected"
        ? `<button class="btn danger" type="button" data-news-action="reject" data-news-id="${item.id}">Từ chối</button>`
        : "";

      const pendingButton = ["rejected", "draft"].includes(item.status)
        ? `<button class="btn" type="button" data-news-action="pending" data-news-id="${item.id}">Gửi duyệt lại</button>`
        : "";

      return `
        <tr>
          <td>
            <div class="news-admin-cell">
              <img
                src="${escapeHTML(imageUrl)}"
                alt=""
                loading="lazy"
                onerror="this.onerror=null;this.src='/static/images/news-doctor.svg';"
              >
              <div>
                <b>${escapeHTML(item.title)}</b>
                <small>${escapeHTML(summaryText)}</small>
              </div>
            </div>
          </td>

          <td>
            <b>${escapeHTML(item.source_name)}</b>
            <small>
              <a
                class="admin-source-link"
                href="${escapeHTML(item.source_url)}"
                target="_blank"
                rel="noopener noreferrer"
              >Mở bài gốc ↗</a>
            </small>
          </td>

          <td>
            <span class="badge">${escapeHTML(item.category_label || "Sức khỏe")}</span>
          </td>

          <td>
            <span class="badge ${statusClass(item.status)}">
              ${escapeHTML(statusLabel(item.status))}
            </span>
            ${
              item.rejection_reason
                ? `<small class="danger-text">${escapeHTML(item.rejection_reason)}</small>`
                : ""
            }
          </td>

          <td>
            ${
              item.is_featured
                ? '<span class="badge success">Nổi bật</span>'
                : "-"
            }
          </td>

          <td>
            <div class="actions news-row-actions">
              <button class="btn" type="button" data-news-edit="${item.id}">Sửa</button>
              ${approveButton}
              ${featureButton}
              ${hideButton}
              ${rejectButton}
              ${pendingButton}
              <button class="btn danger" type="button" data-news-action="delete" data-news-id="${item.id}">Xóa</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function loadNews() {
    const status = $("#newsStatusFilter")?.value || "all";
    const category = $("#newsCategoryFilter")?.value || "all";
    const body = $("#newsTableBody");

    if (body) {
      body.innerHTML = '<tr><td colspan="6" class="empty">Đang tải dữ liệu...</td></tr>';
    }

    try {
      const params = new URLSearchParams({ status, category });
      const data = await requestJSON(`/admin/api/news?${params.toString()}`);

      newsItems = Array.isArray(data.items) ? data.items : [];
      updateCounts(data.counts || {});
      renderTable();

      const syncLabel = $("#syncLabel");
      if (syncLabel) {
        syncLabel.textContent = `Đồng bộ ${new Date().toLocaleTimeString(
          "vi-VN",
          { hour: "2-digit", minute: "2-digit" }
        )}`;
      }
    } catch (error) {
      updateCounts({});
      if (body) {
        body.innerHTML = `
          <tr>
            <td colspan="6" class="empty error-empty">
              Không tải được dữ liệu: ${escapeHTML(error.message)}
            </td>
          </tr>
        `;
      }
      toast(error.message, "error");
    }
  }

  async function uploadImageIfNeeded() {
    const input = $("#newsImageFile");
    const file = input?.files?.[0];

    if (!file) {
      return $("#newsImageUrl")?.value || "";
    }

    if (file.size > 5 * 1024 * 1024) {
      throw new Error("Ảnh không được vượt quá 5 MB.");
    }

    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (file.type && !allowedTypes.includes(file.type)) {
      throw new Error("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.");
    }

    const formData = new FormData();
    formData.append("image", file);

    const data = await requestJSON("/admin/api/news/upload-image", {
      method: "POST",
      body: formData
    });

    const imageUrl = data.image_url || "";
    if ($("#newsImageUrl")) $("#newsImageUrl").value = imageUrl;

    return imageUrl;
  }

  $("#newsImageFile")?.addEventListener("change", () => {
    clearObjectUrl();

    const input = $("#newsImageFile");
    const file = input?.files?.[0];

    if (!file) {
      setImagePreview($("#newsImageUrl")?.value || "", "Ảnh đại diện hiện tại");
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast("Ảnh không được vượt quá 5 MB.", "error");
      input.value = "";
      return;
    }

    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (file.type && !allowedTypes.includes(file.type)) {
      toast("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.", "error");
      input.value = "";
      return;
    }

    currentImageObjectUrl = URL.createObjectURL(file);
    setImagePreview(currentImageObjectUrl, file.name);
  });

  $("#removeNewsImage")?.addEventListener("click", () => {
    clearObjectUrl();

    if ($("#newsImageFile")) $("#newsImageFile").value = "";
    if ($("#newsImageUrl")) $("#newsImageUrl").value = "";

    setImagePreview();
  });

  $("#newsForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();

    const id = $("#newsId")?.value.trim() || "";
    const saveButton = $("#saveNewsButton");

    try {
      if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = $("#newsImageFile")?.files?.[0]
          ? "Đang tải ảnh..."
          : "Đang lưu...";
      }

      const imageUrl = await uploadImageIfNeeded();

      const payload = {
        title: $("#newsTitle")?.value || "",
        source_name: $("#newsSourceName")?.value || "",
        category: $("#newsCategory")?.value || "general",
        source_url: $("#newsSourceUrl")?.value || "",
        image_url: imageUrl,
        summary: $("#newsSummary")?.value || ""
      };

      await requestJSON(
        id ? `/admin/api/news/${id}` : "/admin/api/news",
        {
          method: id ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }
      );

      toast(id ? "Đã lưu thay đổi." : "Đã tạo bài chờ duyệt.");
      resetForm();
      await loadNews();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.textContent = $("#newsId")?.value
          ? "Lưu thay đổi"
          : "Tạo bài chờ duyệt";
      }
    }
  });

  $("#cancelNewsEdit")?.addEventListener("click", resetForm);
  $("#refreshNews")?.addEventListener("click", loadNews);
  $("#newsFilters")?.addEventListener("change", loadNews);

  document.addEventListener("click", async (event) => {
    const editButton = event.target.closest("[data-news-edit]");
    if (editButton) {
      const item = newsItems.find(
        (row) => String(row.id) === String(editButton.dataset.newsEdit)
      );
      if (item) fillForm(item);
      return;
    }

    const actionButton = event.target.closest("[data-news-action]");
    if (!actionButton) return;

    const action = actionButton.dataset.newsAction;
    const id = actionButton.dataset.newsId;
    let reason = "";

    if (action === "delete" && !window.confirm("Xóa vĩnh viễn bài báo này?")) return;
    if (action === "approve" && !window.confirm("Duyệt bài này để hiển thị cho người dùng?")) return;
    if (action === "hide" && !window.confirm("Ẩn bài này khỏi Trang chủ?")) return;
    if (action === "feature" && !window.confirm("Đặt bài này làm bài nổi bật?")) return;
    if (action === "pending" && !window.confirm("Chuyển bài về trạng thái chờ duyệt?")) return;

    if (action === "reject") {
      reason = window.prompt("Lý do từ chối (có thể để trống):", "") || "";
      if (!window.confirm("Xác nhận từ chối bài này?")) return;
    }

    try {
      actionButton.disabled = true;

      await requestJSON(`/admin/api/news/${id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason })
      });

      toast("Đã cập nhật bản tin.");
      await loadNews();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      actionButton.disabled = false;
    }
  });

  loadNews();
})();
