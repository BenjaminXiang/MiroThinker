import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Collapse,
  Descriptions,
  Empty,
  List,
  Result,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { fetchAdminProfessorDetail, markAdminProfessor } from "../api";

const { Paragraph, Text, Title } = Typography;

type MarkAction = "confirm_ready" | "send_to_review" | "flag_recrawl";

export interface ProfessorFact {
  fact_type: string;
  value_raw: string;
  value_normalized?: string | null;
  evidence_span?: string | null;
  confidence?: number | null;
  source_url?: string | null;
  source_role?: string | null;
}

export interface ProfessorAdminDetail {
  identity: {
    professor_id: string;
    canonical_name: string;
    canonical_name_en?: string | null;
    canonical_name_zh?: string | null;
    aliases: string[];
    institution?: string | null;
    department?: string | null;
    title?: string | null;
    discipline_family?: string | null;
    identity_status?: string | null;
  };
  contact: {
    facts: Record<string, ProfessorFact[]>;
    official_profile_url?: string | null;
  };
  research_and_output: {
    research_topics: ProfessorFact[];
    h_index?: number | null;
    citation_count?: number | null;
    paper_count?: number | null;
    representative_papers: unknown[];
  };
  experience: {
    status: "populated" | "not_extracted";
    facts: Record<string, ProfessorFact[]>;
  };
  cleaned_summary: {
    profile_summary?: string | null;
  };
  sources_and_evidence: {
    primary_source?: {
      url?: string | null;
      page_role?: string | null;
      is_official_source?: boolean | null;
    } | null;
    affiliations: unknown[];
    provenance: ProfessorFact[];
  };
  quality_diagnosis: {
    status: string;
    reasons: Array<{ rule_id: string; stage?: string | null; message: string }>;
    open_issues: Array<{
      issue_id?: string;
      stage: string;
      severity: string;
      description: string;
      reported_by: string;
      rule_id?: string | null;
    }>;
    latest_admin_action?: {
      action: string;
      actor: string;
      created_at?: string | null;
    } | null;
  };
}

interface ProfessorWorkbenchViewProps {
  detail: ProfessorAdminDetail;
  marking: boolean;
  onMark: (action: MarkAction) => Promise<void>;
}

