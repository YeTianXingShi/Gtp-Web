import { create } from "zustand";

interface ChatState {
  currentConversationId: number | null;
  searchKeyword: string;
  setCurrentConversation: (id: number | null) => void;
  setSearchKeyword: (q: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  currentConversationId: null,
  searchKeyword: "",
  setCurrentConversation: (id) => set({ currentConversationId: id }),
  setSearchKeyword: (q) => set({ searchKeyword: q }),
}));
