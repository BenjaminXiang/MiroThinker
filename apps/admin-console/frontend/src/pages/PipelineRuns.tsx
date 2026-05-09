import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  CheckCircleOutlined,
  PlayCircleOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Button,
  Descriptions,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  fetchPipelineRun,
  fetchPipelineRuns,
  triggerMilvusBackfill,
  triggerRetrievalValidation,
  type PipelineRun,
  type PipelineRunDetail,
  type PipelineRunSourcePage,
} from "../api";

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  running: "processing",
  succeeded: "success",
  partial: "warning",
  failed: "error",
};

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

function scopeText(scope: Record<string, unknown>): string {
  const domain = typeof scope.domain === "string" ? scope.domain : "";
  const filename = typeof scope.filename === "string" ? scope.filename : "";
  return [domain, filename].filter(Boolean).join(" / ") || "-";
}

const SUMMARY_LABELS: Record<string, string> = {
  imported: "写入/更新",
  batch_id: "批次 ID",
  team_members_inserted: "团队成员",
  funding_events_inserted: "融资事件",
  lineage_rows: "溯源行",
  rows_read: "读取行",
  records_parsed: "解析记录",
  skipped_rows: "跳过行",
  released_record_count: "发布记录",
  company_patent_link_candidates: "关联候选",
  company_patent_links_written: "关联写入",
  company_patent_link_errors: "关联失败",
  artifact_dir: "产物目录",
  milvus_backfill_required: "Milvus 回填",
  milvus_backfill_status: "Milvus 状态",
  milvus_backfill_command: "Milvus 命令",
  data_quality_issues: "质量问题",
  retrieval_validation_report: "检索验收",
};

function resultSummary(
  scope: Record<string, unknown>
): Record<string, unknown> {
  const summary = scope.result_summary;
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    return {};
  }
  return summary as Record<string, unknown>;
}

function formatSummaryValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return JSON.stringify(value);
}

function renderSummaryValue(key: string, value: unknown) {
  if (
    key === "retrieval_validation_report" &&
    value &&
    typeof value === "object" &&
    !Array.isArray(value)
  ) {
    const report = value as Record<string, unknown>;
    const gates = Array.isArray(report.gates) ? report.gates : [];
    return (
      <Space direction="vertical" size={4}>
        <Space wrap>
          <Tag color={report.result === "PASS" ? "success" : "error"}>
            {String(report.result ?? "-")}
          </Tag>
          <Text>失败: {String(report.failures ?? "-")}</Text>
          {typeof report.run_id === "string" && (
            <Text copyable>任务: {report.run_id}</Text>
          )}
        </Space>
        {typeof report.log_file === "string" && (
          <Text type="secondary" copyable>
            {report.log_file}
          </Text>
        )}
        {gates.length > 0 && (
          <Space wrap>
            {gates.map((gate, index) => {
              const item =
                gate && typeof gate === "object"
                  ? (gate as Record<string, unknown>)
                  : {};
              return (
                <Tag key={`${String(item.label ?? "gate")}-${index}`}>
                  {String(item.label ?? "gate")}:{" "}
                  {String(item.query_type ?? "-")} / 引用{" "}
                  {String(item.citations_count ?? "-")}
                </Tag>
              );
            })}
          </Space>
        )}
      </Space>
    );
  }
  return formatSummaryValue(value);
}

function canTriggerMilvusBackfill(detail: PipelineRunDetail): boolean {
  const scope = detail.run_scope;
  if (scope.action === "milvus_backfill") return false;
  const domain = scope.domain;
  if (!["company", "patent", "paper", "professor"].includes(String(domain))) {
    return false;
  }
  const summary = resultSummary(scope);
  return summary.milvus_backfill_required === true || detail.status === "succeeded";
}

function canTriggerRetrievalValidation(detail: PipelineRunDetail): boolean {
  const domain = detail.run_scope.domain;
  return (
    detail.run_kind === "import_xlsx" &&
    ["company", "patent", "paper", "professor"].includes(String(domain))
  );
}

function hasDataQualityIssues(summary: Record<string, unknown>): boolean {
  const issues = summary.data_quality_issues;
  return Array.isArray(issues) && issues.length > 0;
}

function pipelineIssueLink(detail: PipelineRunDetail): string {
  const params = new URLSearchParams({
    task_id: detail.run_id,
    reported_by: "admin_upload_dry_run",
  });
  const domain = detail.run_scope.domain;
  if (typeof domain === "string" && domain) {
    params.set("domain", domain);
  }
  return `/pipeline-issues?${params.toString()}`;
}

