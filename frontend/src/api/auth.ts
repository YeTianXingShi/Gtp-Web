import { apiJson } from "./client";
import { useAuthStore } from "@/stores/authStore";
import type { LoginResponse, User } from "@/types/api";

export async function login(username: string, password: string): Promise<LoginResponse> {
  const data = await apiJson<LoginResponse>("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  useAuthStore.getState().setAuth(data.access_token, data.user);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await apiJson<{ ok: true }>("/api/logout", { method: "POST" });
  } finally {
    useAuthStore.getState().clear();
  }
}

export async function fetchMe(): Promise<User> {
  const data = await apiJson<{ ok: true; user: User }>("/api/me");
  return data.user;
}
