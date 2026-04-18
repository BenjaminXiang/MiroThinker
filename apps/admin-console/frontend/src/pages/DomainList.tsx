import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import {
  Table,
  Input,
  Typography,
  Spin,
  Button,
  Space,
  Select,
  Popconfirm,
  Upload,
  Modal,
  message,
  Dropdown,
} from "antd";
import type { TablePaginationConfig } from "antd";
import type { SorterResult } from "antd/es/table/interface";
import {
  EyeOutlined,
  EditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  fetchDomainList,
  fetchFilterOptions,
  deleteRecord,
  batchUpdateQuality,
  batchDelete,
  exportDomain,
  uploadFile,
  type ReleasedObject,
} from "../api";
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
  company: [{ title: "行业", key: "industry" }],
  paper: [
    { title: "年份", key: "year" },
    { title: "期刊/会议", key: "venue" },
  ],
  patent: [
    { title: "专利类型", key: "patent_type" },
    { title: "申请人", key: "applicants" },
  ],
};

// Domain-specific filterable fields (field key → label)
const DOMAIN_FILTERS: Record<string, { key: string; label: string }[]> = {
  professor: [
    { key: "institution", label: "院校" },
    { key: "department", label: "院系" },
    { key: "title", label: "职称" },
  ],
  company: [{ key: "industry", label: "行业" }],
  paper: [
    { key: "year", label: "年份" },
    { key: "venue", label: "期刊/会议" },
  ],
  patent: [{ key: "patent_type", label: "专利类型" }],
};

