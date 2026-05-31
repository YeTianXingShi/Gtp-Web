import { useState } from "react";
import { Select, Button, Space, Table, Spin, Empty } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { fetchTokenUsage } from "@/api/admin";

interface UserUsageRow {
  username: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  by_model?: Array<{
    model: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  }>;
}

export function UsageTab() {
  const [range, setRange] = useState<"today" | "week" | "month">("month");
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["token-usage", range],
    queryFn: () => fetchTokenUsage(range),
  });

  const rows: UserUsageRow[] = Array.isArray(data) ? (data as UserUsageRow[]) : [];

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          value={range}
          onChange={setRange}
          options={[
            { value: "today", label: "今日" },
            { value: "week", label: "近 7 天" },
            { value: "month", label: "近 30 天" },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
          刷新
        </Button>
      </Space>

      {isLoading ? (
        <Spin />
      ) : rows.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <Table<UserUsageRow>
          rowKey="username"
          dataSource={rows}
          pagination={false}
          expandable={{
            rowExpandable: (row) => Boolean(row.by_model && row.by_model.length),
            expandedRowRender: (row) =>
              row.by_model ? (
                <Table
                  size="small"
                  rowKey="model"
                  pagination={false}
                  dataSource={row.by_model}
                  columns={[
                    { title: "模型", dataIndex: "model" },
                    { title: "输入", dataIndex: "input_tokens" },
                    { title: "输出", dataIndex: "output_tokens" },
                    { title: "合计", dataIndex: "total_tokens" },
                  ]}
                />
              ) : null,
          }}
          columns={[
            { title: "用户", dataIndex: "username" },
            { title: "输入", dataIndex: "total_input_tokens" },
            { title: "输出", dataIndex: "total_output_tokens" },
            { title: "合计", dataIndex: "total_tokens" },
          ]}
        />
      )}
    </>
  );
}
