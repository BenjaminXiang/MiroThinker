import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CompanyEnrichmentBatch from "./CompanyEnrichmentBatch";

function batchPayload(status = "queued") {
  return {
    batch_id: "55555555-5555-5555-5555-555555555555",
    status,
    current_stage: "generic_web_source_judgment",
    progress_percent: 37,
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
  };
}

function renderBatchPage(status = "queued") {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith("/start")) {
      return new Response(
        JSON.stringify({
          task_id: "66666666-6666-6666-6666-666666666666",
          status: "scheduled",
          domain: "company",
          parent_run_id: "22222222-2222-2222-2222-222222222222",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify(batchPayload(status)), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <MemoryRouter
      initialEntries={[
        "/company-enrichment-batches/55555555-5555-5555-5555-555555555555",
      ]}
    >
      <Routes>
        <Route
          path="/company-enrichment-batches/:batchId"
          element={<CompanyEnrichmentBatch />}
        />
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
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CompanyEnrichmentBatch", () => {
  it("renders progress and failure diagnostics", async () => {
    renderBatchPage();

    expect(await screen.findByText("企业增强批次")).toBeTruthy();
    expect(screen.getByText("37 / 100")).toBeTruthy();
    expect(screen.getByText("generic_web_source_judgment")).toBeTruthy();
    expect(screen.getByText("fetch timeout")).toBeTruthy();
    expect(screen.getByText("no_results: 5")).toBeTruthy();
    expect(screen.getByText("COMP-001")).toBeTruthy();
    expect(screen.getByText("synthesis_no_facts")).toBeTruthy();
  });

  it("starts the batch from the confirmation form", async () => {
    const fetchMock = renderBatchPage();

    const button = await screen.findByRole("button", { name: /启动增强/ });
    await act(async () => {
      fireEvent.click(button);
    });

    const startCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/start")
    );
    expect(startCall).toBeTruthy();
    const body = JSON.parse(String(startCall?.[1]?.body ?? "{}"));
    expect(body).toMatchObject({
      limit: 100,
      chunk_size: 20,
      stage_preset: "high_trust_sources",
      include_failed: false,
      skip_milvus: false,
    });
  });
});
