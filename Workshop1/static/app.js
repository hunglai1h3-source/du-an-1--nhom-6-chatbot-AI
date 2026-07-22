const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatBody = document.getElementById("chatBody");
const sendBtn = document.getElementById("sendBtn");
const stopBtn = document.getElementById("stopBtn");

let controller = null;
let isGenerating = false;

let chatSessions =
  JSON.parse(localStorage.getItem("chatSessions")) || [];

let currentChatId = Date.now();
let conversationHistory = [];

/* =========================================================
   ẢNH
========================================================= */

const imageInput = document.getElementById("imageInput");
const attachImageBtn =
  document.getElementById("attachImageBtn");

const imagePreviewPanel =
  document.getElementById("imagePreviewPanel");

const imagePreview =
  document.getElementById("imagePreview");

const imageFileName =
  document.getElementById("imageFileName");

const removeImageBtn =
  document.getElementById("removeImageBtn");

let selectedImage = null;
let selectedImageUrl = null;

/* =========================================================
   VOICE
========================================================= */

const voiceBtn = document.getElementById("voiceBtn");
const voiceStatus =
  document.getElementById("voiceStatus");

let mediaRecorder = null;
let voiceStream = null;
let voiceChunks = [];
let isVoiceRecording = false;
let voiceStopTimer = null;
let activeSpeechButton = null;

/* =========================================================
   ĐĂNG NHẬP
========================================================= */

const openLoginBtn =
  document.getElementById("openLoginBtn");

const closeLoginBtn =
  document.getElementById("closeLoginBtn");

const loginModal =
  document.getElementById("loginModal");

const loginForm =
  document.getElementById("loginForm");

const loginMessage =
  document.getElementById("loginMessage");

const openRegisterBtn =
  document.getElementById("openRegisterBtn");

const closeRegisterBtn =
  document.getElementById("closeRegisterBtn");

const registerModal =
  document.getElementById("registerModal");

const registerForm =
  document.getElementById("registerForm");

const registerMessage =
  document.getElementById("registerMessage");

const backToLoginBtn =
  document.getElementById("backToLoginBtn");

const logoutBtn =
  document.getElementById("logoutBtn");

const userName =
  document.getElementById("userName");

/* =========================================================
   MENU VÀ GIAO DIỆN
========================================================= */

const mobileMenuBtn =
  document.getElementById("mobileMenuBtn");

const navLinks =
  document.getElementById("navLinks");

const dropdown =
  document.querySelector(".dropdown");

const dropdownTrigger =
  document.querySelector(".dropdown-trigger");

const themeBtn =
  document.getElementById("themeBtn");

/* =========================================================
   HÀM VOICE
========================================================= */

function setVoiceStatus(message = "", isError = false) {
  if (!voiceStatus) {
    return;
  }

  voiceStatus.textContent = message;

  voiceStatus.classList.toggle(
    "hidden",
    !message
  );

  voiceStatus.classList.toggle(
    "error",
    Boolean(isError)
  );
}

function stopVoiceStream() {
  if (voiceStopTimer) {
    clearTimeout(voiceStopTimer);
    voiceStopTimer = null;
  }

  if (voiceStream) {
    voiceStream
      .getTracks()
      .forEach((track) => track.stop());

    voiceStream = null;
  }
}

function setVoiceButtonState(state) {
  if (!voiceBtn) {
    return;
  }

  voiceBtn.classList.remove(
    "recording",
    "transcribing"
  );

  if (state === "recording") {
    voiceBtn.classList.add("recording");
    voiceBtn.textContent = "■";
    voiceBtn.title = "Dừng ghi âm";

    voiceBtn.setAttribute(
      "aria-label",
      "Dừng ghi âm"
    );

    voiceBtn.setAttribute(
      "aria-pressed",
      "true"
    );

    voiceBtn.disabled = false;
    return;
  }

  if (state === "transcribing") {
    voiceBtn.classList.add("transcribing");
    voiceBtn.textContent = "…";

    voiceBtn.title =
      "Đang chuyển giọng nói thành chữ";

    voiceBtn.setAttribute(
      "aria-label",
      "Đang chuyển giọng nói thành chữ"
    );

    voiceBtn.setAttribute(
      "aria-pressed",
      "false"
    );

    voiceBtn.disabled = true;
    return;
  }

  voiceBtn.textContent = "🎤";
  voiceBtn.title = "Nhập bằng giọng nói";

  voiceBtn.setAttribute(
    "aria-label",
    "Nhập bằng giọng nói"
  );

  voiceBtn.setAttribute(
    "aria-pressed",
    "false"
  );

  voiceBtn.disabled = false;
}

function getSupportedVoiceMimeType() {
  if (!window.MediaRecorder) {
    return "";
  }

  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus"
  ];

  return (
    candidates.find((type) =>
      MediaRecorder.isTypeSupported(type)
    ) || ""
  );
}

async function transcribeVoiceBlob(audioBlob) {
  if (!audioBlob || audioBlob.size === 0) {
    throw new Error(
      "Không thu được dữ liệu âm thanh."
    );
  }

  const extension =
    audioBlob.type.includes("ogg")
      ? "ogg"
      : "webm";

  const audioFile = new File(
    [audioBlob],
    `voice-${Date.now()}.${extension}`,
    {
      type: audioBlob.type || "audio/webm"
    }
  );

  const formData = new FormData();

  formData.append(
    "audio",
    audioFile
  );

  const response = await fetch(
    "/transcribe",
    {
      method: "POST",
      body: formData
    }
  );

  let data;

  try {
    data = await response.json();
  } catch (error) {
    throw new Error(
      "Máy chủ trả về dữ liệu không hợp lệ."
    );
  }

  if (!response.ok) {
    throw new Error(
      data.error ||
      "Không thể nhận dạng giọng nói."
    );
  }

  return String(
    data.text || ""
  ).trim();
}

