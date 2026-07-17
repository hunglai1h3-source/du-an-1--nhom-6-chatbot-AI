const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatBody = document.getElementById("chatBody");
const sendBtn = document.getElementById("sendBtn");
let controller = null;
let isGenerating = false;

const imageInput = document.getElementById("imageInput");
const attachImageBtn = document.getElementById("attachImageBtn");
const imagePreviewPanel = document.getElementById("imagePreviewPanel");
const imagePreview = document.getElementById("imagePreview");
const imageFileName = document.getElementById("imageFileName");
const removeImageBtn = document.getElementById("removeImageBtn");

const openLoginBtn = document.getElementById("openLoginBtn");
const closeLoginBtn = document.getElementById("closeLoginBtn");
const loginModal = document.getElementById("loginModal");
const loginForm = document.getElementById("loginForm");
const loginMessage = document.getElementById("loginMessage");

const openRegisterBtn = document.getElementById("openRegisterBtn");
const closeRegisterBtn = document.getElementById("closeRegisterBtn");
const registerModal = document.getElementById("registerModal");
const registerForm = document.getElementById("registerForm");
const registerMessage = document.getElementById("registerMessage");
const backToLoginBtn = document.getElementById("backToLoginBtn");

const logoutBtn = document.getElementById("logoutBtn");
const userName = document.getElementById("userName");

const mobileMenuBtn = document.getElementById("mobileMenuBtn");
const navLinks = document.getElementById("navLinks");
const dropdown = document.querySelector(".dropdown");
const dropdownTrigger = document.querySelector(".dropdown-trigger");

let conversationHistory = [];
let selectedImage = null;
let selectedImageUrl = null;
let isSending = false;

let abortController = null;
let typingIndicator = null;

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function formatMessage(value) {

  let html = escapeHtml(value);


  // tiêu đề
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


  // danh sách
  html = html.replace(
    /^- (.*)$/gm,
    "<li>$1</li>"
  );


  html = html.replace(
    /(<li>.*<\/li>)/gs,
    "<ul>$1</ul>"
  );


  // in đậm
  html = html.replace(
    /\*\*(.*?)\*\*/g,
    "<strong>$1</strong>"
  );


  // code
  html = html.replace(
    /`(.*?)`/g,
    "<code>$1</code>"
  );


  html = html.replace(
    /\n/g,
    "<br>"
  );


  return html;

}

function getCurrentTime() {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());
}

function scrollChatToBottom() {
  chatBody.scrollTop = chatBody.scrollHeight;
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

    text.innerHTML =
        formatMessage(content);


    bubble.appendChild(text);


    if(role === "assistant"){

        const copyBtn =
        document.createElement("button");


        copyBtn.className =
        "copy-btn";


        copyBtn.innerHTML =
        "📋 Sao chép";


        copyBtn.onclick = () => {


            navigator.clipboard.writeText(content);


            copyBtn.innerHTML =
            "✅ Đã sao chép";


            setTimeout(()=>{

                copyBtn.innerHTML =
                "📋 Sao chép";

            },1500);


        };


        bubble.appendChild(copyBtn);

    }

}

  const time = document.createElement("time");
  time.textContent = `${getCurrentTime()}${role === "user" ? " ✓✓" : ""}`;
  bubble.appendChild(time);

  row.appendChild(bubble);
  chatBody.appendChild(row);
  scrollChatToBottom();
}

function appendTypingIndicator() {
  const row = document.createElement("div");
  row.className = "message-row assistant";

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
  chatInput.style.height = "auto";
  chatInput.style.height = `${Math.min(chatInput.scrollHeight, 130)}px`;
}

function clearSelectedImage() {
  selectedImage = null;

  if (selectedImageUrl) {
    URL.revokeObjectURL(selectedImageUrl);
    selectedImageUrl = null;
  }

  imageInput.value = "";
  imagePreview.src = "";
  imageFileName.textContent = "";
  imagePreviewPanel.classList.add("hidden");
}

