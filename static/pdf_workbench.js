const chatBtn = document.getElementById("chat-btn");
const adminBtn = document.getElementById("admin-btn");
const logoutBtn = document.getElementById("logout-btn");
const uploadForm = document.getElementById("pdf-upload-form");
const uploadBtn = document.getElementById("pdf-upload-btn");
const fileInputEl = document.getElementById("pdf-file-input");
const uploadResultEl = document.getElementById("pdf-upload-result");
const uploadProgressEl = document.getElementById("pdf-upload-progress");
const uploadProgressBarEl = document.getElementById("pdf-upload-progress-bar");
const uploadProgressLabelEl = document.getElementById("pdf-upload-progress-label");
const uploadProgressValueEl = document.getElementById("pdf-upload-progress-value");
const docListEl = document.getElementById("pdf-doc-list");
const docTitleEl = document.getElementById("pdf-doc-title");
const docStatusEl = document.getElementById("pdf-doc-status");
const docMetaEl = document.getElementById("pdf-doc-meta");
const docMessageEl = document.getElementById("pdf-doc-message");
const sectionsTabEl = document.getElementById("pdf-tab-sections");
const pagesTabEl = document.getElementById("pdf-tab-pages");
const navEmptyEl = document.getElementById("pdf-nav-empty");
const sectionTreeEl = document.getElementById("pdf-section-tree");
const pageGridEl = document.getElementById("pdf-page-grid");
const rangeStartEl = document.getElementById("pdf-range-start");
const rangeEndEl = document.getElementById("pdf-range-end");
const sectionSelectEl = document.getElementById("pdf-section-select");
const buildPageExcerptBtn = document.getElementById("build-page-excerpt-btn");
const buildSectionExcerptBtn = document.getElementById("build-section-excerpt-btn");
const previewMetaEl = document.getElementById("pdf-preview-meta");
const previewEmptyEl = document.getElementById("pdf-preview-empty");
const previewEl = document.getElementById("pdf-preview");
const sendChatBtn = document.getElementById("send-chat-btn");
const openChatBtn = document.getElementById("open-chat-btn");

const PDF_CHAT_DRAFT_STORAGE_KEY = "pdfWorkbenchPendingChatDraftV1";

const state = {
  documents: [],
  currentDocumentId: null,
  currentDocument: null,
  currentExcerpt: null,
  viewMode: "sections",
  uploading: false,
  pollTimer: null,
  uploadProgress: 0,
  uploadProgressPhase: "idle",
  uploadProgressLabel: "准备上传…",
  progressDocumentId: null,
  progressHideTimer: null,
};

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return String(error || "请求失败");
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok || !data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function uploadPdfFile(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.open("POST", "/api/pdf-documents");
    xhr.responseType = "json";

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }
      const ratio = event.total > 0 ? event.loaded / event.total : 0;
      const progress = Math.min(100, Math.max(1, ratio * 100));
      setUploadProgress(progress, "uploading", "正在上传 PDF…");
    });

    xhr.addEventListener("load", () => {
      const data = xhr.response && typeof xhr.response === "object" ? xhr.response : {};
      if (xhr.status >= 200 && xhr.status < 300 && data.ok) {
        resolve(data);
        return;
      }
      reject(new Error(data.error || "上传失败"));
    });

    xhr.addEventListener("error", () => reject(new Error("上传失败，网络连接异常")));
    xhr.addEventListener("abort", () => reject(new Error("上传已取消")));
    xhr.send(formData);
  });
}

