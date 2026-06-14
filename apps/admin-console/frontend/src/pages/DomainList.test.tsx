import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import DomainList, { uploadFailureMessage } from "./DomainList";

const originalGetComputedStyle = window.getComputedStyle;

function professorListPayload() {
  return {
    items: [
      {
        id: "PROF-SUMMARY-1",
        object_type: "professor",
        display_name: "Ahmed Elazab",
        core_facts: {
          institution: "清华大学深圳国际研究生院",
          department: null,
          title: "助理教授，博士生导师",
        },
        summary_fields: {
          profile_summary:
            "Ahmed Elazab现任清华大学深圳国际研究生院助理教授，博士生导师。研究方向包括trustworthy artificial intelligence、medical image analysis。",
        },
        evidence: [],
        last_updated: "2026-05-27T09:18:37.582940+00:00",
        quality_status: "ready",
        lifecycle_state: "active",
        lifecycle_merged_into_id: null,
      },
    ],
    total: 1,
    page: 1,
    page_size: 20,
  };
}

function filterOptionsPayload() {
  return { options: [] };
}

function renderProfessorList() {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
    const path = String(url);
    if (path.startsWith("/api/professor/filters/")) {
      return new Response(JSON.stringify(filterOptionsPayload()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (path.startsWith("/api/professor")) {
      return new Response(JSON.stringify(professorListPayload()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <MemoryRouter initialEntries={["/professor"]}>
      <Routes>
        <Route path="/:domain" element={<DomainList />} />
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

describe("DomainList professor summaries", () => {
  it("renders profile summary previews on the professor list", async () => {
    renderProfessorList();

    expect(await screen.findByText("Ahmed Elazab")).toBeTruthy();
    expect(
      screen.getByText(/Ahmed Elazab现任清华大学深圳国际研究生院助理教授/)
    ).toBeTruthy();
  });
});

describe("uploadFailureMessage", () => {
  it("maps nginx and API 413 upload errors to a large-file message", () => {
    expect(
      uploadFailureMessage(
        new Error(
          "API error: 413 Request Entity Too Large <html><title>413 Request Entity Too Large</title></html>"
        )
      )
    ).toContain("文件过大");

    expect(
      uploadFailureMessage(
        new Error(
          'API error: 413 Request Entity Too Large {"detail":{"code":"upload_too_large","max_mib":128}}'
        )
      )
    ).toContain("128");
  });
});
