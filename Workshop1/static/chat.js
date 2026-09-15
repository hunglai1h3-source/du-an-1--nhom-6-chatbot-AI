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

// Chặn vòng lặp profile-changed -> switchToProfile -> selectProfile -> profile-changed
let isSwitchingProfile = false;

 

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

 

function createSession({ keepExisting = false, profile = null } = {}) {

  if (keepExisting && currentSession()) return currentSession();

  profile = profile || M.getSelectedProfile();

  const newId = `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const session = {

    id: newId,

    title: `Tư vấn cho ${profile.name}`,

    profileId: profile.id,

    favorite: false,

    safetyState: { highest_risk_level: "normal", active_flags: [], safety_unknown: false },

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

  M.currentUser().then((userStatus) => {
    if (userStatus && userStatus.logged_in) {
      fetch("/api/conversations", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: session.id,
          title: session.title,
          profile_id: String(profile.id),
        }),
      }).catch(() => {});
    }
  }).catch(() => {});

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

 

function latestSessionForProfile(profileId) {

  return sessions

    .filter((item) => String(item.profileId) === String(profileId))

    .sort((a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0))[0] || null;

}

 

function switchToProfile(profileId) {

  if (isSwitchingProfile) return;

  isSwitchingProfile = true;

  try {
    const profiles = M.getProfiles();

    const nextProfile = profiles.find(
      (profile) => String(profile.id) === String(profileId)
    );

    if (!nextProfile) {
      M.showToast("Không tìm thấy hồ sơ đã chọn.", "error");
      return;
    }

    const oldSession = currentSession();
    const oldProfileId = oldSession?.profileId;

    if (String(oldProfileId) === String(nextProfile.id)) {
      M.selectProfile(nextProfile);
      renderProfiles();
      closeMenus();
      return;
    }

    // Chuyển currentChatId sang đúng hồ sơ TRƯỚC khi phát profile-changed.
    let targetSession = latestSessionForProfile(nextProfile.id);

    if (!targetSession) {
      targetSession = createSession({ profile: nextProfile });
    } else {
      currentChatId = targetSession.id;
    }

    // Sau khi session đã đúng profile mới gọi selectProfile.
    M.selectProfile(nextProfile);

    clearSelectedImage();

    const chatInput = $("#chatInput");
    if (chatInput) chatInput.value = "";

    autoResizeInput();

    localStorage.removeItem(M.KEYS.specialty);
    renderSpecialty();

    persistSessions();
    renderProfiles();
    renderHistory();
    renderMessages();
    renderEnvironmentAdvice(M.readJSON(M.KEYS.locationContext, null));

    closeMenus();

    M.showToast(
      `Đã chuyển sang hồ sơ ${nextProfile.name}. Lịch sử và ngữ cảnh đã được tách riêng.`,
      "success"
    );
  } finally {
    isSwitchingProfile = false;
  }

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

    switchToProfile(button.dataset.profileId);

  }));

}

 

function formatText(value, isAssistant = false) {
  const raw = String(value || "").replace(/\r\n?/g, "\n").trim();

  // Tin nhắn người dùng: chỉ escape HTML và giữ xuống dòng đơn giản.
  if (!isAssistant) {
    return M.escapeHTML(raw).replace(/\n/g, "<br>");
  }

  // Nội dung AI: render Markdown V2 với bảng biểu, code block, trích dẫn, v.v.
  const escaped = M.escapeHTML(raw);

  const inline = (text) => {
    return text
      // Bold
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/__(.+?)__/g, "<strong>$1</strong>")
      // Italic
      .replace(/\*([^\*\n]+)\*/g, "<em>$1</em>")
      .replace(/_([^_\n]+)_/g, "<em>$1</em>")
      // Inline code
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      // Safe markdown links: [text](url) - only http/https/tel/mailto
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)\"\']+|tel:[^\s\)\"\']+|mailto:[^\s\)\"\']+)\)/g, (match, label, url) => {
        return `<a class="chat-link" href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      });
  };

  const lines = escaped.split("\n");
  const html = [];
  let paragraph = [];
  let inList = false;
  let listType = "ul";
  let inCodeBlock = false;
  let codeBlockLines = [];
  let codeBlockLang = "";
  let inTable = false;
  let tableRows = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!inList) return;
    html.push(`</${listType}>`);
    inList = false;
  };

  const closeTable = () => {
    if (!inTable) return;
    if (tableRows.length > 0) {
      let tableHtml = '<div class="table-wrap"><table>';
      const hasHeader = tableRows.length >= 2;
      const headerRow = tableRows[0];
      tableHtml += '<thead><tr>' + headerRow.map(cell => `<th>${inline(cell)}</th>`).join('') + '</tr></thead>';
      tableHtml += '<tbody>';
      for (let i = (hasHeader ? 1 : 0); i < tableRows.length; i++) {
        tableHtml += '<tr>' + tableRows[i].map(cell => `<td>${inline(cell)}</td>`).join('') + '</tr>';
      }
      tableHtml += '</tbody></table></div>';
      html.push(tableHtml);
    }
    tableRows = [];
    inTable = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const originalLine = lines[i];
    const line = originalLine.trim();

    // Check fenced code block ```
    if (line.startsWith("```")) {
      flushParagraph();
      closeList();
      closeTable();
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeBlockLang = line.slice(3).trim();
        codeBlockLines = [];
      } else {
        inCodeBlock = false;
        const codeContent = codeBlockLines.join("\n");
        const langAttr = codeBlockLang ? ` class="language-${M.escapeHTML(codeBlockLang)}"` : "";
        html.push(`<pre><code${langAttr}>${codeContent}</code></pre>`);
        codeBlockLines = [];
        codeBlockLang = "";
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(originalLine);
      continue;
    }

    if (!line) {
      flushParagraph();
      closeList();
      closeTable();
      continue;
    }

    // Markdown Table Row: | Col 1 | Col 2 |
    if (line.startsWith("|") && line.endsWith("|")) {
      const isSeparator = /^\|(\s*:?-+:?\s*\|)+$/.test(line);
      if (isSeparator) {
        continue;
      }
      flushParagraph();
      closeList();
      inTable = true;
      const cells = line.slice(1, -1).split("|").map(c => c.trim());
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      closeTable();
    }

    // Blockquote: > text or &gt; text
    const bqMatch = line.match(/^(&gt;|>)\s*(.*)$/);
    if (bqMatch) {
      flushParagraph();
      closeList();
      html.push(`<blockquote><p>${inline(bqMatch[2])}</p></blockquote>`);
      continue;
    }

    // Heading: #, ##, ###, ####
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length <= 2 ? 2 : (heading[1].length === 3 ? 3 : 4);
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }

    // Horizontal Rule: ---, ***, ___
    if (/^(-{3,}|_{3,}|\*{3,})$/.test(line)) {
      flushParagraph();
      closeList();
      html.push("<hr>");
      continue;
    }

    // Ordered List: 1. Item
    const ordered = line.match(/^(\d+)[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (!inList || listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
        inList = true;
      }
      html.push(`<li>${inline(ordered[2])}</li>`);
      continue;
    }

    // Bullet List: - Item, * Item, + Item, • Item
    const bullet = line.match(/^[-*+•]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      if (!inList || listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
  closeList();
  closeTable();

  if (inCodeBlock && codeBlockLines.length) {
    const codeContent = codeBlockLines.join("\n");
    html.push(`<pre><code>${codeContent}</code></pre>`);
  }

  return html.join("");
}

function renderEmergencyPanel(message) {
  const emergency = message?.emergency;
  if (!emergency?.active) return "";

  const phone = String(emergency.phone || "115").replace(/[^\d+]/g, "") || "115";
  const phoneUri = String(emergency.phone_uri || emergency.call || `tel:${phone}`);
  const title = emergency.title || "DẤU HIỆU CÓ THỂ CẦN CẤP CỨU";
  const primaryAction = emergency.primary_action || `Gọi ${phone} ngay`;

  return `
    <section class="chat-emergency-panel" role="alert" aria-live="assertive">
      <div class="chat-emergency-heading">
        <span class="chat-emergency-icon" aria-hidden="true">🚨</span>
        <div>
          <strong>${M.escapeHTML(title)}</strong>
          <small>Ưu tiên liên hệ cấp cứu thay vì tiếp tục chờ tư vấn trực tuyến.</small>
        </div>
      </div>

      <a
        class="chat-emergency-call"
        href="${M.escapeHTML(phoneUri)}"
        aria-label="${M.escapeHTML(primaryAction)}"
      >
        <span aria-hidden="true">☎</span>
        <span>
          <b>${M.escapeHTML(primaryAction)}</b>
          <small>Chạm để mở cuộc gọi đến ${M.escapeHTML(phone)}</small>
        </span>
      </a>

      <p class="chat-emergency-note">
        Không tự lái xe nếu đang khó thở, choáng hoặc có nguy cơ mất ý thức.
        Hãy nhờ người ở gần hỗ trợ.
      </p>
    </section>`;
}

function renderRiskNotice(riskLevel) {
  if (riskLevel === "urgent") {
    return `
      <div class="risk-notice urgent" role="alert">
        <span aria-hidden="true">⚠️</span>
        <div>
          <strong>Khuyến nghị thăm khám y tế sớm</strong>
          <p>Triệu chứng của bạn có dấu hiệu cần được bác sĩ chuyên khoa thăm khám trực tiếp để chẩn đoán chính xác.</p>
        </div>
      </div>`;
  }
  if (riskLevel === "caution") {
    return `
      <div class="risk-notice caution" role="status">
        <span aria-hidden="true">ℹ️</span>
        <div>
          <strong>Lưu ý theo dõi triệu chứng</strong>
          <p>Hãy theo dõi sát diễn biến sức khỏe. Đến ngay cơ sở y tế nếu triệu chứng tăng nặng hoặc không đỡ sau 24-48 giờ.</p>
        </div>
      </div>`;
  }
  return "";
}

function renderSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return "";

  const cardsHtml = sources.map((item) => {
    const title = item.title || "Tài liệu y khoa tham khảo";
    let sourceName = item.source || "Kho tri thức Y tế";
    if (/vinmec/i.test(sourceName)) sourceName = "Bệnh viện ĐKQT Vinmec";
    else if (/vnexpress/i.test(sourceName)) sourceName = "VnExpress Sức Khỏe";
    else if (/vihealthqa/i.test(sourceName)) sourceName = "ViHealthQA Y Khoa";

    const trustBadge = (item.trust_level === "verified" || item.trust_level === "authoritative")
      ? '<span class="source-trust-badge">✓ Đã đối chiếu</span>'
      : '<span class="source-trust-badge">Tham khảo</span>';

    const url = item.source_url && /^https?:\/\//i.test(item.source_url) ? item.source_url : "";
    const linkHtml = url
      ? `<a class="source-link" href="${M.escapeHTML(url)}" target="_blank" rel="noopener noreferrer">Đọc bài gốc ↗</a>`
      : "";

    return `
      <div class="rag-source-card">
        <div class="rag-source-header">
          <span class="rag-source-icon">📚</span>
          <span class="rag-source-publisher">${M.escapeHTML(sourceName)}</span>
          ${trustBadge}
        </div>
        <p class="rag-source-title">${M.escapeHTML(title)}</p>
        ${linkHtml}
      </div>`;
  }).join("");

  return `
    <section class="rag-sources-panel" aria-label="Nguồn tham khảo y khoa">
      <div class="rag-sources-title">
        <span>📖 Nguồn tham khảo y khoa đã đối chiếu</span>
        <small>${sources.length} tài liệu liên quan</small>
      </div>
      <div class="rag-sources-list">
        ${cardsHtml}
      </div>
    </section>`;
}

function renderWelcomeHero(profile) {
  const profileName = profile?.name || "bạn";
  return `
    <div class="welcome-hero" id="welcomeHero">
      <div class="welcome-badge">
        <span class="welcome-icon">🏥</span>
        <span>Trợ lý y tế thông minh</span>
      </div>
      <h2 class="welcome-title">Xin chào, tôi là MediCare AI</h2>
      <p class="welcome-subtitle">Đang sẵn sàng đồng hành và tư vấn sức khỏe cho <strong>${M.escapeHTML(profileName)}</strong>. Bạn có thể chọn gợi ý nhanh bên dưới hoặc đặt câu hỏi bất kỳ.</p>
      <div class="starter-cards">
        <button class="starter-card" type="button" data-starter-prompt="Tôi bị sốt nhẹ và đau họng từ hôm qua, cần theo dõi những gì?">
          <span class="starter-icon">🩺</span>
          <strong>Tư vấn triệu chứng</strong>
          <small>Sốt nhẹ, đau đầu, ho dai dẳng, đau bụng...</small>
        </button>
        <button class="starter-card" type="button" data-starter-prompt="Thuốc Paracetamol nên uống cách nhau mấy tiếng và có lưu ý gì khi dùng?">
          <span class="starter-icon">💊</span>
          <strong>Hướng dẫn dùng thuốc</strong>
          <small>Liều lượng, khoảng cách uống, tương tác thuốc...</small>
        </button>
        <button class="starter-card" type="button" data-starter-prompt="Tìm nhà thuốc hoặc phòng khám đa khoa uy tín gần tôi nhất">
          <span class="starter-icon">📍</span>
          <strong>Cơ sở y tế gần bạn</strong>
          <small>Tìm nhà thuốc, trung tâm y tế, bệnh viện gần nhất...</small>
        </button>
        <button class="starter-card" type="button" data-starter-prompt="Chỉ số bụi mịn AQI hôm nay thế nào, người có bệnh hô hấp cần lưu ý gì?">
          <span class="starter-icon">🍃</span>
          <strong>Môi trường & Thời tiết</strong>
          <small>Khuyến cáo bụi mịn PM2.5, dị ứng thời tiết...</small>
        </button>
      </div>
    </div>`;
}

 


function ensureFeedbackModal() {
  let modal = $("#feedbackModal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "feedbackModal";
  modal.className = "shared-modal hidden";
  modal.innerHTML = `
    <section class="shared-modal-card feedback-modal-card" role="dialog" aria-modal="true" aria-labelledby="feedbackTitle">
      <button class="shared-modal-close" data-feedback-close type="button" aria-label="Đóng">×</button>
      <p class="modal-eyebrow">ĐÁNH GIÁ CÂU TRẢ LỜI</p>
      <h2 id="feedbackTitle">Điều gì chưa tốt?</h2>
      <p class="feedback-help">Góp ý giúp MediCare AI cải thiện chất lượng tư vấn. Không nhập thông tin nhạy cảm không cần thiết.</p>
      <form id="feedbackForm">
        <div class="feedback-reasons">
          ${[
            ["inaccurate","Không chính xác"],
            ["irrelevant","Không đúng câu hỏi"],
            ["hard_to_understand","Khó hiểu / quá dài"],
            ["missing_info","Thiếu thông tin"],
            ["unsafe","Có nội dung không an toàn"],
            ["other","Khác"]
          ].map(([value,label]) => `<label><input type="radio" name="reason" value="${value}"><span>${label}</span></label>`).join("")}
        </div>
        <label class="feedback-note">Góp ý thêm (không bắt buộc)
          <textarea name="feedback_text" maxlength="1200" rows="3" placeholder="Ví dụ: câu trả lời chưa giải thích rõ phần..."></textarea>
        </label>
        <p class="feedback-form-message"></p>
        <div class="feedback-form-actions">
          <button type="button" class="feedback-cancel" data-feedback-close>Hủy</button>
          <button type="submit" class="feedback-submit">Gửi đánh giá</button>
        </div>
      </form>
    </section>`;
  document.body.appendChild(modal);
  $$("[data-feedback-close]", modal).forEach((button) => button.addEventListener("click", () => modal.classList.add("hidden")));
  modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });
  return modal;
}

