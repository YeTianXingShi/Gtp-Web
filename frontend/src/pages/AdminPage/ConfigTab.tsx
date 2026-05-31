import { useEffect, useMemo, useState } from "react";
import { Select, Space, Tag, Typography, Button, Alert, message, Spin } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { json as cmJson } from "@codemirror/lang-json";
import { yaml as cmYaml } from "@codemirror/lang-yaml";
import { fetchConfigFile, listConfigFiles, saveConfigFile } from "@/api/admin";
import type { ConfigFileMeta } from "@/types/api";

export function ConfigTab() {
  const qc = useQueryClient();
  const { data: meta, isLoading: metaLoading } = useQuery({
    queryKey: ["config-files"],
    queryFn: listConfigFiles,
  });

  const [currentId, setCurrentId] = useState<string | null>(null);

  useEffect(() => {
    if (meta && currentId == null) {
      setCurrentId(meta.default_file_id);
    }
  }, [meta, currentId]);

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["config-file", currentId],
    queryFn: () => fetchConfigFile(currentId as string),
    enabled: currentId != null,
  });

  const [content, setContent] = useState<string>("");
  const [savedHint, setSavedHint] = useState<string | null>(null);

  useEffect(() => {
    if (detail) {
      setContent(detail.content);
      setSavedHint(null);
    }
  }, [detail]);

  const saveMutation = useMutation({
    mutationFn: (vars: { id: string; content: string }) =>
      saveConfigFile(vars.id, vars.content),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["config-file", currentId] });
      const applied = data.hot_reload?.applied_keys ?? [];
      const restart = data.hot_reload?.restart_required_keys ?? [];
      if (restart.length) {
        setSavedHint(`已保存。需要重启才能生效的键：${restart.join(", ")}`);
      } else if (applied.length) {
        setSavedHint(`已保存并热更新：${applied.join(", ")}`);
      } else {
        setSavedHint("已保存");
      }
      message.success("已保存");
    },
    onError: (e) => {
      setSavedHint(null);
      message.error((e as Error).message);
    },
  });

  const currentMeta: ConfigFileMeta | null = useMemo(() => {
    if (!meta || !currentId) return null;
    return meta.files.find((f) => f.id === currentId) ?? null;
  }, [meta, currentId]);

  if (metaLoading || !meta) return <Spin />;

  const langExt = (() => {
    if (!currentMeta) return undefined;
    if (currentMeta.format === "json" || currentMeta.format === "jsonc") return cmJson();
    return cmYaml();
  })();

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <span>配置文件：</span>
        <Select
          style={{ minWidth: 260 }}
          value={currentId ?? undefined}
          onChange={setCurrentId}
          options={meta.files.map((f) => ({ value: f.id, label: f.label }))}
        />
        {currentMeta?.requires_restart ? (
          <Tag color="orange">部分键需重启</Tag>
        ) : (
          <Tag color="green">支持热更新</Tag>
        )}
      </Space>

      {currentMeta && (
        <>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 4 }}>
            {currentMeta.description}
          </Typography.Paragraph>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
            文件路径：<code>{currentMeta.path}</code>
          </Typography.Paragraph>
        </>
      )}

      {savedHint && (
        <Alert
          type="success"
          message={savedHint}
          showIcon
          closable
          onClose={() => setSavedHint(null)}
          style={{ marginBottom: 12 }}
        />
      )}

      {detailLoading ? (
        <Spin />
      ) : (
        <CodeMirror
          value={content}
          height="480px"
          extensions={langExt ? [langExt] : []}
          onChange={(v) => setContent(v)}
          theme="light"
        />
      )}

      <div style={{ marginTop: 12 }}>
        <Button
          type="primary"
          loading={saveMutation.isPending}
          disabled={!currentId || detailLoading}
          onClick={() => currentId && saveMutation.mutate({ id: currentId, content })}
        >
          保存当前文件
        </Button>
      </div>
    </>
  );
}