export function ProfessorWorkbenchView({
  detail,
  marking,
  onMark,
}: ProfessorWorkbenchViewProps) {
  const { identity, quality_diagnosis: diagnosis } = detail;
  const reasonText =
    diagnosis.reasons.length > 0
      ? diagnosis.reasons.map((reason) => reason.rule_id).join(", ")
      : "ready";

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Button onClick={() => history.back()}>返回</Button>
      <section>
        <Title level={3} style={{ margin: 0 }}>
          {identity.canonical_name}
        </Title>
        <Text type="secondary">{identity.professor_id}</Text>
      </section>

      <Alert
        showIcon
        type={diagnosis.status === "ready" ? "success" : "warning"}
        message={
          <Space wrap>
            <Text strong>质量诊断</Text>
            <Tag>{diagnosis.status}</Tag>
            <Text>{reasonText}</Text>
          </Space>
        }
        description={
          <Space wrap>
            <Button
              icon={<CheckCircleOutlined />}
              loading={marking}
              onClick={() => onMark("confirm_ready")}
            >
              confirm_ready
            </Button>
            <Button
              icon={<ExclamationCircleOutlined />}
              loading={marking}
              onClick={() => onMark("send_to_review")}
            >
              send_to_review
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={marking}
              onClick={() => onMark("flag_recrawl")}
            >
              flag_recrawl
            </Button>
          </Space>
        }
      />

      <Section title="Identity">
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="Institution">
            {identity.institution || "-"}
          </Descriptions.Item>
          <Descriptions.Item label="Department">
            {identity.department || "-"}
          </Descriptions.Item>
          <Descriptions.Item label="Title">{identity.title || "-"}</Descriptions.Item>
          <Descriptions.Item label="Identity status">
            {identity.identity_status || "-"}
          </Descriptions.Item>
        </Descriptions>
      </Section>

      <Section title="Contact">
        <FactList facts={Object.values(detail.contact.facts).flat()} />
      </Section>

      <Section title="Research And Output">
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Space wrap>
            <Tag>h-index {detail.research_and_output.h_index ?? "-"}</Tag>
            <Tag>citations {detail.research_and_output.citation_count ?? "-"}</Tag>
            <Tag>papers {detail.research_and_output.paper_count ?? "-"}</Tag>
          </Space>
          <FactList facts={detail.research_and_output.research_topics} />
        </Space>
      </Section>

      <Section title="Cleaned Summary">
        <Paragraph>{detail.cleaned_summary.profile_summary || "-"}</Paragraph>
      </Section>

      <Section title="Experience">
        {detail.experience.status === "not_extracted" ? (
          <Empty description="not_extracted" />
        ) : (
          Object.entries(detail.experience.facts).map(([type, facts]) => (
            <div key={type}>
              <Text strong>{type}</Text>
              <FactList facts={facts} />
            </div>
          ))
        )}
      </Section>

      <Section title="Sources And Evidence">
        <Collapse
          items={[
            {
              key: "primary",
              label: "Primary source",
              children: (
                <Paragraph copyable>
                  {detail.sources_and_evidence.primary_source?.url || "-"}
                </Paragraph>
              ),
            },
            {
              key: "provenance",
              label: "Field provenance",
              children: (
                <FactList
                  facts={[
                    ...detail.sources_and_evidence.provenance,
                    ...Object.values(detail.contact.facts).flat(),
                    ...detail.research_and_output.research_topics,
                  ]}
                />
              ),
            },
          ]}
        />
      </Section>

      <Section title="Open Issues">
        <List
          dataSource={diagnosis.open_issues}
          locale={{ emptyText: "No open issues" }}
          renderItem={(issue) => (
            <List.Item>
              <Space direction="vertical" size={2}>
                <Space wrap>
                  <Tag>{issue.stage}</Tag>
                  <Tag>{issue.severity}</Tag>
                  <Text>{issue.rule_id || issue.reported_by}</Text>
                </Space>
                <Text>{issue.description}</Text>
              </Space>
            </List.Item>
          )}
        />
      </Section>
    </Space>
  );
}

export default function ProfessorWorkbench() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ProfessorAdminDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [marking, setMarking] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    fetchAdminProfessorDetail(id)
      .then((payload) => setDetail(payload as ProfessorAdminDetail))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleMark = async (action: MarkAction) => {
    setMarking(true);
    try {
      await markAdminProfessor(id, { action });
      message.success("已记录");
      load();
    } catch {
      message.error("操作失败");
    } finally {
      setMarking(false);
    }
  };

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;
  if (error || !detail) {
    return (
      <Result
        status="404"
        title="未找到教授记录"
        subTitle={id}
        extra={<Button onClick={() => navigate("/professor")}>返回列表</Button>}
      />
    );
  }

  return (
    <ProfessorWorkbenchView
      detail={detail}
      marking={marking}
      onMark={handleMark}
    />
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        padding: 16,
      }}
    >
      <Title level={4} style={{ marginTop: 0 }}>
        {title}
      </Title>
      {children}
    </section>
  );
}

function FactList({ facts }: { facts: ProfessorFact[] }) {
  if (!facts.length) return <Empty description="-" />;
  return (
    <List
      dataSource={facts}
      renderItem={(fact) => (
        <List.Item>
          <Space direction="vertical" size={2}>
            <Space wrap>
              <Text>{fact.value_raw}</Text>
              {fact.confidence != null ? (
                <Tag>{Math.round(fact.confidence * 100)}%</Tag>
              ) : null}
            </Space>
            {fact.source_url ? <Text type="secondary">{fact.source_url}</Text> : null}
            {fact.evidence_span ? (
              <Text type="secondary">{fact.evidence_span}</Text>
            ) : null}
          </Space>
        </List.Item>
      )}
    />
  );
}
