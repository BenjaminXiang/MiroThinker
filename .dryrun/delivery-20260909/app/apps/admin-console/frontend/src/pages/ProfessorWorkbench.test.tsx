import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { AdminProfessorDetail } from "../api";
import ProfessorWorkbench from "./ProfessorWorkbench";
import RecordDetail from "./RecordDetail";

const originalGetComputedStyle = window.getComputedStyle;

const detail: AdminProfessorDetail = {
  professor_id: "PROF-ADMIN-1",
  sections: {
    identity: {
      canonical_name: "Ada Lovelace",
      canonical_name_en: "Ada Lovelace",
      institution: "Test University",
      department: "Computer Science",
      title: "Professor",
      identity_status: "resolved",
      lifecycle_state: "active",
      lifecycle_merged_into_id: null,
    },
    contact: { email: "ada@example.edu" },
    research_output: {
      research_overview:
        "My research focuses on developing trustworthy artificial intelligence for medical image analysis.",
      facts: [
        {
          fact_type: "research_topic",
          value_raw: "Computing",
          source_page_url: "https://example.edu/ada",
        },
        {
          fact_type: "education",
          value_raw: "Analytical Engine University | PhD | Computing | 2020-2024",
          source_page_url: "https://example.edu/ada",
        },
        {
          fact_type: "work_experience",
          value_raw: "Test University | Professor | 2024-present",
          source_page_url: "https://example.edu/ada",
        },
        {
          fact_type: "award",
          value_raw: "Best analytical engine paper award.",
          source_page_url: "https://example.edu/ada",
        },
        {
          fact_type: "academic_position",
          value_raw: "Journal of Computing, Associate Editor.",
          source_page_url: "https://example.edu/ada",
        },
        {
          fact_type: "contact",
          value_raw: "ada@example.edu",
          source_page_url: "https://example.edu/ada",
        },
      ],
      papers: [{ paper_id: "PAPER-1", title_clean: "Notes", year: 2026 }],
      patents: [{ patent_id: "PAT-1", title_clean: "Engine", patent_number: null }],
      paper_summary: "Published computing papers.",
      patent_summary: "Inventive computing devices.",
    },
    experience: {
      status: "populated",
      affiliations: [
        {
          institution: "Test University",
          department: "Computer Science",
          title: "Professor",
          source_page_url: "https://example.edu/ada",
        },
      ],
    },
    cleaned_summary: { profile_summary: "Works on analytical engines." },
    sources_evidence: {
      sources: [
        {
          url: "https://example.edu/ada",
          page_role: "official_profile",
          is_official_source: true,
        },
      ],
      admin_actions: [],
    },
    quality_diagnosis: {
      status: "low_confidence",
      reasons: [
        {
          rule_id: "missing_research_topic",
          stage: "research_directions",
          severity: "medium",
          description: "professor quality gate: missing_research_topic",
        },
      ],
      open_issue_count: 1,
      blocking_issue_count: 1,
      non_blocking_issue_count: 0,
      blocking_reasons: [
        {
          rule_id: "missing_research_topic",
          stage: "research_directions",
          severity: "medium",
          description: "professor quality gate: missing_research_topic",
        },
      ],
      non_blocking_reasons: [],
    },
  },
};

