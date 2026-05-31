import { useAuthStore } from "@/stores/authStore";
import type { LoginResponse } from "@/types/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// 同步并发的 refresh 单例：多个 401 请求只触发一次 refresh
let refreshPromise: Promise<string> | null = null;

async function performRefresh(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = fetch(`${API_BASE}/api/refresh`, {
    method: "POST",
    credentials: "include",
  })
    .then(async (resp) => {
      if (!resp.ok) {
        throw new Error("refresh failed");
      }
      const data = (await resp.json()) as LoginResponse;
      useAuthStore.getState().setAuth(data.access_token, data.user);
      return data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

interface ApiFetchOptions extends RequestInit {
  // 内部标记：避免 401 后无限循环重试
  _retried?: boolean;
}

function buildHeaders(init: ApiFetchOptions, token: string | null): HeadersInit {
  const headers = new Headers(init.headers as HeadersInit | undefined);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // FormData 让浏览器自己设置 Content-Type（含 boundary），其他默认 JSON
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

export async function apiFetch(path: string, init: ApiFetchOptions = {}): Promise<Response> {
  const token = useAuthStore.getState().accessToken;
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: buildHeaders(init, token),
  });

  if (resp.status !== 401 || init._retried) {
    return resp;
  }

  // 401 → 尝试 refresh 并重放原请求一次
  try {
    const newToken = await performRefresh();
    return fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: buildHeaders(init, newToken),
    });
  } catch {
    useAuthStore.getState().clear();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.replace("/login");
    }
    throw new Error("登录已过期");
  }
}

// 便捷封装：返回解析后的 JSON。失败抛出 Error 含 message。
export async function apiJson<T>(path: string, init?: ApiFetchOptions): Promise<T> {
  const resp = await apiFetch(path, init);
  const text = await resp.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`响应不是合法 JSON: ${text.slice(0, 200)}`);
    }
  }
  if (!resp.ok) {
    const message =
      data && typeof data === "object" && "error" in (data as Record<string, unknown>)
        ? String((data as Record<string, unknown>).error)
        : `请求失败 (${resp.status})`;
    throw new Error(message);
  }
  return data as T;
}

// 在登录成功 / 启动时手动触发，用于绕过 apiFetch 的 401 处理
export async function tryRefreshOnBoot(): Promise<boolean> {
  try {
    await performRefresh();
    return true;
  } catch {
    useAuthStore.getState().clear();
    return false;
  }
}
