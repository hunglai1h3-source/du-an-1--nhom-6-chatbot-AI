"use strict";
 
 
 
 const M = window.MediCare;
 
 const $ = M.$;
 
 const $$ = M.$$;
 
 
 
 let editingFamilyMember = null;
 
 let familyModalBound = false;
 
 
 
 function familyRawFromProfile(profile) {
 
   return {
 
     id: profile.serverId,
 
     full_name: profile.name,
 
     relationship: profile.relationship || "Khác",
 
     age: profile.age === "--" ? null : profile.age,
 
     gender: profile.gender === "Chưa cập nhật" ? "" : profile.gender,
 
     height_cm: profile.height || null,
 
     weight_kg: profile.weight || null,
 
     medical_conditions: profile.condition === "Không" ? "" : (profile.condition || ""),
 
     allergies: profile.allergies === "Không" ? "" : (profile.allergies || "")
 
   };
 
 }
 
 
 
 function profileCard(profile, selected) {
 
   const isFamilyMember = Boolean(profile.serverId);
 
   const actionButtons = isFamilyMember
 
     ? `
 
       <div class="family-card-actions">
 
         <button type="button" class="edit-family-button" data-edit-family="${profile.serverId}">✏ Sửa</button>
 
         <button type="button" class="delete-family-button" data-delete-family="${profile.serverId}">🗑 Xóa</button>
 
       </div>`
 
     : `
 
       <div class="family-card-actions">
 
         <button type="button" class="edit-self-profile" data-edit-self-profile>✏ Cập nhật hồ sơ</button>
 
       </div>`;
 
 
 
   return `
 
     <article
 
       class="family-card ${profile.id === selected?.id ? "selected" : ""}"
 
       data-profile-id="${M.escapeHTML(profile.id)}"
 
       tabindex="0"
 
       role="button"
 
       aria-label="Chọn hồ sơ ${M.escapeHTML(profile.name)}"
 
     >
 
       ${profile.id === selected?.id ? '<span class="selected-check">✓</span>' : ""}
 
       <div class="family-top">
 
         <span class="family-avatar">${M.escapeHTML(M.initials(profile.name))}</span>
 
         <div>
 
           <strong>${M.escapeHTML(profile.name)}</strong>
 
           <small>${M.escapeHTML(profile.age)} tuổi · ${M.escapeHTML(profile.gender)} · ${M.escapeHTML(profile.relationship)}</small>
 
         </div>
 
       </div>
 
       <span class="family-status">${M.escapeHTML(profile.status || profile.condition || "Chưa cập nhật")}</span>
 
       <div class="family-details">
 
         <p><span>Bệnh nền</span><b>${M.escapeHTML(profile.condition || "Không")}</b></p>
 
         <p><span>Dị ứng</span><b>${M.escapeHTML(profile.allergies || "Không")}</b></p>
 
         <p><span>Chiều cao</span><b>${profile.height || "--"} cm</b></p>
 
         <p><span>Cân nặng</span><b>${profile.weight || "--"} kg</b></p>
 
       </div>
 
       ${actionButtons}
 
       <footer>
 
         <span>◉ ${profile.relationship === "Bản thân" ? "Hồ sơ cá nhân" : "Hồ sơ gia đình"}</span>
 
         <span>${profile.id === selected?.id ? "Đang được chọn" : "Chọn để tư vấn"}</span>
 
       </footer>
 
     </article>`;
 
 }
 
 
 
 function renderProfiles() {
 
   const grid = $("#familyGrid");
 
   const profiles = M.getProfiles();
 
   const selected = profiles.length ? M.getSelectedProfile() : null;

   const familyCountMini = $("#familyCountMini");
   const sidebarName = $("#sidebarName");
   const sidebarMeta = $("#sidebarMeta");
   const sidebarAvatar = $("#sidebarAvatar");

   if (familyCountMini) familyCountMini.textContent = `${profiles.length} hồ sơ`;
   if (sidebarName) sidebarName.textContent = selected?.name || "Chưa có hồ sơ";
   if (sidebarMeta) sidebarMeta.textContent = selected
     ? `${selected.age} tuổi · ${selected.gender}`
     : "Đăng nhập để quản lý";
   if (sidebarAvatar) sidebarAvatar.textContent = selected ? M.initials(selected.name) : "--";

   if (!grid) return;
 
   window.familyMembersCache = profiles
 
     .filter((profile) => profile.serverId)
 
     .map(familyRawFromProfile);
 
 
 
   const emptyState = profiles.length
 
     ? ""
 
     : `
 
       <div class="empty-family-state">
 
         <strong>Chưa có hồ sơ sức khỏe</strong>
 
         <span>Đăng nhập để tải hồ sơ của bạn hoặc thêm thành viên gia đình.</span>
 
       </div>`;
 
 
 
   grid.innerHTML = `${emptyState}${profiles.map((profile) => profileCard(profile, selected)).join("")}
 
     <button class="add-family-card" id="addFamilyButton" type="button">
 
       <span>＋</span><strong>Thêm<br>thành viên</strong>
 
     </button>`;
 
 
 
 
 
 
   $$('[data-profile-id]', grid).forEach((card) => {
 
     const choose = (event) => {
 
       if (event?.target?.closest("button, a")) return;
 
       M.selectProfile(card.dataset.profileId);
 
       renderProfiles();
 
       renderRecommendations(M.readJSON(M.KEYS.locationContext, null));
 
       M.showToast(`Đã chọn hồ sơ ${M.getSelectedProfile().name}.`, "success");
 
     };
 
 
 
     card.addEventListener("click", choose);
 
     card.addEventListener("keydown", (event) => {
 
       if (["Enter", " "].includes(event.key)) {
 
         event.preventDefault();
 
         choose(event);
 
       }
 
     });
 
   });
 
 
 
   $("#addFamilyButton")?.addEventListener("click", async () => {
 
     const auth = await M.currentUser();
 
     if (!auth.logged_in) {
 
       $("#accountButton")?.click();
 
       return;
 
     }
 
     window.openFamilyCreateModal?.();
 
   });
 
 
 
   $$('[data-edit-family]', grid).forEach((button) => {
 
     button.addEventListener("click", (event) => {
 
       event.stopPropagation();
 
       const member = window.familyMembersCache.find(
 
         (item) => String(item.id) === String(button.dataset.editFamily)
 
       );
 
       if (member) window.openFamilyEditor?.(member);
 
     });
 
   });
 
 
 
   $$('[data-delete-family]', grid).forEach((button) => {
 
     button.addEventListener("click", async (event) => {
 
       event.stopPropagation();
 
       const member = window.familyMembersCache.find(
 
         (item) => String(item.id) === String(button.dataset.deleteFamily)
 
       );
 
       if (member) await deleteFamilyMember(member, button);
 
     });
 
   });
 
 
 
   $$('[data-edit-self-profile]', grid).forEach((button) => {
 
     button.addEventListener("click", (event) => {
 
       event.stopPropagation();
 
       window.openSelfHealthModal?.();
 
     });
 
   });
 
 }
 
 
 
 async function refreshProfilesFromServer() {
 
   const auth = await M.currentUser();
 
   if (auth.logged_in) await M.syncProfiles(auth.user);
 
   renderProfiles();
 
 }
 
 
 
 async function deleteFamilyMember(member, sourceButton = null) {
 
   const confirmed = window.confirm(`Bạn có chắc muốn xóa hồ sơ của ${member.full_name} không?`);
 
   if (!confirmed) return;
 
 
 
   const oldText = sourceButton?.textContent;
 
   try {
 
     if (sourceButton) {
 
       sourceButton.disabled = true;
 
       sourceButton.textContent = "Đang xóa...";
 
     }
 
 
 
     const response = await fetch(`/api/family/${member.id}`, {
 
       method: "DELETE",
 
       credentials: "same-origin"
 
     });
 
     const data = await response.json().catch(() => ({}));
 
     if (!response.ok) throw new Error(data.error || "Không thể xóa hồ sơ.");
 
 
 
     const selected = M.getSelectedProfile();
 
     if (String(selected.serverId) === String(member.id)) {
 
       localStorage.removeItem(M.KEYS.selectedProfile);
 
     }
 
 
 
     await refreshProfilesFromServer();
 
     M.showToast("Đã xóa hồ sơ thành viên.", "success");
 
   } catch (error) {
 
     M.showToast(error.message, "error");
 
   } finally {
 
     if (sourceButton) {
 
       sourceButton.disabled = false;
 
       sourceButton.textContent = oldText || "🗑 Xóa";
 
     }
 
   }
 
 }
 
 
 
 function bindFamilyModal() {
 
   if (familyModalBound) return;
 
   familyModalBound = true;
 
 
 
   const modal = $("#familyModal");
 
   const form = $("#familyForm");
 
   const closeButton = $("#closeFamilyModal");
 
   const deleteButton = $("#deleteFamilyButton");
 
   const saveButton = $("#saveFamilyButton");
 
   const title = $("#familyModalTitle");
 
   const message = $("#familyFormMessage");
 
 
 
   if (!modal || !form) {
 
     console.error("Không tìm thấy #familyModal hoặc #familyForm.");
 
     return;
 
   }
 
 
 
   function resetForm() {
 
     form.reset();
 
     editingFamilyMember = null;
 
     $("#familyMemberId").value = "";
 
     title.textContent = "Thêm thành viên gia đình";
 
     message.textContent = "";
 
     deleteButton?.classList.add("hidden");
 
     if (saveButton) {
 
       saveButton.disabled = false;
 
       saveButton.textContent = "Lưu thành viên";
 
     }
 
   }
 
 
 
   function closeModal() {
 
     modal.classList.add("hidden");
 
     resetForm();
 
   }
 
 
 
   function openCreateModal() {
 
     resetForm();
 
     modal.classList.remove("hidden");
 
     setTimeout(() => $("#familyFullName")?.focus(), 80);
 
   }
 
 
 
   function openEditor(member) {
 
     if (!member) return;
 
     editingFamilyMember = member;
 
     $("#familyMemberId").value = member.id || "";
 
     $("#familyFullName").value = member.full_name || "";
 
     $("#familyRelationship").value = member.relationship || "";
 
     $("#familyAge").value = member.age ?? "";
 
     $("#familyGender").value = member.gender || "";
 
     $("#familyHeight").value = member.height_cm ?? "";
 
     $("#familyWeight").value = member.weight_kg ?? "";
 
     $("#familyConditions").value = member.medical_conditions || "";
 
     $("#familyAllergies").value = member.allergies || "";
 
     title.textContent = "Cập nhật thành viên gia đình";
 
     saveButton.textContent = "Cập nhật hồ sơ";
 
     deleteButton?.classList.remove("hidden");
 
     modal.classList.remove("hidden");
 
   }
 
 
 
   window.openFamilyCreateModal = openCreateModal;
 
   window.openFamilyEditor = openEditor;
 
 
 
   closeButton?.addEventListener("click", closeModal);
 
   modal.addEventListener("click", (event) => {
 
     if (event.target === modal) closeModal();
 
   });
 
 
 
   form.addEventListener("submit", async (event) => {
 
     event.preventDefault();
 
     const memberId = editingFamilyMember?.id;
 
     const body = {
 
       full_name: $("#familyFullName").value.trim(),
 
       relationship: $("#familyRelationship").value,
 
       age: $("#familyAge").value || null,
 
       gender: $("#familyGender").value,
 
       height_cm: $("#familyHeight").value || null,
 
       weight_kg: $("#familyWeight").value || null,
 
       medical_conditions: $("#familyConditions").value.trim(),
 
       allergies: $("#familyAllergies").value.trim()
 
     };
 
 
 
     if (!body.full_name || !body.relationship) {
 
       message.textContent = "Vui lòng nhập họ tên và chọn quan hệ.";
 
       return;
 
     }
 
 
 
     try {
 
       saveButton.disabled = true;
 
       saveButton.textContent = memberId ? "Đang cập nhật..." : "Đang lưu...";
 
       const response = await fetch(memberId ? `/api/family/${memberId}` : "/api/family", {
 
         method: memberId ? "PUT" : "POST",
 
         credentials: "same-origin",
 
         headers: { "Content-Type": "application/json" },
 
         body: JSON.stringify(body)
 
       });
 
       const data = await response.json().catch(() => ({}));
 
       if (!response.ok) throw new Error(data.error || "Không thể lưu hồ sơ.");
 
 
 
       closeModal();
 
       await refreshProfilesFromServer();
 
       M.showToast(memberId ? "Đã cập nhật hồ sơ." : "Đã thêm thành viên.", "success");
 
     } catch (error) {
 
       message.textContent = error.message;
 
     } finally {
 
       saveButton.disabled = false;
 
       saveButton.textContent = editingFamilyMember ? "Cập nhật hồ sơ" : "Lưu thành viên";
 
     }
 
   });
 
 
 
   deleteButton?.addEventListener("click", async () => {
 
     if (!editingFamilyMember) return;
 
     const member = editingFamilyMember;
 
     closeModal();
 
     await deleteFamilyMember(member);
 
   });
 
 
 
   document.addEventListener("keydown", (event) => {
 
     if (event.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
 
   });
 
 }
 
 
 
 async function openSelfHealthModal() {
 
   const auth = await M.currentUser();
 
   if (!auth.logged_in) {
 
     $("#accountButton")?.click();
 
     return;
 
   }
 
 
 
   const modal = $("#selfHealthModal");
 
   const message = $("#selfHealthMessage");
 
   if (!modal || !message) return;
 
 
 
   message.textContent = "Đang tải hồ sơ...";
 
   modal.classList.remove("hidden");
 
 
 
   try {
 
     const response = await fetch("/api/health/profile", { credentials: "same-origin" });
 
     const data = await response.json().catch(() => ({}));
 
     if (!response.ok) throw new Error(data.error || "Không tải được hồ sơ.");
 
 
 
     const profile = data.profile || {};
 
     $("#selfHealthSex").value = profile.sex || "";
 
     $("#selfHealthAge").value = profile.age || "";
 
     $("#selfHealthHeight").value = profile.height_cm || "";
 
     $("#selfHealthWeight").value = data.latest_weight_kg || "";
 
     $("#selfHealthActivity").value = profile.activity_level || "sedentary";
 
     $("#selfHealthGoal").value = profile.goal || "maintain";
 
     $("#selfHealthAllergies").value = profile.allergies || "";
 
     $("#selfHealthConditions").value = profile.medical_notes || "";
 
     message.textContent = "";
 
   } catch (error) {
 
     message.textContent = error.message;
 
   }
 
 }
 
 
 
 function bindSelfHealthModal() {
 
   const modal = $("#selfHealthModal");
 
   const form = $("#selfHealthForm");
 
   if (!modal || !form) return;
 
 
 
   const close = () => modal.classList.add("hidden");
 
   window.openSelfHealthModal = openSelfHealthModal;
 
 
 
   $("#closeSelfHealthModal")?.addEventListener("click", close);
 
   $("#openSelfHealthButton")?.addEventListener("click", openSelfHealthModal);
 
   modal.addEventListener("click", (event) => {
 
     if (event.target === modal) close();
 
   });
 
 
 
   form.addEventListener("submit", async (event) => {
 
     event.preventDefault();
 
     const message = $("#selfHealthMessage");
 
     const submitButton = form.querySelector('button[type="submit"]');
 
 
 
     try {
 
       submitButton.disabled = true;
 
       submitButton.textContent = "Đang lưu...";
 
       message.textContent = "";
 
 
 
       const profileResponse = await fetch("/api/health/profile", {
 
         method: "PUT",
 
         credentials: "same-origin",
 
         headers: { "Content-Type": "application/json" },
 
         body: JSON.stringify({
 
           sex: $("#selfHealthSex").value,
 
           age: Number($("#selfHealthAge").value),
 
           height_cm: Number($("#selfHealthHeight").value),
 
           activity_level: $("#selfHealthActivity").value,
 
           goal: $("#selfHealthGoal").value,
 
           diet_preference: "",
 
           allergies: $("#selfHealthAllergies").value.trim(),
 
           medical_notes: $("#selfHealthConditions").value.trim()
 
         })
 
       });
 
       const profileData = await profileResponse.json().catch(() => ({}));
 
       if (!profileResponse.ok) throw new Error(profileData.error || "Không thể cập nhật hồ sơ.");
 
 
 
       const weightResponse = await fetch("/api/health/weight", {
 
         method: "POST",
 
         credentials: "same-origin",
 
         headers: { "Content-Type": "application/json" },
 
         body: JSON.stringify({
 
           weight_kg: Number($("#selfHealthWeight").value),
 
           note: "Cập nhật từ Trang chủ"
 
         })
 
       });
 
       const weightData = await weightResponse.json().catch(() => ({}));
 
       if (!weightResponse.ok) throw new Error(weightData.error || "Không thể cập nhật cân nặng.");
 
 
 
       const current = await M.currentUser();
 
       if (current.logged_in) await M.syncProfiles(current.user);
 
       renderProfiles();
 
       renderRecommendations(M.readJSON(M.KEYS.locationContext, null));
 
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
 
 
 
   document.addEventListener("keydown", (event) => {
 
     if (event.key === "Escape" && !modal.classList.contains("hidden")) close();
 
   });
 
 }
 
 
 
 function renderRecentChats() {
 
   const recentList = $("#recentList");
   if (!recentList) return;

   const sessions = M.readJSON(M.KEYS.chats, []);
 
   const items = Array.isArray(sessions)
 
     ? sessions.slice().reverse().slice(0, 5)
 
     : [];
 
 
 
   recentList.innerHTML = items.length
 
     ? items.map((session, index) => {
 
         const firstUser = session.messages?.find((message) => message.role === "user")?.content || "Mở lại cuộc trò chuyện";
 
         return `
 
           <a class="recent-item ${index === 0 ? "active" : ""}" href="/tu-van" data-chat-id="${M.escapeHTML(session.id || "")}">
 
             <span class="recent-icon">💬</span>
 
             <span><strong>${M.escapeHTML(session.title || "Cuộc tư vấn")}</strong><small>${M.escapeHTML(firstUser)}</small></span>
 
             <time>${new Date(session.updatedAt || Date.now()).toLocaleDateString("vi-VN")}</time>
 
           </a>`;
 
       }).join("")
 
     : '<p class="empty-recent">Chưa có cuộc tư vấn nào.</p>';
 
 
 
   $$('[data-chat-id]').forEach((link) => {
 
     link.addEventListener("click", () => {
 
       if (link.dataset.chatId) localStorage.setItem(M.KEYS.currentChat, link.dataset.chatId);
 
     });
 
   });
 
 }
 
 
 
 function renderRecommendations(context) {
 
   const profile = M.getProfiles().length ? M.getSelectedProfile() : null;
 
   const list = $("#recommendationList");
 
   if (!list) return;
 
   if (!profile) {
 
     list.innerHTML = "<li>Đăng nhập và tạo hồ sơ để nhận khuyến nghị cá nhân hóa.</li>";
 
     return;
 
   }
 
 
 
   const items = [];
 
   const aqi = Number(context?.aqi);
 
   const temperature = Number(context?.temperature);
 
   const condition = String(profile.condition || "").toLowerCase();
 
 
 
   if (Number.isFinite(aqi) && aqi > 60) items.push("Hạn chế ở ngoài trời lâu và ưu tiên khẩu trang lọc bụi phù hợp.");
 
   else if (Number.isFinite(aqi)) items.push("Chất lượng không khí hiện chưa ở mức cao; vẫn nên theo dõi trước khi ra ngoài lâu.");
 
   else items.push("Bấm Làm mới để nhận khuyến nghị theo thời tiết và chất lượng không khí.");
 
 
 
   if (condition.includes("hen") || condition.includes("hô hấp")) {
 
     items.push(`${profile.name} có bệnh hô hấp: tránh khói, bụi và theo dõi ho, khò khè hoặc khó thở.`);
 
   }
 
   if (Number.isFinite(temperature) && temperature >= 35) items.push("Nhiệt độ cao: tránh nắng gắt, uống đủ nước và nghỉ nơi thoáng mát.");
 
   if (condition.includes("huyết áp")) items.push("Người có tăng huyết áp nên hạn chế thay đổi nhiệt độ đột ngột và dùng thuốc đúng chỉ định.");
 
   items.push(`Khuyến nghị đang áp dụng cho ${profile.name}.`);
 
 
 
   list.innerHTML = items.slice(0, 4).map((item) => `<li>${M.escapeHTML(item)}</li>`).join("");
 
 }
 
 
 
 function googleMapUrl(context = M.readJSON(M.KEYS.locationContext, null)) {
 
   return M.mapsSearchUrl(context);
 
 }
 
 
 
 function openGoogleMaps(context = M.readJSON(M.KEYS.locationContext, null)) {
 
   window.open(googleMapUrl(context), "_blank", "noopener,noreferrer");
 
 }
 
 
 
 function renderGooglePharmacy(context) {
 
   const list = $(".pharmacy-list");
 
   if (list) {
 
     list.innerHTML = `
 
       <article class="google-map-card">
 
         <span>G</span>
 
         <div>
 
           <strong>Tìm nhà thuốc trên Google Maps</strong>
 
           <small>${M.escapeHTML(context?.short_address || "Google Maps sẽ dùng vị trí thiết bị của bạn")}</small>
 
         </div>
 
         <button type="button" id="openGooglePharmacy">Mở Maps</button>
 
       </article>
 
       <p class="google-map-note">Kết quả, khoảng cách và giờ mở cửa do Google Maps cung cấp.</p>`;
 
     $("#openGooglePharmacy")?.addEventListener("click", () => openGoogleMaps(context));
 
   }
 
 
 
   const iframe = $("#googlePharmacyMap");
 
   if (iframe) {
 
     const query = context?.latitude && context?.longitude
 
       ? `nhà thuốc gần ${context.latitude},${context.longitude}`
 
       : "nhà thuốc gần tôi";
 
     iframe.src = `https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;
 
   }
 
 }
 
 
 
 function renderLocation(context) {
 
   if (!context) {
 
     renderRecommendations(null);
 
     renderGooglePharmacy(null);
 
     return;
 
   }
 
 
 
   const weather = M.weatherCode(context.weather_code);
 
   const aqi = M.aqiLevel(context.aqi);
 
   const accuracy = Number(context.accuracy_m);
 
 
 
   $("#weatherIcon").textContent = weather.icon;
 
   $("#weatherDescription").textContent = weather.text;
 
   $("#temperatureValue").textContent = Number.isFinite(Number(context.temperature)) ? `${Math.round(context.temperature)}°C` : "--°C";
 
   $("#aqiValue").textContent = Number.isFinite(Number(context.aqi)) ? Math.round(context.aqi) : "--";
 
   $("#aqiLevel").textContent = aqi.text;
 
   $("#pm25Value").textContent = Number.isFinite(Number(context.pm25)) ? Number(context.pm25).toFixed(1) : "--";
 
   $("#humidityValue").textContent = Number.isFinite(Number(context.humidity)) ? `${Math.round(context.humidity)}%` : "--%";
 
   $("#windValue").textContent = Number.isFinite(Number(context.wind_speed)) ? `${Math.round(context.wind_speed)} km/h` : "-- km/h";
 
   $("#feelsLikeValue").textContent = Number.isFinite(Number(context.apparent_temperature)) ? `${Math.round(context.apparent_temperature)}°C` : "--°C";
 
   $("#weatherLocation").innerHTML = `${M.escapeHTML(context.short_address || "Vị trí hiện tại")}${Number.isFinite(accuracy) ? `<span class="location-accuracy">±${Math.round(accuracy)} m</span>` : ""}`;
 
   $("#pharmacyLocation").textContent = `Google Maps · ${context.short_address || "vị trí hiện tại"}`;
 
   $("#environmentUpdatedAt").textContent = `Cập nhật ${new Date(context.updated_at || Date.now()).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
 
   $("#sideAqiText").textContent = `AQI ${Number.isFinite(Number(context.aqi)) ? Math.round(context.aqi) : "--"} · Mức ${aqi.text.toLowerCase()} tại ${context.short_address || "vị trí hiện tại"}.`;
 
   $("#sideAqiBadge").textContent = `AQI ${Number.isFinite(Number(context.aqi)) ? Math.round(context.aqi) : "--"}`;
 
 
 
   renderRecommendations(context);
 
   renderGooglePharmacy(context);
 
 }
 
 
 
 async function refreshLocation(force = true) {
 
   const button = $("#refreshEnvironment");
 
   if (!button) return;
 
   button.disabled = true;
 
   button.textContent = "Đang định vị...";
 
   try {
 
     const context = await M.loadLocationContext({
 
       force,
 
       onProgress: ({ stage, position }) => {
 
         if (stage === "position") {
 
           $("#weatherLocation").textContent = `Đang tối ưu vị trí · độ chính xác ±${Math.round(position.coords.accuracy)} m`;
 
         } else {
 
           $("#weatherLocation").textContent = "Đang tải địa chỉ, thời tiết và không khí...";
 
         }
 
       }
 
     });
 
     renderLocation(context);
 
     M.showToast("Đã cập nhật vị trí và dữ liệu môi trường.", "success");
 
   } catch (error) {
 
     $("#weatherLocation").textContent = "Chưa xác định được vị trí";
 
     renderGooglePharmacy(null);
 
     M.showToast(error.message, "error");
 
   } finally {
 
     button.disabled = false;
 
     button.textContent = "Làm mới";
 
   }
 
 }
 
 
 
 
 
 // =========================================================
 
 // THÔNG BÁO LỊCH NHẮC TRÊN TRÌNH DUYỆT
 
 // Hoạt động khi website đang mở hoặc đang chạy nền trong trình duyệt.
 
 // =========================================================
 
 let reminderPollTimer = null;
 
 let reminderServiceWorker = null;
 
 
 
 async function registerReminderServiceWorker() {
 
   if (!("serviceWorker" in navigator)) return null;
 
 
 
   try {
 
     reminderServiceWorker = await navigator.serviceWorker.register("/static/sw.js");
 
     return reminderServiceWorker;
 
   } catch (error) {
 
     console.warn("Không đăng ký được service worker:", error);
 
     return null;
 
   }
 
 }
 
 
 
 async function enableReminderNotifications({ showMessage = true } = {}) {
 
   if (!("Notification" in window)) {
 
     if (showMessage) M.showToast("Trình duyệt này không hỗ trợ thông báo.", "error");
 
     return false;
 
   }
 
 
 
   if (!window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname)) {
 
     if (showMessage) M.showToast("Thông báo chỉ hoạt động trên HTTPS hoặc localhost.", "error");
 
     return false;
 
   }
 
 
 
   let permission = Notification.permission;
 
   if (permission === "default") permission = await Notification.requestPermission();
 
 
 
   if (permission !== "granted") {
 
     if (showMessage) M.showToast("Bạn chưa cho phép MediCare gửi thông báo.", "error");
 
     return false;
 
   }
 
 
 
   await registerReminderServiceWorker();
 
   localStorage.setItem("medicareReminderNotificationsEnabled", "1");
 
   if (showMessage) M.showToast("Đã bật thông báo lịch nhắc.", "success");
 
   return true;
 
 }
 
 
 
 async function showReminderNotification(item) {
 
   const title = `🔔 ${item.title || "Lịch nhắc sức khỏe"}`;
 
   const parts = [];
 
   if (item.message) parts.push(item.message);
 
   if (item.medicine_name) parts.push(`Thuốc: ${item.medicine_name}`);
 
   if (item.dosage_note) parts.push(item.dosage_note);
 
   const body = parts.join(" · ") || `Đã đến giờ ${item.time_of_day || "thực hiện lịch nhắc"}.`;
 
 
 
   const options = {
 
     body,
 
     icon: "/static/favicon.png",
 
     badge: "/static/favicon.png",
 
     tag: `medicare-reminder-${item.id}-${new Date().toISOString().slice(0, 10)}`,
 
     renotify: true,
 
     data: { url: "/", reminderId: item.id },
 
     vibrate: [200, 100, 200]
 
   };
 
 
 
   try {
 
     const registration = reminderServiceWorker || await registerReminderServiceWorker();
 
     if (registration?.showNotification) {
 
       await registration.showNotification(title, options);
 
     } else {
 
       new Notification(title, options);
 
     }
 
   } catch (error) {
 
     console.warn("Không hiển thị được thông báo:", error);
 
     M.showToast(`${item.title}: ${body}`, "success");
 
   }
 
 }
 
 
 
 async function checkDueReminders() {
 
   if (document.visibilityState === "hidden" && Notification.permission !== "granted") return;
 
 
 
   const auth = await M.currentUser();
 
   if (!auth.logged_in) return;
 
 
 
   try {
 
     const response = await fetch("/api/reminders/due", {
 
       credentials: "same-origin",
 
       cache: "no-store"
 
     });
 
     const data = await response.json().catch(() => ({}));
 
     if (!response.ok) return;
 
 
 
     const items = Array.isArray(data.items) ? data.items : [];
 
     for (const item of items) {
 
       if (Notification.permission === "granted") await showReminderNotification(item);
 
       M.showToast(`Đến giờ: ${item.title}`, "success");
 
     }
 
   } catch (error) {
 
     console.warn("Không kiểm tra được lịch nhắc:", error);
 
   }
 
 }
 
 
 
 async function startReminderPolling() {
 
   clearInterval(reminderPollTimer);
 
   await registerReminderServiceWorker();
 
   await checkDueReminders();
 
   reminderPollTimer = window.setInterval(checkDueReminders, 30 * 1000);
 
 }
 
 
 
 function reminderIcon(type) {
 
   return ({ medicine: "💊", water: "💧", weight: "⚖", exercise: "🏃", meal: "🥗", appointment: "🗓️" })[type] || "🗓";
 
 }
 
 
 
 async function loadReminders({ openModal = false } = {}) {
 
   const preview = $(".reminder-list");
 
   const modal = $("#reminderModal");
 
   const modalList = $("#reminderModalList");
 
   if (!preview || !modal || !modalList) return [];
 
 
 
   const auth = await M.currentUser();
 
   if (!auth.logged_in) {
 
     preview.innerHTML = '<article class="reminder-empty"><span>🔐</span><div><strong>Đăng nhập để xem lịch nhắc</strong><small>Lịch nhắc được lưu riêng theo tài khoản.</small></div></article>';
 
     if (openModal) $("#accountButton")?.click();
 
     return [];
 
   }
 
 
 
   try {
 
     const response = await fetch("/api/reminders", { credentials: "same-origin" });
 
     const data = await response.json().catch(() => ({}));
 
     if (!response.ok) throw new Error(data.error || "Không tải được lịch nhắc.");
 
     const items = Array.isArray(data.items) ? data.items : [];
 
 
 
     preview.innerHTML = items.length
 
       ? items.slice(0, 3).map((item) => `
 
           <article>
 
             <span>${reminderIcon(item.reminder_type)}</span>
 
             <div><strong>${M.escapeHTML(item.title)}</strong><small>${M.escapeHTML(item.time_of_day)} · ${item.is_active ? "Đang bật" : "Đã tắt"}</small></div>
 
             <b>${item.is_active ? "✓" : "—"}</b>
 
           </article>`).join("")
 
       : '<article class="reminder-empty"><span>🗓</span><div><strong>Chưa có lịch nhắc</strong><small>Bấm “Xem tất cả” để tạo lịch mới.</small></div></article>';
 
 
 
     modalList.innerHTML = items.length
 
       ? items.map((item) => `
 
           <article class="reminder-modal-item">
 
             <span>${reminderIcon(item.reminder_type)}</span>
 
             <div><strong>${M.escapeHTML(item.title)}</strong><small>${M.escapeHTML(item.time_of_day)} · ${M.escapeHTML(item.message || item.medicine_name || "Hằng ngày")}</small></div>
 
             <button type="button" data-delete-reminder="${item.id}">Xóa</button>
 
           </article>`).join("")
 
       : '<p class="modal-empty">Chưa có lịch nhắc nào.</p>';
 
 
 
     $$('[data-delete-reminder]', modalList).forEach((button) => {
 
       button.addEventListener("click", async () => {
 
         if (!window.confirm("Xóa lịch nhắc này?")) return;
 
         const response = await fetch(`/api/reminders/${button.dataset.deleteReminder}`, {
 
           method: "DELETE",
 
           credentials: "same-origin"
 
         });
 
         const result = await response.json().catch(() => ({}));
 
         if (!response.ok) {
 
           M.showToast(result.error || "Không thể xóa lịch nhắc.", "error");
 
           return;
 
         }
 
         await loadReminders({ openModal: true });
 
         M.showToast("Đã xóa lịch nhắc.", "success");
 
       });
 
     });
 
 
 
     if (openModal) modal.classList.remove("hidden");
 
     return items;
 
   } catch (error) {
 
     preview.innerHTML = `<article class="reminder-empty"><span>!</span><div><strong>Không tải được lịch nhắc</strong><small>${M.escapeHTML(error.message)}</small></div></article>`;
 
     if (openModal) M.showToast(error.message, "error");
 
     return [];
 
   }
 
 }
 
 
 
 function bindReminderModal() {
 
   const modal = $("#reminderModal");
 
   const form = $("#reminderForm");
 
   const typeSelect = form?.elements?.reminder_type;
 
   const medicineInput = form?.elements?.medicine_name;
 
   if (!modal || !form) return;
 
 
 
   const syncMedicineField = () => {
 
     const medicineMode = typeSelect?.value === "medicine";
 
     medicineInput?.closest("label")?.classList.toggle("hidden", !medicineMode);
 
     if (medicineInput) medicineInput.required = Boolean(medicineMode);
 
   };
 
 
 
   $("#closeReminderModal")?.addEventListener("click", () => modal.classList.add("hidden"));
 
   modal.addEventListener("click", (event) => {
 
     if (event.target === modal) modal.classList.add("hidden");
 
   });
 
   $("#addReminderButton")?.addEventListener("click", () => {
 
     form.classList.toggle("hidden");
 
     syncMedicineField();
 
   });
 
   typeSelect?.addEventListener("change", syncMedicineField);
 
 
 
   form.addEventListener("submit", async (event) => {
 
     event.preventDefault();
 
     const submitButton = form.querySelector('button[type="submit"]');
 
     const body = Object.fromEntries(new FormData(form));
 
     try {
 
       submitButton.disabled = true;
 
       submitButton.textContent = "Đang lưu...";
 
       const response = await fetch("/api/reminders", {
 
         method: "POST",
 
         credentials: "same-origin",
 
         headers: { "Content-Type": "application/json" },
 
         body: JSON.stringify(body)
 
       });
 
       const data = await response.json().catch(() => ({}));
 
       if (!response.ok) throw new Error(data.error || "Không tạo được lịch nhắc.");
 
 
 
       form.reset();
 
       form.classList.add("hidden");
 
       await loadReminders({ openModal: true });
 
       M.showToast("Đã tạo lịch nhắc.", "success");
 
       await enableReminderNotifications({ showMessage: false });
 
       await checkDueReminders();
 
     } catch (error) {
 
       M.showToast(error.message, "error");
 
     } finally {
 
       submitButton.disabled = false;
 
       submitButton.textContent = "Lưu lịch nhắc";
 
     }
 
   });
 
 
 
   syncMedicineField();
 
 }
 
 
 
 function bindSearch() {
 
   const input = $(".search-box input");
 
   if (!input) return;
 
   input.addEventListener("keydown", (event) => {
 
     if (event.key !== "Enter") return;
 
     const term = input.value.trim().toLowerCase();
 
     if (!term) return;
 
 
 
     const profile = M.getProfiles().find((item) => item.name.toLowerCase().includes(term));
 
     if (profile) {
 
       M.selectProfile(profile);
 
       renderProfiles();
 
       const familyPanel = $("#family-health");
       if (familyPanel) familyPanel.scrollIntoView({ behavior: "smooth" });
       else window.location.assign("/suc-khoe-tien-ich#family-health");
 
       return;
 
     }
 
     if (term.includes("nhà thuốc")) {
 
       openGoogleMaps();
 
       return;
 
     }
 
     if (term.includes("thời tiết") || term.includes("bụi") || term.includes("aqi")) {
 
       const utilitiesPanel = $("#utilities");
       if (utilitiesPanel) utilitiesPanel.scrollIntoView({ behavior: "smooth" });
       else window.location.assign("/#utilities");
 
       return;
 
     }
 
     if (term.includes("tư vấn") || term.includes("chat")) {
 
       window.location.assign("/tu-van");
 
       return;
 
     }
 
     M.showToast("Chưa tìm thấy nội dung phù hợp.");
 
   });
 
 }
 
 
 
 async function initializeAccount() {
 
   const user = await M.bindAccountButton($("#accountButton"));
 
   M.bindAccountButton($("#sidebarAuthButton"));
 
   if (user?.logged_in) {
 
     await M.syncProfiles(user.user);
 
     if ($("#welcomeName")) $("#welcomeName").textContent = user.user.full_name;
 
     if ($("#accountAvatar")) $("#accountAvatar").textContent = M.initials(user.user.full_name);
 
   } else {
 
     M.clearPrivateState();
 
     if ($("#welcomeName")) $("#welcomeName").textContent = "Khách";
 
     if ($("#accountAvatar")) $("#accountAvatar").textContent = "K";
 
   }
 
   return user;
 
 }
 
 
 
 function focusPanel(selector) {
 
   const panel = $(selector);
 
   if (!panel) {
     if (selector === "#family-health") window.location.assign("/suc-khoe-tien-ich#family-health");
     else if (selector === "#utilities") window.location.assign("/#utilities");
     return;
   }
 
   panel.scrollIntoView({ behavior: "smooth", block: "center" });
 
   panel.classList.remove("attention-pulse");
 
   requestAnimationFrame(() => panel.classList.add("attention-pulse"));
 
   setTimeout(() => panel.classList.remove("attention-pulse"), 2600);
 
 }
 
 
 
 async function initialize() {
 
   bindFamilyModal();
 
   bindSelfHealthModal();
 
   bindReminderModal();
 
   bindSearch();
 
   await initializeAccount();
 
   renderProfiles();
 
   renderRecentChats();
 
   await loadReminders();
 
   await startReminderPolling();
 
 
 
   const saved = M.readJSON(M.KEYS.locationContext, null);
 
   if (saved) renderLocation(saved);
 
   else {
 
     renderLocation(null);
 
     refreshLocation(false);
 
   }
 
 
 
   $("#startConsultButton")?.addEventListener("click", () => window.location.assign("/tu-van"));
 
   $("#refreshEnvironment")?.addEventListener("click", () => refreshLocation(true));
 
   $("#openMapTop")?.addEventListener("click", () => openGoogleMaps());
 
   $("#openMapBottom")?.addEventListener("click", () => openGoogleMaps());
 
   $("#quickGoogleMaps")?.addEventListener("click", (event) => {
 
     event.preventDefault();
 
     openGoogleMaps();
 
   });
 
   $("#clearRecentButton")?.addEventListener("click", () => {
 
     localStorage.removeItem(M.KEYS.chats);
 
     localStorage.removeItem(M.KEYS.currentChat);
 
     renderRecentChats();
 
     M.showToast("Đã xóa lịch sử tư vấn trên thiết bị.");
 
   });
 
   $("#notificationButton")?.addEventListener("click", async () => {
 
     await enableReminderNotifications();
 
     await loadReminders({ openModal: true });
 
     await checkDueReminders();
 
   });
 
   $("#showAllProfiles")?.addEventListener("click", () => focusPanel("#family-health"));
 
   $("#selectProfileTip")?.addEventListener("click", () => {
 
     focusPanel("#family-health");
 
     M.showToast("Hãy bấm vào đúng thành viên trước khi mở Tư vấn AI.");
 
   });
 
   $("#profileDetailButton")?.addEventListener("click", () => focusPanel("#family-health"));
 
   $("#viewAirQualityButton")?.addEventListener("click", () => focusPanel("#utilities"));
 
   $("#showRemindersButton")?.addEventListener("click", () => loadReminders({ openModal: true }));

   $("#addReminderQuickButton")?.addEventListener("click", async () => {
     await loadReminders({ openModal: true });

     const modal = $("#reminderModal");
     const form = $("#reminderForm");

     // Nếu chưa đăng nhập thì loadReminders sẽ mở phần tài khoản.
     if (!modal || modal.classList.contains("hidden") || !form) return;

     if (form.classList.contains("hidden")) {
       $("#addReminderButton")?.click();
     }

     const firstField = form.querySelector(
       'input[name="title"], select[name="reminder_type"], input:not([type="hidden"])'
     );
     window.setTimeout(() => firstField?.focus(), 80);
   });
 
   $("#openSettings")?.addEventListener("click", () => M.openSettings?.("account"));
 
  const premiumModal = $("#premiumModal");
 
 
 
 $("#upgradeButton")?.addEventListener("click", () => {
 
   premiumModal?.classList.remove("hidden");
 
   document.body.style.overflow = "hidden";
 
 });
 
 
 
 $("#closePremiumModal")?.addEventListener("click", () => {
 
   premiumModal?.classList.add("hidden");
 
   document.body.style.overflow = "";
 
 });
 
 
 
 premiumModal?.addEventListener("click", (event) => {
 
   if (event.target === premiumModal) {
 
     premiumModal.classList.add("hidden");
 
     document.body.style.overflow = "";
 
   }
 
 });
 
 
 
 $("#subscribePremiumButton")?.addEventListener("click", () => {
 
   M.showToast(
 
     "Bạn đã chọn gói MediCare Premium 20.000đ/tháng.",
 
     "success"
 
   );
 
 
 
   premiumModal?.classList.add("hidden");
 
   document.body.style.overflow = "";
 
 });
 
 
 
   window.addEventListener("medicare:profile-changed", () => {
 
     renderProfiles();
 
     renderRecommendations(M.readJSON(M.KEYS.locationContext, null));
 
   });
 
   window.addEventListener("medicare:profiles-updated", renderProfiles);
 
   window.addEventListener("medicare:auth-changed", async (event) => {
 
     if (event.detail) {
 
       await M.syncProfiles(event.detail);
 
       if ($("#welcomeName")) $("#welcomeName").textContent = event.detail.full_name || "Tài khoản";
 
       if ($("#accountAvatar")) $("#accountAvatar").textContent = M.initials(event.detail.full_name);
 
     } else {
 
       M.clearPrivateState();
 
       if ($("#welcomeName")) $("#welcomeName").textContent = "Khách";
 
       if ($("#accountAvatar")) $("#accountAvatar").textContent = "K";
 
     }
 
     renderProfiles();
 
     renderRecentChats();
 
     await loadReminders();
 
     await startReminderPolling();
 
   });
 
 }
 
 
 
 document.addEventListener("DOMContentLoaded", initialize);
 
/* =========================================================
   MEDICARE AI - BONG BÓNG TƯ VẤN NHANH 20260808
   Dùng lại POST /chat và hồ sơ đang chọn; không thay backend.
   ========================================================= */
(() => {
  "use strict";
 
  const STORAGE_KEY = "medicareDashboardWidgetMessagesV3";
  const CONVERSATION_KEY = "medicareDashboardWidgetConversationIdV3";
  const MAX_STORED_MESSAGES = 20;
  let sending = false;
  let activeRequestController = null;
  let chatRevision = 0;
  let activeProfileId = "";
 
  const byId = (id) => document.getElementById(id);
  const nowTime = () => new Date().toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit"
  });
 
  function readMessages() {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.slice(-MAX_STORED_MESSAGES) : [];
    } catch (_) {
      return [];
    }
  }
 
  function saveMessages(messages) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)));
    } catch (_) {}
  }
 
  function conversationId() {
    let id = sessionStorage.getItem(CONVERSATION_KEY);
    if (!id) {
      id = `dashboard-widget-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      sessionStorage.setItem(CONVERSATION_KEY, id);
    }
    return id;
  }
 
  function resetChatForProfile(profile, messages) {
    // Khi đổi người được tư vấn, hủy yêu cầu cũ để câu trả lời của hồ sơ trước
    // không bị chèn vào lịch sử của hồ sơ mới.
    if (activeRequestController) {
      activeRequestController.abort();
      activeRequestController = null;
    }
 
    sending = false;
    chatRevision += 1;
    activeProfileId = String(profile?.id || "");
 
    messages.splice(0, messages.length);
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(CONVERSATION_KEY);
 
    hideTyping();
    const sendButton = byId("mcaiSend");
    if (sendButton) sendButton.disabled = false;
 
    updateProfileBar();
    renderMessages(messages);
  }
 
  function profileSnapshot() {
    const M = window.MediCare;
    const profile = M?.getSelectedProfile?.() || {
      id: "guest",
      name: "Khách",
      relationship: "Khách",
      age: "--",
      gender: "Chưa cập nhật",
      height: "",
      weight: "",
      condition: "Chưa cập nhật",
      allergies: "Chưa cập nhật"
    };
 
    return {
      id: profile.id,
      name: profile.name,
      relationship: profile.relationship,
      age: profile.age,
      gender: profile.gender,
      height: profile.height,
      weight: profile.weight,
      condition: profile.condition,
      allergies: profile.allergies,
      profile_type: profile.relationship === "Bản thân" ? "self" : "family"
    };
  }
 
  function hasUsableProfile(profile) {
    return Boolean(
      profile &&
      profile.id &&
      profile.id !== "guest" &&
      profile.name &&
      profile.name !== "Khách"
    );
  }
 
  async function ensureProfileReady() {
    const M = window.MediCare;
    let profile = profileSnapshot();
 
    // Nếu widget được mở quá sớm khi dashboard còn đang đồng bộ hồ sơ,
    // chờ lấy lại hồ sơ từ server rồi mới gửi câu hỏi.
    if (!hasUsableProfile(profile) && M?.currentUser && M?.syncProfiles) {
      try {
        const current = await M.currentUser();
        if (current?.logged_in && current.user) {
          await M.syncProfiles(current.user);
          profile = profileSnapshot();
        }
      } catch (_) {}
    }
 
    return profile;
  }
 
  function updateProfileBar() {
    const M = window.MediCare;
    const profile = profileSnapshot();
    const avatar = byId("mcaiProfileAvatar");
    const name = byId("mcaiProfileName");
    if (avatar) avatar.textContent = M?.initials?.(profile.name) || "K";
    if (name) name.textContent = profile.name || "Khách";

    const profileBar = byId("mcaiProfileBar");
    if (profileBar) {
      const label = `Xem hồ sơ sức khỏe của ${profile.name || "người đang được tư vấn"}`;
      profileBar.title = label;
      profileBar.setAttribute("aria-label", label);
    }
  }
 
  function messageNode(message) {
    const item = document.createElement("div");
    item.className = `mcai-message ${message.role === "user" ? "user" : "assistant"}`;
    if (message.error) item.classList.add("error");
    if (message.emergency) item.classList.add("emergency");
 
    const content = document.createElement("div");
    content.textContent = message.content || "";
    item.appendChild(content);
 
    if (message.time) {
      const time = document.createElement("small");
      time.className = "mcai-message-time";
      time.textContent = message.time;
      item.appendChild(time);
    }
    return item;
  }
 
  function renderMessages(messages) {
    const box = byId("mcaiMessages");
    if (!box) return;
    box.replaceChildren();
 
    if (!messages.length) {
      const profile = profileSnapshot();
      messages.push({
        role: "assistant",
        content: `Xin chào! Tôi đang hỗ trợ theo hồ sơ của ${profile.name || "bạn"}. Bạn cần tư vấn vấn đề sức khỏe nào?`,
        time: nowTime()
      });
      saveMessages(messages);
    }
 
    messages.forEach((message) => box.appendChild(messageNode(message)));
    box.scrollTop = box.scrollHeight;
  }
 
  function showTyping() {
    const box = byId("mcaiMessages");
    if (!box || byId("mcaiTyping")) return;
    const item = document.createElement("div");
    item.id = "mcaiTyping";
    item.className = "mcai-message assistant";
    item.innerHTML = '<span class="mcai-typing" aria-label="MediCare AI đang trả lời"><i></i><i></i><i></i></span>';
    box.appendChild(item);
    box.scrollTop = box.scrollHeight;
  }
 
  function hideTyping() {
    byId("mcaiTyping")?.remove();
  }
 
  function setOpen(open) {
    const widget = byId("mcaiWidget");
    const launcher = byId("mcaiLauncher");
    const panel = byId("mcaiPanel");
    if (!widget || !launcher || !panel) return;
 
    widget.classList.toggle("is-open", open);
    widget.classList.remove("is-tip-visible");
    launcher.setAttribute("aria-expanded", String(open));
    panel.setAttribute("aria-hidden", String(!open));
 
    if (open) {
      updateProfileBar();
      window.setTimeout(() => byId("mcaiInput")?.focus(), 120);
    }
  }
 
  function resizeInput() {
    const input = byId("mcaiInput");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 96)}px`;
  }
 
  async function sendMessage(text, messages) {
    const cleanText = String(text || "").trim();
    if (!cleanText || sending) return;
 
    const M = window.MediCare;
    const input = byId("mcaiInput");
    const sendButton = byId("mcaiSend");
    const history = messages
      .slice(-10)
      .map(({ role, content }) => ({ role, content }))
      .filter((item) => item.content);
 
    const activeProfile = await ensureProfileReady();
 
    if (!hasUsableProfile(activeProfile)) {
      const errorMessage = "Chưa tải được hồ sơ đang chọn. Vui lòng chờ vài giây rồi thử lại.";
      window.MediCare?.showToast?.(errorMessage, "error");
      return;
    }
 
    messages.push({ role: "user", content: cleanText, time: nowTime() });
    saveMessages(messages);
    renderMessages(messages);
 
    if (input) {
      input.value = "";
      resizeInput();
    }
 
    sending = true;
    if (sendButton) sendButton.disabled = true;
    showTyping();
 
    let requestRevision = chatRevision;
    let requestProfileId = String(activeProfile.id);
    let requestController = null;
 
    try {
      const formData = new FormData();
      formData.append("message", cleanText);
      formData.append("history", JSON.stringify(history));
      formData.append("selected_profile", JSON.stringify(activeProfile));
      formData.append("profile_context_version", "3");
      formData.append("conversation_id", conversationId());
 
      const environment = M?.readJSON?.(M.KEYS?.locationContext, null);
      if (environment) formData.append("environment", JSON.stringify(environment));
 
      const specialtyKey = M?.KEYS?.specialty;
      const specialty = specialtyKey ? (localStorage.getItem(specialtyKey) || "") : "";
      if (specialty) formData.append("specialty", specialty);
 
      requestRevision = chatRevision;
      requestProfileId = String(activeProfile.id);
      requestController = new AbortController();
      activeRequestController = requestController;
 
      const response = await fetch("/chat", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        signal: requestController.signal
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "AI chưa thể phản hồi.");
 
      // Nếu người dùng đã đổi hồ sơ trong lúc AI đang trả lời, bỏ phản hồi cũ.
      if (requestRevision !== chatRevision || String(profileSnapshot().id) !== requestProfileId) {
        return;
      }
 
      const returnedProfileId = data.profile_used?.id;
      if (returnedProfileId != null && String(returnedProfileId) !== requestProfileId) {
        throw new Error("Hồ sơ tư vấn đã thay đổi. Vui lòng thử lại.");
      }
 
      messages.push({
        role: "assistant",
        content: data.reply || "Tôi chưa nhận được nội dung phản hồi. Vui lòng thử lại.",
        time: nowTime(),
        emergency: Boolean(data.emergency?.active)
      });
    } catch (error) {
      if (error?.name === "AbortError" || String(profileSnapshot().id) !== String(activeProfile.id)) {
        return;
      }
 
      messages.push({
        role: "assistant",
        content: `Xin lỗi, hệ thống gặp lỗi: ${error.message || "Không thể kết nối."}`,
        time: nowTime(),
        error: true
      });
    } finally {
      const requestIsStale = (
        requestRevision !== chatRevision ||
        String(profileSnapshot().id) !== requestProfileId
      );
 
      if (requestIsStale) {
        if (activeRequestController === requestController) activeRequestController = null;
        return;
      }
 
      if (activeRequestController === requestController) activeRequestController = null;
      sending = false;
      if (sendButton) sendButton.disabled = false;
      hideTyping();
      saveMessages(messages);
      renderMessages(messages);
      input?.focus();
    }
  }
 
  function initializeDashboardChatWidget() {
    const widget = byId("mcaiWidget");
    if (!widget) return;
 
    const messages = readMessages();
    activeProfileId = String(profileSnapshot().id || "");
    updateProfileBar();
    renderMessages(messages);
 
    byId("mcaiLauncher")?.addEventListener("click", () => {
      setOpen(!widget.classList.contains("is-open"));
    });
 
    byId("mcaiClose")?.addEventListener("click", () => setOpen(false));

    byId("mcaiProfileBar")?.addEventListener("click", async () => {
      const M = window.MediCare;
      const profile = await ensureProfileReady();

      if (!hasUsableProfile(profile)) {
        M?.showToast?.("Chưa tải được hồ sơ sức khỏe đang chọn.", "error");
        return;
      }

      // Hồ sơ bản thân: mở modal cập nhật hồ sơ ngay trên Trang chủ.
      if (
        profile.relationship === "Bản thân" &&
        typeof window.openSelfHealthModal === "function"
      ) {
        setOpen(false);
        await window.openSelfHealthModal();
        return;
      }

      // Hồ sơ thành viên gia đình: đưa người dùng tới Sổ sức khỏe gia đình.
      setOpen(false);
      const familySection = document.getElementById("family-health");
      familySection?.scrollIntoView({ behavior: "smooth", block: "center" });
      M?.showToast?.(`Đang hiển thị hồ sơ ${profile.name}.`, "success");
    });
 
    byId("mcaiForm")?.addEventListener("submit", (event) => {
      event.preventDefault();
      sendMessage(byId("mcaiInput")?.value, messages);
    });
 
    byId("mcaiInput")?.addEventListener("input", resizeInput);
    byId("mcaiInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        byId("mcaiForm")?.requestSubmit();
      }
    });
 
    document.querySelectorAll("[data-mcai-prompt]").forEach((button) => {
      button.addEventListener("click", () => sendMessage(button.dataset.mcaiPrompt, messages));
    });
 
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && widget.classList.contains("is-open")) setOpen(false);
    });
 
    window.addEventListener("medicare:profile-changed", () => {
      const profile = profileSnapshot();
      const nextProfileId = String(profile.id || "");
 
      updateProfileBar();
 
      // Chỉ làm mới khi thực sự đổi sang một hồ sơ khác.
      // Nếu hệ thống đồng bộ lại đúng hồ sơ hiện tại thì giữ nguyên cuộc trò chuyện.
      if (!nextProfileId || nextProfileId === activeProfileId) return;
 
      resetChatForProfile(profile, messages);
      window.MediCare?.showToast?.(
        `Đã chuyển sang hồ sơ ${profile.name}. Lịch sử chat nhanh đã được làm mới.`,
        "success"
      );
    });
 
    widget.classList.add("is-tip-visible");
    window.setTimeout(() => widget.classList.remove("is-tip-visible"), 5500);
  }
 
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeDashboardChatWidget);
  } else {
    initializeDashboardChatWidget();
  }
})();
/* ===== /MEDICARE AI - BONG BÓNG TƯ VẤN NHANH ===== */
