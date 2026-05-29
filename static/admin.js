const chatBtn = document.getElementById("chat-btn");
const logoutBtn = document.getElementById("logout-btn");
const reloadConfigBtn = document.getElementById("reload-config-btn");
const saveConfigBtn = document.getElementById("save-config-btn");
const configErrorEl = document.getElementById("config-error");
const configSaveResultEl = document.getElementById("config-save-result");
const configEditorEl = document.getElementById("config-editor");
const configPathEl = document.getElementById("config-path");
const configFileSelectEl = document.getElementById("config-file-select");
const configDescriptionEl = document.getElementById("config-description");
const configRestartHintEl = document.getElementById("config-restart-hint");

const state = {
  configFiles: Array.isArray(window.__ADMIN_CONFIG__?.configFiles)
    ? window.__ADMIN_CONFIG__.configFiles.slice()
    : [],
  selectedConfigFileId: "",
  loadingConfig: false,
  savingConfig: false,
  activeTab: "dashboard",
  tabLoaded: {},
  auditOffset: 0,
};

// --- Tab system ---
const tabBtns = document.querySelectorAll(".admin-tab");
const tabPanels = document.querySelectorAll(".tab-panel");

function switchTab(tabId) {
  state.activeTab = tabId;
  tabBtns.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tabId));
  tabPanels.forEach((p) => p.classList.toggle("active", p.id === `tab-${tabId}`));
  if (!state.tabLoaded[tabId]) {
    state.tabLoaded[tabId] = true;
    if (tabId === "dashboard") loadDashboard();
    else if (tabId === "users") loadUsers();
    else if (tabId === "usage") loadUsage();
    else if (tabId === "documents") loadAdminDocs();
    else if (tabId === "config") initConfigTab();
    else if (tabId === "audit") { state.auditOffset = 0; loadAuditLogs(false); }
  }
}

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// --- Helpers ---
async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) throw new Error(data.error || "请求失败");
  return data;
}

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "textContent") e.textContent = v;
    else if (k === "className") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (typeof c === "string") e.appendChild(document.createTextNode(c));
    else if (c) e.appendChild(c);
  }
  return e;
}

function formatNumber(n) {
  return typeof n === "number" ? n.toLocaleString() : "-";
}

// --- Dashboard ---
async function loadDashboard() {
  try {
    const data = await fetchJson("/api/admin/dashboard");
    document.getElementById("stat-users").textContent = formatNumber(data.user_count);
    document.getElementById("stat-conversations").textContent = formatNumber(data.conversation_count);
    document.getElementById("stat-tokens").textContent = formatNumber(data.today_tokens);
    document.getElementById("stat-documents").textContent = formatNumber(data.document_count);
  } catch { /* ignore */ }
}

// --- Users ---
async function loadUsers() {
  const list = document.getElementById("users-list");
  list.textContent = "";
  try {
    const data = await fetchJson("/api/admin/users");
    for (const user of data.users) {
      const card = el("div", { className: "user-card" }, [
        el("div", { className: "user-card-head" }, [
          el("div", { className: "user-card-title" }, [
            el("strong", { textContent: user.username }),
            el("span", { className: `role-badge ${user.is_admin ? "is-admin" : ""}`, textContent: user.is_admin ? "管理员" : "普通用户" }),
            !user.enabled ? el("span", { className: "role-badge", textContent: "已禁用", style: "border-color:var(--danger);color:var(--danger-light)" }) : null,
          ]),
          el("div", { className: "user-card-actions" }, [
            el("button", { className: "btn-secondary", textContent: user.enabled ? "禁用" : "启用", onClick: () => toggleUser(user.username, !user.enabled) }),
            el("button", { className: "btn-danger", textContent: "删除", onClick: () => deleteUser(user.username) }),
          ]),
        ]),
      ]);
      list.appendChild(card);
    }
  } catch (err) {
    document.getElementById("users-error").textContent = String(err);
  }
}