export default function PipelineRuns() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [items, setItems] = useState<PipelineRun[]>([]);
  const [detail, setDetail] = useState<PipelineRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    if (runId) {
      fetchPipelineRun(runId)
        .then(setDetail)
        .finally(() => setLoading(false));
      return;
    }
    fetchPipelineRuns({ triggered_by: "admin-console", limit: 100 })
      .then((data) => setItems(data.items))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;

  if (runId && detail) {
    const summary = resultSummary(detail.run_scope);
    const summaryEntries = Object.entries(summary);
    const backfillEnabled = canTriggerMilvusBackfill(detail);
    const retrievalValidationEnabled = canTriggerRetrievalValidation(detail);
    const issueLink = hasDataQualityIssues(summary)
      ? pipelineIssueLink(detail)
      : null;
    async function handleMilvusBackfill() {
      if (!detail) return;
      setActionLoading(true);
      setActionError(null);
      try {
        const response = await triggerMilvusBackfill(detail.run_id);
        navigate(`/pipeline-runs/${response.task_id}`);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        setActionLoading(false);
      }
    }

    async function handleRetrievalValidation() {
      if (!detail) return;
      setActionLoading(true);
      setActionError(null);
      try {
        const response = await triggerRetrievalValidation(detail.run_id);
        navigate(`/pipeline-runs/${response.task_id}`);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : String(error));
      } finally {
        setActionLoading(false);
      }
    }

    return (
      <div>
        <Space wrap style={{ marginBottom: 16 }}>
          <Button onClick={() => navigate("/pipeline-runs")}>返回</Button>
          <Title level={3} style={{ margin: 0 }}>
            导入任务详情
          </Title>
          {backfillEnabled && (
            <Button
              icon={<PlayCircleOutlined />}
              loading={actionLoading}
              onClick={handleMilvusBackfill}
            >
              Milvus 回填
            </Button>
          )}
          {issueLink && (
            <Button
              icon={<WarningOutlined />}
              onClick={() => navigate(issueLink)}
            >
              质量问题
            </Button>
          )}
          {retrievalValidationEnabled && (
            <Button
              icon={<CheckCircleOutlined />}
              loading={actionLoading}
              onClick={handleRetrievalValidation}
            >
              检索验收
            </Button>
          )}
        </Space>
        {actionError && (
          <Text type="danger" style={{ display: "block", marginBottom: 12 }}>
            {actionError}
          </Text>
        )}
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="任务 ID" span={2}>
            <Text copyable>{detail.run_id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLOR[detail.status] ?? "default"}>
              {detail.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="类型">{detail.run_kind}</Descriptions.Item>
          <Descriptions.Item label="触发人">
            {detail.triggered_by ?? "-"}
          </Descriptions.Item>
          <Descriptions.Item label="范围">
            {scopeText(detail.run_scope)}
          </Descriptions.Item>
          <Descriptions.Item label="已处理">
            {detail.items_processed ?? "-"}
          </Descriptions.Item>
          <Descriptions.Item label="失败">
            {detail.items_failed ?? "-"}
          </Descriptions.Item>
          <Descriptions.Item label="开始">
            {formatDate(detail.started_at)}
          </Descriptions.Item>
          <Descriptions.Item label="结束">
            {formatDate(detail.finished_at)}
          </Descriptions.Item>
          <Descriptions.Item label="错误" span={2}>
            {detail.error_summary
              ? JSON.stringify(detail.error_summary)
              : "-"}
          </Descriptions.Item>
        </Descriptions>
        {summaryEntries.length > 0 && (
          <>
            <Title level={4} style={{ marginTop: 24 }}>
              导入摘要
            </Title>
            <Descriptions bordered size="small" column={2}>
              {summaryEntries.map(([key, value]) => (
                <Descriptions.Item
                  key={key}
                  label={SUMMARY_LABELS[key] ?? key}
                  span={
                    key === "artifact_dir" ||
                    key === "milvus_backfill_command" ||
                    key === "retrieval_validation_report"
                      ? 2
                      : 1
                  }
                >
                  {renderSummaryValue(key, value)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </>
        )}
        <Title level={4} style={{ marginTop: 24 }}>
          来源文件
        </Title>
        <Table<PipelineRunSourcePage>
          rowKey="page_id"
          size="small"
          pagination={false}
          dataSource={detail.source_pages}
          columns={[
            { title: "标题", dataIndex: "title", key: "title" },
            { title: "URL", dataIndex: "url", key: "url" },
            {
              title: "路径",
              dataIndex: "clean_text_path",
              key: "clean_text_path",
            },
            {
              title: "时间",
              key: "fetched_at",
              render: (_, record) => formatDate(record.fetched_at),
            },
          ]}
        />
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>导入任务</Title>
      <Table<PipelineRun>
        rowKey="run_id"
        size="middle"
        dataSource={items}
        pagination={{ pageSize: 20 }}
        onRow={(record) => ({
          onClick: () => navigate(`/pipeline-runs/${record.run_id}`),
          style: { cursor: "pointer" },
        })}
        columns={[
          {
            title: "状态",
            key: "status",
            width: 110,
            render: (_, record) => (
              <Tag color={STATUS_COLOR[record.status] ?? "default"}>
                {record.status}
              </Tag>
            ),
          },
          { title: "类型", dataIndex: "run_kind", key: "run_kind" },
          {
            title: "范围",
            key: "scope",
            render: (_, record) => scopeText(record.run_scope),
          },
          {
            title: "已处理",
            dataIndex: "items_processed",
            key: "items_processed",
            width: 100,
          },
          {
            title: "失败",
            dataIndex: "items_failed",
            key: "items_failed",
            width: 90,
          },
          {
            title: "开始时间",
            key: "started_at",
            render: (_, record) => formatDate(record.started_at),
          },
        ]}
      />
    </div>
  );
}
