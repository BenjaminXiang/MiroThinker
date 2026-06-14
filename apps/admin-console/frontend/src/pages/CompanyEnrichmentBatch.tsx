import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Button,
  Checkbox,
  Descriptions,
  InputNumber,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlayCircleOutlined } from "@ant-design/icons";
import {
  fetchCompanyEnrichmentBatch,
  restartStaleCompanyEnrichmentBatch,
  startCompanyEnrichmentBatch,
  type CompanyEnrichmentBatchStatus,
  type CompanyEnrichmentCompanyDiagnostic,
} from "../api";

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  queued: "default",
  running: "processing",
  succeeded: "success",
  partial: "warning",
  failed: "error",
};

const ACTIVE_STATUSES = new Set(["queued", "running"]);

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderCountMap(map?: Record<string, number>) {
  const entries = Object.entries(map ?? {})
    .filter(([, value]) => Number(value) > 0)
    .sort(([left], [right]) => left.localeCompare(right));
  if (entries.length === 0) return "-";
  return (
    <Space wrap>
      {entries.map(([key, value]) => (
        <Tag key={key}>
          {key}: {value}
        </Tag>
      ))}
    </Space>
  );
}

function renderSourceCounts(map?: Record<string, Record<string, number>>) {
  const entries = Object.entries(map ?? {}).sort(([left], [right]) =>
    left.localeCompare(right)
  );
  if (entries.length === 0) return "-";
  return (
    <Space direction="vertical" size={2}>
      {entries.map(([adapter, counts]) => (
        <Text key={adapter}>
          {adapter}: 查询 {counts.query_count ?? 0} / 结果{" "}
          {counts.result_count ?? 0} / 接受 {counts.accepted_count ?? 0} / 拒绝{" "}
          {counts.rejected_count ?? 0}
        </Text>
      ))}
    </Space>
  );
}

function renderQualityReport(report?: Record<string, unknown>) {
  const headline = typeof report?.headline === "string" ? report.headline : "";
  const samples = Array.isArray(report?.sample_company_ids)
    ? report.sample_company_ids
    : [];
  if (!headline && samples.length === 0) return "-";
  return (
    <Space direction="vertical" size={2}>
      {headline && <Text>{headline}</Text>}
      {samples.length > 0 && (
        <Text type="secondary">样例: {samples.map(String).join(", ")}</Text>
      )}
    </Space>
  );
}