async function finishVoiceRecording() {
  isVoiceRecording = false;

  setVoiceButtonState("transcribing");

  setVoiceStatus(
    "Đang chuyển giọng nói thành chữ…"
  );

  const audioType =
    mediaRecorder?.mimeType ||
    "audio/webm";

  const audioBlob = new Blob(
    voiceChunks,
    {
      type: audioType
    }
  );

  voiceChunks = [];

  stopVoiceStream();

  try {
    const transcript =
      await transcribeVoiceBlob(audioBlob);

    if (!transcript) {
      throw new Error(
        "Không nghe rõ nội dung. Bạn hãy nói lại gần micro hơn."
      );
    }

    const currentText =
      chatInput.value.trim();

    chatInput.value =
      currentText
        ? `${currentText} ${transcript}`
        : transcript;

    autoResizeTextarea();
    chatInput.focus();

    setVoiceStatus(
      "Đã chuyển thành chữ. Bạn có thể kiểm tra rồi bấm gửi."
    );

    setTimeout(() => {
      if (
        voiceStatus &&
        voiceStatus.textContent.startsWith(
          "Đã chuyển thành chữ"
        )
      ) {
        setVoiceStatus("");
      }
    }, 3500);
  } catch (error) {
    console.error(
      "Voice transcription error:",
      error
    );

    setVoiceStatus(
      error.message ||
      "Không thể nhận dạng giọng nói.",
      true
    );
  } finally {
    mediaRecorder = null;
    setVoiceButtonState("idle");
  }
}

async function startVoiceRecording() {
  if (
    !navigator.mediaDevices?.getUserMedia ||
    !window.MediaRecorder
  ) {
    setVoiceStatus(
      "Trình duyệt chưa hỗ trợ ghi âm. Hãy dùng Chrome hoặc Edge mới nhất.",
      true
    );

    return;
  }

  try {
    setVoiceStatus(
      "Đang yêu cầu quyền sử dụng micro…"
    );

    voiceStream =
      await navigator.mediaDevices
        .getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        });

    const mimeType =
      getSupportedVoiceMimeType();

    mediaRecorder = mimeType
      ? new MediaRecorder(
          voiceStream,
          {
            mimeType
          }
        )
      : new MediaRecorder(voiceStream);

    voiceChunks = [];

    mediaRecorder.addEventListener(
      "dataavailable",
      (event) => {
        if (
          event.data &&
          event.data.size > 0
        ) {
          voiceChunks.push(event.data);
        }
      }
    );

    mediaRecorder.addEventListener(
      "stop",
      finishVoiceRecording,
      {
        once: true
      }
    );

    mediaRecorder.addEventListener(
      "error",
      (event) => {
        console.error(
          "MediaRecorder error:",
          event
        );

        isVoiceRecording = false;

        stopVoiceStream();
        setVoiceButtonState("idle");

        setVoiceStatus(
          "Ghi âm gặp lỗi. Hãy thử lại.",
          true
        );
      }
    );

    mediaRecorder.start(250);

    isVoiceRecording = true;

    setVoiceButtonState("recording");

    setVoiceStatus(
      "Đang nghe… Bấm nút ■ để dừng. Tối đa 60 giây."
    );

    voiceStopTimer = setTimeout(() => {
      if (
        mediaRecorder &&
        mediaRecorder.state === "recording"
      ) {
        mediaRecorder.stop();
      }
    }, 60000);
  } catch (error) {
    console.error(
      "Microphone permission error:",
      error
    );

    stopVoiceStream();
    setVoiceButtonState("idle");

    const permissionDenied =
      error?.name === "NotAllowedError" ||
      error?.name ===
        "PermissionDeniedError";

    setVoiceStatus(
      permissionDenied
        ? "Bạn chưa cho phép dùng micro. Hãy bấm biểu tượng ổ khóa trên thanh địa chỉ và bật quyền Micro."
        : "Không thể mở micro. Hãy kiểm tra micro và thử lại.",
      true
    );
  }
}

function toggleVoiceRecording() {
  if (isVoiceRecording) {
    if (
      mediaRecorder &&
      mediaRecorder.state === "recording"
    ) {
      mediaRecorder.stop();
    }

    return;
  }

  startVoiceRecording();
}

/* =========================================================
   ĐỌC CÂU TRẢ LỜI AI
========================================================= */

function speakAssistantText(text, button) {
  if (!("speechSynthesis" in window)) {
    alert(
      "Trình duyệt chưa hỗ trợ đọc văn bản."
    );

    return;
  }

  if (
    window.speechSynthesis.speaking &&
    activeSpeechButton === button
  ) {
    window.speechSynthesis.cancel();

    button.innerHTML = "🔊 Nghe";
    activeSpeechButton = null;

    return;
  }

  window.speechSynthesis.cancel();

  if (activeSpeechButton) {
    activeSpeechButton.innerHTML =
      "🔊 Nghe";
  }

  const utterance =
    new SpeechSynthesisUtterance(text);

  utterance.lang = "vi-VN";
  utterance.rate = 1;
  utterance.pitch = 1;

  const vietnameseVoice =
    window.speechSynthesis
      .getVoices()
      .find((voice) =>
        voice.lang
          .toLowerCase()
          .startsWith("vi")
      );

  if (vietnameseVoice) {
    utterance.voice =
      vietnameseVoice;
  }

  activeSpeechButton = button;

  button.innerHTML =
    "⏹ Dừng đọc";

  const resetButton = () => {
    button.innerHTML = "🔊 Nghe";

    if (
      activeSpeechButton === button
    ) {
      activeSpeechButton = null;
    }
  };

  utterance.onend = resetButton;
  utterance.onerror = resetButton;

  window.speechSynthesis.speak(
    utterance
  );
}

