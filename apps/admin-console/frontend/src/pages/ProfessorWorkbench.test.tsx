import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProfessorWorkbenchView, type ProfessorAdminDetail } from "./ProfessorWorkbench";

function detail(overrides: Partial<ProfessorAdminDetail> = {}): ProfessorAdminDetail {
  return {
    identity: {
      professor_id: "PROF-1",
      canonical_name: "Ready Professor",
      canonical_name_en: "Ready Professor",
      canonical_name_zh: "Ready Professor",
      aliases: [],
      institution: "南方科技大学",
      department: "计算机科学与工程系",
      title: "教授",
      discipline_family: "computer_science",
      identity_status: "resolved",
    },
    contact: {
      facts: {
        contact: [
          {
            fact_type: "contact",
            value_raw: "ready@example.test",
            source_url: "https://example.test/ready",
            source_role: "official_profile",
            confidence: 0.99,
          },
        ],
      },
      official_profile_url: "https://example.test/ready",
    },
    research_and_output: {
      research_topics: [
        {
          fact_type: "research_topic",
          value_raw: "机器学习",
          source_url: "https://example.test/ready",
          confidence: 0.95,
        },
      ],
      h_index: 7,
      citation_count: 120,
      paper_count: 4,
      representative_papers: [],
    },
    experience: {
      status: "populated",
      facts: {
        education: [
          {
            fact_type: "education",
            value_raw: "PhD, Example University",
            source_url: "https://example.test/ready",
            confidence: 0.92,
          },
        ],
      },
    },
    cleaned_summary: {
      profile_summary: "Ready Professor studies machine learning.",
    },
    sources_and_evidence: {
      primary_source: {
        url: "https://example.test/ready",
        page_role: "official_profile",
        is_official_source: true,
      },
      affiliations: [],
      provenance: [],
    },
    quality_diagnosis: {
      status: "ready",
      reasons: [],
      open_issues: [],
      latest_admin_action: null,
    },
    ...overrides,
  };
}

const populatedHtml = renderToStaticMarkup(
  <ProfessorWorkbenchView detail={detail()} onMark={async () => {}} marking={false} />
);

assert.match(populatedHtml, /质量诊断/);
assert.match(populatedHtml, /confirm_ready/);
assert.match(populatedHtml, /send_to_review/);
assert.match(populatedHtml, /flag_recrawl/);
assert.match(populatedHtml, /PhD, Example University/);
assert.match(populatedHtml, /https:\/\/example\.test\/ready/);

const placeholderHtml = renderToStaticMarkup(
  <ProfessorWorkbenchView
    detail={detail({ experience: { status: "not_extracted", facts: {} } })}
    onMark={async () => {}}
    marking={false}
  />
);

assert.match(placeholderHtml, /not_extracted/);
assert.doesNotMatch(placeholderHtml, /PhD, Example University/);