async function toggleUser(username, enabled) {
  try {
    await fetchJson(`/api/admin/users/${encodeURIComponent(username)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    state.tabLoaded["users"] = false;
    loadUsers();
  } catch (err) {
    document.getElementById("users-error").textContent = String(err);
  }
}

async function deleteUser(username) {
  if (!confirm(`确认删除用户 ${username}？`)) return;
  try {
    await fetchJson(`/api/admin/users/${encodeURIComponent(username)}`, { method: "DELETE" });
    state.tabLoaded["users"] = false;
    loadUsers();
  } catch (err) {
    document.getElementById("users-error").textContent = String(err);
  }
}

const showCreateUserBtn = document.getElementById("show-create-user");
const createUserForm = document.getElementById("create-user-form");
const createUserBtn = document.getElementById("create-user-btn");
const cancelCreateUserBtn = document.getElementById("cancel-create-user");

showCreateUserBtn.addEventListener("click", () => { createUserForm.hidden = false; });
cancelCreateUserBtn.addEventListener("click", () => { createUserForm.hidden = true; });
createUserBtn.addEventListener("click", async () => {
  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value;
  const isAdmin = document.getElementById("new-is-admin").checked;
  if (!username || !password) { document.getElementById("users-error").textContent = "用户名和密码不能为空"; return; }
  try {
    await fetchJson("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, is_admin: isAdmin }),
    });
    createUserForm.hidden = true;
    document.getElementById("new-username").value = "";
    document.getElementById("new-password").value = "";
    document.getElementById("new-is-admin").checked = false;
    state.tabLoaded["users"] = false;
    loadUsers();
  } catch (err) {
    document.getElementById("users-error").textContent = String(err);
  }
});

// --- Usage ---
async function loadUsage() {
  const container = document.getElementById("usage-table-container");
  container.textContent = "加载中...";
  const range = document.getElementById("usage-range").value;
  try {
    const data = await fetchJson(`/api/admin/token-usage?range=${range}`);
    const rows = data.usage || [];
    if (!rows.length) {
      container.textContent = "暂无数据";
      return;
    }
    const table = el("table", { className: "data-table" });
    const thead = el("thead", {}, [
      el("tr", {}, [
        el("th", { textContent: "用户" }), el("th", { textContent: "模型" }),
        el("th", { textContent: "输入 Tokens" }), el("th", { textContent: "输出 Tokens" }),
        el("th", { textContent: "请求次数" }),
      ]),
    ]);
    table.appendChild(thead);
    const tbody = el("tbody");
    for (const r of rows) {
      tbody.appendChild(el("tr", {}, [
        el("td", { textContent: r.username || "-" }), el("td", { textContent: r.model }),
        el("td", { textContent: formatNumber(r.input_tokens) }),
        el("td", { textContent: formatNumber(r.output_tokens) }),
        el("td", { textContent: formatNumber(r.request_count) }),
      ]));
    }
    table.appendChild(tbody);
    container.textContent = "";
    container.appendChild(table);
  } catch (err) {
    container.textContent = `加载失败：${err}`;
  }
}

document.getElementById("usage-range").addEventListener("change", () => loadUsage());
document.getElementById("refresh-usage").addEventListener("click", () => loadUsage());

// --- Admin Documents ---
async function loadAdminDocs() {
  const container = document.getElementById("admin-docs-list");
  container.textContent = "加载中...";
  try {
    const data = await fetchJson("/api/documents");
    const docs = data.documents || [];
    container.textContent = "";
    if (!docs.length) { container.textContent = "暂无文档"; return; }
    for (const doc of docs) {
      container.appendChild(el("div", { className: "docs-item" }, [
        el("div", { className: "docs-item-info" }, [
          el("span", { className: "docs-item-title", textContent: doc.title }),
          el("span", { className: "docs-item-meta", textContent: `${doc.category} · ${doc.file_name} · ${doc.uploaded_by}` }),
        ]),
        el("div", { style: "display:flex;gap:8px" }, [
          el("a", { className: "docs-item-download", href: `/api/documents/${doc.id}/download`, download: "", textContent: "下载" }),
          el("button", { className: "btn-danger", textContent: "删除", style: "height:30px;padding:0 12px;font-size:13px", onClick: () => deleteDoc(doc.id) }),
        ]),
      ]));
    }
  } catch (err) {
    container.textContent = `加载失败：${err}`;
  }
}

async function deleteDoc(id) {
  if (!confirm("确认删除此文档？")) return;
  try {
    await fetchJson(`/api/admin/documents/${id}`, { method: "DELETE" });
    loadAdminDocs();
  } catch (err) {
    document.getElementById("docs-error").textContent = String(err);
  }
}

const showUploadDocBtn = document.getElementById("show-upload-doc");
const uploadDocForm = document.getElementById("upload-doc-form");
const uploadDocBtn = document.getElementById("upload-doc-btn");
const cancelUploadDocBtn = document.getElementById("cancel-upload-doc");

showUploadDocBtn.addEventListener("click", () => { uploadDocForm.hidden = false; });
cancelUploadDocBtn.addEventListener("click", () => { uploadDocForm.hidden = true; });
uploadDocBtn.addEventListener("click", async () => {
  const fileInput = document.getElementById("doc-file");
  const file = fileInput.files[0];
  if (!file) { document.getElementById("docs-error").textContent = "请选择文件"; return; }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", document.getElementById("doc-title").value.trim());
  formData.append("category", document.getElementById("doc-category").value.trim());
  try {
    await fetch("/api/admin/documents", { method: "POST", body: formData }).then(async (r) => {
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error(d.error || "上传失败");
    });
    uploadDocForm.hidden = true;
    fileInput.value = "";
    document.getElementById("doc-title").value = "";
    document.getElementById("doc-category").value = "";
    loadAdminDocs();
  } catch (err) {
    document.getElementById("docs-error").textContent = String(err);
  }
});

// --- Config (preserved from original) ---
function setConfigError(message) {
  configErrorEl.textContent = String(message || "");
}

function setConfigSaveResult(message, tone = "") {
  configSaveResultEl.textContent = String(message || "");
  configSaveResultEl.classList.remove("is-success", "is-warning");
  if (!message) return;
  configSaveResultEl.classList.add(tone === "warning" ? "is-warning" : "is-success");
}

function updateConfigButtons() {
  const configBusy = state.loadingConfig || state.savingConfig;
  reloadConfigBtn.disabled = configBusy;
  saveConfigBtn.disabled = configBusy || !state.selectedConfigFileId;
  configFileSelectEl.disabled = configBusy || !state.configFiles.length;
}

function renderConfigFileOptions() {
  configFileSelectEl.textContent = "";
  for (const item of state.configFiles) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.label;
    configFileSelectEl.appendChild(option);
  }
  if (!state.selectedConfigFileId && state.configFiles.length) {
    state.selectedConfigFileId = state.configFiles[0].id;
  }
  configFileSelectEl.value = state.selectedConfigFileId;
}

function applyConfigFileMeta(fileData) {
  configPathEl.textContent = fileData.path || "";
  configDescriptionEl.textContent = fileData.description || "";
  if (fileData.format === "dotenv") {
    configRestartHintEl.textContent = "保存后会自动热更新支持的运行项，结构性配置仍需重启";
    configRestartHintEl.classList.add("is-warning");
    return;
  }
  if (fileData.requires_restart) {
    configRestartHintEl.textContent = "修改该文件后通常需要重启服务";
    configRestartHintEl.classList.add("is-warning");
  } else {
    configRestartHintEl.textContent = "保存后立即生效";
    configRestartHintEl.classList.remove("is-warning");
  }
}

function buildHotReloadMessage(hotReload) {
  const appliedKeys = Array.isArray(hotReload?.applied_keys) ? hotReload.applied_keys : [];
  const restartRequiredKeys = Array.isArray(hotReload?.restart_required_keys) ? hotReload.restart_required_keys : [];
  if (!appliedKeys.length && !restartRequiredKeys.length) return "保存成功，未检测到需要变更的运行项。";
  const parts = [];
  if (appliedKeys.length) parts.push(`已热更新：${appliedKeys.join("、")}`);
  if (restartRequiredKeys.length) parts.push(`仍需重启：${restartRequiredKeys.join("、")}`);
  return parts.join("；");
}

function getHotReloadTone(hotReload) {
  const restartRequiredKeys = Array.isArray(hotReload?.restart_required_keys) ? hotReload.restart_required_keys : [];
  return restartRequiredKeys.length ? "warning" : "success";
}

async function loadConfigFiles() {
  state.loadingConfig = true;
  updateConfigButtons();
  try {
    const data = await fetchJson("/api/admin/config-files");
    state.configFiles = data.files || [];
    if (!state.configFiles.some((item) => item.id === state.selectedConfigFileId)) state.selectedConfigFileId = "";
    state.selectedConfigFileId = state.selectedConfigFileId || data.default_file_id || state.configFiles[0]?.id || "";
    renderConfigFileOptions();
  } finally {
    state.loadingConfig = false;
    updateConfigButtons();
  }
}

async function loadCurrentConfigFile() {
  if (!state.selectedConfigFileId) {
    configEditorEl.value = "";
    configPathEl.textContent = "";
    configDescriptionEl.textContent = "";
    configRestartHintEl.textContent = "";
    setConfigSaveResult("");
    return;
  }
  state.loadingConfig = true;
  updateConfigButtons();
  try {
    const data = await fetchJson(`/api/admin/config-files/${encodeURIComponent(state.selectedConfigFileId)}`);
    configEditorEl.value = data.content || "";
    applyConfigFileMeta(data);
    setConfigSaveResult("");
  } finally {
    state.loadingConfig = false;
    updateConfigButtons();
  }
}

async function initConfigTab() {
  updateConfigButtons();
  try {
    await loadConfigFiles();
    await loadCurrentConfigFile();
  } catch (err) {
    setConfigError(`初始化失败：${err}`);
  }
}

configFileSelectEl.addEventListener("change", async () => {
  state.selectedConfigFileId = configFileSelectEl.value;
  setConfigError("");
  try { await loadCurrentConfigFile(); } catch (err) { setConfigError(`加载配置失败：${err}`); }
});

reloadConfigBtn.addEventListener("click", async () => {
  setConfigError(""); setConfigSaveResult("");
  try { await loadConfigFiles(); await loadCurrentConfigFile(); } catch (err) { setConfigError(`加载配置失败：${err}`); }
});

saveConfigBtn.addEventListener("click", async () => {
  if (state.savingConfig || !state.selectedConfigFileId) return;
  setConfigError(""); setConfigSaveResult("");
  state.savingConfig = true;
  updateConfigButtons();
  try {
    const data = await fetchJson(`/api/admin/config-files/${encodeURIComponent(state.selectedConfigFileId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: configEditorEl.value }),
    });
    configEditorEl.value = data.content || configEditorEl.value;
    applyConfigFileMeta(data);
    if (data.hot_reload) {
      setConfigSaveResult(buildHotReloadMessage(data.hot_reload), getHotReloadTone(data.hot_reload));
    } else {
      setConfigSaveResult(
        data.requires_restart ? "保存成功，修改已写入文件，按提示决定是否重启。" : "保存成功，修改已立即生效。",
        data.requires_restart ? "warning" : "success"
      );
    }
  } catch (err) {
    setConfigError(`保存配置失败：${err}`);
  } finally {
    state.savingConfig = false;
    updateConfigButtons();
  }
});

