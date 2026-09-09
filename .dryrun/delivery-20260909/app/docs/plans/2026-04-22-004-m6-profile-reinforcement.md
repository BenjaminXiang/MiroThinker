---
title: "M6: Profile reinforcement from paper full text"
type: feat
status: active
date: 2026-04-22
milestone: M6
origin:
  - docs/plans/2026-04-20-003-agentic-rag-execution-plan.md  # §M6
depends_on:
  - 80acd19  # M2.4 Phase A — paper_full_text table
  - 4ff72c2  # M2.4 Phase B — orchestrator populates paper_full_text
---

# M6 — Profile Reinforcement Loop

## Overview

For each professor, pull their linked papers' `paper_full_text` rows (abstract + intro from M2.3) plus their existing profile fields, and use Gemma4 to synthesize an enriched `profile_summary`. Closes the loop 001 §5 flagged: most profs have empty / weak `profile_summary` because we never had a good source beyond the homepage bio paragraph.

Pure Python module + backfill CLI + mocked tests. No new DB schema. No operator blocker beyond running M2.4 to populate `paper_full_text` first.

## Requirements Trace

- **R1** (003 §M6.1): Function `generate_reinforced_profile_summary(prof, paper_contexts, llm_client, llm_model) -> str` takes a prof record + list of paper-context dicts, returns an enriched summary string (200-500 chars).
- **R2** (003 §M6.1): Use `resolve_professor_llm_settings("gemma4")` — shared resolver; no hardcoded keys (memory: Shape 1).
- **R3** (003 §M6.2): Backfill script `scripts/run_profile_summary_reinforcement.py` with `--limit`, `--only-missing` (default), `--resume`, `--dry-run`.
- **R4** (derived): `summary_reinforcement_needed(prof) -> bool` returns True when `profile_summary` is None / empty / < 50 chars.
- **R5** (derived): Never raise on LLM failure in core function — return empty string + log; caller decides.
- **R6** (derived): Backfill CLI never raises on per-prof failures; files pipeline_issue row, moves on.
- **R7** (derived): Tests all hermetic — mock LLM client, mock psycopg. No live model calls.

## Scope Boundaries

**In scope:**
- `apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py` — core generator + `summary_reinforcement_needed` helper
- `apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py` — CLI
- Writer to update `professor.profile_summary` + `updated_at` (uses existing `professor/canonical_writer.py` conventions; new small helper ok)

