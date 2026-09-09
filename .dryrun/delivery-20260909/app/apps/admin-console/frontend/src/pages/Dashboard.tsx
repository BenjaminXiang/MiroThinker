import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Col, Row, Space, Spin, Table, Tag, Typography } from "antd";
import {
  TeamOutlined,
  BankOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";
import {
  fetchDashboard,
  triggerMilvusBackfill,
  triggerRetrievalValidation,
  type DashboardResponse,
  type PipelineAction,
  type PipelineFailureSample,
  type PipelineIssueSample,
  type PipelineStageSummary,
} from "../api";
import StatCard from "../components/StatCard";
import QualityTag from "../components/QualityTag";

const { Text, Title } = Typography;

const DOMAIN_META: Record<string, { label: string; icon: ReactNode }> = {
  professor: { label: "教授", icon: <TeamOutlined /> },
  company: { label: "企业", icon: <BankOutlined /> },
  paper: { label: "论文", icon: <FileTextOutlined /> },
  patent: { label: "专利", icon: <SafetyCertificateOutlined /> },
};

const STAGE_LABELS: Record<string, string> = {
  import_xlsx: "Excel 导入",
  backfill_real: "Milvus 回填",
  answer_readiness_eval: "检索验收",
  professor_v3: "教授采集",
  quality_scan: "质量扫描",
};

const STATUS_COLOR: Record<string, string> = {
  running: "processing",
  succeeded: "success",
  partial: "warning",
  failed: "error",
};

const SEVERITY_COLOR: Record<string, string> = {
  low: "default",
  medium: "warning",
  high: "error",
};

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

function actionButtonLabel(action: string): string {
  if (action === "retrieval_validation") return "检索验收";
  if (action === "milvus_backfill") return "Milvus dry-run";
  if (action === "review_issues") return "查看问题";
  return "执行";
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;
  if (!data) return null;

  const qualityColumns = [
    {
      title: "数据域",
      dataIndex: "name",
      key: "name",
      render: (name: string) => DOMAIN_META[name]?.label ?? name,
    },
    {
      title: "就绪",
      key: "ready",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="ready" /> {record.quality.ready ?? 0}
        </span>
      ),
    },
    {
      title: "待审核",
      key: "needs_review",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="needs_review" />{" "}
          {record.quality.needs_review ?? 0}
        </span>
      ),
    },
    {
      title: "低置信度",
      key: "low_confidence",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="low_confidence" />{" "}
          {record.quality.low_confidence ?? 0}
        </span>
      ),
    },
    {
      title: "需补充",
      key: "needs_enrichment",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="needs_enrichment" />{" "}
          {record.quality.needs_enrichment ?? 0}
        </span>
      ),
    },
    {
      title: "最后更新",
      key: "last_updated",
      render: (_: unknown, record: (typeof data.domains)[0]) =>
        formatDate(record.last_updated),
    },
  ];

  async function handleAction(action: PipelineAction) {
    if (action.action === "review_issues") {
      navigate("/pipeline-issues?resolved=false");
      return;
    }
    if (!action.run_id) return;
    setActionLoading(`${action.action}:${action.run_id}`);
    setActionError(null);
    try {
      if (action.action === "retrieval_validation") {
        const response = await triggerRetrievalValidation(action.run_id);
        navigate(`/pipeline-runs/${response.task_id}`);
        return;
      }
      if (action.action === "milvus_backfill") {
        const response = await triggerMilvusBackfill(action.run_id, {
          dryRun: true,
        });
        navigate(`/pipeline-runs/${response.task_id}`);
        return;
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionLoading(null);
    }
  }

  const stageColumns = [
    {
      title: "阶段",
      key: "stage",
      render: (_: unknown, record: PipelineStageSummary) => (
        <Space direction="vertical" size={0}>
          <Text strong>{stageLabel(record.stage)}</Text>
          <Text type="secondary">{record.stage}</Text>
        </Space>
      ),
    },
    {
      title: "最近数据域",
      key: "latest_domain",
      width: 120,
      render: (_: unknown, record: PipelineStageSummary) =>
        record.latest_domain ?? "-",
    },
    {
      title: "进度",
      key: "progress",
      render: (_: unknown, record: PipelineStageSummary) => (
        <Space wrap>
          <Tag>总计 {record.total}</Tag>
          {record.running > 0 && <Tag color="processing">运行 {record.running}</Tag>}
          {record.succeeded > 0 && <Tag color="success">成功 {record.succeeded}</Tag>}
          {record.partial > 0 && <Tag color="warning">部分 {record.partial}</Tag>}
          {record.failed > 0 && <Tag color="error">失败 {record.failed}</Tag>}
        </Space>
      ),
    },
    {
      title: "最近开始",
      key: "latest_started_at",
      width: 170,
      render: (_: unknown, record: PipelineStageSummary) =>
        formatDate(record.latest_started_at),
    },
    {
      title: "操作",
      key: "action",
      width: 110,
      render: (_: unknown, record: PipelineStageSummary) =>
        record.latest_run_id ? (
          <Button
            size="small"
            onClick={() => navigate(`/pipeline-runs/${record.latest_run_id}`)}
          >
            详情
          </Button>
        ) : (
          "-"
        ),
    },
  ];

  const failureColumns = [
    {
      title: "状态",
      key: "status",
      width: 100,
      render: (_: unknown, record: PipelineFailureSample) => (
        <Tag color={STATUS_COLOR[record.status] ?? "default"}>
          {record.status}
        </Tag>
      ),
    },
    {
      title: "阶段 / 数据域",
      key: "stage",
      render: (_: unknown, record: PipelineFailureSample) => (
        <Space direction="vertical" size={0}>
          <Text strong>{stageLabel(record.run_kind)}</Text>
          <Text type="secondary">{record.domain ?? "-"}</Text>
        </Space>
      ),
    },
    {
      title: "处理 / 失败",
      key: "counts",
      width: 120,
      render: (_: unknown, record: PipelineFailureSample) =>
        `${record.items_processed ?? "-"} / ${record.items_failed ?? "-"}`,
    },
    {
      title: "错误摘要",
      key: "error",
      ellipsis: true,
      render: (_: unknown, record: PipelineFailureSample) =>
        record.error_summary ? JSON.stringify(record.error_summary) : "-",
    },
    {
      title: "开始时间",
      key: "started_at",
      width: 170,
      render: (_: unknown, record: PipelineFailureSample) =>
        formatDate(record.started_at),
    },
    {
      title: "操作",
      key: "action",
      width: 110,
      render: (_: unknown, record: PipelineFailureSample) => (
        <Button
          size="small"
          onClick={() => navigate(`/pipeline-runs/${record.run_id}`)}
        >
          详情
        </Button>
      ),
    },
  ];

  const issueColumns = [
    {
      title: "等级",
      key: "severity",
      width: 90,
      render: (_: unknown, record: PipelineIssueSample) => (
        <Tag color={SEVERITY_COLOR[record.severity] ?? "default"}>
          {record.severity}
        </Tag>
      ),
    },
    {
      title: "类型",
      key: "type",
      render: (_: unknown, record: PipelineIssueSample) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.issue_type ?? "-"}</Text>
          <Text type="secondary">{record.domain ?? "-"}</Text>
        </Space>
      ),
    },
    {
      title: "描述",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
    },
    {
      title: "源行",
      key: "source_rows",
      width: 120,
      render: (_: unknown, record: PipelineIssueSample) =>
        record.source_rows.length > 0 ? record.source_rows.join(", ") : "-",
    },
    {
      title: "建议",
      key: "recommended_action",
      ellipsis: true,
      render: (_: unknown, record: PipelineIssueSample) =>
        record.recommended_action ?? "-",
    },
    {
      title: "操作",
      key: "action",
      width: 110,
      render: (_: unknown, record: PipelineIssueSample) => {
        const params = new URLSearchParams({ resolved: "false" });
        if (record.task_id) params.set("task_id", record.task_id);
        if (record.domain) params.set("domain", record.domain);
        if (record.issue_type) params.set("issue_type", record.issue_type);
        return (
          <Button
            size="small"
            icon={<WarningOutlined />}
            onClick={() => navigate(`/pipeline-issues?${params.toString()}`)}
          >
            处理
          </Button>
        );
      },
    },
  ];

  const actionColumns = [
    {
      title: "动作",
      key: "label",
      render: (_: unknown, record: PipelineAction) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.label}</Text>
          <Text type="secondary">{record.reason}</Text>
        </Space>
      ),
    },
    {
      title: "数据域",
      dataIndex: "domain",
      key: "domain",
      width: 100,
      render: (domain: string | null) => domain ?? "-",
    },
    {
      title: "执行",
      key: "execute",
      width: 150,
      render: (_: unknown, record: PipelineAction) => (
        <Button
          size="small"
          icon={
            record.action === "milvus_backfill" ? (
              <PlayCircleOutlined />
            ) : (
              <CheckCircleOutlined />
            )
          }
          loading={actionLoading === `${record.action}:${record.run_id}`}
          onClick={() => handleAction(record)}
        >
          {actionButtonLabel(record.action)}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>数据总览</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {data.domains.map((d) => (
          <Col key={d.name} xs={12} sm={6}>
            <StatCard
              title={DOMAIN_META[d.name]?.label ?? d.name}
              value={d.count}
              icon={DOMAIN_META[d.name]?.icon}
              lastUpdated={formatDate(d.last_updated)}
            />
          </Col>
        ))}
      </Row>
      <Title level={4}>采集运维</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <StatCard
            title="运行中任务"
            value={data.ops.active_runs}
            icon={<PlayCircleOutlined />}
            lastUpdated={formatDate(data.ops.generated_at)}
          />
        </Col>
        <Col xs={24} sm={8}>
          <StatCard
            title="近期异常任务"
            value={data.ops.recent_failed_runs}
            icon={<WarningOutlined />}
            lastUpdated={formatDate(data.ops.generated_at)}
          />
        </Col>
        <Col xs={24} sm={8}>
          <StatCard
            title="开放质量问题"
            value={data.ops.open_issue_count}
            icon={<SafetyCertificateOutlined />}
            lastUpdated={formatDate(data.ops.generated_at)}
          />
        </Col>
      </Row>
      {actionError && (
        <Alert
          type="error"
          showIcon
          message={actionError}
          style={{ marginBottom: 16 }}
        />
      )}
      <Space direction="vertical" size={24} style={{ width: "100%" }}>
        <div>
          <Title level={5}>阶段进度</Title>
          <Table<PipelineStageSummary>
            rowKey="stage"
            size="small"
            dataSource={data.ops.stages}
            columns={stageColumns}
            pagination={false}
          />
        </div>
        <div>
          <Title level={5}>待处理动作</Title>
          <Table<PipelineAction>
            rowKey={(record) => `${record.action}:${record.run_id ?? "issues"}`}
            size="small"
            dataSource={data.ops.actions}
            columns={actionColumns}
            pagination={false}
            locale={{ emptyText: "暂无待处理动作" }}
          />
        </div>
        <div>
          <Title level={5}>失败样例</Title>
          <Table<PipelineFailureSample>
            rowKey="run_id"
            size="small"
            dataSource={data.ops.failure_samples}
            columns={failureColumns}
            pagination={false}
            locale={{ emptyText: "暂无失败样例" }}
          />
        </div>
        <div>
          <Title level={5}>开放质量问题样例</Title>
          <Table<PipelineIssueSample>
            rowKey="issue_id"
            size="small"
            dataSource={data.ops.issue_samples}
            columns={issueColumns}
            pagination={false}
            locale={{ emptyText: "暂无开放质量问题" }}
          />
        </div>
      </Space>
      <Title level={4}>质量概览</Title>
      <Table
        dataSource={data.domains}
        columns={qualityColumns}
        rowKey="name"
        pagination={false}
        size="middle"
      />
    </div>
  );
}