configEditorEl.addEventListener("input", () => { setConfigSaveResult(""); });

// --- Audit Logs ---
async function loadAuditLogs(append) {
  const container = document.getElementById("audit-table-container");
  if (!append) { container.textContent = "加载中..."; state.auditOffset = 0; }
  try {
    const data = await fetchJson(`/api/admin/audit-logs?limit=50&offset=${state.auditOffset}`);
    const logs = data.logs || [];
    if (!append) container.textContent = "";
    let table = container.querySelector("table");
    let tbody;
    if (!table) {
      table = el("table", { className: "data-table" });
      table.appendChild(el("thead", {}, [
        el("tr", {}, [
          el("th", { textContent: "时间" }), el("th", { textContent: "用户" }),
          el("th", { textContent: "操作" }), el("th", { textContent: "目标" }),
          el("th", { textContent: "详情" }),
        ]),
      ]));
      tbody = el("tbody");
      table.appendChild(tbody);
      container.appendChild(table);
    } else {
      tbody = table.querySelector("tbody");
    }
    for (const log of logs) {
      tbody.appendChild(el("tr", {}, [
        el("td", { textContent: (log.created_at || "").slice(0, 19) }),
        el("td", { textContent: log.username }),
        el("td", { textContent: log.action }),
        el("td", { textContent: `${log.target_type} ${log.target_id}`.trim() }),
        el("td", { textContent: log.detail }),
      ]));
    }
    state.auditOffset += logs.length;
    if (!logs.length && !append) container.textContent = "暂无日志";
    document.getElementById("audit-load-more").hidden = logs.length < 50;
  } catch (err) {
    if (!append) container.textContent = `加载失败：${err}`;
  }
}

document.getElementById("refresh-audit").addEventListener("click", () => { state.auditOffset = 0; loadAuditLogs(false); });
document.getElementById("audit-load-more").addEventListener("click", () => loadAuditLogs(true));

// --- Navigation ---
chatBtn.addEventListener("click", () => { window.location.href = "/chat"; });
logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

// --- Init ---
switchTab("dashboard");
