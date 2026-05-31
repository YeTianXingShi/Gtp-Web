import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore } from "@/stores/authStore";
import { tryRefreshOnBoot } from "@/api/client";

interface AuthGuardProps {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

// 启动时尝试 refresh：成功则进入受保护路由，失败跳登录。
// 同 tab 多个守卫共享一次启动状态。
let bootstrapPromise: Promise<boolean> | null = null;

function ensureBootstrap(): Promise<boolean> {
  if (bootstrapPromise) return bootstrapPromise;
  bootstrapPromise = tryRefreshOnBoot().finally(() => {
    useAuthStore.getState().setInitialized(true);
  });
  return bootstrapPromise;
}

export function AuthGuard({ children, requireAdmin }: AuthGuardProps) {
  const { accessToken, user, initialized } = useAuthStore();
  const [, setTick] = useState(0);
  const location = useLocation();

  useEffect(() => {
    if (!initialized) {
      ensureBootstrap().then(() => setTick((n) => n + 1));
    }
  }, [initialized]);

  if (!initialized) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!accessToken || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (requireAdmin && !user.is_admin) {
    return <Navigate to="/chat" replace />;
  }

  return <>{children}</>;
}
