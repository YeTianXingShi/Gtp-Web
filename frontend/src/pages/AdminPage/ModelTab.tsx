import { useEffect, useState } from "react";
import {
  Card, Button, Space, Form, Input, Select, Switch, Tag, Popconfirm,
  Collapse, message, Spin, Empty, Divider,
} from "antd";
import { PlusOutlined, DeleteOutlined, SaveOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchConfigFile, saveConfigFile } from "@/api/admin";

interface ThinkingConfig {
  enabled: boolean;
  effort: string;
  effort_options: string[];
  summary?: string;
  include_thoughts?: boolean;
  level?: string;
  level_options?: string[];
}

interface ModelEntry {
  name: string;
  label: string;
  reasoning?: ThinkingConfig | null;
  thinking?: ThinkingConfig | null;
}

interface ModelsConfig {
  openai: { models: ModelEntry[] };
  google: { models: ModelEntry[] };
  claude: { models: ModelEntry[] };
}

const PROVIDERS: { key: keyof ModelsConfig; label: string; thinkingKey: "reasoning" | "thinking" }[] = [
  { key: "openai", label: "OpenAI", thinkingKey: "reasoning" },
  { key: "google", label: "Google Gemini", thinkingKey: "thinking" },
  { key: "claude", label: "Anthropic Claude", thinkingKey: "thinking" },
];

const EFFORT_OPTIONS = ["minimal", "low", "medium", "high", "xhigh", "max"];
const EFFORT_LABELS: Record<string, string> = {
  minimal: "最小", low: "轻量", medium: "标准", high: "深度", xhigh: "极致", max: "最大",
};

function parseModelsConfig(raw: string): ModelsConfig {
  const cleaned = raw.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
  const parsed = JSON.parse(cleaned);
  return {
    openai: { models: parsed.openai?.models ?? [] },
    google: { models: parsed.google?.models ?? [] },
    claude: { models: parsed.claude?.models ?? [] },
  };
}

function serializeModelsConfig(config: ModelsConfig): string {
  return JSON.stringify(config, null, 2);
}

export function ModelTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["config-file", "models"],
    queryFn: () => fetchConfigFile("models"),
  });

  const [config, setConfig] = useState<ModelsConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data?.content && !config) {
      try {
        setConfig(parseModelsConfig(data.content));
      } catch {
        message.error("模型配置文件解析失败");
      }
    }
  }, [data, config]);

  const reload = () => {
    setConfig(null);
    setDirty(false);
    qc.invalidateQueries({ queryKey: ["config-file", "models"] });
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      await saveConfigFile("models", serializeModelsConfig(config));
      setDirty(false);
      message.success("模型配置已保存并生效");
      qc.invalidateQueries({ queryKey: ["config-file", "models"] });
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const update = (fn: (c: ModelsConfig) => ModelsConfig) => {
    setConfig((prev) => {
      if (!prev) return prev;
      const next = fn(prev);
      setDirty(true);
      return next;
    });
  };

  const updateModel = (
    provider: keyof ModelsConfig,
    index: number,
    patch: Partial<ModelEntry>,
  ) => {
    update((c) => {
      const models = [...c[provider].models];
      models[index] = { ...models[index], ...patch };
      return { ...c, [provider]: { models } };
    });
  };

  const addModel = (provider: keyof ModelsConfig) => {
    update((c) => {
      const thinkingKey = PROVIDERS.find((p) => p.key === provider)!.thinkingKey;
      const newModel: ModelEntry = { name: "", label: "" };
      if (thinkingKey === "reasoning") {
        newModel.reasoning = { enabled: true, effort: "medium", effort_options: ["low", "medium", "high"], summary: "auto" };
      } else {
        newModel.thinking = { enabled: true, effort: "medium", effort_options: ["low", "medium", "high"], include_thoughts: true };
      }
      return { ...c, [provider]: { models: [...c[provider].models, newModel] } };
    });
  };

  const removeModel = (provider: keyof ModelsConfig, index: number) => {
    update((c) => {
      const models = c[provider].models.filter((_, i) => i !== index);
      return { ...c, [provider]: { models } };
    });
  };

  if (isLoading) return <Spin />;
  if (!config) return <Empty description="加载模型配置失败" />;

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
          disabled={!dirty}
        >
          保存配置
        </Button>
        <Button icon={<ReloadOutlined />} onClick={reload}>重新加载</Button>
        {dirty && <Tag color="orange">有未保存的修改</Tag>}
      </Space>

      <Collapse
        defaultActiveKey={PROVIDERS.filter((p) => config[p.key].models.length > 0).map((p) => p.key)}
        items={PROVIDERS.map((prov) => ({
          key: prov.key,
          label: (
            <Space>
              <span style={{ fontWeight: 600 }}>{prov.label}</span>
              <Tag>{config[prov.key].models.length} 个模型</Tag>
            </Space>
          ),
          children: (
            <>
              {config[prov.key].models.map((model, idx) => (
                <ModelCard
                  key={idx}
                  model={model}
                  provider={prov}
                  onChange={(patch) => updateModel(prov.key, idx, patch)}
                  onRemove={() => removeModel(prov.key, idx)}
                />
              ))}
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => addModel(prov.key)}
                block
                style={{ marginTop: 8 }}
              >
                添加模型
              </Button>
            </>
          ),
        }))}
      />
    </>
  );
}

