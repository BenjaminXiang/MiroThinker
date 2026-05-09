import React, { useEffect, useRef, useState } from "react";
import {
  Input,
  Button,
  Card,
  Tag,
  Space,
  Typography,
  Spin,
  Alert,
  Tooltip,
} from "antd";
import {
  SendOutlined,
  UserOutlined,
  RobotOutlined,
  TeamOutlined,
  FileTextOutlined,
  BankOutlined,
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  BranchesOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  reportChatFeedback,
  resetChatSession,
  sendChatMessage,
  type ChatCandidateOption,
  type ChatCitation,
  type ChatResponse,
} from "../api";

const { Text, Paragraph } = Typography;

interface TurnUser {
  role: "user";
  query: string;
  at: number;
}

interface TurnAssistant {
  role: "assistant";
  response: ChatResponse;
  at: number;
}

interface TurnError {
  role: "error";
  message: string;
  at: number;
}

type Turn = TurnUser | TurnAssistant | TurnError;

const CITATION_ICON: Record<ChatCitation["type"], React.ReactElement> = {
  professor: <TeamOutlined />,
  paper: <FileTextOutlined />,
  patent: <SafetyCertificateOutlined />,
  company: <BankOutlined />,
};

const CITATION_COLOR: Record<ChatCitation["type"], string> = {
  professor: "blue",
  paper: "purple",
  patent: "gold",
  company: "green",
};

const SAMPLE_QUERIES = [
  "介绍无界智航的相关信息",
  "深圳有哪些做具身智能的教授和企业",
  "具身智能合成数据有几种实现方法",
];

export default function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [resetting, setResetting] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, pending]);

  async function submit(
    query: string,
    params: { entityIdHint?: string; displayQuery?: string } = {}
  ) {
    const trimmed = query.trim();
    if (!trimmed || pending) return;
    const now = Date.now();
    setTurns((prev) => [
      ...prev,
      { role: "user", query: params.displayQuery ?? trimmed, at: now },
    ]);
    setDraft("");
    setPending(true);
    try {
      const response = await sendChatMessage(trimmed, {
        entityIdHint: params.entityIdHint,
      });
      setTurns((prev) => [
        ...prev,
        { role: "assistant", response, at: Date.now() },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTurns((prev) => [
        ...prev,
        { role: "error", message, at: Date.now() },
      ]);
    } finally {
      setPending(false);
    }
  }

  async function startNewConversation() {
    if (pending || resetting) return;
    setResetting(true);
    try {
      await resetChatSession();
      setTurns([]);
      setDraft("");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTurns((prev) => [
        ...prev,
        { role: "error", message, at: Date.now() },
      ]);
    } finally {
      setResetting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
          marginBottom: 8,
        }}
      >
        <Text strong>对话检索</Text>
        <Tooltip title="开始新会话">
          <Button
            size="small"
            icon={<PlusOutlined />}
            loading={resetting}
            disabled={pending}
            onClick={startNewConversation}
          >
            新对话
          </Button>
        </Tooltip>
      </div>
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          paddingRight: 8,
          paddingBottom: 16,
        }}
      >
        {turns.length === 0 && !pending && (
          <Card title="对话检索" style={{ marginBottom: 12 }}>
            <Paragraph>
              用自然语言在教授、企业、论文、专利四个数据域中提问，系统会自动路由到语义检索与网页兜底，返回带出处的答案。
            </Paragraph>
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              <Text type="secondary">试试这些问题：</Text>
              {SAMPLE_QUERIES.map((q) => (
                <Button
                  key={q}
                  size="small"
                  type="link"
                  style={{ padding: 0, textAlign: "left", height: "auto" }}
                  onClick={() => submit(q)}
                >
                  {q}
                </Button>
              ))}
            </Space>
          </Card>
        )}

        {turns.map((turn) => {
          if (turn.role === "user") {
            return (
              <Bubble key={turn.at} align="right" icon={<UserOutlined />}>
                <Text>{turn.query}</Text>
              </Bubble>
            );
          }
          if (turn.role === "error") {
            return (
              <Bubble key={turn.at} align="left" icon={<RobotOutlined />}>
                <Alert type="error" message={turn.message} showIcon={false} />
              </Bubble>
            );
          }
          return (
            <AssistantBubble
              key={turn.at}
              response={turn.response}
              onSelectCandidate={(option) =>
                submit(turn.response.query, {
                  entityIdHint: option.id,
                  displayQuery: `选择：${option.label}`,
                })
              }
              onFollowup={(query) => submit(query)}
            />
          );
        })}

        {pending && (
          <Bubble align="left" icon={<RobotOutlined />}>
            <Spin size="small" /> <Text type="secondary">检索中…</Text>
          </Bubble>
        )}

        <div ref={endRef} />
      </div>

      <div style={{ display: "flex", gap: 8, paddingTop: 8 }}>
        <Input.TextArea
          placeholder="例如：清华大学深圳国际研究生院做人工智能的教授"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(draft);
            }
          }}
          disabled={pending}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={() => submit(draft)}
          loading={pending}
          disabled={!draft.trim()}
        >
          发送
        </Button>
      </div>
    </div>
  );
}