async function postMessageFeedback(message, rating, reason = "", feedbackText = "") {
  message.feedback = rating || "";
  message.feedbackReason = reason;
  message.feedbackText = feedbackText;
  persistSessions();

  if (!message.chatLogId) {
    M.showToast("Đã ghi nhận đánh giá trên thiết bị.", "success");
    return;
  }

  const response = await fetch("/api/chat-feedback", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_log_id: message.chatLogId,
      rating,
      reason,
      feedback_text: feedbackText
    })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Không thể gửi đánh giá.");
  M.showToast(data.message || "Cảm ơn bạn đã đánh giá!", "success");
}

function openDislikeFeedback(index) {
  const session = ensureSession();
  const message = session.messages[Number(index)];
  if (!message) return;

  const modal = ensureFeedbackModal();
  const form = $("#feedbackForm", modal);
  form.reset();
  form.dataset.messageIndex = String(index);
  $(".feedback-form-message", form).textContent = "";
  modal.classList.remove("hidden");

  form.onsubmit = async (event) => {
    event.preventDefault();
    const submit = $(".feedback-submit", form);
    const status = $(".feedback-form-message", form);
    const data = Object.fromEntries(new FormData(form));
    submit.disabled = true;
    submit.textContent = "Đang gửi...";
    status.textContent = "";
    try {
      await postMessageFeedback(message, "dislike", data.reason || "", data.feedback_text || "");
      modal.classList.add("hidden");
      renderMessages();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
      submit.textContent = "Gửi đánh giá";
    }
  };
}

