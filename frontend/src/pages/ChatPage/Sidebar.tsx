import { Layout, Input, Button, List, Popconfirm, Dropdown, Modal, Form, Tooltip, message } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ExportOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import {
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useUpdateConversation,
} from "@/hooks/useConversations";
import { useChatStore } from "@/stores/chatStore";
import { exportConversation } from "@/api/conversation";
import type { BootstrapData, Conversation } from "@/types/api";

interface SidebarProps {
  collapsed: boolean;
  bootstrap: BootstrapData;
  selectedModel: string;
}

export function Sidebar({ collapsed, bootstrap, selectedModel }: SidebarProps) {
  const searchKeyword = useChatStore((s) => s.searchKeyword);
  const setSearchKeyword = useChatStore((s) => s.setSearchKeyword);
  const currentId = useChatStore((s) => s.currentConversationId);
  const setCurrentId = useChatStore((s) => s.setCurrentConversation);

  const { data: conversations = [], isLoading } = useConversations(searchKeyword);
  const createMutation = useCreateConversation();
  const deleteMutation = useDeleteConversation();
  const updateMutation = useUpdateConversation();

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    if (currentId == null && conversations.length > 0) {
      setCurrentId(conversations[0].id);
    }
  }, [conversations, currentId, setCurrentId]);

  const currentConv = conversations.find((c) => c.id === currentId);

  const handleNew = async () => {
    if (!selectedModel) {
      message.warning("请先选择模型");
      return;
    }
    const conv = await createMutation.mutateAsync({ model: selectedModel });
    setCurrentId(conv.id);
  };

  const handleRename = async () => {
    if (!currentConv) return;
    const trimmed = renameValue.trim();
    if (!trimmed) return;
    await updateMutation.mutateAsync([currentConv.id, { title: trimmed }]);
    setRenameOpen(false);
    message.success("已重命名");
  };

  const handleDelete = async () => {
    if (!currentConv) return;
    await deleteMutation.mutateAsync(currentConv.id);
    setCurrentId(null);
    message.success("已删除");
  };

  const handleExport = async (format: "json" | "txt" | "md") => {
    if (!currentConv) return;
    try {
      await exportConversation(currentConv.id, format);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  return (
    <Layout.Sider
      width={260}
      collapsedWidth={0}
      collapsed={collapsed}
      collapsible
      trigger={null}
      style={{
        background: "#fff",
        borderRight: "1px solid #f0f0f0",
        overflow: "hidden",
      }}
    >
      <div className="chat-sidebar">
        <div className="chat-sidebar-actions" style={{ padding: "12px 12px 0" }}>
          <Input.Search
            allowClear
            placeholder="搜索会话..."
            defaultValue={searchKeyword}
            onSearch={setSearchKeyword}
            style={{ marginBottom: 8 }}
            size="small"
          />
          <div style={{ display: "flex", gap: 4 }}>
            <Button icon={<PlusOutlined />} type="primary" size="small" onClick={handleNew} style={{ flex: 1 }}>
              新对话
            </Button>
            <Tooltip title="重命名">
              <Button
                icon={<EditOutlined />}
                size="small"
                disabled={!currentConv}
                onClick={() => {
                  if (currentConv) {
                    setRenameValue(currentConv.title);
                    setRenameOpen(true);
                  }
                }}
              />
            </Tooltip>
            <Dropdown
              disabled={!currentConv}
              menu={{
                items: [
                  { key: "json", label: "JSON", onClick: () => handleExport("json") },
                  { key: "txt", label: "TXT", onClick: () => handleExport("txt") },
                  { key: "md", label: "Markdown", onClick: () => handleExport("md") },
                ],
              }}
            >
              <Tooltip title="导出">
                <Button icon={<ExportOutlined />} size="small" disabled={!currentConv} />
              </Tooltip>
            </Dropdown>
            <Popconfirm
              title="删除当前会话？"
              description="删除后不可恢复"
              okText="确认"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              disabled={!currentConv}
              onConfirm={handleDelete}
            >
              <Tooltip title="删除">
                <Button danger icon={<DeleteOutlined />} size="small" disabled={!currentConv} />
              </Tooltip>
            </Popconfirm>
          </div>
        </div>

        <div className="chat-sidebar-list" style={{ padding: "4px 12px 12px" }}>
          <List
            loading={isLoading}
            dataSource={conversations}
            split={false}
            renderItem={(conv: Conversation) => (
              <List.Item
                key={conv.id}
                style={{
                  cursor: "pointer",
                  padding: "8px 10px",
                  borderRadius: 6,
                  background: conv.id === currentId ? "#e6f4ff" : undefined,
                  border: "none",
                }}
                onClick={() => setCurrentId(conv.id)}
              >
                <List.Item.Meta
                  title={
                    <div
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontSize: 13,
                        fontWeight: conv.id === currentId ? 600 : 400,
                      }}
                    >
                      {conv.title}
                    </div>
                  }
                  description={
                    <div style={{ fontSize: 11, color: "#999" }}>
                      {bootstrap.models.options.find((o) => o.id === conv.model)?.label || conv.model}
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      </div>

      <Modal
        title="重命名会话"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={handleRename}
        confirmLoading={updateMutation.isPending}
      >
        <Form layout="vertical">
          <Form.Item label="名称">
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              maxLength={60}
              showCount
              autoFocus
            />
          </Form.Item>
        </Form>
      </Modal>
    </Layout.Sider>
  );
}