attachImageBtn.addEventListener("click", () => {
  imageInput.click();
});

imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];

  if (!file) return;

  const allowedTypes = [
    "image/jpeg",
    "image/png",
    "image/webp"
  ];

  if (!allowedTypes.includes(file.type)) {
    alert("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.");
    clearSelectedImage();
    return;
  }

  if (file.size > 5 * 1024 * 1024) {
    alert("Ảnh không được vượt quá 5 MB.");
    clearSelectedImage();
    return;
  }

  selectedImage = file;
  selectedImageUrl = URL.createObjectURL(file);

  imagePreview.src = selectedImageUrl;
  imageFileName.textContent = file.name;
  imagePreviewPanel.classList.remove("hidden");
});

removeImageBtn.addEventListener("click", clearSelectedImage);

async function sendMessage() {

  if (isGenerating) {

    if (controller) {
      controller.abort();
    }

    isGenerating = false;
    sendBtn.innerHTML = "➤";
    sendBtn.classList.remove("stop");

    return;
  }


  const message = chatInput.value.trim();

  if (!message && !selectedImage) return;


  isGenerating = true;

  sendBtn.innerHTML = "■";
  sendBtn.classList.add("stop");


  controller = new AbortController();


  const imageToSend = selectedImage;
  const imageUrlForMessage = selectedImageUrl;


  appendMessage(
    message || "Tôi gửi một ảnh cần tư vấn.",
    "user",
    imageUrlForMessage
  );


  chatInput.value="";
  autoResizeTextarea();


  clearSelectedImage();


  const typingIndicator = appendTypingIndicator();


  try {


    const formData = new FormData();


    formData.append(
      "message",
      message
    );


    formData.append(
      "history",
      JSON.stringify(conversationHistory)
    );


    if(imageToSend){

      formData.append(
        "image",
        imageToSend
      );

    }



    const response = await fetch("/chat",{

      method:"POST",

      body:formData,

      signal:controller.signal

    });



    const data = await response.json();


    typingIndicator.remove();



    if(!response.ok){

      appendMessage(
        data.error || "AI đang lỗi.",
        "assistant"
      );

      return;

    }



    appendMessage(
      data.reply,
      "assistant"
    );



    conversationHistory.push({

      role:"user",

      content:message

    });


    conversationHistory.push({

      role:"assistant",

      content:data.reply

    });



    conversationHistory =
      conversationHistory.slice(-12);



  }


  catch(error){


    typingIndicator.remove();


    if(error.name==="AbortError"){


      appendMessage(
        "Đã dừng trả lời.",
        "assistant"
      );


    }else{


      console.error(error);


      appendMessage(
        "Không thể kết nối với máy chủ Flask.",
        "assistant"
      );


    }


  }


  finally{


    isGenerating=false;


    sendBtn.innerHTML="➤";


    sendBtn.classList.remove("stop");


    controller=null;


  }


}

chatForm.addEventListener("submit", event => {
  event.preventDefault();
  sendMessage();
});

chatInput.addEventListener("input", autoResizeTextarea);

chatInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

document.querySelectorAll("[data-question]").forEach(button => {
  button.addEventListener("click", () => {
    chatInput.value = button.dataset.question;
    autoResizeTextarea();
    chatInput.focus();
  });
});

document.querySelectorAll("[data-specialty]").forEach(button => {
  button.addEventListener("click", () => {
    const specialty = button.dataset.specialty;

    chatInput.value =
      `Tôi muốn được tư vấn về chuyên khoa ${specialty}.`;

    autoResizeTextarea();
    chatInput.focus();

    document.getElementById("tu-van").scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
  });
});

function openModal(modal) {
  modal.classList.add("show");
  document.body.classList.add("modal-open");
}

function closeModal(modal) {
  modal.classList.remove("show");
  document.body.classList.remove("modal-open");
}

