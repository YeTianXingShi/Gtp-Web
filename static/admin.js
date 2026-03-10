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
};

function setConfigError(message) {
  configErrorEl.textContent = String(message || "");
}

function setConfigSaveResult(message, tone = "") {
  configSaveResultEl.textContent = String(message || "");
  configSaveResultEl.classList.remove("is-success", "is-warning");
  if (!message) return;
  configSaveResultEl.classList.add(tone === "warning" ? "is-warning" : "is-success");
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
  const configBusy = state.loadingConfig || state.savingConfig;
  reloadConfigBtn.disabled = configBusy;
  saveConfigBtn.disabled = configBusy || !state.selectedConfigFileId;
  configFileSelectEl.disabled = configBusy || !state.configFiles.length;
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
  const restartRequiredKeys = Array.isArray(hotReload?.restart_required_keys)
    ? hotReload.restart_required_keys
    : [];

  if (!appliedKeys.length && !restartRequiredKeys.length) {
    return "保存成功，未检测到需要变更的运行项。";
  }

  const parts = [];
  if (appliedKeys.length) {
    parts.push(`已热更新：${appliedKeys.join("、")}`);
  }
  if (restartRequiredKeys.length) {
    parts.push(`仍需重启：${restartRequiredKeys.join("、")}`);
  }
  return parts.join("；");
}

function getHotReloadTone(hotReload) {
  const restartRequiredKeys = Array.isArray(hotReload?.restart_required_keys)
    ? hotReload.restart_required_keys
    : [];
  return restartRequiredKeys.length ? "warning" : "success";
}

async function loadConfigFiles() {
  state.loadingConfig = true;
  updateActionButtons();
  try {
    const data = await fetchJson("/api/admin/config-files");
    state.configFiles = data.files || [];
    if (!state.configFiles.some((item) => item.id === state.selectedConfigFileId)) {
      state.selectedConfigFileId = "";
    }
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
    setConfigSaveResult("");
    return;
  }

  state.loadingConfig = true;
  updateActionButtons();
  try {
    const data = await fetchJson(`/api/admin/config-files/${encodeURIComponent(state.selectedConfigFileId)}`);
    configEditorEl.value = data.content || "";
    applyConfigFileMeta(data);
    setConfigSaveResult("");
  } finally {
    state.loadingConfig = false;
    updateActionButtons();
  }
}

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
  setConfigSaveResult("");
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
  setConfigSaveResult("");
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
    updateActionButtons();
  }
});

configEditorEl.addEventListener("input", () => {
  setConfigSaveResult("");
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
    await loadConfigFiles();
    await loadCurrentConfigFile();
  } catch (err) {
    setConfigError(`初始化失败：${err}`);
  }
})();
