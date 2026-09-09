import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RecordDetail from "./RecordDetail";

const originalGetComputedStyle = window.getComputedStyle;

function companyDetailPayload() {
  return {
    id: "COMP-UI-1",
    object_type: "company",
    display_name: "深圳测试科技",
    core_facts: {
      name: "深圳测试科技",
      industry: "人工智能",
      products: [
        {
          product_id: "PROD-hidden",
          name: "Test Product",
          description: "面向企业客户的智能分析平台。",
          source_url: "https://example.com/source-hidden",
          quality_status: "ready",
          confidence: 0.95,
          product_category: "智能分析平台",
          technical_tags: ["AI", "数据分析"],
          target_customers: ["企业客户", "运营团队"],
          application_scenarios: ["客户运营", "数据洞察"],
        },
      ],
      application_scenarios: [
        {
          scenario_id: "SCN-hidden",
          scenario_name: "客户运营",
          description: "用于提升客户留存。",
          target_customer: "运营团队",
          source_url: "https://example.com/scenario-hidden",
          quality_status: "ready",
          confidence: 0.8,
        },
      ],
      recent_events: [
        {
          event_id: "EVT-hidden",
          event_type: "funding",
          event_date: "2026-01-01",
          summary: "完成融资",
          normalized: { amount_cny_wan: null },
          source_url: "https://example.com/event-hidden",
        },
      ],
    },
    summary_fields: {
      profile_summary: "深圳测试科技是一家企业服务公司。",
    },
    evidence: [
      {
        source_type: "public_web",
        source_url: "https://example.com/evidence-source",
        source_file: null,
        fetched_at: "2026-05-28T00:00:00Z",
        snippet: "来源网页摘要",
        confidence: 0.91,
      },
    ],
    last_updated: "2026-05-28T00:00:00Z",
    quality_status: "ready",
  };
}

