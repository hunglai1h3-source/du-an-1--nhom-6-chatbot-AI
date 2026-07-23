"use strict";

const M = window.MediCare;
const $ = M.$;
const $$ = M.$$;
let activeCategory = "all";

function normalized(value) {
  return String(value || "").toLocaleLowerCase("vi-VN").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function updateAskLinks() {
  const query = $("#knowledgeSearch").value.trim();
  const prompt = query ? `Hãy giải thích và hướng dẫn tôi về: ${query}` : "Tôi muốn hỏi về một chủ đề sức khỏe";
  const href = `/tu-van?prompt=${encodeURIComponent(prompt)}`;
  $("#askAIFromSearch").href = href;
  $("#emptyAskAI").href = href;
}

function filterArticles() {
  const query = normalized($("#knowledgeSearch").value.trim());
  let visible = 0;
  $$(".knowledge-card").forEach((card) => {
    const categoryMatch = activeCategory === "all" || card.dataset.category === activeCategory;
    const haystack = normalized(`${card.dataset.keywords} ${card.textContent}`);
    const queryMatch = !query || haystack.includes(query);
    const show = categoryMatch && queryMatch;
    card.classList.toggle("hidden", !show);
    if (show) visible += 1;
  });
  $("#knowledgeResultCount").textContent = `${visible} bài viết`;
  $("#knowledgeGrid").classList.toggle("hidden", visible === 0);
  $("#knowledgeEmpty").classList.toggle("hidden", visible !== 0);
  updateAskLinks();
}

function openArticle(card) {
  const modal = $("#articleModal");
  const title = $("h3", card).textContent.trim();
  const tag = $(".card-tag", card).textContent.trim();
  const summary = $("p", card).textContent.trim();
  const list = $$('li', card).map((item) => `<li>${M.escapeHTML(item.textContent.trim())}</li>`).join("");
  $("#articleModalTag").textContent = tag;
  $("#articleModalTitle").textContent = title;
  $("#articleModalContent").innerHTML = `<p>${M.escapeHTML(summary)}</p><ul>${list}</ul><p><strong>Lưu ý:</strong> Nội dung này chỉ hỗ trợ theo dõi ban đầu. Khi triệu chứng nặng, kéo dài hoặc có dấu hiệu bất thường, hãy đi khám.</p>`;
  const askLink = $(".card-actions a", card);
  $("#articleModalAskAI").href = askLink?.href || `/tu-van?prompt=${encodeURIComponent(title)}`;
  modal.classList.remove("hidden");
}

function closeArticle() {
  $("#articleModal").classList.add("hidden");
}

async function renderProfileContext() {
  const user = await M.currentUser();
  if (user.logged_in) await M.syncProfiles(user.user).catch(() => {});
  const profile = M.getSelectedProfile();
  $("#knowledgeProfileAvatar").textContent = M.initials(profile.name);
  $("#knowledgeProfileName").textContent = profile.name;
  $("#knowledgeProfileMeta").textContent = `${profile.age} tuổi · ${profile.gender} · ${profile.relationship}`;
}

document.addEventListener("DOMContentLoaded", async () => {
  await M.bindAccountButton($("#accountButton"));
  const current = await M.currentUser();
  $("#accountAvatar").textContent = current.logged_in ? M.initials(current.user.full_name) : "K";
  await renderProfileContext();

  $("#knowledgeSearch").addEventListener("input", filterArticles);
  $("#clearKnowledgeSearch").addEventListener("click", () => { $("#knowledgeSearch").value = ""; filterArticles(); $("#knowledgeSearch").focus(); });
  $$('[data-category]').forEach((button) => button.addEventListener("click", () => {
    activeCategory = button.dataset.category;
    $$('[data-category]').forEach((item) => item.classList.toggle("active", item === button));
    filterArticles();
  }));
  $$('[data-search-topic]').forEach((button) => button.addEventListener("click", () => {
    activeCategory = "all";
    $$('[data-category]').forEach((item) => item.classList.toggle("active", item.dataset.category === "all"));
    $("#knowledgeSearch").value = button.dataset.searchTopic;
    filterArticles();
    $("#knowledgeSearch").scrollIntoView({ behavior: "smooth", block: "center" });
  }));
  $$('[data-read-article]').forEach((button) => button.addEventListener("click", () => openArticle(button.closest(".knowledge-card"))));
  $("#closeArticleModal").addEventListener("click", closeArticle);
  $("#articleModal").addEventListener("click", (event) => { if (event.target.id === "articleModal") closeArticle(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeArticle(); });
  window.addEventListener("medicare:profile-changed", renderProfileContext);
  filterArticles();
});
