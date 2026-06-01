import { useMemo, useState } from "react";
import {
  Layout,
  Button,
  Card,
  Typography,
  Space,
  Tabs,
  Alert,
  Tag,
  Spin,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  CopyOutlined,
  CheckOutlined,
  DownloadOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchClientsConfig } from "@/api/bootstrap";

const { Title, Paragraph, Text, Link: AntLink } = Typography;

const CLAUDE_DOWNLOAD_URL = "https://www.claude.com/product/claude-code";
const CODEX_DOWNLOAD_URL = "https://developers.openai.com/codex/cli";

interface ConfigBlockProps {
  title: string;
  filename: string;
  language: string;
  content: string;
}

function ConfigBlock({ title, filename, language, content }: ConfigBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      message.error("复制失败");
    }
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card
      size="small"
      title={
        <Space size={8}>
          <Text strong>{title}</Text>
          <Tag color="blue">{filename}</Tag>
        </Space>
      }
      extra={
        <Space size={4}>
          <Button
            size="small"
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            onClick={handleCopy}
          >
            {copied ? "已复制" : "复制"}
          </Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload}>
            下载
          </Button>
        </Space>
      }
      style={{ marginBottom: 16 }}
      styles={{ body: { padding: 0 } }}
    >
      <pre
        style={{
          margin: 0,
          padding: "12px 16px",
          background: "#0f172a",
          color: "#e2e8f0",
          borderRadius: "0 0 6px 6px",
          fontSize: 13,
          lineHeight: 1.6,
          overflow: "auto",
          maxHeight: 360,
        }}
      >
        <code data-language={language}>{content}</code>
      </pre>
    </Card>
  );
}

function buildCodexConfigToml(baseUrl: string): string {
  const safeBase = baseUrl || "https://api.openai.com/v1";
  return `# ~/.codex/config.toml
# Codex CLI 配置：使用本站作为 OpenAI 兼容代理

model_provider = "gtp-web"
model = "gpt-5"

[model_providers.gtp-web]
name = "Gtp-Web"
base_url = "${safeBase}"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
`;
}

function buildCodexAuthJson(apiKey: string): string {
  const key = apiKey || "<在此填写你的 OpenAI API Key>";
  return `{
  "OPENAI_API_KEY": "${key}"
}
`;
}

function buildCodexShellEnv(baseUrl: string, apiKey: string): string {
  const safeBase = baseUrl || "https://api.openai.com/v1";
  const key = apiKey || "<your-openai-api-key>";
  return `# 写入 ~/.zshrc 或 ~/.bashrc
export OPENAI_BASE_URL="${safeBase}"
export OPENAI_API_KEY="${key}"
`;
}

function buildClaudeShellEnv(baseUrl: string, apiKey: string): string {
  const safeBase = baseUrl || "https://api.anthropic.com";
  const key = apiKey || "<your-claude-api-key>";
  return `# 写入 ~/.zshrc 或 ~/.bashrc
export ANTHROPIC_BASE_URL="${safeBase}"
export ANTHROPIC_AUTH_TOKEN="${key}"
`;
}

function buildClaudeSettingsJson(baseUrl: string, apiKey: string): string {
  const safeBase = baseUrl || "https://api.anthropic.com";
  const key = apiKey || "<your-claude-api-key>";
  return `{
  "env": {
    "ANTHROPIC_BASE_URL": "${safeBase}",
    "ANTHROPIC_AUTH_TOKEN": "${key}"
  }
}
`;
}