function Bubble({
  align,
  icon,
  children,
}: {
  align: "left" | "right";
  icon: React.ReactElement;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: align === "right" ? "flex-end" : "flex-start",
        marginBottom: 12,
        gap: 8,
      }}
    >
      {align === "left" && (
        <div style={{ fontSize: 20, color: "#888", paddingTop: 4 }}>{icon}</div>
      )}
      <div
        style={{
          maxWidth: "78%",
          background: align === "right" ? "#e6f4ff" : "#fafafa",
          border: "1px solid #eee",
          borderRadius: 8,
          padding: "8px 12px",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {children}
      </div>
      {align === "right" && (
        <div style={{ fontSize: 20, color: "#888", paddingTop: 4 }}>{icon}</div>
      )}
    </div>
  );
}

function AssistantBubble({
  response,
  onSelectCandidate,
  onFollowup,
}: {
  response: ChatResponse;
  onSelectCandidate: (option: ChatCandidateOption) => void;
  onFollowup: (query: string) => void;
}) {
  const cits = response.citations ?? [];
  const clarification = response.clarification;
  const followups = response.suggested_followups ?? [];
  const [feedbackState, setFeedbackState] = useState<
    "idle" | "sending" | "sent"
  >("idle");
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  async function submitFeedback() {
    if (feedbackState !== "idle") return;
    setFeedbackError(null);
    setFeedbackState("sending");
    try {
      await reportChatFeedback(response, {
        note: "Flagged from admin-console chat UI.",
      });
      setFeedbackState("sent");
    } catch (err) {
      setFeedbackState("idle");
      setFeedbackError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Bubble align="left" icon={<RobotOutlined />}>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <div>
          {response.answer_text || (
            <Text type="secondary">（未生成回答）</Text>
          )}
        </div>
        {cits.length > 0 && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, marginRight: 6 }}>
              引用：
            </Text>
            <Space size={[4, 4]} wrap>
              {cits.map((c, idx) => (
                <Tooltip key={`${c.type}:${c.id}:${idx}`} title={c.label}>
                  <Tag
                    color={CITATION_COLOR[c.type]}
                    icon={CITATION_ICON[c.type]}
                    style={{ cursor: c.url ? "pointer" : "default" }}
                    onClick={() => {
                      if (c.url) window.open(c.url, "_blank", "noopener");
                    }}
                  >
                    [{idx + 1}] {c.label}
                  </Tag>
                </Tooltip>
              ))}
            </Space>
          </div>
        )}
        {clarification && clarification.options.length > 0 && (
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {clarification.prompt}
            </Text>
            <Space size={[6, 6]} wrap style={{ marginTop: 6 }}>
              {clarification.options.map((option) => (
                <Tooltip key={option.id} title={option.hint}>
                  <Button
                    size="small"
                    type={
                      option.id === clarification.default_id
                        ? "primary"
                        : "default"
                    }
                    onClick={() => onSelectCandidate(option)}
                  >
                    {option.label}
                  </Button>
                </Tooltip>
              ))}
              {clarification.omitted > 0 && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  另有 {clarification.omitted} 个候选未展示
                </Text>
              )}
            </Space>
          </div>
        )}
        {followups.length > 0 && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, marginRight: 6 }}>
              继续问：
            </Text>
            <Space size={[4, 4]} wrap>
              {followups.map((query) => (
                <Button
                  key={query}
                  size="small"
                  type="link"
                  icon={<BranchesOutlined />}
                  style={{ padding: "0 4px", height: 22 }}
                  onClick={() => onFollowup(query)}
                >
                  {query}
                </Button>
              ))}
            </Space>
          </div>
        )}
        {feedbackError && (
          <Alert type="error" message={feedbackError} showIcon={false} />
        )}
        <Space size={8} wrap>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {response.query_type} · {response.answer_style}
          </Text>
          <Tooltip title="提交到问题列表">
            <Button
              size="small"
              type="text"
              icon={<ExclamationCircleOutlined />}
              loading={feedbackState === "sending"}
              disabled={feedbackState === "sent"}
              onClick={submitFeedback}
            >
              {feedbackState === "sent" ? "已反馈" : "反馈"}
            </Button>
          </Tooltip>
        </Space>
      </Space>
    </Bubble>
  );
}
