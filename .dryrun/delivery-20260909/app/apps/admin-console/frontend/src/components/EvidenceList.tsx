import { Timeline, Tag, Typography } from "antd";
import type { Evidence } from "../api";

const { Text, Link } = Typography;

const TYPE_LABELS: Record<string, string> = {
  official_site: "官方网站",
  xlsx_import: "表格导入",
  public_web: "公开网页",
  academic_platform: "学术平台",
  manual_review: "人工审核",
};

interface Props {
  evidence: Evidence[];
}

export default function EvidenceList({ evidence }: Props) {
  if (!evidence.length) return <Text type="secondary">暂无来源信息</Text>;

  return (
    <Timeline
      items={evidence.map((e, i) => ({
        key: i,
        children: (
          <div>
            <Tag>{TYPE_LABELS[e.source_type] ?? e.source_type}</Tag>
            {e.source_url && (
              <Link href={e.source_url} target="_blank">
                {e.source_url}
              </Link>
            )}
            {e.snippet && (
              <div>
                <Text type="secondary">{e.snippet}</Text>
              </div>
            )}
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {e.fetched_at}
                {e.confidence != null && ` | 置信度: ${e.confidence}`}
              </Text>
            </div>
          </div>
        ),
      }))}
    />
  );
}
