import { useState } from "react";
import { Button, message } from "antd";
import { CopyOutlined, CheckOutlined } from "@ant-design/icons";

interface CodeBlockProps {
  className?: string;
  children?: React.ReactNode;
  // ReactMarkdown 在 inline 代码时传入此 prop
  inline?: boolean;
}

export function CodeBlock({ className, children, inline }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const text = String(children ?? "").replace(/\n$/, "");

  if (inline || !text.includes("\n")) {
    return <code className={className}>{children}</code>;
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      message.error("复制失败");
    }
  };

  return (
    <div className="code-block-wrapper">
      <Button
        size="small"
        type="text"
        className="code-copy-btn"
        icon={copied ? <CheckOutlined /> : <CopyOutlined />}
        onClick={handleCopy}
      >
        {copied ? "已复制" : "复制"}
      </Button>
      <pre>
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}
