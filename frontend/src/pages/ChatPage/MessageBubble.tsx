import { Collapse, Tag, Space, Button, App as AntApp } from "antd";
import { CopyOutlined, DownloadOutlined } from "@ant-design/icons";
import { AuthImage } from "@/components/AuthImage";
import { Markdown } from "@/components/Markdown";
import { apiFetch } from "@/api/client";
import type { Message, MessageAttachment } from "@/types/api";

interface MessageBubbleProps {
  message: Message;
  streaming?: boolean;
  reasoningOverride?: string;
}

async function downloadAttachment(att: MessageAttachment) {
  try {
    const resp = await apiFetch(att.download_url);
    if (!resp.ok) throw new Error("下载失败");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = att.file_name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    /* ignore */
  }
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
              <div key={att.id} style={{ position: "relative", display: "inline-block" }}>
                <AuthImage
                  src={att.preview_url}
                  alt={att.file_name}
                  style={{ maxWidth: 220, maxHeight: 220, borderRadius: 6, display: "block" }}
                />
                <Button
                  size="small"
                  type="text"
                  icon={<DownloadOutlined />}
                  onClick={() => downloadAttachment(att)}
                  style={{
                    position: "absolute",
                    bottom: 4,
                    right: 4,
                    background: "rgba(0,0,0,0.45)",
                    color: "#fff",
                    borderRadius: 4,
                    fontSize: 12,
                  }}
                />
              </div>
            ) : (
              <Tag
                key={att.id}
                color={isUser ? "blue" : "default"}
                style={{ cursor: "pointer" }}
                icon={<DownloadOutlined />}
                onClick={() => downloadAttachment(att)}
              >
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
