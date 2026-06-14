import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Descriptions,
  Empty,
  Input,
  message,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  CheckOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  fetchAdminProfessorDetail,
  markAdminProfessor,
  type AdminProfessorDetail,
  type AdminProfessorIssueReason,
} from "../api";
import QualityTag from "../components/QualityTag";
import LifecycleTag from "../components/LifecycleTag";

const { Title, Text, Paragraph } = Typography;

const FIELD_LABELS: Record<string, string> = {
  canonical_name: "姓名",
  canonical_name_en: "英文名",
  institution: "院校",
  department: "院系",
  title: "职称",
  identity_status: "身份状态",
  lifecycle_state: "生命周期",
  lifecycle_merged_into_id: "合并目标",
  email: "邮箱",
  profile_summary: "清洗简介",
};

function text(value: unknown): string {
  if (value == null || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function sourceUrl(row: Record<string, unknown>): string | null {
  const value = row.source_page_url ?? row.url;
  return typeof value === "string" && value ? value : null;
}

function factValue(row: Record<string, unknown>): string {
  return text(row.value_raw);
}

function factsOfType(
  facts: Record<string, unknown>[],
  factType: string
): Record<string, unknown>[] {
  return facts.filter((fact) => fact.fact_type === factType);
}

function FactTable({
  rows,
  emptyText,
}: {
  rows: Record<string, unknown>[];
  emptyText: string;
}) {
  return (
    <Table
      size="small"
      rowKey={(row) =>
        `fact-${text(row.fact_type)}-${factValue(row)}-${text(sourceUrl(row))}`
      }
      dataSource={rows}
      pagination={false}
      columns={[
        { title: "内容", render: (_value, row) => factValue(row) },
        {
          title: "来源",
          width: 360,
          render: (_value, row) => {
            const url = sourceUrl(row);
            return url ? <a href={url}>{url}</a> : "-";
          },
        },
      ]}
      locale={{ emptyText }}
    />
  );
}

function ReasonTags({ reasons }: { reasons: AdminProfessorIssueReason[] }) {
  if (reasons.length === 0) return <Text type="secondary">无未关闭诊断</Text>;
  return (
    <Space wrap>
      {reasons.map((reason, index) => (
        <Tag key={`${reason.rule_id ?? reason.stage}-${index}`} color="orange">
          {reason.rule_id ?? reason.stage ?? "issue"}
        </Tag>
      ))}
    </Space>
  );
}

export default function ProfessorWorkbench() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AdminProfessorDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [marking, setMarking] = useState(false);
  const [noteOpen, setNoteOpen] = useState<
    "confirm_ready" | "send_to_review" | "flag_recrawl" | null
  >(null);
  const [note, setNote] = useState("");

  const load = () => {
    setLoading(true);
    fetchAdminProfessorDetail(id)
      .then(setDetail)
      .catch(() => message.error("加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(load, [id]);

  const submitMark = async () => {
    if (!noteOpen) return;
    setMarking(true);
    try {
      await markAdminProfessor(id, {
        action: noteOpen,
        actor: "admin-console",
        note: note || undefined,
      });
      setNoteOpen(null);
      setNote("");
      await fetchAdminProfessorDetail(id).then(setDetail);
      message.success("已记录");
    } catch {
      message.error("操作失败");
    } finally {
      setMarking(false);
    }
  };

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;
  if (!detail) {
    return (
      <Empty
        description="未找到教授"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const sections = detail.sections;
  const identity = sections.identity;
  const contact = sections.contact;
  const diagnosis = sections.quality_diagnosis;
  const research = sections.research_output;
  const experience = sections.experience;
  const evidence = sections.sources_evidence;
  const facts = research.facts ?? [];
  const papers = research.papers ?? [];
  const patents = research.patents ?? [];
  const affiliations = experience.affiliations ?? [];
  const sources = evidence.sources ?? [];
  const actions = evidence.admin_actions ?? [];
  const researchTopics = factsOfType(facts, "research_topic");
  const educationFacts = factsOfType(facts, "education");
  const workExperienceFacts = factsOfType(facts, "work_experience");
  const awardFacts = factsOfType(facts, "award");
  const academicPositionFacts = factsOfType(facts, "academic_position");

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        type="link"
        onClick={() => navigate("/professor")}
        style={{ paddingLeft: 0, marginBottom: 12 }}
      >
        返回教授列表
      </Button>

      <Space align="center" wrap style={{ marginBottom: 8 }}>
        <Title level={3} style={{ margin: 0 }}>
          {text(identity.canonical_name)}
        </Title>
        <QualityTag status={diagnosis.status} />
        <LifecycleTag status={identity.lifecycle_state as string | undefined} />
      </Space>
      <Text type="secondary">ID: {detail.professor_id}</Text>

      <Alert
        style={{ marginTop: 16, marginBottom: 16 }}
        type={diagnosis.status === "ready" ? "success" : "warning"}
        showIcon
        message={
          <Space wrap>
            <Text strong>质量诊断</Text>
            <QualityTag status={diagnosis.status} />
            <Text>未关闭问题 {diagnosis.open_issue_count}</Text>
            <ReasonTags reasons={diagnosis.reasons} />
          </Space>
        }
        action={
          <Space wrap>
            <Button
              icon={<CheckOutlined />}
              size="small"
              onClick={() => setNoteOpen("confirm_ready")}
            >
              确认就绪
            </Button>
            <Button
              icon={<WarningOutlined />}
              size="small"
              onClick={() => setNoteOpen("send_to_review")}
            >
              送审
            </Button>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={() => setNoteOpen("flag_recrawl")}
            >
              重采
            </Button>
          </Space>
        }
      />

      <section style={{ marginBottom: 20 }}>
        <Title level={4}>身份与联系</Title>
        <Descriptions bordered size="small" column={2}>
          {[
            "canonical_name",
            "canonical_name_en",
            "institution",
            "department",
            "title",
            "identity_status",
            "lifecycle_state",
            "email",
          ].map((key) => (
            <Descriptions.Item key={key} label={FIELD_LABELS[key] ?? key}>
              {key === "email" ? text(contact.email) : text(identity[key])}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </section>

      <section style={{ marginBottom: 20 }}>
        <Title level={4}>研究与产出</Title>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {research.research_overview && (
            <div>
              <Title level={5}>研究领域介绍</Title>
              <Paragraph style={{ marginBottom: 0 }}>
                {research.research_overview}
              </Paragraph>
            </div>
          )}
          <div>
            <Title level={5}>研究方向</Title>
            {researchTopics.length > 0 ? (
              <Space wrap>
                {researchTopics.map((fact, index) => (
                  <Tag key={`${factValue(fact)}-${index}`} color="blue">
                    {factValue(fact)}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Text type="secondary">暂无研究方向</Text>
            )}
          </div>
          {academicPositionFacts.length > 0 && (
            <div>
              <Title level={5}>学术兼职</Title>
              <FactTable rows={academicPositionFacts} emptyText="暂无学术兼职" />
            </div>
          )}
          <Table
            size="small"
            rowKey={(row) => text(row.paper_id)}
            dataSource={papers}
            pagination={false}
            columns={[
              {
                title: "论文",
                render: (_value, row) => {
                  const paperId = text(row.paper_id);
                  return paperId !== "-" ? (
                    <Link to={`/paper/${paperId}`}>
                      {text(row.title_clean ?? row.title ?? row.paper_id)}
                    </Link>
                  ) : (
                    text(row.title_clean ?? row.title)
                  );
                },
              },
              { title: "年份", dataIndex: "year", width: 120 },
            ]}
            locale={{ emptyText: "暂无论文" }}
          />
          <Table
            size="small"
            rowKey={(row) => text(row.patent_id)}
            dataSource={patents}
            pagination={false}
            columns={[
              { title: "专利", dataIndex: "title_clean" },
              { title: "专利号", dataIndex: "patent_number", width: 180 },
            ]}
            locale={{ emptyText: "暂无专利" }}
          />
        </Space>
      </section>

      <section style={{ marginBottom: 20 }}>
        <Title level={4}>教育与经历</Title>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {educationFacts.length > 0 && (
            <div>
              <Title level={5}>教育经历</Title>
              <FactTable rows={educationFacts} emptyText="暂无教育经历" />
            </div>
          )}
          {workExperienceFacts.length > 0 && (
            <div>
              <Title level={5}>工作经历</Title>
              <FactTable rows={workExperienceFacts} emptyText="暂无工作经历" />
            </div>
          )}
        </Space>
        {experience.status === "not_extracted" &&
        educationFacts.length === 0 &&
        workExperienceFacts.length === 0 ? (
          <Alert type="info" showIcon message="not_extracted" />
        ) : affiliations.length > 0 && workExperienceFacts.length === 0 ? (
          <Table
            style={{ marginTop: 12 }}
            size="small"
            rowKey={(row) =>
              `affiliation-${text(row.institution)}-${text(row.department)}-${text(row.title)}-${text(sourceUrl(row))}`
            }
            dataSource={affiliations}
            pagination={false}
            columns={[
              { title: "机构", dataIndex: "institution" },
              { title: "院系", dataIndex: "department" },
              { title: "职称", dataIndex: "title" },
              {
                title: "来源",
                render: (_value, row) => {
                  const url = sourceUrl(row);
                  return url ? <a href={url}>{url}</a> : "-";
                },
              },
            ]}
          />
        ) : null}
      </section>

      {awardFacts.length > 0 && (
        <section style={{ marginBottom: 20 }}>
          <Title level={4}>荣誉奖项</Title>
          <FactTable rows={awardFacts} emptyText="暂无荣誉奖项" />
        </section>
      )}

      <section style={{ marginBottom: 20 }}>
        <Title level={4}>清洗摘要</Title>
        <Paragraph>
          {text(sections.cleaned_summary.profile_summary)}
        </Paragraph>
        {research.paper_summary && (
          <Paragraph>
            <Text strong>论文：</Text>
            {research.paper_summary}
          </Paragraph>
        )}
        {research.patent_summary && (
          <Paragraph>
            <Text strong>专利：</Text>
            {research.patent_summary}
          </Paragraph>
        )}
      </section>

      <section style={{ marginBottom: 20 }}>
        <Title level={4}>来源与操作</Title>
        <Table
          size="small"
          rowKey={(row) => text(row.url)}
          dataSource={sources}
          pagination={false}
          columns={[
            {
              title: "URL",
              render: (_value, row) => {
                const url = sourceUrl(row);
                return url ? <a href={url}>{url}</a> : "-";
              },
            },
            { title: "类型", dataIndex: "page_role", width: 180 },
            {
              title: "官方源",
              dataIndex: "is_official_source",
              width: 100,
              render: (value) => (value ? "是" : "否"),
            },
          ]}
          locale={{ emptyText: "暂无来源" }}
        />
        <Table
          style={{ marginTop: 12 }}
          size="small"
          rowKey={(row) =>
            `action-${text(row.created_at)}-${text(row.action)}-${text(row.actor)}-${text(row.note)}`
          }
          dataSource={actions}
          pagination={false}
          columns={[
            { title: "动作", dataIndex: "action" },
            { title: "操作者", dataIndex: "actor" },
            { title: "备注", dataIndex: "note" },
            { title: "记录时间", dataIndex: "created_at" },
          ]}
          locale={{ emptyText: "暂无操作" }}
        />
      </section>

      <Modal
        title="记录操作"
        open={noteOpen !== null}
        onOk={submitMark}
        onCancel={() => setNoteOpen(null)}
        confirmLoading={marking}
        okText="提交"
        cancelText="取消"
      >
        <Input.TextArea
          rows={4}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </Modal>
    </div>
  );
}
