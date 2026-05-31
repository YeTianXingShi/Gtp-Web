import { useAuthStore } from "@/stores/authStore";
import { parseSseChunks } from "@/utils/sse";
import type { ChatStreamEvent } from "@/types/sse";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const IDLE_TIMEOUT_MS = 30_000;

export interface ChatStreamRequest {
  conversationId: number;
  content: string;
  files?: File[];
  model?: string;
  reasoningEffort?: string;
  thinkingLevel?: string;
}

export interface ChatStreamCallbacks {
  onDelta?: (text: string) => void;
  onReasoning?: (text: string) => void;
  onUsage?: (input: number, output: number) => void;
  onDone?: (reply: string) => void;
  onError?: (error: string) => void;
}

function buildFormData(req: ChatStreamRequest): FormData {
  const form = new FormData();
  form.append("conversation_id", String(req.conversationId));
  form.append("content", req.content);
  if (req.model) form.append("model", req.model);
  if (req.reasoningEffort) form.append("reasoning_effort", req.reasoningEffort);
  if (req.thinkingLevel) form.append("thinking_level", req.thinkingLevel);
  for (const file of req.files ?? []) {
    form.append("files", file);
  }
  return form;
}

async function postStream(
  endpoint: string,
  body: FormData,
  signal: AbortSignal,
): Promise<Response> {
  const token = useAuthStore.getState().accessToken;
  const headers: HeadersInit = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    body,
    credentials: "include",
    headers,
    signal,
  });
}

async function consumeStream(
  resp: Response,
  callbacks: ChatStreamCallbacks,
  abortController: AbortController,
): Promise<void> {
  if (!resp.ok || !resp.body) {
    let errorMsg = `请求失败 (${resp.status})`;
    try {
      const data = await resp.json();
      if (data?.error) errorMsg = String(data.error);
    } catch {
      /* 流式响应解析失败也无所谓 */
    }
    callbacks.onError?.(errorMsg);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  const armIdle = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => abortController.abort(), IDLE_TIMEOUT_MS);
  };
  armIdle();

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      armIdle();
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseChunks(buffer);
      buffer = rest;
      for (const evt of events) {
        let parsed: ChatStreamEvent | null = null;
        try {
          parsed = JSON.parse(evt.data) as ChatStreamEvent;
        } catch {
          continue;
        }
        if (!parsed) continue;
        if (parsed.type === "delta") callbacks.onDelta?.(parsed.text);
        else if (parsed.type === "reasoning") callbacks.onReasoning?.(parsed.text);
        else if (parsed.type === "usage")
          callbacks.onUsage?.(parsed.input_tokens, parsed.output_tokens);
        else if (parsed.type === "done") callbacks.onDone?.(parsed.reply);
        else if (parsed.type === "error") callbacks.onError?.(parsed.error);
      }
    }
  } finally {
    if (idleTimer) clearTimeout(idleTimer);
    try {
      reader.releaseLock();
    } catch {
      /* 已释放 */
    }
  }
}

export interface StreamHandle {
  abort: () => void;
  promise: Promise<void>;
}

export function startChatStream(
  req: ChatStreamRequest,
  callbacks: ChatStreamCallbacks,
): StreamHandle {
  const controller = new AbortController();
  const promise = (async () => {
    try {
      const resp = await postStream("/api/chat/stream", buildFormData(req), controller.signal);
      // 401 不会自动 refresh（流式请求体无法重放 FormData 中的文件指针）；
      // 退化为提示用户重新发送。绝大多数情况下进入聊天页时已通过 /api/me 触发过 refresh。
      if (resp.status === 401) {
        callbacks.onError?.("登录已过期，请刷新页面后重试");
        return;
      }
      await consumeStream(resp, callbacks, controller);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      callbacks.onError?.((err as Error).message ?? "网络异常");
    }
  })();
  return { abort: () => controller.abort(), promise };
}

export function startRetryStream(
  conversationId: number,
  callbacks: ChatStreamCallbacks,
): StreamHandle {
  const controller = new AbortController();
  const form = new FormData();
  form.append("conversation_id", String(conversationId));
  const promise = (async () => {
    try {
      const resp = await postStream("/api/chat/retry/stream", form, controller.signal);
      if (resp.status === 401) {
        callbacks.onError?.("登录已过期，请刷新页面后重试");
        return;
      }
      await consumeStream(resp, callbacks, controller);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      callbacks.onError?.((err as Error).message ?? "网络异常");
    }
  })();
  return { abort: () => controller.abort(), promise };
}
