const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const promptEl = document.getElementById("prompt");
const modelSelectEl = document.getElementById("model-select");
const logoutBtn = document.getElementById("logout-btn");
const sendBtn = document.getElementById("send-btn");
const newConvBtn = document.getElementById("new-conv-btn");
const renameConvBtn = document.getElementById("rename-conv-btn");
const exportConvBtn = document.getElementById("export-conv-btn");
const deleteConvBtn = document.getElementById("delete-conv-btn");
const searchInputEl = document.getElementById("search-input");
const conversationListEl = document.getElementById("conversation-list");
const fileInputEl = document.getElementById("file-input");
const selectedFilesEl = document.getElementById("selected-files");

const state = {
  conversations: [],
  currentConversationId: null,
  sending: false,
  renaming: false,
  searchKeyword: "",
  editingConversationId: null,
  editingTitleDraft: "",
  pendingFiles: [],
};

let searchDebounceTimer = null;
const MAX_FILES_PER_MESSAGE =
  Number.parseInt(window.__APP_CONFIG__?.maxAttachmentsPerMessage, 10) || 5;
const MAX_UPLOAD_MB = Number.parseInt(window.__APP_CONFIG__?.maxUploadMB, 10) || 15;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
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

function addMessage(role, content, options = {}) {
  const { autoScroll = true } = options;
  const div = document.createElement("div");
  div.className = `message ${role}`;
  const contentEl = document.createElement("div");
  contentEl.className = "message-content";
  contentEl.innerHTML = renderMarkdown(content);
  div.appendChild(contentEl);
  messagesEl.appendChild(div);
  if (autoScroll) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  return div;
}

function clearMessages() {
  messagesEl.innerHTML = "";
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function clearPendingFiles() {
  state.pendingFiles = [];
  fileInputEl.value = "";
  renderSelectedFiles();
}

function renderSelectedFiles() {
  selectedFilesEl.innerHTML = "";
  if (!state.pendingFiles.length) {
    const hint = document.createElement("span");
    hint.className = "selected-files-hint";
    hint.textContent = "未选择附件";
    selectedFilesEl.appendChild(hint);
    return;
  }

  for (const [index, file] of state.pendingFiles.entries()) {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.textContent = `${file.name} (${formatFileSize(file.size)})`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "file-chip-remove";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      state.pendingFiles.splice(index, 1);
      renderSelectedFiles();
    });

    chip.appendChild(removeBtn);
    selectedFilesEl.appendChild(chip);
  }
}

function buildUserMessagePreview(content, files) {
  const text = content.trim();
  const fileLines = files.map((file) => `[附件] ${file.name}`);
  return [text, ...fileLines].filter(Boolean).join("\n");
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

function showNoConversationHint() {
  clearMessages();
  if (state.searchKeyword) {
    addMessage("system", "没有匹配的会话，请修改关键词或新建会话。");
    return;
  }
  addMessage("system", "暂无会话，点击“新对话”开始。");
}

function updateActionButtons() {
  const busy = state.sending || state.renaming;
  const hasConversation = Number.isInteger(state.currentConversationId);
  sendBtn.disabled = busy;
  newConvBtn.disabled = busy;
  renameConvBtn.disabled = busy || !hasConversation || state.editingConversationId !== null;
  exportConvBtn.disabled = busy || !hasConversation;
  deleteConvBtn.disabled = busy || !hasConversation;
  modelSelectEl.disabled = busy;
  fileInputEl.disabled = busy;
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
    modelSelectEl.value = current.model;
  }
  renderConversations();
}

