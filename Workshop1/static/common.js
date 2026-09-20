"use strict";

(() => {
  const KEYS = {
    profiles: "medicareFamilyProfilesV4",
    selectedProfile: "medicareSelectedFamilyProfileV4",
    locationContext: "medicareLocationContextV4",
    specialty: "medicareSelectedSpecialtyV4",
    theme: "medicareThemeV4",
    chats: "medicareChatSessionsV4",
    currentChat: "medicareCurrentChatIdV4",
    authUserId: "medicareAuthUserIdV4"
  };

  const guestProfile = {
    id: "guest",
    name: "Khách",
    relationship: "Khách",
    age: "--",
    gender: "Chưa cập nhật",
    height: "",
    weight: "",
    condition: "Chưa cập nhật",
    allergies: "Chưa cập nhật",
    status: "Chưa có hồ sơ"
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      console.warn(`Không thể đọc ${key}`, error);
      return fallback;
    }
  }

  function writeJSON(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[character]));
  }

  function initials(name) {
    return String(name || "TV")
      .trim()
      .split(/\s+/)
      .slice(-2)
      .map((part) => part[0]?.toUpperCase() || "")
      .join("");
  }

  function getProfiles() {
    const saved = readJSON(KEYS.profiles, []);
    return Array.isArray(saved) ? saved : [];
  }

  function saveProfiles(profiles) {
    writeJSON(KEYS.profiles, Array.isArray(profiles) ? profiles : []);
  }

  function getSelectedProfile() {
    const profiles = getProfiles();
    const selected = readJSON(KEYS.selectedProfile, null);
    return profiles.find((profile) => String(profile.id) === String(selected?.id)) || profiles[0] || { ...guestProfile };
  }

  function selectProfile(profileOrId) {
    const profiles = getProfiles();
    const profile = typeof profileOrId === "object"
      ? profileOrId
      : profiles.find((item) => String(item.id) === String(profileOrId));

    if (!profile) {
      localStorage.removeItem(KEYS.selectedProfile);
      return { ...guestProfile };
    }

    const previousSelected = readJSON(KEYS.selectedProfile, null);
    writeJSON(KEYS.selectedProfile, profile);

    // Chỉ phát sự kiện nếu thực sự đổi sang ID hồ sơ khác.
    // Tránh selectProfile -> profile-changed -> switchToProfile -> selectProfile lặp vô hạn.
    const profileChanged =
      String(previousSelected?.id ?? "") !== String(profile.id ?? "");

    if (profileChanged) {
      window.dispatchEvent(
        new CustomEvent("medicare:profile-changed", { detail: profile })
      );
    }

    return profile;
  }
  function mapFamilyMember(member) {
    return {
      id: `family-${member.id}`,
      serverId: member.id,
      name: member.full_name,
      relationship: member.relationship || "Khác",
      age: member.age ?? "--",
      gender: member.gender || "Chưa cập nhật",
      height: member.height_cm ?? "",
      weight: member.weight_kg ?? "",
      condition: member.medical_conditions || "Không",
      allergies: member.allergies || "Không",
      status: member.medical_conditions || "Chưa cập nhật"
    };
  }

  function clearPrivateState() {
    const legacyKeys = [
      KEYS.profiles, KEYS.selectedProfile, KEYS.chats, KEYS.currentChat, KEYS.specialty,
      "medicareFamilyProfilesV1", "medicareFamilyProfilesV2", "medicareFamilyProfilesV3",
      "medicareSelectedFamilyProfileV1", "medicareSelectedFamilyProfileV2", "medicareSelectedFamilyProfileV3",
      "medicareChatSessionsV1", "medicareChatSessionsV2", "medicareChatSessionsV3",
      "medicareCurrentChatIdV1", "medicareCurrentChatIdV2", "medicareCurrentChatIdV3",
      "medicareSelectedSpecialtyV1", "medicareSelectedSpecialtyV2", "medicareSelectedSpecialtyV3"
    ];
    legacyKeys.forEach((key) => localStorage.removeItem(key));
    sessionStorage.removeItem(KEYS.authUserId);
  }

  async function syncProfiles(userData = null) {
    const user = userData?.user || userData;
    if (!user?.id) {
      clearPrivateState();
      return [];
    }

    const previousUserId = sessionStorage.getItem(KEYS.authUserId);
    if (previousUserId && String(previousUserId) !== String(user.id)) clearPrivateState();
    sessionStorage.setItem(KEYS.authUserId, String(user.id));

    const [familyResult, healthResult] = await Promise.allSettled([
      fetch("/api/family", { credentials: "same-origin" }).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không tải được hồ sơ gia đình.");
        return data;
      }),
      fetch("/api/health/profile", { credentials: "same-origin" }).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) return {};
        return data;
      })
    ]);

    const healthData = healthResult.status === "fulfilled" ? healthResult.value : {};
    const profile = healthData.profile || {};
    const genderMap = { male: "Nam", female: "Nữ" };
    const selfProfile = {
      id: `self-${user.id}`,
      name: user.full_name || "Tài khoản của tôi",
      relationship: "Bản thân",
      age: profile.age ?? "--",
      gender: genderMap[profile.sex] || profile.sex || "Chưa cập nhật",
      height: profile.height_cm ?? "",
      weight: healthData.latest_weight_kg ?? "",
      condition: profile.medical_notes || "Không",
      allergies: profile.allergies || "Không",
      status: profile.medical_notes || "Chưa cập nhật"
    };

    const familyMembers = familyResult.status === "fulfilled"
      ? (familyResult.value.members || []).map(mapFamilyMember)
      : [];
    const profiles = [selfProfile, ...familyMembers];
    const previousSelected = readJSON(KEYS.selectedProfile, null);
    saveProfiles(profiles);
    const nextSelected = profiles.find((item) => String(item.id) === String(previousSelected?.id)) || selfProfile;
    writeJSON(KEYS.selectedProfile, nextSelected);
    window.dispatchEvent(new CustomEvent("medicare:profiles-updated", { detail: profiles }));
    window.dispatchEvent(new CustomEvent("medicare:profile-changed", { detail: nextSelected }));
    return profiles;
  }

  async function addProfile(profile) {
    const current = await currentUser();
    if (!current.logged_in) throw new Error("Vui lòng đăng nhập trước khi thêm thành viên.");
    const payload = {
      full_name: String(profile.name || "").trim(),
      relationship: String(profile.relationship || "Khác").trim(),
      age: profile.age === "" ? null : Number(profile.age),
      gender: String(profile.gender || "").trim(),
      height_cm: profile.height === "" ? null : Number(profile.height),
      weight_kg: profile.weight === "" ? null : Number(profile.weight),
      medical_conditions: String(profile.condition || "").trim(),
      allergies: String(profile.allergies || "").trim()
    };
    const response = await fetch("/api/family", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không thể thêm thành viên.");
    await syncProfiles(current.user);
    const created = getProfiles().find((item) => item.serverId === data.member?.id) || getProfiles().at(-1);
    if (created) selectProfile(created);
    return created;
  }

  function showToast(message, kind = "info") {
    let toast = $("#globalToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "globalToast";
      toast.className = "global-toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.dataset.kind = kind;
    toast.classList.add("show");
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove("show"), 3600);
  }

  function applyTheme(theme) {
    const urlTheme = new URLSearchParams(window.location.search).get("theme");
    const selected = theme || urlTheme || localStorage.getItem(KEYS.theme) || "light";
    document.documentElement.dataset.theme = selected;
    document.documentElement.setAttribute("data-theme", selected);
    localStorage.setItem(KEYS.theme, selected);
    $$('[data-action="toggle-theme"]').forEach((button) => {
      button.textContent = selected === "dark" ? "☀" : "☾";
      button.setAttribute("aria-label", selected === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối");
    });
  }

  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  }

  function weatherCode(code) {
    const value = Number(code);
    if (value === 0) return { icon: "☀️", text: "Trời quang" };
    if ([1, 2, 3].includes(value)) return { icon: "⛅", text: "Có mây" };
    if ([45, 48].includes(value)) return { icon: "🌫️", text: "Có sương mù" };
    if ([51, 53, 55, 56, 57].includes(value)) return { icon: "🌦️", text: "Mưa phùn" };
    if ([61, 63, 65, 66, 67, 80, 81, 82].includes(value)) return { icon: "🌧️", text: "Có mưa" };
    if ([95, 96, 99].includes(value)) return { icon: "⛈️", text: "Có dông" };
    return { icon: "🌤️", text: "Thời tiết hiện tại" };
  }

  function aqiLevel(aqi) {
    const value = Number(aqi);
    if (!Number.isFinite(value)) return { text: "Chưa có dữ liệu", key: "unknown" };
    if (value <= 20) return { text: "Tốt", key: "good" };
    if (value <= 40) return { text: "Khá", key: "fair" };
    if (value <= 60) return { text: "Trung bình", key: "moderate" };
    if (value <= 80) return { text: "Kém", key: "poor" };
    if (value <= 100) return { text: "Rất kém", key: "very-poor" };
    return { text: "Cực kỳ kém", key: "extreme" };
  }

  function geolocationErrorMessage(error) {
    if (!error) return "Không thể xác định vị trí.";
    if (error.code === 1) return "Bạn chưa cho phép website truy cập vị trí.";
    if (error.code === 2) return "Thiết bị chưa xác định được vị trí. Hãy bật GPS hoặc Wi-Fi.";
    if (error.code === 3) return "Quá thời gian lấy vị trí. Hãy thử lại ở nơi có tín hiệu tốt hơn.";
    return error.message || "Không thể xác định vị trí.";
  }

  function getBestPosition({ timeoutMs = 20000, targetAccuracy = 25, onProgress } = {}) {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Trình duyệt không hỗ trợ định vị."));
        return;
      }

      let bestPosition = null;
      let watchId = null;
      let finished = false;

      const finish = (error = null) => {
        if (finished) return;
        finished = true;
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        clearTimeout(timer);
        if (bestPosition) resolve(bestPosition);
        else reject(error || new Error("Không lấy được vị trí."));
      };

      const timer = setTimeout(() => finish(new Error("Quá thời gian lấy vị trí.")), timeoutMs);

      watchId = navigator.geolocation.watchPosition(
        (position) => {
          const accuracy = Number(position.coords.accuracy);
          if (!bestPosition || accuracy < Number(bestPosition.coords.accuracy)) {
            bestPosition = position;
            onProgress?.(position);
          }
          if (Number.isFinite(accuracy) && accuracy <= targetAccuracy) finish();
        },
        (error) => {
          if (bestPosition) finish();
          else finish(new Error(geolocationErrorMessage(error)));
        },
        { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 }
      );
    });
  }

  async function loadLocationContext({ force = false, onProgress } = {}) {
    const saved = readJSON(KEYS.locationContext, null);
    const ageMs = saved?.updated_at ? Date.now() - new Date(saved.updated_at).getTime() : Infinity;
    if (!force && saved && ageMs < 5 * 60 * 1000) return saved;

    if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      throw new Error("Định vị chỉ hoạt động trên HTTPS hoặc localhost.");
    }

    const position = await getBestPosition({
      onProgress: (current) => onProgress?.({ stage: "position", position: current })
    });
    const payload = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: position.coords.accuracy,
      force_refresh: Boolean(force)
    };
    onProgress?.({ stage: "loading", position });

    const response = await fetch("/api/location/context", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không thể tải dữ liệu vị trí.");

    const normalized = {
      ...data,
      short_address: data.location?.short_address || "Vị trí hiện tại",
      ...data.environment,
      accuracy_m: data.accuracy_m,
      pharmacies: Array.isArray(data.pharmacies) ? data.pharmacies : []
    };
    writeJSON(KEYS.locationContext, normalized);
    window.dispatchEvent(new CustomEvent("medicare:location-updated", { detail: normalized }));
    return normalized;
  }

  function mapsSearchUrl(context = readJSON(KEYS.locationContext, null)) {
    const query = context?.latitude && context?.longitude
      ? `nhà thuốc gần ${context.latitude},${context.longitude}`
      : "nhà thuốc gần tôi";
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
  }


  function pharmacyMapUrl() {
    return mapsSearchUrl();
  }

  function mapsDirectionsUrl(pharmacy, context = readJSON(KEYS.locationContext, null)) {
    const destination = pharmacy?.latitude && pharmacy?.longitude
      ? `${pharmacy.latitude},${pharmacy.longitude}`
      : pharmacy?.name || "nhà thuốc";
    const params = new URLSearchParams({ api: "1", destination, travelmode: "driving" });
    if (context?.latitude && context?.longitude) {
      params.set("origin", `${context.latitude},${context.longitude}`);
    }
    return `https://www.google.com/maps/dir/?${params}`;
  }

  async function currentUser() {
    try {
      const response = await fetch("/current-user", { credentials: "same-origin" });
      if (!response.ok) return { logged_in: false };
      return await response.json();
    } catch {
      return { logged_in: false };
    }
  }

  function ensureAuthModal() {
    if ($("#authModal")) return;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="shared-modal hidden" id="authModal" role="dialog" aria-modal="true" aria-labelledby="authTitle">
        <div class="shared-modal-card auth-card">
          <button class="shared-modal-close" data-auth-close type="button" aria-label="Đóng">×</button>
          <div class="auth-tabs">
            <button class="active" data-auth-tab="login" type="button">Đăng nhập</button>
            <button data-auth-tab="register" type="button">Đăng ký</button>
          </div>
          <form id="sharedLoginForm" class="auth-form">
            <h2 id="authTitle">Đăng nhập MediCare AI</h2>
            <label>Email hoặc số điện thoại<input name="account" autocomplete="username" required></label>
            <label>Mật khẩu<input name="password" type="password" autocomplete="current-password" required></label>
            <p class="auth-message" data-auth-message></p>
            <button class="auth-submit" type="submit">Đăng nhập</button>
          </form>
          <form id="sharedRegisterForm" class="auth-form hidden">
            <h2>Tạo tài khoản</h2>
            <label>Họ và tên<input name="full_name" required minlength="2"></label>
            <label>Email<input name="email" type="email" required></label>
            <label>Số điện thoại<input name="phone" inputmode="tel"></label>
            <label>Mật khẩu<input name="password" type="password" required minlength="8"></label>
            <label>Xác nhận mật khẩu<input name="confirm_password" type="password" required minlength="8"></label>
            <p class="auth-message" data-auth-message></p>
            <button class="auth-submit" type="submit">Đăng ký</button>
          </form>
        </div>
      </div>`;
    document.body.appendChild(wrapper.firstElementChild);

    const modal = $("#authModal");
    const setTab = (tab) => {
      $$('[data-auth-tab]', modal).forEach((button) => button.classList.toggle("active", button.dataset.authTab === tab));
      $("#sharedLoginForm").classList.toggle("hidden", tab !== "login");
      $("#sharedRegisterForm").classList.toggle("hidden", tab !== "register");
    };
    $$('[data-auth-tab]', modal).forEach((button) => button.addEventListener("click", () => setTab(button.dataset.authTab)));
    $('[data-auth-close]', modal).addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });

    $("#sharedLoginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const message = $("[data-auth-message]", form);
      const submitButton = $("button[type=submit]", form);
      message.textContent = "";
      submitButton.disabled = true;
      submitButton.textContent = "Đang đăng nhập...";

      try {
        const body = Object.fromEntries(new FormData(form));
        const response = await fetch("/login", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Đăng nhập thất bại.");

        modal.classList.add("hidden");
        form.reset();
        showToast("Đăng nhập thành công.", "success");
        window.dispatchEvent(new CustomEvent("medicare:auth-changed", { detail: data.user }));

        const params = new URLSearchParams(window.location.search);
        const next = params.get("next");
        if (next && next.startsWith("/")) {
          window.location.assign(next);
        } else if (data.user?.role === "admin" && params.get("login") === "1") {
          window.location.assign("/admin");
        }
      } catch (error) {
        message.textContent = error.message || "Không thể kết nối máy chủ.";
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Đăng nhập";
      }
    });

    $("#sharedRegisterForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = $("[data-auth-message]", event.currentTarget);
      const body = Object.fromEntries(new FormData(event.currentTarget));
      const response = await fetch("/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { message.textContent = data.error || "Đăng ký thất bại."; return; }
      message.textContent = "Đăng ký thành công. Bạn có thể đăng nhập.";
      setTab("login");
    });
  }

  let accountDropdownEl = null;

  function ensureAccountDropdown() {
    if (accountDropdownEl && document.body.contains(accountDropdownEl)) {
      return accountDropdownEl;
    }
    const existing = $("#accountDropdownMenu");
    if (existing) {
      accountDropdownEl = existing;
      return existing;
    }

    const dropdown = document.createElement("div");
    dropdown.id = "accountDropdownMenu";
    dropdown.className = "account-dropdown-menu";
    dropdown.setAttribute("role", "menu");
    dropdown.setAttribute("aria-hidden", "true");
    dropdown.innerHTML = `
      <div class="account-dropdown-header">
        <span class="account-dropdown-avatar" id="accountMenuAvatar">K</span>
        <div class="account-dropdown-info">
          <strong class="account-dropdown-name" id="accountMenuName">Khách</strong>
          <span class="account-dropdown-email" id="accountMenuEmail">Chưa đăng nhập</span>
          <span class="account-dropdown-badge" id="accountMenuRole">Tài khoản</span>
        </div>
      </div>
      <div class="account-dropdown-menu-list">
        <button type="button" class="account-dropdown-item" id="accountMenuItemSettings">
          <span class="account-item-icon">⚙️</span>
          <span>Tài khoản của tôi</span>
        </button>
        <a href="/suc-khoe-tien-ich#family-health" class="account-dropdown-item" id="accountMenuItemHealth">
          <span class="account-item-icon">🩺</span>
          <span>Hồ sơ sức khỏe gia đình</span>
        </a>
        <button type="button" class="account-dropdown-item danger" id="accountMenuItemLogout">
          <span class="account-item-icon">🚪</span>
          <span>Đăng xuất</span>
        </button>
      </div>
    `;

    document.body.appendChild(dropdown);
    accountDropdownEl = dropdown;

    $("#accountMenuItemSettings", dropdown)?.addEventListener("click", (e) => {
      e.preventDefault();
      closeAccountDropdown();
      openSettings();
    });

    $("#accountMenuItemLogout", dropdown)?.addEventListener("click", async (e) => {
      e.preventDefault();
      closeAccountDropdown();
      await performLogout();
    });

    document.addEventListener("click", (e) => {
      if (!accountDropdownEl || !accountDropdownEl.classList.contains("active")) return;
      if (!accountDropdownEl.contains(e.target) && !e.target.closest("#accountButton")) {
        closeAccountDropdown();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && accountDropdownEl?.classList.contains("active")) {
        closeAccountDropdown();
      }
    });

    return dropdown;
  }

  function openAccountDropdown(anchorEl, userData) {
    const dropdown = ensureAccountDropdown();
    if (!dropdown || !anchorEl) return;

    const user = userData?.user || {};
    const name = user.full_name || "Tài khoản";
    const email = user.email || user.phone || "Đã đăng nhập";
    const initialChar = initials(name);
    const roleText = user.role === "admin" ? "Quản trị viên" : "Thành viên";

    const avatarNode = $("#accountMenuAvatar", dropdown);
    const nameNode = $("#accountMenuName", dropdown);
    const emailNode = $("#accountMenuEmail", dropdown);
    const roleNode = $("#accountMenuRole", dropdown);

    if (avatarNode) avatarNode.textContent = initialChar;
    if (nameNode) nameNode.textContent = name;
    if (emailNode) emailNode.textContent = email;
    if (roleNode) roleNode.textContent = roleText;

    const rect = anchorEl.getBoundingClientRect();
    const dropdownWidth = 290;
    let left = rect.right - dropdownWidth;
    if (left < 16) left = 16;
    if (left + dropdownWidth > window.innerWidth - 16) {
      left = window.innerWidth - dropdownWidth - 16;
    }
    const top = rect.bottom + 8;

    dropdown.style.top = `${top}px`;
    dropdown.style.left = `${left}px`;
    dropdown.classList.add("active");
    dropdown.setAttribute("aria-hidden", "false");
    anchorEl.setAttribute("aria-expanded", "true");
  }

  function closeAccountDropdown() {
    if (accountDropdownEl) {
      accountDropdownEl.classList.remove("active");
      accountDropdownEl.setAttribute("aria-hidden", "true");
    }
    const btn = $("#accountButton");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  async function performLogout() {
    try {
      await fetch("/logout", { method: "POST", credentials: "same-origin" });
    } catch (err) {
      console.warn("Logout fetch failed:", err);
    }
    clearPrivateState();
    showToast("Đã đăng xuất.", "success");
    window.dispatchEvent(new CustomEvent("medicare:auth-changed", { detail: null }));
    window.location.assign("/landing");
  }

  async function bindAccountButton(button) {
    if (!button) return { logged_in: false };
    ensureAuthModal();

    const params = new URLSearchParams(window.location.search);
    if (params.get("login") === "1") {
      $("#authModal").classList.remove("hidden");
    }
    if (params.get("admin_error") === "1") {
      showToast("Tài khoản này chưa có quyền quản trị.", "error");
    }

    const refresh = async () => {
      const data = await currentUser();
      button.dataset.loggedIn = data.logged_in ? "true" : "false";

      const nameNode = $("[data-account-name]", button) || $("#accountName");
      const avatarNode = $("#accountAvatar", button) || $("#accountAvatar");
      const welcomeNode = $("#welcomeName");

      if (data.logged_in && data.user) {
        if (nameNode) nameNode.textContent = data.user.full_name || "Tài khoản";
        if (avatarNode) avatarNode.textContent = initials(data.user.full_name);
        if (welcomeNode) welcomeNode.textContent = data.user.full_name || "Tài khoản";
      } else {
        if (nameNode) nameNode.textContent = "Khách";
        if (avatarNode) avatarNode.textContent = "K";
        if (welcomeNode) welcomeNode.textContent = "Khách";
        if (!nameNode && !avatarNode) {
          button.textContent = "⇥ Đăng nhập";
        }
      }
      return data;
    };

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const data = await currentUser();

      if (!data.logged_in) {
        window.location.assign("/login");
        return;
      }

      if (data.user?.role === "admin" && button.id === "sidebarAuthButton") {
        window.location.assign("/admin");
        return;
      }

      const dropdown = ensureAccountDropdown();
      if (dropdown.classList.contains("active")) {
        closeAccountDropdown();
      } else {
        openAccountDropdown(button, data);
      }
    });

    window.addEventListener("medicare:auth-changed", refresh);
    return refresh();
  }


  function passwordFieldHTML(name, label, autocomplete) {
    return `
      <label class="settings-field">
        <span>${escapeHTML(label)}</span>
        <span class="password-input-wrap">
          <input name="${escapeHTML(name)}" type="password" autocomplete="${escapeHTML(autocomplete)}" required>
          <button type="button" class="password-eye" data-toggle-password aria-label="Hiện mật khẩu" title="Hiện/ẩn mật khẩu">👁</button>
        </span>
      </label>`;
  }

  function ensureSettingsModal() {
    if ($("#settingsModal")) return $("#settingsModal");

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="shared-modal hidden settings-modal settings-page-modal" id="settingsModal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
        <section class="shared-modal-card settings-card settings-page-card">
          <button class="shared-modal-close" data-settings-close type="button" aria-label="Đóng">×</button>
          <header class="settings-header">
            <div>
              <p class="settings-eyebrow">CÀI ĐẶT</p>
              <h2 id="settingsTitle">Cài đặt tài khoản</h2>
              <p>Quản lý tài khoản, bảo mật, quyền riêng tư và dữ liệu cá nhân.</p>
            </div>
          </header>

          <div class="settings-sections">
            <section class="settings-box">
              <h3>Tài khoản</h3>
              <div class="settings-account-summary">
                <span class="settings-avatar" id="settingsAvatar">K</span>
                <div class="settings-account-main">
                  <strong id="settingsAccountName">Khách</strong>
                  <small id="settingsAccountEmail">Chưa đăng nhập</small>
                  <button type="button" class="settings-link-btn" data-avatar-change>Thay đổi ảnh đại diện</button>
                </div>
              </div>
            </section>

            <section class="settings-box">
              <h3>Thông tin tài khoản</h3>
              <form id="settingsAccountForm" class="settings-profile-table">
                <label><span>Họ và tên</span><input name="full_name" maxlength="120" required><em>Sửa</em></label>
                <label><span>Email</span><input name="email" type="email" disabled><em class="muted-edit">Cố định</em></label>
                <label><span>Số điện thoại</span><input name="phone" inputmode="tel" maxlength="20" placeholder="Chưa cập nhật"><em>Sửa</em></label>
                <label><span>Ngày sinh</span><input name="birth_date" type="date"><em>Sửa</em></label>
                <p class="settings-message" data-account-settings-message></p>
                <div class="settings-row-actions"><button class="settings-primary" type="submit">Lưu thay đổi</button></div>
              </form>
            </section>

            <section class="settings-box">
              <h3>Mật khẩu & bảo mật</h3>
              <div class="security-summary-row">
                <span>Mật khẩu</span><b>••••••••••••</b>
                <button type="button" class="settings-secondary" data-open-password>Đổi mật khẩu</button>
              </div>
              <div class="login-session">
                <strong>Phiên đăng nhập</strong>
                <span>Chrome · Windows · Thiết bị hiện tại</span>
              </div>
              <div class="settings-row-actions">
                <button type="button" class="settings-secondary" data-logout-other>Đăng xuất khỏi thiết bị khác</button>
              </div>
            </section>

            <section class="settings-box">
              <h3>Quyền riêng tư</h3>
              <div class="privacy-row"><div><strong>Lưu lịch sử trò chuyện</strong><small>Lưu các cuộc trò chuyện để xem lại.</small></div><label class="switch"><input type="checkbox" data-privacy="save_history"><span></span></label></div>
              <div class="privacy-row"><div><strong>Cho AI sử dụng hồ sơ sức khỏe</strong><small>Dùng hồ sơ đã chọn để cá nhân hóa câu trả lời.</small></div><label class="switch"><input type="checkbox" data-privacy="use_health_profile"><span></span></label></div>
              <div class="privacy-row"><div><strong>Nhận thông báo nhắc lịch</strong><small>Cho phép hiển thị nhắc lịch trên thiết bị.</small></div><label class="switch"><input type="checkbox" data-privacy="reminder_notifications"><span></span></label></div>
            </section>

            <section class="settings-box danger-data-box">
              <h3>Dữ liệu cá nhân</h3>
              <div class="personal-data-actions">
                <button type="button" class="settings-secondary" data-export-data>Xuất dữ liệu của tôi</button>
                <button type="button" class="settings-danger-outline" data-clear-server-chats>Xóa lịch sử trò chuyện</button>
                <button type="button" class="settings-danger" data-delete-account>Xóa tài khoản</button>
              </div>
            </section>
          </div>
        </section>
      </div>

      <div class="shared-modal hidden password-change-modal" id="passwordChangeModal" role="dialog" aria-modal="true" aria-labelledby="passwordChangeTitle">
        <section class="shared-modal-card password-change-card">
          <button class="shared-modal-close" data-password-close type="button" aria-label="Đóng">×</button>
          <h2 id="passwordChangeTitle">Đổi mật khẩu</h2>
          <form id="settingsPasswordForm" class="settings-form">
            ${passwordFieldHTML("current_password", "Mật khẩu hiện tại", "current-password")}
            ${passwordFieldHTML("new_password", "Mật khẩu mới", "new-password")}
            ${passwordFieldHTML("confirm_password", "Xác nhận mật khẩu mới", "new-password")}
            <div class="password-rules">
              <span data-rule-length>✓ Ít nhất 8 ký tự</span>
              <span data-rule-mixed>✓ Có chữ và số</span>
            </div>
            <p class="settings-message" data-password-settings-message></p>
            <div class="password-actions">
              <button type="button" class="settings-secondary" data-password-cancel>Hủy</button>
              <button class="settings-primary" type="submit">Cập nhật mật khẩu</button>
            </div>
          </form>
        </section>
      </div>`;

    document.body.append(...Array.from(wrapper.children));
    const modal = $("#settingsModal");
    const passwordModal = $("#passwordChangeModal");

    const closePassword = () => passwordModal?.classList.add("hidden");
    $("[data-settings-close]", modal)?.addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });
    $("[data-password-close]", passwordModal)?.addEventListener("click", closePassword);
    $("[data-password-cancel]", passwordModal)?.addEventListener("click", closePassword);
    passwordModal?.addEventListener("click", (event) => { if (event.target === passwordModal) closePassword(); });
    $("[data-open-password]", modal)?.addEventListener("click", () => passwordModal?.classList.remove("hidden"));

    $$("[data-toggle-password]", passwordModal).forEach((button) => {
      button.addEventListener("click", () => {
        const input = button.parentElement?.querySelector("input");
        if (!input) return;
        input.type = input.type === "password" ? "text" : "password";
        button.textContent = input.type === "password" ? "👁" : "🙈";
        button.setAttribute("aria-label", input.type === "password" ? "Hiện mật khẩu" : "Ẩn mật khẩu");
      });
    });

    const newPassword = passwordModal?.querySelector('input[name="new_password"]');
    const updateRules = () => {
      const value = newPassword?.value || "";
      const lengthRule = $("[data-rule-length]", passwordModal);
      const mixedRule = $("[data-rule-mixed]", passwordModal);
      lengthRule?.classList.toggle("valid", value.length >= 8);
      mixedRule?.classList.toggle("valid", /[A-Za-zÀ-ỹ]/.test(value) && /\d/.test(value));
    };
    newPassword?.addEventListener("input", updateRules);

    $("#settingsAccountForm", modal)?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const message = $("[data-account-settings-message]", form);
      const submit = $("button[type=submit]", form);
      const body = Object.fromEntries(new FormData(form));
      delete body.email;
      message.textContent = "";
      submit.disabled = true;
      submit.textContent = "Đang lưu...";
      try {
        const response = await fetch("/api/account/profile", {
          method: "PATCH", credentials: "same-origin",
          headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không thể cập nhật tài khoản.");
        message.textContent = data.message || "Đã lưu.";
        message.dataset.kind = "success";
        showToast(message.textContent, "success");
        await fillSettingsAccount();
        window.dispatchEvent(new CustomEvent("medicare:auth-changed", {detail:data.user}));
      } catch (error) {
        message.textContent = error.message; message.dataset.kind = "error";
      } finally {
        submit.disabled = false; submit.textContent = "Lưu thay đổi";
      }
    });

    $("#settingsPasswordForm", passwordModal)?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const message = $("[data-password-settings-message]", form);
      const submit = $("button[type=submit]", form);
      const body = Object.fromEntries(new FormData(form));
      message.textContent = "";
      if (body.new_password.length < 8 || !/[A-Za-zÀ-ỹ]/.test(body.new_password) || !/\d/.test(body.new_password)) {
        message.textContent = "Mật khẩu mới phải có ít nhất 8 ký tự, gồm chữ và số.";
        message.dataset.kind = "error"; return;
      }
      if (body.new_password !== body.confirm_password) {
        message.textContent = "Xác nhận mật khẩu mới không khớp.";
        message.dataset.kind = "error"; return;
      }
      submit.disabled = true; submit.textContent = "Đang cập nhật...";
      try {
        const response = await fetch("/api/account/change-password", {
          method:"POST", credentials:"same-origin",
          headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không thể đổi mật khẩu.");
        form.reset(); updateRules();
        $$("input", form).forEach(input => input.type = "password");
        message.textContent = data.message || "Đổi mật khẩu thành công.";
        message.dataset.kind = "success";
        showToast(message.textContent, "success");
        setTimeout(closePassword, 900);
      } catch (error) {
        message.textContent = error.message; message.dataset.kind = "error";
      } finally {
        submit.disabled = false; submit.textContent = "Cập nhật mật khẩu";
      }
    });

    const privacyKey = "medicarePrivacyV1";
    const defaults = {save_history:true, use_health_profile:true, reminder_notifications:true};
    const loadPrivacy = () => ({...defaults, ...readJSON(privacyKey, {})});
    $$("[data-privacy]", modal).forEach(input => {
      input.checked = !!loadPrivacy()[input.dataset.privacy];
      input.addEventListener("change", () => {
        const prefs = loadPrivacy();
        prefs[input.dataset.privacy] = input.checked;
        writeJSON(privacyKey, prefs);
        showToast("Đã cập nhật quyền riêng tư.", "success");
      });
    });

    $("[data-avatar-change]", modal)?.addEventListener("click", () => {
      showToast("Ảnh đại diện hiện dùng chữ viết tắt. Có thể bổ sung upload ảnh ở bản tiếp theo.");
    });

    $("[data-logout-other]", modal)?.addEventListener("click", () => {
      showToast("Phiên đăng nhập hiện tại được giữ nguyên. Hệ thống hiện chưa lưu nhiều phiên để thu hồi riêng.");
    });

    $("[data-export-data]", modal)?.addEventListener("click", () => {
      window.location.assign("/api/account/export");
    });

    $("[data-clear-server-chats]", modal)?.addEventListener("click", async () => {
      if (!confirm("Bạn chắc chắn muốn xóa toàn bộ lịch sử trò chuyện? Hành động này không thể hoàn tác.")) return;
      try {
        const response = await fetch("/api/account/chat-history", {method:"DELETE", credentials:"same-origin"});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không thể xóa lịch sử.");
        localStorage.removeItem(KEYS.chats); localStorage.removeItem(KEYS.currentChat);
        showToast(data.message || "Đã xóa lịch sử trò chuyện.", "success");
        window.dispatchEvent(new CustomEvent("medicare:chats-cleared"));
      } catch(error) { showToast(error.message, "error"); }
    });

    $("[data-delete-account]", modal)?.addEventListener("click", async () => {
      const typed = prompt('Để xóa tài khoản, nhập chính xác "XOA TAI KHOAN":');
      if (typed !== "XOA TAI KHOAN") return;
      try {
        const response = await fetch("/api/account", {method:"DELETE", credentials:"same-origin"});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Không thể xóa tài khoản.");
        clearPrivateState();
        alert(data.message || "Tài khoản đã được xóa.");
        window.location.assign("/");
      } catch(error) { showToast(error.message, "error"); }
    });

    return modal;
  }

  async function fillSettingsAccount() {
    const modal = ensureSettingsModal();
    const data = await currentUser();
    if (!data.logged_in) return false;
    const user = data.user || {};
    $("#settingsAvatar", modal).textContent = initials(user.full_name || "K");
    $("#settingsAccountName", modal).textContent = user.full_name || "Tài khoản";
    $("#settingsAccountEmail", modal).textContent = user.email || "";
    const form = $("#settingsAccountForm", modal);
    form.elements.full_name.value = user.full_name || "";
    form.elements.email.value = user.email || "";
    form.elements.phone.value = user.phone || "";
    form.elements.birth_date.value = user.birth_date || "";
    return true;
  }

  async function openSettings() {
    const data = await currentUser();
    if (!data.logged_in) {
      ensureAuthModal(); $("#authModal")?.classList.remove("hidden");
      showToast("Vui lòng đăng nhập để mở Cài đặt."); return;
    }
    const modal = ensureSettingsModal();
    await fillSettingsAccount();
    modal.classList.remove("hidden");
  }

  window.MediCare = {
    KEYS, $, $$, readJSON, writeJSON, escapeHTML, initials,
    getProfiles, saveProfiles, getSelectedProfile, selectProfile, addProfile, syncProfiles, clearPrivateState,
    showToast, applyTheme, toggleTheme, weatherCode, aqiLevel,
    getBestPosition, loadLocationContext, mapsSearchUrl, pharmacyMapUrl, mapsDirectionsUrl,
    currentUser, bindAccountButton, openSettings, ensureSettingsModal,
    logout: performLogout, openAccountDropdown, closeAccountDropdown
  };

  function bindSettingsTriggers(root = document) {
    root.querySelectorAll?.('#openSettings, [data-open-settings]').forEach((button) => {
      if (button.dataset.settingsBound === "1") return;
      button.dataset.settingsBound = "1";
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openSettings().catch((error) => {
          console.error("Không thể mở Cài đặt:", error);
          showToast(error?.message || "Không thể mở Cài đặt.", "error");
        });
      });
    });
  }

  window.MediCare.bindSettingsTriggers = bindSettingsTriggers;

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest?.('#openSettings, [data-open-settings]');
    if (!trigger || trigger.dataset.settingsBound === "1") return;
    event.preventDefault();
    openSettings().catch((error) => {
      console.error("Không thể mở Cài đặt:", error);
      showToast(error?.message || "Không thể mở Cài đặt.", "error");
    });
  });

  // ==========================================================================
  // APEX MAXIMUM: GLOBAL COMMAND PALETTE (Ctrl/Cmd + K)
  // ==========================================================================
  const COMMANDS = [
    {
      id: "new-chat",
      title: "Cuộc trò chuyện mới",
      badge: "Tư vấn AI",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
      action: () => {
        if (window.location.pathname === "/tu-van") {
          window.location.href = "/tu-van?reset=1";
        } else {
          window.location.href = "/tu-van";
        }
      }
    },
    {
      id: "home",
      title: "Trung tâm điều hành Sức khỏe (Home)",
      badge: "Hệ điều hành",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
      action: () => { window.location.href = "/"; }
    },
    {
      id: "consult",
      title: "Không gian Tư vấn AI (Medical Workspace)",
      badge: "AI",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>',
      action: () => { window.location.href = "/tu-van"; }
    },
    {
      id: "health-space",
      title: "Hồ sơ sức khỏe, Gia đình & Diễn biến bệnh",
      badge: "Hồ sơ",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
      action: () => { window.location.href = "/suc-khoe-tien-ich"; }
    },
    {
      id: "knowledge",
      title: "Thư viện Kiến thức Y khoa Đã kiểm duyệt",
      badge: "Kiến thức",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
      action: () => { window.location.href = "/kien-thuc"; }
    },
    {
      id: "news",
      title: "Bản tin Sức khỏe Chính thống",
      badge: "Bản tin",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1m2 13a2 2 0 0 1-2-2V7m2 13a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2"/></svg>',
      action: () => { window.location.href = "/ban-tin-suc-khoe"; }
    },
    {
      id: "pharmacy",
      title: "Tìm kiếm Nhà thuốc GPP & Trạm Y tế gần nhất",
      badge: "Bản đồ",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
      action: () => { window.location.href = "/nha-thuoc"; }
    },
    {
      id: "theme",
      title: "Chuyển đổi giao diện Sáng / Tối (Dark / Light Mode)",
      badge: "Giao diện",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>',
      action: () => { toggleTheme(); }
    },
    {
      id: "settings",
      title: "Cài đặt tài khoản & Thông tin y tế",
      badge: "Tài khoản",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
      action: () => { openSettings(); }
    },
    {
      id: "emergency-115",
      title: "Gọi khẩn cấp Cấp cứu 115",
      badge: "Khẩn cấp",
      icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#ef4444" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
      action: () => { window.location.href = "tel:115"; }
    }
  ];

  let cmdBackdrop = null;
  let cmdInput = null;
  let cmdList = null;
  let selectedIndex = 0;
  let filteredCommands = [...COMMANDS];

  function initCommandPalette() {
    if (document.getElementById("cmdPaletteBackdrop")) return;

    cmdBackdrop = document.createElement("div");
    cmdBackdrop.id = "cmdPaletteBackdrop";
    cmdBackdrop.className = "cmd-palette-backdrop";
    cmdBackdrop.setAttribute("role", "dialog");
    cmdBackdrop.setAttribute("aria-modal", "true");
    cmdBackdrop.setAttribute("aria-label", "MediCare Command Palette");

    cmdBackdrop.innerHTML = `
      <div class="cmd-palette-modal">
        <div class="cmd-palette-header">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input type="text" class="cmd-palette-input" id="cmdPaletteInput" placeholder="Tìm kiếm trang, chức năng hoặc hành động (Ctrl+K)..." autocomplete="off" spellcheck="false">
          <kbd class="cmd-palette-kbd">ESC</kbd>
        </div>
        <ul class="cmd-palette-list" id="cmdPaletteList"></ul>
      </div>
    `;

    document.body.appendChild(cmdBackdrop);
    cmdInput = document.getElementById("cmdPaletteInput");
    cmdList = document.getElementById("cmdPaletteList");

    cmdBackdrop.addEventListener("click", (e) => {
      if (e.target === cmdBackdrop) closeCommandPalette();
    });

    cmdInput.addEventListener("input", (e) => {
      filterCommands(e.target.value);
    });

    cmdInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeCommandPalette();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % Math.max(1, filteredCommands.length);
        renderCommandItems();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = (selectedIndex - 1 + filteredCommands.length) % Math.max(1, filteredCommands.length);
        renderCommandItems();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          const action = filteredCommands[selectedIndex].action;
          closeCommandPalette();
          action();
        }
      }
    });

    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        toggleCommandPalette();
      }
    });
  }

  function filterCommands(query) {
    const q = (query || "").toLowerCase().trim();
    if (!q) {
      filteredCommands = [...COMMANDS];
    } else {
      filteredCommands = COMMANDS.filter(cmd => 
        cmd.title.toLowerCase().includes(q) || cmd.badge.toLowerCase().includes(q)
      );
    }
    selectedIndex = 0;
    renderCommandItems();
  }

  function renderCommandItems() {
    if (!cmdList) return;
    cmdList.innerHTML = "";
    if (filteredCommands.length === 0) {
      cmdList.innerHTML = `<li style="padding: 20px; text-align: center; color: var(--text-tertiary);">Không tìm thấy lệnh hoặc trang phù hợp.</li>`;
      return;
    }

    filteredCommands.forEach((cmd, idx) => {
      const li = document.createElement("li");
      li.className = `cmd-palette-item ${idx === selectedIndex ? 'selected' : ''}`;
      li.innerHTML = `
        <div class="cmd-item-left">
          ${cmd.icon}
          <span>${escapeHTML(cmd.title)}</span>
        </div>
        <span class="cmd-badge">${escapeHTML(cmd.badge)}</span>
      `;
      li.addEventListener("click", () => {
        closeCommandPalette();
        cmd.action();
      });
      li.addEventListener("mouseenter", () => {
        selectedIndex = idx;
        renderCommandItems();
      });
      cmdList.appendChild(li);
    });
  }

  function toggleCommandPalette() {
    if (!cmdBackdrop) initCommandPalette();
    if (cmdBackdrop.classList.contains("active")) {
      closeCommandPalette();
    } else {
      openCommandPalette();
    }
  }

  function openCommandPalette() {
    initCommandPalette();
    filteredCommands = [...COMMANDS];
    selectedIndex = 0;
    renderCommandItems();
    cmdBackdrop.classList.add("active");
    if (cmdInput) {
      cmdInput.value = "";
      setTimeout(() => cmdInput.focus(), 50);
    }
  }

  function closeCommandPalette() {
    if (cmdBackdrop) {
      cmdBackdrop.classList.remove("active");
    }
  }

  window.MediCare.openCommandPalette = openCommandPalette;
  window.MediCare.closeCommandPalette = closeCommandPalette;

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme();
    $$('[data-action="toggle-theme"]').forEach((button) => button.addEventListener("click", toggleTheme));
    bindSettingsTriggers(document);
    initCommandPalette();
  });
})();