export default function CompanyEnrichmentBatch() {
  const { batchId = "" } = useParams();
  const navigate = useNavigate();
  const [batch, setBatch] = useState<CompanyEnrichmentBatchStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<number | null>(100);
  const [chunkSize, setChunkSize] = useState<number>(20);
  const [stagePreset, setStagePreset] =
    useState<"trusted_xlsx" | "high_trust_sources" | "full">(
      "high_trust_sources"
    );
  const [includeFailed, setIncludeFailed] = useState(false);
  const [skipMilvus, setSkipMilvus] = useState(false);

  function load() {
    if (!batchId) return;
    setLoading(true);
    fetchCompanyEnrichmentBatch(batchId)
      .then((data) => {
        setBatch(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }

  useEffect(load, [batchId]);

  useEffect(() => {
    if (!batch || !ACTIVE_STATUSES.has(batch.status)) return;
    const timer = window.setInterval(() => {
      fetchCompanyEnrichmentBatch(batch.batch_id)
        .then(setBatch)
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [batch]);

  async function handleStart() {
    if (!batch) return;
    setStarting(true);
    setError(null);
    try {
      const response = await startCompanyEnrichmentBatch(batch.batch_id, {
        limit,
        chunk_size: chunkSize,
        stage_preset: stagePreset,
        include_failed: includeFailed,
        skip_milvus: skipMilvus,
      });
      message.success("已启动后台增强批处理");
      navigate(`/pipeline-runs/${response.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }

  async function handleRestartStale() {
    if (!batch) return;
    setStarting(true);
    setError(null);
    try {
      const response = await restartStaleCompanyEnrichmentBatch(batch.batch_id, {
        limit,
        chunk_size: chunkSize,
        stage_preset: stagePreset,
        include_failed: true,
        skip_milvus: skipMilvus,
      });
      message.success("已重启心跳超时的后台增强批处理");
      navigate(`/pipeline-runs/${response.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }

  if (loading && !batch) {
    return <Spin size="large" style={{ marginTop: 100 }} />;
  }

  if (!batch) {
    return (
      <div>
        <Title level={3}>企业增强批次</Title>
        <Text type="danger">{error ?? "批次不存在"}</Text>
      </div>
    );
  }

  const canStart = batch.status !== "running";

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate(-1)}>返回</Button>
        <Title level={3} style={{ margin: 0 }}>
          企业增强批次
        </Title>
        <Tag color={STATUS_COLOR[batch.status] ?? "default"}>{batch.status}</Tag>
      </Space>
      {error && (
        <Text type="danger" style={{ display: "block", marginBottom: 12 }}>
          {error}
        </Text>
      )}

      <Descriptions bordered size="small" column={2}>
        <Descriptions.Item label="批次 ID" span={2}>
          <Text copyable>{batch.batch_id}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="当前阶段">
          {batch.current_stage ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="进度">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Progress percent={batch.progress_percent} size="small" />
            <Text>
              {batch.companies_processed} / {batch.companies_selected}
            </Text>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="成功/失败">
          {batch.companies_succeeded} / {batch.companies_failed}
        </Descriptions.Item>
        <Descriptions.Item label="来源接受/拒绝">
          {batch.accepted_source_count} / {batch.rejected_source_count}
        </Descriptions.Item>
        <Descriptions.Item label="产品/场景/动态">
          {batch.product_count} / {batch.scenario_count} /{" "}
          {batch.funding_event_count}
        </Descriptions.Item>
        <Descriptions.Item label="向量刷新">
          {batch.vector_refreshed_count} / {batch.companies_selected}
        </Descriptions.Item>
        <Descriptions.Item label="后台心跳">
          {formatDate(batch.runner_heartbeat_at)}
        </Descriptions.Item>
        <Descriptions.Item label="最后完成企业">
          {batch.last_completed_company_id ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="后台进程">
          {batch.runner_pid ? `PID ${batch.runner_pid}` : "-"}
          {batch.runner_is_stale ? <Tag color="error">心跳超时</Tag> : null}
        </Descriptions.Item>
        <Descriptions.Item label="日志路径">
          {batch.runner_log_path ? <Text copyable>{batch.runner_log_path}</Text> : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="质量报告" span={2}>
          {renderQualityReport(batch.quality_report)}
        </Descriptions.Item>
        <Descriptions.Item label="最后错误" span={2}>
          {batch.last_error ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {formatDate(batch.created_at)}
        </Descriptions.Item>
        <Descriptions.Item label="更新时间">
          {formatDate(batch.updated_at)}
        </Descriptions.Item>
      </Descriptions>

      <Title level={4} style={{ marginTop: 24 }}>
        启动后台增强
      </Title>
      <Space wrap style={{ marginBottom: 16 }}>
        <InputNumber
          min={1}
          max={10000}
          value={limit}
          onChange={(value) => setLimit(value ?? null)}
          addonBefore="limit"
          style={{ width: 180 }}
        />
        <InputNumber
          min={1}
          max={500}
          value={chunkSize}
          onChange={(value) => setChunkSize(value ?? 20)}
          addonBefore="chunk"
          style={{ width: 180 }}
        />
        <Select
          value={stagePreset}
          onChange={setStagePreset}
          style={{ width: 180 }}
          options={[
            { value: "trusted_xlsx", label: "XLSX 可信字段" },
            { value: "high_trust_sources", label: "高可信外部源" },
            { value: "full", label: "完整增强" },
          ]}
        />
        <Checkbox
          checked={includeFailed}
          onChange={(event) => setIncludeFailed(event.target.checked)}
        >
          包含失败项
        </Checkbox>
        <Checkbox
          checked={skipMilvus}
          onChange={(event) => setSkipMilvus(event.target.checked)}
        >
          跳过向量刷新
        </Checkbox>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          disabled={!canStart}
          loading={starting}
          onClick={handleStart}
        >
          启动增强
        </Button>
        {batch.runner_is_stale && (
          <Button
            danger
            icon={<PlayCircleOutlined />}
            loading={starting}
            onClick={handleRestartStale}
          >
            重启超时任务
          </Button>
        )}
      </Space>

      <Title level={4} style={{ marginTop: 24 }}>
        阶段与失败原因
      </Title>
      <Descriptions bordered size="small" column={2}>
        <Descriptions.Item label="状态分布">
          {renderCountMap(batch.status_counts)}
        </Descriptions.Item>
        <Descriptions.Item label="阶段分布">
          {renderCountMap(batch.current_stage_counts)}
        </Descriptions.Item>
        <Descriptions.Item label="未命中原因">
          {renderCountMap(batch.miss_reasons)}
        </Descriptions.Item>
        <Descriptions.Item label="运营原因分类">
          {renderCountMap(batch.miss_reason_buckets)}
        </Descriptions.Item>
        <Descriptions.Item label="官网失败原因">
          {renderCountMap(batch.official_failure_reasons)}
        </Descriptions.Item>
        <Descriptions.Item label="候选拒绝原因" span={2}>
          {renderCountMap(batch.rejected_candidate_reasons)}
        </Descriptions.Item>
        <Descriptions.Item label="来源分布" span={2}>
          {renderSourceCounts(batch.source_counts_by_adapter)}
        </Descriptions.Item>
      </Descriptions>

      <Title level={4} style={{ marginTop: 24 }}>
        公司级诊断
      </Title>
      <Table<CompanyEnrichmentCompanyDiagnostic>
        rowKey="company_id"
        size="small"
        dataSource={batch.company_diagnostics}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "公司", dataIndex: "company_id", key: "company_id" },
          { title: "状态", dataIndex: "status", key: "status" },
          { title: "阶段", dataIndex: "current_stage", key: "current_stage" },
          {
            title: "失败/未命中原因",
            key: "reason",
            render: (_, record) => record.miss_reason ?? record.last_error ?? "-",
          },
          {
            title: "产品/场景/动态",
            key: "facts",
            render: (_, record) =>
              `${record.product_count} / ${record.scenario_count} / ${record.funding_event_count}`,
          },
        ]}
      />
    </div>
  );
}
