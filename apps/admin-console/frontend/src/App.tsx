import { Layout, Menu } from "antd";
import {
  DashboardOutlined,
  TeamOutlined,
  BankOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  MessageOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import DomainList from "./pages/DomainList";
import RecordDetail from "./pages/RecordDetail";
import ProfessorWorkbench from "./pages/ProfessorWorkbench";
import Chat from "./pages/Chat";
import PipelineRuns from "./pages/PipelineRuns";
import PipelineIssues from "./pages/PipelineIssues";
import Seeds from "./pages/Seeds";

const { Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: "数据总览" },
  { key: "/chat", icon: <MessageOutlined />, label: "对话检索" },
  { key: "/seeds", icon: <LinkOutlined />, label: "Seed 索引" },
  { key: "/pipeline-runs", icon: <ClockCircleOutlined />, label: "导入任务" },
  { key: "/pipeline-issues", icon: <WarningOutlined />, label: "质量问题" },
  { key: "/professor", icon: <TeamOutlined />, label: "教授" },
  { key: "/company", icon: <BankOutlined />, label: "企业" },
  { key: "/paper", icon: <FileTextOutlined />, label: "论文" },
  { key: "/patent", icon: <SafetyCertificateOutlined />, label: "专利" },
];

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey =
    NAV_ITEMS.find(
      (item) => item.key !== "/" && location.pathname.startsWith(item.key)
    )?.key ?? "/";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" width={200}>
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          科创数据平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Content style={{ margin: 24 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/seeds" element={<Seeds />} />
            <Route path="/pipeline-runs" element={<PipelineRuns />} />
            <Route path="/pipeline-runs/:runId" element={<PipelineRuns />} />
            <Route path="/pipeline-issues" element={<PipelineIssues />} />
            <Route path="/professor/:id" element={<ProfessorWorkbench />} />
            <Route path="/:domain" element={<DomainList />} />
            <Route path="/:domain/:id" element={<RecordDetail />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
