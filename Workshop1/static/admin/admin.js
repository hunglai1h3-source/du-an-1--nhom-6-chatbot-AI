(()=>{"use strict";const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const fmt=n=>new Intl.NumberFormat("vi-VN").format(Number(n||0));const toast=m=>{const e=$("#toast");if(!e)return;e.textContent=m;e.classList.add("show");setTimeout(()=>e.classList.remove("show"),2200)};$("#menuToggle")?.addEventListener("click",()=>$("#sidebar")?.classList.toggle("open"));const theme=localStorage.getItem("admin-theme");if(theme)document.documentElement.dataset.theme=theme;
const adminNav=$(".sidebar nav");
if(adminNav&&!adminNav.querySelector("[data-admin-news-link]")){
  const newsLink=document.createElement("a");
  newsLink.href="/admin/news";
  newsLink.dataset.adminNewsLink="";
  newsLink.innerHTML="▤ Bản tin sức khỏe";
  if(location.pathname.startsWith("/admin/news"))newsLink.classList.add("active");
  adminNav.appendChild(newsLink);
}
$("#themeToggle")?.addEventListener("click",()=>{const d=document.documentElement;d.dataset.theme=d.dataset.theme==="dark"?"light":"dark";localStorage.setItem("admin-theme",d.dataset.theme)});
async function getJSON(url,opts){const r=await fetch(url,{cache:"no-store",...opts});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||"Có lỗi xảy ra");return d}
function setSync(t){$("#syncLabel")&&( $("#syncLabel").textContent="Đồng bộ "+t)}
let chart;
function chartRender(rows){if(!$("#activityChart")||!window.Chart)return;const labels=rows.map(x=>x.day.slice(5));const data={labels,datasets:[{label:"Lượt chat",data:rows.map(x=>x.chats),borderColor:"#10b981",backgroundColor:"rgba(16,185,129,.12)",fill:true,tension:.35},{label:"Người dùng mới",data:rows.map(x=>x.users),borderColor:"#3b82f6",backgroundColor:"rgba(59,130,246,.08)",fill:true,tension:.35}]};if(chart){chart.data=data;chart.update()}else chart=new Chart($("#activityChart"),{type:"line",data,options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom"}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}})}
async function loadDashboard(){try{const d=await getJSON("/admin/api/dashboard");Object.entries(d.stats).forEach(([k,v])=>$$(`[data-stat="${k}"]`).forEach(e=>e.textContent=k==="avg_latency"?fmt(v)+" ms":k==="success_rate"?fmt(v):fmt(v)));$("#lastSync")&&($("#lastSync").textContent=d.server_time);setSync(d.server_time);chartRender(d.chart);if(d.ai){$("#activeTextModel")&&($("#activeTextModel").textContent=d.ai.text_model);$("#activeVisionModel")&&($("#activeVisionModel").textContent=d.ai.vision_model);$("#apiConfigured")&&($("#apiConfigured").textContent=d.ai.api_configured?"Đã cấu hình":"Chưa có");}$("#recentUsers")&&($("#recentUsers").innerHTML=d.recent_users.map(u=>`<a class="list-item" href="/admin/users/${u.id}"><div class="user-cell"><div class="avatar">${esc(u.full_name[0]||"U")}</div><div><b>${esc(u.full_name)}</b><small>${esc(u.email)} · ${esc(u.created_at)}</small></div></div><span class="badge ${u.is_active?"success":"danger"}">${u.role}</span></a>`).join("")||'<div class="empty">Chưa có người dùng</div>');$("#recentChats")&&($("#recentChats").innerHTML=d.recent_chats.map(c=>`<div class="list-item"><div><b>${esc(c.full_name)}</b><small>${esc(c.question).slice(0,80)}</small></div><span class="badge ${c.status==="success"?"success":"danger"}">${esc(c.model||"-")}</span></div>`).join("")||'<div class="empty">Chưa có chat</div>')}catch(e){toast(e.message)}}
let userPage=1;
async function loadUsers(page=userPage){userPage=page;const f=$("#userFilters"),q=new URLSearchParams(new FormData(f));q.set("page",page);try{const d=await getJSON("/admin/api/users?"+q);$("#userTotal").textContent=fmt(d.total);$("#usersSync").textContent=d.server_time;$("#userCount")&&($("#userCount").textContent=fmt(d.counts?.user));$("#adminCount")&&($("#adminCount").textContent=fmt(d.counts?.admin));$("#allCount")&&($("#allCount").textContent=fmt(d.counts?.all));$("#latestUserId")&&($("#latestUserId").textContent=d.latest_id);$("#databaseInfo")&&($("#databaseInfo").textContent="Database đang đọc: "+d.database_file);setSync(d.server_time);$("#usersBody").innerHTML=d.items.map(u=>`<tr><td><a class="user-cell" href="/admin/users/${u.id}"><div class="avatar">${esc(u.full_name[0]||"U")}</div><div><b>${esc(u.full_name)}</b><small>#${u.id}</small></div></a></td><td><b>${esc(u.email)}</b><br><small>${esc(u.phone||"Chưa có SĐT")}</small></td><td><select data-role="${u.id}" ${u.id===window.AdminCurrentUser?"disabled":""}><option value="user" ${u.role==="user"?"selected":""}>User</option><option value="admin" ${u.role==="admin"?"selected":""}>Admin</option></select></td><td><span class="badge ${u.is_active?"success":"danger"}">${u.is_active?"Hoạt động":"Đã khóa"}</span></td><td>${fmt(u.chat_count)}</td><td class="nowrap">${esc(u.created_at)}</td><td><div class="actions"><a class="btn" href="/admin/users/${u.id}">Xem</a>${u.id!==window.AdminCurrentUser?`<button class="btn ${u.is_active?"danger":""}" data-toggle="${u.id}">${u.is_active?"Khóa":"Mở"}</button>`:""}</div></td></tr>`).join("")||'<tr><td colspan="7" class="empty">Không tìm thấy người dùng</td></tr>';$("#usersPagination").innerHTML=Array.from({length:d.pages},(_,i)=>i+1).slice(Math.max(0,d.page-3),d.page+2).map(p=>`<button class="${p===d.page?"active":""}" data-page="${p}">${p}</button>`).join("")}catch(e){toast(e.message)}}
async function loadChats(page=1){const f=$("#chatFilters"),q=new URLSearchParams(new FormData(f));q.set("page",page);try{const d=await getJSON("/admin/api/chats?"+q);$("#chatTotal").textContent=fmt(d.total);$("#chatsSync").textContent=d.server_time;setSync(d.server_time);$("#chatsBody").innerHTML=d.items.map(c=>`<tr><td><b>${esc(c.full_name)}</b><br><small>${esc(c.email||"Khách")}</small></td><td class="truncate" title="${esc(c.question)}">${esc(c.question)}</td><td><span class="badge">${esc(c.model||"-")}</span></td><td>${fmt((c.prompt_tokens||0)+(c.completion_tokens||0))}</td><td>${fmt(c.latency_ms)} ms</td><td><span class="badge ${c.status==="success"?"success":"danger"}">${esc(c.status)}</span></td><td class="nowrap">${esc(c.created_at)}</td></tr>`).join("")||'<tr><td colspan="7" class="empty">Chưa có hội thoại</td></tr>';$("#chatsPagination").innerHTML=Array.from({length:d.pages},(_,i)=>i+1).slice(Math.max(0,d.page-3),d.page+2).map(p=>`<button class="${p===d.page?"active":""}" data-chat-page="${p}">${p}</button>`).join("")}catch(e){toast(e.message)}}
document.addEventListener("click",async e=>{const t=e.target.closest("[data-toggle]");if(t){if(!confirm("Xác nhận thay đổi trạng thái tài khoản?"))return;try{await getJSON(`/admin/users/${t.dataset.toggle}/toggle-active`,{method:"POST"});toast("Đã cập nhật");loadUsers()}catch(x){toast(x.message)}}const p=e.target.closest("[data-page]");p&&loadUsers(Number(p.dataset.page));const cp=e.target.closest("[data-chat-page]");cp&&loadChats(Number(cp.dataset.chatPage));const detail=e.target.closest("[data-chat-detail]");if(detail){const c=(window.__adminChats||[]).find(x=>String(x.id)===String(detail.dataset.chatDetail));if(c){$("#chatDetailMeta").textContent=`${c.full_name||"Khách"} · ${c.model||"-"} · ${c.created_at||""}`;$("#chatDetailQuestion").textContent=c.question||"";$("#chatDetailAnswer").textContent=c.answer||"Không có câu trả lời";$("#chatDetailError").textContent=c.error_message||"";$("#chatDetailErrorWrap").classList.toggle("hidden",!c.error_message);$("#chatDetailModal").classList.remove("hidden")}}const del=e.target.closest("[data-delete-dataset]");if(del&&confirm("Xóa dataset này?")){try{await getJSON(`/admin/datasets/${encodeURIComponent(del.dataset.deleteDataset)}/delete`,{method:"POST"});location.reload()}catch(x){toast(x.message)}}});
document.addEventListener("change",async e=>{const s=e.target.closest("[data-role]");if(s){try{await getJSON(`/admin/users/${s.dataset.role}/role`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({role:s.value})});toast("Đã đổi quyền");loadUsers()}catch(x){toast(x.message)}}});
if(window.AdminPage==="dashboard"){try{chartRender(JSON.parse($("#initialChart")?.textContent||"[]"))}catch{}loadDashboard();$("#refreshDashboard")?.addEventListener("click",loadDashboard);setInterval(loadDashboard,5000)}
if(window.AdminPage==="users"){document.addEventListener("click",e=>{const tab=e.target.closest("[data-role-tab]");if(!tab)return;$$('[data-role-tab]').forEach(x=>x.classList.remove('active'));tab.classList.add('active');$("#roleFilter").value=tab.dataset.roleTab;$("#accountListTitle").textContent=tab.dataset.roleTab==="admin"?"Tài khoản quản trị viên":tab.dataset.roleTab==="user"?"Tài khoản người dùng":"Tất cả tài khoản";loadUsers(1)});$("#clearUserFilters")?.addEventListener("click",()=>{$("#userFilters").reset();$("#roleFilter").value="user";$$('[data-role-tab]').forEach(x=>x.classList.toggle('active',x.dataset.roleTab==='user'));loadUsers(1)});loadUsers();$("#refreshUsers")?.addEventListener("click",()=>loadUsers(1));$("#userFilters")?.addEventListener("submit",e=>{e.preventDefault();loadUsers(1)});setInterval(()=>{if(!document.hidden)loadUsers(userPage)},3000)}
if(window.AdminPage==="chats"){$("#closeChatDetail")?.addEventListener("click",()=>$("#chatDetailModal").classList.add("hidden"));$("#chatDetailModal")?.addEventListener("click",e=>{if(e.target.id==="chatDetailModal")e.currentTarget.classList.add("hidden")});loadChats();$("#refreshChats")?.addEventListener("click",()=>loadChats(1));$("#chatFilters")?.addEventListener("submit",e=>{e.preventDefault();loadChats(1)});setInterval(()=>loadChats(1),5000)}
if(window.AdminPage==="ai-settings"){$("#testGeminiButton")?.addEventListener("click",async()=>{const b=$("#testGeminiButton"),r=$("#geminiTestResult");b.disabled=true;b.textContent="Đang kiểm tra...";r.className="test-result muted";r.textContent="Đang gửi một yêu cầu kiểm tra ngắn tới Gemini...";try{const d=await getJSON("/admin/api/ai/test",{method:"POST"});r.className="test-result success";r.textContent=`Kết nối thành công · Model: ${d.model} · Độ trễ: ${fmt(d.latency_ms)} ms · Phản hồi: ${d.reply}`}catch(e){r.className="test-result error";r.textContent="Kiểm tra thất bại: "+e.message}finally{b.disabled=false;b.textContent="Kiểm tra kết nối Gemini"}})}
document.addEventListener("click",async e=>{const b=e.target.closest("[data-premium-action]");if(!b)return;const action=b.dataset.premiumAction;const label=action==="approve"?"xác nhận đã nhận thanh toán và kích hoạt Premium":"từ chối hóa đơn";if(!confirm(`Bạn chắc chắn muốn ${label}?`))return;try{await getJSON(`/admin/premium/${b.dataset.orderId}/${action}`,{method:"POST"});toast("Đã cập nhật hóa đơn");setTimeout(()=>location.reload(),500)}catch(x){toast(x.message)}});

if(window.AdminPage==="news"){
  let newsItems=[];

  const statusLabel=s=>({
    pending:"Chờ duyệt",
    approved:"Đã duyệt",
    draft:"Đã ẩn",
    rejected:"Từ chối"
  }[s]||s);

  const statusClass=s=>s==="approved"?"success":s==="rejected"?"danger":s==="pending"?"warning":"";

  function setNewsImagePreview(url="", label=""){
    const box=$("#newsImagePreviewBox");
    const image=$("#newsImagePreview");
    const fileName=$("#newsImageFileName");

    if(!box||!image||!fileName)return;

    if(url){
      image.src=url;
      fileName.textContent=label||"Ảnh đại diện đã tải lên";
      box.classList.remove("hidden");
    }else{
      image.removeAttribute("src");
      fileName.textContent="Ảnh đại diện";
      box.classList.add("hidden");
    }
  }

  function resetNewsForm(){
    $("#newsForm")?.reset();
    $("#newsId").value="";
    $("#newsImageUrl").value="";
    setNewsImagePreview();
    $("#newsFormTitle").textContent="Thêm bài báo";
    $("#saveNewsButton").textContent="Tạo bài chờ duyệt";
    $("#cancelNewsEdit")?.classList.add("hidden");
  }

  function fillNewsForm(item){
    $("#newsId").value=item.id;
    $("#newsTitle").value=item.title||"";
    $("#newsSourceName").value=item.source_name||"";
    $("#newsCategory").value=item.category||"general";
    $("#newsSourceUrl").value=item.source_url||"";
    $("#newsImageUrl").value=item.image_url||"";
    $("#newsImageFile").value="";
    setNewsImagePreview(
      item.image_url||"",
      item.image_url?"Ảnh đại diện hiện tại":""
    );
    $("#newsSummary").value=item.summary||"";
    $("#newsFormTitle").textContent=`Sửa bài #${item.id}`;
    $("#saveNewsButton").textContent="Lưu thay đổi";
    $("#cancelNewsEdit")?.classList.remove("hidden");
    window.scrollTo({top:0,behavior:"smooth"});
  }

  async function loadNews(){
    const status=$("#newsStatusFilter")?.value||"all";
    const category=$("#newsCategoryFilter")?.value||"all";

    try{
      const d=await getJSON(`/admin/api/news?status=${encodeURIComponent(status)}&category=${encodeURIComponent(category)}`);
      newsItems=d.items||[];

      $("#newsCountAll").textContent=fmt(d.counts?.all);
      $("#newsCountPending").textContent=fmt(d.counts?.pending);
      $("#newsCountApproved").textContent=fmt(d.counts?.approved);
      $("#newsCountRejected").textContent=fmt(d.counts?.rejected);

      $("#newsTableBody").innerHTML=newsItems.map(item=>`
        <tr>
          <td>
            <div class="news-admin-cell">
              <img src="${esc(item.image_url||"/static/images/news-doctor.svg")}" alt="" onerror="this.onerror=null;this.src='/static/images/news-doctor.svg'">
              <div>
                <b>${esc(item.title)}</b>
                <small>${esc(item.summary).slice(0,130)}${String(item.summary||"").length>130?"…":""}</small>
              </div>
            </div>
          </td>
          <td>
            <b>${esc(item.source_name)}</b>
            <small><a class="admin-source-link" href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">Mở bài gốc ↗</a></small>
          </td>
          <td><span class="badge">${esc(item.category_label)}</span></td>
          <td>
            <span class="badge ${statusClass(item.status)}">${esc(statusLabel(item.status))}</span>
            ${item.rejection_reason?`<small class="danger-text">${esc(item.rejection_reason)}</small>`:""}
          </td>
          <td>${item.is_featured?'<span class="badge success">Nổi bật</span>':'-'}</td>
          <td>
            <div class="actions">
              <button class="btn" type="button" data-news-edit="${item.id}">Sửa</button>
              ${item.status!=="approved"?`<button class="btn primary" type="button" data-news-action="approve" data-news-id="${item.id}">Duyệt</button>`:""}
              ${item.status==="approved"&&!item.is_featured?`<button class="btn" type="button" data-news-action="feature" data-news-id="${item.id}">Nổi bật</button>`:""}
              ${item.status==="approved"?`<button class="btn" type="button" data-news-action="hide" data-news-id="${item.id}">Ẩn</button>`:""}
              ${item.status!=="rejected"?`<button class="btn danger" type="button" data-news-action="reject" data-news-id="${item.id}">Từ chối</button>`:""}
              ${item.status==="rejected"||item.status==="draft"?`<button class="btn" type="button" data-news-action="pending" data-news-id="${item.id}">Gửi duyệt lại</button>`:""}
              <button class="btn danger" type="button" data-news-action="delete" data-news-id="${item.id}">Xóa</button>
            </div>
          </td>
        </tr>
      `).join("")||'<tr><td colspan="6" class="empty">Không có bài báo phù hợp.</td></tr>';

      setSync(new Date().toLocaleTimeString("vi-VN",{hour:"2-digit",minute:"2-digit"}));
    }catch(e){
      toast(e.message);
    }
  }

  async function uploadSelectedNewsImage(){
    const input=$("#newsImageFile");
    const file=input?.files?.[0];

    if(!file)return $("#newsImageUrl")?.value||"";

    const formData=new FormData();
    formData.append("image",file);

    const response=await fetch("/admin/api/news/upload-image",{
      method:"POST",
      body:formData,
      cache:"no-store"
    });

    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||"Không tải được ảnh.");

    $("#newsImageUrl").value=data.image_url||"";
    setNewsImagePreview(
      data.image_url||"",
      file.name
    );

    return data.image_url||"";
  }

  $("#newsImageFile")?.addEventListener("change",()=>{
    const file=$("#newsImageFile")?.files?.[0];
    if(!file)return;

    if(file.size>5*1024*1024){
      toast("Ảnh không được vượt quá 5 MB.");
      $("#newsImageFile").value="";
      return;
    }

    const allowed=["image/jpeg","image/png","image/webp"];
    if(file.type&&!allowed.includes(file.type)){
      toast("Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.");
      $("#newsImageFile").value="";
      return;
    }

    const objectUrl=URL.createObjectURL(file);
    setNewsImagePreview(objectUrl,file.name);

    const preview=$("#newsImagePreview");
    preview?.addEventListener("load",()=>{
      URL.revokeObjectURL(objectUrl);
    },{once:true});
  });

  $("#removeNewsImage")?.addEventListener("click",()=>{
    $("#newsImageFile").value="";
    $("#newsImageUrl").value="";
    setNewsImagePreview();
  });

  $("#newsForm")?.addEventListener("submit",async e=>{
    e.preventDefault();
    const id=$("#newsId").value.trim();
    const saveButton=$("#saveNewsButton");

    try{
      saveButton.disabled=true;
      saveButton.textContent=$("#newsImageFile")?.files?.[0]
        ?"Đang tải ảnh..."
        :"Đang lưu...";

      const imageUrl=await uploadSelectedNewsImage();

      const payload={
        title:$("#newsTitle").value,
        source_name:$("#newsSourceName").value,
        category:$("#newsCategory").value,
        source_url:$("#newsSourceUrl").value,
        image_url:imageUrl,
        summary:$("#newsSummary").value
      };

      saveButton.textContent="Đang lưu...";

      await getJSON(
        id?`/admin/api/news/${id}`:"/admin/api/news",
        {
          method:id?"PUT":"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(payload)
        }
      );
      toast(id?"Đã lưu thay đổi.":"Đã tạo bài chờ duyệt.");
      resetNewsForm();
      await loadNews();
    }catch(e){
      toast(e.message);
    }finally{
      saveButton.disabled=false;
      saveButton.textContent=$("#newsId").value
        ?"Lưu thay đổi"
        :"Tạo bài chờ duyệt";
    }
  });

  $("#cancelNewsEdit")?.addEventListener("click",resetNewsForm);
  $("#refreshNews")?.addEventListener("click",loadNews);
  $("#newsFilters")?.addEventListener("change",loadNews);

  document.addEventListener("click",async e=>{
    const edit=e.target.closest("[data-news-edit]");
    if(edit){
      const item=newsItems.find(x=>String(x.id)===String(edit.dataset.newsEdit));
      if(item)fillNewsForm(item);
      return;
    }

    const actionButton=e.target.closest("[data-news-action]");
    if(!actionButton)return;

    const action=actionButton.dataset.newsAction;
    const id=actionButton.dataset.newsId;
    let reason="";

    if(action==="delete"&&!confirm("Xóa vĩnh viễn bài báo này?"))return;
    if(action==="approve"&&!confirm("Duyệt bài này để hiển thị cho người dùng?"))return;
    if(action==="hide"&&!confirm("Ẩn bài này khỏi Trang chủ?"))return;
    if(action==="feature"&&!confirm("Đặt bài này làm bài nổi bật?"))return;
    if(action==="pending"&&!confirm("Chuyển bài về trạng thái chờ duyệt?"))return;

    if(action==="reject"){
      reason=prompt("Lý do từ chối (có thể để trống):","")||"";
      if(!confirm("Xác nhận từ chối bài này?"))return;
    }

    try{
      await getJSON(`/admin/api/news/${id}/${action}`,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({reason})
      });
      toast("Đã cập nhật bản tin.");
      await loadNews();
    }catch(e){
      toast(e.message);
    }
  });

  loadNews();
}

})();