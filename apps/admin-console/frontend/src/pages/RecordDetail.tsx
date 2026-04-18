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
  updateRecord,
  type ReleasedObject,
  type RelatedResponse,
} from "../api";
import QualityTag from "../components/QualityTag";
import EvidenceList from "../components/EvidenceList";

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
};

const SUMMARY_LABELS: Record<string, string> = {
  profile_summary: "个人简介",
  evaluation_summary: "评估摘要",
  technology_route_summary: "技术路线",
  summary_zh: "中文摘要",
  summary_text: "摘要",
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
const TABLE_FIELDS = new Set(["education", "awards"]);

const HIDDEN_FACT_FIELDS = new Set(["top_papers"]);

function renderValue(key: string, value: unknown): React.ReactNode {
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
      const cols = Object.keys(value[0]).map((k) => ({
        title: k,
        dataIndex: k,
        key: k,
        render: (v: unknown) => (v != null ? String(v) : "-"),
      }));
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

export default function RecordDetail() {
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
  const summaryEntries = Object.entries(record.summary_fields).filter(
    ([, v]) => v != null && v !== ""
  );

  // Separate table/tag fields from simple fields
  const simpleFacts = factEntries.filter(
    ([k]) => !TABLE_FIELDS.has(k)
  );
  const tableFacts = factEntries.filter(([k]) => TABLE_FIELDS.has(k));

  // Related records tab items
  const relatedTabs = [];
  if (related?.papers && related.papers.length > 0) {
    relatedTabs.push({
      key: "papers",
      label: `论文 (${related.papers.length})`,
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
      label: `专利 (${related.patents.length})`,
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
      label: `企业 (${related.companies.length})`,
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
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        ID: {record.id} | 更新: {record.last_updated}
      </Text>

      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          {simpleFacts.map(([key, value]) => (
            <Descriptions.Item
              key={key}
              label={FACT_LABELS[key] ?? key}
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

      {tableFacts.map(([key, value]) => (
        <Card
          key={key}
          title={FACT_LABELS[key] ?? key}
          style={{ marginBottom: 16 }}
        >
          {renderValue(key, value)}
        </Card>
      ))}

      {summaryEntries.length > 0 && (
        <Card title="摘要" style={{ marginBottom: 16 }}>
          {summaryEntries.map(([key, value]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <Title level={5}>{SUMMARY_LABELS[key] ?? key}</Title>
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
              label={FACT_LABELS[key] ?? key}
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
              label={SUMMARY_LABELS[key] ?? key}
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
