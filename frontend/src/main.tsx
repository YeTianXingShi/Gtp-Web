import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import { App as AntdApp } from "antd";

import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";
import { AdminPage } from "@/pages/AdminPage";
import { TutorialPage } from "@/pages/TutorialPage";
import { ClientsPage } from "@/pages/ClientsPage";
import { AuthGuard } from "@/components/AuthGuard";
import "@/styles/global.css";

dayjs.locale("zh-cn");

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/chat",
    element: (
      <AuthGuard>
        <ChatPage />
      </AuthGuard>
    ),
  },
  {
    path: "/admin",
    element: (
      <AuthGuard requireAdmin>
        <AdminPage />
      </AuthGuard>
    ),
  },
  {
    path: "/tutorial",
    element: (
      <AuthGuard>
        <TutorialPage />
      </AuthGuard>
    ),
  },
  {
    path: "/clients",
    element: (
      <AuthGuard>
        <ClientsPage />
      </AuthGuard>
    ),
  },
  { path: "/", element: <AuthGuard><ChatPage /></AuthGuard> },
  { path: "*", element: <AuthGuard><ChatPage /></AuthGuard> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#1677ff",
          borderRadius: 6,
        },
      }}
    >
      <AntdApp>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
