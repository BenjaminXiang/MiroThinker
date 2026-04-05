import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Descriptions,
  Spin,
  Typography,
  Button,
  Collapse,
  Result,
  Card,
} from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { fetchDomainObject, type ReleasedObject } from "../api";
import QualityTag from "../components/QualityTag";
import EvidenceList from "../components/EvidenceList";

const { Title, Paragraph } = Typography;

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
};

const SUMMARY_LABELS: Record<string, string> = {
  profile_summary: "个人简介",
  evaluation_summary: "评估摘要",
  technology_route_summary: "技术路线",
  summary_zh: "中文摘要",
  summary_text: "摘要",
};

function formatValue(value: unknown): string {
  if (value == null) return "-";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export default function RecordDetail() {
  const { domain = "professor", id = "" } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<ReleasedObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchDomainObject(domain, id)
      .then(setRecord)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [domain, id]);

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
    ([, v]) => v != null && v !== "" && !(Array.isArray(v) && v.length === 0)
  );

  const summaryEntries = Object.entries(record.summary_fields).filter(
    ([, v]) => v != null && v !== ""
  );

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        type="link"
        onClick={() => navigate(`/${domain}`)}
        style={{ marginBottom: 16, paddingLeft: 0 }}
      >
        返回{DOMAIN_LABELS[domain] ?? domain}列表
      </Button>

      <Title level={3}>
        {record.display_name} <QualityTag status={record.quality_status} />
      </Title>

      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          {factEntries.map(([key, value]) => (
            <Descriptions.Item
              key={key}
              label={FACT_LABELS[key] ?? key}
              span={
                typeof value === "string" && value.length > 50 ? 2 : 1
              }
            >
              {formatValue(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Card>

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

      <Card title="数据来源" style={{ marginBottom: 16 }}>
        <EvidenceList evidence={record.evidence} />
      </Card>

      <Collapse
        items={[
          {
            key: "raw",
            label: "原始 JSON",
            children: (
              <pre style={{ fontSize: 12, maxHeight: 400, overflow: "auto" }}>
                {JSON.stringify(record, null, 2)}
              </pre>
            ),
          },
        ]}
      />
    </div>
  );
}