openLoginBtn.addEventListener("click", () => {
  loginMessage.textContent = "";
  openModal(loginModal);
});

closeLoginBtn.addEventListener("click", () => {
  closeModal(loginModal);
});

openRegisterBtn.addEventListener("click", () => {
  closeModal(loginModal);
  registerMessage.textContent = "";
  openModal(registerModal);
});

closeRegisterBtn.addEventListener("click", () => {
  closeModal(registerModal);
});

backToLoginBtn.addEventListener("click", () => {
  closeModal(registerModal);
  openModal(loginModal);
});

registerForm.addEventListener("submit", async event => {
  event.preventDefault();

  registerMessage.textContent = "Đang đăng ký...";
  registerMessage.className = "form-message";

  const payload = {
    full_name: document.getElementById("registerName").value.trim(),
    email: document.getElementById("registerEmail").value.trim(),
    phone: document.getElementById("registerPhone").value.trim(),
    password: document.getElementById("registerPassword").value,
    confirm_password:
      document.getElementById("registerConfirmPassword").value
  };

  try {
    const response = await fetch("/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
      registerMessage.textContent =
        data.error || "Đăng ký không thành công.";

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
      document.getElementById("loginAccount").value = payload.email;
      openModal(loginModal);
    }, 800);

  } catch (error) {
    registerMessage.textContent =
      "Không thể kết nối với máy chủ.";

    registerMessage.className =
      "form-message error";
  }
});

loginForm.addEventListener("submit", async event => {
  event.preventDefault();

  loginMessage.textContent = "Đang đăng nhập...";
  loginMessage.className = "form-message";

  const payload = {
    account: document.getElementById("loginAccount").value.trim(),
    password: document.getElementById("loginPassword").value
  };

  try {
    const response = await fetch("/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
      loginMessage.textContent =
        data.error || "Đăng nhập không thành công.";

      loginMessage.className =
        "form-message error";

      return;
    }

    loginMessage.textContent = "Đăng nhập thành công.";
    loginMessage.className = "form-message success";

    updateUserInterface(data.user);

    setTimeout(() => {
      closeModal(loginModal);
    }, 600);

  } catch (error) {
    loginMessage.textContent =
      "Không thể kết nối với máy chủ.";

    loginMessage.className =
      "form-message error";
  }
});

function updateUserInterface(user) {
  if (user) {
    openLoginBtn.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
    userName.classList.remove("hidden");
    userName.textContent = `Xin chào, ${user.full_name}`;
  } else {
    openLoginBtn.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
    userName.classList.add("hidden");
    userName.textContent = "";
  }
}

async function checkCurrentUser() {
  const response = await fetch("/current-user");
  const data = await response.json();

  updateUserInterface(
    data.logged_in ? data.user : null
  );
}

logoutBtn.addEventListener("click", async () => {
  await fetch("/logout", {
    method: "POST"
  });

  updateUserInterface(null);
});

mobileMenuBtn.addEventListener("click", () => {
  navLinks.classList.toggle("show");
});

dropdownTrigger.addEventListener("click", () => {
  dropdown.classList.toggle("open");
});
// Tạo cuộc trò chuyện mới
const newChatBtn = document.getElementById("newChatBtn");

if (newChatBtn) {

    newChatBtn.addEventListener("click", () => {


        // Xóa nội dung chat
        chatBody.innerHTML = "";


        // Xóa lịch sử hội thoại
        conversationHistory = [];


        // Xóa ảnh đang chọn
        clearSelectedImage();


        // Hiện lời chào mới
        appendMessage(
            "Xin chào! Tôi là MediCare AI. Bạn muốn được hỗ trợ về triệu chứng sức khỏe, dinh dưỡng, vận động hay giấc ngủ?",
            "assistant"
        );


        chatInput.value = "";

        autoResizeTextarea();


    });

}
checkCurrentUser();