export function ClientsPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["clients-config"],
    queryFn: fetchClientsConfig,
  });

  const codexConfigs = useMemo(() => {
    if (!data) return null;
    return {
      configToml: buildCodexConfigToml(data.openai.base_url),
      authJson: buildCodexAuthJson(data.openai.api_key),
      shellEnv: buildCodexShellEnv(data.openai.base_url, data.openai.api_key),
    };
  }, [data]);

  const claudeConfigs = useMemo(() => {
    if (!data) return null;
    return {
      shellEnv: buildClaudeShellEnv(data.claude.base_url, data.claude.api_key),
      settingsJson: buildClaudeSettingsJson(data.claude.base_url, data.claude.api_key),
    };
  }, [data]);

  const hasOpenaiKey = !!data?.openai.api_key;
  const hasClaudeKey = !!data?.claude.api_key;

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
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/chat")}>
          返回聊天
        </Button>
        <Title level={4} style={{ margin: "0 0 0 16px" }}>
          客户端配置
        </Title>
      </Layout.Header>

      <Layout.Content style={{ padding: 24, background: "#f5f5f5" }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          {isLoading ? (
            <Card>
              <Spin />
            </Card>
          ) : error ? (
            <Alert type="error" message="加载配置失败" description={String(error)} showIcon />
          ) : (
            <Tabs
              defaultActiveKey="claude"
              type="card"
              items={[
                {
                  key: "claude",
                  label: "Claude Code",
                  children: (
                    <Card>
                      <Title level={4}>Claude Code 是什么</Title>
                      <Paragraph>
                        Claude Code 是 Anthropic 出品的智能编程助手，可以通过命令行直接在你的项目目录中读写代码、运行命令、调试问题。它支持环境变量切换 API 端点，所以可以接入本站作为代理。
                      </Paragraph>

                      <Title level={5}>第一步：下载并安装</Title>
                      <Paragraph>
                        <Space>
                          <Button
                            type="primary"
                            icon={<LinkOutlined />}
                            href={CLAUDE_DOWNLOAD_URL}
                            target="_blank"
                            rel="noreferrer"
                          >
                            打开 Claude Code 下载页
                          </Button>
                          <Text type="secondary">
                            或直接在终端运行 <Text code>npm install -g @anthropic-ai/claude-code</Text>
                          </Text>
                        </Space>
                      </Paragraph>

                      <Title level={5}>第二步：配置 API</Title>
                      <Paragraph>
                        Claude Code 通过环境变量
                        <Text code>ANTHROPIC_BASE_URL</Text> 和
                        <Text code>ANTHROPIC_AUTH_TOKEN</Text>
                        切换接入端点。任选下面一种方式即可。
                      </Paragraph>

                      {!hasClaudeKey && (
                        <Alert
                          type="warning"
                          showIcon
                          style={{ marginBottom: 16 }}
                          message="你的账号尚未配置 Claude API Key"
                          description={
                            <span>
                              示例配置中 key 字段为空，请联系管理员在用户管理中配置，或自行替换为可用 Key。
                            </span>
                          }
                        />
                      )}

                      <ConfigBlock
                        title="方式 A：Shell 环境变量（推荐）"
                        filename="claude-code.env.sh"
                        language="bash"
                        content={claudeConfigs?.shellEnv ?? ""}
                      />

                      <ConfigBlock
                        title="方式 B：Claude Code settings.json"
                        filename="settings.json"
                        language="json"
                        content={claudeConfigs?.settingsJson ?? ""}
                      />

                      <Title level={5}>第三步：启动</Title>
                      <Paragraph>
                        在任意项目目录执行 <Text code>claude</Text>
                        即可进入交互式会话；首次启动可能需要确认登录方式，选择
                        <Text strong> API Key </Text>
                        即可。详细文档见
                        <AntLink href={CLAUDE_DOWNLOAD_URL} target="_blank" rel="noreferrer">
                          官方页面
                        </AntLink>
                        。
                      </Paragraph>
                    </Card>
                  ),
                },
                {
                  key: "codex",
                  label: "Codex",
                  children: (
                    <Card>
                      <Title level={4}>Codex 是什么</Title>
                      <Paragraph>
                        Codex 是 OpenAI 推出的命令行 / 桌面端智能编程助手，使用 OpenAI Responses API。它通过
                        <Text code>~/.codex/config.toml</Text>
                        指定 model provider，可以指向兼容 OpenAI 的代理（也就是本站）。
                      </Paragraph>

                      <Title level={5}>第一步：下载并安装</Title>
                      <Paragraph>
                        <Space>
                          <Button
                            type="primary"
                            icon={<LinkOutlined />}
                            href={CODEX_DOWNLOAD_URL}
                            target="_blank"
                            rel="noreferrer"
                          >
                            打开 Codex 下载页
                          </Button>
                          <Text type="secondary">
                            或直接在终端运行 <Text code>npm install -g @openai/codex</Text>
                          </Text>
                        </Space>
                      </Paragraph>

                      <Title level={5}>第二步：配置 API</Title>
                      <Paragraph>
                        把下面的
                        <Text code>config.toml</Text>
                        放到
                        <Text code>~/.codex/config.toml</Text>
                        ，然后通过环境变量或
                        <Text code>~/.codex/auth.json</Text>
                        提供 API Key。
                      </Paragraph>

                      {!hasOpenaiKey && (
                        <Alert
                          type="warning"
                          showIcon
                          style={{ marginBottom: 16 }}
                          message="你的账号尚未配置 OpenAI API Key"
                          description={
                            <span>
                              示例配置中 key 字段为空，请联系管理员在用户管理中配置，或自行替换为可用 Key。
                            </span>
                          }
                        />
                      )}

                      <ConfigBlock
                        title="主配置：~/.codex/config.toml"
                        filename="config.toml"
                        language="toml"
                        content={codexConfigs?.configToml ?? ""}
                      />

                      <ConfigBlock
                        title="方式 A：Shell 环境变量（推荐）"
                        filename="codex.env.sh"
                        language="bash"
                        content={codexConfigs?.shellEnv ?? ""}
                      />

                      <ConfigBlock
                        title="方式 B：~/.codex/auth.json"
                        filename="auth.json"
                        language="json"
                        content={codexConfigs?.authJson ?? ""}
                      />

                      <Title level={5}>第三步：启动</Title>
                      <Paragraph>
                        在任意项目目录执行 <Text code>codex</Text>
                        进入交互式会话。如需切换模型，使用
                        <Text code>codex --model gpt-5</Text>
                        或在
                        <Text code>config.toml</Text>
                        中修改
                        <Text code>model</Text>
                        字段。详细文档见
                        <AntLink href={CODEX_DOWNLOAD_URL} target="_blank" rel="noreferrer">
                          官方页面
                        </AntLink>
                        。
                      </Paragraph>
                    </Card>
                  ),
                },
              ]}
            />
          )}
        </div>
      </Layout.Content>
    </Layout>
  );
}