function escapeHtml(raw) {
  return String(raw ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatNumber(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return "0";
  return parsed.toLocaleString("zh-CN");
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${Math.round(value)} B`;
}

function clearPollTimer() {
  if (state.pollTimer != null) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function clearProgressHideTimer() {
  if (state.progressHideTimer != null) {
    window.clearTimeout(state.progressHideTimer);
    state.progressHideTimer = null;
  }
}

function renderUploadProgress() {
  const visible = state.uploading || state.uploadProgressPhase !== "idle";
  uploadProgressEl.hidden = !visible;
  uploadProgressEl.classList.toggle("is-warning", state.uploadProgressPhase === "error");
  uploadProgressBarEl.style.width = `${Math.max(0, Math.min(100, state.uploadProgress))}%`;
  uploadProgressValueEl.textContent = `${Math.round(state.uploadProgress)}%`;
  uploadProgressLabelEl.textContent = state.uploadProgressLabel || "准备上传…";
}

function setUploadProgress(progress, phase, label = "") {
  if (typeof phase === "string") {
    state.uploadProgressPhase = phase;
  }
  if (Number.isFinite(progress)) {
    state.uploadProgress = Math.max(0, Math.min(100, progress));
  }
  if (typeof label === "string" && label) {
    state.uploadProgressLabel = label;
  } else if (state.uploadProgressPhase === "idle") {
    state.uploadProgressLabel = "准备上传…";
  }
  renderUploadProgress();
}

function resetUploadProgress() {
  clearProgressHideTimer();
  state.uploadProgress = 0;
  state.uploadProgressPhase = "idle";
  state.uploadProgressLabel = "准备上传…";
  renderUploadProgress();
}

function getDocumentProgress(document) {
  const value = Number.parseInt(document?.parse_progress, 10);
  if (!Number.isFinite(value)) {
    return document?.parse_status === "ready" ? 100 : 0;
  }
  return Math.max(0, Math.min(100, value));
}

function getDocumentStage(document) {
  return String(document?.parse_stage || document?.parse_status_label || "");
}

function syncTrackedUploadProgress() {
  if (state.uploading || !Number.isInteger(state.progressDocumentId)) {
    return;
  }
  const trackedDocument = (
    state.currentDocument?.id === state.progressDocumentId
      ? state.currentDocument
      : state.documents.find((item) => item.id === state.progressDocumentId)
  ) || null;

  if (!trackedDocument) {
    return;
  }

  const progress = getDocumentProgress(trackedDocument);
  const stage = getDocumentStage(trackedDocument);

  if (trackedDocument.parse_status === "ready") {
    setUploadResult(
      trackedDocument.parse_warning || "PDF 解析完成。",
      trackedDocument.parse_warning ? "is-warning" : "is-success",
    );
    setUploadProgress(100, "done", stage || "解析完成");
    clearProgressHideTimer();
    state.progressHideTimer = window.setTimeout(() => {
      if (state.progressDocumentId === trackedDocument.id) {
        state.progressDocumentId = null;
      }
      resetUploadProgress();
    }, 1500);
    return;
  }

  clearProgressHideTimer();
  if (trackedDocument.parse_status === "failed") {
    setUploadResult(trackedDocument.parse_error || "PDF 解析失败。", "is-warning");
    setUploadProgress(progress, "error", stage || "解析失败");
    return;
  }

  if (["pending", "processing"].includes(trackedDocument.parse_status)) {
    setUploadProgress(progress, "processing", stage || trackedDocument.parse_status_label);
  }
}

function schedulePollIfNeeded() {
  clearPollTimer();
  if (!state.documents.some((item) => ["pending", "processing"].includes(item.parse_status))) {
    return;
  }
  state.pollTimer = window.setTimeout(() => {
    void loadDocuments({ preserveSelection: true, refreshDetail: true });
  }, 1200);
}

function setUploadResult(message, type = "") {
  uploadResultEl.textContent = message || "";
  uploadResultEl.className = "config-save-result";
  if (type) {
    uploadResultEl.classList.add(type);
  }
}

function setDocumentMessage(message, type = "") {
  docMessageEl.textContent = message || "";
  docMessageEl.className = "config-save-result";
  if (type) {
    docMessageEl.classList.add(type);
  }
}

function setPreviewEmpty(message) {
  previewMetaEl.textContent = "";
  previewEl.hidden = true;
  previewEl.innerHTML = "";
  previewEmptyEl.hidden = false;
  previewEmptyEl.textContent = message;
  state.currentExcerpt = null;
  syncActionButtons();
}

function syncActionButtons() {
  const ready = state.currentDocument?.parse_status === "ready";
  buildPageExcerptBtn.disabled = !ready || state.uploading;
  buildSectionExcerptBtn.disabled = !ready || !sectionSelectEl.value || state.uploading;
  rangeStartEl.disabled = !ready || state.uploading;
  rangeEndEl.disabled = !ready || state.uploading;
  sectionSelectEl.disabled = !ready || sectionSelectEl.options.length <= 1 || state.uploading;
  sectionsTabEl.disabled = !ready || sectionTreeEl.childElementCount === 0;
  pagesTabEl.disabled = !ready;
  sendChatBtn.disabled = !state.currentExcerpt?.text || state.uploading;
  uploadBtn.disabled = state.uploading;
  fileInputEl.disabled = state.uploading;
}

function setViewMode(nextMode) {
  const hasSections = sectionTreeEl.childElementCount > 0;
  state.viewMode = nextMode === "pages" || !hasSections ? "pages" : "sections";
  sectionsTabEl.classList.toggle("is-active", state.viewMode === "sections");
  pagesTabEl.classList.toggle("is-active", state.viewMode === "pages");
  sectionTreeEl.hidden = state.viewMode !== "sections";
  pageGridEl.hidden = state.viewMode !== "pages";
}

function renderDocuments() {
  docListEl.innerHTML = "";
  if (!state.documents.length) {
    const emptyEl = document.createElement("div");
    emptyEl.className = "admin-empty";
    emptyEl.textContent = "还没有 PDF 文档，先上传一个试试。";
    docListEl.appendChild(emptyEl);
    return;
  }

  for (const doc of state.documents) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pdf-doc-item";
    if (doc.id === state.currentDocumentId) {
      button.classList.add("is-active");
    }
    const docProgress = `${formatNumber(doc.parse_progress)}%`;
    const docStage = escapeHtml(doc.parse_stage || doc.parse_status_label);
    const metaHtml = doc.parse_status === "ready"
      ? `
        <span>${formatNumber(doc.page_count)} 页</span>
        <span>${formatNumber(doc.total_chars)} 字</span>
        <span>${escapeHtml(doc.section_source_label)}</span>
      `
      : `
        <span>${docProgress}</span>
        <span>${docStage}</span>
        <span>${escapeHtml(doc.section_source_label)}</span>
      `;
    button.innerHTML = `
      <div class="pdf-doc-item-head">
        <span class="pdf-doc-item-title">${escapeHtml(doc.display_title)}</span>
        <span class="status-badge is-${escapeHtml(doc.parse_status)}">${escapeHtml(doc.parse_status_label)}</span>
      </div>
      <div class="pdf-doc-item-meta">
        ${metaHtml}
      </div>
      <div class="pdf-doc-item-name">${escapeHtml(doc.original_file_name)}</div>
    `;
    button.addEventListener("click", () => {
      void selectDocument(doc.id);
    });
    docListEl.appendChild(button);
  }
}

function flattenSections(sections, result = []) {
  for (const section of sections) {
    result.push(section);
    flattenSections(section.children || [], result);
  }
  return result;
}

function renderSections(sections) {
  sectionTreeEl.innerHTML = "";
  sectionSelectEl.innerHTML = '<option value="">请选择章节</option>';
  const flatSections = flattenSections(sections, []);

  for (const section of flatSections) {
    const option = document.createElement("option");
    option.value = String(section.id);
    option.textContent = `${"  ".repeat(Math.max(0, section.level - 1))}${section.title}（${section.start_page}-${section.end_page} 页）`;
    sectionSelectEl.appendChild(option);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "pdf-section-item";
    button.style.paddingLeft = `${12 + Math.max(0, section.level - 1) * 18}px`;
    button.innerHTML = `
      <span class="pdf-section-item-title">${escapeHtml(section.title)}</span>
      <span class="pdf-section-item-meta">第 ${section.start_page} - ${section.end_page} 页</span>
    `;
    button.addEventListener("click", () => {
      setViewMode("sections");
      sectionSelectEl.value = String(section.id);
      syncActionButtons();
      void buildSectionExcerpt(section.id);
    });
    sectionTreeEl.appendChild(button);
  }
}

function renderPages(pages) {
  pageGridEl.innerHTML = "";
  for (const page of pages) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pdf-page-btn";
    if (!page.has_text) {
      button.classList.add("is-empty");
    }
    button.textContent = String(page.page_number);
    button.title = page.has_text ? `第 ${page.page_number} 页` : `第 ${page.page_number} 页（无文本）`;
    button.addEventListener("click", () => {
      setViewMode("pages");
      rangeStartEl.value = String(page.page_number);
      rangeEndEl.value = String(page.page_number);
      void buildPageExcerpt(page.page_number, page.page_number);
    });
    pageGridEl.appendChild(button);
  }
}

function renderDocumentMeta(document) {
  docTitleEl.textContent = document?.display_title || "请选择一个 PDF";
  if (!document) {
    docStatusEl.textContent = "上传后会在这里显示解析状态与摘要信息。";
    docMetaEl.innerHTML = "";
    setDocumentMessage("");
    renderSections([]);
    renderPages([]);
    navEmptyEl.hidden = false;
    sectionTreeEl.hidden = true;
    pageGridEl.hidden = true;
    setPreviewEmpty("点击章节、页码或手动输入页范围后开始预览。");
    syncActionButtons();
    return;
  }

  const documentProgress = `${formatNumber(document.parse_progress)}%`;
  const documentStage = escapeHtml(document.parse_stage || document.parse_status_label);
  docStatusEl.innerHTML = `当前状态：<span class="status-badge is-${escapeHtml(document.parse_status)}">${escapeHtml(document.parse_status_label)}</span> · ${documentStage} · ${documentProgress}`;
  docMetaEl.innerHTML = `
    <div class="pdf-meta-item"><span>原文件</span><strong>${escapeHtml(document.original_file_name)}</strong></div>
    <div class="pdf-meta-item"><span>解析进度</span><strong>${documentProgress}</strong></div>
    <div class="pdf-meta-item"><span>页数</span><strong>${formatNumber(document.page_count)}</strong></div>
    <div class="pdf-meta-item"><span>字符数</span><strong>${formatNumber(document.total_chars)}</strong></div>
    <div class="pdf-meta-item"><span>文件大小</span><strong>${formatFileSize(document.file_size_bytes)}</strong></div>
    <div class="pdf-meta-item"><span>章节来源</span><strong>${escapeHtml(document.section_source_label)}</strong></div>
    <div class="pdf-meta-item"><span>解析时间</span><strong>${escapeHtml(document.parsed_at || "--")}</strong></div>
  `;

  if (document.parse_error) {
    setDocumentMessage(document.parse_error, "is-warning");
  } else if (document.parse_warning) {
    setDocumentMessage(document.parse_warning, "is-warning");
  } else {
    setDocumentMessage(
      document.parse_status === "ready"
        ? "PDF 解析完成，可以开始浏览和节选。"
        : `${document.parse_stage || "等待后台任务排队"}（${documentProgress}）`,
      document.parse_status === "ready" ? "is-success" : "",
    );
  }
}

function renderDocumentDetail(data) {
  const document = data?.document || null;
  state.currentDocument = document;
  renderDocumentMeta(document);
  syncTrackedUploadProgress();
  state.currentExcerpt = null;
  previewMetaEl.textContent = "";
  previewEl.hidden = true;
  previewEl.innerHTML = "";
  previewEmptyEl.hidden = false;
  previewEmptyEl.textContent = "点击章节、页码或手动输入页范围后开始预览。";

  if (!document || document.parse_status !== "ready") {
    navEmptyEl.hidden = false;
    sectionTreeEl.innerHTML = "";
    pageGridEl.innerHTML = "";
    sectionTreeEl.hidden = true;
    pageGridEl.hidden = true;
    rangeStartEl.value = "";
    rangeEndEl.value = "";
    sectionSelectEl.innerHTML = '<option value="">请选择章节</option>';
    setPreviewEmpty(
      !document
        ? "点击章节、页码或手动输入页范围后开始预览。"
        : (document.parse_status === "failed" ? "PDF 解析失败，当前无法浏览正文内容。" : "等待解析完成后可浏览内容。"),
    );
    syncActionButtons();
    return;
  }

  const pages = Array.isArray(data.pages) ? data.pages : [];
  const sections = Array.isArray(data.sections) ? data.sections : [];
  const maxPage = Math.max(1, document.page_count || pages.length || 1);
  rangeStartEl.min = "1";
  rangeStartEl.max = String(maxPage);
  rangeEndEl.min = "1";
  rangeEndEl.max = String(maxPage);
  rangeStartEl.value = rangeStartEl.value || "1";
  rangeEndEl.value = rangeEndEl.value || String(Math.min(maxPage, Number.parseInt(rangeStartEl.value, 10) || 1));

  renderSections(sections);
  renderPages(pages);
  navEmptyEl.hidden = Boolean(sections.length || pages.length);
  setViewMode(sections.length ? state.viewMode : "pages");
  syncActionButtons();
}

function renderExcerpt(excerpt) {
  state.currentExcerpt = excerpt;
  previewMetaEl.textContent = `当前节选：${excerpt.label}｜${formatNumber(excerpt.char_count)} 字${excerpt.warning ? `｜${excerpt.warning}` : ""}`;
  previewEl.innerHTML = "";
  previewEl.hidden = false;
  previewEmptyEl.hidden = true;

  for (const block of excerpt.blocks || []) {
    const blockEl = document.createElement("section");
    blockEl.className = "pdf-preview-block";
    const labelEl = document.createElement("div");
    labelEl.className = "pdf-preview-block-label";
    labelEl.textContent = block.label || "内容";
    const contentEl = document.createElement("pre");
    contentEl.className = "pdf-preview-block-content";
    contentEl.textContent = block.text || "";
    blockEl.append(labelEl, contentEl);
    previewEl.appendChild(blockEl);
  }
  syncActionButtons();
}

async function loadDocumentDetail(documentId) {
  const data = await fetchJson(`/api/pdf-documents/${documentId}`);
  state.currentDocumentId = data.document.id;
  renderDocumentDetail(data);
  syncTrackedUploadProgress();
  renderDocuments();
}

async function selectDocument(documentId) {
  state.currentDocumentId = documentId;
  renderDocuments();
  await loadDocumentDetail(documentId);
}

async function loadDocuments(options = {}) {
  const { preserveSelection = true, refreshDetail = false, preferredId = null } = options;
  const data = await fetchJson("/api/pdf-documents");
  state.documents = Array.isArray(data.documents) ? data.documents : [];

  const nextDocumentId = preferredId
    || (preserveSelection ? state.currentDocumentId : null)
    || state.documents[0]?.id
    || null;

  if (nextDocumentId && !state.documents.some((item) => item.id === nextDocumentId)) {
    state.currentDocumentId = state.documents[0]?.id || null;
  } else {
    state.currentDocumentId = nextDocumentId;
  }

  if (!Number.isInteger(state.progressDocumentId)) {
    state.progressDocumentId = state.documents.find((item) => ["pending", "processing"].includes(item.parse_status))?.id || null;
  }

  renderDocuments();
  syncTrackedUploadProgress();
  schedulePollIfNeeded();

  if (!state.currentDocumentId) {
    renderDocumentDetail(null);
    return;
  }

  if (refreshDetail || !state.currentDocument || state.currentDocument.id !== state.currentDocumentId) {
    await loadDocumentDetail(state.currentDocumentId);
  }
}

async function buildPageExcerpt(startPage, endPage) {
  const documentId = state.currentDocumentId;
  if (!Number.isInteger(documentId)) return;
  const data = await fetchJson(`/api/pdf-documents/${documentId}/excerpt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: "page_range",
      start_page: startPage,
      end_page: endPage,
    }),
  });
  renderExcerpt(data.excerpt);
}

