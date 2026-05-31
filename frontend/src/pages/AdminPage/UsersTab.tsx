import { useState } from "react";
import {
  Button, Modal, Form, Input, Switch, Table, Space, Popconfirm,
  Drawer, message, Tag, Divider,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, MinusCircleOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAdminUser, deleteAdminUser, listAdminUsers, updateAdminUser,
} from "@/api/admin";
import type { AdminUser } from "@/types/api";

const PROFILE_PRESETS = [
  { key: "real_name", label: "真实姓名" },
  { key: "employee_id", label: "工号" },
  { key: "position", label: "职位" },
  { key: "department", label: "部门" },
  { key: "phone", label: "手机号" },
  { key: "email", label: "邮箱" },
];

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

  const profileSummary = (user: AdminUser) => {
    const p = user.profile ?? {};
    const parts: string[] = [];
    for (const preset of PROFILE_PRESETS) {
      if (p[preset.key]) parts.push(`${preset.label}: ${p[preset.key]}`);
    }
    for (const [k, v] of Object.entries(p)) {
      if (!PROFILE_PRESETS.some((pr) => pr.key === k) && v) {
        parts.push(`${k}: ${v}`);
      }
    }
    return parts.join("｜") || "-";
  };

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
        size="small"
        columns={[
          { title: "用户名", dataIndex: "username", width: 120 },
          {
            title: "角色",
            dataIndex: "is_admin",
            width: 80,
            render: (v) => <Tag color={v ? "blue" : "default"}>{v ? "管理员" : "普通"}</Tag>,
          },
          {
            title: "启用",
            dataIndex: "enabled",
            width: 70,
            render: (v, row) => (
              <Switch
                checked={v !== false}
                size="small"
                onChange={(checked) =>
                  updateMutation.mutate({ username: row.username, patch: { enabled: checked } })
                }
              />
            ),
          },
          {
            title: "用户信息",
            ellipsis: true,
            render: (_, row) => (
              <span style={{ color: "#666", fontSize: 12 }}>{profileSummary(row)}</span>
            ),
          },
          {
            title: "操作",
            width: 140,
            render: (_, row) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => setDrawerUser(row)}>
                  编辑
                </Button>
                <Popconfirm
                  title={`删除用户 ${row.username}？`}
                  okText="确认"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => deleteMutation.mutate(row.username)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} />
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
            { onSuccess: () => setDrawerUser(null) },
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
    profile?: Record<string, string>;
  }) => void;
  saving: boolean;
}

function UserEditDrawer({ user, onClose, onSave, saving }: UserEditDrawerProps) {
  const [form] = Form.useForm();
  const [profileFields, setProfileFields] = useState<{ key: string; value: string }[]>([]);

  const initProfile = (u: AdminUser) => {
    const p = u.profile ?? {};
    const fields: { key: string; value: string }[] = [];
    for (const preset of PROFILE_PRESETS) {
      fields.push({ key: preset.key, value: p[preset.key] ?? "" });
    }
    for (const [k, v] of Object.entries(p)) {
      if (!PROFILE_PRESETS.some((pr) => pr.key === k)) {
        fields.push({ key: k, value: v });
      }
    }
    return fields;
  };

  return (
    <Drawer
      title={user ? `编辑用户: ${user.username}` : ""}
      open={!!user}
      onClose={onClose}
      width={480}
      destroyOnHidden
      afterOpenChange={(open) => {
        if (open && user) {
          form.setFieldsValue({
            is_admin: user.is_admin,
            openai: user.api_keys?.openai ?? "",
            google: user.api_keys?.google ?? "",
            claude: user.api_keys?.claude ?? "",
          });
          setProfileFields(initProfile(user));
        }
      }}
    >
      {user && (
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            const profile: Record<string, string> = {};
            for (const f of profileFields) {
              const k = f.key.trim();
              const v = f.value.trim();
              if (k && v) profile[k] = v;
            }
            const patch: Parameters<UserEditDrawerProps["onSave"]>[0] = {
              is_admin: values.is_admin,
              api_keys: {
                ...(values.openai ? { openai: values.openai } : {}),
                ...(values.google ? { google: values.google } : {}),
                ...(values.claude ? { claude: values.claude } : {}),
              },
              profile,
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

          <Divider orientation="left" style={{ fontSize: 13 }}>用户信息</Divider>
          {profileFields.map((field, idx) => {
            const preset = PROFILE_PRESETS.find((p) => p.key === field.key);
            return (
              <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                {preset ? (
                  <Input value={preset.label} disabled style={{ width: 100, flexShrink: 0 }} />
                ) : (
                  <Input
                    value={field.key}
                    placeholder="字段名"
                    style={{ width: 100, flexShrink: 0 }}
                    onChange={(e) => {
                      const arr = [...profileFields];
                      arr[idx] = { ...arr[idx], key: e.target.value };
                      setProfileFields(arr);
                    }}
                  />
                )}
                <Input
                  value={field.value}
                  placeholder={preset?.label ?? "值"}
                  onChange={(e) => {
                    const arr = [...profileFields];
                    arr[idx] = { ...arr[idx], value: e.target.value };
                    setProfileFields(arr);
                  }}
                />
                {!preset && (
                  <Button
                    type="text"
                    danger
                    icon={<MinusCircleOutlined />}
                    onClick={() => setProfileFields(profileFields.filter((_, i) => i !== idx))}
                  />
                )}
              </div>
            );
          })}
          <Button
            type="dashed"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => setProfileFields([...profileFields, { key: "", value: "" }])}
            style={{ marginBottom: 16 }}
          >
            添加自定义字段
          </Button>

          <Divider orientation="left" style={{ fontSize: 13 }}>API Key（可选）</Divider>
          <Form.Item name="openai" label="OpenAI">
            <Input.Password />
          </Form.Item>
          <Form.Item name="google" label="Google">
            <Input.Password />
          </Form.Item>
          <Form.Item name="claude" label="Claude">
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
