import { apiFetch, apiJson } from "./client";
import type { DocumentMeta } from "@/types/api";

export async function listDocuments(): Promise<DocumentMeta[]> {
  const data = await apiJson<{ ok: true; documents: DocumentMeta[] }>("/api/documents");
  return data.documents;
}

// 通过 apiFetch 拿原始响应触发下载
export async function downloadDocument(doc: DocumentMeta): Promise<void> {
  const resp = await apiFetch(`/api/documents/${doc.id}/download`);
  if (!resp.ok) throw new Error(`下载失败 (${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = doc.file_name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function uploadDocument(payload: {
  file: File;
  title?: string;
  category?: string;
}): Promise<{ id: number; title: string; category: string }> {
  const form = new FormData();
  form.append("file", payload.file);
  if (payload.title) form.append("title", payload.title);
  if (payload.category) form.append("category", payload.category);
  const data = await apiJson<{ ok: true; document: { id: number; title: string; category: string } }>(
    "/api/admin/documents",
    { method: "POST", body: form },
  );
  return data.document;
}

export async function updateDocument(
  id: number,
  patch: { title?: string; category?: string },
): Promise<void> {
  await apiJson<{ ok: true }>(`/api/admin/documents/${id}`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export async function deleteDocument(id: number): Promise<void> {
  await apiJson<{ ok: true }>(`/api/admin/documents/${id}`, { method: "DELETE" });
}
