import { Layout } from "antd";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBootstrap } from "@/hooks/useBootstrap";
import { useChatStream } from "@/hooks/useChatStream";
import { useConversationMessages } from "@/hooks/useConversations";
import { useChatStore } from "@/stores/chatStore";
import { Topbar } from "./Topbar";
import { Sidebar } from "./Sidebar";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { DocsModal } from "./modals/DocsModal";
import { UsageModal } from "./modals/UsageModal";
import { ChatStreamContext } from "./streamContext";

export function ChatPage() {
  const { data: bootstrap, isLoading } = useBootstrap();
  const currentConversationId = useChatStore((s) => s.currentConversationId);
  const [docsOpen, setDocsOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [reasoningEffort, setReasoningEffort] = useState<string>("");
  const [thinkingLevel, setThinkingLevel] = useState<string>("");

  const queryClient = useQueryClient();

  const refreshAfterStream = () => {
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
    if (currentConversationId != null) {
      queryClient.invalidateQueries({
        queryKey: ["conversation-messages", currentConversationId],
      });
    }
  };

  const stream = useChatStream({
    onDone: refreshAfterStream,
    onError: refreshAfterStream,
  });

  useEffect(() => {
    if (bootstrap && !selectedModel) {
      setSelectedModel(bootstrap.models.default || bootstrap.models.options[0]?.id || "");
    }
  }, [bootstrap, selectedModel]);

  // 切换会话时清理上一次流状态
  useEffect(() => {
    stream.abort();
    stream.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentConversationId]);

  // 加载当前会话的消息（同时拿到会话的 model/effort/level）
  const { data: conversationDetail } = useConversationMessages(currentConversationId);

  // 切换会话时同步模型和参数到 Topbar
  useEffect(() => {
    if (!conversationDetail || !bootstrap) return;
    const convModel = conversationDetail.model;
    if (convModel && bootstrap.models.options.some((o) => o.id === convModel)) {
      setSelectedModel(convModel);
    }
    setReasoningEffort(conversationDetail.reasoning_effort || "");
    setThinkingLevel(conversationDetail.thinking_level || "");
  }, [conversationDetail, bootstrap]);

  if (isLoading || !bootstrap) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        加载中...
      </div>
    );
  }

  return (
    <ChatStreamContext.Provider value={stream}>
      <Layout className="chat-layout" style={{ height: "100vh", overflow: "hidden" }}>
        <Topbar
          bootstrap={bootstrap}
          selectedModel={selectedModel}
          onSelectModel={(id) => {
            setSelectedModel(id);
            setReasoningEffort("");
            setThinkingLevel("");
          }}
          reasoningEffort={reasoningEffort}
          onReasoningEffortChange={setReasoningEffort}
          thinkingLevel={thinkingLevel}
          onThinkingLevelChange={setThinkingLevel}
          onToggleSidebar={() => setCollapsed((v) => !v)}
          onOpenDocs={() => setDocsOpen(true)}
          onOpenUsage={() => setUsageOpen(true)}
        />

        <Layout style={{ overflow: "hidden" }}>
          <Sidebar collapsed={collapsed} bootstrap={bootstrap} selectedModel={selectedModel} />

          <Layout.Content style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <MessageList conversationId={currentConversationId} />
            <Composer
              bootstrap={bootstrap}
              conversationId={currentConversationId}
              selectedModel={selectedModel}
              reasoningEffort={reasoningEffort}
              thinkingLevel={thinkingLevel}
            />
          </Layout.Content>
        </Layout>

        <DocsModal open={docsOpen} onClose={() => setDocsOpen(false)} />
        <UsageModal open={usageOpen} onClose={() => setUsageOpen(false)} />
      </Layout>
    </ChatStreamContext.Provider>
  );
}
