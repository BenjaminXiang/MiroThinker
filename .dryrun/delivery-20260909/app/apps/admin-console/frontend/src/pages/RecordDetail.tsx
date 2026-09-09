import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  Descriptions,
  Spin,
  Typography,
  Button,
  Collapse,
  Result,
  Card,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Table,
  Tabs,
} from "antd";
import { ArrowLeftOutlined, EditOutlined } from "@ant-design/icons";
import {
  fetchDomainObject,
  fetchRelated,
  reviewCompanyEnrichmentItem,
  updateRecord,
  type ReleasedObject,
  type RelatedResponse,
} from "../api";
import QualityTag from "../components/QualityTag";
import LifecycleTag from "../components/LifecycleTag";
import EvidenceList from "../components/EvidenceList";
import ProfessorWorkbench from "./ProfessorWorkbench";

const { Title, Paragraph, Text } = Typography;

const DOMAIN_LABELS: Record<string, string> = {
  professor: "教授",
  company: "企业",
  paper: "论文",
  patent: "专利",
};

const FACT_LABELS: Record<string, string> = {
  name: "姓名",
  institution: "院校",
  department: "院系",
  title: "职称",
  email: "邮箱",
  homepage: "主页",
  research_directions: "研究方向",
  h_index: "H指数",
  citation_count: "引用数",
  paper_count: "论文数",
  industry: "行业",
  website: "官网",
  normalized_name: "标准名称",
  authors: "作者",
  year: "年份",
  venue: "期刊/会议",
  doi: "DOI",
  abstract: "摘要",
  patent_number: "专利号",
  patent_type: "专利类型",
  applicants: "申请人",
  inventors: "发明人",
  filing_date: "申请日",
  publication_date: "公开日",
  keywords: "关键词",
  ipc_codes: "IPC分类号",
  education: "教育经历",
  awards: "荣誉奖项",
  products: "产品",
  application_scenarios: "应用场景",
  recent_events: "最近动态",
};

const DOMAIN_FACT_LABELS: Record<string, Record<string, string>> = {
  paper: {
    title: "标题",
  },
  patent: {
    title: "标题",
  },
};

const SUMMARY_LABELS: Record<string, string> = {
  profile_summary: "个人简介",
  evaluation_summary: "评估摘要",
  technology_route_summary: "技术路线",
  summary_zh: "中文摘要",
  summary_text: "摘要",
};

const DOMAIN_SUMMARY_LABELS: Record<string, Record<string, string>> = {
  company: {
    profile_summary: "公司简介",
    technology_route_summary: "技术路线",
  },
};

// Fields rendered as tags
const TAG_FIELDS = new Set([
  "research_directions",
  "keywords",
  "ipc_codes",
  "applicants",
  "inventors",
  "authors",
]);

// Fields rendered as tables
const TABLE_FIELDS = new Set([
  "education",
  "awards",
  "products",
  "application_scenarios",
  "recent_events",
]);

const HIDDEN_FACT_FIELDS = new Set(["top_papers"]);

type ReviewAction = "accept" | "reject" | "needs_review";

type CompanyEnrichmentReview = {
  companyId: string;
  onReview: (
    targetType: "product" | "scenario",
    targetId: string,
    action: ReviewAction
  ) => void;
  reviewingKey: string | null;
};

