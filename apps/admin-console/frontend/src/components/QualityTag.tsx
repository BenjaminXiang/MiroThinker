import { Tag } from "antd";

const COLOR_MAP: Record<string, string> = {
  ready: "green",
  needs_review: "orange",
  low_confidence: "red",
};

const LABEL_MAP: Record<string, string> = {
  ready: "就绪",
  needs_review: "待审核",
  low_confidence: "低置信度",
};

interface Props {
  status: string;
}

export default function QualityTag({ status }: Props) {
  return (
    <Tag color={COLOR_MAP[status] ?? "default"}>
      {LABEL_MAP[status] ?? status}
    </Tag>
  );
}
