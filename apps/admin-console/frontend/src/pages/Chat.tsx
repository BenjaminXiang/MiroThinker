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
} from "@ant-design/icons";
import { sendChatMessage, type ChatCitation, type ChatResponse } from "../api";

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
  "清华大学深圳国际研究生院做人工智能的教授",
  "深度学习在医学影像中的应用",
  "深圳理工大学做生物的教授",
];

export default function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, pending]);

  async function submit(query: string) {
    const trimmed = query.trim();
    if (!trimmed || pending) return;
    const now = Date.now();
    setTurns((prev) => [...prev, { role: "user", query: trimmed, at: now }]);
    setDraft("");
    setPending(true);
    try {
      const response = await sendChatMessage(trimmed);
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

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)" }}>
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
          return <AssistantBubble key={turn.at} response={turn.response} />;
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

function AssistantBubble({ response }: { response: ChatResponse }) {
  const cits = response.citations ?? [];
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
        <Text type="secondary" style={{ fontSize: 11 }}>
          {response.query_type} · {response.answer_style}
        </Text>
      </Space>
    </Bubble>
  );
}