function renderValue(
  key: string,
  value: unknown,
  review?: {
    companyId: string;
    onReview: (
      targetType: "product" | "scenario",
      targetId: string,
      action: ReviewAction
    ) => void;
    reviewingKey: string | null;
  }
): React.ReactNode {
  if (value == null) return "-";

  if (TAG_FIELDS.has(key) && Array.isArray(value)) {
    return (
      <Space wrap>
        {value.map((v, i) => (
          <Tag key={i} color="blue">
            {String(v)}
          </Tag>
        ))}
      </Space>
    );
  }

  if (TABLE_FIELDS.has(key) && Array.isArray(value)) {
    if (value.length === 0) return "-";
    if (typeof value[0] === "object" && value[0] !== null) {
      const cols: any[] = Object.keys(value[0]).map((k) => ({
        title: k,
        dataIndex: k,
        key: k,
        render: (v: unknown) => formatTableCell(v),
      }));
      if (review && (key === "products" || key === "application_scenarios")) {
        cols.push({
          title: "操作",
          dataIndex: "__actions",
          key: "__actions",
          render: (_v: unknown, row: Record<string, unknown>) => {
            const targetType = key === "products" ? "product" : "scenario";
            const targetId = String(
              targetType === "product" ? row.product_id : row.scenario_id
            );
            if (!targetId || targetId === "undefined") return "-";
            const rowKey = `${targetType}:${targetId}`;
            return (
              <Space>
                <Button
                  size="small"
                  loading={review.reviewingKey === `${rowKey}:accept`}
                  onClick={() => review.onReview(targetType, targetId, "accept")}
                >
                  接受
                </Button>
                <Button
                  size="small"
                  loading={review.reviewingKey === `${rowKey}:needs_review`}
                  onClick={() => review.onReview(targetType, targetId, "needs_review")}
                >
                  待审核
                </Button>
                <Button
                  size="small"
                  danger
                  loading={review.reviewingKey === `${rowKey}:reject`}
                  onClick={() => review.onReview(targetType, targetId, "reject")}
                >
                  驳回
                </Button>
              </Space>
            );
          },
        });
      }
      return (
        <Table
          dataSource={value}
          columns={cols}
          rowKey={(_, i) => String(i)}
          pagination={false}
          size="small"
          style={{ marginTop: 4 }}
        />
      );
    }
    return value.map(String).join(", ");
  }

  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function formatTableCell(value: unknown): React.ReactNode {
  if (value == null || value === "") return "-";
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "object") {
    return (
      <Typography.Text style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {JSON.stringify(value, null, 2)}
      </Typography.Text>
    );
  }
  return String(value);
}

function summaryLabel(domain: string, key: string): string {
  return DOMAIN_SUMMARY_LABELS[domain]?.[key] ?? SUMMARY_LABELS[key] ?? key;
}

function factLabel(domain: string, key: string): string {
  return DOMAIN_FACT_LABELS[domain]?.[key] ?? FACT_LABELS[key] ?? key;
}

function relatedLabel(fallback: string, rows: ReleasedObject[] = []): string {
  const objectType = rows.find((row) => row.object_type)?.object_type;
  return objectType ? DOMAIN_LABELS[objectType] ?? fallback : fallback;
}

function summaryComparableText(value: unknown): string {
  return value == null ? "" : String(value).trim();
}

function asObjectArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item)
  );
}

function firstText(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value == null || value === "") continue;
    if (Array.isArray(value)) {
      const text = value.map(String).filter(Boolean).join("、");
      if (text) return text;
    } else if (typeof value === "object") {
      continue;
    } else {
      const text = String(value).trim();
      if (text) return text;
    }
  }
  return "";
}

function renderBusinessValue(value: unknown): React.ReactNode {
  if (value == null || value === "") return <Text type="secondary">-</Text>;
  if (Array.isArray(value)) {
    const items = value.map(String).filter(Boolean);
    if (items.length === 0) return <Text type="secondary">-</Text>;
    return (
      <Space wrap size={[4, 4]}>
        {items.map((item) => (
          <Tag key={item}>{item}</Tag>
        ))}
      </Space>
    );
  }
  return (
    <Text style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
      {String(value)}
    </Text>
  );
}

function BusinessField({
  label,
  value,
  span = 1,
}: {
  label: string;
  value: unknown;
  span?: 1 | 2;
}) {
  return (
    <div style={{ gridColumn: span === 2 ? "1 / -1" : undefined }}>
      <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
        {label}
      </Text>
      {renderBusinessValue(value)}
    </div>
  );
}

