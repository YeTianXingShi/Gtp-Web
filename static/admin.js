const chatBtn = document.getElementById("chat-btn");
const logoutBtn = document.getElementById("logout-btn");
const reloadUsersBtn = document.getElementById("reload-users-btn");
const reloadConfigBtn = document.getElementById("reload-config-btn");
const saveConfigBtn = document.getElementById("save-config-btn");
const createUserForm = document.getElementById("create-user-form");
const newUsernameEl = document.getElementById("new-username");
const newPasswordEl = document.getElementById("new-password");
const newIsAdminEl = document.getElementById("new-is-admin");
const usersListEl = document.getElementById("users-list");
const usersErrorEl = document.getElementById("users-error");
const configErrorEl = document.getElementById("config-error");
const configEditorEl = document.getElementById("config-editor");
const configPathEl = document.getElementById("config-path");
const configFileSelectEl = document.getElementById("config-file-select");
const configDescriptionEl = document.getElementById("config-description");
const configRestartHintEl = document.getElementById("config-restart-hint");

const state = {
  users: [],
  configFiles: Array.isArray(window.__ADMIN_CONFIG__?.configFiles)
    ? window.__ADMIN_CONFIG__.configFiles.slice()
    : [],
  selectedConfigFileId: "",
  loadingUsers: false,
  savingUsers: false,
  loadingConfig: false,
  savingConfig: false,
};

function setUsersError(message) {
  usersErrorEl.textContent = String(message || "");
}

