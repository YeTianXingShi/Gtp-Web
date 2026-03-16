const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const promptEl = document.getElementById("prompt");
const modelSelectEl = document.getElementById("model-select");
const modelSettingFieldEl = document.getElementById("model-setting-field");
const modelSettingLabelEl = document.getElementById("model-setting-label");
const modelSettingSelectEl = document.getElementById("model-setting-select");
const logoutBtn = document.getElementById("logout-btn");
const adminBtn = document.getElementById("admin-btn");
const sendBtn = document.getElementById("send-btn");
const newConvBtn = document.getElementById("new-conv-btn");
const renameConvBtn = document.getElementById("rename-conv-btn");
const exportConvBtn = document.getElementById("export-conv-btn");
const exportMenuEl = document.getElementById("export-menu");
const exportMenuItemEls = Array.from(document.querySelectorAll("[data-export-format]"));
const deleteConvBtn = document.getElementById("delete-conv-btn");
const deleteConfirmPanelEl = document.getElementById("delete-confirm-panel");
const confirmDeleteBtn = document.getElementById("confirm-delete-btn");
const cancelDeleteBtn = document.getElementById("cancel-delete-btn");
const searchInputEl = document.getElementById("search-input");
const conversationListEl = document.getElementById("conversation-list");
const fileInputEl = document.getElementById("file-input");
const selectedFilesEl = document.getElementById("selected-files");

const state = {
  conversations: [],
  currentConversationId: null,
  sending: false,
  renaming: false,
  deleting: false,
  syncingConversationSettings: false,
  searchKeyword: "",
  editingConversationId: null,
  editingTitleDraft: "",
  pendingFiles: [],
  exportMenuOpen: false,
  deleteConfirmOpen: false,
};

let searchDebounceTimer = null;
const MAX_FILES_PER_MESSAGE =
  Number.parseInt(window.__APP_CONFIG__?.maxAttachmentsPerMessage, 10) || 5;
const MAX_UPLOAD_MB = Number.parseInt(window.__APP_CONFIG__?.maxUploadMB, 10) || 15;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const MODEL_OPTIONS = Array.isArray(window.__APP_CONFIG__?.modelOptions)
  ? window.__APP_CONFIG__.modelOptions
  : [];
const MODEL_OPTION_MAP = new Map(
  MODEL_OPTIONS.map((item) => [String(item?.id || ""), item])
);
const ALLOWED_ATTACHMENT_EXTS = Array.isArray(
  window.__APP_CONFIG__?.allowedAttachmentExts
)
  ? window.__APP_CONFIG__.allowedAttachmentExts.map((ext) =>
      String(ext || "").trim().toLowerCase()
    )
  : [];
