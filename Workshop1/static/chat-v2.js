"use strict";

const $ = (selector) =>
  document.querySelector(selector);

const $$ = (selector) =>
  [...document.querySelectorAll(selector)];

let chatHistory = [];
let currentProfile = null;
let currentUser = null;
let selectedImage = null;
let selectedSpecialty = "";

function initials(name) {
  const parts = String(name || "Khách")
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (!parts.length) {
    return "K";
  }

  return parts
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function sexLabel(value) {
  if (value === "male") {
    return "Nam";
  }

  if (value === "female") {
    return "Nữ";
  }

  return "Chưa cập nhật";
}

function showToast(message) {
  const toast = $("#toast");

  toast.textContent = message;
  toast.classList.add("show");

  window.clearTimeout(showToast.timer);

  showToast.timer = window.setTimeout(() => {
    toast.classList.remove("show");
  }, 2800);
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options
  });

  const data = await response
    .json()
    .catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.error ||
      `Lỗi HTTP ${response.status}`
    );
  }

  return data;
}

function addMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  const content = document.createElement("div");
  content.textContent = text;

  const time = document.createElement("time");
  time.className = "message-time";

  time.textContent =
    new Date().toLocaleTimeString(
      "vi-VN",
      {
        hour: "2-digit",
        minute: "2-digit"
      }
    );

  bubble.append(content, time);
  row.appendChild(bubble);

  $("#chatMessages").appendChild(row);

  $("#chatMessages").scrollTop =
    $("#chatMessages").scrollHeight;
}

function renderProfile() {
  const name =
    currentUser?.full_name ||
    "Chưa đăng nhập";

  const profile =
    currentProfile?.profile || {};

  const weight =
    currentProfile?.latest_weight_kg;

  const avatar = initials(name);

  $("#accountAvatar").textContent = avatar;
  $("#accountName").textContent = name;

  $("#profileAvatar").textContent = avatar;
  $("#rightProfileAvatar").textContent = avatar;

  $("#profileName").textContent = name;
  $("#rightProfileName").textContent = name;

  $("#profileAge").textContent =
    profile.age ?? "--";

  $("#rightProfileAge").textContent =
    profile.age ?? "--";

  $("#profileSex").textContent =
    sexLabel(profile.sex);

  $("#rightProfileSex").textContent =
    sexLabel(profile.sex);

  $("#profileHeight").textContent =
    profile.height_cm
      ? `${profile.height_cm} cm`
      : "-- cm";

  $("#rightProfileHeight").textContent =
    profile.height_cm
      ? `${profile.height_cm} cm`
      : "-- cm";

  $("#profileWeight").textContent =
    weight
      ? `${weight} kg`
      : "-- kg";

  $("#rightProfileWeight").textContent =
    weight
      ? `${weight} kg`
      : "-- kg";

  $("#rightProfileAllergies").textContent =
    profile.allergies || "Không";

  $("#rightProfileConditions").textContent =
    profile.medical_notes || "Không";

  const contextParts = [
    profile.age
      ? `${profile.age} tuổi`
      : "Chưa cập nhật tuổi",

    sexLabel(profile.sex),

    profile.height_cm
      ? `${profile.height_cm} cm`
      : "Chưa cập nhật chiều cao",

    weight
      ? `${weight} kg`
      : "Chưa cập nhật cân nặng"
  ];

  if (profile.allergies) {
    contextParts.push(
      `Dị ứng: ${profile.allergies}`
    );
  }

  if (profile.medical_notes) {
    contextParts.push(
      `Bệnh nền: ${profile.medical_notes}`
    );
  }

  $("#profileContextBar").textContent =
    contextParts.join(" • ");
}

async function loadProfile() {
  try {
    const userData =
      await requestJSON("/current-user");

    if (!userData.logged_in) {
      currentUser = null;
      currentProfile = {
        profile: null,
        latest_weight_kg: null
      };

      renderProfile();
      return;
    }

    currentUser = userData.user;

    currentProfile =
      await requestJSON(
        "/api/health/profile"
      );

    renderProfile();
  } catch (error) {
    console.error(error);

    showToast(
      "Không tải được hồ sơ sức khỏe."
    );
  }
}

