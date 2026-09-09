import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Button,
  Descriptions,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Alert,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  EyeOutlined,
  FileSearchOutlined,
  MessageOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import type { TablePaginationConfig } from "antd";
import {
  fetchPipelineIssueSourceRows,
  fetchPipelineIssues,
  updatePipelineIssue,
  type PipelineIssue,
  type PipelineIssueListResponse,
  type PipelineIssueSourceRowsResponse,
  type SourceRowPreview,
} from "../api";

const { Text, Title } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  low: "default",
  medium: "warning",
  high: "error",
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

function evidenceText(issue: PipelineIssue, key: string): string {
  const value = issue.evidence_snapshot?.[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function issueTypeText(issue: PipelineIssue): string {
  return issue.issue_type || evidenceText(issue, "issue_type") || "-";
}

function domainText(issue: PipelineIssue): string {
  return issue.domain || evidenceText(issue, "domain") || "-";
}

function taskIdText(issue: PipelineIssue): string {
  return issue.task_id || evidenceText(issue, "task_id");
}

function recommendedActionText(issue: PipelineIssue): string {
  return issue.recommended_action || evidenceText(issue, "recommended_action") || "-";
}

function sourceRowsText(issue: PipelineIssue): string {
  if (issue.source_rows.length > 0) return issue.source_rows.join(", ");
  const value = issue.evidence_snapshot?.source_rows;
  if (!Array.isArray(value)) return "-";
  return value.map(String).join(", ");
}

function hasSourceRows(issue: PipelineIssue): boolean {
  if (issue.source_rows.length > 0) return true;
  const value = issue.evidence_snapshot?.source_rows;
  return Array.isArray(value) && value.length > 0;
}

function isChatFeedback(issue: PipelineIssue): boolean {
  return (
    issue.reported_by === "chat_user_feedback" ||
    issueTypeText(issue) === "chat_feedback"
  );
}

function sourceRowText(row: SourceRowPreview): string {
  return row.cells
    .map((cell) => {
      const label = cell.header || cell.column_letter;
      return `${label}: ${cell.value ?? "-"}`;
    })
    .join(" / ");
}

function shortText(value: string | null | undefined, maxLength = 120): string {
  if (!value) return "-";
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function resolveBoolean(value: string | null): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

function IssueDetail({ issue }: { issue: PipelineIssue }) {
  const chat = issue.chat_feedback;
  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      <Descriptions
        size="small"
        column={2}
        items={[
          {
            key: "issue_id",
            label: "Issue ID",
            children: <Text copyable>{issue.issue_id}</Text>,
          },
          {
            key: "status",
            label: "状态",
            children: issue.resolved ? "已处理" : "待处理",
          },
          {
            key: "type",
            label: "类型",
            children: issueTypeText(issue),
          },
          {
            key: "domain",
            label: "数据域",
            children: domainText(issue),
          },
          {
            key: "reported_by",
            label: "来源",
            children: issue.reported_by ?? "-",
          },
          {
            key: "reported_at",
            label: "时间",
            children: formatDate(issue.reported_at),
          },
          {
            key: "session_id",
            label: "Session",
            children: chat?.session_id ?? "-",
          },
          {
            key: "task_id",
            label: "任务 ID",
            children: taskIdText(issue) || "-",
          },
        ]}
      />
      <div>
        <Text strong>描述</Text>
        <Typography.Paragraph style={{ marginTop: 6, marginBottom: 0 }}>
          {issue.description}
        </Typography.Paragraph>
      </div>
      {chat && (
        <>
          <div>
            <Text strong>问题</Text>
            <Typography.Paragraph style={{ marginTop: 6, marginBottom: 0 }}>
              {chat.query ?? "-"}
            </Typography.Paragraph>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {chat.query_type ?? "-"} · {chat.answer_style ?? "-"} ·{" "}
              {chat.feedback_type ?? "-"}
            </Text>
          </div>
          <div>
            <Text strong>回答</Text>
            <Typography.Paragraph
              style={{ whiteSpace: "pre-wrap", marginTop: 6, marginBottom: 0 }}
            >
              {chat.answer_text ?? "-"}
            </Typography.Paragraph>
          </div>
          {chat.citations.length > 0 && (
            <div>
              <Text strong>引用</Text>
              <Space size={[4, 4]} wrap style={{ marginTop: 6, display: "flex" }}>
                {chat.citations.map((citation, idx) => (
                  <Tag key={`${citation.type}:${citation.id}:${idx}`}>
                    [{idx + 1}] {citation.label || citation.id}
                  </Tag>
                ))}
              </Space>
            </div>
          )}
          {chat.note && (
            <Alert type="warning" message={chat.note} showIcon={false} />
          )}
        </>
      )}
      <div>
        <Text strong>建议</Text>
        <Typography.Paragraph style={{ marginTop: 6, marginBottom: 0 }}>
          {recommendedActionText(issue)}
        </Typography.Paragraph>
      </div>
    </Space>
  );
}

export default function PipelineIssues() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const searchString = searchParams.toString();
  const [data, setData] = useState<PipelineIssueListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionIssueId, setActionIssueId] = useState<string | null>(null);
  const [preview, setPreview] =
    useState<PipelineIssueSourceRowsResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [detailIssue, setDetailIssue] = useState<PipelineIssue | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams(searchString);
    const page = Number(params.get("page") ?? "1");
    const pageSize = Number(params.get("page_size") ?? "50");
    return {
      stage: params.get("stage") || undefined,
      severity: params.get("severity") || undefined,
      resolved: resolveBoolean(params.get("resolved")),
      reported_by: params.get("reported_by") || undefined,
      professor_id: params.get("professor_id") || undefined,
      task_id: params.get("task_id") || undefined,
      domain: params.get("domain") || undefined,
      issue_type: params.get("issue_type") || undefined,
      q: params.get("q") || undefined,
      page: Number.isFinite(page) && page > 0 ? page : 1,
      page_size: Number.isFinite(pageSize) && pageSize > 0 ? pageSize : 50,
    };
  }, [searchString]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchPipelineIssues(query)
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  const handleIssueState = async (issue: PipelineIssue, resolved: boolean) => {
    setActionIssueId(issue.issue_id);
    try {
      await updatePipelineIssue(issue.issue_id, {
        resolved,
        resolution_notes: resolved
          ? "resolved from admin-console"
          : "reopened from admin-console",
        resolution_round: "admin-console",
      });
      message.success(resolved ? "已关闭" : "已重开");
      load();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setActionIssueId(null);
    }
  };

  const openSourceRows = async (issue: PipelineIssue) => {
    setPreview(null);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      setPreview(await fetchPipelineIssueSourceRows(issue.issue_id));
    } catch (err: unknown) {
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  };

  const updatePagination = (pagination: TablePaginationConfig) => {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(pagination.current ?? 1));
    next.set("page_size", String(pagination.pageSize ?? 50));
    setSearchParams(next);
  };

  const applyQuickFilter = (values: Record<string, string | boolean>) => {
    const next = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) {
      next.set(key, String(value));
    }
    next.set("page", "1");
    next.set("page_size", String(query.page_size));
    setSearchParams(next);
  };

  const filterTags = [
    ["任务", query.task_id],
    ["数据域", query.domain],
    ["类型", query.issue_type],
    ["来源", query.reported_by],
    ["阶段", query.stage],
    ["级别", query.severity],
    ["状态", query.resolved === undefined ? undefined : query.resolved ? "已处理" : "待处理"],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  if (loading && !data) return <Spin size="large" style={{ marginTop: 100 }} />;

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          质量问题
        </Title>
        <Button
          icon={<MessageOutlined />}
          onClick={() =>
            applyQuickFilter({
              reported_by: "chat_user_feedback",
              issue_type: "chat_feedback",
              resolved: false,
            })
          }
        >
          待处理对话反馈
        </Button>
        <Button
          icon={<FileSearchOutlined />}
          onClick={() =>
            applyQuickFilter({
              reported_by: "admin_upload_dry_run",
              resolved: false,
            })
          }
        >
          待处理导入问题
        </Button>
        {filterTags.map(([label, value]) => (
          <Tag key={label}>
            {label}: {value}
          </Tag>
        ))}
        {filterTags.length > 0 && (
          <Button
            icon={<CloseOutlined />}
            onClick={() => setSearchParams(new URLSearchParams())}
          >
            清除
          </Button>
        )}
      </Space>
      {error && (
        <Text type="danger" style={{ display: "block", marginBottom: 12 }}>
          {error}
        </Text>
      )}
      <Table<PipelineIssue>
        rowKey="issue_id"
        size="middle"
        loading={loading}
        dataSource={data?.items ?? []}
        onChange={updatePagination}
        pagination={{
          current: data?.page ?? query.page,
          pageSize: data?.page_size ?? query.page_size,
          total: data?.total ?? 0,
          showSizeChanger: true,
        }}
        columns={[
          {
            title: "级别",
            key: "severity",
            width: 100,
            render: (_, record) => (
              <Tag color={SEVERITY_COLOR[record.severity] ?? "default"}>
                {record.severity}
              </Tag>
            ),
          },
          {
            title: "描述",
            dataIndex: "description",
            key: "description",
            render: (_, record) => (
              <Space direction="vertical" size={2}>
                <Text>{record.description}</Text>
                {record.chat_feedback?.query && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    问：{shortText(record.chat_feedback.query)}
                  </Text>
                )}
              </Space>
            ),
          },
          {
            title: "类型",
            key: "issue_type",
            width: 160,
            render: (_, record) => {
              const issueType = issueTypeText(record);
              return (
                <Tag color={issueType === "chat_feedback" ? "processing" : "default"}>
                  {issueType}
                </Tag>
              );
            },
          },
          {
            title: "源行",
            key: "source_rows",
            width: 150,
            render: (_, record) =>
              isChatFeedback(record) ? (
                <Tag icon={<MessageOutlined />}>对话</Tag>
              ) : (
                sourceRowsText(record)
              ),
          },
          {
            title: "数据域",
            key: "domain",
            width: 100,
            render: (_, record) => domainText(record),
          },
          {
            title: "建议",
            key: "recommended_action",
            width: 240,
            render: (_, record) => recommendedActionText(record),
          },
          {
            title: "任务 ID",
            key: "task_id",
            width: 270,
            render: (_, record) => {
              const taskId = taskIdText(record);
              return taskId ? <Text copyable>{taskId}</Text> : "-";
            },
          },
          {
            title: "来源",
            dataIndex: "reported_by",
            key: "reported_by",
            width: 190,
            render: (value: string | null) => value ?? "-",
          },
          {
            title: "时间",
            key: "reported_at",
            width: 170,
            render: (_, record) => formatDate(record.reported_at),
          },
          {
            title: "状态",
            key: "resolved",
            width: 90,
            render: (_, record) => (
              <Tag color={record.resolved ? "success" : "warning"}>
                {record.resolved ? "已处理" : "待处理"}
              </Tag>
            ),
          },
          {
            title: "操作",
            key: "actions",
            width: 230,
            render: (_, record) => {
              const taskId = taskIdText(record);
              const nextResolved = !record.resolved;
              return (
                <Space size={4}>
                  <Button
                    type="link"
                    icon={<EyeOutlined />}
                    onClick={() => setDetailIssue(record)}
                  >
                    详情
                  </Button>
                  {taskId && (
                    <Button
                      type="link"
                      icon={<ClockCircleOutlined />}
                      onClick={() => navigate(`/pipeline-runs/${taskId}`)}
                    >
                      任务
                    </Button>
                  )}
                  {hasSourceRows(record) && (
                    <Button
                      type="link"
                      icon={<FileSearchOutlined />}
                      onClick={() => openSourceRows(record)}
                    >
                      源行
                    </Button>
                  )}
                  <Popconfirm
                    title={nextResolved ? "确认关闭该问题？" : "确认重新打开？"}
                    okText="确认"
                    cancelText="取消"
                    onConfirm={() => handleIssueState(record, nextResolved)}
                  >
                    <Button
                      type="link"
                      icon={
                        nextResolved ? <CheckCircleOutlined /> : <ReloadOutlined />
                      }
                      loading={actionIssueId === record.issue_id}
                    >
                      {nextResolved ? "关闭" : "重开"}
                    </Button>
                  </Popconfirm>
                </Space>
              );
            },
          },
        ]}
      />
      <Modal
        title="原始行预览"
        open={previewLoading || preview !== null || previewError !== null}
        onCancel={() => {
          setPreview(null);
          setPreviewError(null);
          setPreviewLoading(false);
        }}
        footer={null}
        width={960}
      >
        {previewLoading && <Spin />}
        {previewError && <Text type="danger">{previewError}</Text>}
        {preview && (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space wrap>
              {preview.sheet_name && <Tag>Sheet: {preview.sheet_name}</Tag>}
              {preview.header_row_number && (
                <Tag>表头行: {preview.header_row_number}</Tag>
              )}
              {preview.warning && <Tag color="warning">{preview.warning}</Tag>}
            </Space>
            {preview.upload_path && (
              <Text type="secondary" copyable>
                {preview.upload_path}
              </Text>
            )}
            <Table<SourceRowPreview>
              rowKey="row_number"
              size="small"
              pagination={false}
              dataSource={preview.rows}
              columns={[
                {
                  title: "Excel 行",
                  dataIndex: "row_number",
                  key: "row_number",
                  width: 120,
                },
                {
                  title: "内容",
                  key: "cells",
                  render: (_, record) => sourceRowText(record),
                },
              ]}
            />
          </Space>
        )}
      </Modal>
      <Modal
        title="问题详情"
        open={detailIssue !== null}
        onCancel={() => setDetailIssue(null)}
        footer={null}
        width={960}
      >
        {detailIssue && <IssueDetail issue={detailIssue} />}
      </Modal>
    </div>
  );
}
