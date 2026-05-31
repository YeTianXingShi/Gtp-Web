import { apiJson, apiFetch } from "./client";
import type { Conversation, ConversationDetail } from "@/types/api";

export async function listConversations(query?: string): Promise<Conversation[]> {
  const search = query ? `?q=${encodeURIComponent(query)}` : "";
  const data = await apiJson<{ ok: true; conversations: Conversation[] }>(
    `/api/conversations${search}`,
  );
  return data.conversations;
}

export async function createConversation(payload: {
  model: string;
  reasoning_effort?: string;
  thinking_level?: string;
  title?: string;
}): Promise<Conversation> {
  const data = await apiJson<{ ok: true; conversation: Conversation }>(
    "/api/conversations",
    { method: "POST", body: JSON.stringify(payload) },
  );
  return data.conversation;
}

export async function updateConversation(
  id: number,
  patch: { title?: string; model?: string; reasoning_effort?: string; thinking_level?: string },
): Promise<Conversation> {
  const data = await apiJson<{ ok: true; conversation: Conversation }>(
    `/api/conversations/${id}`,
    { method: "PATCH", body: JSON.stringify(patch) },
  );
  return data.conversation;
}

export async function deleteConversation(id: number): Promise<void> {
  await apiJson<{ ok: true }>(`/api/conversations/${id}`, { method: "DELETE" });
}

export async function fetchMessages(id: number): Promise<ConversationDetail> {
  return apiJson<ConversationDetail>(`/api/conversations/${id}/messages`);
}

// 通过 apiFetch 拿原始响应，用于触发浏览器下载
export async function exportConversation(id: number, format: "json" | "txt" | "md"): Promise<void> {
  const resp = await apiFetch(`/api/conversations/${id}/export?format=${format}`);
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { error?: string }).error ?? "导出失败");
  }
  const blob = await resp.blob();
  // 从 Content-Disposition 提取文件名
  const disposition = resp.headers.get("Content-Disposition") ?? "";
  let filename = `conversation_${id}.${format}`;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/);
  if (utf8Match) {
    filename = decodeURIComponent(utf8Match[1]);
  } else {
    const asciiMatch = disposition.match(/filename="([^"]+)"/);
    if (asciiMatch) filename = asciiMatch[1];
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function fetchMyUsage(): Promise<unknown> {
  const data = await apiJson<{ ok: true; usage: unknown }>("/api/me/usage");
  return data.usage;
}
