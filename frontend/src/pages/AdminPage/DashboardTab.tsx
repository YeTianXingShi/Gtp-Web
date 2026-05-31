import { Card, Row, Col, Statistic, Spin } from "antd";
import { UserOutlined, MessageOutlined, DollarOutlined, FileTextOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/admin";

export function DashboardTab() {
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: fetchDashboard });

  if (isLoading || !data) return <Spin />;

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card>
          <Statistic title="注册用户" value={data.user_count} prefix={<UserOutlined />} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="会话总数" value={data.conversation_count} prefix={<MessageOutlined />} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="今日 Token" value={data.today_tokens} prefix={<DollarOutlined />} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="文档数量" value={data.document_count} prefix={<FileTextOutlined />} />
        </Card>
      </Col>
    </Row>
  );
}