const QUALITY_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "ready", label: "就绪" },
  { value: "needs_review", label: "待审核" },
  { value: "low_confidence", label: "低置信度" },
  { value: "needs_enrichment", label: "需补充" },
];

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
  const qualityFilter = searchParams.get("quality_status") ?? "";

  const [items, setItems] = useState<ReleasedObject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Domain-specific filter options loaded from API
  const [filterOptions, setFilterOptions] = useState<
    Record<string, string[]>
  >({});

  // Read active domain filters from URL params
  const domainFilters = DOMAIN_FILTERS[domain] ?? [];
  const getFilterValue = (key: string) => searchParams.get(`f_${key}`) ?? "";

  // Load filter options when domain changes
  useEffect(() => {
    setFilterOptions({});
    const fields = (DOMAIN_FILTERS[domain] ?? []).map((f) => f.key);
    fields.forEach((field) => {
      fetchFilterOptions(domain, field)
        .then((resp) => {
          setFilterOptions((prev) => ({ ...prev, [field]: resp.options }));
        })
        .catch(() => {});
    });
  }, [domain]);

  // Build filters object from URL params
  const buildFilters = useCallback(() => {
    const filters: Record<string, string> = {};
    if (qualityFilter) filters["quality_status"] = qualityFilter;
    for (const f of DOMAIN_FILTERS[domain] ?? []) {
      const val = searchParams.get(`f_${f.key}`);
      if (val) filters[f.key] = val;
    }
    return Object.keys(filters).length > 0 ? filters : undefined;
  }, [domain, qualityFilter, searchParams]);

  const load = useCallback(() => {
    setLoading(true);
    fetchDomainList(domain, {
      q,
      page,
      page_size: 20,
      sort_by: sortBy,
      sort_order: sortOrder,
      filters: buildFilters(),
    })
      .then((data) => {
        setItems(data.items);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [domain, q, page, sortBy, sortOrder, buildFilters]);

  useEffect(() => {
    load();
    setSelectedRowKeys([]);
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

  const handleDelete = async (id: string) => {
    await deleteRecord(domain, id);
    message.success("已删除");
    load();
  };

  const handleBatchQuality = async (status: string) => {
    const resp = await batchUpdateQuality(selectedRowKeys, status);
    message.success(`已更新 ${resp.updated} 条记录`);
    setSelectedRowKeys([]);
    load();
  };

  const handleBatchDelete = async () => {
    const resp = await batchDelete(selectedRowKeys);
    message.success(`已删除 ${resp.deleted} 条记录`);
    setSelectedRowKeys([]);
    load();
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const resp = await uploadFile(domain as "company" | "patent", file);
      message.success(
        `导入 ${resp.imported} 条，当前共 ${resp.total_in_store} 条`
      );
      setUploadModalOpen(false);
      load();
    } catch {
      message.error("上传失败，请检查文件格式");
    } finally {
      setUploading(false);
    }
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
      width: 110,
      render: (_: unknown, record: ReleasedObject) => (
        <QualityTag status={record.quality_status} />
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_: unknown, record: ReleasedObject) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/${domain}/${record.id}`);
            }}
          />
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/${domain}/${record.id}?edit=1`);
            }}
          />
          <Popconfirm
            title="确定删除？"
            onConfirm={(e) => {
              e?.stopPropagation();
              handleDelete(record.id);
            }}
            onCancel={(e) => e?.stopPropagation()}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => e.stopPropagation()}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const hasSelection = selectedRowKeys.length > 0;
  const canUpload = domain === "company" || domain === "patent";

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
        <Title level={3} style={{ margin: 0 }}>
          {DOMAIN_LABELS[domain] ?? domain}
        </Title>
        <Space>
          {canUpload && (
            <Button
              icon={<UploadOutlined />}
              onClick={() => setUploadModalOpen(true)}
            >
              上传 Excel
            </Button>
          )}
          <Dropdown
            menu={{
              items: [
                {
                  key: "csv",
                  label: "导出 CSV",
                  onClick: () =>
                    exportDomain(
                      domain,
                      "csv",
                      hasSelection ? selectedRowKeys : undefined
                    ),
                },
                {
                  key: "xlsx",
                  label: "导出 Excel",
                  onClick: () =>
                    exportDomain(
                      domain,
                      "xlsx",
                      hasSelection ? selectedRowKeys : undefined
                    ),
                },
              ],
            }}
          >
            <Button icon={<DownloadOutlined />}>
              导出{hasSelection ? ` (${selectedRowKeys.length})` : ""}
            </Button>
          </Dropdown>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Search
          placeholder="搜索名称..."
          defaultValue={q}
          onSearch={(value) => updateParams({ q: value, page: "1" })}
          style={{ width: 220 }}
          allowClear
        />
        <Select
          value={qualityFilter || undefined}
          placeholder="质量状态"
          options={QUALITY_OPTIONS}
          onChange={(val) =>
            updateParams({ quality_status: val ?? "", page: "1" })
          }
          style={{ width: 130 }}
          allowClear
        />
        {domainFilters.map((f) => (
          <Select
            key={f.key}
            value={getFilterValue(f.key) || undefined}
            placeholder={f.label}
            options={(filterOptions[f.key] ?? []).map((v) => ({
              value: v,
              label: v,
            }))}
            onChange={(val) =>
              updateParams({ [`f_${f.key}`]: val ?? "", page: "1" })
            }
            style={{ width: f.key === "venue" ? 200 : 150 }}
            allowClear
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? "")
                .toLowerCase()
                .includes(input.toLowerCase())
            }
          />
        ))}
      </Space>

      {hasSelection && (
        <Space style={{ marginBottom: 12 }}>
          <span>已选 {selectedRowKeys.length} 条</span>
          <Dropdown
            menu={{
              items: [
                {
                  key: "ready",
                  label: "设为就绪",
                  onClick: () => handleBatchQuality("ready"),
                },
                {
                  key: "needs_review",
                  label: "设为待审核",
                  onClick: () => handleBatchQuality("needs_review"),
                },
                {
                  key: "low_confidence",
                  label: "设为低置信度",
                  onClick: () => handleBatchQuality("low_confidence"),
                },
                {
                  key: "needs_enrichment",
                  label: "设为需补充",
                  onClick: () => handleBatchQuality("needs_enrichment"),
                },
              ],
            }}
          >
            <Button size="small">批量状态</Button>
          </Dropdown>
          <Popconfirm
            title={`确定删除 ${selectedRowKeys.length} 条记录？`}
            onConfirm={handleBatchDelete}
          >
            <Button size="small" danger>
              批量删除
            </Button>
          </Popconfirm>
        </Space>
      )}

      {loading ? (
        <Spin />
      ) : (
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as string[]),
          }}
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

      <Modal
        title={`上传 ${DOMAIN_LABELS[domain]} Excel`}
        open={uploadModalOpen}
        onCancel={() => setUploadModalOpen(false)}
        footer={null}
      >
        <Upload.Dragger
          accept=".xlsx"
          showUploadList={false}
          beforeUpload={(file) => {
            handleUpload(file);
            return false;
          }}
          disabled={uploading}
        >
          <p style={{ fontSize: 40, color: "#999" }}>
            <UploadOutlined />
          </p>
          <p>{uploading ? "上传中..." : "点击或拖拽 .xlsx 文件到此处"}</p>
        </Upload.Dragger>
      </Modal>
    </div>
  );
}