**Out of scope:**
- M6.3 incremental Milvus re-embed — separate follow-up (runs `ProfessorVectorizer` after reinforcement; doesn't need new code, just a `scripts/` wrapper)
- New DB columns — reuses V010's `profile_summary` + `profile_raw_text`
- Real-prod acceptance run — operator dogfood via `run_homepage_paper_ingest.py` first
- Paper-citation links INSIDE the generated summary — summary is prose, no citation markers

## Key Technical Decisions

- **Sync, not async** — matches M0.1-M5.2 pattern. Backfill is sequential.
- **Pure function core** — `generate_reinforced_profile_summary` takes pre-fetched paper contexts. Caller (backfill) does the SQL join.
- **Paper contexts capped at 5** per prof — Gemma4 context window + diminishing returns beyond top 5 papers.
- **Prompt structure**:
  - System: 深圳科创检索助手画像合成员, ≤500 chars Chinese, ground facts in provided abstracts, no hallucination.
  - User: prof name + institution + research_directions + bio (if any) + numbered paper list with abstracts.
- **Output validation**: strip markdown, reject if < 100 chars (LLM hiccup), cap at 800 chars.
- **`only_missing` filter**: `profile_summary IS NULL OR length(profile_summary) < 50`.
- **Resume JSONL**: `logs/data_agents/professor/summary_reinforcement_runs/<run_id>.jsonl`.

## Implementation Units

- [ ] **Unit 1: `summary_reinforcement.py` core + helper**

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/professor/summary_reinforcement.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_summary_reinforcement.py`

**Approach:**
- `@dataclass(frozen=True, slots=True) class PaperContext`: `title`, `abstract`, `intro`, `year`, `venue`.
- `@dataclass(frozen=True, slots=True) class ReinforcementResult`: `summary` (str, may be empty), `source_paper_count` (int), `error` (str | None).
- `summary_reinforcement_needed(profile_summary: str | None, *, min_length: int = 50) -> bool`.
- `generate_reinforced_profile_summary(prof_name, institution, research_directions, bio, paper_contexts, llm_client, llm_model, *, max_papers: int = 5, extra_body=None) -> ReinforcementResult`:
  - Cap paper_contexts to first `max_papers`.
  - Build prompt (system + user messages).
  - `llm_client.chat.completions.create(...)` with temperature 0.2, max_tokens 600.
  - Extract text, strip markdown code fences, whitespace-trim.
  - If `< 100 chars` or exception → return `ReinforcementResult(summary="", source_paper_count=N, error=<str>)`.
  - Else return `ReinforcementResult(summary=text, source_paper_count=N, error=None)`.

**Test scenarios:**
- `summary_reinforcement_needed`: None → True; "" → True; 30 chars → True; 100 chars → False.
- Happy path: mock LLM returns 300-char summary → `ReinforcementResult.summary` populated, `error=None`.
- Empty paper_contexts: still calls LLM with prof-only context, returns summary.
- max_papers=3 with 10 inputs: only first 3 reach the prompt (verify via captured mock call).
- LLM raises RuntimeError → `summary=""`, `error="<RuntimeError str>"`, no raise.
- LLM returns < 100 chars ("OK") → rejected, empty summary + error tag.
- LLM returns markdown-fenced text → fences stripped.

**Verification:**
- Tests pass.
- `grep -c "os.getenv\|API_KEY" summary_reinforcement.py` returns 0 (uses injected llm_client).

---

- [ ] **Unit 2: Backfill CLI**

**Files:**
- Create: `apps/miroflow-agent/scripts/run_profile_summary_reinforcement.py`
- Test: `apps/miroflow-agent/tests/scripts/test_run_profile_summary_reinforcement.py`

**Approach:**
- argparse: `--limit INT`, `--only-missing` (default True; `--all` inverse), `--resume [PATH]`, `--dry-run`, `--log-level`, `--max-papers INT default=5`.
- `_open_database_connection`, `_open_llm_client` (via resolve_professor_llm_settings("gemma4")).
- Main loop:
  1. `SELECT p.professor_id, p.canonical_name, p.institution, p.research_directions, p.profile_summary, p.profile_raw_text FROM professor p WHERE <filter>` + LIMIT.
  2. Build resume set from `--resume` JSONL.
  3. For each prof (skip if in resume):
     - `SELECT pft.title?, pft.abstract, pft.intro, ... FROM professor_paper_link ppl JOIN paper p ON ... JOIN paper_full_text pft ON ... WHERE ppl.professor_id = %s LIMIT 5`.
     - `PaperContext` list.
     - `generate_reinforced_profile_summary(...)`.
     - If success (non-empty summary): `UPDATE professor SET profile_summary=%s, updated_at=NOW() WHERE professor_id=%s` (unless `--dry-run`).
     - Append JSONL `{prof_id, status, source_paper_count, chars}`.
     - On exception: file pipeline_issue (reuse existing helper from homepage_ingest), continue.
- Emit JSON report at end.

**Test scenarios:**
- `--help` exits 0 with usage.
- `--dry-run --limit 1` dispatches, no UPDATE called.
- `--only-missing` adds `WHERE profile_summary IS NULL OR length(profile_summary) < 50` clause.
- `--all` removes that clause.
- Resume set skips processed profs.

**Verification:**
- All CLI tests pass; no DATABASE_URL required (mock conn).

## System-Wide Impact

- **Interaction graph:** First production caller of `summary_reinforcement.py`. Consumes `paper_full_text` (M2.4 Phase A), `professor_paper_link` (existing). Writes to `professor.profile_summary` column.
- **Error propagation:** Core never raises; CLI isolates per-prof failures via pipeline_issue.
- **Unchanged invariants:** No schema change. No touch to existing canonical_writer / vectorizer / retrieval files.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| LLM hallucinates facts not in abstracts | Prompt explicit "only use provided content"; acceptance is manual spot-check post-dogfood |
| Gemma4 quota / latency under batch load | `--limit` gives operator control; no concurrency |
| `paper_full_text` empty → all profs get LLM called with prof-only context, weak summaries | `--only-missing` + pre-filter check; alternatively skip profs with zero linked papers |
| Tests pass but real Gemma4 hits CJK encoding issues | Integration test via real endpoint optional follow-up |

## Sources & References

- **Origin:** 003 §M6
- **Upstream:** M2.3 (3420d86), M2.4 Phase A (80acd19)
- **Patterns:** `professor/llm_profiles.py::resolve_professor_llm_settings`, homepage_ingest's pipeline_issue filing
