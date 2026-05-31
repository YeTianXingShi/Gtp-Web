import { apiJson } from "./client";
import type { BootstrapData } from "@/types/api";

export async function fetchBootstrap(): Promise<BootstrapData> {
  const data = await apiJson<BootstrapData & { ok: true }>("/api/bootstrap");
  return data;
}

export async function fetchTutorial(): Promise<{ content: string; exists: boolean }> {
  const data = await apiJson<{ ok: true; content: string; exists: boolean }>(
    "/api/tutorial",
  );
  return { content: data.content, exists: data.exists };
}
