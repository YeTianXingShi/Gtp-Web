import { apiJson } from "./client";
import type { AdminUser, AuditLog, ConfigFileMeta, DashboardStats } from "@/types/api";

export async function fetchDashboard(): Promise<DashboardStats> {
  return apiJson<DashboardStats>("/api/admin/dashboard");
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  const data = await apiJson<{ ok: true; users: AdminUser[] }>("/api/admin/users");
  return data.users;
}

export async function createAdminUser(payload: {
  username: string;
  password: string;
  is_admin: boolean;
}): Promise<void> {
  await apiJson<{ ok: true }>("/api/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAdminUser(
  username: string,
  patch: {
    password?: string;
    is_admin?: boolean;
    enabled?: boolean;
    api_keys?: Record<string, string>;
    profile?: Record<string, string>;
  },
): Promise<void> {
  await apiJson<{ ok: true }>(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteAdminUser(username: string): Promise<void> {
  await apiJson<{ ok: true }>(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export async function fetchTokenUsage(
  range: "today" | "week" | "month",
  username?: string,
): Promise<unknown> {
  const params = new URLSearchParams({ range });
  if (username) params.set("username", username);
  const data = await apiJson<{ ok: true; usage: unknown }>(
    `/api/admin/token-usage?${params.toString()}`,
  );
  return data.usage;
}

export async function fetchAuditLogs(opts?: {
  username?: string;
  action?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLog[]> {
  const params = new URLSearchParams();
  if (opts?.username) params.set("username", opts.username);
  if (opts?.action) params.set("action", opts.action);
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.offset) params.set("offset", String(opts.offset));
  const data = await apiJson<{ ok: true; logs: AuditLog[] }>(
    `/api/admin/audit-logs${params.toString() ? "?" + params.toString() : ""}`,
  );
  return data.logs;
}

export interface ConfigFileListResponse {
  ok: true;
  files: ConfigFileMeta[];
  default_file_id: string;
}

export async function listConfigFiles(): Promise<ConfigFileListResponse> {
  return apiJson<ConfigFileListResponse>("/api/admin/config-files");
}

export interface ConfigFileDetail extends ConfigFileMeta {
  ok: true;
  content: string;
  hot_reload?: { applied_keys: string[]; restart_required_keys: string[] };
}

export async function fetchConfigFile(id: string): Promise<ConfigFileDetail> {
  return apiJson<ConfigFileDetail>(`/api/admin/config-files/${id}`);
}

export async function saveConfigFile(id: string, content: string): Promise<ConfigFileDetail> {
  return apiJson<ConfigFileDetail>(`/api/admin/config-files/${id}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
}