/* =========================================================
   HIỂN THỊ TIN NHẮN
========================================================= */

function escapeHtml(value) {
  const div =
    document.createElement("div");

  div.textContent =
    String(value ?? "");

  return div.innerHTML;
}

function formatMessage(value) {
  let html =
    escapeHtml(value);

  html = html.replace(
    /^### (.*)$/gm,
    "<h3>$1</h3>"
  );

  html = html.replace(
    /^## (.*)$/gm,
    "<h2>$1</h2>"
  );

  html = html.replace(
    /^# (.*)$/gm,
    "<h1>$1</h1>"
  );

  html = html.replace(
    /\*\*(.*?)\*\*/g,
    "<strong>$1</strong>"
  );

  html = html.replace(
    /`(.*?)`/g,
    "<code>$1</code>"
  );

  html = html.replace(
    /^- (.*)$/gm,
    "<li>$1</li>"
  );

  html = html.replace(
    /((?:<li>.*?<\/li>\s*)+)/gs,
    "<ul>$1</ul>"
  );

  html = html.replace(
    /\n/g,
    "<br>"
  );

  return html;
}

function getCurrentTime() {
  return new Intl.DateTimeFormat(
    "vi-VN",
    {
      hour: "2-digit",
      minute: "2-digit"
    }
  ).format(new Date());
}

function scrollChatToBottom() {
  if (!chatBody) {
    return;
  }

  chatBody.scrollTop =
    chatBody.scrollHeight;
}

function appendMessage(content, role, imageUrl = null) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "small-avatar";
    avatar.textContent = "🤖";
    row.appendChild(avatar);
  }

  /* Phải tạo bubble trước khi sử dụng bubble */
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (imageUrl) {
    const image = document.createElement("img");
    image.className = "message-image";
    image.src = imageUrl;
    image.alt = "Ảnh người dùng gửi";

    bubble.appendChild(image);
  }

  if (content) {
    const text = document.createElement("div");
    text.className = "ai-content";
    text.innerHTML = formatMessage(content);

    bubble.appendChild(text);

    if (role === "assistant") {
      const actions = document.createElement("div");
      actions.className = "message-actions";

      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-btn";
      copyBtn.innerHTML = "📋 Sao chép";

      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(content);

          copyBtn.innerHTML = "✅ Đã sao chép";

          setTimeout(() => {
            copyBtn.innerHTML = "📋 Sao chép";
          }, 1500);
        } catch (error) {
          console.error("Lỗi sao chép:", error);
        }
      });

      actions.appendChild(copyBtn);

      /* Chỉ thêm nút nghe khi đã có hàm voice */
      if (typeof speakAssistantText === "function") {
        const speakBtn = document.createElement("button");

        speakBtn.type = "button";
        speakBtn.className = "copy-btn speak-btn";
        speakBtn.innerHTML = "🔊 Nghe";

        speakBtn.addEventListener("click", () => {
          speakAssistantText(content, speakBtn);
        });

        actions.appendChild(speakBtn);
      }

      bubble.appendChild(actions);
    }
  }

  const time = document.createElement("time");

  time.textContent =
    `${getCurrentTime()}${role === "user" ? " ✓✓" : ""}`;

  bubble.appendChild(time);

  row.appendChild(bubble);
  chatBody.appendChild(row);

  scrollChatToBottom();
}

