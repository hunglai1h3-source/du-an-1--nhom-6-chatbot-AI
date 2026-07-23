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
    writeJSON(KEYS.selectedProfile, profile);
    window.dispatchEvent(new CustomEvent("medicare:profile-changed", { detail: profile }));
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
    const selected = theme || localStorage.getItem(KEYS.theme) || "light";
    document.documentElement.dataset.theme = selected;
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
      const message = $("[data-auth-message]", event.currentTarget);
      const body = Object.fromEntries(new FormData(event.currentTarget));
      const response = await fetch("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { message.textContent = data.error || "Đăng nhập thất bại."; return; }
      modal.classList.add("hidden");
      showToast("Đăng nhập thành công.", "success");
      window.dispatchEvent(new CustomEvent("medicare:auth-changed", { detail: data.user }));
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

  async function bindAccountButton(button) {
    if (!button) return { logged_in: false };
    ensureAuthModal();

    const refresh = async () => {
      const data = await currentUser();
      button.dataset.loggedIn = data.logged_in ? "true" : "false";
      const nameNode = $("[data-account-name]", button);
      if (nameNode) {
        nameNode.textContent = data.logged_in ? (data.user?.full_name || "Tài khoản") : "Khách";
      } else {
        button.textContent = data.logged_in ? "⇥ Đăng xuất" : "⇥ Đăng nhập";
      }
      return data;
    };

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const data = await refresh();
      if (!data.logged_in) {
        $("#authModal").classList.remove("hidden");
        return;
      }
      const shouldLogout = confirm(`Bạn đang đăng nhập với tên ${data.user?.full_name || "người dùng"}. Bạn muốn đăng xuất?`);
      if (!shouldLogout) return;
      const response = await fetch("/logout", { method: "POST", credentials: "same-origin" });
      if (!response.ok) {
        showToast("Đăng xuất chưa thành công. Hãy thử lại.", "error");
        return;
      }
      clearPrivateState();
      showToast("Đã đăng xuất.", "success");
      window.dispatchEvent(new CustomEvent("medicare:auth-changed", { detail: null }));
      window.location.assign("/");
    });

    window.addEventListener("medicare:auth-changed", refresh);
    return refresh();
  }

  window.MediCare = {
    KEYS, $, $$, readJSON, writeJSON, escapeHTML, initials,
    getProfiles, saveProfiles, getSelectedProfile, selectProfile, addProfile, syncProfiles, clearPrivateState,
    showToast, applyTheme, toggleTheme, weatherCode, aqiLevel,
    getBestPosition, loadLocationContext, mapsSearchUrl, pharmacyMapUrl, mapsDirectionsUrl,
    currentUser, bindAccountButton
  };

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme();
    $$('[data-action="toggle-theme"]').forEach((button) => button.addEventListener("click", toggleTheme));
  });
})();
