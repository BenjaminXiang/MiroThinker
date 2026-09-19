import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import Seeds from "./Seeds";
import type { Seed } from "../api";

const originalGetComputedStyle = window.getComputedStyle;

const { fetchSeedsMock } = vi.hoisted(() => ({ fetchSeedsMock: vi.fn() }));

vi.mock("../api", () => ({
  createSeed: vi.fn(),
  deleteSeed: vi.fn(),
  fetchSeeds: fetchSeedsMock,
  triggerSeed: vi.fn(),
  updateSeed: vi.fn(),
}));

function seed(overrides: Partial<Seed>): Seed {
  return {
    id: 1,
    school: "某某大学",
    department: null,
    seed_url: "https://example.edu/faculty",
    last_run_at: "2026-09-01T08:00:00Z",
    last_run_status: "never_run",
    failure_class: null,
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    ...overrides,
  };
}

function seedsPayload(): Seed[] {
  return [
    seed({ id: 1, school: "中断大学", last_run_status: "interrupted" }),
    seed({ id: 2, school: "成功大学", last_run_status: "success" }),
    seed({ id: 3, school: "失败大学", last_run_status: "failure" }),
  ];
}

beforeEach(() => {
  fetchSeedsMock.mockResolvedValue(seedsPayload());
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
  vi.clearAllMocks();
});

describe("Seeds interrupted status", () => {
  it("exposes the interrupted state as a pill and a summary stat", async () => {
    render(<Seeds />);

    expect(await screen.findByText("中断大学")).toBeTruthy();

    const pill = screen.getByRole("button", { name: "已中断 1" });
    expect(pill.className).toContain("seed-pill-interrupted");

    const stat = document.querySelector(".seed-sum-interrupted .seed-sum-n");
    expect(stat?.textContent).toBe("1");
    expect(
      document.querySelector(".seed-sum-interrupted .seed-sum-l")?.textContent
    ).toBe("已中断");
  });

  it("gives every counted status its own stat cell, never_run included", async () => {
    render(<Seeds />);

    expect(await screen.findByText("中断大学")).toBeTruthy();

    for (const [tone, label] of [
      ["interrupted", "已中断"],
      ["never", "未运行"],
      ["success", "success"],
      ["failure", "failure"],
      ["missing", "adapter 缺失"],
    ]) {
      expect(
        document.querySelector(`.seed-sum-${tone} .seed-sum-l`)?.textContent
      ).toBe(label);
    }
  });

  it("filters the table to interrupted seeds when the pill is clicked", async () => {
    render(<Seeds />);

    expect(await screen.findByText("中断大学")).toBeTruthy();
    expect(screen.getByText("成功大学")).toBeTruthy();

    const pill = screen.getByRole("button", { name: "已中断 1" });
    fireEvent.click(pill);

    expect(pill.className).toContain("seed-pill-active");
    expect(screen.getByText("中断大学")).toBeTruthy();
    expect(screen.queryByText("成功大学")).toBeNull();
    expect(screen.queryByText("失败大学")).toBeNull();
  });
});
