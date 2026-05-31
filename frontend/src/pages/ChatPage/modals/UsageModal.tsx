import { Modal, Spin, Empty, Statistic, Row, Col, Table } from "antd";
import { useQuery } from "@tanstack/react-query";
import { fetchMyUsage } from "@/api/conversation";

interface UsageModalProps {
  open: boolean;
  onClose: () => void;
}

interface UsageRow {
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
}

interface UsageData {
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_tokens?: number;
  by_model?: UsageRow[];
}

export function UsageModal({ open, onClose }: UsageModalProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["my-usage"],
    queryFn: fetchMyUsage,
    enabled: open,
  });

  return (
    <Modal title="我的用量" open={open} onCancel={onClose} footer={null} width={680}>
      {isLoading ? (
        <Spin />
      ) : !data ? (
        <Empty description="暂无数据" />
      ) : (
        <UsageContent usage={data as UsageData} />
      )}
    </Modal>
  );
}

function UsageContent({ usage }: { usage: UsageData }) {
  const byModel = usage.by_model ?? [];
  return (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Statistic title="输入 Token" value={usage.total_input_tokens ?? 0} />
        </Col>
        <Col span={8}>
          <Statistic title="输出 Token" value={usage.total_output_tokens ?? 0} />
        </Col>
        <Col span={8}>
          <Statistic title="合计 Token" value={usage.total_tokens ?? 0} />
        </Col>
      </Row>
      <Table<UsageRow>
        rowKey={(row) => String(row.model)}
        dataSource={byModel}
        size="small"
        pagination={false}
        columns={[
          { title: "模型", dataIndex: "model" },
          { title: "输入", dataIndex: "input_tokens", width: 120 },
          { title: "输出", dataIndex: "output_tokens", width: 120 },
          { title: "合计", dataIndex: "total_tokens", width: 120 },
        ]}
      />
    </>
  );
}
