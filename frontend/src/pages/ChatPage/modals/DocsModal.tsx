import { Modal, Table, Button, message } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { listDocuments, downloadDocument } from "@/api/documents";
import type { DocumentMeta } from "@/types/api";

interface DocsModalProps {
  open: boolean;
  onClose: () => void;
}

export function DocsModal({ open, onClose }: DocsModalProps) {
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
    enabled: open,
  });

  const handleDownload = async (doc: DocumentMeta) => {
    try {
      await downloadDocument(doc);
    } catch (err) {
      message.error((err as Error).message);
    }
  };

  return (
    <Modal title="文档中心" open={open} onCancel={onClose} footer={null} width={760}>
      <Table<DocumentMeta>
        rowKey="id"
        dataSource={docs}
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: "标题", dataIndex: "title" },
          { title: "分类", dataIndex: "category", width: 100 },
          { title: "上传者", dataIndex: "uploaded_by", width: 100 },
          { title: "时间", dataIndex: "updated_at", width: 160 },
          {
            title: "操作",
            width: 120,
            render: (_, doc) => (
              <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(doc)}>
                下载
              </Button>
            ),
          },
        ]}
      />
    </Modal>
  );
}
