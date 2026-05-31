import { Layout, Tabs, Button, Space } from "antd";
import { useNavigate } from "react-router-dom";
import { LogoutOutlined } from "@ant-design/icons";
import { logout } from "@/api/auth";
import { DashboardTab } from "./DashboardTab";
import { UsersTab } from "./UsersTab";
import { UsageTab } from "./UsageTab";
import { DocumentsTab } from "./DocumentsTab";
import { ModelTab } from "./ModelTab";
import { ConfigTab } from "./ConfigTab";
import { AuditTab } from "./AuditTab";
import { LogoTab } from "./LogoTab";

export function AdminPage() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Header
        style={{
          background: "#fff",
          padding: "0 24px",
          height: 56,
          lineHeight: "56px",
          borderBottom: "1px solid #f0f0f0",
          display: "flex",
          alignItems: "center",
        }}
      >
        <img src="/api/logo" alt="Logo" style={{ width: 28, height: 28, borderRadius: 4 }} />
        <span style={{ marginLeft: 12, fontWeight: 600, fontSize: 16 }}>后台管理</span>
        <div style={{ flex: 1 }} />
        <Space>
          <Button onClick={() => navigate("/chat")}>进入聊天</Button>
          <Button icon={<LogoutOutlined />} onClick={handleLogout}>
            退出
          </Button>
        </Space>
      </Layout.Header>

      <Layout.Content style={{ padding: 24, background: "#f5f5f5" }}>
        <div style={{ background: "#fff", padding: 16, borderRadius: 8 }}>
          <Tabs
            defaultActiveKey="dashboard"
            destroyOnHidden
            items={[
              { key: "dashboard", label: "仪表盘", children: <DashboardTab /> },
              { key: "users", label: "账号管理", children: <UsersTab /> },
              { key: "usage", label: "用量统计", children: <UsageTab /> },
              { key: "documents", label: "文档管理", children: <DocumentsTab /> },
              { key: "models", label: "模型配置", children: <ModelTab /> },
              { key: "config", label: "配置文件", children: <ConfigTab /> },
              { key: "logo", label: "Logo 管理", children: <LogoTab /> },
              { key: "audit", label: "审计日志", children: <AuditTab /> },
            ]}
          />
        </div>
      </Layout.Content>
    </Layout>
  );
}
