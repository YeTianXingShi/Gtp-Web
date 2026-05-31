import { Collapse, Tag, Space, Button, App as AntApp } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import { AuthImage } from "@/components/AuthImage";
import { Markdown } from "@/components/Markdown";
import type { Message } from "@/types/api";

interface MessageBubbleProps {
  message: Message;
  // 流式状态：当 streaming=true 表示这条助手气泡正在接收
  streaming?: boolean;
  reasoningOverride?: string;
}

export function MessageBubble({ message, streaming, reasoningOverride }: MessageBubbleProps) {
  const { message: messageApi } = AntApp.useApp();
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const reasoningText = reasoningOverride ?? message.reasoning;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      messageApi.success("已复制");
    } catch {
      /* ignore */
    }
  };

  return (
    <div className={`message-bubble ${message.role}`}>
      {reasoningText && (
        <Collapse
          size="small"
          ghost
          items={[
            {
              key: "r",
              label: <span style={{ fontSize: 12, color: "#666" }}>思考摘要</span>,
              children: (
                <div className="reasoning-block">
                  <Markdown source={reasoningText} />
                </div>
              ),
            },
          ]}
        />
      )}

      {message.attachments?.length > 0 && (
        <Space wrap style={{ marginBottom: 6 }}>
          {message.attachments.map((att) =>
            att.is_image && att.preview_url ? (
              <AuthImage
                key={att.id}
                src={att.preview_url}
                alt={att.file_name}
                style={{ maxWidth: 220, maxHeight: 220, borderRadius: 6 }}
              />
            ) : (
              <Tag key={att.id} color={isUser ? "blue" : "default"}>
                {att.file_name}
              </Tag>
            ),
          )}
        </Space>
      )}

      {message.content && <Markdown source={message.content} />}

      {streaming && !message.content && (
        <span style={{ opacity: 0.6 }}>正在生成…</span>
      )}

      {!isUser && !isSystem && message.content && !streaming && (
        <div className="message-meta">
          <Button size="small" type="text" icon={<CopyOutlined />} onClick={handleCopy}>
            复制
          </Button>
          {message.status === "incomplete" && <span style={{ color: "#fa8c16" }}>未完成</span>}
        </div>
      )}
    </div>
  );
}
