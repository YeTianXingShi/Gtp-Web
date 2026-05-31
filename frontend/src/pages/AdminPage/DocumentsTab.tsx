import { useState } from "react";
import { Button, Modal, Form, Input, Upload, Table, Space, Popconfirm, message } from "antd";
import { PlusOutlined, DeleteOutlined, DownloadOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  downloadDocument,
} from "@/api/documents";
import type { DocumentMeta } from "@/types/api";

export function DocumentsTab() {
  const qc = useQueryClient();
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<UploadFile | null>(null);

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      message.success("已上传");
      setOpen(false);
      setFile(null);
    },
    onError: (e) => message.error((e as Error).message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      message.success("已删除");
    },
    onError: (e) => message.error((e as Error).message),
  });

  const handleUpload = (values: { title?: string; category?: string }) => {
    const f = file?.originFileObj;
    if (!f) {
      message.warning("请选择文件");
      return;
    }
    uploadMutation.mutate({ file: f as File, title: values.title, category: values.category });
  };

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          上传文档
        </Button>
      </Space>

      <Table<DocumentMeta>
        rowKey="id"
        dataSource={docs}
        loading={isLoading}
        pagination={false}
        columns={[
          { title: "标题", dataIndex: "title" },
          { title: "分类", dataIndex: "category", width: 120 },
          { title: "文件名", dataIndex: "file_name" },
          { title: "上传者", dataIndex: "uploaded_by", width: 120 },
          { title: "时间", dataIndex: "updated_at", width: 160 },
          {
            title: "操作",
            width: 200,
            render: (_, doc) => (
              <Space>
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() => downloadDocument(doc).catch((e) => message.error(e.message))}
                >
                  下载
                </Button>
                <Popconfirm
                  title={`删除 ${doc.title}？`}
                  okText="确认删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => deleteMutation.mutate(doc.id)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="上传文档"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form layout="vertical" onFinish={handleUpload} requiredMark={false}>
          <Form.Item name="title" label="标题（留空则用文件名）">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="分类（留空则归入未分类）">
            <Input placeholder="如：SOP、通知" />
          </Form.Item>
          <Form.Item label="文件" required>
            <Upload
              maxCount={1}
              beforeUpload={() => false}
              fileList={file ? [file] : []}
              onChange={(info) => setFile(info.fileList[0] ?? null)}
              onRemove={() => setFile(null)}
            >
              <Button>选择文件</Button>
            </Upload>
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={uploadMutation.isPending}
            block
          >
            上传
          </Button>
        </Form>
      </Modal>
    </>
  );
}
