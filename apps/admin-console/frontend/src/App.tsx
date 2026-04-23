import { Layout, Menu } from "antd";
import {
  DashboardOutlined,
  TeamOutlined,
  BankOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  MessageOutlined,
} from "@ant-design/icons";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import DomainList from "./pages/DomainList";
import RecordDetail from "./pages/RecordDetail";
import Chat from "./pages/Chat";

const { Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: "数据总览" },
  { key: "/chat", icon: <MessageOutlined />, label: "对话检索" },
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
            <Route path="/:domain" element={<DomainList />} />
            <Route path="/:domain/:id" element={<RecordDetail />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
