"use strict";

const M = window.MediCare;
const $ = M.$;
const $$ = M.$$;

let sessions = [];
let currentChatId = "";
let favoriteOnly = false;
let selectedImage = null;
let selectedImageUrl = "";
let mediaRecorder = null;
let mediaStream = null;
let audioChunks = [];
let isSending = false;

const quickSets = [
  ["🌙 Ho về đêm", "☁ Bụi mịn hôm nay", "💊 Thuốc phù hợp", "🩺 Cần đi khám khi nào?"],
  ["🌡 Sốt nhẹ", "🤧 Dị ứng thời tiết", "🥗 Chế độ ăn phù hợp", "🏥 Chọn chuyên khoa"],
  ["🫁 Khó thở khi vận động", "🧠 Đau đầu kéo dài", "🛌 Khó ngủ", "📋 Tóm tắt triệu chứng"]
];
let quickSetIndex = 0;

function nowTime() {
  return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function currentSession() {
  return sessions.find((session) => String(session.id) === String(currentChatId)) || null;
}

function createSession({ keepExisting = false } = {}) {
  if (keepExisting && currentSession()) return currentSession();
  const profile = M.getSelectedProfile();
  const session = {
    id: `chat-${Date.now()}`,
    title: `Tư vấn cho ${profile.name}`,
    profileId: profile.id,
    favorite: false,
    updatedAt: new Date().toISOString(),
    messages: [{
      role: "assistant",
      content: `Xin chào! Tôi đang hỗ trợ theo hồ sơ của ${profile.name}. Bạn hãy mô tả triệu chứng hoặc câu hỏi sức khỏe cần tư vấn.`,
      time: nowTime()
    }]
  };
  sessions.push(session);
  currentChatId = session.id;
  persistSessions();
  return session;
}

function persistSessions() {
  if (sessions.length > 30) sessions = sessions.slice(-30);
  M.writeJSON(M.KEYS.chats, sessions);
  localStorage.setItem(M.KEYS.currentChat, currentChatId);
}

function ensureSession() {
  return currentSession() || createSession();
}

function profileForSession(session) {
  return M.getProfiles().find((profile) => String(profile.id) === String(session?.profileId)) || M.getSelectedProfile();
}

function renderProfiles() {
  const selected = M.getSelectedProfile();
  const relation = selected.relationship === "Con" ? "Bé" : selected.relationship;
  $("#selectedProfileAvatar").textContent = M.initials(selected.name);
  $("#selectedProfileName").textContent = selected.name;
  $("#sidebarProfileAvatar").textContent = M.initials(selected.name);
  $("#sidebarProfileName").textContent = selected.name;
  $("#sidebarProfileMeta").textContent = `${selected.age} tuổi · ${selected.gender}`;
  $("#sidebarRelationship").textContent = relation;
  $("#rightProfileAvatar").textContent = M.initials(selected.name);
  $("#rightProfileName").textContent = selected.name;
  $("#rightProfileRelationship").textContent = selected.relationship;

  $("#profileContextStrip").innerHTML = [
    `♙ ${selected.gender}, ${selected.age} tuổi`,
    `⚕ ${selected.condition || "Không có bệnh nền"}`,
    `↕ ${selected.height || "--"} cm`,
    `⚖ ${selected.weight || "--"} kg`
  ].map((item) => `<span>${M.escapeHTML(item)}</span>`).join('<b>•</b>');

  $("#profileDetails").innerHTML = `
    <dt>Họ tên</dt><dd>${M.escapeHTML(selected.name)}</dd>
    <dt>Tuổi</dt><dd>${M.escapeHTML(selected.age)}</dd>
    <dt>Giới tính</dt><dd>${M.escapeHTML(selected.gender)}</dd>
    <dt>Bệnh nền</dt><dd>${M.escapeHTML(selected.condition || "Không")}</dd>
    <dt>Chiều cao</dt><dd>${M.escapeHTML(selected.height || "--")} cm</dd>
    <dt>Cân nặng</dt><dd>${M.escapeHTML(selected.weight || "--")} kg</dd>
    <dt>Dị ứng</dt><dd>${M.escapeHTML(selected.allergies || "Không")}</dd>`;

  $("#profileMenu").innerHTML = M.getProfiles().map((profile) => `
    <button class="${profile.id === selected.id ? "selected" : ""}" type="button" data-profile-id="${M.escapeHTML(profile.id)}">
      <span>${M.escapeHTML(M.initials(profile.name))}</span>
      <div><strong>${M.escapeHTML(profile.name)}</strong><small>${M.escapeHTML(profile.age)} tuổi · ${M.escapeHTML(profile.relationship)}</small></div>
    </button>`).join("");

  $$('[data-profile-id]', $("#profileMenu")).forEach((button) => button.addEventListener("click", () => {
    M.selectProfile(button.dataset.profileId);
    const session = ensureSession();
    session.profileId = button.dataset.profileId;
    session.updatedAt = new Date().toISOString();
    persistSessions();
    renderProfiles();
    renderHistory();
    renderEnvironmentAdvice(M.readJSON(M.KEYS.locationContext, null));
    closeMenus();
    M.showToast(`Đã chuyển sang hồ sơ ${M.getSelectedProfile().name}.`, "success");
  }));
}

function formatText(value) {
  const escaped = M.escapeHTML(value);
  return escaped
    .replace(/^###\s+(.+)$/gm, "<strong>$1</strong>")
    .replace(/^[-•]\s+(.+)$/gm, "<div>• $1</div>")
    .replace(/\n/g, "<br>");
}

function renderMessages() {
  const session = ensureSession();
  const list = $("#messageList");
  const profile = profileForSession(session);
  list.innerHTML = session.messages.map((message, index) => {
    const isUser = message.role === "user";
    const avatar = isUser ? M.initials(profile.name) : "🤖";
    return `
      <article class="message-row ${isUser ? "user" : "assistant"}" data-message-index="${index}">
        ${isUser ? "" : `<span class="message-avatar">${avatar}</span>`}
        <div class="message-bubble">
          ${message.imagePreview ? `<img src="${message.imagePreview}" alt="Ảnh người dùng gửi" style="display:block;max-width:240px;max-height:190px;object-fit:cover;border-radius:11px;margin-bottom:9px">` : ""}
          <div>${formatText(message.content)}</div>
          <div class="message-meta"><time>${M.escapeHTML(message.time || "")}</time>${isUser ? "<span>✓✓</span>" : ""}</div>
          ${isUser ? "" : `<div class="message-actions"><button type="button" data-copy-index="${index}">Sao chép</button><button type="button" data-like-index="${index}">${message.liked ? "♥ Đã lưu" : "♡ Lưu"}</button></div>`}
        </div>
        ${isUser ? `<span class="message-avatar">${avatar}</span>` : ""}
      </article>`;
  }).join("");
  list.scrollTop = list.scrollHeight;

  $$('[data-copy-index]').forEach((button) => button.addEventListener("click", async () => {
    const message = session.messages[Number(button.dataset.copyIndex)];
    await navigator.clipboard.writeText(message.content).catch(() => {});
    M.showToast("Đã sao chép câu trả lời.", "success");
  }));
  $$('[data-like-index]').forEach((button) => button.addEventListener("click", () => {
    const message = session.messages[Number(button.dataset.likeIndex)];
    message.liked = !message.liked;
    persistSessions();
    renderMessages();
  }));
}

function renderHistory() {
  const search = $("#historySearch").value.trim().toLowerCase();
  const list = sessions
    .slice()
    .reverse()
    .filter((session) => !favoriteOnly || session.favorite)
    .filter((session) => !search || `${session.title} ${session.messages.map((message) => message.content).join(" ")}`.toLowerCase().includes(search));

  $("#historyList").innerHTML = list.length ? list.map((session) => {
    const firstUser = session.messages.find((message) => message.role === "user")?.content || "Chưa có câu hỏi";
    return `
      <button class="history-item ${String(session.id) === String(currentChatId) ? "active" : ""}" type="button" data-session-id="${session.id}">
        <span class="history-item-icon">💬</span>
        <span><strong>${M.escapeHTML(session.title)}</strong><small>${M.escapeHTML(firstUser)}</small></span>
        <time>${new Date(session.updatedAt || Date.now()).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</time>
        ${session.favorite ? '<span class="favorite">★</span>' : ""}
      </button>`;
  }).join("") : '<p style="padding:18px 8px;color:#7b887f;font-size:12px">Không có cuộc trò chuyện phù hợp.</p>';

  $$('[data-session-id]').forEach((button) => button.addEventListener("click", () => {
    currentChatId = button.dataset.sessionId;
    const session = ensureSession();
    const profile = profileForSession(session);
    M.selectProfile(profile);
    persistSessions();
    renderProfiles();
    renderHistory();
    renderMessages();
  }));
}

function renderQuickPrompts() {
  $("#quickList").innerHTML = quickSets[quickSetIndex].map((text) => `<button type="button">${M.escapeHTML(text)}</button>`).join("");
  $$("button", $("#quickList")).forEach((button) => button.addEventListener("click", () => {
    const label = button.textContent.replace(/^[^\p{L}\p{N}]+/u, "").trim();
    if (/chọn chuyên khoa/i.test(label)) { openSpecialtyModal(); return; }
    $("#chatInput").value = label;
    autoResizeInput();
    $("#chatInput").focus();
  }));
}

function renderSpecialty() {
  const specialty = localStorage.getItem(M.KEYS.specialty) || "";
  $("#specialtyStrip").classList.toggle("hidden", !specialty);
  $("#specialtyName").textContent = specialty;
}


function openSpecialtyModal() {
  $("#specialtyModal").classList.remove("hidden");
}

function closeSpecialtyModal() {
  $("#specialtyModal").classList.add("hidden");
}

function chooseSpecialty(specialty) {
  localStorage.setItem(M.KEYS.specialty, specialty);
  renderSpecialty();
  closeSpecialtyModal();
  M.showToast(`Đã thêm tag chuyên khoa ${specialty}.`, "success");
}

function bindSpecialtyPicker() {
  // Nút chọn chuyên khoa cạnh “Gợi ý nhanh” đã được bỏ khỏi giao diện.
  // Dùng optional chaining để việc thiếu nút này không làm dừng toàn bộ chat.js.
  $("#chooseSpecialtyButton")?.addEventListener("click", openSpecialtyModal);
  $("#openSpecialtyNav")?.addEventListener("click", (event) => { event.preventDefault(); openSpecialtyModal(); });
  $("#closeSpecialtyModal")?.addEventListener("click", closeSpecialtyModal);
  $("#specialtyModal")?.addEventListener("click", (event) => { if (event.target.id === "specialtyModal") closeSpecialtyModal(); });
  $$('[data-choose-specialty]').forEach((button) => button.addEventListener("click", () => chooseSpecialty(button.dataset.chooseSpecialty)));
  const params = new URLSearchParams(window.location.search);
  const prompt = params.get("prompt");
  if (prompt) {
    $("#chatInput").value = prompt.slice(0, 4000);
    autoResizeInput();
    $("#chatInput").focus();
  }
  if (params.get("openSpecialty") === "1") openSpecialtyModal();
  if (prompt || params.get("openSpecialty") === "1") history.replaceState({}, "", "/tu-van");
}

function renderEnvironmentAdvice(context) {
  const list = $("#environmentAdvice");
  const profile = M.getSelectedProfile();
  const items = [];
  const aqi = Number(context?.aqi);
  const temp = Number(context?.temperature);
  if (Number.isFinite(aqi) && aqi > 60) items.push("Hạn chế ở ngoài trời lâu và cân nhắc khẩu trang lọc bụi.");
  else if (Number.isFinite(aqi)) items.push("Có thể hoạt động ngoài trời vừa phải; theo dõi AQI nếu ở ngoài lâu.");
  if (/hen|hô hấp/i.test(profile.condition || "")) items.push(`Với ${profile.name}: tránh khói, bụi và theo dõi ho hoặc khó thở.`);
  if (Number.isFinite(temp) && temp >= 35) items.push("Tránh nắng gắt, bổ sung nước và nghỉ ở nơi thoáng mát.");
  if (!items.length) items.push("Làm mới vị trí để nhận khuyến nghị phù hợp.");
  list.innerHTML = items.slice(0, 3).map((item) => `<li>${M.escapeHTML(item)}</li>`).join("");
}

function renderPharmacies(context) {
  const frame = $("#googlePharmacyMap");
  if (!frame) return;

  const latitude = Number(context?.latitude);
  const longitude = Number(context?.longitude);
  const query = Number.isFinite(latitude) && Number.isFinite(longitude)
    ? `nhà thuốc gần ${latitude},${longitude}`
    : "nhà thuốc gần tôi";

  frame.src = `https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;
}

function renderLocation(context) {
  if (!context) return;
  const weather = M.weatherCode(context.weather_code);
  const level = M.aqiLevel(context.aqi);
  $("#locationName").textContent = context.short_address || "Vị trí hiện tại";
  $("#weatherIcon").textContent = weather.icon;
  $("#weatherText").textContent = weather.text;
  $("#temperatureValue").textContent = Number.isFinite(Number(context.temperature)) ? `${Math.round(context.temperature)}°C` : "--°C";
  $("#aqiValue").textContent = Number.isFinite(Number(context.aqi)) ? Math.round(context.aqi) : "--";
  $("#aqiLevel").textContent = level.text;
  $("#pm25Value").textContent = Number.isFinite(Number(context.pm25)) ? Number(context.pm25).toFixed(1) : "--";
  $("#locationAccuracy").textContent = Number.isFinite(Number(context.accuracy_m))
    ? `Độ chính xác thiết bị khoảng ±${Math.round(context.accuracy_m)} m · cập nhật ${new Date(context.updated_at || Date.now()).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`
    : "Vị trí lấy từ thiết bị.";
  const warnings = Array.isArray(context.warnings) ? context.warnings.filter(Boolean) : [];
  const warningElement = $("#locationServiceWarning");
  if (warnings.length) {
    warningElement.textContent = warnings.join(" · ");
    warningElement.classList.remove("hidden");
  } else {
    warningElement.textContent = "";
    warningElement.classList.add("hidden");
  }
  renderEnvironmentAdvice(context);
  renderPharmacies(context);
}

async function refreshLocation(force = true) {
  const refreshButton = $("#refreshLocationButton");
  const useButton = $("#useCurrentLocationButton");
  [refreshButton, useButton].filter(Boolean).forEach((button) => { button.disabled = true; });
  refreshButton.textContent = "…";
  useButton.textContent = "Đang định vị...";
  try {
    const context = await M.loadLocationContext({
      force,
      onProgress: ({ stage, position }) => {
        if (stage === "position") $("#locationAccuracy").textContent = `Đang tối ưu độ chính xác: ±${Math.round(position.coords.accuracy)} m`;
        else $("#locationAccuracy").textContent = "Đang tải địa chỉ, thời tiết, cảnh báo và nhà thuốc...";
      }
    });
    renderLocation(context);
    M.showToast("Đã cập nhật vị trí và dữ liệu môi trường.", "success");
  } catch (error) {
    $("#locationAccuracy").textContent = error.message;
    const warningElement = $("#locationServiceWarning");
    warningElement.textContent = error.message.includes("cho phép")
      ? "Hãy bấm biểu tượng ổ khóa bên trái thanh địa chỉ → Vị trí → Cho phép, sau đó thử lại."
      : "Bạn có thể bật GPS/Wi-Fi hoặc mở Google Maps để kiểm tra vị trí rồi thử lại.";
    warningElement.classList.remove("hidden");
    M.showToast(error.message, "error");
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "↻";
    useButton.disabled = false;
    useButton.textContent = "📍 Dùng vị trí hiện tại";
  }
}

function openCurrentLocationMap() {
  const context = M.readJSON(M.KEYS.locationContext, null);
  if (!context?.latitude || !context?.longitude) {
    M.showToast("Chưa có tọa độ. Hãy bấm Dùng vị trí hiện tại trước.", "error");
    return;
  }
  const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${context.latitude},${context.longitude}`)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function askAboutCurrentEnvironment() {
  const context = M.readJSON(M.KEYS.locationContext, null);
  if (!context) {
    M.showToast("Hãy cập nhật vị trí trước khi hỏi AI.", "error");
    return;
  }
  const profile = M.getSelectedProfile();
  const prompt = `Với ${profile.name}, chỉ số AQI hiện tại là ${context.aqi ?? "chưa rõ"}, PM2.5 là ${context.pm25 ?? "chưa rõ"} µg/m³, nhiệt độ ${context.temperature ?? "chưa rõ"}°C tại ${context.short_address || "vị trí hiện tại"}. Hãy đưa ra khuyến nghị bảo vệ sức khỏe ngắn gọn, có lưu ý theo bệnh nền và dị ứng trong hồ sơ.`;
  $("#chatInput").value = prompt.slice(0, 4000);
  autoResizeInput();
  $("#chatInput").focus();
}

function addTyping() {
  const row = document.createElement("article");
  row.className = "message-row assistant";
  row.id = "typingRow";
  row.innerHTML = '<span class="message-avatar">🤖</span><div class="message-bubble"><div class="typing-dots"><i></i><i></i><i></i></div></div>';
  $("#messageList").appendChild(row);
  $("#messageList").scrollTop = $("#messageList").scrollHeight;
}

function removeTyping() {
  $("#typingRow")?.remove();
}

function autoResizeInput() {
  const input = $("#chatInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

async function sendMessage(event) {
  event?.preventDefault();
  if (isSending) return;
  const input = $("#chatInput");
  const text = input.value.trim();
  if (!text && !selectedImage) { M.showToast("Hãy nhập câu hỏi hoặc chọn ảnh."); return; }

  isSending = true;
  $("#sendButton").disabled = true;
  const session = ensureSession();
  const previousHistory = session.messages.map(({ role, content }) => ({ role, content })).slice(-12);
  const imageForDisplay = selectedImageUrl;
  session.messages.push({ role: "user", content: text || "Hãy phân tích ảnh này.", time: nowTime(), imagePreview: imageForDisplay });
  if (session.messages.filter((message) => message.role === "user").length === 1) {
    session.title = (text || "Phân tích hình ảnh").slice(0, 55);
  }
  session.profileId = M.getSelectedProfile().id;
  session.updatedAt = new Date().toISOString();
  persistSessions();
  renderMessages();
  renderHistory();
  input.value = "";
  autoResizeInput();
  addTyping();

  const formData = new FormData();
  formData.append("message", text);
  formData.append("history", JSON.stringify(previousHistory));
  formData.append("selected_profile", JSON.stringify(M.getSelectedProfile()));
  const environment = M.readJSON(M.KEYS.locationContext, null);
  if (environment) formData.append("environment", JSON.stringify(environment));
  const specialty = localStorage.getItem(M.KEYS.specialty) || "";
  if (specialty) formData.append("specialty", specialty);
  if (selectedImage) formData.append("image", selectedImage);

  clearSelectedImage(false);
  try {
    const response = await fetch("/chat", { method: "POST", body: formData, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "AI chưa thể phản hồi.");
    session.messages.push({ role: "assistant", content: data.reply, time: nowTime() });
  } catch (error) {
    session.messages.push({ role: "assistant", content: `Xin lỗi, hệ thống gặp lỗi: ${error.message}`, time: nowTime(), error: true });
  } finally {
    removeTyping();
    session.updatedAt = new Date().toISOString();
    persistSessions();
    renderMessages();
    renderHistory();
    isSending = false;
    $("#sendButton").disabled = false;
  }
}

function selectImage(file) {
  if (!file) return;
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) { M.showToast("Chỉ hỗ trợ JPG, PNG hoặc WEBP.", "error"); return; }
  if (file.size > 5 * 1024 * 1024) { M.showToast("Ảnh vượt quá 5 MB.", "error"); return; }
  clearSelectedImage(false);
  selectedImage = file;
  selectedImageUrl = URL.createObjectURL(file);
  $("#imagePreviewThumb").src = selectedImageUrl;
  $("#imagePreviewName").textContent = file.name;
  $("#imagePreview").classList.remove("hidden");
}

function clearSelectedImage(revoke = true) {
  if (revoke && selectedImageUrl) URL.revokeObjectURL(selectedImageUrl);
  selectedImage = null;
  selectedImageUrl = "";
  $("#imageInput").value = "";
  $("#imagePreview").classList.add("hidden");
}

function setVoiceStatus(message = "", error = false) {
  const node = $("#voiceStatus");
  node.textContent = message;
  node.classList.toggle("hidden", !message);
  node.classList.toggle("error", error);
}

async function toggleVoice() {
  const button = $("#voiceButton");
  if (mediaRecorder?.state === "recording") { mediaRecorder.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setVoiceStatus("Trình duyệt chưa hỗ trợ ghi âm.", true); return; }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    audioChunks = [];
    const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
    const mimeType = mimeCandidates.find((item) => MediaRecorder.isTypeSupported(item));
    mediaRecorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);
    mediaRecorder.addEventListener("dataavailable", (event) => { if (event.data.size) audioChunks.push(event.data); });
    mediaRecorder.addEventListener("stop", transcribeVoice, { once: true });
    mediaRecorder.start(250);
    button.classList.add("recording");
    button.textContent = "■";
    setVoiceStatus("Đang ghi âm — bấm lại để dừng.");
  } catch (error) {
    setVoiceStatus("Không thể dùng micro. Hãy kiểm tra quyền truy cập.", true);
  }
}

async function transcribeVoice() {
  const button = $("#voiceButton");
  button.classList.remove("recording");
  button.textContent = "🎙";
  mediaStream?.getTracks().forEach((track) => track.stop());
  const blob = new Blob(audioChunks, { type: mediaRecorder?.mimeType || "audio/webm" });
  if (!blob.size) { setVoiceStatus("Không thu được âm thanh.", true); return; }
  setVoiceStatus("Đang chuyển giọng nói thành chữ...");
  const extension = blob.type.includes("ogg") ? "ogg" : "webm";
  const formData = new FormData();
  formData.append("audio", new File([blob], `voice.${extension}`, { type: blob.type }));
  try {
    const response = await fetch("/transcribe", { method: "POST", body: formData, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không nhận dạng được giọng nói.");
    const input = $("#chatInput");
    input.value = `${input.value.trim()} ${data.text}`.trim();
    autoResizeInput();
    input.focus();
    setVoiceStatus("Đã chuyển thành chữ. Hãy kiểm tra trước khi gửi.");
    setTimeout(() => setVoiceStatus(""), 3500);
  } catch (error) {
    setVoiceStatus(error.message, true);
  }
}

function closeMenus() {
  $("#profileMenu").classList.add("hidden");
  $("#moreMenu").classList.add("hidden");
  $("#profileControl").setAttribute("aria-expanded", "false");
}

function exportCurrentChat() {
  const session = ensureSession();
  const content = [session.title, "", ...session.messages.map((message) => `${message.role === "user" ? "Người dùng" : "MediCare AI"} (${message.time}):\n${message.content}\n`)].join("\n");
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `medicare-${session.id}.txt`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function bindChatActions() {
  $$('[data-chat-action]').forEach((button) => button.addEventListener("click", () => {
    const action = button.dataset.chatAction;
    const session = ensureSession();
    if (action === "export") exportCurrentChat();
    if (action === "clear") {
      session.messages = [];
      session.updatedAt = new Date().toISOString();
      persistSessions(); renderMessages(); renderHistory();
    }
    if (action === "delete") {
      sessions = sessions.filter((item) => item.id !== session.id);
      currentChatId = "";
      createSession(); renderMessages(); renderHistory();
    }
    closeMenus();
  }));
}


async function openHealthProfileModal() {
  const current = await M.currentUser();
  if (!current.logged_in) {
    $("#accountButton")?.click();
    return;
  }

  const modal = $("#healthProfileModal");
  const message = $("#healthProfileMessage");
  message.textContent = "Đang tải hồ sơ...";
  modal.classList.remove("hidden");

  try {
    const response = await fetch("/api/health/profile", { credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không tải được hồ sơ.");
    const profile = data.profile || {};
    $("#healthSex").value = profile.sex || "";
    $("#healthAge").value = profile.age || "";
    $("#healthHeight").value = profile.height_cm || "";
    $("#healthWeight").value = data.latest_weight_kg || "";
    $("#healthActivity").value = profile.activity_level || "sedentary";
    $("#healthGoal").value = profile.goal || "maintain";
    $("#healthAllergies").value = profile.allergies || "";
    $("#healthConditions").value = profile.medical_notes || "";
    message.textContent = "";
  } catch (error) {
    message.textContent = error.message;
  }
}

function bindHealthProfileModal() {
  const modal = $("#healthProfileModal");
  const form = $("#healthProfileForm");
  if (!modal || !form) return;

  const close = () => modal.classList.add("hidden");
  $("#closeHealthProfileModal")?.addEventListener("click", close);
  modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
  $("#editSelfHealthButton")?.addEventListener("click", openHealthProfileModal);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = $("#healthProfileMessage");
    const submitButton = form.querySelector('button[type="submit"]');
    try {
      submitButton.disabled = true;
      submitButton.textContent = "Đang lưu...";
      const profilePayload = {
        sex: $("#healthSex").value,
        age: Number($("#healthAge").value),
        height_cm: Number($("#healthHeight").value),
        activity_level: $("#healthActivity").value,
        goal: $("#healthGoal").value,
        diet_preference: "",
        allergies: $("#healthAllergies").value.trim(),
        medical_notes: $("#healthConditions").value.trim()
      };
      const profileResponse = await fetch("/api/health/profile", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profilePayload)
      });
      const profileData = await profileResponse.json().catch(() => ({}));
      if (!profileResponse.ok) throw new Error(profileData.error || "Không thể cập nhật hồ sơ.");

      const weightResponse = await fetch("/api/health/weight", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          weight_kg: Number($("#healthWeight").value),
          note: "Cập nhật từ hồ sơ sức khỏe"
        })
      });
      const weightData = await weightResponse.json().catch(() => ({}));
      if (!weightResponse.ok) throw new Error(weightData.error || "Không thể cập nhật cân nặng.");

      const current = await M.currentUser();
      if (current.logged_in) await M.syncProfiles(current.user);
      renderProfiles();
      message.textContent = "Đã cập nhật hồ sơ thành công.";
      M.showToast("Đã cập nhật hồ sơ sức khỏe.", "success");
      setTimeout(close, 650);
    } catch (error) {
      message.textContent = error.message;
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Lưu hồ sơ";
    }
  });
}

async function initializeAccount() {
  const data = await M.bindAccountButton($("#accountButton"));
  if (data?.logged_in) {
    await M.syncProfiles(data.user);
    $("#accountName").textContent = data.user.full_name;
    $("#accountAvatar").textContent = M.initials(data.user.full_name);
  } else {
    M.clearPrivateState();
    $("#accountName").textContent = "Khách";
    $("#accountAvatar").textContent = "K";
  }
  return data;
}

async function initialize() {
  bindHealthProfileModal();
  await initializeAccount();
  sessions = M.readJSON(M.KEYS.chats, []);
  currentChatId = localStorage.getItem(M.KEYS.currentChat) || "";
  ensureSession();
  renderProfiles();
  renderHistory();
  renderMessages();
  renderQuickPrompts();
  renderSpecialty();
  const promptFromUrl = new URLSearchParams(window.location.search).get("prompt");
  if (promptFromUrl) {
    $("#chatInput").value = promptFromUrl.slice(0, 4000);
    autoResizeInput();
    history.replaceState({}, "", "/tu-van");
  }
  const savedLocation = M.readJSON(M.KEYS.locationContext, null);
  if (savedLocation) {
    renderLocation(savedLocation);
    const ageMs = savedLocation.updated_at ? Date.now() - new Date(savedLocation.updated_at).getTime() : Infinity;
    if ((!savedLocation.latitude || !savedLocation.longitude) || ageMs > 10 * 60 * 1000) refreshLocation(true);
  } else {
    $("#locationAccuracy").textContent = "Bấm “Dùng vị trí hiện tại” để tải thời tiết, cảnh báo và nhà thuốc gần bạn.";
  }

  $("#newChatButton").addEventListener("click", () => { createSession(); renderHistory(); renderMessages(); });
  $("#historySearch").addEventListener("input", renderHistory);
  $("#favoriteFilterButton").addEventListener("click", (event) => { favoriteOnly = !favoriteOnly; event.currentTarget.classList.toggle("active", favoriteOnly); event.currentTarget.textContent = favoriteOnly ? "★" : "☆"; renderHistory(); });
  $("#clearAllHistoryButton").addEventListener("click", () => { if (!confirm("Xóa toàn bộ lịch sử chat trên thiết bị?")) return; sessions = []; currentChatId = ""; createSession(); renderHistory(); renderMessages(); });
  $("#profileControl").addEventListener("click", (event) => { event.stopPropagation(); const menu = $("#profileMenu"); menu.classList.toggle("hidden"); $("#moreMenu").classList.add("hidden"); event.currentTarget.setAttribute("aria-expanded", String(!menu.classList.contains("hidden"))); });
  $("#changeProfileButton").addEventListener("click", () => $("#profileControl").click());
  $("#contextChangeProfileButton").addEventListener("click", () => $("#profileControl").click());
  $("#headerChangeProfileButton")?.addEventListener("click", () => $("#profileControl").click());
  $("#moreButton").addEventListener("click", (event) => { event.stopPropagation(); $("#moreMenu").classList.toggle("hidden"); $("#profileMenu").classList.add("hidden"); });
  document.addEventListener("click", closeMenus);
  bindChatActions();
  bindSpecialtyPicker();
  if (new URLSearchParams(window.location.search).get("editProfile") === "1") {
    await openHealthProfileModal();
    history.replaceState({}, "", "/tu-van");
  }
  $("#refreshQuickButton").addEventListener("click", () => { quickSetIndex = (quickSetIndex + 1) % quickSets.length; renderQuickPrompts(); });
  $("#removeSpecialtyButton").addEventListener("click", () => { localStorage.removeItem(M.KEYS.specialty); renderSpecialty(); });
  $("#chatForm")?.addEventListener("submit", sendMessage);
  $("#chatInput")?.addEventListener("input", autoResizeInput);
  $("#chatInput")?.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } });

  const imageInput = $("#imageInput");
  $("#attachImageButton")?.addEventListener("click", (event) => {
    event.preventDefault();
    if (!imageInput) {
      M.showToast("Không tìm thấy ô chọn ảnh trên trang.", "error");
      return;
    }
    // Cho phép chọn lại đúng file vừa chọn trước đó.
    imageInput.value = "";
    imageInput.click();
  });
  imageInput?.addEventListener("change", (event) => selectImage(event.target.files?.[0]));
  $("#removeImageButton")?.addEventListener("click", () => clearSelectedImage());
  $("#voiceButton")?.addEventListener("click", (event) => {
    event.preventDefault();
    toggleVoice();
  });
  $("#refreshLocationButton").addEventListener("click", () => refreshLocation(true));
  $("#useCurrentLocationButton").addEventListener("click", () => refreshLocation(true));
  $("#openLocationMapButton").addEventListener("click", openCurrentLocationMap);
  $("#askEnvironmentButton").addEventListener("click", askAboutCurrentEnvironment);
  $("#viewAllPharmaciesButton").addEventListener("click", () => window.open(M.mapsSearchUrl(M.readJSON(M.KEYS.locationContext, null)), "_blank", "noopener,noreferrer"));
  $("#notificationButton").addEventListener("click", () => M.showToast("Bạn có 3 nhắc nhở sức khỏe chưa xem."));
  window.addEventListener("medicare:profile-changed", () => { renderProfiles(); renderEnvironmentAdvice(M.readJSON(M.KEYS.locationContext, null)); });
  window.addEventListener("medicare:auth-changed", async (event) => {
    if (event.detail) {
      await M.syncProfiles(event.detail);
      sessions = M.readJSON(M.KEYS.chats, []);
      currentChatId = localStorage.getItem(M.KEYS.currentChat) || "";
      ensureSession();
      $("#accountName").textContent = event.detail.full_name || "Tài khoản";
      $("#accountAvatar").textContent = M.initials(event.detail.full_name);
      renderProfiles(); renderHistory(); renderMessages();
    } else {
      sessions = []; currentChatId = "";
      $("#accountName").textContent = "Khách";
      $("#accountAvatar").textContent = "K";
      ensureSession(); renderProfiles(); renderHistory(); renderMessages();
    }
  });
}

document.addEventListener("DOMContentLoaded", initialize);
