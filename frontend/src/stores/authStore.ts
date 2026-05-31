import { create } from "zustand";
import type { User } from "@/types/api";

interface AuthState {
  accessToken: string | null;
  user: User | null;
  // 应用初始化中：尚未尝试 refresh，路由守卫不应做决断
  initialized: boolean;
  setAuth: (token: string, user: User) => void;
  clear: () => void;
  setInitialized: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  initialized: false,
  setAuth: (accessToken, user) => set({ accessToken, user }),
  clear: () => set({ accessToken: null, user: null }),
  setInitialized: (initialized) => set({ initialized }),
}));
