import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PipelineRuns from "./PipelineRuns";

const originalGetComputedStyle = window.getComputedStyle;

function pipelineRunDetailPayload(status = "succeeded") {
  return {
    run_id: "22222222-2222-2222-2222-222222222222",
    run_kind: "import_xlsx",
    status,
    run_scope: {
      domain: "company",
      source: "admin-console-upload",
      result_summary: { rows_read: 6527, records_parsed: 6527 },
    },
    triggered_by: "admin-console",
    started_at: "2026-05-29T04:00:00Z",
    finished_at: status === "running" ? null : "2026-05-29T04:01:00Z",
    items_processed: 6512,
    items_failed: 0,
    error_summary: null,
    source_pages: [],
    company_enrichment_batches: [
      {
        batch_id: "55555555-5555-5555-5555-555555555555",
        status: "running",
        current_stage: "generic_web_source_judgment",
        companies_total: 100,
        companies_selected: 100,
        companies_processed: 37,
        companies_succeeded: 35,
        companies_failed: 2,
        query_count: 12,
        source_result_count: 44,
        accepted_source_count: 8,
        rejected_source_count: 16,
        product_count: 6,
        scenario_count: 3,
        official_product_count: 2,
        funding_event_count: 4,
        vector_refreshed_count: 35,
        llm_failure_count: 1,
        status_counts: { succeeded: 35, failed: 2 },
        current_stage_counts: { generic_web_source_judgment: 37 },
        miss_reasons: { no_results: 5 },
        official_failure_reasons: { http_403: 2 },
        rejected_candidate_reasons: { candidate_belongs_to_other_company: 4 },
        source_counts_by_adapter: {
          iyiou: {
            query_count: 3,
            result_count: 20,
            accepted_count: 5,
            rejected_count: 7,
          },
        },
        company_diagnostics: [
          {
            company_id: "COMP-001",
            status: "partial",
            current_stage: "source_product_extract",
            miss_reason: "synthesis_no_facts",
            last_error: null,
            query_count: 3,
            source_result_count: 20,
            accepted_source_count: 5,
            rejected_source_count: 7,
            product_count: 0,
            scenario_count: 0,
            official_product_count: 0,
            funding_event_count: 1,
            vector_refreshed: false,
            stage_status: {
              official_product_capture: { miss_reason: "http_403" },
            },
            updated_at: "2026-05-29T04:01:00Z",
          },
        ],
        company_diagnostics_truncated: false,
        last_error: "fetch timeout",
        created_at: "2026-05-29T04:00:00Z",
        started_at: "2026-05-29T04:00:05Z",
        finished_at: null,
        updated_at: "2026-05-29T04:02:00Z",
      },
    ],
  };
}

function renderPipelineRunDetail(status = "succeeded") {
  const fetchMock = vi.fn(async () => {
    return new Response(JSON.stringify(pipelineRunDetailPayload(status)), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <MemoryRouter
      initialEntries={["/pipeline-runs/22222222-2222-2222-2222-222222222222"]}
    >
      <Routes>
        <Route path="/pipeline-runs/:runId" element={<PipelineRuns />} />
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
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PipelineRuns company enrichment status", () => {
  it("renders upload-scoped company enrichment batch progress", async () => {
    renderPipelineRunDetail();

    expect(await screen.findByText("企业增强处理状态")).toBeTruthy();
    const section = screen.getByText("企业增强处理状态").closest("div");
    expect(section).not.toBeNull();
    const scope = within(section as HTMLElement);

    expect(scope.getByText("generic_web_source_judgment")).toBeTruthy();
    expect(scope.getByText("37 / 100")).toBeTruthy();
    expect(scope.getByText("35")).toBeTruthy();
    expect(scope.getByText("2")).toBeTruthy();
    expect(scope.getByText("fetch timeout")).toBeTruthy();
    expect(scope.getAllByText("来源接受/拒绝").length).toBeGreaterThan(0);
    expect(scope.getAllByText("8 / 16").length).toBeGreaterThan(0);
    expect(scope.getAllByText("产品/场景/动态").length).toBeGreaterThan(0);
    expect(scope.getAllByText("6 / 3 / 4").length).toBeGreaterThan(0);
    expect(scope.getByText("向量刷新")).toBeTruthy();
    expect(scope.getByText("35 / 100")).toBeTruthy();
    expect(scope.getByText("官网失败原因")).toBeTruthy();
    expect(
      scope.getAllByText((_, element) => element?.textContent === "http_403: 2")
        .length
    ).toBeGreaterThan(0);
    expect(scope.getByText("候选拒绝原因")).toBeTruthy();
    expect(
      scope.getAllByText(
        (_, element) =>
          element?.textContent === "candidate_belongs_to_other_company: 4"
      ).length
    ).toBeGreaterThan(0);
    expect(scope.getByText("来源分布")).toBeTruthy();
    expect(
      scope.getAllByText(
        (_, element) =>
          element?.textContent ===
          "iyiou: 查询 3 / 结果 20 / 接受 5 / 拒绝 7"
      ).length
    ).toBeGreaterThan(0);
    expect(scope.getByText("公司级诊断样例")).toBeTruthy();
    expect(
      scope.getAllByText(
        (_, element) =>
          element?.textContent ===
          "COMP-001: partial / source_product_extract / synthesis_no_facts"
      ).length
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /检索验收/ })).toBeNull();
  });

  it("summarizes company upload processing progress in operator language", async () => {
    renderPipelineRunDetail();

    expect(await screen.findByText("企业上传处理总览")).toBeTruthy();
    expect(screen.getByText("后台增强正在运行")).toBeTruthy();
    expect(screen.getByText("基础数据已导入，企业详情页可查看。")).toBeTruthy();
    expect(screen.getByText("外部增强正在执行，完成后会更新产品、场景、动态和简介。")).toBeTruthy();
    expect(screen.getByText("已处理企业")).toBeTruthy();
    expect(screen.getAllByText("37 / 100").length).toBeGreaterThan(0);
    expect(screen.getByText("检索刷新")).toBeTruthy();
    expect(screen.getAllByText("35 / 100").length).toBeGreaterThan(0);
    expect(screen.getByText("当前阶段：generic_web_source_judgment")).toBeTruthy();
    expect(screen.getByText("以实时增强批次为准")).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开企业列表" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Milvus 回填/ })).toBeNull();
  });

  it("refreshes detail while a company enrichment batch is active", async () => {
    vi.useFakeTimers();
    const fetchMock = renderPipelineRunDetail("succeeded");

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("企业增强处理状态")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
