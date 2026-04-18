import { useEffect, useState } from "react";
import { Col, Row, Spin, Table, Typography } from "antd";
import {
  TeamOutlined,
  BankOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";
import { fetchDashboard, type DashboardResponse } from "../api";
import StatCard from "../components/StatCard";
import QualityTag from "../components/QualityTag";

const { Title } = Typography;

const DOMAIN_META: Record<string, { label: string; icon: ReactNode }> = {
  professor: { label: "教授", icon: <TeamOutlined /> },
  company: { label: "企业", icon: <BankOutlined /> },
  paper: { label: "论文", icon: <FileTextOutlined /> },
  patent: { label: "专利", icon: <SafetyCertificateOutlined /> },
};

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ marginTop: 100 }} />;
  if (!data) return null;

  const qualityColumns = [
    {
      title: "数据域",
      dataIndex: "name",
      key: "name",
      render: (name: string) => DOMAIN_META[name]?.label ?? name,
    },
    {
      title: "就绪",
      key: "ready",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="ready" /> {record.quality.ready ?? 0}
        </span>
      ),
    },
    {
      title: "待审核",
      key: "needs_review",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="needs_review" />{" "}
          {record.quality.needs_review ?? 0}
        </span>
      ),
    },
    {
      title: "低置信度",
      key: "low_confidence",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="low_confidence" />{" "}
          {record.quality.low_confidence ?? 0}
        </span>
      ),
    },
    {
      title: "需补充",
      key: "needs_enrichment",
      render: (_: unknown, record: (typeof data.domains)[0]) => (
        <span>
          <QualityTag status="needs_enrichment" />{" "}
          {record.quality.needs_enrichment ?? 0}
        </span>
      ),
    },
    {
      title: "最后更新",
      key: "last_updated",
      render: (_: unknown, record: (typeof data.domains)[0]) =>
        formatDate(record.last_updated),
    },
  ];

  return (
    <div>
      <Title level={3}>数据总览</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {data.domains.map((d) => (
          <Col key={d.name} xs={12} sm={6}>
            <StatCard
              title={DOMAIN_META[d.name]?.label ?? d.name}
              value={d.count}
              icon={DOMAIN_META[d.name]?.icon}
              lastUpdated={formatDate(d.last_updated)}
            />
          </Col>
        ))}
      </Row>
      <Title level={4}>质量概览</Title>
      <Table
        dataSource={data.domains}
        columns={qualityColumns}
        rowKey="name"
        pagination={false}
        size="middle"
      />
    </div>
  );
}