function CompanyReviewControls({
  targetType,
  targetId,
  qualityStatus,
  review,
}: {
  targetType: "product" | "scenario";
  targetId: string;
  qualityStatus: unknown;
  review?: CompanyEnrichmentReview;
}) {
  const status = String(qualityStatus || "").trim();
  if (!status && !targetId) return null;
  const rowKey = `${targetType}:${targetId}`;
  return (
    <div style={{ marginTop: 12 }}>
      <Space wrap>
        {status && (
          <Space size={4}>
            <Text type="secondary">审核状态</Text>
            <QualityTag status={status} />
          </Space>
        )}
        {review && targetId && (
          <>
            <Button
              size="small"
              loading={review.reviewingKey === `${rowKey}:accept`}
              onClick={() => review.onReview(targetType, targetId, "accept")}
            >
              接受
            </Button>
            <Button
              size="small"
              loading={review.reviewingKey === `${rowKey}:needs_review`}
              onClick={() => review.onReview(targetType, targetId, "needs_review")}
            >
              待审核
            </Button>
            <Button
              size="small"
              danger
              loading={review.reviewingKey === `${rowKey}:reject`}
              onClick={() => review.onReview(targetType, targetId, "reject")}
            >
              驳回
            </Button>
          </>
        )}
      </Space>
    </div>
  );
}

function renderCompanyProducts(
  value: unknown,
  review?: CompanyEnrichmentReview
): React.ReactNode {
  const rows = asObjectArray(value);
  if (rows.length === 0) return <Text type="secondary">暂无产品数据</Text>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {rows.map((row, index) => {
        const productName = firstText(row, ["name", "canonical_name", "product_name"]);
        return (
          <div
            key={String(row.product_id ?? productName ?? index)}
            style={{
              borderBottom:
                index === rows.length - 1 ? undefined : "1px solid #f0f0f0",
              paddingBottom: index === rows.length - 1 ? 0 : 16,
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "12px 20px",
              }}
            >
              <BusinessField label="产品名称" value={productName} />
              <BusinessField
                label="产品类别"
                value={row.product_category ?? row.category}
              />
              <BusinessField
                label="产品简介"
                value={row.description ?? row.short_description}
                span={2}
              />
              <BusinessField label="技术标签" value={row.technical_tags} />
              <BusinessField label="目标客户" value={row.target_customers} />
              <BusinessField label="应用场景" value={row.application_scenarios} span={2} />
            </div>
            <CompanyReviewControls
              targetType="product"
              targetId={String(row.product_id ?? "")}
              qualityStatus={row.quality_status}
              review={review}
            />
          </div>
        );
      })}
    </div>
  );
}

function renderCompanyScenarios(
  value: unknown,
  review?: CompanyEnrichmentReview
): React.ReactNode {
  const rows = asObjectArray(value);
  if (rows.length === 0) return <Text type="secondary">暂无应用场景数据</Text>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {rows.map((row, index) => (
        <div
          key={String(row.scenario_id ?? row.scenario_name ?? index)}
          style={{
            borderBottom:
              index === rows.length - 1 ? undefined : "1px solid #f0f0f0",
            paddingBottom: index === rows.length - 1 ? 0 : 12,
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "12px 20px",
            }}
          >
            <BusinessField
              label="应用场景"
              value={row.scenario_name ?? row.name}
            />
            <BusinessField label="目标客户" value={row.target_customer} />
            <BusinessField
              label="场景说明"
              value={row.description}
              span={2}
            />
          </div>
          <CompanyReviewControls
            targetType="scenario"
            targetId={String(row.scenario_id ?? "")}
            qualityStatus={row.quality_status}
            review={review}
          />
        </div>
      ))}
    </div>
  );
}

function renderCompanyRecentEvents(value: unknown): React.ReactNode {
  const rows = asObjectArray(value);
  if (rows.length === 0) return <Text type="secondary">暂无最近动态</Text>;
  return (
    <Table
      dataSource={rows}
      columns={[
        {
          title: "日期",
          dataIndex: "event_date",
          key: "event_date",
          width: 120,
          render: (v: unknown) => renderBusinessValue(v),
        },
        {
          title: "类型",
          dataIndex: "event_type",
          key: "event_type",
          width: 120,
          render: (v: unknown) => renderBusinessValue(v),
        },
        {
          title: "摘要",
          dataIndex: "summary",
          key: "summary",
          render: (v: unknown) => renderBusinessValue(v),
        },
      ]}
      rowKey={(row) => String(row.event_id ?? row.summary ?? row.event_date)}
      pagination={false}
      size="small"
      tableLayout="fixed"
    />
  );
}