function openProfileModal() {
  if (!currentUser) {
    showToast(
      "Bạn cần đăng nhập trước khi cập nhật hồ sơ."
    );

    return;
  }

  const profile =
    currentProfile?.profile || {};

  $("#profileFormSex").value =
    profile.sex || "";

  $("#profileFormAge").value =
    profile.age || "";

  $("#profileFormHeight").value =
    profile.height_cm || "";

  $("#profileFormWeight").value =
    currentProfile?.latest_weight_kg || "";

  $("#profileFormActivity").value =
    profile.activity_level ||
    "sedentary";

  $("#profileFormGoal").value =
    profile.goal ||
    "maintain";

  $("#profileFormAllergies").value =
    profile.allergies || "";

  $("#profileFormConditions").value =
    profile.medical_notes || "";

  $("#profileFormMessage").textContent =
    "";

  $("#profileModal").classList.remove(
    "hidden"
  );
}

function closeProfileModal() {
  $("#profileModal").classList.add(
    "hidden"
  );
}

async function saveProfile(event) {
  event.preventDefault();

  const message =
    $("#profileFormMessage");

  message.textContent = "Đang lưu...";

  const weight = Number(
    $("#profileFormWeight").value
  );

  const profilePayload = {
    sex:
      $("#profileFormSex").value,

    age:
      Number(
        $("#profileFormAge").value
      ),

    height_cm:
      Number(
        $("#profileFormHeight").value
      ),

    activity_level:
      $("#profileFormActivity").value,

    goal:
      $("#profileFormGoal").value,

    diet_preference: "",

    allergies:
      $("#profileFormAllergies")
        .value
        .trim(),

    medical_notes:
      $("#profileFormConditions")
        .value
        .trim()
  };

  try {
    await requestJSON(
      "/api/health/profile",
      {
        method: "PUT",
        headers: {
          "Content-Type":
            "application/json"
        },
        body:
          JSON.stringify(
            profilePayload
          )
      }
    );

    await requestJSON(
      "/api/health/weight",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body:
          JSON.stringify({
            weight_kg: weight,
            note:
              "Cập nhật từ hồ sơ sức khỏe"
          })
      }
    );

    message.style.color = "#078844";

    message.textContent =
      "Đã cập nhật hồ sơ thành công.";

    await loadProfile();

    window.setTimeout(() => {
      closeProfileModal();

      message.style.color = "";
    }, 700);
  } catch (error) {
    console.error(error);

    message.style.color = "#c32c2c";
    message.textContent = error.message;
  }
}

function openSpecialty() {
  $("#specialtyArea").classList.remove(
    "hidden"
  );

  $("#specialtyArea").scrollIntoView({
    behavior: "smooth",
    block: "nearest"
  });
}

function closeSpecialty() {
  $("#specialtyArea").classList.add(
    "hidden"
  );
}

function selectSpecialty(value) {
  selectedSpecialty = value;

  $("#selectedSpecialtyText").textContent =
    `Chuyên khoa: ${value}`;

  $("#selectedSpecialty").classList.remove(
    "hidden"
  );

  closeSpecialty();
}

function removeSpecialty() {
  selectedSpecialty = "";

  $("#selectedSpecialty").classList.add(
    "hidden"
  );
}

async function sendMessage(event) {
  event.preventDefault();

  const input = $("#messageInput");

  const rawMessage =
    input.value.trim();

  if (!rawMessage && !selectedImage) {
    showToast(
      "Bạn chưa nhập câu hỏi hoặc chọn ảnh."
    );

    return;
  }

  let finalMessage = rawMessage;

  if (selectedSpecialty) {
    finalMessage =
      `[Chuyên khoa đã chọn: ${selectedSpecialty}]\n` +
      rawMessage;
  }

  addMessage(
    "user",
    rawMessage ||
    "Đã gửi một hình ảnh."
  );

  input.value = "";
  input.style.height = "auto";

  $("#sendButton").disabled = true;

  let responseData;

  try {
    if (selectedImage) {
      const formData =
        new FormData();

      formData.append(
        "message",
        finalMessage
      );

      formData.append(
        "history",
        JSON.stringify(
          chatHistory.slice(-12)
        )
      );

      formData.append(
        "image",
        selectedImage
      );

      responseData =
        await requestJSON(
          "/chat",
          {
            method: "POST",
            body: formData
          }
        );
    } else {
      responseData =
        await requestJSON(
          "/chat",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json"
            },
            body:
              JSON.stringify({
                message: finalMessage,
                history:
                  chatHistory.slice(-12)
              })
          }
        );
    }

    addMessage(
      "assistant",
      responseData.reply
    );

    chatHistory.push({
      role: "user",
      content: finalMessage
    });

    chatHistory.push({
      role: "assistant",
      content: responseData.reply
    });

    selectedImage = null;

    $("#imageInput").value = "";

    $("#selectedFile")
      .classList
      .add("hidden");
  } catch (error) {
    console.error(error);

    addMessage(
      "assistant",
      `Không thể gửi câu hỏi: ${error.message}`
    );
  } finally {
    $("#sendButton").disabled = false;
    input.focus();
  }
}