function renderCompanyDetail() {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.includes("/related")) {
      return new Response(
        JSON.stringify({ papers: [], patents: [], companies: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify(companyDetailPayload()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/company/COMP-UI-1"]}>
      <Routes>
        <Route path="/:domain/:id" element={<RecordDetail />} />
      </Routes>
    </MemoryRouter>
  );
  return fetchMock;
}

function paperDetailPayload() {
  const summaryZh = "这是一段论文中文总结。";
  return {
    id: "PAPER-UI-1",
    object_type: "paper",
    display_name: "A Paper With Summary",
    core_facts: {
      title: "A Paper With Summary",
      abstract: "An English abstract.",
      year: 2026,
    },
    summary_fields: {
      summary_text: summaryZh,
      summary_zh: summaryZh,
    },
    evidence: [],
    last_updated: "2026-06-09T00:00:00Z",
    quality_status: "ready",
  };
}

function renderPaperDetail() {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.includes("/related")) {
      return new Response(
        JSON.stringify({
          papers: [
            {
              id: "PROF-RELATED",
              object_type: "professor",
              display_name: "Related Professor",
              core_facts: {},
              summary_fields: {},
              evidence: [],
              last_updated: "2026-06-09T00:00:00Z",
              quality_status: "ready",
            },
          ],
          patents: [],
          companies: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify(paperDetailPayload()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/paper/PAPER-UI-1"]}>
      <Routes>
        <Route path="/:domain/:id" element={<RecordDetail />} />
      </Routes>
    </MemoryRouter>
  );
  return fetchMock;
}

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, "getComputedStyle", {
    writable: true,
    value: (element: Element) => originalGetComputedStyle(element),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecordDetail company business fields", () => {
  it("renders company products with only business-facing product fields", async () => {
    renderCompanyDetail();

    expect(await screen.findByRole("heading", { name: /深圳测试科技/ })).toBeTruthy();
    const productSection = screen.getByText("产品").closest(".ant-card");
    expect(productSection).not.toBeNull();
    const scope = within(productSection as HTMLElement);

    expect(scope.getByText("产品名称")).toBeTruthy();
    expect(scope.getByText("产品简介")).toBeTruthy();
    expect(scope.getByText("产品类别")).toBeTruthy();
    expect(scope.getByText("技术标签")).toBeTruthy();
    expect(scope.getByText("目标客户")).toBeTruthy();
    expect(scope.getByText("应用场景")).toBeTruthy();
    expect(scope.getByText("Test Product")).toBeTruthy();
    expect(scope.getByText("面向企业客户的智能分析平台。")).toBeTruthy();
    expect(scope.getByText("AI")).toBeTruthy();
    expect(scope.getByText("客户运营")).toBeTruthy();

    expect(scope.queryByText("product_id")).toBeNull();
    expect(scope.queryByText("source_url")).toBeNull();
    expect(scope.queryByText("quality_status")).toBeNull();
    expect(scope.queryByText("confidence")).toBeNull();
    expect(scope.queryByText("操作")).toBeNull();
    expect(scope.queryByText("PROD-hidden")).toBeNull();
    expect(scope.queryByText("https://example.com/source-hidden")).toBeNull();
  });

  it("shows product review state and review actions separately from product fields", async () => {
    renderCompanyDetail();

    expect(await screen.findByRole("heading", { name: /深圳测试科技/ })).toBeTruthy();
    const productSection = screen.getByText("产品").closest(".ant-card");
    expect(productSection).not.toBeNull();
    const scope = within(productSection as HTMLElement);

    expect(scope.getByText("审核状态")).toBeTruthy();
    expect(scope.getByRole("button", { name: /接\s*受/ })).toBeTruthy();
    expect(scope.getByRole("button", { name: "待审核" })).toBeTruthy();
    expect(scope.getByRole("button", { name: /驳\s*回/ })).toBeTruthy();
    expect(scope.queryByText("quality_status")).toBeNull();
  });

  it("places company sections in business review order", async () => {
    renderCompanyDetail();

    expect(await screen.findByRole("heading", { name: /深圳测试科技/ })).toBeTruthy();
    const text = document.body.textContent ?? "";

    const basicIndex = text.indexOf("基本信息");
    const productIndex = text.indexOf("产品");
    const scenarioIndex = text.indexOf("应用场景");
    const recentIndex = text.indexOf("最近动态");

    expect(basicIndex).toBeGreaterThanOrEqual(0);
    expect(productIndex).toBeGreaterThan(basicIndex);
    expect(scenarioIndex).toBeGreaterThan(productIndex);
    expect(recentIndex).toBeGreaterThan(scenarioIndex);
  });

  it("uses company-specific summary labels instead of professor labels", async () => {
    renderCompanyDetail();

    const companySummaryLabel = await screen.findByText("公司简介");
    const section = companySummaryLabel.closest(".ant-card");
    expect(section).not.toBeNull();
    expect(within(section as HTMLElement).queryByText("个人简介")).toBeNull();
  });

  it("keeps source links in the evidence section instead of product fields", async () => {
    renderCompanyDetail();

    expect(await screen.findByRole("heading", { name: /深圳测试科技/ })).toBeTruthy();
    const productSection = screen.getByText("产品").closest(".ant-card");
    expect(productSection).not.toBeNull();
    expect(
      within(productSection as HTMLElement).queryByText(
        "https://example.com/source-hidden"
      )
    ).toBeNull();

    const sourceSection = screen.getByText("数据来源").closest(".ant-card");
    expect(sourceSection).not.toBeNull();
    const scope = within(sourceSection as HTMLElement);
    expect(scope.getByText("公开网页")).toBeTruthy();
    expect(scope.getByText("https://example.com/evidence-source")).toBeTruthy();
    expect(scope.getByText("来源网页摘要")).toBeTruthy();
  });
});

describe("RecordDetail paper summary fields", () => {
  it("uses paper-specific title label in basic facts", async () => {
    renderPaperDetail();

    expect(await screen.findByRole("heading", { name: /A Paper With Summary/ })).toBeTruthy();
    const basicSection = screen.getByText("基本信息").closest(".ant-card");
    expect(basicSection).not.toBeNull();
    const scope = within(basicSection as HTMLElement);

    expect(scope.getByText("标题")).toBeTruthy();
    expect(scope.queryByText("职称")).toBeNull();
  });

  it("deduplicates summary_text when it aliases summary_zh", async () => {
    renderPaperDetail();

    expect(await screen.findByRole("heading", { name: /A Paper With Summary/ })).toBeTruthy();

    expect(screen.getByText("中文摘要")).toBeTruthy();
    expect(screen.getAllByText("这是一段论文中文总结。")).toHaveLength(1);
  });

  it("labels related professors by object_type even when backend uses papers bucket", async () => {
    renderPaperDetail();

    expect(await screen.findByRole("heading", { name: /A Paper With Summary/ })).toBeTruthy();

    expect(await screen.findByText("教授 (1)")).toBeTruthy();
    expect(screen.queryByText("论文 (1)")).toBeNull();
    expect(screen.getByText("Related Professor")).toBeTruthy();
  });
});
