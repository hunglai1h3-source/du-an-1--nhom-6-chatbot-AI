const chatBox = document.getElementById("chatBox");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const clearChatButton = document.getElementById("clearChatButton");

const imageInput = document.getElementById("imageInput");
const imageButton = document.getElementById("imageButton");
const imagePreview = document.getElementById("imagePreview");
const imagePreviewContainer = document.getElementById(
    "imagePreviewContainer"
);
const removeImageButton = document.getElementById(
    "removeImageButton"
);

const quickQuestions = document.querySelectorAll(
    ".quick-question"
);

let selectedImage = null;
let conversationHistory = [];

const allowedImageTypes = [
    "image/jpeg",
    "image/png",
    "image/webp"
];

const maximumImageSize = 5 * 1024 * 1024;


function getCurrentTime() {
    return new Date().toLocaleTimeString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit"
    });
}


function createMessage(role, text, imageData = null) {
    const messageRow = document.createElement("div");

    messageRow.className =
        role === "user"
            ? "message-row user-row"
            : "message-row bot-row";

    if (role !== "user") {
        const avatar = document.createElement("div");

        avatar.className = "message-avatar";
        avatar.textContent = "AI";

        messageRow.appendChild(avatar);
    }

    const content = document.createElement("div");
    content.className = "message-content";

    const message = document.createElement("div");

    message.className =
        role === "user"
            ? "message user-message"
            : "message bot-message";

    if (imageData) {
        const image = document.createElement("img");

        image.src = imageData;
        image.alt = "Ảnh người dùng gửi";
        image.className = "message-image";

        message.appendChild(image);
    }

    if (text) {
        const textNode = document.createElement("div");

        textNode.textContent = text;
        message.appendChild(textNode);
    }

    const time = document.createElement("span");

    time.className = "message-time";
    time.textContent = getCurrentTime();

    content.appendChild(message);
    content.appendChild(time);
    messageRow.appendChild(content);

    chatBox.appendChild(messageRow);
    scrollToBottom();
}


function scrollToBottom() {
    chatBox.scrollTop = chatBox.scrollHeight;
}


function showTypingIndicator() {
    const row = document.createElement("div");

    row.id = "typingIndicator";
    row.className = "message-row bot-row";

    row.innerHTML = `
        <div class="message-avatar">AI</div>

        <div class="message-content">
            <div class="message bot-message">
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;

    chatBox.appendChild(row);
    scrollToBottom();
}


function removeTypingIndicator() {
    const typingIndicator =
        document.getElementById("typingIndicator");

    if (typingIndicator) {
        typingIndicator.remove();
    }
}


function clearSelectedImage() {
    selectedImage = null;
    imageInput.value = "";
    imagePreview.src = "";
    imagePreviewContainer.hidden = true;
}


imageButton.addEventListener("click", () => {
    imageInput.click();
});


imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];

    if (!file) {
        return;
    }

    if (!allowedImageTypes.includes(file.type)) {
        alert("Chỉ chấp nhận ảnh JPG, PNG hoặc WEBP.");
        clearSelectedImage();
        return;
    }

    if (file.size > maximumImageSize) {
        alert("Dung lượng ảnh không được vượt quá 5 MB.");
        clearSelectedImage();
        return;
    }

    const reader = new FileReader();

    reader.onload = event => {
        selectedImage = event.target.result;
        imagePreview.src = selectedImage;
        imagePreviewContainer.hidden = false;
    };

    reader.readAsDataURL(file);
});


removeImageButton.addEventListener("click", () => {
    clearSelectedImage();
});


quickQuestions.forEach(button => {
    button.addEventListener("click", () => {
        messageInput.value = button.dataset.message;
        messageInput.focus();
    });
});


messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";

    messageInput.style.height =
        Math.min(messageInput.scrollHeight, 120) + "px";
});


async function sendMessage() {
    const message = messageInput.value.trim();

    if (!message && !selectedImage) {
        messageInput.focus();
        return;
    }

    const currentImage = selectedImage;

    const userText =
        message || "Hãy hỗ trợ phân tích ảnh này.";

    createMessage(
        "user",
        userText,
        currentImage
    );

    messageInput.value = "";
    messageInput.style.height = "auto";

    clearSelectedImage();

    sendButton.disabled = true;
    imageButton.disabled = true;

    showTypingIndicator();

    try {
        const response = await fetch("/chat", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: userText,
                image: currentImage,
                history: conversationHistory
            })
        });

        const data = await response.json();

        removeTypingIndicator();

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Không thể kết nối với hệ thống."
            );
        }

        createMessage("assistant", data.reply);

        conversationHistory.push({
            role: "user",
            content: userText
        });

        conversationHistory.push({
            role: "assistant",
            content: data.reply
        });

    } catch (error) {
        removeTypingIndicator();

        createMessage(
            "assistant",
            "Hệ thống đang gặp lỗi. Vui lòng thử lại sau."
        );

        console.error(error);

    } finally {
        sendButton.disabled = false;
        imageButton.disabled = false;
        messageInput.focus();
    }
}


sendButton.addEventListener("click", sendMessage);


messageInput.addEventListener("keydown", event => {
    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {
        event.preventDefault();
        sendMessage();
    }
});


clearChatButton.addEventListener("click", () => {
    const confirmClear = confirm(
        "Bạn có muốn xóa toàn bộ cuộc trò chuyện không?"
    );

    if (!confirmClear) {
        return;
    }

    conversationHistory = [];
    clearSelectedImage();

    chatBox.innerHTML = `
        <div class="message-row bot-row">
            <div class="message-avatar">AI</div>

            <div class="message-content">
                <div class="message bot-message">
                    Cuộc trò chuyện đã được làm mới.
                    Bạn đang gặp vấn đề sức khỏe gì?
                </div>

                <span class="message-time">
                    ${getCurrentTime()}
                </span>
            </div>
        </div>
    `;
});