export default function RecordDetail() {
  const { domain = "professor" } = useParams();
  if (domain === "professor") return <ProfessorWorkbench />;
  return <GenericRecordDetail />;
}

function GenericRecordDetail() {
  const { domain = "professor", id = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [record, setRecord] = useState<ReleasedObject | null>(null);
  const [related, setRelated] = useState<RelatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [editOpen, setEditOpen] = useState(
    searchParams.get("edit") === "1"
  );
  const [saving, setSaving] = useState(false);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    setLoading(true);
    setError(false);
    Promise.all([
      fetchDomainObject(domain, id),
      fetchRelated(domain, id).catch(() => null),
    ])
      .then(([obj, rel]) => {
        setRecord(obj);
        setRelated(rel);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [domain, id]);

  const openEdit = () => {
    if (!record) return;
    form.setFieldsValue({
      quality_status: record.quality_status,
      ...Object.fromEntries(
        Object.entries(record.core_facts).map(([k, v]) => [
          `cf_${k}`,
          Array.isArray(v) ? v.join(", ") : v != null ? String(v) : "",
        ])
      ),
      ...Object.fromEntries(
        Object.entries(record.summary_fields).map(([k, v]) => [
          `sf_${k}`,
          v != null ? String(v) : "",
        ])
      ),
    });
    setEditOpen(true);
  };

  const handleSave = async () => {
    if (!record) return;
    const values = form.getFieldsValue();
    setSaving(true);
    try {
      const coreFacts: Record<string, unknown> = {};
      const summaryFields: Record<string, unknown> = {};

      for (const [k, v] of Object.entries(values)) {
        if (k.startsWith("cf_")) {
          const field = k.slice(3);
          const original = record.core_facts[field];
          if (Array.isArray(original)) {
            coreFacts[field] = String(v || "")
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
          } else {
            coreFacts[field] = v;
          }
        } else if (k.startsWith("sf_")) {
          summaryFields[k.slice(3)] = v;
        }
      }

      const updated = await updateRecord(domain, id, {
        core_facts: coreFacts,
        summary_fields: summaryFields,
        quality_status: values.quality_status,
      });
      setRecord(updated);
      setEditOpen(false);
      message.success("保存成功");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleEnrichmentReview = async (
    targetType: "product" | "scenario",
    targetId: string,
    action: ReviewAction
  ) => {
    if (!record || record.object_type !== "company") return;
    const key = `${targetType}:${targetId}:${action}`;
    setReviewingKey(key);
    try {
      const result = await reviewCompanyEnrichmentItem(record.id, targetType, targetId, {
        action,
        actor: "admin-console",
      });
      const field = targetType === "product" ? "products" : "application_scenarios";
      const idField = targetType === "product" ? "product_id" : "scenario_id";
      const rows = Array.isArray(record.core_facts[field])
        ? (record.core_facts[field] as Record<string, unknown>[])
        : [];
      setRecord({
        ...record,
        core_facts: {
          ...record.core_facts,
          [field]: rows.map((row) =>
            row[idField] === targetId
              ? { ...row, quality_status: result.new_status }
              : row
          ),
        },
      });
      message.success("审核状态已更新");
    } catch {
      message.error("审核状态更新失败");
    } finally {
      setReviewingKey(null);
    }
  };

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;
  if (error || !record) {
    return (
      <Result
        status="404"
        title="未找到记录"
        subTitle={`${DOMAIN_LABELS[domain] ?? domain} ${id} 不存在`}
        extra={
          <Button onClick={() => navigate(`/${domain}`)}>返回列表</Button>
        }
      />
    );
  }

  const factEntries = Object.entries(record.core_facts).filter(
    ([k, v]) => !HIDDEN_FACT_FIELDS.has(k) && v != null && v !== "" && !(Array.isArray(v) && v.length === 0)
  );
  const summaryZhText = summaryComparableText(record.summary_fields.summary_zh);
  const summaryEntries = Object.entries(record.summary_fields).filter(([k, v]) => {
    if (v == null || v === "") return false;
    if (
      k === "summary_text" &&
      summaryZhText &&
      summaryComparableText(v) === summaryZhText
    ) {
      return false;
    }
    return true;
  });

  // Separate table/tag fields from simple fields
  const simpleFacts = factEntries.filter(
    ([k]) => !TABLE_FIELDS.has(k)
  );
  const tableFacts = factEntries.filter(([k]) => TABLE_FIELDS.has(k));
  const companyTopFactKeys = ["products", "application_scenarios", "recent_events"];
  const topTableFacts =
    domain === "company"
      ? companyTopFactKeys.map((key) => [key, record.core_facts[key] ?? []] as const)
      : [];
  const remainingTableFacts =
    domain === "company"
      ? tableFacts.filter(([key]) => !companyTopFactKeys.includes(key))
      : tableFacts;
  const companyReview =
    domain === "company"
      ? {
          companyId: id,
          onReview: handleEnrichmentReview,
          reviewingKey,
        }
      : undefined;
  const renderTableFactCard = ([key, value]: readonly [string, unknown]) => (
    <Card
      key={key}
      title={factLabel(domain, key)}
      style={{ marginBottom: 16 }}
    >
      {domain === "company" && key === "products"
        ? renderCompanyProducts(value, companyReview)
        : domain === "company" && key === "application_scenarios"
          ? renderCompanyScenarios(value, companyReview)
          : domain === "company" && key === "recent_events"
            ? renderCompanyRecentEvents(value)
            : renderValue(
                key,
                value,
                domain === "company"
                  ? {
                      companyId: id,
                      onReview: handleEnrichmentReview,
                      reviewingKey,
                    }
                  : undefined
              )}
    </Card>
  );

  // Related records tab items
  const relatedTabs = [];
  if (related?.papers && related.papers.length > 0) {
    relatedTabs.push({
      key: "papers",
      label: `${relatedLabel("论文", related.papers)} (${related.papers.length})`,
      children: (
        <Table
          dataSource={related.papers}
          columns={[
            { title: "名称", dataIndex: "display_name", key: "name" },
            { title: "ID", dataIndex: "id", key: "id" },
            {
              title: "质量",
              key: "qs",
              render: (_: unknown, r: ReleasedObject) => (
                <QualityTag status={r.quality_status} />
              ),
            },
          ]}
          rowKey="id"
          size="small"
          pagination={false}
          onRow={(r) => ({
            onClick: () => navigate(`/${r.object_type}/${r.id}`),
            style: { cursor: "pointer" },
          })}
        />
      ),
    });
  }
  if (related?.patents && related.patents.length > 0) {
    relatedTabs.push({
      key: "patents",
      label: `${relatedLabel("专利", related.patents)} (${related.patents.length})`,
      children: (
        <Table
          dataSource={related.patents}
          columns={[
            { title: "名称", dataIndex: "display_name", key: "name" },
            { title: "ID", dataIndex: "id", key: "id" },
            {
              title: "质量",
              key: "qs",
              render: (_: unknown, r: ReleasedObject) => (
                <QualityTag status={r.quality_status} />
              ),
            },
          ]}
          rowKey="id"
          size="small"
          pagination={false}
          onRow={(r) => ({
            onClick: () => navigate(`/${r.object_type}/${r.id}`),
            style: { cursor: "pointer" },
          })}
        />
      ),
    });
  }
  if (related?.companies && related.companies.length > 0) {
    relatedTabs.push({
      key: "companies",
      label: `${relatedLabel("企业", related.companies)} (${related.companies.length})`,
      children: (
        <Table
          dataSource={related.companies}
          columns={[
            { title: "名称", dataIndex: "display_name", key: "name" },
            { title: "ID", dataIndex: "id", key: "id" },
            {
              title: "质量",
              key: "qs",
              render: (_: unknown, r: ReleasedObject) => (
                <QualityTag status={r.quality_status} />
              ),
            },
          ]}
          rowKey="id"
          size="small"
          pagination={false}
          onRow={(r) => ({
            onClick: () => navigate(`/${r.object_type}/${r.id}`),
            style: { cursor: "pointer" },
          })}
        />
      ),
    });
  }

  // Editable fields for the modal
  const editableCoreFacts = Object.entries(record.core_facts).filter(
    ([k]) => !HIDDEN_FACT_FIELDS.has(k) && !TABLE_FIELDS.has(k) && k !== "professor_ids" && k !== "company_ids"
  );
  const editableSummaryFields = Object.entries(record.summary_fields);

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Button
          icon={<ArrowLeftOutlined />}
          type="link"
          onClick={() => navigate(`/${domain}`)}
          style={{ paddingLeft: 0 }}
        >
          返回{DOMAIN_LABELS[domain] ?? domain}列表
        </Button>
        <Button icon={<EditOutlined />} type="primary" onClick={openEdit}>
          编辑
        </Button>
      </div>

      <Title level={3}>
        {record.display_name} <QualityTag status={record.quality_status} />
        {record.object_type === "professor" && (
          <LifecycleTag status={record.lifecycle_state} />
        )}
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        ID: {record.id} | 更新: {record.last_updated}
      </Text>

      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          {simpleFacts.map(([key, value]) => (
            <Descriptions.Item
              key={key}
              label={factLabel(domain, key)}
              span={
                TAG_FIELDS.has(key) ||
                (typeof value === "string" && value.length > 50)
                  ? 2
                  : 1
              }
            >
              {renderValue(key, value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Card>

      {topTableFacts.map(renderTableFactCard)}

      {remainingTableFacts.map(renderTableFactCard)}

      {summaryEntries.length > 0 && (
        <Card title="摘要" style={{ marginBottom: 16 }}>
          {summaryEntries.map(([key, value]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <Title level={5}>{summaryLabel(domain, key)}</Title>
              <Paragraph>{String(value)}</Paragraph>
            </div>
          ))}
        </Card>
      )}

      {relatedTabs.length > 0 && (
        <Card title="关联数据" style={{ marginBottom: 16 }}>
          <Tabs items={relatedTabs} />
        </Card>
      )}

      <Card title="数据来源" style={{ marginBottom: 16 }}>
        <EvidenceList evidence={record.evidence} />
      </Card>

      <Collapse
        items={[
          {
            key: "raw",
            label: "原始 JSON",
            children: (
              <pre
                style={{ fontSize: 12, maxHeight: 400, overflow: "auto" }}
              >
                {JSON.stringify(record, null, 2)}
              </pre>
            ),
          },
        ]}
      />

      <Modal
        title="编辑记录"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={700}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="质量状态" name="quality_status">
            <Select
              options={[
                { value: "ready", label: "就绪" },
                { value: "needs_review", label: "待审核" },
                { value: "low_confidence", label: "低置信度" },
                { value: "needs_enrichment", label: "需补充" },
              ]}
            />
          </Form.Item>

          <Title level={5}>基本信息</Title>
          {editableCoreFacts.map(([key, value]) => (
            <Form.Item
              key={key}
              label={factLabel(domain, key)}
              name={`cf_${key}`}
            >
              {typeof value === "string" && value.length > 100 ? (
                <Input.TextArea rows={3} />
              ) : (
                <Input />
              )}
            </Form.Item>
          ))}

          <Title level={5}>摘要字段</Title>
          {editableSummaryFields.map(([key]) => (
            <Form.Item
              key={key}
              label={summaryLabel(domain, key)}
              name={`sf_${key}`}
            >
              <Input.TextArea rows={4} />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </div>
  );
}