function ModelCard({
  model,
  provider,
  onChange,
  onRemove,
}: {
  model: ModelEntry;
  provider: (typeof PROVIDERS)[number];
  onChange: (patch: Partial<ModelEntry>) => void;
  onRemove: () => void;
}) {
  const thinkingKey = provider.thinkingKey;
  const thinkingConfig = (thinkingKey === "reasoning" ? model.reasoning : model.thinking) as ThinkingConfig | null | undefined;
  const enabled = thinkingConfig?.enabled ?? false;

  const updateThinking = (patch: Partial<ThinkingConfig>) => {
    const current: ThinkingConfig = thinkingConfig ?? {
      enabled: false, effort: "medium", effort_options: ["low", "medium", "high"],
    };
    onChange({ [thinkingKey]: { ...current, ...patch } });
  };

  return (
    <Card
      size="small"
      style={{ marginBottom: 8 }}
      title={
        <Space>
          <span>{model.label || model.name || "新模型"}</span>
          {model.name && <Tag color="blue">{model.name}</Tag>}
        </Space>
      }
      extra={
        <Popconfirm title="确认删除该模型？" onConfirm={onRemove}>
          <Button danger size="small" icon={<DeleteOutlined />} />
        </Popconfirm>
      }
    >
      <Form layout="inline" size="small" style={{ flexWrap: "wrap", gap: 8 }}>
        <Form.Item label="模型 ID">
          <Input
            value={model.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="如 gpt-5.4"
            style={{ width: 180 }}
          />
        </Form.Item>
        <Form.Item label="显示名称">
          <Input
            value={model.label}
            onChange={(e) => onChange({ label: e.target.value })}
            placeholder="如 GPT-5.4（增强版）"
            style={{ width: 220 }}
          />
        </Form.Item>
      </Form>

      <Divider style={{ margin: "8px 0" }} />

      <Form layout="inline" size="small" style={{ flexWrap: "wrap", gap: 8 }}>
        <Form.Item label="启用思考">
          <Switch checked={enabled} onChange={(v) => updateThinking({ enabled: v })} />
        </Form.Item>
        {enabled && (
          <>
            <Form.Item label="默认强度">
              <Select
                value={thinkingConfig?.effort || "medium"}
                onChange={(v) => updateThinking({ effort: v })}
                style={{ width: 100 }}
                options={EFFORT_OPTIONS.map((o) => ({ value: o, label: EFFORT_LABELS[o] || o }))}
              />
            </Form.Item>
            <Form.Item label="可选强度">
              <Select
                mode="multiple"
                value={thinkingConfig?.effort_options ?? []}
                onChange={(v) => updateThinking({ effort_options: v })}
                style={{ minWidth: 200 }}
                options={EFFORT_OPTIONS.map((o) => ({ value: o, label: EFFORT_LABELS[o] || o }))}
              />
            </Form.Item>
            {thinkingKey === "reasoning" && (
              <Form.Item label="摘要">
                <Select
                  value={(thinkingConfig as ThinkingConfig)?.summary || "auto"}
                  onChange={(v) => updateThinking({ summary: v })}
                  style={{ width: 100 }}
                  options={[
                    { value: "auto", label: "自动" },
                    { value: "concise", label: "精简" },
                    { value: "none", label: "无" },
                  ]}
                />
              </Form.Item>
            )}
            {thinkingKey === "thinking" && (
              <Form.Item label="返回思考摘要">
                <Switch
                  checked={thinkingConfig?.include_thoughts ?? true}
                  onChange={(v) => updateThinking({ include_thoughts: v })}
                />
              </Form.Item>
            )}
          </>
        )}
      </Form>
    </Card>
  );
}
