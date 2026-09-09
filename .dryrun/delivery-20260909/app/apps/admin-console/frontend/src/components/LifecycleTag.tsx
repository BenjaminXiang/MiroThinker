import { Tag } from "antd";

const COLOR_MAP: Record<string, string> = {
  active: "green",
  archived: "default",
  merged_to_other_school: "blue",
};

const LABEL_MAP: Record<string, string> = {
  active: "在职",
  archived: "归档",
  merged_to_other_school: "已合并",
};

interface Props {
  status?: string | null;
}

export default function LifecycleTag({ status }: Props) {
  const value = status || "active";
  return <Tag color={COLOR_MAP[value] ?? "default"}>{LABEL_MAP[value] ?? value}</Tag>;
}
