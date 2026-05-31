import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Form, Input, Button, Alert, Typography } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { login } from "@/api/auth";
import { useAuthStore } from "@/stores/authStore";

interface LoginForm {
  username: string;
  password: string;
}

export function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);

  if (accessToken && user) {
    // 已登录的用户访问 /login 直接跳走
    navigate(user.is_admin ? "/admin" : "/chat", { replace: true });
  }

  const onFinish = async (values: LoginForm) => {
    setError(null);
    setLoading(true);
    try {
      const data = await login(values.username.trim(), values.password);
      navigate(data.user.is_admin ? "/admin" : "/chat", { replace: true });
    } catch (err) {
      setError((err as Error).message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #f0f4ff 0%, #e6f7ff 100%)",
      }}
    >
      <Card
        style={{ width: 380, boxShadow: "0 4px 20px rgba(0,0,0,0.08)" }}
        styles={{ body: { padding: "32px 28px" } }}
      >
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <img src="/api/logo" alt="Logo" style={{ width: 56, height: 56, borderRadius: 12 }} />
          <Typography.Title level={3} style={{ marginTop: 12, marginBottom: 4 }}>
            AI 智能助手
          </Typography.Title>
          <Typography.Text type="secondary">请使用账号登录</Typography.Text>
        </div>

        {error && (
          <Alert
            type="error"
            message={error}
            showIcon
            closable
            onClose={() => setError(null)}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form<LoginForm>
          name="login"
          layout="vertical"
          onFinish={onFinish}
          autoComplete="on"
          requiredMark={false}
        >
          <Form.Item
            name="username"
            label="账号"
            rules={[{ required: true, message: "请输入账号" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus size="large" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
