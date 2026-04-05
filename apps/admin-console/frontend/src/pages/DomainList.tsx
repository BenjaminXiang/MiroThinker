import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Table, Input, Typography, Spin } from "antd";
import type { TablePaginationConfig } from "antd";
import type { SorterResult } from "antd/es/table/interface";
import { fetchDomainList, type ReleasedObject } from "../api";
import QualityTag from "../components/QualityTag";

const { Title } = Typography;
const { Search } = Input;

const DOMAIN_LABELS: Record<string, string> = {
  professor: "教授",
  company: "企业",
  paper: "论文",
  patent: "专利",
};

const DOMAIN_COLUMNS: Record<string, { title: string; key: string }[]> = {
  professor: [
    { title: "院校", key: "institution" },
    { title: "院系", key: "department" },
    { title: "职称", key: "title" },
  ],
  company: [
    { title: "行业", key: "industry" },
  ],
  paper: [
    { title: "年份", key: "year" },
    { title: "期刊/会议", key: "venue" },
  ],
  patent: [
    { title: "专利类型", key: "patent_type" },
    { title: "申请人", key: "applicants" },
  ],
};

export default function DomainList() {
  const { domain = "professor" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Number(searchParams.get("page") ?? "1");
  const q = searchParams.get("q") ?? "";
  const sortBy = searchParams.get("sort_by") ?? "display_name";
  const sortOrder = (searchParams.get("sort_order") ?? "asc") as
    | "asc"
    | "desc";

  const [items, setItems] = useState<ReleasedObject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchDomainList(domain, {
      q,
      page,
      page_size: 20,
      sort_by: sortBy,
      sort_order: sortOrder,
    })
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [domain, q, page, sortBy, sortOrder]);

  useEffect(() => {
    load();
  }, [load]);

  const updateParams = (updates: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(updates)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setSearchParams(next);
  };

  const handleTableChange = (
    pagination: TablePaginationConfig,
    _filters: Record<string, unknown>,
    sorter: SorterResult<ReleasedObject> | SorterResult<ReleasedObject>[]
  ) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter;
    updateParams({
      page: String(pagination.current ?? 1),
      sort_by: (s?.field as string) ?? "display_name",
      sort_order: s?.order === "descend" ? "desc" : "asc",
    });
  };

  const columns = [
    {
      title: "名称",
      dataIndex: "display_name",
      key: "display_name",
      sorter: true,
      sortOrder:
        sortBy === "display_name"
          ? sortOrder === "desc"
            ? ("descend" as const)
            : ("ascend" as const)
          : undefined,
    },
    ...(DOMAIN_COLUMNS[domain] ?? []).map((col) => ({
      title: col.title,
      key: col.key,
      render: (_: unknown, record: ReleasedObject) => {
        const val = record.core_facts[col.key];
        if (Array.isArray(val)) return val.join(", ");
        return val != null ? String(val) : "-";
      },
    })),
    {
      title: "质量状态",
      key: "quality_status",
      render: (_: unknown, record: ReleasedObject) => (
        <QualityTag status={record.quality_status} />
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>{DOMAIN_LABELS[domain] ?? domain}</Title>
      <Search
        placeholder="搜索名称..."
        defaultValue={q}
        onSearch={(value) => updateParams({ q: value, page: "1" })}
        style={{ width: 300, marginBottom: 16 }}
        allowClear
      />
      {loading ? (
        <Spin />
      ) : (
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          pagination={{
            current: page,
            pageSize: 20,
            total,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={handleTableChange}
          onRow={(record) => ({
            onClick: () => navigate(`/${domain}/${record.id}`),
            style: { cursor: "pointer" },
          })}
          size="middle"
        />
      )}
    </div>
  );
}
