import { Layout, Select, Button, Space, Typography, Dropdown, Avatar } from "antd";
import { MenuOutlined, UserOutlined, LogoutOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useMemo } from "react";
import { useAuthStore } from "@/stores/authStore";
import { logout } from "@/api/auth";
import type { BootstrapData, ModelOption } from "@/types/api";

interface TopbarProps {
  bootstrap: BootstrapData;
  selectedModel: string;
  onSelectModel: (id: string) => void;
  reasoningEffort: string;
  onReasoningEffortChange: (v: string) => void;
  thinkingLevel: string;
  onThinkingLevelChange: (v: string) => void;
  onToggleSidebar: () => void;
  onOpenDocs: () => void;
  onOpenUsage: () => void;
}

interface EffortConfig {
  enabled: boolean;
  options: string[];
  type: "reasoning_effort" | "thinking_level" | null;
  label: string;
}

function detectEffortConfig(option: ModelOption | undefined): EffortConfig {
  if (!option) return { enabled: false, options: [], type: null, label: "" };
  if (option.openai_reasoning?.enabled && option.openai_reasoning.effort_options.length) {
    return {
      enabled: true,
      options: option.openai_reasoning.effort_options,
      type: "reasoning_effort",
      label: "Effort",
    };
  }
  if (option.google_thinking?.enabled && option.google_thinking.level_options.length) {
    return {
      enabled: true,
      options: option.google_thinking.level_options,
      type: "thinking_level",
      label: "Thinking",
    };
  }
  if (option.claude_thinking?.enabled && option.claude_thinking.effort_options.length) {
    return {
      enabled: true,
      options: option.claude_thinking.effort_options,
      type: "reasoning_effort",
      label: "Thinking",
    };
  }
  return { enabled: false, options: [], type: null, label: "" };
}

export function Topbar({
  bootstrap,
  selectedModel,
  onSelectModel,
  reasoningEffort,
  onReasoningEffortChange,
  thinkingLevel,
  onThinkingLevelChange,
  onToggleSidebar,
  onOpenDocs,
  onOpenUsage,
}: TopbarProps) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const modelOptionsForSelect = useMemo(
    () =>
      bootstrap.models.groups.map((group) => ({
        label: group.label,
        title: group.label,
        options: group.options.map((opt) => ({ value: opt.id, label: opt.label })),
      })),
    [bootstrap],
  );

  const currentOption = bootstrap.models.options.find((o) => o.id === selectedModel);
  const effort = detectEffortConfig(currentOption);
  const effortValue =
    effort.type === "reasoning_effort"
      ? reasoningEffort || effort.options[0] || ""
      : thinkingLevel || effort.options[0] || "";

  const handleEffortChange = (v: string) => {
    if (effort.type === "reasoning_effort") onReasoningEffortChange(v);
    else if (effort.type === "thinking_level") onThinkingLevelChange(v);
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <Layout.Header
      style={{
        background: "#fff",
        padding: "0 16px",
        height: 48,
        lineHeight: "48px",
        borderBottom: "1px solid #f0f0f0",
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      <Button type="text" icon={<MenuOutlined />} onClick={onToggleSidebar} size="small" />
      <Typography.Text strong style={{ whiteSpace: "nowrap" }}>
        AI 智能助手
      </Typography.Text>

      <Space size={4} style={{ marginLeft: 8 }}>
        <span style={{ color: "rgba(0,0,0,0.65)", fontSize: 13 }}>模型：</span>
        <Select
          style={{ minWidth: 200 }}
          size="small"
          value={selectedModel || undefined}
          onChange={onSelectModel}
          options={modelOptionsForSelect}
        />
        {effort.enabled && (
          <>
            <span style={{ color: "rgba(0,0,0,0.65)", fontSize: 13 }}>{effort.label}：</span>
            <Select
              style={{ minWidth: 90 }}
              size="small"
              value={effortValue}
              onChange={handleEffortChange}
              options={effort.options.map((o) => ({ value: o, label: o }))}
            />
          </>
        )}
      </Space>

      <div style={{ flex: 1 }} />

      <Space size={4}>
        {user?.is_admin && (
          <Button size="small" onClick={() => navigate("/admin")}>后台</Button>
        )}
        <Button size="small" onClick={onOpenDocs}>文档</Button>
        <Button size="small" onClick={() => navigate("/tutorial")}>教程</Button>
        <Button size="small" onClick={onOpenUsage}>用量</Button>
        <Dropdown
          menu={{
            items: [
              { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: handleLogout },
            ],
          }}
        >
          <Avatar icon={<UserOutlined />} style={{ cursor: "pointer", background: "#1677ff" }}>
            {user?.username?.slice(0, 1).toUpperCase()}
          </Avatar>
        </Dropdown>
      </Space>
    </Layout.Header>
  );
}
