import { Layout, Button, Card, Typography, Empty, Spin } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchTutorial } from "@/api/bootstrap";
import { Markdown } from "@/components/Markdown";

export function TutorialPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["tutorial"],
    queryFn: fetchTutorial,
  });

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Header
        style={{
          background: "#fff",
          padding: "0 24px",
          height: 56,
          lineHeight: "56px",
          borderBottom: "1px solid #f0f0f0",
          display: "flex",
          alignItems: "center",
        }}
      >
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/chat")}>
          返回聊天
        </Button>
        <Typography.Title level={4} style={{ margin: "0 0 0 16px" }}>
          使用教程
        </Typography.Title>
      </Layout.Header>

      <Layout.Content style={{ padding: 24, background: "#f5f5f5" }}>
        <Card style={{ maxWidth: 920, margin: "0 auto" }}>
          {isLoading ? (
            <Spin />
          ) : !data?.exists || !data.content ? (
            <Empty description="教程内容暂未配置" />
          ) : (
            <Markdown source={data.content} />
          )}
        </Card>
      </Layout.Content>
    </Layout>
  );
}
