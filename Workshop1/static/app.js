document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("chat-form");
    const userInput = document.getElementById("user-input");
    const chatMessages = document.getElementById("chat-messages");
    const clearBtn = document.getElementById("clear-btn");

    // History to maintain conversation context (Level 4)
    let conversationHistory = [];

    // Helper function to format timestamp (Level 6)
    function getCurrentTime() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    // Helper to format simple markdown-like text to HTML
    function formatMessage(text) {
        // Replace **bold** with <strong>bold</strong>
        let formatted = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Replace newlines with <br>
        formatted = formatted.replace(/\n/g, '<br>');
        return formatted;
    }

    // Append message to the chat container
    function appendMessage(sender, text, isSystem = false) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", sender === "user" ? "user-message" : "bot-message");

        const contentDiv = document.createElement("div");
        contentDiv.classList.add("message-content");
        contentDiv.innerHTML = formatMessage(text);

        const timeDiv = document.createElement("div");
        timeDiv.classList.add("message-time");
        timeDiv.textContent = isSystem ? "Hệ thống" : getCurrentTime();

        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timeDiv);
        chatMessages.appendChild(messageDiv);

        scrollToBottom();
    }

    // Auto scroll to bottom (Level 3)
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Show/hide typing indicator (Level 2)
    function showTypingIndicator() {
        const indicator = document.createElement("div");
        indicator.id = "typing-indicator";
        indicator.classList.add("message", "bot-message");
        indicator.innerHTML = `
            <div class="message-content">
                <div class="typing-indicator">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById("typing-indicator");
        if (indicator) {
            indicator.remove();
        }
    }

    // Handle form submission
    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const messageText = userInput.value.trim();
        if (!messageText) return;

        // Clear input field
        userInput.value = "";

        // Display user message
        appendMessage("user", messageText);

        // Show typing indicator
        showTypingIndicator();

        try {
            // Send request to Flask API
            const response = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    message: messageText,
                    history: conversationHistory
                }),
            });

            const data = await response.json();
            removeTypingIndicator();

            if (response.ok && data.reply) {
                // Add to history
                conversationHistory.push({ role: "user", content: messageText });
                conversationHistory.push({ role: "assistant", content: data.reply });

                // Display bot response
                appendMessage("bot", data.reply);
            } else {
                appendMessage("bot", "Lỗi: " + (data.error || "Không thể kết nối đến máy chủ AI."));
            }
        } catch (error) {
            removeTypingIndicator();
            appendMessage("bot", "Lỗi hệ thống: Không thể gửi yêu cầu.");
            console.error("Error:", error);
        }
    });

// Handle clear chat
clearBtn.addEventListener("click", (e) => {
    e.preventDefault(); // Ngăn nút clear submit form

    if (!confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử trò chuyện?")) {
        return;
    }

    // Xóa tin nhắn
    chatMessages.innerHTML = "";

    // Xóa lịch sử hội thoại
    conversationHistory = [];

    // Hiển thị lời chào mới
    appendMessage(
        "bot",
        "Lịch sử trò chuyện đã được xóa. Mình có thể giúp gì thêm cho bạn?",
        true
    );

    // Kích hoạt lại ô nhập
    userInput.disabled = false;
    userInput.value = "";
    userInput.focus();

    // Kích hoạt lại nút gửi nếu có
    const sendBtn = document.querySelector("#chat-form button[type='submit']");
if (sendBtn) {
    sendBtn.disabled = false;
}
});

// Đóng hàm DOMContentLoaded
});