function appendTypingIndicator() {
  const row =
    document.createElement("div");

  row.className =
    "message-row assistant";

  row.innerHTML = `
    <div class="small-avatar">🤖</div>
    <div class="message-bubble typing-bubble">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;

  chatBody.appendChild(row);

  scrollChatToBottom();

  return row;
}

function autoResizeTextarea() {
  if (!chatInput) {
    return;
  }

  chatInput.style.height =
    "auto";

  chatInput.style.height =
    `${Math.min(
      chatInput.scrollHeight,
      130
    )}px`;
}

/* =========================================================
   ẢNH
========================================================= */

function clearSelectedImage() {
  selectedImage = null;

  if (selectedImageUrl) {
    URL.revokeObjectURL(
      selectedImageUrl
    );

    selectedImageUrl = null;
  }

  if (imageInput) {
    imageInput.value = "";
  }

  if (imagePreview) {
    imagePreview.src = "";
  }

  if (imageFileName) {
    imageFileName.textContent = "";
  }

  imagePreviewPanel?.classList.add(
    "hidden"
  );
}

attachImageBtn?.addEventListener(
  "click",
  () => {
    imageInput?.click();
  }
);

imageInput?.addEventListener(
  "change",
  () => {
    const file =
      imageInput.files?.[0];

    if (!file) {
      return;
    }

    const allowedTypes = [
      "image/jpeg",
      "image/png",
      "image/webp"
    ];

    if (
      !allowedTypes.includes(file.type)
    ) {
      alert(
        "Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP."
      );

      clearSelectedImage();
      return;
    }

    if (
      file.size >
      5 * 1024 * 1024
    ) {
      alert(
        "Ảnh không được vượt quá 5 MB."
      );

      clearSelectedImage();
      return;
    }

    selectedImage = file;

    selectedImageUrl =
      URL.createObjectURL(file);

    imagePreview.src =
      selectedImageUrl;

    imageFileName.textContent =
      file.name;

    imagePreviewPanel.classList.remove(
      "hidden"
    );
  }
);

removeImageBtn?.addEventListener(
  "click",
  clearSelectedImage
);

/* =========================================================
   GỬI CHAT
========================================================= */

function setGeneratingState(generating) {
  isGenerating = generating;

  if (generating) {
    sendBtn.innerHTML = "■";
    sendBtn.classList.add("stop");

    stopBtn?.classList.remove(
      "hidden"
    );
  } else {
    sendBtn.innerHTML = "➤";
    sendBtn.classList.remove("stop");

    stopBtn?.classList.add(
      "hidden"
    );
  }
}

function stopGeneratingAnswer() {
  if (controller) {
    controller.abort();
  }

  setGeneratingState(false);
}

async function sendMessage() {
  const message = chatInput.value.trim();

  if (isGenerating) {
    if (controller) {
      controller.abort();
    }

    return;
  }

  if (!message && !selectedImage) {
    return;
  }

  const imageToSend = selectedImage;
  const imageUrlForMessage = selectedImageUrl;

  controller = new AbortController();
  isGenerating = true;

  sendBtn.innerHTML = "■";
  sendBtn.classList.add("stop");
  stopBtn?.classList.remove("hidden");

  let typingIndicator = null;

  try {
    const userText =
      message || "Tôi gửi một ảnh cần tư vấn.";

    /* Hiển thị tin nhắn người dùng */
    appendMessage(
      userText,
      "user",
      imageUrlForMessage
    );

    chatInput.value = "";
    autoResizeTextarea();
    clearSelectedImage();

    typingIndicator = appendTypingIndicator();

    const formData = new FormData();

    formData.append(
      "message",
      message
    );

    formData.append(
      "history",
      JSON.stringify(conversationHistory)
    );

    if (imageToSend) {
      formData.append(
        "image",
        imageToSend
      );
    }

    const response = await fetch(
      "/chat",
      {
        method: "POST",
        body: formData,
        signal: controller.signal
      }
    );

    const responseText =
      await response.text();

    let data = {};

    try {
      data = responseText
        ? JSON.parse(responseText)
        : {};
    } catch (jsonError) {
      console.error(
        "Phản hồi không phải JSON:",
        responseText
      );

      throw new Error(
        "Máy chủ trả về dữ liệu không hợp lệ."
      );
    }

    typingIndicator?.remove();
    typingIndicator = null;

    if (!response.ok) {
      throw new Error(
        data.error ||
        `Máy chủ báo lỗi ${response.status}.`
      );
    }

    if (!data.reply) {
      throw new Error(
        "AI không trả về nội dung."
      );
    }

    appendMessage(
      data.reply,
      "assistant"
    );

    conversationHistory.push({
      role: "user",
      content: userText
    });

    conversationHistory.push({
      role: "assistant",
      content: data.reply
    });

    conversationHistory =
      conversationHistory.slice(-12);

    saveCurrentChat();

  } catch (error) {
    typingIndicator?.remove();

    console.error(
      "Lỗi gửi tin nhắn:",
      error
    );

    if (error.name === "AbortError") {
      appendMessage(
        "Đã dừng trả lời.",
        "assistant"
      );
    } else {
      appendMessage(
        error.message ||
        "Không thể kết nối với máy chủ Flask.",
        "assistant"
      );
    }

  } finally {
    isGenerating = false;
    controller = null;

    sendBtn.innerHTML = "➤";
    sendBtn.classList.remove("stop");

    stopBtn?.classList.add("hidden");
  }
}


/* Bấm nút gửi */
chatForm.addEventListener(
  "submit",
  function (event) {
    event.preventDefault();
    sendMessage();
  }
);


/* Tự thay đổi chiều cao ô nhập */
chatInput.addEventListener(
  "input",
  autoResizeTextarea
);


/* Enter để gửi, Shift + Enter để xuống dòng */
chatInput.addEventListener(
  "keydown",
  function (event) {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      sendMessage();
    }
  }
);


/* Nút dừng trả lời */
stopBtn?.addEventListener(
  "click",
  function () {
    if (controller) {
      controller.abort();
    }
  }
);
/* =========================================================
   NÚT GỢI Ý
========================================================= */

document
  .querySelectorAll(
    "[data-question]"
  )
  .forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        chatInput.value =
          button.dataset.question || "";

        autoResizeTextarea();
        chatInput.focus();
      }
    );
  });

document
  .querySelectorAll(
    "[data-specialty]"
  )
  .forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        const specialty =
          button.dataset.specialty;

        chatInput.value =
          `Tôi muốn được tư vấn về chuyên khoa ${specialty}.`;

        autoResizeTextarea();
        chatInput.focus();

        document
          .getElementById("tu-van")
          ?.scrollIntoView({
            behavior: "smooth",
            block: "center"
          });
      }
    );
  });

/* =========================================================
   VOICE EVENT
========================================================= */

voiceBtn?.addEventListener(
  "click",
  toggleVoiceRecording
);

window.addEventListener(
  "beforeunload",
  () => {
    stopVoiceStream();

    if (
      "speechSynthesis" in window
    ) {
      window.speechSynthesis.cancel();
    }
  }
);

/* =========================================================
   MODAL
========================================================= */

function openModal(modal) {
  if (!modal) {
    return;
  }

  modal.classList.add("show");

  modal.setAttribute(
    "aria-hidden",
    "false"
  );

  document.body.classList.add(
    "modal-open"
  );
}

function closeModal(modal) {
  if (!modal) {
    return;
  }

  modal.classList.remove("show");

  modal.setAttribute(
    "aria-hidden",
    "true"
  );

  document.body.classList.remove(
    "modal-open"
  );
}

openLoginBtn?.addEventListener(
  "click",
  () => {
    loginMessage.textContent = "";
    openModal(loginModal);
  }
);

closeLoginBtn?.addEventListener(
  "click",
  () => {
    closeModal(loginModal);
  }
);

openRegisterBtn?.addEventListener(
  "click",
  () => {
    closeModal(loginModal);
    registerMessage.textContent = "";
    openModal(registerModal);
  }
);

closeRegisterBtn?.addEventListener(
  "click",
  () => {
    closeModal(registerModal);
  }
);

backToLoginBtn?.addEventListener(
  "click",
  () => {
    closeModal(registerModal);
    openModal(loginModal);
  }
);

loginModal?.addEventListener(
  "click",
  (event) => {
    if (
      event.target === loginModal
    ) {
      closeModal(loginModal);
    }
  }
);

registerModal?.addEventListener(
  "click",
  (event) => {
    if (
      event.target === registerModal
    ) {
      closeModal(registerModal);
    }
  }
);

/* =========================================================
   ĐĂNG KÝ
========================================================= */

registerForm?.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    registerMessage.textContent =
      "Đang đăng ký…";

    registerMessage.className =
      "form-message";

    const payload = {
      full_name:
        document
          .getElementById(
            "registerName"
          )
          .value.trim(),

      email:
        document
          .getElementById(
            "registerEmail"
          )
          .value.trim(),

      phone:
        document
          .getElementById(
            "registerPhone"
          )
          .value.trim(),

      password:
        document
          .getElementById(
            "registerPassword"
          )
          .value,

      confirm_password:
        document
          .getElementById(
            "registerConfirmPassword"
          )
          .value
    };

    try {
      const response =
        await fetch(
          "/register",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json"
            },
            body:
              JSON.stringify(payload)
          }
        );

      const data =
        await response.json();

      if (!response.ok) {
        registerMessage.textContent =
          data.error ||
          "Đăng ký không thành công.";

        registerMessage.className =
          "form-message error";

        return;
      }

      registerMessage.textContent =
        "Đăng ký thành công.";

      registerMessage.className =
        "form-message success";

      registerForm.reset();

      setTimeout(() => {
        closeModal(registerModal);

        document
          .getElementById(
            "loginAccount"
          )
          .value = payload.email;

        openModal(loginModal);
      }, 800);
    } catch (error) {
      console.error(
        "Register error:",
        error
      );

      registerMessage.textContent =
        "Không thể kết nối với máy chủ.";

      registerMessage.className =
        "form-message error";
    }
  }
);

/* =========================================================
   ĐĂNG NHẬP
========================================================= */

loginForm?.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    loginMessage.textContent =
      "Đang đăng nhập…";

    loginMessage.className =
      "form-message";

    const payload = {
      account:
        document
          .getElementById(
            "loginAccount"
          )
          .value.trim(),

      password:
        document
          .getElementById(
            "loginPassword"
          )
          .value
    };

    try {
      const response =
        await fetch(
          "/login",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json"
            },
            body:
              JSON.stringify(payload)
          }
        );

      const data =
        await response.json();

      if (!response.ok) {
        loginMessage.textContent =
          data.error ||
          "Đăng nhập không thành công.";

        loginMessage.className =
          "form-message error";

        return;
      }

      loginMessage.textContent =
        "Đăng nhập thành công.";

      loginMessage.className =
        "form-message success";

      updateUserInterface(
        data.user
      );

      setTimeout(() => {
        closeModal(loginModal);
      }, 600);
    } catch (error) {
      console.error(
        "Login error:",
        error
      );

      loginMessage.textContent =
        "Không thể kết nối với máy chủ.";

      loginMessage.className =
        "form-message error";
    }
  }
);

function updateUserInterface(user) {
  if (user) {
    openLoginBtn?.classList.add(
      "hidden"
    );

    logoutBtn?.classList.remove(
      "hidden"
    );

    userName?.classList.remove(
      "hidden"
    );

    if (userName) {
      userName.textContent =
        `Xin chào, ${user.full_name}`;
    }
  } else {
    openLoginBtn?.classList.remove(
      "hidden"
    );

    logoutBtn?.classList.add(
      "hidden"
    );

    userName?.classList.add(
      "hidden"
    );

    if (userName) {
      userName.textContent = "";
    }
  }
}

async function checkCurrentUser() {
  try {
    const response =
      await fetch("/current-user");

    const data =
      await response.json();

    updateUserInterface(
      data.logged_in
        ? data.user
        : null
    );
  } catch (error) {
    console.error(
      "Current user error:",
      error
    );

    updateUserInterface(null);
  }
}

logoutBtn?.addEventListener(
  "click",
  async () => {
    try {
      await fetch(
        "/logout",
        {
          method: "POST"
        }
      );
    } catch (error) {
      console.error(
        "Logout error:",
        error
      );
    }

    updateUserInterface(null);
  }
);

/* =========================================================
   MENU ĐIỆN THOẠI
========================================================= */

mobileMenuBtn?.addEventListener(
  "click",
  () => {
    navLinks?.classList.toggle(
      "show"
    );
  }
);

dropdownTrigger?.addEventListener(
  "click",
  () => {
    dropdown?.classList.toggle(
      "open"
    );
  }
);

/* =========================================================
   DARK MODE
========================================================= */

function applyTheme(theme) {
  const useDark =
    theme === "dark";

  document.body.classList.toggle(
    "dark-mode",
    useDark
  );

  if (themeBtn) {
    themeBtn.textContent =
      useDark
        ? "☀️"
        : "🌙";

    themeBtn.title =
      useDark
        ? "Chuyển sang giao diện sáng"
        : "Chuyển sang giao diện tối";
  }
}

const savedTheme =
  localStorage.getItem(
    "medicareTheme"
  ) || "light";

applyTheme(savedTheme);

themeBtn?.addEventListener(
  "click",
  () => {
    const nextTheme =
      document.body.classList.contains(
        "dark-mode"
      )
        ? "light"
        : "dark";

    localStorage.setItem(
      "medicareTheme",
      nextTheme
    );

    applyTheme(nextTheme);
  }
);

/* =========================================================
   CUỘC TRÒ CHUYỆN MỚI
========================================================= */

const newChatBtn =
  document.getElementById("newChatBtn");

function resetCurrentChat() {
  chatBody.innerHTML = "";
  conversationHistory = [];
  currentChatId = Date.now();

  clearSelectedImage();
  setVoiceStatus("");

  if (
    "speechSynthesis" in window
  ) {
    window.speechSynthesis.cancel();
  }

  appendMessage(
    "Xin chào! Tôi là MediCare AI. Bạn muốn được hỗ trợ về triệu chứng sức khỏe, dinh dưỡng, vận động hay giấc ngủ?",
    "assistant"
  );

  chatInput.value = "";
  autoResizeTextarea();
  chatInput.focus();

  loadHistory();
}

newChatBtn?.addEventListener(
  "click",
  () => {
    saveCurrentChat();
    resetCurrentChat();
  }
);

/* =========================================================
   LƯU LỊCH SỬ
========================================================= */

function getChatTitle() {
  const firstUserMessage =
    chatBody.querySelector(
      ".message-row.user .ai-content"
    );

  const text =
    firstUserMessage?.textContent
      ?.trim();

  if (text) {
    return text.length > 38
      ? `${text.slice(0, 38)}…`
      : text;
  }

  return (
    "Cuộc trò chuyện " +
    new Date().toLocaleString(
      "vi-VN"
    )
  );
}

function saveChatSessions() {
  localStorage.setItem(
    "chatSessions",
    JSON.stringify(chatSessions)
  );
}
function getChatTitle() {
  const firstUserMessage =
    chatBody.querySelector(
      ".message-row.user .ai-content"
    );

  const title =
    firstUserMessage?.textContent?.trim();

  if (!title) {
    return "Cuộc trò chuyện mới";
  }

  return title.length > 38
    ? title.slice(0, 38) + "…"
    : title;
}
function saveCurrentChat() {
  if (
    !chatBody ||
    chatBody.innerHTML.trim() === ""
  ) {
    return;
  }

  const existing =
    chatSessions.find(
      (chat) =>
        chat.id === currentChatId
    );

  const sessionData = {
    id: currentChatId,
    title: getChatTitle(),
    content:
      chatBody.innerHTML,
    conversationHistory:
      conversationHistory,
    updatedAt:
      Date.now()
  };

  if (existing) {
    Object.assign(
      existing,
      sessionData
    );
  } else {
    chatSessions.push(
      sessionData
    );
  }

  saveChatSessions();
  loadHistory();
}

/* =========================================================
   XÓA VÀ MỞ LỊCH SỬ
========================================================= */

function closeHistoryMenus() {
  document
    .querySelectorAll(
      ".history-menu.show"
    )
    .forEach((menu) => {
      menu.classList.remove(
        "show"
      );
    });
}

function deleteChat(chatId) {
  const selectedChat =
    chatSessions.find(
      (chat) =>
        chat.id === chatId
    );

  if (!selectedChat) {
    return;
  }

  const confirmed =
    window.confirm(
      `Bạn có chắc muốn xóa "${selectedChat.title}" không?\n\nHành động này không thể hoàn tác.`
    );

  if (!confirmed) {
    return;
  }

  chatSessions =
    chatSessions.filter(
      (chat) =>
        chat.id !== chatId
    );

  saveChatSessions();

  if (
    currentChatId === chatId
  ) {
    resetCurrentChat();
  } else {
    loadHistory();
  }
}

function openSavedChat(chat) {
  saveCurrentChat();

  chatBody.innerHTML =
    chat.content || "";

  currentChatId =
    chat.id;

  conversationHistory =
    Array.isArray(
      chat.conversationHistory
    )
      ? chat.conversationHistory
      : [];

  loadHistory();
  scrollChatToBottom();
}

function loadHistory() {
  const historyList =
    document.getElementById(
      "historyList"
    );

  if (!historyList) {
    return;
  }

  historyList.innerHTML = "";

  if (
    chatSessions.length === 0
  ) {
    const emptyMessage =
      document.createElement(
        "div"
      );

    emptyMessage.className =
      "history-empty";

    emptyMessage.textContent =
      "Chưa có cuộc trò chuyện nào.";

    historyList.appendChild(
      emptyMessage
    );

    return;
  }

  const sortedSessions =
    [...chatSessions].sort(
      (a, b) =>
        (b.updatedAt || b.id) -
        (a.updatedAt || a.id)
    );

  sortedSessions.forEach(
    (chat) => {
      const row =
        document.createElement(
          "div"
        );

      row.className =
        "history-row";

      if (
        chat.id === currentChatId
      ) {
        row.classList.add(
          "active"
        );
      }

      const openButton =
        document.createElement(
          "button"
        );

      openButton.type =
        "button";

      openButton.className =
        "history-item";

      openButton.textContent =
        chat.title;

      openButton.title =
        chat.title;

      openButton.addEventListener(
        "click",
        (event) => {
          event.stopPropagation();

          closeHistoryMenus();

          openSavedChat(chat);
        }
      );

      const moreButton =
        document.createElement(
          "button"
        );

      moreButton.type =
        "button";

      moreButton.className =
        "history-more-btn";

      moreButton.textContent =
        "⋯";

      moreButton.title =
        "Tùy chọn";

      moreButton.setAttribute(
        "aria-label",
        `Tùy chọn cho ${chat.title}`
      );

      const menu =
        document.createElement(
          "div"
        );

      menu.className =
        "history-menu";

      const deleteButton =
        document.createElement(
          "button"
        );

      deleteButton.type =
        "button";

      deleteButton.className =
        "history-delete-btn";

      deleteButton.innerHTML = `
        <span aria-hidden="true">🗑</span>
        <span>Xóa</span>
      `;

      moreButton.addEventListener(
        "click",
        (event) => {
          event.stopPropagation();

          const shouldOpen =
            !menu.classList.contains(
              "show"
            );

          closeHistoryMenus();

          if (shouldOpen) {
            menu.classList.add(
              "show"
            );
          }
        }
      );

      deleteButton.addEventListener(
        "click",
        (event) => {
          event.stopPropagation();

          deleteChat(chat.id);
        }
      );

      menu.appendChild(
        deleteButton
      );

      row.appendChild(
        openButton
      );

      row.appendChild(
        moreButton
      );

      row.appendChild(menu);

      historyList.appendChild(
        row
      );
    }
  );
}

document.addEventListener(
  "click",
  closeHistoryMenus
);

/* =========================================================
   SIDEBAR
========================================================= */

document.addEventListener(
  "DOMContentLoaded",
  () => {
    const body =
      document.body;

    const sidebarOpenBtn =
      document.getElementById(
        "sidebarOpenBtn"
      );

    const sidebarCloseBtn =
      document.getElementById(
        "sidebarCloseBtn"
      );

    const sidebarOverlay =
      document.getElementById(
        "sidebarOverlay"
      );

    const sidebarNewChatBtn =
      document.getElementById(
        "sidebarNewChatBtn"
      );

    function setSidebarCollapsed(
      collapsed
    ) {
      body.classList.toggle(
        "sidebar-collapsed",
        collapsed
      );

      localStorage.setItem(
        "medicareSidebarCollapsed",
        String(collapsed)
      );
    }

    const savedState =
      localStorage.getItem(
        "medicareSidebarCollapsed"
      );

    const isMobile =
      window.matchMedia(
        "(max-width: 900px)"
      ).matches;

    if (
      savedState === "true" ||
      (
        savedState === null &&
        isMobile
      )
    ) {
      body.classList.add(
        "sidebar-collapsed"
      );
    }

    sidebarOpenBtn?.addEventListener(
      "click",
      () => {
        setSidebarCollapsed(false);
      }
    );

    sidebarCloseBtn?.addEventListener(
      "click",
      () => {
        setSidebarCollapsed(true);
      }
    );

    sidebarOverlay?.addEventListener(
      "click",
      () => {
        setSidebarCollapsed(true);
      }
    );

    sidebarNewChatBtn?.addEventListener(
  "click",
  function () {
    /* Lưu cuộc trò chuyện đang mở */
    if (typeof saveCurrentChat === "function") {
      saveCurrentChat();
    }

    /* Dừng câu trả lời đang chạy */
    if (controller) {
      controller.abort();
      controller = null;
    }

    isGenerating = false;

    if (sendBtn) {
      sendBtn.innerHTML = "➤";
      sendBtn.classList.remove("stop");
    }

    stopBtn?.classList.add("hidden");

    /* Dừng đọc giọng nói */
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    /* Tạo cuộc trò chuyện mới */
    chatBody.innerHTML = "";
    conversationHistory = [];
    currentChatId = Date.now();

    if (typeof clearSelectedImage === "function") {
      clearSelectedImage();
    }

    if (typeof setVoiceStatus === "function") {
      setVoiceStatus("");
    }

    appendMessage(
      "Xin chào! Tôi là MediCare AI. Bạn muốn được hỗ trợ về triệu chứng sức khỏe, dinh dưỡng, vận động hay giấc ngủ?",
      "assistant"
    );

    chatInput.value = "";

    if (typeof autoResizeTextarea === "function") {
      autoResizeTextarea();
    }

    if (typeof loadHistory === "function") {
      loadHistory();
    }

    chatInput.focus();

    /* Trên điện thoại thì đóng sidebar */
    if (
      window.matchMedia(
        "(max-width: 900px)"
      ).matches
    ) {
      setSidebarCollapsed(true);
    }
  }
);

    document.addEventListener(
      "keydown",
      (event) => {
        if (
          event.key === "Escape"
        ) {
          closeHistoryMenus();

          if (
            isVoiceRecording &&
            mediaRecorder?.state ===
              "recording"
          ) {
            mediaRecorder.stop();
          }

          setSidebarCollapsed(true);
        }
      }
    );
  }
);

/* =========================================================
   KHỞI TẠO
========================================================= */

loadHistory();
checkCurrentUser();
autoResizeTextarea();
setVoiceButtonState("idle");
/* =========================================================
   CẢNH BÁO TÌNH HUỐNG KHẨN CẤP
========================================================= */

function normalizeEmergencyText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}


function hasEmergencySigns(value) {
  let text = normalizeEmergencyText(value);

  if (!text) {
    return false;
  }

  /*
   * Loại bớt trường hợp người dùng phủ định triệu chứng:
   * "tôi không khó thở", "không bị đau ngực"...
   */
  const negativePatterns = [
    /\bkhong\s+(bi\s+)?kho tho\b/g,
    /\bchua\s+(bi\s+)?kho tho\b/g,

    /\bkhong\s+(bi\s+)?dau nguc\b/g,
    /\bchua\s+(bi\s+)?dau nguc\b/g,

    /\bkhong\s+(bi\s+)?chay mau\b/g,
    /\bchua\s+(bi\s+)?chay mau\b/g,

    /\bkhong\s+(bi\s+)?co giat\b/g,
    /\bchua\s+(bi\s+)?co giat\b/g
  ];

  negativePatterns.forEach((pattern) => {
    text = text.replace(pattern, "");
  });

  const emergencyKeywords = [
  /* Hô hấp */
  "khó thở",
  "khó thở nặng",
  "không thở được",
  "nghẹt thở",
  "thở gấp",
  "tím tái",
  "tím môi",

  /* Đau ngực */
  "đau ngực dữ dội",
  "đau thắt ngực",
  "tức ngực nặng",
  "đau ngực lan",
  "đau ngực kèm khó thở",

  /* Mất ý thức */
  "bất tỉnh",
  "mất ý thức",
  "không đánh thức được",
  "ngất xỉu",
  "hôn mê",

  /* Chảy máu */
  "chảy máu nhiều",
  "chảy máu không cầm",
  "không cầm được máu",
  "nôn ra máu",
  "đi ngoài ra máu",
  "phân đen",

  /* Thần kinh */
  "co giật",
  "méo miệng",
  "yếu liệt một bên",
  "nói khó đột ngột",
  "không nói được",
  "đau đầu dữ dội đột ngột",

  /* Dị ứng nặng */
  "sưng môi",
  "sưng lưỡi",
  "sưng họng",
  "phản vệ"
];

return emergencyKeywords.some((keyword) =>
  text.includes(
    normalizeEmergencyText(keyword)
  )
);
}


function showEmergencyAlert() {
  if (!chatBody) {
    return;
  }

  /*
   * Không hiển thị nhiều cảnh báo trùng nhau.
   */
  const oldAlert =
    document.getElementById("emergencyAlert");

  if (oldAlert) {
    oldAlert.remove();
  }

  const alertBox =
    document.createElement("div");

  alertBox.id = "emergencyAlert";
  alertBox.className = "emergency-alert";

  alertBox.setAttribute(
    "role",
    "alert"
  );

  alertBox.setAttribute(
    "aria-live",
    "assertive"
  );

  alertBox.innerHTML = `
    <div class="emergency-alert-icon">
      ⚠
    </div>

    <div class="emergency-alert-content">
      <strong>
        Có dấu hiệu cần cấp cứu
      </strong>

      <p>
        Hãy gọi 115 hoặc đến cơ sở y tế gần nhất ngay.
        Không nên chờ chatbot trả lời nếu tình trạng đang nghiêm trọng.
      </p>

      <div class="emergency-alert-actions">
        <a
          class="emergency-call-button"
          href="tel:115"
        >
          ☎ Gọi 115
        </a>

        <button
          class="emergency-close-button"
          id="closeEmergencyAlert"
          type="button"
        >
          Đóng
        </button>
      </div>
    </div>
  `;

  chatBody.appendChild(alertBox);

  const closeButton =
    alertBox.querySelector(
      "#closeEmergencyAlert"
    );

  closeButton?.addEventListener(
    "click",
    () => {
      alertBox.remove();
    }
  );

  /*
   * Cuộn xuống để người dùng nhìn thấy ngay.
   */
  if (
    typeof scrollChatToBottom === "function"
  ) {
    scrollChatToBottom();
  } else {
    chatBody.scrollTop =
      chatBody.scrollHeight;
  }
}


function checkEmergencyBeforeSending() {
  const message =
    chatInput?.value.trim() || "";

  if (!hasEmergencySigns(message)) {
    return;
  }

  /*
   * Chờ sendMessage thêm câu hỏi người dùng trước,
   * sau đó mới chèn cảnh báo đỏ bên dưới.
   */
  setTimeout(() => {
    showEmergencyAlert();
  }, 0);
}


/*
 * Bắt sự kiện khi bấm nút gửi.
 * true = chạy trước listener gửi tin nhắn hiện tại.
 */
chatForm?.addEventListener(
  "submit",
  checkEmergencyBeforeSending,
  true
);


/*
 * Bắt cả trường hợp nhấn Enter để gửi.
 */
chatInput?.addEventListener(
  "keydown",
  (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      checkEmergencyBeforeSending();
    }
  },
  true
);