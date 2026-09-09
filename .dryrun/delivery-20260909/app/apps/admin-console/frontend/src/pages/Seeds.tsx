import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  createSeed,
  deleteSeed,
  fetchSeeds,
  type Seed,
  type SeedFailureClass,
  type SeedLastRunStatus,
  type SeedPayload,
  type SeedTriggerMode,
  triggerSeed,
  updateSeed,
} from "../api";
import "./Seeds.css";

const { Title, Paragraph } = Typography;

const STATUS_LABELS: Record<SeedLastRunStatus, string> = {
  success: "成功",
  failure: "失败",
  in_progress: "运行中",
  never_run: "未运行",
  adapter_missing: "缺 adapter",
};
const FAILURE_CLASS_LABELS: Record<SeedFailureClass, string> = {
  adapter_missing: "缺 adapter",
  fetch_blocked: "抓取受阻",
  manual_interruption: "人工中断",
  parser_low_quality: "解析低质",
  pipeline_exception: "运行异常",
  success: "成功",
};

const STATUS_TAG_COLOR: Record<SeedLastRunStatus, string> = {
  success: "success",
  failure: "error",
  in_progress: "processing",
  never_run: "default",
  adapter_missing: "orange",
};

type Filter = "all" | SeedLastRunStatus;

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Seeds() {
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [editing, setEditing] = useState<Seed | "new" | null>(null);
  const [triggering, setTriggering] = useState<Seed | null>(null);
  const [triggerMode, setTriggerMode] = useState<SeedTriggerMode>("sample");
  const [triggerLimit, setTriggerLimit] = useState<number | null>(3);
  const [fullConfirmed, setFullConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [triggeringSeedId, setTriggeringSeedId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const reload = useCallback(async () => {
    try {
      const rows = await fetchSeeds();
      setSeeds(rows);
    } catch (err) {
      messageApi.error(`加载失败: ${err instanceof Error ? err.message : err}`);
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Poll every 10s while any seed is in_progress (per spec T3.6).
  const hasInProgress = useMemo(
    () => seeds.some((s) => s.last_run_status === "in_progress"),
    [seeds],
  );
  useEffect(() => {
    if (!hasInProgress) return;
    const t = window.setInterval(() => void reload(), 10_000);
    return () => window.clearInterval(t);
  }, [hasInProgress, reload]);

  const counts = useMemo(() => {
    const c: Record<SeedLastRunStatus, number> = {
      success: 0,
      failure: 0,
      in_progress: 0,
      never_run: 0,
      adapter_missing: 0,
    };
    for (const s of seeds) c[s.last_run_status] += 1;
    return c;
  }, [seeds]);

  const visible = useMemo(
    () => (filter === "all" ? seeds : seeds.filter((s) => s.last_run_status === filter)),
    [seeds, filter],
  );

  const openAdd = () => {
    form.resetFields();
    setEditing("new");
  };

  const openEdit = (seed: Seed) => {
    form.setFieldsValue({
      school: seed.school,
      department: seed.department ?? "",
      seed_url: seed.seed_url,
    });
    setEditing(seed);
  };

  const closeModal = () => {
    if (submitting) return;
    setEditing(null);
    form.resetFields();
  };

  const openTrigger = (seed: Seed) => {
    setTriggering(seed);
    setTriggerMode("sample");
    setTriggerLimit(3);
    setFullConfirmed(false);
  };

  const closeTriggerModal = () => {
    if (triggeringSeedId !== null) return;
    setTriggering(null);
    setTriggerMode("sample");
    setTriggerLimit(3);
    setFullConfirmed(false);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: SeedPayload = {
        school: values.school.trim(),
        department: values.department?.trim() || null,
        seed_url: values.seed_url.trim(),
      };
      setSubmitting(true);
      if (editing === "new") {
        await createSeed(payload);
        messageApi.success("已添加 seed");
      } else if (editing) {
        await updateSeed(editing.id, payload);
        messageApi.success("已保存");
      }
      setEditing(null);
      form.resetFields();
      await reload();
    } catch (err) {
      // Form validation throws ValidationError without message; only show
      // if it's an API/network error.
      if (err instanceof Error) messageApi.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (seed: Seed) => {
    Modal.confirm({
      title: "删除 seed？",
      content: (
        <div>
          <p style={{ marginBottom: 8 }}>
            <strong>{seed.school}</strong>
            {seed.department ? ` · ${seed.department}` : " · school-wide"}
          </p>
          <p style={{ fontFamily: "var(--seed-font-mono)", fontSize: 12, color: "#888" }}>
            {seed.seed_url}
          </p>
          <p style={{ marginTop: 12, color: "#d4380d" }}>
            该操作不可逆。已发布的 professor / paper / patent 不会受影响。
          </p>
        </div>
      ),
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deleteSeed(seed.id);
          messageApi.success("已删除");
          await reload();
        } catch (err) {
          messageApi.error(err instanceof Error ? err.message : "删除失败");
          throw err;
        }
      },
    });
  };

  const handleTrigger = async () => {
    if (!triggering) return;
    if (triggerMode === "sample" && (!triggerLimit || triggerLimit <= 0)) {
      messageApi.error("sample 需要正数 limit");
      return;
    }
    if (triggerMode === "full" && !fullConfirmed) {
      messageApi.error("请确认 full run");
      return;
    }
    const seed = triggering;
    try {
      setTriggeringSeedId(seed.id);
      await triggerSeed(seed.id, {
        mode: triggerMode,
        limit: triggerMode === "sample" ? triggerLimit : null,
      });
      setSeeds((rows) =>
        rows.map((row) =>
          row.id === seed.id
            ? { ...row, last_run_status: "in_progress" as const }
            : row,
        ),
      );
      messageApi.success("已开始爬取");
      closeTriggerModal();
    } catch (err) {
      messageApi.error(err instanceof Error ? err.message : "触发失败");
      await reload();
    } finally {
      setTriggeringSeedId(null);
    }
  };

  const columns: ColumnsType<Seed> = [
    {
      title: "学校",
      dataIndex: "school",
      key: "school",
      width: 160,
      render: (school: string, _seed, idx) => (
        <Space size="small" align="baseline">
          <span className="seed-row-num">
            {String(idx + 1).padStart(2, "0")}
          </span>
          <span className="seed-school-name">{school}</span>
        </Space>
      ),
    },
    {
      title: "院系",
      dataIndex: "department",
      key: "department",
      width: 220,
      render: (dept: string | null) =>
        dept ? (
          <span>{dept}</span>
        ) : (
          <span className="seed-empty-dept">school-wide</span>
        ),
    },
    {
      title: "Seed URL",
      dataIndex: "seed_url",
      key: "seed_url",
      ellipsis: { showTitle: true },
      render: (url: string) => (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="seed-url-pill"
          title={url}
        >
          {url}
        </a>
      ),
    },
    {
      title: "上次抓取",
      dataIndex: "last_run_at",
      key: "last_run_at",
      width: 160,
      render: (iso: string | null) => (
        <span className="seed-time-cell">{formatTimestamp(iso)}</span>
      ),
    },
    {
      title: "状态",
      dataIndex: "last_run_status",
      key: "last_run_status",
      width: 160,
      render: (status: SeedLastRunStatus, seed) => {
        const label =
          status === "failure" && seed.failure_class
            ? FAILURE_CLASS_LABELS[seed.failure_class]
            : STATUS_LABELS[status];
        const raw =
          status === "failure" && seed.failure_class
            ? seed.failure_class
            : status;
        return (
          <Tag color={STATUS_TAG_COLOR[status]} className="seed-status-tag">
            {label}
            <span className="seed-status-raw">{raw}</span>
          </Tag>
        );
      },
    },
    {
      title: "操作",
      key: "actions",
      width: 240,
      render: (_v, seed) => {
        const triggerDisabled = seed.last_run_status === "in_progress";
        const tooltip =
          seed.last_run_status === "adapter_missing"
            ? "重新检测 adapter"
            : seed.last_run_status === "in_progress"
              ? "运行中"
              : "立即爬取";
        return (
          <Space size="small">
            <Tooltip title={tooltip} placement="top">
              <Button
                size="small"
                type="primary"
                ghost
                icon={<ThunderboltOutlined />}
                disabled={triggerDisabled}
                loading={triggeringSeedId === seed.id}
                onClick={() => openTrigger(seed)}
                className="seed-trigger-btn"
              >
                触发
              </Button>
            </Tooltip>
            <Button
              size="small"
              type="default"
              icon={<EditOutlined />}
              onClick={() => openEdit(seed)}
            >
              编辑
            </Button>
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(seed)}
            >
              删除
            </Button>
          </Space>
        );
      },
    },
  ];

  const filterPills: Array<{ key: Filter; label: string; tone?: string }> = [
    { key: "all", label: `全部 ${seeds.length}` },
    { key: "success", label: `success ${counts.success}`, tone: "success" },
    { key: "failure", label: `failure ${counts.failure}`, tone: "failure" },
    { key: "in_progress", label: `运行中 ${counts.in_progress}`, tone: "progress" },
    { key: "never_run", label: `未运行 ${counts.never_run}`, tone: "never" },
    {
      key: "adapter_missing",
      label: `adapter 缺 ${counts.adapter_missing}`,
      tone: "missing",
    },
  ];

  return (
    <div className="seed-page">
      {contextHolder}
      <header className="seed-page-head">
        <div className="seed-head-section">
          <div className="seed-eyebrow">Admin / Professor / Seed Registry</div>
          <Title level={1} className="seed-h1">
            Seed
            <span className="seed-h1-accent">索引</span>
          </Title>
          <Paragraph className="seed-lede">
            管理教师 roster 入口 URL ── 决定 pipeline 抓取哪些学校、哪些院系。
          </Paragraph>
        </div>
        <div className="seed-head-summary">
          <SummaryStat n={seeds.length} l="seed 总数" />
          <SummaryStat n={counts.success} l="success" tone="success" />
          <SummaryStat n={counts.failure} l="failure" tone="failure" />
          <SummaryStat n={counts.in_progress} l="in progress" tone="progress" />
          <SummaryStat n={counts.adapter_missing} l="adapter 缺失" tone="missing" />
        </div>
      </header>

      <div className="seed-toolbar">
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={openAdd}
          className="seed-add-btn"
        >
          添加 seed
        </Button>
        <div className="seed-filters">
          {filterPills.map((p) => (
            <button
              key={p.key}
              className={`seed-pill seed-pill-${p.tone ?? "default"} ${
                filter === p.key ? "seed-pill-active" : ""
              }`}
              onClick={() => setFilter(p.key)}
              type="button"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <Table<Seed>
        rowKey="id"
        columns={columns}
        dataSource={visible}
        loading={loading}
        pagination={false}
        rowClassName={(seed) =>
          `seed-row seed-row-${seed.last_run_status}`
        }
      />

      <footer className="seed-page-foot">
        <span className="seed-foot-build">build phase B · trigger enabled</span>
      </footer>

      <Modal
        title={editing === "new" ? "添加 seed" : "编辑 seed"}
        open={editing !== null}
        onCancel={closeModal}
        onOk={handleSubmit}
        okText={editing === "new" ? "添加" : "保存"}
        cancelText="取消"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          requiredMark="optional"
          autoComplete="off"
        >
          <Form.Item
            label="学校"
            name="school"
            rules={[{ required: true, message: "请填写学校名称" }]}
          >
            <Input placeholder="SUSTech / SZU / 清华深研院" autoFocus />
          </Form.Item>
          <Form.Item
            label="院系"
            name="department"
            extra="留空 = 全校统一 roster（如南科大）"
          >
            <Input placeholder="计算机与软件学院（可选）" />
          </Form.Item>
          <Form.Item
            label="Seed URL"
            name="seed_url"
            rules={[
              { required: true, message: "请填写 roster 页面 URL" },
              { type: "url", message: "URL 格式无效（必须为 http(s)）" },
            ]}
            extra="教师 roster 页面 URL，pipeline 直接抓这里"
          >
            <Input placeholder="https://faculty.sustech.edu.cn" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="触发 seed"
        open={triggering !== null}
        onCancel={closeTriggerModal}
        onOk={() => void handleTrigger()}
        okText={triggerMode === "full" ? "确认 full run" : "开始"}
        cancelText="取消"
        confirmLoading={triggeringSeedId !== null}
        destroyOnHidden
      >
        {triggering ? (
          <div className="seed-trigger-modal">
            <div className="seed-trigger-identity">
              <strong>{triggering.school}</strong>
              <span>
                {triggering.department ? ` · ${triggering.department}` : " · school-wide"}
              </span>
              <code>{triggering.seed_url}</code>
            </div>
            <Radio.Group
              value={triggerMode}
              onChange={(e) => {
                setTriggerMode(e.target.value);
                setFullConfirmed(false);
              }}
              className="seed-trigger-mode"
            >
              <Radio.Button value="sample">sample</Radio.Button>
              <Radio.Button value="preview">preview</Radio.Button>
              <Radio.Button value="full">full</Radio.Button>
            </Radio.Group>
            {triggerMode === "sample" ? (
              <Form layout="vertical" className="seed-trigger-limit-form">
                <Form.Item label="limit" required>
                  <InputNumber
                    min={1}
                    max={1000}
                    value={triggerLimit}
                    onChange={(value) => setTriggerLimit(value)}
                    className="seed-trigger-limit"
                  />
                </Form.Item>
              </Form>
            ) : null}
            {triggerMode === "full" ? (
              <Checkbox
                checked={fullConfirmed}
                onChange={(e) => setFullConfirmed(e.target.checked)}
              >
                确认执行 full run
              </Checkbox>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

function SummaryStat({
  n,
  l,
  tone,
}: {
  n: number;
  l: string;
  tone?: string;
}) {
  return (
    <div className={`seed-sum-stat seed-sum-${tone ?? "default"}`}>
      <div className="seed-sum-n">{n}</div>
      <div className="seed-sum-l">{l}</div>
    </div>
  );
}