function setConfigError(message) {
  configErrorEl.textContent = String(message || "");
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function updateActionButtons() {
  const userBusy = state.loadingUsers || state.savingUsers;
  const configBusy = state.loadingConfig || state.savingConfig;
  reloadUsersBtn.disabled = userBusy;
  reloadConfigBtn.disabled = configBusy;
  saveConfigBtn.disabled = configBusy || !state.selectedConfigFileId;
  configFileSelectEl.disabled = configBusy || !state.configFiles.length;
  createUserForm.querySelector("button[type='submit']").disabled = userBusy;
}

function renderUsers() {
  usersListEl.innerHTML = "";
  if (!state.users.length) {
    const empty = document.createElement("div");
    empty.className = "admin-empty";
    empty.textContent = "暂无用户";
    usersListEl.appendChild(empty);
    return;
  }

  for (const user of state.users) {
    const card = document.createElement("article");
    card.className = "user-card";

    const head = document.createElement("div");
    head.className = "user-card-head";

    const title = document.createElement("div");
    title.className = "user-card-title";
    const name = document.createElement("strong");
    name.textContent = user.username;
    const badge = document.createElement("span");
    badge.className = `role-badge${user.is_admin ? " is-admin" : ""}`;
    badge.textContent = user.is_admin ? "管理员" : "普通用户";
    title.appendChild(name);
    title.appendChild(badge);
    head.appendChild(title);
    card.appendChild(head);

    const passwordLabel = document.createElement("label");
    passwordLabel.className = "stack-field";
    const passwordText = document.createElement("span");
    passwordText.textContent = "重置密码";
    const passwordInput = document.createElement("input");
    passwordInput.type = "password";
    passwordInput.placeholder = "留空表示不修改";
    passwordInput.maxLength = 120;
    passwordLabel.appendChild(passwordText);
    passwordLabel.appendChild(passwordInput);

    const adminLabel = document.createElement("label");
    adminLabel.className = "toggle-field stack-field";
    const adminText = document.createElement("span");
    adminText.textContent = "管理员权限";
    const adminInline = document.createElement("div");
    adminInline.className = "toggle-inline";
    const adminCheckbox = document.createElement("input");
    adminCheckbox.type = "checkbox";
    adminCheckbox.checked = Boolean(user.is_admin);
    const adminHint = document.createElement("span");
    adminHint.textContent = "允许访问后台管理";
    adminInline.appendChild(adminCheckbox);
    adminInline.appendChild(adminHint);
    adminLabel.appendChild(adminText);
    adminLabel.appendChild(adminInline);

    const actions = document.createElement("div");
    actions.className = "user-card-actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "保存";
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn-danger";
    deleteBtn.textContent = "删除";

    saveBtn.addEventListener("click", async () => {
      if (state.savingUsers) return;
      setUsersError("");
      state.savingUsers = true;
      updateActionButtons();
      try {
        const payload = { is_admin: adminCheckbox.checked };
        if (passwordInput.value) {
          payload.password = passwordInput.value;
        }
        await fetchJson(`/api/admin/users/${encodeURIComponent(user.username)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        passwordInput.value = "";
        await loadUsers();
        await loadCurrentConfigFile();
      } catch (err) {
        setUsersError(`保存用户失败：${err}`);
      } finally {
        state.savingUsers = false;
        updateActionButtons();
      }
    });

    deleteBtn.addEventListener("click", async () => {
      if (state.savingUsers) return;
      const confirmed = window.confirm(`确认删除用户 ${user.username} 吗？`);
      if (!confirmed) return;
      setUsersError("");
      state.savingUsers = true;
      updateActionButtons();
      try {
        await fetchJson(`/api/admin/users/${encodeURIComponent(user.username)}`, {
          method: "DELETE",
        });
        await loadUsers();
        await loadCurrentConfigFile();
      } catch (err) {
        setUsersError(`删除用户失败：${err}`);
      } finally {
        state.savingUsers = false;
        updateActionButtons();
      }
    });

    actions.appendChild(saveBtn);
    actions.appendChild(deleteBtn);
    card.appendChild(passwordLabel);
    card.appendChild(adminLabel);
    card.appendChild(actions);
    usersListEl.appendChild(card);
  }
}

function renderConfigFileOptions() {
  configFileSelectEl.innerHTML = "";
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
  if (fileData.requires_restart) {
    configRestartHintEl.textContent = "修改该文件后通常需要重启服务";
    configRestartHintEl.classList.add("is-warning");
  } else {
    configRestartHintEl.textContent = "保存后立即生效";
    configRestartHintEl.classList.remove("is-warning");
  }
}

async function loadUsers() {
  state.loadingUsers = true;
  updateActionButtons();
  try {
    const data = await fetchJson("/api/admin/users");
    state.users = data.users || [];
    renderUsers();
  } finally {
    state.loadingUsers = false;
    updateActionButtons();
  }
}

async function loadConfigFiles() {
  state.loadingConfig = true;
  updateActionButtons();
  try {
    const data = await fetchJson("/api/admin/config-files");
    state.configFiles = data.files || [];
    state.selectedConfigFileId =
      state.selectedConfigFileId || data.default_file_id || state.configFiles[0]?.id || "";
    renderConfigFileOptions();
  } finally {
    state.loadingConfig = false;
    updateActionButtons();
  }
}

async function loadCurrentConfigFile() {
  if (!state.selectedConfigFileId) {
    configEditorEl.value = "";
    configPathEl.textContent = "";
    configDescriptionEl.textContent = "";
    configRestartHintEl.textContent = "";
    return;
  }

  state.loadingConfig = true;
  updateActionButtons();
  try {
    const data = await fetchJson(`/api/admin/config-files/${encodeURIComponent(state.selectedConfigFileId)}`);
    configEditorEl.value = data.content || "";
    applyConfigFileMeta(data);
  } finally {
    state.loadingConfig = false;
    updateActionButtons();
  }
}

createUserForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.savingUsers) return;

  setUsersError("");
  state.savingUsers = true;
  updateActionButtons();
  try {
    await fetchJson("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: newUsernameEl.value.trim(),
        password: newPasswordEl.value,
        is_admin: newIsAdminEl.checked,
      }),
    });
    createUserForm.reset();
    await loadUsers();
    await loadCurrentConfigFile();
  } catch (err) {
    setUsersError(`新增用户失败：${err}`);
  } finally {
    state.savingUsers = false;
    updateActionButtons();
  }
});

reloadUsersBtn.addEventListener("click", async () => {
  setUsersError("");
  try {
    await loadUsers();
  } catch (err) {
    setUsersError(`加载用户失败：${err}`);
  }
});

configFileSelectEl.addEventListener("change", async () => {
  state.selectedConfigFileId = configFileSelectEl.value;
  setConfigError("");
  try {
    await loadCurrentConfigFile();
  } catch (err) {
    setConfigError(`加载配置失败：${err}`);
  }
});

reloadConfigBtn.addEventListener("click", async () => {
  setConfigError("");
  try {
    await loadConfigFiles();
    await loadCurrentConfigFile();
  } catch (err) {
    setConfigError(`加载配置失败：${err}`);
  }
});

saveConfigBtn.addEventListener("click", async () => {
  if (state.savingConfig || !state.selectedConfigFileId) return;
  setConfigError("");
  state.savingConfig = true;
  updateActionButtons();
  try {
    const data = await fetchJson(
      `/api/admin/config-files/${encodeURIComponent(state.selectedConfigFileId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: configEditorEl.value }),
      }
    );
    configEditorEl.value = data.content || configEditorEl.value;
    applyConfigFileMeta(data);
    if (state.selectedConfigFileId === "auth_users") {
      await loadUsers();
    }
  } catch (err) {
    setConfigError(`保存配置失败：${err}`);
  } finally {
    state.savingConfig = false;
    updateActionButtons();
  }
});

chatBtn.addEventListener("click", () => {
  window.location.href = "/chat";
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

(async function init() {
  updateActionButtons();
  try {
    await loadUsers();
    await loadConfigFiles();
    await loadCurrentConfigFile();
  } catch (err) {
    setUsersError(`初始化失败：${err}`);
  }
})();
