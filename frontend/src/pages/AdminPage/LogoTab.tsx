import { useState } from "react";
import { Upload, Button, Space, message, Popconfirm, Card, Empty, Spin } from "antd";
import { UploadOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson, apiFetch } from "@/api/client";

interface LogoInfo {
  ok: true;
  has_logo: boolean;
  url: string | null;
}

async function fetchLogoInfo(): Promise<LogoInfo> {
  return apiJson<LogoInfo>("/api/admin/logo");
}

export function LogoTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-logo"],
    queryFn: fetchLogoInfo,
  });
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const cacheBuster = useState(() => Date.now())[0];
  const [cb, setCb] = useState(cacheBuster);

  const handleUpload = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      message.error("仅支持图片文件");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      message.error("Logo 不能超过 5MB");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await apiFetch("/api/admin/logo", { method: "POST", body: form });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        throw new Error((d as { error?: string }).error ?? "上传失败");
      }
      message.success("Logo 已更新");
      setCb(Date.now());
      qc.invalidateQueries({ queryKey: ["admin-logo"] });
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await apiJson("/api/admin/logo", { method: "DELETE" });
      message.success("Logo 已删除，将使用默认 Logo");
      setCb(Date.now());
      qc.invalidateQueries({ queryKey: ["admin-logo"] });
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  if (isLoading) return <Spin />;

  return (
    <Card title="Logo 管理" style={{ maxWidth: 480 }}>
      <div style={{ marginBottom: 16, textAlign: "center" }}>
        {data?.has_logo ? (
          <img
            src={`/api/logo?_=${cb}`}
            alt="当前 Logo"
            style={{ maxWidth: 200, maxHeight: 200, borderRadius: 8, border: "1px solid #f0f0f0" }}
          />
        ) : (
          <Empty description="暂未上传自定义 Logo，使用默认 Logo" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>

      <Space>
        <Upload
          showUploadList={false}
          accept="image/*"
          beforeUpload={(file) => {
            handleUpload(file as File);
            return false;
          }}
        >
          <Button icon={<UploadOutlined />} loading={uploading} type="primary">
            {data?.has_logo ? "更换 Logo" : "上传 Logo"}
          </Button>
        </Upload>
        {data?.has_logo && (
          <Popconfirm title="确认删除 Logo？" description="删除后将使用默认 Logo" onConfirm={handleDelete}>
            <Button danger icon={<DeleteOutlined />} loading={deleting}>
              删除
            </Button>
          </Popconfirm>
        )}
        <Button icon={<ReloadOutlined />} onClick={() => { setCb(Date.now()); qc.invalidateQueries({ queryKey: ["admin-logo"] }); }}>
          刷新
        </Button>
      </Space>

      <div style={{ marginTop: 12, color: "#999", fontSize: 12 }}>
        建议尺寸：128×128 像素，支持 PNG / JPG / SVG，最大 5MB
      </div>
    </Card>
  );
}