async function buildSectionExcerpt(sectionId) {
  const documentId = state.currentDocumentId;
  if (!Number.isInteger(documentId)) return;
  const data = await fetchJson(`/api/pdf-documents/${documentId}/excerpt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: "section",
      section_id: sectionId,
    }),
  });
  renderExcerpt(data.excerpt);
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInputEl.files?.[0] || null;
  if (!file) {
    setUploadResult("请先选择一个 PDF 文件。", "is-warning");
    return;
  }

  state.uploading = true;
  state.progressDocumentId = null;
  clearProgressHideTimer();
  setUploadProgress(0, "uploading", "正在上传 PDF…");
  syncActionButtons();
  setUploadResult("正在上传 PDF，上传完成后会转入后台解析。");
  try {
    const data = await uploadPdfFile(file);
    state.uploading = false;
    state.progressDocumentId = Number.parseInt(data.document?.id, 10) || null;
    fileInputEl.value = "";
    setUploadResult("上传成功，已提交后台解析任务。", "is-success");
    syncTrackedUploadProgress();
    await loadDocuments({ preserveSelection: false, refreshDetail: true, preferredId: data.document.id });
  } catch (error) {
    state.uploading = false;
    state.progressDocumentId = null;
    setUploadProgress(state.uploadProgress || 0, "error", "上传失败");
    setUploadResult(getErrorMessage(error), "is-warning");
    await loadDocuments({ preserveSelection: true, refreshDetail: true });
  } finally {
    syncActionButtons();
  }
});

sectionsTabEl.addEventListener("click", () => {
  setViewMode("sections");
});

pagesTabEl.addEventListener("click", () => {
  setViewMode("pages");
});

sectionSelectEl.addEventListener("change", () => {
  syncActionButtons();
});

buildPageExcerptBtn.addEventListener("click", async () => {
  const startPage = Number.parseInt(rangeStartEl.value, 10);
  const endPage = Number.parseInt(rangeEndEl.value, 10);
  if (!Number.isFinite(startPage) || !Number.isFinite(endPage) || startPage <= 0 || endPage <= 0) {
    setPreviewEmpty("请输入有效的页码范围。", "is-warning");
    return;
  }
  try {
    await buildPageExcerpt(startPage, endPage);
  } catch (error) {
    setPreviewEmpty(getErrorMessage(error));
  }
});

buildSectionExcerptBtn.addEventListener("click", async () => {
  const sectionId = Number.parseInt(sectionSelectEl.value, 10);
  if (!Number.isFinite(sectionId) || sectionId <= 0) {
    setPreviewEmpty("请先选择一个章节。", "is-warning");
    return;
  }
  try {
    await buildSectionExcerpt(sectionId);
  } catch (error) {
    setPreviewEmpty(getErrorMessage(error));
  }
});

sendChatBtn.addEventListener("click", () => {
  if (!state.currentExcerpt?.text) {
    setPreviewEmpty("请先生成可发送的节选内容。");
    return;
  }

  const payload = {
    type: "pdf_excerpt",
    text: state.currentExcerpt.text,
    label: state.currentExcerpt.label,
    documentId: state.currentDocument?.id || null,
    documentTitle: state.currentDocument?.display_title || "PDF 节选",
    originalFileName: state.currentDocument?.original_file_name || "",
    createdAt: new Date().toISOString(),
    createNewConversation: true,
  };
  window.localStorage.setItem(PDF_CHAT_DRAFT_STORAGE_KEY, JSON.stringify(payload));
  window.location.href = "/chat";
});

openChatBtn.addEventListener("click", () => {
  window.location.href = "/chat";
});

chatBtn?.addEventListener("click", () => {
  window.location.href = "/chat";
});

adminBtn?.addEventListener("click", () => {
  window.location.href = "/admin";
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

window.addEventListener("beforeunload", () => {
  clearPollTimer();
  clearProgressHideTimer();
});

(async function init() {
  syncActionButtons();
  try {
    await loadDocuments({ preserveSelection: true, refreshDetail: true });
  } catch (error) {
    renderDocumentDetail(null);
    setUploadResult(`初始化失败：${getErrorMessage(error)}`, "is-warning");
  }
})();