function renderWorkbench(payload = detail) {
  const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith("/mark")) {
      return new Response(
        JSON.stringify({
          professor_id: "PROF-ADMIN-1",
          action: "confirm_ready",
          quality_status: "ready",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/professor/PROF-ADMIN-1"]}>
      <Routes>
        <Route path="/professor/:id" element={<ProfessorWorkbench />} />
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

describe("ProfessorWorkbench", () => {
  it("renders populated facts, provenance, diagnosis, and marking actions", async () => {
    const fetchMock = renderWorkbench();

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeTruthy();
    expect(screen.getByText("质量诊断")).toBeTruthy();
    expect(screen.getByText("missing_research_topic")).toBeTruthy();
    expect(screen.getByText("研究领域介绍")).toBeTruthy();
    expect(
      screen.getByText(
        "My research focuses on developing trustworthy artificial intelligence for medical image analysis."
      )
    ).toBeTruthy();
    expect(screen.getByText("Computing")).toBeTruthy();
    expect(screen.getByText("学术兼职")).toBeTruthy();
    expect(screen.getByText("Journal of Computing, Associate Editor.")).toBeTruthy();
    expect(screen.getByText("教育经历")).toBeTruthy();
    expect(
      screen.getByText("Analytical Engine University | PhD | Computing | 2020-2024")
    ).toBeTruthy();
    expect(screen.getByText("工作经历")).toBeTruthy();
    expect(screen.getByText("Test University | Professor | 2024-present")).toBeTruthy();
    expect(screen.getByText("荣誉奖项")).toBeTruthy();
    expect(screen.getByText("Best analytical engine paper award.")).toBeTruthy();
    const paperLink = screen.getByRole("link", { name: "Notes" });
    expect(paperLink.getAttribute("href")).toBe("/paper/PAPER-1");
    expect(screen.getAllByText("https://example.edu/ada").length).toBeGreaterThan(0);
    const experienceSection = screen
      .getByRole("heading", { name: "教育与经历" })
      .closest("section");
    expect(experienceSection).not.toBeNull();
    expect(
      within(experienceSection as HTMLElement).getByText(
        "Test University | Professor | 2024-present"
      )
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /确认就绪/ }));
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "Source evidence reviewed." },
    });
    fireEvent.click(await screen.findByRole("button", { name: /提\s*交/ }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => String(url).endsWith("/mark") && init?.method === "POST"
        )
      ).toBe(true);
    });
  });

  it("renders not_extracted experience state", async () => {
    renderWorkbench({
      ...detail,
      sections: {
        ...detail.sections,
        research_output: {
          ...detail.sections.research_output,
          facts: [
            {
              fact_type: "research_topic",
              value_raw: "Computing",
              source_page_url: "https://example.edu/ada",
            },
          ],
        },
        experience: { status: "not_extracted", affiliations: [] },
      },
    });

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeTruthy();
    expect(screen.getByText("not_extracted")).toBeTruthy();
  });

  it("renders historical diagnostics separately from release blockers", async () => {
    renderWorkbench({
      ...detail,
      sections: {
        ...detail.sections,
        quality_diagnosis: {
          status: "ready",
          reasons: [
            {
              rule_id: "missing_research_topic",
              stage: "research_directions",
              severity: "medium",
              description: "historical professor quality gate issue",
            },
          ],
          open_issue_count: 108,
          blocking_issue_count: 0,
          non_blocking_issue_count: 108,
          blocking_reasons: [],
          non_blocking_reasons: [
            {
              rule_id: "missing_research_topic",
              stage: "research_directions",
              severity: "medium",
              description: "historical professor quality gate issue",
            },
          ],
        },
      },
    });

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeTruthy();
    expect(screen.getByText("发布阻塞 0")).toBeTruthy();
    expect(screen.getByText("历史诊断 108")).toBeTruthy();
    expect(screen.getByText("无发布阻塞诊断")).toBeTruthy();
    expect(screen.queryByText("未关闭问题 108")).toBeNull();
    expect(screen.queryByText("missing_research_topic")).toBeNull();
  });

  it("routes professor details to the workbench instead of the generic editor", async () => {
    renderWorkbenchWithRecordDetail();

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /确认就绪/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /编辑/ })).toBeNull();
  });
});

function renderWorkbenchWithRecordDetail() {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(detail), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/professor/PROF-ADMIN-1"]}>
      <Routes>
        <Route path="/:domain/:id" element={<RecordDetail />} />
      </Routes>
    </MemoryRouter>
  );
  return fetchMock;
}
