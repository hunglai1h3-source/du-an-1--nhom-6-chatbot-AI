"use strict";

(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const modal = $("#premiumModal");
  const openButton = $("#upgradeButton");
  const closeButton = $("#closePremiumModal");
  const actionButton = $("#subscribePremiumButton");
  const orderArea = $("#premiumOrderArea");
  const usageArea = $("#premiumUsageArea");
  const planBadge = $("#accountPlanBadge");
  const priceText = $("#premiumPriceText");

  if (!modal || !actionButton || !orderArea) return;

  let state = null;
  let busy = false;

  const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));

  const money = (value) => new Intl.NumberFormat("vi-VN").format(Number(value || 0)) + "đ";

  async function requestJSON(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      ...options
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Có lỗi xảy ra.");
    return data;
  }

  function showToast(message) {
    const toast = $("#toastMessage");
    if (!toast) {
      alert(message);
      return;
    }
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function openModal() {
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    loadSubscription();
  }

  function closeModal() {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  function renderUsage(data) {
    if (!usageArea) return;
    const chatUsed = Number(data.usage?.chat || 0);
    const imageUsed = Number(data.usage?.image || 0);
    const chatLimit = data.limits?.chat ?? "∞";
    const imageLimit = data.limits?.image ?? "∞";

    usageArea.innerHTML = `
      <div><span>Chat hôm nay</span><strong>${chatUsed}/${chatLimit}</strong></div>
      <div><span>Ảnh hôm nay</span><strong>${imageUsed}/${imageLimit}</strong></div>
    `;
  }

  function renderBankInvoice(order, bank) {
    // Dùng ảnh QR cố định của tài khoản ngân hàng đã đặt trong static/images.
    // Người dùng vẫn cần chuyển đúng số tiền và đúng nội dung hóa đơn hiển thị bên cạnh.
    const qrUrl = "/static/images/payment_qr.png";

    if (!bank.configured) {
      orderArea.innerHTML = `
        <section class="premium-invoice">
          <div class="premium-invoice-head">
            <div>
              <small>MÃ HÓA ĐƠN</small>
              <strong>${escapeHTML(order.invoice_code)}</strong>
            </div>
            <span class="premium-status warning">Chờ cấu hình thanh toán</span>
          </div>
          <dl class="premium-invoice-summary">
            <div><dt>Số tiền</dt><dd>${money(order.amount)}</dd></div>
            <div><dt>Thời hạn</dt><dd>${escapeHTML(order.duration_days)} ngày</dd></div>
          </dl>
          <div class="premium-bank-warning">
            <strong>Chưa thể chuyển khoản</strong>
            <p>Admin chưa cập nhật đầy đủ ngân hàng, số tài khoản, tên chủ tài khoản và BANK_BIN.</p>
          </div>
        </section>
      `;
      actionButton.textContent = "Chưa thể thanh toán";
      actionButton.disabled = true;
      actionButton.dataset.mode = "disabled";
      return;
    }

    orderArea.innerHTML = `
      <section class="premium-invoice">
        <div class="premium-invoice-head">
          <div>
            <small>MÃ HÓA ĐƠN</small>
            <strong>${escapeHTML(order.invoice_code)}</strong>
          </div>
          <span class="premium-status pending">Chờ chuyển khoản</span>
        </div>

        <dl class="premium-invoice-summary">
          <div><dt>Số tiền</dt><dd>${money(order.amount)}</dd></div>
          <div><dt>Thời hạn</dt><dd>${escapeHTML(order.duration_days)} ngày</dd></div>
        </dl>

        <div class="premium-payment-grid">
          <figure class="premium-qr-box">
            <img class="premium-qr" src="${escapeHTML(qrUrl)}" alt="Mã QR chuyển khoản Premium">
            <figcaption>Quét mã QR để mở thông tin tài khoản</figcaption>
          </figure>
          <dl class="premium-bank-details">
            <div><dt>Ngân hàng</dt><dd>${escapeHTML(bank.name)}</dd></div>
            <div><dt>Số tài khoản</dt><dd>${escapeHTML(bank.account_number)}</dd></div>
            <div><dt>Chủ tài khoản</dt><dd>${escapeHTML(bank.account_name)}</dd></div>
            <div><dt>Số tiền</dt><dd>${money(order.amount)}</dd></div>
            <div><dt>Nội dung chuyển khoản</dt><dd class="payment-note">${escapeHTML(order.payment_note)}</dd></div>
          </dl>
        </div>

        <p class="premium-payment-note">
          Mã QR là QR cố định của tài khoản. Hãy kiểm tra đúng số tiền và nhập đúng nội dung hóa đơn trước khi chuyển khoản.
        </p>
      </section>
    `;
    actionButton.textContent = "Tôi đã chuyển khoản";
    actionButton.disabled = false;
    actionButton.dataset.mode = "submit";
    actionButton.dataset.orderId = order.id;
  }

  function renderState(data) {
    state = data;
    priceText.textContent = money(data.price);
    renderUsage(data);

    if (planBadge) {
      planBadge.textContent = data.is_admin ? "Admin" : data.is_premium ? "Premium" : "Free";
      planBadge.classList.toggle("is-premium", Boolean(data.is_premium || data.is_admin));
    }

    if (data.is_premium || data.is_admin) {
      const expiry = data.expires_at
        ? new Date(data.expires_at).toLocaleDateString("vi-VN")
        : "Không giới hạn";
      orderArea.innerHTML = `
        <section class="premium-success-card">
          <span>✓</span>
          <div>
            <strong>${data.is_admin ? "Tài khoản Admin" : "Premium đang hoạt động"}</strong>
            <p>Ngày hết hạn: ${escapeHTML(expiry)}</p>
          </div>
        </section>
      `;
      actionButton.classList.add("hidden");
      return;
    }

    actionButton.classList.remove("hidden");
    const order = data.pending_order;

    if (!order) {
      orderArea.innerHTML = `
        <section class="premium-intro-note">
          <strong>Thanh toán chuyển khoản</strong>
          <p>Hệ thống sẽ tạo một hóa đơn riêng. Premium chỉ được kích hoạt sau khi Admin kiểm tra và xác nhận giao dịch.</p>
        </section>
      `;
      actionButton.textContent = `Tạo hóa đơn ${money(data.price)}`;
      actionButton.disabled = false;
      actionButton.dataset.mode = "create";
      delete actionButton.dataset.orderId;
      return;
    }

    if (order.status === "awaiting_review") {
      orderArea.innerHTML = `
        <section class="premium-awaiting-card">
          <span>⌛</span>
          <div>
            <small>MÃ HÓA ĐƠN</small>
            <strong>${escapeHTML(order.invoice_code)}</strong>
            <p>Yêu cầu đã được gửi. Admin đang đối chiếu giao dịch ngân hàng.</p>
          </div>
        </section>
      `;
      actionButton.textContent = "Đang chờ Admin xác nhận";
      actionButton.disabled = true;
      actionButton.dataset.mode = "disabled";
      return;
    }

    renderBankInvoice(order, data.bank || {});
  }

  async function loadSubscription() {
    orderArea.innerHTML = '<p class="premium-loading">Đang tải thông tin gói...</p>';
    actionButton.disabled = true;
    try {
      const data = await requestJSON("/api/subscription");
      renderState(data);
    } catch (error) {
      orderArea.innerHTML = `
        <div class="premium-bank-warning">
          <strong>Không tải được thông tin Premium</strong>
          <p>${escapeHTML(error.message)}</p>
        </div>
      `;
      actionButton.textContent = "Đăng nhập để nâng cấp";
      actionButton.disabled = false;
      actionButton.dataset.mode = "login";
    }
  }

  async function handleAction() {
    if (busy || actionButton.disabled) return;
    const mode = actionButton.dataset.mode;

    if (mode === "login") {
      closeModal();
      $("#accountButton")?.click();
      return;
    }

    busy = true;
    actionButton.disabled = true;

    try {
      if (mode === "create") {
        await requestJSON("/api/premium/orders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}"
        });
        await loadSubscription();
        showToast("Đã tạo hóa đơn Premium.");
        return;
      }

      if (mode === "submit") {
        const orderId = actionButton.dataset.orderId;
        if (!orderId) throw new Error("Không xác định được hóa đơn.");

        if (!confirm("Bạn xác nhận đã hoàn tất chuyển khoản đúng số tiền và nội dung?")) {
          actionButton.disabled = false;
          return;
        }

        const result = await requestJSON(`/api/premium/orders/${orderId}/submitted`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: "Người dùng xác nhận đã chuyển khoản." })
        });
        showToast(result.message || "Đã gửi yêu cầu xác nhận.");
        await loadSubscription();
      }
    } catch (error) {
      showToast(error.message);
      await loadSubscription();
    } finally {
      busy = false;
    }
  }

  openButton?.addEventListener("click", openModal);
  closeButton?.addEventListener("click", closeModal);
  actionButton.addEventListener("click", handleAction);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });

  // Đồng bộ huy hiệu gói ngay khi trang tải.
  loadSubscription().catch(() => {});
})();
