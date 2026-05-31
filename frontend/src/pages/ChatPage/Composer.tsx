import { Input, Button, Tag, Space, Upload, message } from "antd";
import { PaperClipOutlined, SendOutlined, StopOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useRef, useState } from "react";
import { useChatStreamContext } from "./streamContext";
import type { BootstrapData } from "@/types/api";
import { useCreateConversation } from "@/hooks/useConversations";
import { useChatStore } from "@/stores/chatStore";

interface ComposerProps {
  bootstrap: BootstrapData;
  conversationId: number | null;
  selectedModel: string;
  reasoningEffort: string;
  thinkingLevel: string;
}

export function Composer({
  bootstrap,
  conversationId,
  selectedModel,
  reasoningEffort,
  thinkingLevel,
}: ComposerProps) {
  const stream = useChatStreamContext();
  const setCurrentId = useChatStore((s) => s.setCurrentConversation);
  const createMutation = useCreateConversation();
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<UploadFile[]>([]);
  const fileIdCounter = useRef(0);

  // 流结束后清空输入
  const wasActive = useRefValue(stream.active);
  useEffect(() => {
    if (wasActive && !stream.active && !stream.error) {
      setContent("");
      setFiles([]);
    }
  }, [stream.active, stream.error, wasActive]);

  const addFiles = (newFiles: File[]) => {
    const maxMb = bootstrap.attachments.max_upload_mb;
    const maxCount = bootstrap.attachments.max_per_message;
    const toAdd: UploadFile[] = [];
    for (const f of newFiles) {
      if (files.length + toAdd.length >= maxCount) {
        message.error(`最多上传 ${maxCount} 个附件`);
        break;
      }
      if (f.size / 1024 / 1024 > maxMb) {
        message.error(`${f.name} 超过 ${maxMb}MB 限制`);
        continue;
      }
      fileIdCounter.current += 1;
      toAdd.push({
        uid: `paste-${fileIdCounter.current}`,
        name: f.name,
        originFileObj: f as never,
        status: "done",
      });
    }
    if (toAdd.length > 0) {
      setFiles((prev) => [...prev, ...toAdd].slice(0, maxCount));
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const pastedFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) pastedFiles.push(file);
      }
    }
    if (pastedFiles.length > 0) {
      e.preventDefault();
      addFiles(pastedFiles);
    }
  };

  const handleSend = async () => {
    const text = content.trim();
    if (!text && files.length === 0) {
      message.warning("消息内容和附件不能同时为空");
      return;
    }
    if (!selectedModel) {
      message.warning("请先选择模型");
      return;
    }

    let convId = conversationId;
    if (convId == null) {
      const conv = await createMutation.mutateAsync({ model: selectedModel });
      convId = conv.id;
      setCurrentId(convId);
    }

    const realFiles = files
      .map((f) => (f.originFileObj ?? null) as File | null)
      .filter((f): f is File => Boolean(f));

    const fileNames = realFiles.map((f) => f.name);

    stream.send({
      conversationId: convId,
      content: text,
      files: realFiles,
      model: selectedModel,
      reasoningEffort,
      thinkingLevel,
    }, fileNames);
  };

  const handleStop = () => {
    stream.abort();
  };

  const beforeUpload = (file: File): boolean => {
    const sizeMb = file.size / 1024 / 1024;
    if (sizeMb > bootstrap.attachments.max_upload_mb) {
      message.error(`${file.name} 超过 ${bootstrap.attachments.max_upload_mb}MB 限制`);
      return false;
    }
    if (files.length >= bootstrap.attachments.max_per_message) {
      message.error(`最多上传 ${bootstrap.attachments.max_per_message} 个附件`);
      return false;
    }
    return false; // 阻止 AntD 自动上传，由我们在 send 时手动 POST
  };

  const handleFileChange = (info: { fileList: UploadFile[] }) => {
    setFiles(info.fileList.slice(0, bootstrap.attachments.max_per_message));
  };

  return (
    <div
      style={{
        borderTop: "1px solid #f0f0f0",
        background: "#fff",
        padding: "12px 24px",
      }}
    >
      <Space style={{ marginBottom: 8 }} wrap>
        <Upload
          multiple
          showUploadList={false}
          beforeUpload={beforeUpload}
          fileList={files}
          onChange={handleFileChange}
        >
          <Button icon={<PaperClipOutlined />} size="small">
            添加文件
          </Button>
        </Upload>
        {files.map((f) => (
          <Tag
            key={f.uid}
            closable
            onClose={() => setFiles((prev) => prev.filter((x) => x.uid !== f.uid))}
          >
            {f.name}
          </Tag>
        ))}
        <span style={{ color: "#999", fontSize: 12 }}>
          ≤{bootstrap.attachments.max_upload_mb}MB ×{bootstrap.attachments.max_per_message}，支持粘贴图片/文件
        </span>
      </Space>

      <Input.TextArea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="输入你的问题。Enter 发送，Shift+Enter 换行，可粘贴图片/文件"
        autoSize={{ minRows: 3, maxRows: 8 }}
        onPaste={handlePaste}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault();
            if (!stream.active) handleSend();
          }
        }}
      />

      <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end", gap: 8 }}>
        {stream.active ? (
          <Button danger icon={<StopOutlined />} onClick={handleStop}>
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={createMutation.isPending}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
}

// 小工具：返回上一个 render 的值，用于检测变化
function useRefValue<T>(value: T): T {
  const ref = useRef(value);
  const prev = ref.current;
  ref.current = value;
  return prev;
}
