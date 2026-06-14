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
  Progress,
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
  type CompanyEnrichmentBatchStatus,
  type PipelineRun,
  type PipelineRunDetail,
  type PipelineRunSourcePage,
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
  if (isCompanyUpload(detail)) {
    const batches = detail.company_enrichment_batches ?? [];
    if (batches.some((batch) => ACTIVE_STATUSES.has(batch.status))) {
      return false;
    }
    if (
      batches.length > 0 &&
      batches.every(
        (batch) =>
          batch.status === "succeeded" &&
          batch.companies_selected > 0 &&
          batch.vector_refreshed_count >= batch.companies_selected
      )
    ) {
      return false;
    }
  }
  const summary = resultSummary(scope);
  return summary.milvus_backfill_required === true || detail.status === "succeeded";
}

function canTriggerRetrievalValidation(detail: PipelineRunDetail): boolean {
  const domain = detail.run_scope.domain;
  return (
    detail.run_kind === "import_xlsx" &&
    ["patent", "paper", "professor"].includes(String(domain))
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

function hasActiveProcessing(detail: PipelineRunDetail): boolean {
  if (ACTIVE_STATUSES.has(detail.status)) return true;
  return (detail.company_enrichment_batches ?? []).some((batch) =>
    ACTIVE_STATUSES.has(batch.status)
  );
}

function mapEntries(map?: Record<string, number>): [string, number][] {
  if (!map) return [];
  return Object.entries(map)
    .filter(([, value]) => Number(value) > 0)
    .sort(([left], [right]) => left.localeCompare(right));
}

function renderCountMap(map?: Record<string, number>) {
  const entries = mapEntries(map);
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

function renderSourceCounts(
  map?: Record<string, Record<string, number>>
) {
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

function renderCompanyDiagnostics(batch: CompanyEnrichmentBatchStatus) {
  const diagnostics = batch.company_diagnostics ?? [];
  if (diagnostics.length === 0) return "-";
  return (
    <Space direction="vertical" size={2}>
      {diagnostics.slice(0, 8).map((item) => (
        <Text key={item.company_id}>
          {item.company_id}: {item.status} / {item.current_stage ?? "-"} /{" "}
          {item.miss_reason ?? item.last_error ?? "-"}
        </Text>
      ))}
      {batch.company_diagnostics_truncated && (
        <Text type="secondary">仅显示前 50 条公司诊断</Text>
      )}
    </Space>
  );
}

function renderQualityHeadline(batch: CompanyEnrichmentBatchStatus) {
  const headline =
    typeof batch.quality_report?.headline === "string"
      ? batch.quality_report.headline
      : "";
  return headline || "-";
}

function isCompanyUpload(detail: PipelineRunDetail): boolean {
  return (
    detail.run_kind === "import_xlsx" &&
    String(detail.run_scope.domain ?? "") === "company"
  );
}

function latestCompanyBatch(
  batches: CompanyEnrichmentBatchStatus[]
): CompanyEnrichmentBatchStatus | null {
  if (batches.length === 0) return null;
  return [...batches].sort((left, right) =>
    String(right.created_at ?? "").localeCompare(String(left.created_at ?? ""))
  )[0];
}

function companyUploadConclusion(
  detail: PipelineRunDetail,
  batch: CompanyEnrichmentBatchStatus | null
): { status: string; tone: string; lines: string[] } {
  if (detail.status === "failed") {
    return {
      status: "上传导入失败",
      tone: "error",
      lines: ["基础数据未完成导入，请先查看任务错误和源文件格式。"],
    };
  }
  if (!batch) {
    return {
      status: "基础导入已完成",
      tone: "default",
      lines: [
        "基础数据已导入，企业详情页可查看。",
        "后台增强批次尚未创建，产品、场景、动态和检索刷新状态还不可判断。",
      ],
    };
  }
  if (batch.status === "succeeded") {
    return {
      status: "处理已完成",
      tone: "success",
      lines: [
        "基础数据已导入，企业详情页可查看。",
        "外部增强、产品/场景抽取和检索刷新已结束，可以在企业页面搜索。",
      ],
    };
  }
  if (batch.status === "running") {
    return {
      status: "后台增强正在运行",
      tone: "processing",
      lines: [
        "基础数据已导入，企业详情页可查看。",
        "外部增强正在执行，完成后会更新产品、场景、动态和简介。",
      ],
    };
  }
  if (batch.status === "partial") {
    return {
      status: "部分完成，仍有失败项",
      tone: "warning",
      lines: [
        "已完成的企业可以查看和搜索。",
        "失败或未命中的企业需要看批次诊断后决定是否重跑。",
      ],
    };
  }
  if (batch.status === "failed") {
    return {
      status: "后台增强失败",
      tone: "error",
      lines: [
        "基础导入可能已经完成，但外部增强没有闭环。",
        "请打开批次查看失败阶段和错误原因后重跑。",
      ],
    };
  }
  return {
    status: "后台增强等待中",
    tone: "default",
    lines: [
      "基础数据已导入，企业详情页可查看。",
      "后台增强正在排队，完成后会更新产品、场景、动态和检索刷新状态。",
    ],
  };
}

function companyProcessingStageText(batch: CompanyEnrichmentBatchStatus | null) {
  if (!batch) return "当前阶段：等待创建增强批次";
  return `当前阶段：${batch.current_stage ?? batch.status}`;
}

function renderCompanyUploadOverview(
  detail: PipelineRunDetail,
  batches: CompanyEnrichmentBatchStatus[],
  navigate: (path: string) => void
) {
  if (!isCompanyUpload(detail)) return null;
  const batch = latestCompanyBatch(batches);
  const conclusion = companyUploadConclusion(detail, batch);
  const selected = batch?.companies_selected ?? detail.items_processed ?? 0;
  const processed = batch?.companies_processed ?? detail.items_processed ?? 0;
  const succeeded = batch?.companies_succeeded ?? 0;
  const failed = batch?.companies_failed ?? detail.items_failed ?? 0;
  const products = batch?.product_count ?? 0;
  const scenarios = batch?.scenario_count ?? 0;
  const events = batch?.funding_event_count ?? 0;
  const vectors = batch?.vector_refreshed_count ?? 0;
  const progress = batch?.progress_percent ?? (detail.status === "succeeded" ? 100 : 0);

  return (
    <div>
      <Space wrap style={{ marginTop: 24, marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          企业上传处理总览
        </Title>
        <Tag color={conclusion.tone}>{conclusion.status}</Tag>
        <Tag>以实时增强批次为准</Tag>
        <Button size="small" onClick={() => navigate("/company")}>
          打开企业列表
        </Button>
        {batch && (
          <Button
            size="small"
            onClick={() => navigate(`/company-enrichment-batches/${batch.batch_id}`)}
          >
            打开增强批次
          </Button>
        )}
      </Space>
      <Descriptions bordered size="small" column={2}>
        <Descriptions.Item label="当前结论" span={2}>
          <Space direction="vertical" size={2}>
            {conclusion.lines.map((line) => (
              <Text key={line}>{line}</Text>
            ))}
            <Text type="secondary">{companyProcessingStageText(batch)}</Text>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="总进度">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Progress percent={progress} size="small" />
            <Text>
              {processed} / {selected}
            </Text>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="导入结果">
          {detail.items_processed ?? "-"} / 失败 {detail.items_failed ?? 0}
        </Descriptions.Item>
        <Descriptions.Item label="已处理企业">
          {processed} / {selected}
        </Descriptions.Item>
        <Descriptions.Item label="成功/失败">
          {succeeded} / {failed}
        </Descriptions.Item>
        <Descriptions.Item label="产品/场景/动态">
          {products} / {scenarios} / {events}
        </Descriptions.Item>
        <Descriptions.Item label="检索刷新">
          {vectors} / {selected}
        </Descriptions.Item>
        <Descriptions.Item label="外部来源接受/拒绝">
          {batch ? `${batch.accepted_source_count} / ${batch.rejected_source_count}` : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="后台心跳">
          {batch ? formatDate(batch.runner_heartbeat_at) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="最后完成企业">
          {batch?.last_completed_company_id ?? "-"}
        </Descriptions.Item>
        <Descriptions.Item label="质量报告" span={2}>
          {batch ? renderQualityHeadline(batch) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="最后错误">
          {batch?.last_error ??
            (detail.error_summary ? JSON.stringify(detail.error_summary) : "-")}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
}

function renderBatchDiagnostics(record: CompanyEnrichmentBatchStatus) {
  return (
    <Descriptions bordered size="small" column={2}>
      <Descriptions.Item label="来源查询/结果">
        {record.query_count} / {record.source_result_count}
      </Descriptions.Item>
      <Descriptions.Item label="来源接受/拒绝">
        {record.accepted_source_count} / {record.rejected_source_count}
      </Descriptions.Item>
      <Descriptions.Item label="产品/场景/动态">
        {record.product_count} / {record.scenario_count} /{" "}
        {record.funding_event_count}
      </Descriptions.Item>
      <Descriptions.Item label="官网产品/向量刷新">
        {record.official_product_count} / {record.vector_refreshed_count}
      </Descriptions.Item>
      <Descriptions.Item label="状态分布">
        {renderCountMap(record.status_counts)}
      </Descriptions.Item>
      <Descriptions.Item label="阶段分布">
        {renderCountMap(record.current_stage_counts)}
      </Descriptions.Item>
      <Descriptions.Item label="未命中原因">
        {renderCountMap(record.miss_reasons)}
      </Descriptions.Item>
      <Descriptions.Item label="运营原因分类">
        {renderCountMap(record.miss_reason_buckets)}
      </Descriptions.Item>
      <Descriptions.Item label="官网失败原因">
        {renderCountMap(record.official_failure_reasons)}
      </Descriptions.Item>
      <Descriptions.Item label="候选拒绝原因" span={2}>
        {renderCountMap(record.rejected_candidate_reasons)}
      </Descriptions.Item>
      <Descriptions.Item label="来源分布" span={2}>
        {renderSourceCounts(record.source_counts_by_adapter)}
      </Descriptions.Item>
      <Descriptions.Item label="公司级诊断样例" span={2}>
        {renderCompanyDiagnostics(record)}
      </Descriptions.Item>
      <Descriptions.Item label="后台心跳">
        {formatDate(record.runner_heartbeat_at)}
      </Descriptions.Item>
      <Descriptions.Item label="最后完成企业">
        {record.last_completed_company_id ?? "-"}
      </Descriptions.Item>
      <Descriptions.Item label="日志路径" span={2}>
        {record.runner_log_path ? <Text copyable>{record.runner_log_path}</Text> : "-"}
      </Descriptions.Item>
    </Descriptions>
  );
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
    let cancelled = false;
    setLoading(true);
    if (runId) {
      fetchPipelineRun(runId)
        .then((data) => {
          if (!cancelled) setDetail(data);
        })
        .finally(() => setLoading(false));
      return () => {
        cancelled = true;
      };
    }
    fetchPipelineRuns({ triggered_by: "admin-console", limit: 100 })
      .then((data) => {
        if (!cancelled) setItems(data.items);
      })
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    if (!runId || !detail || !hasActiveProcessing(detail)) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchPipelineRun(runId)
        .then(setDetail)
        .catch((error) =>
          setActionError(error instanceof Error ? error.message : String(error))
        );
    }, 5000);
    return () => window.clearInterval(timer);
  }, [detail, runId]);

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;

  if (runId && detail) {
    const summary = resultSummary(detail.run_scope);
    const summaryEntries = Object.entries(summary);
    const backfillEnabled = canTriggerMilvusBackfill(detail);
    const retrievalValidationEnabled = canTriggerRetrievalValidation(detail);
    const issueLink = hasDataQualityIssues(summary)
      ? pipelineIssueLink(detail)
      : null;
    const companyEnrichmentBatches = detail.company_enrichment_batches ?? [];
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
        {renderCompanyUploadOverview(
          detail,
          companyEnrichmentBatches,
          navigate
        )}
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
        {companyEnrichmentBatches.length > 0 && (
          <div>
            <Title level={4} style={{ marginTop: 24 }}>
              企业增强处理状态
            </Title>
            <Table<CompanyEnrichmentBatchStatus>
              rowKey="batch_id"
              size="small"
              pagination={false}
              dataSource={companyEnrichmentBatches}
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
                {
                  title: "当前阶段",
                  dataIndex: "current_stage",
                  key: "current_stage",
                  render: (value) => value ?? "-",
                },
                {
                  title: "进度",
                  key: "progress",
                  width: 120,
                  render: (_, record) =>
                    `${record.companies_processed} / ${record.companies_selected}`,
                },
                {
                  title: "成功",
                  dataIndex: "companies_succeeded",
                  key: "companies_succeeded",
                  width: 90,
                },
                {
                  title: "失败",
                  dataIndex: "companies_failed",
                  key: "companies_failed",
                  width: 90,
                },
                {
                  title: "来源接受/拒绝",
                  key: "sources",
                  render: (_, record) =>
                    `${record.accepted_source_count} / ${record.rejected_source_count}`,
                },
                {
                  title: "产品/场景/动态",
                  key: "facts",
                  render: (_, record) =>
                    `${record.product_count} / ${record.scenario_count} / ${record.funding_event_count}`,
                },
                {
                  title: "向量刷新",
                  key: "vectors",
                  render: (_, record) =>
                    `${record.vector_refreshed_count} / ${record.companies_selected}`,
                },
                {
                  title: "更新时间",
                  key: "updated_at",
                  render: (_, record) => formatDate(record.updated_at),
                },
                {
                  title: "错误",
                  dataIndex: "last_error",
                  key: "last_error",
                  render: (value) => value ?? "-",
                },
                {
                  title: "操作",
                  key: "actions",
                  width: 120,
                  render: (_, record) => (
                    <Button
                      size="small"
                      onClick={() =>
                        navigate(`/company-enrichment-batches/${record.batch_id}`)
                      }
                    >
                      打开批次
                    </Button>
                  ),
                },
              ]}
              expandable={{
                defaultExpandAllRows: true,
                expandedRowRender: renderBatchDiagnostics,
              }}
            />
          </div>
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
