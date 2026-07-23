"use strict";

const M = window.MediCare;
const $ = M.$;
let currentContext = M.readJSON(M.KEYS.locationContext, null);

function updateMap(context) {
  currentContext = context || currentContext;
  const query = currentContext?.latitude && currentContext?.longitude
    ? `nhà thuốc gần ${currentContext.latitude},${currentContext.longitude}`
    : "nhà thuốc gần tôi";
  $("#googleMapFrame").src = `https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;
  $("#locationStatus").textContent = currentContext?.short_address
    ? `Đang tìm quanh: ${currentContext.short_address}`
    : "Google Maps sẽ dùng vị trí thiết bị khi bạn mở bản đồ.";
}

document.addEventListener("DOMContentLoaded", async () => {
  const account = await M.bindAccountButton($("#accountButton"));
  if (account.logged_in) {
    $("#accountAvatar").textContent = M.initials(account.user.full_name);
    $("#accountName").textContent = account.user.full_name;
  }
  updateMap(currentContext);

  $("#openGoogleMaps").addEventListener("click", () => {
    window.open(M.mapsSearchUrl(currentContext), "_blank", "noopener,noreferrer");
  });

  $("#useCurrentLocation").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "Đang định vị...";
    try {
      const position = await M.getBestPosition();
      currentContext = {
        ...(currentContext || {}),
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_m: position.coords.accuracy,
        short_address: "Vị trí hiện tại"
      };
      updateMap(currentContext);
      $("#locationStatus").textContent = `Đã lấy vị trí với độ chính xác khoảng ±${Math.round(position.coords.accuracy)} m.`;
    } catch (error) {
      $("#locationStatus").textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = "📍 Dùng vị trí hiện tại";
    }
  });
});
