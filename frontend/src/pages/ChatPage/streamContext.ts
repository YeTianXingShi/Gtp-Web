import { createContext, useContext } from "react";
import type { useChatStream } from "@/hooks/useChatStream";

export type ChatStreamHandle = ReturnType<typeof useChatStream>;

export const ChatStreamContext = createContext<ChatStreamHandle | null>(null);

export function useChatStreamContext(): ChatStreamHandle {
  const ctx = useContext(ChatStreamContext);
  if (!ctx) throw new Error("ChatStreamContext 未提供");
  return ctx;
}