const ALLOWED_ATTACHMENT_EXT_SET = new Set(
  ALLOWED_ATTACHMENT_EXTS.filter(Boolean)
);
const IMAGE_ATTACHMENT_EXT_SET = new Set([".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]);
const MIME_TO_EXT = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "image/gif": ".gif",
  "image/bmp": ".bmp",
  "text/plain": ".txt",
  "text/markdown": ".md",
  "text/x-markdown": ".md",
  "application/json": ".json",
  "text/csv": ".csv",
  "text/tab-separated-values": ".tsv",
  "application/xml": ".xml",
  "text/xml": ".xml",
  "text/html": ".html",
  "application/msword": ".doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "application/vnd.ms-excel": ".xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
};
const temporaryMessageObjectUrls = new Set();
const STREAM_IDLE_TIMEOUT_MS = 30000;
const STREAM_IDLE_TIMEOUT_SECONDS = Math.floor(STREAM_IDLE_TIMEOUT_MS / 1000);
let pendingFileSeq = 0;
const SUPPORTED_EXPORT_FORMATS = new Set(["json", "txt", "md"]);

function escapeHtml(raw) {
  return String(raw ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderInlineMarkdown(text) {
  let rendered = escapeHtml(text);
  const inlineTokens = [];

  rendered = rendered.replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@MD_INLINE_${inlineTokens.length}@@`;
    inlineTokens.push(`<code>${code}</code>`);
    return token;
  });

  rendered = rendered.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, rawUrl) => {
    const url = String(rawUrl || "").trim();
    if (!/^(https?:\/\/|mailto:)/i.test(url)) {
      return label;
    }
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  rendered = rendered.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  rendered = rendered.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");

  rendered = rendered.replace(/@@MD_INLINE_(\d+)@@/g, (_, idx) => {
    const html = inlineTokens[Number.parseInt(idx, 10)];
    return html || "";
  });
  return rendered;
}

function renderMarkdown(raw) {
  const normalized = String(raw ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (!normalized.trim()) return "";

  const blockTokens = [];
  const textWithBlocks = normalized.replace(
    /```([^\n`]*)\n([\s\S]*?)```/g,
    (_, language, codeText) => {
      const lang = String(language || "").trim().toLowerCase();
      const token = `@@MD_BLOCK_${blockTokens.length}@@`;
      const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      blockTokens.push(`<pre><code${langClass}>${escapeHtml(codeText)}</code></pre>`);
      return `\n${token}\n`;
    }
  );

  const lines = textWithBlocks.split("\n");
  const htmlBlocks = [];

  const isBlockToken = (line) => /^@@MD_BLOCK_\d+@@$/.test(line.trim());
  const isHeading = (line) => /^\s{0,3}#{1,6}\s+/.test(line);
  const isHr = (line) => /^\s*([-*_]\s*){3,}$/.test(line);
  const isQuote = (line) => /^\s*>\s?/.test(line);
  const isUnordered = (line) => /^\s*[-*+]\s+/.test(line);
  const isOrdered = (line) => /^\s*\d+\.\s+/.test(line);
  const isBoundary = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return true;
    return (
      isBlockToken(line) ||
      isHeading(line) ||
      isHr(line) ||
      isQuote(line) ||
      isUnordered(line) ||
      isOrdered(line)
    );
  };

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (isBlockToken(line)) {
      const match = /@@MD_BLOCK_(\d+)@@/.exec(trimmed);
      const tokenIndex = Number.parseInt(match?.[1] || "-1", 10);
      htmlBlocks.push(blockTokens[tokenIndex] || "");
      index += 1;
      continue;
    }

    if (isHr(line)) {
      htmlBlocks.push("<hr />");
      index += 1;
      continue;
    }

    const headingMatch = /^\s{0,3}(#{1,6})\s+(.+)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      htmlBlocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (isQuote(line)) {
      const quoteLines = [];
      while (index < lines.length && isQuote(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      const quoteHtml = renderInlineMarkdown(quoteLines.join("\n")).replaceAll("\n", "<br>");
      htmlBlocks.push(`<blockquote>${quoteHtml}</blockquote>`);
      continue;
    }

    if (isUnordered(line) || isOrdered(line)) {
      const ordered = isOrdered(line);
      const itemPattern = ordered ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
      const tagName = ordered ? "ol" : "ul";
      const items = [];
      while (index < lines.length) {
        const itemMatch = itemPattern.exec(lines[index]);
        if (!itemMatch) break;
        items.push(`<li>${renderInlineMarkdown(itemMatch[1])}</li>`);
        index += 1;
      }
      htmlBlocks.push(`<${tagName}>${items.join("")}</${tagName}>`);
      continue;
    }

    const paragraphLines = [line];
    index += 1;
    while (index < lines.length && !isBoundary(lines[index])) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    const paragraphHtml = renderInlineMarkdown(paragraphLines.join("\n")).replaceAll(
      "\n",
      "<br>"
    );
    htmlBlocks.push(`<p>${paragraphHtml}</p>`);
  }

  return htmlBlocks.join("");
}

function isImageMimeType(mimeType) {
  return String(mimeType || "")
    .trim()
    .toLowerCase()
    .startsWith("image/");
}

function isImageFileName(fileName) {
  return IMAGE_ATTACHMENT_EXT_SET.has(getFileExt(String(fileName || "")));
}

function isImageFile(file) {
  return isImageMimeType(file.type) || isImageFileName(file.name);
}

function stripAttachmentMarkerLines(text) {
  return String(text || "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("[附件] "))
    .join("\n")
    .trim();
}

function registerTemporaryMessageObjectUrl(url) {
  if (url && typeof url === "string" && url.startsWith("blob:")) {
    temporaryMessageObjectUrls.add(url);
  }
}

function revokeAllTemporaryMessageObjectUrls() {
  for (const url of temporaryMessageObjectUrls) {
    URL.revokeObjectURL(url);
  }
  temporaryMessageObjectUrls.clear();
}

function renderMessageAttachments(contentEl, attachments) {
  if (!Array.isArray(attachments) || !attachments.length) return;

  const wrapper = document.createElement("div");
  wrapper.className = "message-attachments";

  for (const attachment of attachments) {
    const fileName = String(attachment.file_name || "未命名附件");
    const mimeType = String(attachment.mime_type || "").trim().toLowerCase();
    const previewUrl = String(attachment.preview_url || "");
    const isImage =
      typeof attachment.is_image === "boolean"
        ? attachment.is_image
        : isImageMimeType(mimeType) || isImageFileName(fileName);

    const item = document.createElement("div");
    item.className = `message-attachment${isImage ? " is-image" : ""}`;

    if (isImage && previewUrl) {
      const link = document.createElement("a");
      link.className = "message-attachment-image-link";
      link.href = previewUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";

      const img = document.createElement("img");
      img.className = "message-attachment-image";
      img.src = previewUrl;
      img.alt = fileName;
      img.loading = "lazy";

      link.appendChild(img);
      item.appendChild(link);
    }

    const meta = document.createElement("div");
    meta.className = "message-attachment-meta";

    const nameEl = document.createElement("span");
    nameEl.className = "message-attachment-name";
    nameEl.textContent = fileName;
    meta.appendChild(nameEl);

    if (!isImage && mimeType) {
      const typeEl = document.createElement("span");
      typeEl.className = "message-attachment-type";
      typeEl.textContent = mimeType;
      meta.appendChild(typeEl);
    }

    item.appendChild(meta);
    wrapper.appendChild(item);
  }

  contentEl.appendChild(wrapper);
}

function addMessage(role, content, options = {}) {
  const {
    autoScroll = true,
    attachments = [],
    reasoning = "",
    status = "complete",
    actions = [],
  } = options;
  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (status === "incomplete") {
    div.classList.add("is-incomplete");
  }
  const contentEl = document.createElement("div");
  contentEl.className = "message-content";
  contentEl.innerHTML = renderMarkdown(content);
  renderMessageAttachments(contentEl, attachments);
  div.appendChild(contentEl);

  if (reasoning) {
    const { panelEl, contentEl: reasoningContentEl } = ensureReasoningPanel(div);
    panelEl.hidden = false;
    reasoningContentEl.innerHTML = renderMarkdown(reasoning);
  }

  if (Array.isArray(actions) && actions.length) {
    const actionsEl = document.createElement("div");
    actionsEl.className = "message-actions";
    for (const action of actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = action.className || "message-action-btn";
      button.textContent = action.label || "操作";
      if (action.disabled) {
        button.disabled = true;
      }
      button.addEventListener("click", (event) => {
        action.onClick?.(event, { buttonEl: button, messageEl: div });
      });
      actionsEl.appendChild(button);
    }
    div.appendChild(actionsEl);
  }

  messagesEl.appendChild(div);
  if (autoScroll) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  return div;
}

function ensureReasoningPanel(messageEl) {
  let panelEl = messageEl.querySelector(".message-reasoning");
  let contentEl = panelEl?.querySelector(".message-reasoning-content") || null;
  if (panelEl && contentEl) {
    return { panelEl, contentEl };
  }

  panelEl = document.createElement("details");
  panelEl.className = "message-reasoning";
  panelEl.hidden = true;
  panelEl.open = true;

  const summaryEl = document.createElement("summary");
  summaryEl.textContent = "思考摘要";
  panelEl.appendChild(summaryEl);

  contentEl = document.createElement("div");
  contentEl.className = "message-reasoning-content";
  panelEl.appendChild(contentEl);

  const messageContentEl = messageEl.querySelector(".message-content");
  if (messageContentEl) {
    messageEl.insertBefore(panelEl, messageContentEl);
  } else {
    messageEl.appendChild(panelEl);
  }

  return { panelEl, contentEl };
}

function clearMessages() {
  revokeAllTemporaryMessageObjectUrls();
  messagesEl.innerHTML = "";
}

function clearRetryPrompts() {
  for (const el of messagesEl.querySelectorAll(".message.system.is-retry-prompt")) {
    el.remove();
  }
}

function setRetryButtonsDisabled(disabled) {
  for (const button of messagesEl.querySelectorAll(".message-retry-btn")) {
    button.disabled = disabled;
  }
}

function analyzeRetryState(messages) {
  if (!Array.isArray(messages) || !messages.length) {
    return { kind: "none" };
  }

  const last = messages[messages.length - 1];
  const previous = messages.length > 1 ? messages[messages.length - 2] : null;
  if (last.role === "assistant") {
    if (last.status === "complete") {
      return { kind: "complete" };
    }
    if (last.status === "incomplete" && previous?.role === "user") {
      return {
        kind: "retry",
        hasIncompleteAssistant: true,
      };
    }
    return { kind: "unsupported" };
  }

  if (last.role === "user") {
    return {
      kind: "retry",
      hasIncompleteAssistant: false,
    };
  }

  return { kind: "unsupported" };
}

function resetAssistantMessageForRetry(assistantEl) {
  if (!assistantEl) return;
  assistantEl.classList.remove("is-incomplete");
  const contentEl = assistantEl.querySelector(".message-content");
  if (contentEl) {
    contentEl.classList.remove("is-streaming");
    contentEl.textContent = "";
  }
  const attachmentsEl = assistantEl.querySelector(".message-attachments");
  attachmentsEl?.remove();
  const reasoningEl = assistantEl.querySelector(".message-reasoning");
  reasoningEl?.remove();
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function createPendingFileItem(file) {
  const image = isImageFile(file);
  return {
    id: `${Date.now()}_${pendingFileSeq++}`,
    file,
    isImage: image,
    previewUrl: image ? URL.createObjectURL(file) : "",
  };
}

function revokePendingFilePreview(item) {
  if (item && item.previewUrl) {
    URL.revokeObjectURL(item.previewUrl);
  }
}

function clearPendingFiles() {
  for (const item of state.pendingFiles) {
    revokePendingFilePreview(item);
  }
  state.pendingFiles = [];
  fileInputEl.value = "";
  renderSelectedFiles();
}

function renderSelectedFiles() {
  selectedFilesEl.innerHTML = "";
  if (!state.pendingFiles.length) {
    const hint = document.createElement("span");
    hint.className = "selected-files-hint";
    hint.textContent = "未选择附件，可直接在输入框粘贴文件";
    selectedFilesEl.appendChild(hint);
    return;
  }

  for (const [index, item] of state.pendingFiles.entries()) {
    const file = item.file;
    const chip = document.createElement("span");
    chip.className = `file-chip${item.isImage ? " is-image" : ""}`;

    if (item.isImage && item.previewUrl) {
      const img = document.createElement("img");
      img.className = "file-chip-image";
      img.src = item.previewUrl;
      img.alt = file.name;
      chip.appendChild(img);
    }

    const label = document.createElement("span");
    label.className = "file-chip-label";
    label.textContent = `${file.name} (${formatFileSize(file.size)})`;
    chip.appendChild(label);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "file-chip-remove";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      const removed = state.pendingFiles.splice(index, 1)[0];
      revokePendingFilePreview(removed);
      renderSelectedFiles();
    });

    chip.appendChild(removeBtn);
    selectedFilesEl.appendChild(chip);
  }
}

function getFileExt(fileName) {
  const idx = fileName.lastIndexOf(".");
  if (idx <= 0 || idx === fileName.length - 1) return "";
  return fileName.slice(idx).toLowerCase();
}

function isAllowedAttachment(file) {
  if (!ALLOWED_ATTACHMENT_EXT_SET.size) return true;
  return ALLOWED_ATTACHMENT_EXT_SET.has(getFileExt(file.name));
}

function inferExtFromMimeType(mimeType) {
  const key = String(mimeType || "").trim().toLowerCase();
  return MIME_TO_EXT[key] || "";
}

function normalizeIncomingFile(file, source = "picker") {
  if (!(file instanceof File)) return null;

  const rawName = String(file.name || "").trim();
  if (rawName && getFileExt(rawName)) {
    return file;
  }

  const extByMime = inferExtFromMimeType(file.type);
  let baseName = rawName || `${source}_file_${Date.now()}`;
  baseName = baseName.replace(/[\\/:*?"<>|]/g, "_").trim();
  if (!baseName) {
    baseName = `file_${Date.now()}`;
  }

  const normalizedName = getFileExt(baseName) ? baseName : `${baseName}${extByMime}`;
  if (!normalizedName) return file;

  try {
    return new File([file], normalizedName, {
      type: file.type || "application/octet-stream",
      lastModified: file.lastModified || Date.now(),
    });
  } catch {
    return file;
  }
}

function appendPendingFiles(incomingFiles, source = "picker") {
  if (!Array.isArray(incomingFiles) || !incomingFiles.length) return;

  const merged = [...state.pendingFiles];
  for (const rawFile of incomingFiles) {
    const file = normalizeIncomingFile(rawFile, source);
    if (!file) continue;

    if (!isAllowedAttachment(file)) {
      addMessage("system", `不支持的文件类型：${file.name}`);
      continue;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      addMessage("system", `文件 ${file.name} 超过 ${MAX_UPLOAD_MB}MB 限制。`);
      continue;
    }
    if (merged.length >= MAX_FILES_PER_MESSAGE) {
      addMessage("system", `单次最多选择 ${MAX_FILES_PER_MESSAGE} 个附件。`);
      break;
    }
    merged.push(createPendingFileItem(file));
  }

  state.pendingFiles = merged;
  fileInputEl.value = "";
  renderSelectedFiles();
}

function buildFileFingerprint(file) {
  return [
    String(file.name || ""),
    String(file.type || ""),
    String(file.size || 0),
    String(file.lastModified || 0),
  ].join("::");
}

function clipboardLooksLikeFilePaste(clipboardData) {
  if (!clipboardData) return false;

  const types = Array.from(clipboardData.types || []).map((type) =>
    String(type || "").trim().toLowerCase()
  );
  if (types.includes("files")) {
    return true;
  }

  return Array.from(clipboardData.items || []).some((item) => item.kind === "file");
}

function collectClipboardFiles(clipboardData) {
  if (!clipboardData) return [];

  const seen = new Set();
  const files = [];
  const pushFile = (file) => {
    if (!(file instanceof File)) return;
    const fingerprint = buildFileFingerprint(file);
    if (seen.has(fingerprint)) return;
    seen.add(fingerprint);
    files.push(file);
  };

  for (const file of Array.from(clipboardData.files || [])) {
    pushFile(file);
  }

  for (const item of Array.from(clipboardData.items || [])) {
    if (item.kind !== "file") continue;
    const file = item.getAsFile();
    if (!file) continue;
    pushFile(file);
  }

  return files;
}

function buildLocalMessageAttachments(pendingFiles) {
  return pendingFiles.map((item) => {
    const file = item.file;
    const previewUrl = item.isImage ? URL.createObjectURL(file) : "";
    registerTemporaryMessageObjectUrl(previewUrl);
    return {
      file_name: file.name,
      mime_type: file.type || "",
      is_image: item.isImage,
      kind: item.isImage ? "image" : "binary",
      preview_url: previewUrl,
    };
  });
}

function getCurrentConversation() {
  return (
    state.conversations.find((item) => item.id === state.currentConversationId) || null
  );
}

function getModelConfig(modelId) {
  return MODEL_OPTION_MAP.get(String(modelId || "")) || null;
}

function getModelSettingOptionLabel(modelOption, key, optionValue) {
  const value = String(optionValue || "").trim().toLowerCase();
  if (!value) return "";

  if (key === "reasoning_effort") {
    const openAiLabels = {
      minimal: "极简",
      low: "低",
      medium: "中",
      high: "高",
      xhigh: "超高",
    };
    return openAiLabels[value] || value;
  }

  if (key === "thinking_level" && modelOption?.provider === "google") {
    const modelName = String(modelOption.name || "").toLowerCase();
    const baseLabels = {
      minimal: "极简",
      low: "低",
      medium: "中",
      high: "高",
      xhigh: "超高",
    };

    if (modelName.includes("gemini-3") && modelName.includes("pro")) {
      if (value === "low") return "低";
      if (value === "high") return "高";
    }

    if (modelName.includes("gemini-3") && modelName.includes("flash")) {
      return baseLabels[value] || value;
    }

    return baseLabels[value] || value;
  }

  return value;
}

function buildModelSettingOptions(modelOption, key, rawOptions) {
  return rawOptions
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean)
    .map((value) => ({
      value,
      label: getModelSettingOptionLabel(modelOption, key, value),
    }));
}

function getModelSettingDescriptor(modelId) {
  const modelOption = getModelConfig(modelId);
  if (!modelOption) return null;

  const reasoning = modelOption.reasoning;
  if (
    modelOption.provider === "openai" &&
    reasoning?.enabled &&
    Array.isArray(reasoning.effort_options) &&
    reasoning.effort_options.length
  ) {
    const options = buildModelSettingOptions(
      modelOption,
      "reasoning_effort",
      reasoning.effort_options
    );
    if (!options.length) return null;
    return {
      key: "reasoning_effort",
      label: "思考强度：",
      options,
      defaultValue: String(reasoning.effort || options[0]?.value || "")
        .trim()
        .toLowerCase(),
    };
  }

  const thinking = modelOption.thinking;
  if (
    modelOption.provider === "google" &&
    thinking?.enabled &&
    Array.isArray(thinking.level_options) &&
    thinking.level_options.length
  ) {
    const options = buildModelSettingOptions(
      modelOption,
      "thinking_level",
      thinking.level_options
    );
    if (!options.length) return null;
    return {
      key: "thinking_level",
      label: "思考等级：",
      options,
      defaultValue: String(thinking.level || options[0]?.value || "")
        .trim()
        .toLowerCase(),
    };
  }

  return null;
}

function normalizeModelSettingValue(descriptor, rawValue) {
  if (!descriptor) return "";
  const normalized = String(rawValue || "").trim().toLowerCase();
  const optionValues = descriptor.options.map((item) => item.value);
  if (optionValues.includes(normalized)) {
    return normalized;
  }
  if (optionValues.includes(descriptor.defaultValue)) {
    return descriptor.defaultValue;
  }
  return optionValues[0] || "";
}

function syncModelSettingControl(options = {}) {
  const {
    modelId = modelSelectEl.value,
    reasoningEffort = "",
    thinkingLevel = "",
    preserveCurrentValue = false,
  } = options;

  if (!modelSettingFieldEl || !modelSettingLabelEl || !modelSettingSelectEl) {
    return { reasoning_effort: "", thinking_level: "" };
  }

  const descriptor = getModelSettingDescriptor(modelId);
  if (!descriptor) {
    modelSettingFieldEl.hidden = true;
    modelSettingSelectEl.innerHTML = "";
    modelSettingSelectEl.disabled = true;
    return { reasoning_effort: "", thinking_level: "" };
  }

  const preferredValue = preserveCurrentValue
    ? modelSettingSelectEl.value
    : descriptor.key === "reasoning_effort"
      ? reasoningEffort
      : thinkingLevel;
  const normalizedValue = normalizeModelSettingValue(descriptor, preferredValue);

  modelSettingLabelEl.textContent = descriptor.label;
  modelSettingSelectEl.innerHTML = "";
  for (const optionItem of descriptor.options) {
    const optionEl = document.createElement("option");
    optionEl.value = optionItem.value;
    optionEl.textContent = optionItem.label;
    modelSettingSelectEl.appendChild(optionEl);
  }
  modelSettingFieldEl.hidden = false;
  modelSettingSelectEl.disabled = false;
  modelSettingSelectEl.value = normalizedValue;

  if (descriptor.key === "reasoning_effort") {
    return { reasoning_effort: normalizedValue, thinking_level: "" };
  }
  return { reasoning_effort: "", thinking_level: normalizedValue };
}

function getSelectedModelSettings() {
  const descriptor = getModelSettingDescriptor(modelSelectEl.value);
  if (!descriptor || !modelSettingSelectEl || modelSettingFieldEl?.hidden) {
    return { reasoning_effort: "", thinking_level: "" };
  }

  const normalizedValue = normalizeModelSettingValue(
    descriptor,
    modelSettingSelectEl.value
  );
  modelSettingSelectEl.value = normalizedValue;
  if (descriptor.key === "reasoning_effort") {
    return { reasoning_effort: normalizedValue, thinking_level: "" };
  }
  return { reasoning_effort: "", thinking_level: normalizedValue };
}

function applyConversationSelection(conversation) {
  if (!conversation) {
    syncModelSettingControl({
      modelId: modelSelectEl.value,
      preserveCurrentValue: true,
    });
    return;
  }

  modelSelectEl.value = conversation.model;
  syncModelSettingControl({
    modelId: conversation.model,
    reasoningEffort: conversation.reasoning_effort || "",
    thinkingLevel: conversation.thinking_level || "",
  });
}

function getConversationSelectionSnapshot(conversation = null) {
  const source = conversation || getCurrentConversation();
  if (source) {
    return {
      model: source.model,
      reasoning_effort: source.reasoning_effort || "",
      thinking_level: source.thinking_level || "",
    };
  }

  const selectedSettings = getSelectedModelSettings();
  return {
    model: modelSelectEl.value,
    reasoning_effort: selectedSettings.reasoning_effort,
    thinking_level: selectedSettings.thinking_level,
  };
}

function restoreConversationSelection(snapshot) {
  if (!snapshot) return;
  modelSelectEl.value = snapshot.model;
  syncModelSettingControl({
    modelId: snapshot.model,
    reasoningEffort: snapshot.reasoning_effort,
    thinkingLevel: snapshot.thinking_level,
  });
}

function showNoConversationHint() {
  clearMessages();
  if (state.searchKeyword) {
    addMessage("system", "没有匹配的会话，请修改关键词或新建会话。");
    return;
  }
  addMessage("system", "暂无会话，点击“新对话”开始。");
}

function updateActionButtons() {
  const busy =
    state.sending ||
    state.renaming ||
    state.deleting ||
    state.syncingConversationSettings;
  const hasConversation = Number.isInteger(state.currentConversationId);
  sendBtn.disabled = busy;
  newConvBtn.disabled = busy;
  renameConvBtn.disabled = busy || !hasConversation || state.editingConversationId !== null;
  exportConvBtn.disabled = busy || !hasConversation;
  for (const exportItemEl of exportMenuItemEls) {
    exportItemEl.disabled = busy || !hasConversation;
  }
  deleteConvBtn.disabled = busy || !hasConversation;
  if (confirmDeleteBtn) {
    confirmDeleteBtn.disabled = busy || !hasConversation;
  }
  if (cancelDeleteBtn) {
    cancelDeleteBtn.disabled = busy;
  }
  modelSelectEl.disabled = busy;
  if (modelSettingSelectEl) {
    modelSettingSelectEl.disabled = busy || Boolean(modelSettingFieldEl?.hidden);
  }
  fileInputEl.disabled = busy;
  setRetryButtonsDisabled(busy);

  if (busy || !hasConversation) {
    setExportMenuOpen(false);
    setDeleteConfirmOpen(false);
  }
}

function setExportMenuOpen(open, options = {}) {
  if (!exportMenuEl) return;

  const { focusFirstItem = false } = options;
  const shouldOpen = Boolean(open) && !exportConvBtn.disabled;
  state.exportMenuOpen = shouldOpen;
  exportMenuEl.parentElement?.classList.toggle("is-open", shouldOpen);
  exportMenuEl.setAttribute("aria-hidden", String(!shouldOpen));
  exportConvBtn.setAttribute("aria-expanded", String(shouldOpen));

  if (!shouldOpen) {
    return;
  }

  setDeleteConfirmOpen(false);
  if (focusFirstItem) {
    setTimeout(() => {
      exportMenuItemEls[0]?.focus();
    }, 0);
  }
}

function setDeleteConfirmOpen(open) {
  if (!deleteConfirmPanelEl) return;

  const shouldOpen = Boolean(open) && !deleteConvBtn.disabled;
  state.deleteConfirmOpen = shouldOpen;
  deleteConfirmPanelEl.parentElement?.classList.toggle("is-open", shouldOpen);
  deleteConfirmPanelEl.setAttribute("aria-hidden", String(!shouldOpen));
  deleteConvBtn.setAttribute("aria-expanded", String(shouldOpen));

  if (!shouldOpen) {
    return;
  }

  setExportMenuOpen(false);
  setTimeout(() => {
    confirmDeleteBtn?.focus();
  }, 0);
}

function clearInlineRenameState() {
  state.editingConversationId = null;
  state.editingTitleDraft = "";
}

function focusInlineEditInput() {
  setTimeout(() => {
    const input = conversationListEl.querySelector(".conversation-edit-input");
    if (input) {
      input.focus();
      input.select();
    }
  }, 0);
}

function renderConversations() {
  conversationListEl.innerHTML = "";
  if (!state.conversations.length) {
    const empty = document.createElement("div");
    empty.className = "conversation-empty";
    empty.textContent = "暂无会话";
    conversationListEl.appendChild(empty);
    updateActionButtons();
    return;
  }

  for (const conv of state.conversations) {
    if (conv.id === state.editingConversationId) {
      const row = document.createElement("div");
      row.className = "conversation-edit-row";

      const input = document.createElement("input");
      input.type = "text";
      input.className = "conversation-edit-input";
      input.maxLength = 60;
      input.value = state.editingTitleDraft || conv.title;
      input.addEventListener("input", () => {
        state.editingTitleDraft = input.value;
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void commitInlineRename();
        } else if (event.key === "Escape") {
          event.preventDefault();
          clearInlineRenameState();
          renderConversations();
        }
      });

      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "conversation-edit-save";
      saveBtn.textContent = "保存";
      saveBtn.addEventListener("click", () => {
        void commitInlineRename();
      });

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "conversation-edit-cancel";
      cancelBtn.textContent = "取消";
      cancelBtn.addEventListener("click", () => {
        clearInlineRenameState();
        renderConversations();
      });

      row.appendChild(input);
      row.appendChild(saveBtn);
      row.appendChild(cancelBtn);
      conversationListEl.appendChild(row);
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item";
    if (conv.id === state.currentConversationId) {
      button.classList.add("active");
    }
    button.title = conv.title;
    button.textContent = conv.title;
    button.addEventListener("click", () => {
      void selectConversation(conv.id);
    });
    conversationListEl.appendChild(button);
  }
  updateActionButtons();
  if (state.editingConversationId !== null) {
    focusInlineEditInput();
  }
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadConversations() {
  const params = new URLSearchParams();
  if (state.searchKeyword) {
    params.set("q", state.searchKeyword);
  }
  const url = params.toString()
    ? `/api/conversations?${params.toString()}`
    : "/api/conversations";
  const data = await fetchJson(url);

  state.conversations = data.conversations || [];
  if (state.currentConversationId == null && state.conversations.length) {
    state.currentConversationId = state.conversations[0].id;
  }
  if (
    state.currentConversationId != null &&
    !state.conversations.find((item) => item.id === state.currentConversationId)
  ) {
    state.currentConversationId = state.conversations.length
      ? state.conversations[0].id
      : null;
  }
  if (
    state.editingConversationId != null &&
    !state.conversations.find((item) => item.id === state.editingConversationId)
  ) {
    clearInlineRenameState();
  }

  const current = state.conversations.find(
    (item) => item.id === state.currentConversationId
  );
  if (current) {
    applyConversationSelection(current);
  } else {
    syncModelSettingControl({
      modelId: modelSelectEl.value,
      preserveCurrentValue: true,
    });
  }
  renderConversations();
}

async function syncCurrentConversationSettings(payload) {
  if (!Number.isInteger(state.currentConversationId)) return;

  state.syncingConversationSettings = true;
  updateActionButtons();
  try {
    await fetchJson(`/api/conversations/${state.currentConversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadConversations();
  } finally {
    state.syncingConversationSettings = false;
    updateActionButtons();
  }
}

async function createConversation() {
  clearInlineRenameState();
  clearPendingFiles();
  if (state.searchKeyword) {
    state.searchKeyword = "";
    searchInputEl.value = "";
  }
  const model = modelSelectEl.value;
  const modelSettings = getSelectedModelSettings();
  const data = await fetchJson("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      reasoning_effort: modelSettings.reasoning_effort,
      thinking_level: modelSettings.thinking_level,
    }),
  });
  state.currentConversationId = data.conversation.id;
  await loadConversations();
  await loadMessages(state.currentConversationId);
}

async function fetchConversationMessages(conversationId) {
  return fetchJson(`/api/conversations/${conversationId}/messages`);
}

function renderConversationMessagesData(conversationId, data) {
  clearMessages();
  if (!data.messages.length) {
    addMessage("system", "开始新的对话吧。");
  } else {
    let retryAssistantEl = null;
    for (const msg of data.messages) {
      const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
      const displayContent = attachments.length
        ? stripAttachmentMarkerLines(msg.content || "")
        : msg.content || "";
      const messageEl = addMessage(msg.role, displayContent, {
        attachments,
        reasoning: msg.reasoning || "",
        status: msg.status || "complete",
      });
      if (msg.role === "assistant" && msg.status === "incomplete") {
        retryAssistantEl = messageEl;
      }
    }

    const retryState = analyzeRetryState(data.messages);
    if (retryState.kind === "retry") {
      addRetryPrompt({
        conversationId,
        message: retryState.hasIncompleteAssistant
          ? "上一条回复未完成，可点击重试。"
          : "上一条消息尚未收到回复，可点击重试。",
        assistantEl: retryAssistantEl,
      });
    }
  }
  const current = getCurrentConversation();
  if (current) {
    current.model = data.model;
    current.reasoning_effort = data.reasoning_effort || "";
    current.thinking_level = data.thinking_level || "";
  }
  applyConversationSelection({
    model: data.model,
    reasoning_effort: data.reasoning_effort || "",
    thinking_level: data.thinking_level || "",
  });
}

async function loadMessages(conversationId, preloadedData = null) {
  const data = preloadedData || (await fetchConversationMessages(conversationId));
  renderConversationMessagesData(conversationId, data);
  return data;
}

async function selectConversation(conversationId) {
  if (state.sending) return;
  clearPendingFiles();
  state.currentConversationId = conversationId;
  renderConversations();
  await loadMessages(conversationId);
}

function parseSseEvents(textChunk, onEvent) {
  // Some gateways/proxies use CRLF (\r\n) for SSE boundaries.
  // Normalize line endings so events can be parsed incrementally.
  const normalized = textChunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const blocks = normalized.split("\n\n");
  const remainder = blocks.pop();

  for (const block of blocks) {
    const dataLines = [];
    const lines = block.split("\n");
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      dataLines.push(raw);
    }
    if (!dataLines.length) continue;

    const rawEvent = dataLines.join("\n");
    if (rawEvent === "[DONE]") continue;
    try {
      onEvent(JSON.parse(rawEvent));
    } catch {
      // Ignore malformed SSE lines.
    }
  }
  return remainder || "";
}

function scheduleUiFrame(callback) {
  if (typeof window.requestAnimationFrame === "function") {
    return window.requestAnimationFrame(callback);
  }
  return window.setTimeout(callback, 16);
}

function cancelUiFrame(handle) {
  if (handle == null) return;
  if (typeof window.cancelAnimationFrame === "function") {
    window.cancelAnimationFrame(handle);
    return;
  }
  window.clearTimeout(handle);
}

function buildStreamError(message, partialReply = "") {
  const error = new Error(message);
  if (partialReply) {
    error.keepPartial = true;
    error.partialReply = partialReply;
  }
  return error;
}

function getErrorMessage(err) {
  if (err instanceof Error && err.message) return err.message;
  return String(err);
}

function addRetryPrompt({ conversationId, message, assistantEl = null }) {
  clearRetryPrompts();
  if (assistantEl instanceof HTMLElement && assistantEl.isConnected) {
    assistantEl.classList.add("is-incomplete");
  }
  const retryMessageEl = addMessage("system", message, {
    actions: [
      {
        label: "重试",
        className: "message-action-btn message-retry-btn",
        onClick: () => {
          void retryFailedReply({
            conversationId,
            assistantEl,
            retryMessageEl,
          });
        },
      },
    ],
  });
  retryMessageEl.classList.add("is-retry-prompt");
  return retryMessageEl;
}

function buildChatRequestFormData({
  conversationId,
  model,
  reasoningEffort,
  thinkingLevel,
  content,
  files,
}) {
  const formData = new FormData();
  formData.append("conversation_id", String(conversationId));
  formData.append("model", model);
  formData.append("reasoning_effort", reasoningEffort || "");
  formData.append("thinking_level", thinkingLevel || "");
  formData.append("content", content);
  for (const file of files) {
    formData.append("files", file);
  }
  return formData;
}

function buildRetryRequestFormData(conversationId) {
  const formData = new FormData();
  formData.append("conversation_id", String(conversationId));
  return formData;
}

async function streamReply({
  url = "/api/chat/stream",
  body,
  assistantEl,
}) {
  const controller = new AbortController();
  const assistantContentEl = assistantEl.querySelector(".message-content");
  const reasoningPanel = ensureReasoningPanel(assistantEl);
  const reasoningPanelEl = reasoningPanel.panelEl;
  const reasoningContentEl = reasoningPanel.contentEl;
  let idleTimer = null;
  let buffer = "";
  let streamError = "";
  let finalReply = "";
  let finalReasoning = "";
  let pendingStreamText = "";
  let pendingReasoningText = "";
  let streamRenderHandle = null;
  let reasoningRenderHandle = null;
  let streamTextNode = null;
  let reasoningTextNode = null;
  let sawDoneEvent = false;
  let shouldStopReading = false;
  let streamAbortReason = "";

  const clearIdleTimer = () => {
    if (idleTimer != null) {
      window.clearTimeout(idleTimer);
      idleTimer = null;
    }
  };

  const resetIdleTimer = () => {
    clearIdleTimer();
    idleTimer = window.setTimeout(() => {
      streamAbortReason = finalReply
        ? `流式响应超过 ${STREAM_IDLE_TIMEOUT_SECONDS} 秒未返回新内容，已保留当前内容，请重试继续。`
        : `流式响应超过 ${STREAM_IDLE_TIMEOUT_SECONDS} 秒未返回新内容，请重试。`;
      controller.abort();
    }, STREAM_IDLE_TIMEOUT_MS);
  };

  const buildDisconnectedMessage = () =>
    finalReply
      ? "流式连接已中断，已保留当前内容，请重试继续。"
      : "流式连接已中断，请重试。";

  const buildUnexpectedEndMessage = () =>
    finalReply
      ? "流式响应异常结束，已保留当前内容，请重试继续。"
      : "流式响应异常结束，请重试。";

  const flushStreamText = () => {
    streamRenderHandle = null;
    if (!streamTextNode || !pendingStreamText) return;
    streamTextNode.appendData(pendingStreamText);
    pendingStreamText = "";
  };

  const flushReasoningText = () => {
    reasoningRenderHandle = null;
    if (!reasoningTextNode || !pendingReasoningText) return;
    reasoningTextNode.appendData(pendingReasoningText);
    pendingReasoningText = "";
  };

  const scheduleStreamTextFlush = () => {
    if (!assistantContentEl || !streamTextNode || !pendingStreamText) return;
    if (streamRenderHandle != null) return;
    streamRenderHandle = scheduleUiFrame(flushStreamText);
  };

  const revealReasoningPanel = () => {
    if (!reasoningPanelEl || !reasoningContentEl) return;
    reasoningPanelEl.hidden = false;
    reasoningPanelEl.classList.add("is-streaming");
    reasoningContentEl.classList.add("is-streaming");
    if (reasoningTextNode) return;
    reasoningContentEl.textContent = "";
    reasoningTextNode = document.createTextNode("");
    reasoningContentEl.appendChild(reasoningTextNode);
  };

  const scheduleReasoningTextFlush = () => {
    if (!reasoningContentEl || !reasoningTextNode || !pendingReasoningText) return;
    if (reasoningRenderHandle != null) return;
    reasoningRenderHandle = scheduleUiFrame(flushReasoningText);
  };

  const finalizeReasoningRender = () => {
    if (!reasoningPanelEl || !reasoningContentEl) return;
    cancelUiFrame(reasoningRenderHandle);
    reasoningRenderHandle = null;
    flushReasoningText();
    reasoningPanelEl.classList.remove("is-streaming");
    reasoningContentEl.classList.remove("is-streaming");
    if (!finalReasoning) {
      reasoningPanelEl.hidden = true;
      reasoningContentEl.textContent = "";
      reasoningTextNode = null;
      return;
    }
    reasoningPanelEl.hidden = false;
    reasoningContentEl.innerHTML = renderMarkdown(finalReasoning);
  };

  const finalizeStreamRender = () => {
    if (!assistantContentEl) return;
    cancelUiFrame(streamRenderHandle);
    streamRenderHandle = null;
    flushStreamText();
    finalizeReasoningRender();
    assistantContentEl.classList.remove("is-streaming");
    assistantContentEl.innerHTML = renderMarkdown(finalReply);
  };

  if (assistantContentEl) {
    assistantContentEl.classList.add("is-streaming");
    assistantContentEl.textContent = "";
    streamTextNode = document.createTextNode("");
    assistantContentEl.appendChild(streamTextNode);
  }

  resetIdleTimer();

  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      body,
      signal: controller.signal,
    });
  } catch (err) {
    clearIdleTimer();
    if (controller.signal.aborted && streamAbortReason) {
      throw buildStreamError(streamAbortReason, finalReply);
    }
    throw err;
  }

  if (!resp.ok) {
    clearIdleTimer();
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || "请求失败");
  }
  if (!resp.body) {
    clearIdleTimer();
    throw new Error("浏览器不支持流式响应");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      resetIdleTimer();
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseEvents(buffer, (event) => {
        if (event.type === "reasoning" && typeof event.text === "string") {
          finalReasoning += event.text;
          pendingReasoningText += event.text;
          revealReasoningPanel();
          scheduleReasoningTextFlush();
        } else if (event.type === "delta" && typeof event.text === "string") {
          finalReply += event.text;
          pendingStreamText += event.text;
          scheduleStreamTextFlush();
        } else if (event.type === "error" && typeof event.error === "string") {
          streamError = event.error;
        } else if (event.type === "done") {
          sawDoneEvent = true;
          shouldStopReading = true;
          clearIdleTimer();
          if (typeof event.reply === "string") {
            finalReply = event.reply;
          }
        }
      });
      if (shouldStopReading) {
        await reader.cancel().catch(() => {});
        break;
      }
    }
  } catch (err) {
    if (controller.signal.aborted && streamAbortReason) {
      streamError = streamAbortReason;
    } else if (!streamError) {
      streamError = buildDisconnectedMessage();
    }
  } finally {
    clearIdleTimer();
  }

  if (buffer) {
    parseSseEvents(buffer + "\n\n", (event) => {
      if (event.type === "reasoning" && typeof event.text === "string") {
        finalReasoning += event.text;
        pendingReasoningText += event.text;
      } else if (event.type === "delta" && typeof event.text === "string") {
        finalReply += event.text;
        pendingStreamText += event.text;
      } else if (event.type === "error" && typeof event.error === "string") {
        streamError = event.error;
      } else if (event.type === "done") {
        sawDoneEvent = true;
        clearIdleTimer();
        if (typeof event.reply === "string") {
          finalReply = event.reply;
        }
      }
    });
  }

  finalizeStreamRender();

  if (!sawDoneEvent && !streamError) {
    streamError = buildUnexpectedEndMessage();
  }
  if (streamError) {
    throw buildStreamError(streamError, finalReply);
  }
  return finalReply;
}

async function retryFailedReply({ conversationId, assistantEl, retryMessageEl }) {
  if (state.sending) return;

  retryMessageEl?.remove();

  state.sending = true;
  updateActionButtons();

  let streamSucceeded = false;
  let targetAssistantEl =
    assistantEl instanceof HTMLElement && assistantEl.isConnected ? assistantEl : null;

  try {
    const latestData = await fetchConversationMessages(conversationId);
    const retryState = analyzeRetryState(latestData.messages);

    if (retryState.kind === "complete") {
      await loadMessages(conversationId, latestData);
      streamSucceeded = true;
    } else if (retryState.kind !== "retry") {
      throw new Error("当前没有可重试的失败回复。");
    } else {
      if (targetAssistantEl) {
        resetAssistantMessageForRetry(targetAssistantEl);
      } else {
        targetAssistantEl = addMessage("assistant", "", { autoScroll: false });
      }

      await streamReply({
        url: "/api/chat/retry/stream",
        body: buildRetryRequestFormData(conversationId),
        assistantEl: targetAssistantEl,
      });
      streamSucceeded = true;
    }
  } catch (err) {
    if (!err || err.keepPartial !== true) {
      targetAssistantEl?.remove();
      targetAssistantEl = null;
    }
    addRetryPrompt({
      conversationId,
      message: `请求失败：${getErrorMessage(err)}`,
      assistantEl: targetAssistantEl,
    });
  } finally {
    state.sending = false;
    updateActionButtons();
    promptEl.focus();
  }

  if (!streamSucceeded) {
    return;
  }

  clearRetryPrompts();
  try {
    await loadConversations();
  } catch (err) {
    addMessage("system", `刷新会话列表失败：${getErrorMessage(err)}`);
  }
}

function getFilenameFromDisposition(headerValue) {
  if (!headerValue) return "";

  const encodedMatch = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(headerValue);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      // Fallback to plain filename.
    }
  }

  const plainMatch = /filename\s*=\s*"?([^";]+)"?/i.exec(headerValue);
  return plainMatch ? plainMatch[1] : "";
}

function getExportFileExtension(format) {
  if (format === "txt") return "txt";
  if (format === "md") return "md";
  return "json";
}

async function exportCurrentConversation(format = "json") {
  if (!Number.isInteger(state.currentConversationId)) return;
  const normalizedFormat = SUPPORTED_EXPORT_FORMATS.has(format) ? format : "json";
  const resp = await fetch(
    `/api/conversations/${state.currentConversationId}/export?format=${encodeURIComponent(normalizedFormat)}`
  );
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || "导出失败");
  }
  const blob = await resp.blob();
  const filename =
    getFilenameFromDisposition(resp.headers.get("Content-Disposition")) ||
    `conversation.${getExportFileExtension(normalizedFormat)}`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function renameCurrentConversation() {
  if (!Number.isInteger(state.currentConversationId)) return;
  const current = state.conversations.find(
    (item) => item.id === state.currentConversationId
  );
  if (!current) return;
  state.editingConversationId = current.id;
  state.editingTitleDraft = current.title;
  renderConversations();
}

async function commitInlineRename() {
  if (!Number.isInteger(state.editingConversationId)) return;
  if (state.renaming || state.sending) return;

  const title = state.editingTitleDraft.trim();
  if (!title) {
    throw new Error("会话名称不能为空");
  }

  const conversationId = state.editingConversationId;
  state.renaming = true;
  updateActionButtons();

  try {
    await fetchJson(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });

    clearInlineRenameState();
    await loadConversations();
    if (state.currentConversationId == null) {
      showNoConversationHint();
    }
  } finally {
    state.renaming = false;
    updateActionButtons();
  }
}

async function deleteCurrentConversation() {
  if (!Number.isInteger(state.currentConversationId)) return;
  setDeleteConfirmOpen(false);

  state.deleting = true;
  updateActionButtons();
  try {
    await fetchJson(`/api/conversations/${state.currentConversationId}`, {
      method: "DELETE",
    });
    clearInlineRenameState();
    clearPendingFiles();

    await loadConversations();
    if (state.currentConversationId == null) {
      showNoConversationHint();
      return;
    }
    await loadMessages(state.currentConversationId);
  } finally {
    state.deleting = false;
    updateActionButtons();
  }
}

async function refreshConversationsAndMessages() {
  await loadConversations();
  if (state.currentConversationId == null) {
    showNoConversationHint();
    return;
  }
  await loadMessages(state.currentConversationId);
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.sending) return;

  const content = promptEl.value.trim();
  const pendingFiles = state.pendingFiles.slice();
  const files = pendingFiles.map((item) => item.file);
  if (!content && !files.length) return;
  if (state.currentConversationId == null) {
    await createConversation();
  }
  clearRetryPrompts();

  const model = modelSelectEl.value;
  const modelSettings = getSelectedModelSettings();
  const conversationId = state.currentConversationId;
  const localAttachments = buildLocalMessageAttachments(pendingFiles);
  addMessage("user", content, { attachments: localAttachments });
  const assistantEl = addMessage("assistant", "", { autoScroll: false });
  promptEl.value = "";
  clearPendingFiles();

  state.sending = true;
  updateActionButtons();

  let streamSucceeded = false;
  try {
    await streamReply({
      body: buildChatRequestFormData({
        conversationId,
        model,
        reasoningEffort: modelSettings.reasoning_effort,
        thinkingLevel: modelSettings.thinking_level,
        content,
        files,
      }),
      assistantEl,
    });
    streamSucceeded = true;
  } catch (err) {
    if (!err || err.keepPartial !== true) {
      assistantEl.remove();
    }
    addRetryPrompt({
      conversationId,
      message: `请求失败：${getErrorMessage(err)}`,
      assistantEl: err?.keepPartial === true ? assistantEl : null,
    });
  } finally {
    state.sending = false;
    updateActionButtons();
    promptEl.focus();
  }

  if (!streamSucceeded) {
    return;
  }

  try {
    await loadConversations();
  } catch (err) {
    addMessage("system", `刷新会话列表失败：${getErrorMessage(err)}`);
  }
});

modelSelectEl.addEventListener("change", async () => {
  const previousSelection = getConversationSelectionSnapshot();
  const nextSettings = syncModelSettingControl({ modelId: modelSelectEl.value });
  updateActionButtons();

  if (!Number.isInteger(state.currentConversationId) || state.sending) {
    return;
  }

  try {
    await syncCurrentConversationSettings({
      model: modelSelectEl.value,
      reasoning_effort: nextSettings.reasoning_effort,
      thinking_level: nextSettings.thinking_level,
    });
  } catch (err) {
    restoreConversationSelection(previousSelection);
    addMessage("system", `切换模型失败：${getErrorMessage(err)}`);
  }
});

modelSettingSelectEl?.addEventListener("change", async () => {
  const previousSelection = getConversationSelectionSnapshot();
  const nextSettings = getSelectedModelSettings();
  updateActionButtons();

  if (!Number.isInteger(state.currentConversationId) || state.sending) {
    return;
  }

  try {
    await syncCurrentConversationSettings({
      model: modelSelectEl.value,
      reasoning_effort: nextSettings.reasoning_effort,
      thinking_level: nextSettings.thinking_level,
    });
  } catch (err) {
    restoreConversationSelection(previousSelection);
    addMessage("system", `切换思考参数失败：${getErrorMessage(err)}`);
  }
});

newConvBtn.addEventListener("click", async () => {
  if (state.sending) return;
  try {
    await createConversation();
  } catch (err) {
    addMessage("system", `创建会话失败：${err}`);
  }
});

renameConvBtn.addEventListener("click", async () => {
  if (state.sending) return;
  try {
    await renameCurrentConversation();
  } catch (err) {
    addMessage("system", `重命名失败：${err}`);
  }
});

exportConvBtn.addEventListener("click", async () => {
  if (state.sending) return;
  if (!Number.isInteger(state.currentConversationId)) return;
  setExportMenuOpen(!state.exportMenuOpen, { focusFirstItem: true });
});

deleteConvBtn.addEventListener("click", async () => {
  if (state.sending) return;
  if (!Number.isInteger(state.currentConversationId)) return;
  setDeleteConfirmOpen(!state.deleteConfirmOpen);
});

for (const exportMenuItemEl of exportMenuItemEls) {
  exportMenuItemEl.addEventListener("click", async () => {
    if (state.sending) return;
    const format = exportMenuItemEl.dataset.exportFormat || "json";
    setExportMenuOpen(false);
    try {
      await exportCurrentConversation(format);
    } catch (err) {
      addMessage("system", `导出失败：${err}`);
    }
  });
}

confirmDeleteBtn?.addEventListener("click", async () => {
  if (state.sending) return;
  try {
    await deleteCurrentConversation();
  } catch (err) {
    addMessage("system", `删除失败：${err}`);
  }
});

cancelDeleteBtn?.addEventListener("click", () => {
  setDeleteConfirmOpen(false);
  deleteConvBtn.focus();
});

fileInputEl.addEventListener("change", () => {
  const incoming = Array.from(fileInputEl.files || []);
  if (!incoming.length) return;
  appendPendingFiles(incoming, "picker");
});

promptEl.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.isComposing || event.keyCode === 229) return;

  event.preventDefault();
  if (state.sending) return;
  if (typeof chatForm.requestSubmit === "function") {
    chatForm.requestSubmit();
    return;
  }
  sendBtn.click();
});

promptEl.addEventListener("paste", (event) => {
  const clipboardData = event.clipboardData;
  if (!clipboardData) return;

  const pastedFiles = collectClipboardFiles(clipboardData);
  if (!pastedFiles.length) {
    if (clipboardLooksLikeFilePaste(clipboardData)) {
      event.preventDefault();
      addMessage("system", "未能读取剪贴板中的文件内容，请改用“添加文件”上传。");
    }
    return;
  }

  event.preventDefault();
  appendPendingFiles(pastedFiles, "paste");
});

searchInputEl.addEventListener("input", () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
  }
  searchDebounceTimer = setTimeout(async () => {
    if (state.sending) return;
    clearInlineRenameState();
    clearPendingFiles();
    state.searchKeyword = searchInputEl.value.trim();
    try {
      await refreshConversationsAndMessages();
    } catch (err) {
      addMessage("system", `搜索失败：${err}`);
    }
  }, 250);
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Node)) return;

  const exportMenuRoot = exportMenuEl?.parentElement;
  if (state.exportMenuOpen && exportMenuRoot && !exportMenuRoot.contains(target)) {
    setExportMenuOpen(false);
  }

  const deleteConfirmRoot = deleteConfirmPanelEl?.parentElement;
  if (state.deleteConfirmOpen && deleteConfirmRoot && !deleteConfirmRoot.contains(target)) {
    setDeleteConfirmOpen(false);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;

  if (state.exportMenuOpen) {
    event.preventDefault();
    setExportMenuOpen(false);
    exportConvBtn.focus();
    return;
  }

  if (state.deleteConfirmOpen) {
    event.preventDefault();
    setDeleteConfirmOpen(false);
    deleteConvBtn.focus();
  }
});

if (adminBtn) {
  adminBtn.addEventListener("click", () => {
    window.location.href = "/admin";
  });
}

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

window.addEventListener("beforeunload", () => {
  revokeAllTemporaryMessageObjectUrls();
  for (const item of state.pendingFiles) {
    revokePendingFilePreview(item);
  }
});

(async function init() {
  if (ALLOWED_ATTACHMENT_EXTS.length) {
    fileInputEl.setAttribute("accept", ALLOWED_ATTACHMENT_EXTS.join(","));
  }
  syncModelSettingControl({ modelId: modelSelectEl.value });
  updateActionButtons();
  renderSelectedFiles();
  try {
    await loadConversations();
    if (!state.conversations.length) {
      await createConversation();
    } else {
      await loadMessages(state.currentConversationId);
    }
  } catch (err) {
    clearMessages();
    addMessage("system", `初始化失败：${err}`);
  }
})();
