import { useState } from "react";
import {
  Button,
  Modal,
  Form,
  Input,
  Switch,
  Table,
  Space,
  Popconfirm,
  Drawer,
  message,
  Tag,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAdminUser,
  deleteAdminUser,
  listAdminUsers,
  updateAdminUser,
} from "@/api/admin";
import type { AdminUser } from "@/types/api";

export function UsersTab() {
  const qc = useQueryClient();
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: listAdminUsers,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [drawerUser, setDrawerUser] = useState<AdminUser | null>(null);

  const createMutation = useMutation({
    mutationFn: createAdminUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      message.success("已创建");
      setCreateOpen(false);
    },
    onError: (e) => message.error((e as Error).message),
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { username: string; patch: Parameters<typeof updateAdminUser>[1] }) =>
      updateAdminUser(vars.username, vars.patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      message.success("已更新");
    },
    onError: (e) => message.error((e as Error).message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAdminUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      message.success("已删除");
    },
    onError: (e) => message.error((e as Error).message),
  });

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新增用户
        </Button>
      </Space>

      <Table<AdminUser>
        rowKey="username"
        dataSource={users}
        loading={isLoading}
        pagination={false}
        columns={[
          { title: "用户名", dataIndex: "username" },
          {
            title: "角色",
            dataIndex: "is_admin",
            width: 100,
            render: (v) => <Tag color={v ? "blue" : "default"}>{v ? "管理员" : "普通"}</Tag>,
          },
          {
            title: "启用",
            dataIndex: "enabled",
            width: 100,
            render: (v, row) => (
              <Switch
                checked={v !== false}
                onChange={(checked) =>
                  updateMutation.mutate({ username: row.username, patch: { enabled: checked } })
                }
              />
            ),
          },
          {
            title: "操作",
            width: 240,
            render: (_, row) => (
              <Space>
                <Button size="small" icon={<KeyOutlined />} onClick={() => setDrawerUser(row)}>
                  编辑
                </Button>
                <Popconfirm
                  title={`删除用户 ${row.username}？`}
                  okText="确认删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => deleteMutation.mutate(row.username)}
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
        title="新增用户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form
          layout="vertical"
          onFinish={(values) => createMutation.mutate(values)}
          requiredMark={false}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_admin" label="管理员" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending} block>
            创建
          </Button>
        </Form>
      </Modal>

      <UserEditDrawer
        user={drawerUser}
        onClose={() => setDrawerUser(null)}
        onSave={(patch) => {
          if (!drawerUser) return;
          updateMutation.mutate(
            { username: drawerUser.username, patch },
            {
              onSuccess: () => setDrawerUser(null),
            },
          );
        }}
        saving={updateMutation.isPending}
      />
    </>
  );
}

interface UserEditDrawerProps {
  user: AdminUser | null;
  onClose: () => void;
  onSave: (patch: {
    password?: string;
    is_admin?: boolean;
    api_keys?: Record<string, string>;
  }) => void;
  saving: boolean;
}

function UserEditDrawer({ user, onClose, onSave, saving }: UserEditDrawerProps) {
  const [form] = Form.useForm<{
    password: string;
    is_admin: boolean;
    openai: string;
    google: string;
    claude: string;
  }>();

  return (
    <Drawer
      title={user ? `编辑用户: ${user.username}` : ""}
      open={!!user}
      onClose={onClose}
      width={420}
      destroyOnHidden
    >
      {user && (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            is_admin: user.is_admin,
            openai: user.api_keys?.openai ?? "",
            google: user.api_keys?.google ?? "",
            claude: user.api_keys?.claude ?? "",
          }}
          onFinish={(values) => {
            const patch: Parameters<UserEditDrawerProps["onSave"]>[0] = {
              is_admin: values.is_admin,
              api_keys: {
                ...(values.openai ? { openai: values.openai } : {}),
                ...(values.google ? { google: values.google } : {}),
                ...(values.claude ? { claude: values.claude } : {}),
              },
            };
            if (values.password) patch.password = values.password;
            onSave(patch);
          }}
          requiredMark={false}
        >
          <Form.Item name="password" label="重置密码（留空不修改）">
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="is_admin" label="管理员" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="openai" label="OpenAI API Key（可选）">
            <Input.Password />
          </Form.Item>
          <Form.Item name="google" label="Google API Key（可选）">
            <Input.Password />
          </Form.Item>
          <Form.Item name="claude" label="Claude API Key（可选）">
            <Input.Password />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" icon={<EditOutlined />} loading={saving}>
              保存
            </Button>
            <Button onClick={onClose}>取消</Button>
          </Space>
        </Form>
      )}
    </Drawer>
  );
}