function renderMessages() {
  const session = ensureSession();
  const list = $("#messageList");
  const profile = profileForSession(session);

  const hasUserMessage = session.messages.some((m) => m.role === "user");
  const heroHtml = !hasUserMessage ? renderWelcomeHero(profile) : "";

  const messagesHtml = session.messages.map((message, index) => {
    const isUser = message.role === "user";
    const avatar = isUser ? M.initials(profile.name) : "🤖";

    const riskLevel = message.safetyState?.highest_risk_level?.toLowerCase() || (message.emergency?.active ? "emergency" : "normal");
    let safetyHtml = "";
    if (message.emergency?.active) {
      safetyHtml = renderEmergencyPanel(message);
    } else if (riskLevel === "urgent") {
      safetyHtml = renderRiskNotice("urgent");
    } else if (riskLevel === "caution") {
      safetyHtml = renderRiskNotice("caution");
    }

    const sourcesHtml = !isUser && message.sources ? renderSources(message.sources) : "";

    return `
      <article class="message-row ${isUser ? "user" : "assistant"}" data-message-index="${index}">
        ${isUser ? "" : `<span class="message-avatar">${avatar}</span>`}
        <div class="message-bubble">
          ${message.imagePreview ? `<img src="${message.imagePreview}" alt="Ảnh người dùng gửi" style="display:block;max-width:240px;max-height:190px;object-fit:cover;border-radius:11px;margin-bottom:9px">` : ""}
          <div class="${isUser ? "user-content" : "ai-content"}">${formatText(message.content, !isUser)}</div>
          ${safetyHtml}
          ${sourcesHtml}
          <div class="message-meta"><time>${M.escapeHTML(message.time || "")}</time>${isUser ? "<span>✓✓</span>" : ""}</div>
          ${isUser ? "" : `<div class="message-actions">
            <button type="button" data-copy-index="${index}" title="Sao chép">⧉ <span>Sao chép</span></button>
            <button type="button" class="feedback-action ${message.feedback === "like" ? "active" : ""}" data-feedback-like="${index}" title="Câu trả lời hữu ích" aria-label="Hữu ích">👍</button>
            <button type="button" class="feedback-action ${message.feedback === "dislike" ? "active" : ""}" data-feedback-dislike="${index}" title="Câu trả lời chưa tốt" aria-label="Chưa tốt">👎</button>
            <button type="button" data-like-index="${index}">${message.liked ? "♥ Đã lưu" : "♡ Lưu"}</button>
          </div>`}
        </div>
        ${isUser ? `<span class="message-avatar">${avatar}</span>` : ""}
      </article>`;
  }).join("");

  const isNearBottom = (list.scrollHeight - list.scrollTop - list.clientHeight) < 140;
  list.innerHTML = heroHtml + messagesHtml;
  if (isNearBottom || isSending || !hasUserMessage) {
    list.scrollTop = list.scrollHeight;
  }

  $$('[data-starter-prompt]').forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.dataset.starterPrompt;
      const input = $("#chatInput");
      if (input && prompt) {
        input.value = prompt;
        autoResizeInput();
        input.focus();
      }
    });
  });

 

  $$('[data-copy-index]').forEach((button) => button.addEventListener("click", async () => {

    const message = session.messages[Number(button.dataset.copyIndex)];

    await navigator.clipboard.writeText(message.content).catch(() => {});

    M.showToast("Đã sao chép câu trả lời.", "success");

  }));

  $$("[data-feedback-like]").forEach((button) => button.addEventListener("click", async () => {
    const message = session.messages[Number(button.dataset.feedbackLike)];
    const next = message.feedback === "like" ? "" : "like";
    try {
      await postMessageFeedback(message, next);
      renderMessages();
    } catch (error) {
      M.showToast(error.message, "error");
    }
  }));

  $$("[data-feedback-dislike]").forEach((button) => button.addEventListener("click", () => {
    const message = session.messages[Number(button.dataset.feedbackDislike)];
    if (message.feedback === "dislike") {
      postMessageFeedback(message, "").then(renderMessages).catch((error) => M.showToast(error.message, "error"));
      return;
    }
    openDislikeFeedback(button.dataset.feedbackDislike);
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

 

  $$('[data-session-id]').forEach((button) => button.addEventListener("click", async () => {

    currentChatId = button.dataset.sessionId;

    const session = ensureSession();

    const profile = profileForSession(session);

    M.selectProfile(profile);

    persistSessions();

    renderProfiles();

    renderHistory();

    renderMessages();

    await loadSessionMessages(currentChatId);

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
  row.innerHTML = `
    <span class="message-avatar">🤖</span>
    <div class="message-bubble ai-thinking-bubble">
      <div class="ai-thinking-indicator">
        <span class="medical-pulse-dot" aria-hidden="true"></span>
        <span class="ai-thinking-text">MediCare AI đang phân tích dữ liệu y tế...</span>
        <div class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></div>
      </div>
    </div>
  `;
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

 

  const selectedProfile = M.getSelectedProfile();

  let session = ensureSession();

 

  // Nếu giao diện vừa đổi hồ sơ nhưng cuộc trò chuyện chưa đổi, đồng bộ trước khi gửi.

  if (String(session.profileId) !== String(selectedProfile.id)) {

    switchToProfile(selectedProfile.id);

    session = ensureSession();

  }

 

  isSending = true;

  $("#sendButton").disabled = true;
  $("#chatInput").disabled = true;
  const attachBtnStart = $("#attachImageButton");
  if (attachBtnStart) attachBtnStart.disabled = true;
  const voiceBtnStart = $("#voiceButton");
  if (voiceBtnStart) voiceBtnStart.disabled = true;

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

 

  // Gửi ảnh chụp hồ sơ đang chọn trong MỖI lượt chat để backend/AI không hỏi lại dữ liệu đã có.

  const activeProfile = profileForSession(session) || M.getSelectedProfile();

  formData.append("selected_profile", JSON.stringify({

    id: activeProfile.id,

    name: activeProfile.name,

    relationship: activeProfile.relationship,

    age: activeProfile.age,

    gender: activeProfile.gender,

    height: activeProfile.height,

    weight: activeProfile.weight,

    condition: activeProfile.condition,

    allergies: activeProfile.allergies,

    profile_type: activeProfile.relationship === "Bản thân" ? "self" : "family"

  }));

  formData.append("profile_context_version", "3");

  formData.append("conversation_id", String(session.id));

  const clientMessageId = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

  formData.append("client_message_id", clientMessageId);

  if (session.safetyState) formData.append("safety_state", JSON.stringify(session.safetyState));

 

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

 

    const returnedProfileId = data.profile_used?.id;

    if (returnedProfileId != null && String(returnedProfileId) !== String(activeProfile.id)) {

      throw new Error("Máy chủ trả về sai hồ sơ tư vấn. Vui lòng tải lại trang.");

    }

 

    if (data.safety_state) {

      session.safetyState = data.safety_state;

    }

 

    session.messages.push({
      role: "assistant",
      content: data.reply,
      time: nowTime(),
      emergency: data.emergency?.active ? data.emergency : null,
      safetyState: data.safety_state || null,
      sources: Array.isArray(data.sources) && data.sources.length > 0 ? data.sources : null,
      chatLogId: data.chat_log_id || null
    });

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
    $("#chatInput").disabled = false;
    const attachBtn = $("#attachImageButton");
    if (attachBtn) attachBtn.disabled = false;
    const voiceBtn = $("#voiceButton");
    if (voiceBtn) voiceBtn.disabled = false;
    $("#chatInput")?.focus();

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

 

let speechRecognition = null;
let isSpeechRecognizing = false;
let speechBaseText = "";

function toggleVoice() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  const button = $("#voiceButton");
  const input = $("#chatInput");

  if (!SpeechRecognition) {
    setVoiceStatus(
      "Trình duyệt này chưa hỗ trợ nhập giọng nói trực tiếp. Hãy dùng Chrome hoặc Edge.",
      true
    );
    return;
  }

  // Nếu đang nghe thì bấm lần nữa để dừng
  if (isSpeechRecognizing && speechRecognition) {
    speechRecognition.stop();
    return;
  }

  speechRecognition = new SpeechRecognition();

speechRecognition.lang = "vi-VN";
speechRecognition.continuous = true;
speechRecognition.interimResults = true;
speechRecognition.maxAlternatives = 3;

  // Giữ lại nội dung người dùng đã gõ trước đó
  speechBaseText = input.value.trim();

  speechRecognition.onstart = () => {
    isSpeechRecognizing = true;

    button.classList.add("recording");
    button.textContent = "■";

    setVoiceStatus("Đang nghe... bạn có thể nói ngay.");
  };

speechRecognition.onresult = (event) => {
  let finalText = "";
  let interimText = "";

  for (let i = 0; i < event.results.length; i++) {
    const result = event.results[i];

    // Mặc định lấy kết quả đầu tiên
    let bestAlternative = result[0];

    // So sánh tối đa 3 kết quả nhận dạng
    // và chọn kết quả có confidence cao nhất
    for (let j = 1; j < result.length; j++) {
      const currentConfidence =
        typeof result[j].confidence === "number"
          ? result[j].confidence
          : 0;

      const bestConfidence =
        typeof bestAlternative.confidence === "number"
          ? bestAlternative.confidence
          : 0;

      if (currentConfidence > bestConfidence) {
        bestAlternative = result[j];
      }
    }

    const transcript = bestAlternative.transcript;

    if (result.isFinal) {
      finalText += transcript + " ";
    } else {
      interimText += transcript;
    }
  }

  const spokenText = `${finalText}${interimText}`.trim();

  input.value = `${speechBaseText} ${spokenText}`.trim();

  autoResizeInput();
  input.focus();
};

  speechRecognition.onerror = (event) => {
    isSpeechRecognizing = false;

    button.classList.remove("recording");
    button.textContent = "🎙";

    if (event.error === "not-allowed") {
      setVoiceStatus(
        "Bạn chưa cho phép sử dụng micro. Hãy bật quyền micro cho website.",
        true
      );
    } else if (event.error === "no-speech") {
      setVoiceStatus("Không nghe thấy giọng nói. Hãy thử lại.", true);
    } else {
      setVoiceStatus(
        `Không nhận dạng được giọng nói: ${event.error}`,
        true
      );
    }
  };

  speechRecognition.onend = () => {
    isSpeechRecognizing = false;

    button.classList.remove("recording");
    button.textContent = "🎙";

    setVoiceStatus("Đã dừng nhận giọng nói.");

    setTimeout(() => {
      setVoiceStatus("");
    }, 2000);
  };

  try {
    speechRecognition.start();
  } catch (error) {
    setVoiceStatus("Không thể khởi động micro. Hãy thử lại.", true);
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

 

function openConfirmModal({ title, message, confirmText = "Xóa", onConfirm }) {
  const modal = $("#confirmDeleteModal");
  if (!modal) {
    if (confirm(message)) onConfirm?.();
    return;
  }
  $("#confirmDeleteTitle").textContent = title || "Xác nhận";
  $("#confirmDeleteMessage").textContent = message || "Bạn có chắc chắn muốn thực hiện?";
  const actionBtn = $("#actionConfirmDeleteButton");
  actionBtn.textContent = confirmText;

  modal.classList.remove("hidden");

  const close = () => {
    modal.classList.add("hidden");
    actionBtn.onclick = null;
  };

  $("#closeConfirmDeleteModal").onclick = close;
  $("#cancelConfirmDeleteButton").onclick = close;
  modal.onclick = (e) => { if (e.target === modal) close(); };

  actionBtn.onclick = () => {
    close();
    onConfirm?.();
  };
}

function bindChatActions() {
  $$('[data-chat-action]').forEach((button) => button.addEventListener("click", () => {
    const action = button.dataset.chatAction;
    const session = ensureSession();

    if (action === "export") exportCurrentChat();

    if (action === "clear") {
      openConfirmModal({
        title: "Xóa nội dung cuộc trò chuyện",
        message: "Toàn bộ tin nhắn trong cuộc trò chuyện này sẽ bị xóa. Bạn có chắc chắn?",
        confirmText: "Xóa nội dung",
        onConfirm: () => {
          const resetConvId = String(session.id);
          fetch(`/api/conversations/${encodeURIComponent(resetConvId)}/clear`, {
            method: "POST",
            credentials: "same-origin"
          }).catch(() => {
            fetch("/chat/reset", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ conversation_id: resetConvId })
            }).catch(() => {});
          });

          session.messages = [];
          session.safetyState = { highest_risk_level: "normal", active_flags: [], safety_unknown: false };
          session.updatedAt = new Date().toISOString();
          persistSessions();
          renderMessages();
          renderHistory();
          M.showToast("Đã xóa nội dung cuộc trò chuyện.", "success");
        }
      });
    }

    if (action === "delete") {
      openConfirmModal({
        title: "Xóa cuộc trò chuyện",
        message: "Cuộc trò chuyện này sẽ bị xóa vĩnh viễn khỏi thiết bị và tài khoản. Bạn có chắc chắn?",
        confirmText: "Xóa vĩnh viễn",
        onConfirm: () => {
          const deleteConvId = String(session.id);
          fetch(`/api/conversations/${encodeURIComponent(deleteConvId)}`, {
            method: "DELETE",
            credentials: "same-origin"
          }).catch(() => {
            fetch("/chat/reset", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ conversation_id: deleteConvId })
            }).catch(() => {});
          });

          sessions = sessions.filter((item) => item.id !== session.id);
          currentChatId = "";
          createSession();
          renderMessages();
          renderHistory();
          M.showToast("Đã xóa cuộc trò chuyện.", "success");
        }
      });
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



async function loadSessionMessages(sessionId) {
  if (!sessionId) return;
  const session = sessions.find((s) => String(s.id) === String(sessionId));
  if (!session) return;
  if (session.messages && session.messages.some((m) => m.role === "user")) return;

  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}/messages`, { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    if (Array.isArray(data.messages) && data.messages.length > 0) {
      session.messages = data.messages.map((m) => {
        const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : nowTime();
        return {
          role: m.role,
          content: m.content,
          time: timeStr,
          emergency: m.metadata?.emergency || null,
          safetyState: m.metadata?.safety_state || null,
          sources: m.metadata?.sources || null,
          chatLogId: m.metadata?.chat_log_id || null,
          imagePreview: m.metadata?.imagePreview || null,
        };
      });
      persistSessions();
      renderMessages();
    }
  } catch (err) {
    console.warn("Lỗi loadSessionMessages:", err);
  }
}

async function syncConversationsFromBackend() {
  try {
    const userStatus = await M.currentUser();
    if (!userStatus || !userStatus.logged_in) return;

    if (!sessions.length) {
      const historyList = $("#historyList");
      if (historyList) {
        historyList.innerHTML = `
          <div class="history-skeleton"><div class="skeleton-line" style="width:75%;height:14px;margin-bottom:8px"></div><div class="skeleton-line" style="width:50%;height:10px"></div></div>
          <div class="history-skeleton"><div class="skeleton-line" style="width:80%;height:14px;margin-bottom:8px"></div><div class="skeleton-line" style="width:40%;height:10px"></div></div>
          <div class="history-skeleton"><div class="skeleton-line" style="width:65%;height:14px;margin-bottom:8px"></div><div class="skeleton-line" style="width:55%;height:10px"></div></div>
        `;
      }
    }

    const response = await fetch("/api/conversations", { credentials: "same-origin" });
    if (!response.ok) return;

    const data = await response.json();
    if (Array.isArray(data.conversations) && data.conversations.length > 0) {
      const serverSessions = data.conversations.map((c) => {
        const existing = sessions.find((s) => String(s.id) === String(c.id));
        return {
          id: c.id,
          title: c.title || "Cuộc trò chuyện",
          profileId: c.profile_id || null,
          favorite: existing ? existing.favorite : false,
          summary: c.summary || "",
          updatedAt: c.updated_at,
          messages: existing?.messages?.length ? existing.messages : [],
        };
      });

      sessions = serverSessions;
      if (!currentChatId || !sessions.some((s) => String(s.id) === String(currentChatId))) {
        currentChatId = sessions[0].id;
      }
      persistSessions();
      await loadSessionMessages(currentChatId);
    }
  } catch (err) {
    console.warn("Không thể đồng bộ danh sách cuộc trò chuyện từ backend:", err);
  }
}

async function initialize() {

  bindHealthProfileModal();

  await initializeAccount();

  sessions = M.readJSON(M.KEYS.chats, []);

  currentChatId = localStorage.getItem(M.KEYS.currentChat) || "";

  await syncConversationsFromBackend();

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

  $("#clearAllHistoryButton").addEventListener("click", () => {
    openConfirmModal({
      title: "Xóa toàn bộ lịch sử",
      message: "Toàn bộ lịch sử trò chuyện trên thiết bị này sẽ bị xóa. Bạn có chắc chắn?",
      confirmText: "Xóa tất cả",
      onConfirm: () => {
        sessions = [];
        currentChatId = "";
        createSession();
        renderHistory();
        renderMessages();
        M.showToast("Đã xóa toàn bộ lịch sử.", "success");
      }
    });
  });

  // Toggle Context Sidebar (Desktop)
  const shell = $("#consultationShell");
  const toggleContextBtn = $("#toggleContextButton");
  toggleContextBtn?.addEventListener("click", () => {
    shell?.classList.toggle("context-collapsed");
  });

  // Mobile Drawers
  const mobileMenuBtn = $("#mobileMenuButton");
  const mobileContextBtn = $("#mobileContextButton");
  const historySidebar = $("#historySidebar");
  const contextSidebar = $("#contextSidebar");
  const backdrop = $("#sidebarBackdrop");
  const closeHistoryBtn = $("#closeHistorySidebar");
  const closeContextBtn = $("#closeContextSidebar");

  const closeDrawers = () => {
    historySidebar?.classList.remove("mobile-open");
    contextSidebar?.classList.remove("mobile-open");
    backdrop?.classList.add("hidden");
  };

  mobileMenuBtn?.addEventListener("click", () => {
    contextSidebar?.classList.remove("mobile-open");
    historySidebar?.classList.toggle("mobile-open");
    backdrop?.classList.toggle("hidden", !historySidebar?.classList.contains("mobile-open"));
  });

  mobileContextBtn?.addEventListener("click", () => {
    historySidebar?.classList.remove("mobile-open");
    contextSidebar?.classList.toggle("mobile-open");
    backdrop?.classList.toggle("hidden", !contextSidebar?.classList.contains("mobile-open"));
  });

  closeHistoryBtn?.addEventListener("click", closeDrawers);
  closeContextBtn?.addEventListener("click", closeDrawers);
  backdrop?.addEventListener("click", closeDrawers);

  // Character counter for composer
  const chatInputEl = $("#chatInput");
  const charCounterEl = $("#charCounter");
  if (chatInputEl && charCounterEl) {
    chatInputEl.addEventListener("input", () => {
      const len = chatInputEl.value.length;
      charCounterEl.textContent = `${len}/4000`;
      charCounterEl.classList.toggle("hidden", len < 3000);
      charCounterEl.classList.toggle("warning", len >= 3800);
    });
  }

  $("#profileControl").addEventListener("click", (event) => { event.stopPropagation(); const menu = $("#profileMenu"); menu.classList.toggle("hidden"); $("#moreMenu").classList.add("hidden"); event.currentTarget.setAttribute("aria-expanded", String(!menu.classList.contains("hidden"))); });

  $("#changeProfileButton").addEventListener("click", () => $("#profileControl").click());

  $("#contextChangeProfileButton").addEventListener("click", () => $("#profileControl").click());

  $("#headerChangeProfileButton")?.addEventListener("click", () => $("#profileControl").click());

  $("#moreButton").addEventListener("click", (event) => { event.stopPropagation(); $("#moreMenu").classList.toggle("hidden"); $("#profileMenu").classList.add("hidden"); });

  document.addEventListener("click", closeMenus);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenus();
      $("#confirmDeleteModal")?.classList.add("hidden");
      $("#specialtyModal")?.classList.add("hidden");
      $("#healthProfileModal")?.classList.add("hidden");
      $("#feedbackModal")?.classList.add("hidden");
      closeDrawers();
    }
  });

  bindChatActions();

  bindSpecialtyPicker();

  if (new URLSearchParams(window.location.search).get("editProfile") === "1") {

    await openHealthProfileModal();

    history.replaceState({}, "", "/tu-van");

  }

  $("#refreshQuickButton").addEventListener("click", () => { quickSetIndex = (quickSetIndex + 1) % quickSets.length; renderQuickPrompts(); });

  const quickArea = $("#quickArea");
  const quickToggleButton = $("#quickToggleButton");

  quickToggleButton?.addEventListener("click", () => {
    const isCollapsed = quickArea.classList.toggle("collapsed");

    quickToggleButton.textContent = isCollapsed ? "▲" : "▼";
    quickToggleButton.setAttribute("aria-expanded", String(!isCollapsed));
    quickToggleButton.setAttribute("aria-label", isCollapsed ? "Hiện gợi ý" : "Thu gọn gợi ý");
    quickToggleButton.title = isCollapsed ? "Hiện gợi ý" : "Thu gọn gợi ý";
  });

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

  window.addEventListener("medicare:profile-changed", (event) => {

    // Nếu chính switchToProfile đang đồng bộ profile thì bỏ qua event lồng nhau.
    if (isSwitchingProfile) return;

    const selected = event.detail || M.getSelectedProfile();

    if (String(currentSession()?.profileId) !== String(selected.id)) {
      switchToProfile(selected.id);
      return;
    }

    renderProfiles();
    renderEnvironmentAdvice(M.readJSON(M.KEYS.locationContext, null));

  });
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