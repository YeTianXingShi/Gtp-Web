import { useState } from "react";
import { Table, Button, Space, Input, Select } from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { fetchAuditLogs } from "@/api/admin";
import type { AuditLog } from "@/types/api";

const PAGE_SIZE = 100;

const ACTION_OPTIONS = [
  { value: "", label: "全部动作" },
  { value: "login", label: "登录" },
  { value: "chat", label: "发送消息" },
  { value: "create_conversation", label: "创建会话" },
  { value: "delete_conversation", label: "删除会话" },
  { value: "create_user", label: "创建用户" },
  { value: "update_user", label: "修改用户" },
  { value: "delete_user", label: "删除用户" },
  { value: "update_config", label: "修改配置" },
];

export function AuditTab() {
  const [offset, setOffset] = useState(0);
  const [accumulated, setAccumulated] = useState<AuditLog[]>([]);
  const [filterUser, setFilterUser] = useState("");
  const [filterAction, setFilterAction] = useState("");

  const { data = [], isFetching, refetch } = useQuery({
    queryKey: ["audit-logs", offset, filterUser, filterAction],
    queryFn: () =>
      fetchAuditLogs({
        limit: PAGE_SIZE,
        offset,
        username: filterUser || undefined,
        action: filterAction || undefined,
      }),
    placeholderData: (prev) => prev,
  });

  if (offset === 0 && accumulated !== data && data.length > 0 && accumulated.length === 0) {
    setAccumulated(data);
  }

  const allLogs = offset === 0 ? data : [...accumulated, ...data];

  const handleLoadMore = () => {
    if (offset === 0) {
      setAccumulated(data);
    } else {
      setAccumulated((prev) => [...prev, ...data]);
    }
    setOffset((prev) => prev + PAGE_SIZE);
  };

  const handleSearch = () => {
    setAccumulated([]);
    setOffset(0);
    refetch();
  };

  const handleRefresh = () => {
    setFilterUser("");
    setFilterAction("");
    setAccumulated([]);
    setOffset(0);
    refetch();
  };

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="筛选用户名"
          prefix={<SearchOutlined />}
          value={filterUser}
          onChange={(e) => setFilterUser(e.target.value)}
          onPressEnter={handleSearch}
          allowClear
          style={{ width: 160 }}
        />
        <Select
          value={filterAction}
          onChange={(v) => { setFilterAction(v); setAccumulated([]); setOffset(0); }}
          options={ACTION_OPTIONS}
          style={{ width: 140 }}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          搜索
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
          重置
        </Button>
      </Space>

      <Table<AuditLog>
        rowKey="id"
        dataSource={allLogs}
        loading={isFetching}
        pagination={false}
        size="small"
        columns={[
          { title: "时间", dataIndex: "created_at", width: 160 },
          { title: "用户", dataIndex: "username", width: 100 },
          {
            title: "动作",
            dataIndex: "action",
            width: 120,
            render: (v: string) => ACTION_OPTIONS.find((o) => o.value === v)?.label ?? v,
          },
          { title: "对象", dataIndex: "target_id", width: 140 },
          { title: "详情", dataIndex: "detail", ellipsis: true },
          { title: "IP", dataIndex: "ip_address", width: 130 },
        ]}
      />

      <div style={{ marginTop: 12, textAlign: "center" }}>
        {data.length === PAGE_SIZE && (
          <Button onClick={handleLoadMore} loading={isFetching}>
            加载更多
          </Button>
        )}
      </div>
    </>
  );
}