async function createConversation() {
  clearInlineRenameState();
  clearPendingFiles();
  if (state.searchKeyword) {
    state.searchKeyword = "";
    searchInputEl.value = "";
  }
  const model = modelSelectEl.value;
  const data = await fetchJson("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  state.currentConversationId = data.conversation.id;
  await loadConversations();
  await loadMessages(state.currentConversationId);
}

async function loadMessages(conversationId) {
  const data = await fetchJson(`/api/conversations/${conversationId}/messages`);
  clearMessages();
  if (!data.messages.length) {
    addMessage("system", "开始新的对话吧。");
  } else {
    for (const msg of data.messages) {
      let displayContent = msg.content || "";
      if (Array.isArray(msg.attachments) && msg.attachments.length) {
        const existing = new Set(
          displayContent
            .split("\n")
            .map((line) => line.trim())
            .filter((line) => line.startsWith("[附件] "))
        );
        const lines = msg.attachments
          .map((att) => `[附件] ${att.file_name}`)
          .filter((line) => !existing.has(line));
        displayContent = [displayContent, ...lines].filter(Boolean).join("\n");
      }
      addMessage(msg.role, displayContent);
    }
  }
  modelSelectEl.value = data.model;
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

async function streamReply({ conversationId, model, content, files, assistantEl }) {
  const formData = new FormData();
  formData.append("conversation_id", String(conversationId));
  formData.append("model", model);
  formData.append("content", content);
  for (const file of files) {
    formData.append("files", file);
  }

  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || "请求失败");
  }
  if (!resp.body) {
    throw new Error("浏览器不支持流式响应");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const assistantContentEl = assistantEl.querySelector(".message-content");
  let buffer = "";
  let streamError = "";
  let finalReply = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = parseSseEvents(buffer, (event) => {
      if (event.type === "delta" && typeof event.text === "string") {
        finalReply += event.text;
        if (assistantContentEl) {
          assistantContentEl.innerHTML = renderMarkdown(finalReply);
        }
      } else if (event.type === "error" && typeof event.error === "string") {
        streamError = event.error;
      }
    });
  }

  if (buffer) {
    parseSseEvents(buffer + "\n\n", (event) => {
      if (event.type === "delta" && typeof event.text === "string") {
        finalReply += event.text;
      } else if (event.type === "error" && typeof event.error === "string") {
        streamError = event.error;
      }
    });
    if (assistantContentEl) {
      assistantContentEl.innerHTML = renderMarkdown(finalReply);
    }
  }

  if (streamError) {
    throw new Error(streamError);
  }
  return finalReply;
}

function getFilenameFromDisposition(headerValue) {
  if (!headerValue) return "";
  const match = /filename="?([^"]+)"?/i.exec(headerValue);
  return match ? match[1] : "";
}

async function exportCurrentConversation() {
  if (!Number.isInteger(state.currentConversationId)) return;
  const resp = await fetch(
    `/api/conversations/${state.currentConversationId}/export?format=json`
  );
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || "导出失败");
  }
  const blob = await resp.blob();
  const filename =
    getFilenameFromDisposition(resp.headers.get("Content-Disposition")) ||
    "conversation.json";
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
  const confirmed = window.confirm("确认删除当前会话吗？删除后不可恢复。");
  if (!confirmed) return;

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
  const files = state.pendingFiles.slice();
  if (!content && !files.length) return;
  if (state.currentConversationId == null) {
    await createConversation();
  }

  const model = modelSelectEl.value;
  const conversationId = state.currentConversationId;
  addMessage("user", buildUserMessagePreview(content, files));
  const assistantEl = addMessage("assistant", "", { autoScroll: false });
  promptEl.value = "";
  clearPendingFiles();

  state.sending = true;
  updateActionButtons();

  try {
    await streamReply({ conversationId, model, content, files, assistantEl });
    await loadConversations();
    renderConversations();
  } catch (err) {
    assistantEl.remove();
    addMessage("system", `请求失败：${err}`);
  } finally {
    state.sending = false;
    updateActionButtons();
    promptEl.focus();
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
  try {
    await exportCurrentConversation();
  } catch (err) {
    addMessage("system", `导出失败：${err}`);
  }
});

deleteConvBtn.addEventListener("click", async () => {
  if (state.sending) return;
  try {
    await deleteCurrentConversation();
  } catch (err) {
    addMessage("system", `删除失败：${err}`);
  }
});

fileInputEl.addEventListener("change", () => {
  const incoming = Array.from(fileInputEl.files || []);
  if (!incoming.length) return;

  const merged = [...state.pendingFiles];
  for (const file of incoming) {
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
    merged.push(file);
  }
  state.pendingFiles = merged;
  fileInputEl.value = "";
  renderSelectedFiles();
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

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

(async function init() {
  if (ALLOWED_ATTACHMENT_EXTS.length) {
    fileInputEl.setAttribute("accept", ALLOWED_ATTACHMENT_EXTS.join(","));
  }
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
