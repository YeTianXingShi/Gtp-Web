import { useEffect, useRef } from "react";
import { Empty, Button, Space, message as toast } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useConversationMessages } from "@/hooks/useConversations";
import { useChatStreamContext } from "./streamContext";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/types/api";

interface MessageListProps {
  conversationId: number | null;
}

export function MessageList({ conversationId }: MessageListProps) {
  const { data, isLoading, refetch } = useConversationMessages(conversationId);
  const stream = useChatStreamContext();
  const containerRef = useRef<HTMLDivElement>(null);

  // 自动滚到底部
  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [data?.messages?.length, stream.reply, stream.reasoning, stream.pendingUserMessage]);

  // 流式完成后刷新消息列表（拿到落库的最终消息 + 助手回复）
  useEffect(() => {
    if (!stream.active && stream.reply && conversationId != null) {
      refetch();
    }
  }, [stream.active, stream.reply, conversationId, refetch]);

  if (conversationId == null) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Empty description="选择或新建一个对话开始" />
      </div>
    );
  }

  if (isLoading) {
    return <div style={{ padding: 24 }}>加载消息中...</div>;
  }

  const messages = data?.messages ?? [];

  // 流式中的乐观消息：附加在已落库消息之后
  const showStreaming = stream.active || stream.error;
  const pendingText = stream.pendingUserMessage ?? "";
  const pendingFileLines = stream.pendingFileNames.map((n) => `[附件] ${n}`).join("\n");
  const pendingDisplay = [pendingText, pendingFileLines].filter(Boolean).join("\n");
  const pendingUserBubble: Message | null = pendingDisplay
    ? {
        id: -2,
        role: "user",
        content: pendingDisplay,
        reasoning: "",
        status: "complete",
        created_at: new Date().toISOString(),
        attachments: [],
      }
    : null;
  const streamingBubble: Message | null = showStreaming
    ? {
        id: -1,
        role: "assistant",
        content: stream.reply,
        reasoning: stream.reasoning,
        status: stream.error ? "incomplete" : "complete",
        created_at: new Date().toISOString(),
        attachments: [],
      }
    : null;

  const handleRetry = () => {
    if (conversationId != null) {
      stream.retry(conversationId);
    } else {
      toast.warning("没有可重试的会话");
    }
  };

  return (
    <div
      ref={containerRef}
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "16px 24px",
        display: "flex",
        flexDirection: "column",
        background: "#f5f5f5",
      }}
    >
      {messages.length === 0 && !showStreaming && (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Empty description="对话开始" />
        </div>
      )}

      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}

      {pendingUserBubble && (
        <MessageBubble message={pendingUserBubble} />
      )}

      {streamingBubble && (
        <MessageBubble message={streamingBubble} streaming={stream.active} />
      )}

      {stream.error && (
        <div className="message-bubble system" style={{ marginTop: 8 }}>
          <Space>
            <span style={{ color: "#cf1322" }}>错误：{stream.error}</span>
            <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
              重试
            </Button>
          </Space>
        </div>
      )}

      {/* 末尾尾巴消息（已 incomplete 但没在流式态）：提供重试按钮 */}
      {!showStreaming &&
        messages.length > 0 &&
        messages[messages.length - 1].role === "assistant" &&
        messages[messages.length - 1].status === "incomplete" && (
          <div style={{ margin: "8px 0", textAlign: "center" }}>
            <Button icon={<ReloadOutlined />} onClick={handleRetry}>
              重试上一条
            </Button>
          </div>
        )}
    </div>
  );
}
