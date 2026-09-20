/**
 * MEDICARE AI — ADMIN APEX MAXIMUM JAVASCRIPT
 * Full UI + RBAC + Operations + Knowledge V2 + Monitoring + Privacy
 */

(() => {
  "use strict";

  // UTILITIES
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
  const fmt = (n) => new Intl.NumberFormat("vi-VN").format(Number(n || 0));

  const toast = (message, duration = 2600) => {
    const el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("show"), duration);
  };

  async function apiFetch(url, opts = {}) {
    const defaultHeaders = {
      "Accept": "application/json",
      "Cache-Control": "no-store",
    };
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      opts.body = JSON.stringify(opts.body);
      defaultHeaders["Content-Type"] = "application/json";
    }
    const res = await fetch(url, {
      ...opts,
      headers: { ...defaultHeaders, ...(opts.headers || {}) }
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `Lỗi yêu cầu HTTP ${res.status}`);
    }
    return data;
  }

  function setSyncTime(t) {
    const el = $("#syncLabel");
    if (el) el.textContent = "Đồng bộ " + t;
  }

  // ==========================================================================
  // SHELL CONTROLS: THEME, RAIL, COMMAND PALETTE, DROPDOWNS
  // ==========================================================================

  // 1. Theme Toggle
  const savedTheme = localStorage.getItem("admin-theme") || "dark";
  document.documentElement.dataset.theme = savedTheme;

  function toggleTheme() {
    const current = document.documentElement.dataset.theme;
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("admin-theme", next);
    toast(`Đã chuyển sang giao diện ${next === "dark" ? "Tối (Dark)" : "Sáng (Light)"}`);
  }

  $("#themeToggle")?.addEventListener("click", toggleTheme);
  $("#cmdToggleTheme")?.addEventListener("click", () => {
    closeCmdPalette();
    toggleTheme();
  });

  // 2. Collapsible Rail
  const isRailCollapsed = localStorage.getItem("admin_rail_collapsed") === "1";
  if (isRailCollapsed) {
    $("#sidebar")?.classList.add("collapsed");
  }

  $("#railToggleBtn")?.addEventListener("click", () => {
    const sidebar = $("#sidebar");
    if (!sidebar) return;
    const collapsed = sidebar.classList.toggle("collapsed");
    localStorage.setItem("admin_rail_collapsed", collapsed ? "1" : "0");
  });

  // Mobile menu
  $("#menuToggle")?.addEventListener("click", () => {
    $("#sidebar")?.classList.toggle("open");
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#sidebar") && !e.target.closest("#menuToggle")) {
      $("#sidebar")?.classList.remove("open");
    }
  });

  // 3. User Avatar Dropdown
  const userTrigger = $("#userMenuTrigger");
  const userMenu = $("#userDropdownMenu");
  if (userTrigger && userMenu) {
    userTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      userMenu.classList.toggle("hidden");
      userTrigger.setAttribute("aria-expanded", !userMenu.classList.contains("hidden"));
    });
    document.addEventListener("click", () => {
      userMenu.classList.add("hidden");
      userTrigger.setAttribute("aria-expanded", "false");
    });
  }

  // 4. Command Palette (Ctrl+K)
  const cmdModal = $("#cmdPaletteModal");
  const cmdInput = $("#cmdSearchInput");
  const cmdList = $("#cmdList");

  function openCmdPalette() {
    if (!cmdModal) return;
    cmdModal.classList.remove("hidden");
    if (cmdInput) {
      cmdInput.value = "";
      cmdInput.focus();
      filterCmdItems("");
    }
  }

  function closeCmdPalette() {
    if (!cmdModal) return;
    cmdModal.classList.add("hidden");
  }

  function filterCmdItems(query) {
    if (!cmdList) return;
    const q = query.toLowerCase().trim();
    const items = $$(".cmd-item", cmdList);
    items.forEach(item => {
      const text = (item.textContent || "").toLowerCase();
      item.classList.toggle("hidden", q !== "" && !text.includes(q));
    });
  }

  $("#cmdPaletteTrigger")?.addEventListener("click", openCmdPalette);
  cmdInput?.addEventListener("input", (e) => filterCmdItems(e.target.value));

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (cmdModal?.classList.contains("hidden")) {
        openCmdPalette();
      } else {
        closeCmdPalette();
      }
    } else if (e.key === "Escape") {
      closeCmdPalette();
    }
  });

  cmdModal?.addEventListener("click", (e) => {
    if (e.target === cmdModal) closeCmdPalette();
  });

  // ==========================================================================
  // DASHBOARD MODULE
  // ==========================================================================
  let activityChartInstance = null;

  function renderActivityChart(rows) {
    const canvas = $("#activityChart");
    if (!canvas || !window.Chart) return;
    const labels = rows.map(r => String(r.day || "").slice(5));
    const data = {
      labels,
      datasets: [
        {
          label: "Lượt chat AI",
          data: rows.map(r => r.chats || 0),
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
        },
        {
          label: "Người dùng mới",
          data: rows.map(r => r.users || 0),
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.08)",
          fill: true,
          tension: 0.35,
        }
      ]
    };

    if (activityChartInstance) {
      activityChartInstance.data = data;
      activityChartInstance.update();
    } else {
      activityChartInstance = new Chart(canvas, {
        type: "line",
        data,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "bottom" } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
      });
    }
  }

  async function loadDashboard() {
    try {
      const data = await apiFetch("/admin/api/dashboard");
      if (data.stats) {
        Object.entries(data.stats).forEach(([k, v]) => {
          $$(`[data-stat="${k}"]`).forEach(el => {
            el.textContent = k === "avg_latency" ? fmt(v) : fmt(v);
          });
        });
      }
      if (data.server_time) {
        setSyncTime(data.server_time);
        const lastSync = $("#lastSync");
        if (lastSync) lastSync.textContent = data.server_time;
      }
      if (Array.isArray(data.chart)) {
        renderActivityChart(data.chart);
      }
      if (data.ai) {
        const textModel = $("#activeTextModel");
        const visionModel = $("#activeVisionModel");
        const apiConf = $("#apiConfigured");
        if (textModel) textModel.textContent = data.ai.text_model || "--";
        if (visionModel) visionModel.textContent = data.ai.vision_model || "--";
        if (apiConf) {
          apiConf.textContent = data.ai.api_configured ? "Đã thiết lập ✓" : "Chưa có ✗";
          apiConf.className = data.ai.api_configured ? "text-success font-bold" : "text-danger font-bold";
        }
      }
      if (Array.isArray(data.recent_users)) {
        const wrap = $("#recentUsers");
        if (wrap) {
          wrap.innerHTML = data.recent_users.map(u => `
            <div class="spec-row">
              <div class="user-cell">
                <div class="user-avatar">${esc((u.full_name || "U")[0].toUpperCase())}</div>
                <div>
                  <b>${esc(u.full_name)}</b>
                  <small class="muted">${esc(u.email || "")}</small>
                </div>
              </div>
              <span class="role-pill role-${esc(u.role || 'user')}">${esc(u.role || 'user')}</span>
            </div>
          `).join("") || '<div class="table-loading">Chưa có người dùng mới</div>';
        }
      }
      if (Array.isArray(data.recent_chats)) {
        const wrap = $("#recentChats");
        if (wrap) {
          wrap.innerHTML = data.recent_chats.map(c => `
            <div class="spec-row">
              <div>
                <b>${esc(c.full_name || "Khách")}</b>
                <p class="text-xs muted">${esc((c.question || "").slice(0, 60))}...</p>
              </div>
              <span class="badge ${c.status === "success" ? "badge-success" : "badge-danger"}">${esc(c.status || "ok")}</span>
            </div>
          `).join("") || '<div class="table-loading">Chưa có hội thoại</div>';
        }
      }
    } catch (err) {
      console.warn("Dashboard sync error:", err);
    }
  }

  // ==========================================================================
  // USERS & RBAC MODULE
  // ==========================================================================
  let currentUserPage = 1;
  let activeDrawerUserId = null;

  async function loadUsers(page = currentUserPage) {
    currentUserPage = page;
    const form = $("#userFilters");
    const params = new URLSearchParams(form ? new FormData(form) : {});
    params.set("page", page);

    try {
      const data = await apiFetch("/admin/api/users?" + params.toString());
      const totalEl = $("#userTotal");
      if (totalEl) totalEl.textContent = fmt(data.total);

      const syncEl = $("#usersSync");
      if (syncEl && data.server_time) syncEl.textContent = data.server_time;
      setSyncTime(data.server_time || "");

      // Counts per role tab
      if (data.counts) {
        $("#allCount") && ($("#allCount").textContent = fmt(data.counts.all));
        $("#userCount") && ($("#userCount").textContent = fmt(data.counts.user));
        $("#superAdminCount") && ($("#superAdminCount").textContent = fmt(data.counts.super_admin));
        $("#adminCount") && ($("#adminCount").textContent = fmt(data.counts.admin));
        $("#editorCount") && ($("#editorCount").textContent = fmt(data.counts.content_editor));
        $("#reviewerCount") && ($("#reviewerCount").textContent = fmt(data.counts.medical_reviewer));
        $("#supportCount") && ($("#supportCount").textContent = fmt(data.counts.support));
      }

      const tbody = $("#usersBody");
      if (!tbody) return;

      if (!data.items || !data.items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="table-loading">Không tìm thấy tài khoản phù hợp</td></tr>';
        return;
      }

      tbody.innerHTML = data.items.map(u => {
        const initial = esc((u.full_name || "U")[0].toUpperCase());
        const isSelf = Number(u.id) === Number(window.AdminCurrentUser);
        return `
          <tr>
            <td>
              <div class="user-cell">
                <div class="user-avatar">${initial}</div>
                <div>
                  <b>${esc(u.full_name)}</b>
                  <small class="muted font-mono">#${u.id} ${isSelf ? '(Bạn)' : ''}</small>
                </div>
              </div>
            </td>
            <td>
              <b>${esc(u.email || "")}</b><br>
              <small class="muted">${esc(u.phone || "Chưa có SĐT")}</small>
            </td>
            <td>
              <span class="role-pill role-${esc(u.role || 'user')}">${esc(u.role_name || u.role)}</span>
            </td>
            <td>
              <span class="badge ${u.is_active ? 'badge-success' : 'badge-danger'}">
                ${u.is_active ? 'Hoạt động' : 'Đã khóa'}
              </span>
            </td>
            <td>
              <b>${fmt(u.chat_count)}</b> chat<br>
              <small class="muted">${fmt(u.profile_count)} hồ sơ</small>
            </td>
            <td class="font-mono text-xs muted">
              ${esc(u.created_at || "")}
            </td>
            <td class="text-right">
              <div class="table-actions">
                <button type="button" class="btn btn-secondary btn-sm" data-open-drawer="${u.id}">
                  Chi tiết
                </button>
                ${!isSelf ? `
                  <button type="button" class="btn ${u.is_active ? 'btn-danger' : 'btn-secondary'} btn-sm" data-toggle-active="${u.id}">
                    ${u.is_active ? 'Khóa' : 'Mở'}
                  </button>
                ` : ''}
              </div>
            </td>
          </tr>
        `;
      }).join("");

      // Pagination
      renderPagination($("#usersPagination"), data.page, data.pages, loadUsers);
      const pageInfo = $("#paginationInfo");
      if (pageInfo) {
        pageInfo.textContent = `Trang ${data.page} / ${data.pages} (Tổng ${fmt(data.total)} tài khoản)`;
      }
    } catch (err) {
      toast("Lỗi tải danh sách người dùng: " + err.message);
    }
  }

  function renderPagination(container, currentPage, totalPages, callback) {
    if (!container) return;
    if (totalPages <= 1) {
      container.innerHTML = "";
      return;
    }
    const btns = [];
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);

    if (start > 1) {
      btns.push(`<button type="button" data-p="1">1</button>`);
      if (start > 2) btns.push(`<span class="muted" style="padding:4px">...</span>`);
    }
    for (let p = start; p <= end; p++) {
      btns.push(`<button type="button" class="${p === currentPage ? 'active' : ''}" data-p="${p}">${p}</button>`);
    }
    if (end < totalPages) {
      if (end < totalPages - 1) btns.push(`<span class="muted" style="padding:4px">...</span>`);
      btns.push(`<button type="button" data-p="${totalPages}">${totalPages}</button>`);
    }
    container.innerHTML = btns.join("");
    $$("button[data-p]", container).forEach(btn => {
      btn.addEventListener("click", () => callback(Number(btn.dataset.p)));
    });
  }

  // USER DRAWER HANDLERS
  async function openUserDrawer(userId) {
    activeDrawerUserId = userId;
    const backdrop = $("#userDrawerBackdrop");
    if (!backdrop) return;
    backdrop.classList.remove("hidden");

    // Reset drawer state
    switchDrawerTab("profile");
    $("#phiLockedNotice")?.classList.remove("hidden");
    $("#phiDataArea")?.classList.add("hidden");

    try {
      const data = await apiFetch(`/admin/api/users?q=${userId}&per_page=1`);
      const user = (data.items || []).find(u => Number(u.id) === Number(userId));
      if (!user) throw new Error("Không tìm thấy thông tin tài khoản.");

      $("#drawerUserName") && ($("#drawerUserName").textContent = user.full_name || "Người dùng");
      $("#drawerUserId") && ($("#drawerUserId").textContent = `ID: #${user.id}`);
      $("#drawerAvatar") && ($("#drawerAvatar").textContent = (user.full_name || "U")[0].toUpperCase());

      $("#drawerFullName") && ($("#drawerFullName").textContent = user.full_name || "--");
      $("#drawerEmail") && ($("#drawerEmail").textContent = user.email || "--");
      $("#drawerPhone") && ($("#drawerPhone").textContent = user.phone || "Chưa có");
      $("#drawerCreatedAt") && ($("#drawerCreatedAt").textContent = user.created_at || "--");

      const rolePill = $("#drawerRolePill");
      if (rolePill) {
        rolePill.textContent = user.role_name || user.role;
        rolePill.className = `role-pill role-${user.role}`;
      }

      const statusPill = $("#drawerStatusPill");
      if (statusPill) {
        statusPill.innerHTML = `<span class="badge ${user.is_active ? 'badge-success' : 'badge-danger'}">${user.is_active ? 'Hoạt động' : 'Đã khóa'}</span>`;
      }

      $("#drawerChatCount") && ($("#drawerChatCount").textContent = fmt(user.chat_count));
      $("#drawerProfileCount") && ($("#drawerProfileCount").textContent = fmt(user.profile_count));
      $("#drawerLastActivity") && ($("#drawerLastActivity").textContent = user.last_activity || "Chưa có hoạt động");

      const roleSelect = $("#drawerRoleSelect");
      if (roleSelect) roleSelect.value = user.role;

      const toggleBtn = $("#drawerToggleActiveBtn");
      if (toggleBtn) {
        toggleBtn.textContent = user.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản";
        toggleBtn.className = `btn ${user.is_active ? 'btn-danger' : 'btn-primary'}`;
        toggleBtn.disabled = Number(user.id) === Number(window.AdminCurrentUser);
      }
    } catch (err) {
      toast("Lỗi tải chi tiết: " + err.message);
    }
  }

  function closeUserDrawer() {
    $("#userDrawerBackdrop")?.classList.add("hidden");
    activeDrawerUserId = null;
  }

  function switchDrawerTab(tabName) {
    $$(".drawer-tab").forEach(tab => {
      tab.classList.toggle("active", tab.dataset.drawerTab === tabName);
    });
    $$(".drawer-tab-content").forEach(content => {
      content.classList.toggle("active", content.id === `tabContent${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    });
  }

  // ==========================================================================
  // KNOWLEDGE V2 MODULE
  // ==========================================================================
  let currentDocPage = 1;

  async function loadKnowledgeOverview() {
    try {
      const data = await apiFetch("/admin/api/knowledge/overview");
      $("#kTotalDocs") && ($("#kTotalDocs").textContent = fmt(data.total_documents));
      $("#kTotalChunks") && ($("#kTotalChunks").textContent = fmt(data.total_chunks));
      $("#kTotalSources") && ($("#kTotalSources").textContent = fmt(data.total_sources));
      $("#kDrugRecalls") && ($("#kDrugRecalls").textContent = fmt(data.drug_recalls));
    } catch (err) {
      console.warn("Knowledge overview load error:", err);
    }
  }

  async function loadKnowledgeDocs(page = currentDocPage) {
    currentDocPage = page;
    const form = $("#docFilters");
    const params = new URLSearchParams(form ? new FormData(form) : {});
    params.set("page", page);

    try {
      const data = await apiFetch("/admin/api/knowledge/documents?" + params.toString());
      $("#docTotal") && ($("#docTotal").textContent = fmt(data.total));

      const tbody = $("#docsBody");
      if (!tbody) return;

      if (!data.items || !data.items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="table-loading">Không có tài liệu phù hợp</td></tr>';
        return;
      }

      tbody.innerHTML = data.items.map(doc => `
        <tr>
          <td>
            <b>${esc(doc.title)}</b><br>
            <small class="muted font-mono">${esc(doc.document_id)}</small>
          </td>
          <td>
            <span class="tier-badge tier-${esc(doc.trust_tier)}">${esc(doc.trust_tier)}</span>
          </td>
          <td>
            <b>${esc(doc.issuing_authority || doc.publisher || "Chưa rõ")}</b>
          </td>
          <td class="text-xs font-mono">
            ${esc(doc.document_number || "-")}<br>
            <span class="muted">${esc(doc.issue_date || "")}</span>
          </td>
          <td class="font-mono">
            <b>${fmt(doc.total_chunks)}</b>
          </td>
          <td>
            <span class="badge ${doc.review_status === 'APPROVED_OFFICIAL' ? 'badge-success' : doc.review_status === 'REJECTED' ? 'badge-danger' : 'badge-warning'}">
              ${esc(doc.review_status || 'PENDING')}
            </span>
          </td>
          <td class="text-right">
            <button type="button" class="btn btn-secondary btn-sm" data-review-doc="${esc(doc.document_id)}" data-review-title="${esc(doc.title)}" data-current-status="${esc(doc.review_status || '')}">
              Thẩm định
            </button>
          </td>
        </tr>
      `).join("");

      renderPagination($("#docsPagination"), data.page, data.total_pages, loadKnowledgeDocs);
      const pageInfo = $("#docsPaginationInfo");
      if (pageInfo) {
        pageInfo.textContent = `Trang ${data.page} / ${data.total_pages} (Tổng ${fmt(data.total)} tài liệu)`;
      }
    } catch (err) {
      toast("Lỗi tải tài liệu: " + err.message);
    }
  }

  async function loadKnowledgeSources() {
    try {
      const data = await apiFetch("/admin/api/knowledge/sources");
      const tbody = $("#sourcesBody");
      if (!tbody) return;

      tbody.innerHTML = (data.sources || []).map(s => `
        <tr>
          <td class="font-mono font-bold">${esc(s.source_id)}</td>
          <td><b>${esc(s.name)}</b></td>
          <td><span class="tier-badge tier-${esc(s.trust_tier)}">${esc(s.trust_tier)}</span></td>
          <td class="font-mono">${esc(s.trust_weight || "1.0")}</td>
          <td><span class="badge badge-success">Đang kích hoạt</span></td>
        </tr>
      `).join("") || '<tr><td colspan="5" class="table-loading">Chưa có danh bạ nguồn</td></tr>';
    } catch (err) {
      console.warn("Knowledge sources load error:", err);
    }
  }

  // ==========================================================================
  // RAG OPERATIONS MODULE
  // ==========================================================================
  async function loadRagStatus() {
    try {
      const data = await apiFetch("/admin/api/rag/status");
      $("#ragActiveEngine") && ($("#ragActiveEngine").textContent = data.active_engine || "--");
      if (data.v2) {
        $("#ragV2Chunks") && ($("#ragV2Chunks").textContent = fmt(data.v2.chunks));
        $("#ragV2Size") && ($("#ragV2Size").textContent = fmt(data.v2.db_size_mb));
        $("#v2StatusBadge") && ($("#v2StatusBadge").textContent = data.v2.available ? "Khả dụng (Active)" : "Chưa sẵn sàng");
      }
      if (data.v1) {
        $("#ragV1Docs") && ($("#ragV1Docs").textContent = fmt(data.v1.docs));
        $("#ragV1Size") && ($("#ragV1Size").textContent = fmt(data.v1.db_size_mb));
        $("#v1StatusBadge") && ($("#v1StatusBadge").textContent = data.v1.available ? "Sẵn sàng dự phòng" : "Không có");
      }
    } catch (err) {
      console.warn("RAG status load error:", err);
    }
  }

  // ==========================================================================
  // SYSTEM HEALTH MODULE
  // ==========================================================================
  async function loadSystemHealth() {
    try {
      const data = await apiFetch("/admin/api/system/health");
      $("#systemTimestamp") && ($("#systemTimestamp").textContent = data.timestamp || "--:--:--");

      const overallPulse = $("#overallPulse");
      const overallText = $("#overallStatusText");
      if (data.overall === "HEALTHY") {
        if (overallPulse) overallPulse.className = "pulse-indicator";
        if (overallText) overallText.textContent = "Toàn bộ dịch vụ đang hoạt động bình thường (HEALTHY)";
      } else {
        if (overallPulse) overallPulse.className = "pulse-indicator degraded";
        if (overallText) overallText.textContent = "Một số dịch vụ đang hoạt động ở chế độ giảm thiểu (DEGRADED)";
      }

      const s = data.services || {};
      if (s.database) {
        $("#dbLatency") && ($("#dbLatency").textContent = `${s.database.latency_ms || 0} ms`);
        const pool = s.database.pool || {};
        $("#dbPoolStats") && ($("#dbPoolStats").textContent = `Max: ${pool.max_connections || 20} | In Use: ${pool.in_use || 0} | Avail: ${pool.available || 0}`);
        const badge = $("#dbStatusBadge");
        if (badge) {
          badge.textContent = s.database.status;
          badge.className = s.database.status === "HEALTHY" ? "badge badge-success" : "badge badge-danger";
        }
      }

      if (s.ai_provider) {
        $("#aiTextModel") && ($("#aiTextModel").textContent = s.ai_provider.model || "--");
        $("#aiVisionModel") && ($("#aiVisionModel").textContent = s.ai_provider.vision_model || "--");
        const keySt = $("#aiKeyStatus");
        if (keySt) {
          keySt.textContent = s.ai_provider.configured ? "Đã cấu hình ✓" : "Chưa có ✗";
          keySt.className = s.ai_provider.configured ? "text-success font-bold" : "text-danger font-bold";
        }
        const badge = $("#aiStatusBadge");
        if (badge) {
          badge.textContent = s.ai_provider.status;
          badge.className = s.ai_provider.status === "HEALTHY" ? "badge badge-success" : "badge badge-warning";
        }
      }

      if (s.knowledge_v2) {
        $("#knowledgeAvailText") && ($("#knowledgeAvailText").textContent = s.knowledge_v2.available ? "Khả dụng (Read-Only) ✓" : "Chưa kết nối ✗");
        const badge = $("#knowledgeStatusBadge");
        if (badge) {
          badge.textContent = s.knowledge_v2.status;
          badge.className = s.knowledge_v2.status === "HEALTHY" ? "badge badge-success" : "badge badge-warning";
        }
      }

      const env = data.environment || {};
      $("#envGeminiKey") && ($("#envGeminiKey").innerHTML = `<span class="badge ${env.GEMINI_API_KEY?.includes('✓') ? 'badge-success' : 'badge-danger'}">${esc(env.GEMINI_API_KEY)}</span>`);
      $("#envDatabaseUrl") && ($("#envDatabaseUrl").innerHTML = `<span class="badge ${env.DATABASE_URL?.includes('✓') ? 'badge-success' : 'badge-danger'}">${esc(env.DATABASE_URL)}</span>`);
      $("#envSecretKey") && ($("#envSecretKey").innerHTML = `<span class="badge badge-success">${esc(env.SECRET_KEY)}</span>`);
      $("#envFlaskEnv") && ($("#envFlaskEnv").textContent = esc(env.FLASK_ENV || "production"));
    } catch (err) {
      toast("Lỗi tải trạng thái hệ thống: " + err.message);
    }
  }

  // ==========================================================================
  // AUDIT LOGS MODULE
  // ==========================================================================
  let currentAuditPage = 1;

  async function loadAuditLogs(page = currentAuditPage) {
    currentAuditPage = page;
    const form = $("#auditFilters");
    const params = new URLSearchParams(form ? new FormData(form) : {});
    params.set("page", page);

    try {
      const data = await apiFetch("/admin/api/audit-logs?" + params.toString());
      $("#auditTotal") && ($("#auditTotal").textContent = fmt(data.total));

      const tbody = $("#auditBody");
      if (!tbody) return;

      if (!data.logs || !data.logs.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="table-loading">Chưa có nhật ký kiểm toán phù hợp</td></tr>';
        return;
      }

      tbody.innerHTML = data.logs.map(l => `
        <tr>
          <td class="font-mono text-xs muted">${esc(l.created_at)}</td>
          <td>
            <b>${esc(l.admin_name || "Admin")}</b><br>
            <span class="role-pill role-${esc(l.admin_role || 'admin')}">${esc(l.admin_role || 'admin')}</span>
          </td>
          <td>
            <span class="badge badge-neutral font-bold">${esc(l.action)}</span>
          </td>
          <td class="font-mono text-xs">
            ${esc(l.target_type || "-")}: <b>${esc(l.target_id || "-")}</b>
          </td>
          <td class="text-sm" style="max-width: 320px;">
            ${esc(l.details || "-")}
          </td>
          <td>
            <span class="badge ${l.result === 'SUCCESS' ? 'badge-success' : l.result === 'DENIED' ? 'badge-warning' : 'badge-danger'}">
              ${esc(l.result || 'SUCCESS')}
            </span>
          </td>
          <td class="font-mono text-xs muted">
            ${esc((l.request_id || "-").slice(0, 16))}
          </td>
        </tr>
      `).join("");

      renderPagination($("#auditPagination"), data.page, data.total_pages, loadAuditLogs);
      const pageInfo = $("#auditPaginationInfo");
      if (pageInfo) {
        pageInfo.textContent = `Trang ${data.page} / ${data.total_pages} (Tổng ${fmt(data.total)} bản ghi)`;
      }
    } catch (err) {
      console.warn("Audit log load error:", err);
    }
  }

  // ==========================================================================
  // GLOBAL EVENT LISTENERS (DELEGATED)
  // ==========================================================================
  document.addEventListener("click", async (e) => {
    // 1. Open User Drawer
    const openDrawerBtn = e.target.closest("[data-open-drawer]");
    if (openDrawerBtn) {
      openUserDrawer(openDrawerBtn.dataset.openDrawer);
      return;
    }

    // Close User Drawer
    if (e.target.closest("#closeDrawerBtn") || e.target.id === "userDrawerBackdrop") {
      closeUserDrawer();
      return;
    }

    // Drawer Tabs
    const drawerTab = e.target.closest(".drawer-tab");
    if (drawerTab) {
      switchDrawerTab(drawerTab.dataset.drawerTab);
      return;
    }

    // Toggle Active User
    const toggleBtn = e.target.closest("[data-toggle-active]");
    if (toggleBtn) {
      const uid = toggleBtn.dataset.toggleActive;
      if (!confirm("Bạn có chắc chắn muốn thay đổi trạng thái kích hoạt của tài khoản này?")) return;
      try {
        await apiFetch(`/admin/users/${uid}/toggle-active`, { method: "POST" });
        toast("Đã cập nhật trạng thái tài khoản thành công!");
        loadUsers();
        if (activeDrawerUserId) openUserDrawer(activeDrawerUserId);
      } catch (err) {
        toast("Lỗi: " + err.message);
      }
      return;
    }

    // Drawer Toggle Active Button
    if (e.target.closest("#drawerToggleActiveBtn") && activeDrawerUserId) {
      if (!confirm("Xác nhận thay đổi trạng thái của tài khoản này?")) return;
      try {
        await apiFetch(`/admin/users/${activeDrawerUserId}/toggle-active`, { method: "POST" });
        toast("Đã cập nhật trạng thái tài khoản!");
        loadUsers();
        openUserDrawer(activeDrawerUserId);
      } catch (err) {
        toast("Lỗi: " + err.message);
      }
      return;
    }

    // Force Logout User
    if (e.target.closest("#drawerForceLogoutBtn") && activeDrawerUserId) {
      if (!confirm("CẢNH BÁO: Thao tác này sẽ ngay lập tức thu hồi toàn bộ token và phiên đăng nhập của người dùng trên mọi thiết bị. Tiếp tục?")) return;
      try {
        const res = await apiFetch(`/admin/users/${activeDrawerUserId}/force-logout`, { method: "POST" });
        toast(res.message || "Đã thu hồi toàn bộ phiên đăng nhập!");
        loadUsers();
        openUserDrawer(activeDrawerUserId);
      } catch (err) {
        toast("Lỗi: " + err.message);
      }
      return;
    }

    // Save Role Change
    if (e.target.closest("#saveRoleBtn") && activeDrawerUserId) {
      const select = $("#drawerRoleSelect");
      const newRole = select ? select.value : "";
      if (!confirm(`Xác nhận đổi vai trò tài khoản sang "${newRole.toUpperCase()}"?`)) return;
      try {
        await apiFetch(`/admin/users/${activeDrawerUserId}/role`, {
          method: "POST",
          body: { role: newRole }
        });
        toast("Đã thay đổi vai trò tài khoản thành công!");
        loadUsers();
        openUserDrawer(activeDrawerUserId);
      } catch (err) {
        toast("Lỗi đổi quyền: " + err.message);
      }
      return;
    }

    // Request PHI Access in Drawer
    if (e.target.closest("#requestPhiAccessBtn") && activeDrawerUserId) {
      if (!confirm("BẢO VỆ DỮ LIỆU Y TẾ: Yêu cầu giải mã PHI này sẽ ghi nhận danh tính quản trị viên và thời gian vào Nhật ký Kiểm toán (Audit Log). Bạn có chắc chắn muốn tiếp tục?")) return;
      try {
        const html = await (await fetch(`/admin/users/${activeDrawerUserId}?include_sensitive=1`)).text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");
        const phiCard = doc.querySelector(".phi-data-card");
        if (phiCard) {
          $("#phiLockedNotice")?.classList.add("hidden");
          const area = $("#phiDataArea");
          if (area) {
            area.innerHTML = phiCard.innerHTML;
            area.classList.remove("hidden");
          }
          toast("Đã giải mã dữ liệu PHI (Audit Logged)");
        } else {
          toast("Không thể giải mã PHI hoặc tài khoản không có quyền.");
        }
      } catch (err) {
        toast("Lỗi: " + err.message);
      }
      return;
    }

    // Role Tab clicks (Users page)
    const roleTab = e.target.closest("[data-role-tab]");
    if (roleTab) {
      $$("[data-role-tab]").forEach(t => t.classList.remove("active"));
      roleTab.classList.add("active");
      const roleVal = roleTab.dataset.roleTab;
      const roleFilterInput = $("#roleFilter");
      if (roleFilterInput) roleFilterInput.value = roleVal;
      const title = $("#accountListTitle");
      if (title) {
        title.textContent = roleVal ? `Tài khoản ${roleTab.textContent.trim()}` : "Danh sách tất cả tài khoản";
      }
      loadUsers(1);
      return;
    }

    // Knowledge Tabs (docs vs sources)
    const kTab = e.target.closest("#knowledgeTabs [data-tab]");
    if (kTab) {
      $$("#knowledgeTabs [data-tab]").forEach(t => t.classList.remove("active"));
      kTab.classList.add("active");
      const isDocs = kTab.dataset.tab === "docs";
      $("#docsSection")?.classList.toggle("hidden", !isDocs);
      $("#sourcesSection")?.classList.toggle("hidden", isDocs);
      if (!isDocs) loadKnowledgeSources();
      return;
    }

    // Knowledge Review Modal trigger
    const reviewBtn = e.target.closest("[data-review-doc]");
    if (reviewBtn) {
      const docId = reviewBtn.dataset.reviewDoc;
      const title = reviewBtn.dataset.reviewTitle;
      const curStatus = reviewBtn.dataset.currentStatus;

      $("#reviewDocId") && ($("#reviewDocId").value = docId);
      $("#reviewDocTitle") && ($("#reviewDocTitle").textContent = `${docId} - ${title}`);
      $("#reviewStatusSelect") && ($("#reviewStatusSelect").value = curStatus || "APPROVED_OFFICIAL");
      $("#reviewModal")?.classList.remove("hidden");
      return;
    }

    // Close Review Modal
    if (e.target.closest("#closeReviewModalBtn") || e.target.closest("#cancelReviewBtn")) {
      $("#reviewModal")?.classList.add("hidden");
      return;
    }
  });

  // KNOWLEDGE REVIEW SUBMIT
  $("#reviewDocForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const docId = $("#reviewDocId")?.value;
    const reviewStatus = $("#reviewStatusSelect")?.value;
    const notes = $("#reviewNotes")?.value || "";

    try {
      await apiFetch("/admin/api/knowledge/review", {
        method: "POST",
        body: {
          document_id: docId,
          review_status: reviewStatus,
          notes: notes
        }
      });
      toast(`Đã cập nhật thẩm định tài liệu ${docId} thành công!`);
      $("#reviewModal")?.classList.add("hidden");
      loadKnowledgeDocs();
      loadKnowledgeOverview();
    } catch (err) {
      toast("Lỗi thẩm định: " + err.message);
    }
  });

  // ==========================================================================
  // PAGE INITIALIZERS
  // ==========================================================================
  const page = window.AdminPage;

  if (page === "dashboard") {
    try {
      const initChart = JSON.parse($("#initialChart")?.textContent || "[]");
      renderActivityChart(initChart);
    } catch {}
    loadDashboard();
    $("#refreshDashboard")?.addEventListener("click", loadDashboard);
    setInterval(loadDashboard, 5000);
  }

  if (page === "users") {
    loadUsers();
    $("#userFilters")?.addEventListener("submit", (e) => {
      e.preventDefault();
      loadUsers(1);
    });
    $("#refreshUsers")?.addEventListener("click", () => loadUsers(1));
    $("#clearUserFilters")?.addEventListener("click", () => {
      $("#userFilters")?.reset();
      const roleFilterInput = $("#roleFilter");
      if (roleFilterInput) roleFilterInput.value = "";
      $$("[data-role-tab]").forEach(t => t.classList.toggle("active", t.dataset.roleTab === ""));
      loadUsers(1);
    });
    setInterval(() => {
      if (!document.hidden && !activeDrawerUserId) loadUsers(currentUserPage);
    }, 5000);
  }

  if (page === "knowledge") {
    loadKnowledgeOverview();
    loadKnowledgeDocs();
    $("#docFilters")?.addEventListener("submit", (e) => {
      e.preventDefault();
      loadKnowledgeDocs(1);
    });
    $("#refreshDocs")?.addEventListener("click", () => loadKnowledgeDocs(1));
    $("#clearDocFilters")?.addEventListener("click", () => {
      $("#docFilters")?.reset();
      loadKnowledgeDocs(1);
    });
  }

  if (page === "rag") {
    loadRagStatus();
  }

  if (page === "system") {
    loadSystemHealth();
    $("#refreshSystemBtn")?.addEventListener("click", loadSystemHealth);
    setInterval(loadSystemHealth, 5000);
  }

  if (page === "audit") {
    loadAuditLogs();
    $("#auditFilters")?.addEventListener("submit", (e) => {
      e.preventDefault();
      loadAuditLogs(1);
    });
    $("#refreshAudit")?.addEventListener("click", () => loadAuditLogs(1));
    $("#clearAuditFilters")?.addEventListener("click", () => {
      $("#auditFilters")?.reset();
      loadAuditLogs(1);
    });
    setInterval(() => {
      if (!document.hidden) loadAuditLogs(currentAuditPage);
    }, 5000);
  }

  // ==========================================================================
  // FEEDBACK NOTIFICATIONS (PRESERVED & WORKING)
  // ==========================================================================
  (() => {
    const bell = $("#feedbackBell");
    if (!bell) return;

    const badge = $("#feedbackBadge");
    const sideBadge = $("#sideFeedbackBadge");
    const popover = $("#feedbackPopover");
    const list = $("#feedbackPopoverList");
    const summary = $("#feedbackPopoverSummary");
    let previousPending = null;

    function updateCount(count) {
      const n = Number(count || 0);
      [badge, sideBadge].forEach(el => {
        if (!el) return;
        el.textContent = n > 99 ? "99+" : String(n);
        el.classList.toggle("hidden", n <= 0);
      });
      bell.classList.toggle("has-pending", n > 0);
      bell.title = n > 0 ? `${n} đánh giá AI đang chờ xử lý` : "Không có đánh giá AI mới";
      if (summary) summary.textContent = n > 0 ? `${n} đánh giá đang chờ bạn kiểm tra` : "Không có đánh giá mới";
    }

    function renderRecent(items) {
      if (!list) return;
      if (!Array.isArray(items) || !items.length) {
        list.innerHTML = '<div class="feedback-popover-empty">✓ Không có đánh giá nào đang chờ xử lý.</div>';
        return;
      }
      list.innerHTML = items.map(item => {
        const ratingLabel = item.rating === "dislike" ? "👎 Chưa tốt" : "👍 Hữu ích";
        const reason = item.reason_label || item.reason || "Không ghi lý do";
        const user = item.full_name || item.email || "Khách";
        return `
          <a class="feedback-popover-item" href="/admin/feedback?status=pending#feedback-${item.id}">
            <div class="row-top">
              <span class="rating ${esc(item.rating)}">${ratingLabel}</span>
              <time>${esc(item.updated_at || "")}</time>
            </div>
            <b>${esc(user)} · ${esc(reason)}</b>
            <p>${esc(item.feedback_text || item.question || "Đánh giá câu trả lời AI")}</p>
          </a>
        `;
      }).join("");
    }

    async function loadFeedbackNotice(showError = false) {
      try {
        const response = await fetch("/admin/api/feedback-summary", { cache: "no-store", credentials: "same-origin" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không tải được đánh giá.");
        const pending = Number(data.pending || 0);

        if (previousPending !== null && pending > previousPending) {
          toast(`Có ${pending - previousPending} đánh giá AI mới cần xử lý.`);
        }
        previousPending = pending;
        updateCount(pending);
        renderRecent(data.items || []);
      } catch (error) {
        if (showError && summary && list) {
          summary.textContent = "Không tải được thông báo";
          list.innerHTML = `<div class="feedback-popover-empty">${esc(error.message)}</div>`;
        }
      }
    }

    bell.addEventListener("click", async (event) => {
      event.stopPropagation();
      const opening = popover.classList.contains("hidden");
      popover.classList.toggle("hidden", !opening);
      bell.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) await loadFeedbackNotice(true);
    });

    popover?.addEventListener("click", e => e.stopPropagation());
    document.addEventListener("click", () => {
      popover?.classList.add("hidden");
      bell.setAttribute("aria-expanded", "false");
    });

    loadFeedbackNotice(false);
    setInterval(() => loadFeedbackNotice(false), 10000);
  })();

})();
