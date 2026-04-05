import { Card, Statistic } from "antd";
import type { ReactNode } from "react";

interface Props {
  title: string;
  value: number;
  icon: ReactNode;
}

export default function StatCard({ title, value, icon }: Props) {
  return (
    <Card>
      <Statistic title={title} value={value} prefix={icon} />
    </Card>
  );
}
