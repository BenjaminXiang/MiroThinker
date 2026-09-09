import { Card, Statistic, Typography } from "antd";
import type { ReactNode } from "react";

const { Text } = Typography;

interface Props {
  title: string;
  value: number;
  icon: ReactNode;
  lastUpdated?: string;
}

export default function StatCard({ title, value, icon, lastUpdated }: Props) {
  return (
    <Card>
      <Statistic title={title} value={value} prefix={icon} />
      {lastUpdated && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          更新: {lastUpdated}
        </Text>
      )}
    </Card>
  );
}