function resetChat() {
  chatHistory = [];

  $("#chatMessages").innerHTML = "";

  const name =
    currentUser?.full_name ||
    "bạn";

  addMessage(
    "assistant",
    `Xin chào ${name}! Bạn hãy mô tả triệu chứng hoặc câu hỏi sức khỏe cần tư vấn.`
  );
}

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    await loadProfile();

    resetChat();

    const params =
      new URLSearchParams(
        window.location.search
      );

    const prompt =
      params.get("prompt");

    if (prompt) {
      $("#messageInput").value = prompt;
    }

    if (
      params.get("editProfile") === "1"
    ) {
      openProfileModal();
    }

    if (
      params.get("openSpecialty") === "1"
    ) {
      openSpecialty();
    }

    $("#chatForm").addEventListener(
      "submit",
      sendMessage
    );

    $("#newChatButton").addEventListener(
      "click",
      resetChat
    );

    $("#editProfileButton").addEventListener(
      "click",
      openProfileModal
    );

    $("#openProfileButton").addEventListener(
      "click",
      openProfileModal
    );

    $("#rightEditProfileButton").addEventListener(
      "click",
      openProfileModal
    );

    $("#closeProfileModal").addEventListener(
      "click",
      closeProfileModal
    );

    $("#profileModal").addEventListener(
      "click",
      (event) => {
        if (
          event.target.id ===
          "profileModal"
        ) {
          closeProfileModal();
        }
      }
    );

    $("#profileForm").addEventListener(
      "submit",
      saveProfile
    );

    $("#chooseSpecialtyButton").addEventListener(
      "click",
      openSpecialty
    );

    $("#rightSpecialtyButton").addEventListener(
      "click",
      openSpecialty
    );

    $("#closeSpecialtyButton").addEventListener(
      "click",
      closeSpecialty
    );

    $("#removeSpecialtyButton").addEventListener(
      "click",
      removeSpecialty
    );

    $$("[data-specialty]").forEach(
      (button) => {
        button.addEventListener(
          "click",
          () => {
            selectSpecialty(
              button.dataset.specialty
            );
          }
        );
      }
    );

    $$("[data-prompt]").forEach(
      (button) => {
        button.addEventListener(
          "click",
          () => {
            $("#messageInput").value =
              button.dataset.prompt;

            $("#messageInput").focus();
          }
        );
      }
    );

    $("#imageButton").addEventListener(
      "click",
      () => {
        $("#imageInput").click();
      }
    );

    $("#imageInput").addEventListener(
      "change",
      () => {
        selectedImage =
          $("#imageInput").files[0] ||
          null;

        if (selectedImage) {
          $("#selectedFile").textContent =
            `Ảnh đã chọn: ${selectedImage.name}`;

          $("#selectedFile")
            .classList
            .remove("hidden");
        }
      }
    );

    $("#messageInput").addEventListener(
      "input",
      () => {
        const input =
          $("#messageInput");

        input.style.height = "auto";

        input.style.height =
          `${Math.min(
            input.scrollHeight,
            120
          )}px`;
      }
    );

    $("#messageInput").addEventListener(
      "keydown",
      (event) => {
        if (
          event.key === "Enter" &&
          !event.shiftKey
        ) {
          event.preventDefault();

          $("#chatForm").requestSubmit();
        }
      }
    );

    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key === "Escape") {
          closeProfileModal();
          closeSpecialty();
        }
      }
    );
  }
);