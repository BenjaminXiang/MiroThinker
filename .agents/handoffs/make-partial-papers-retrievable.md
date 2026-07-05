# Handoff → Codex: make-partial-papers-retrievable (one Ready slice)

> Claude → Codex. References artifact paths, does NOT copy the spec. Read the
> change + verification contract in place before editing.

## What to build

Implement the **Ready** OpenSpec change `make-partial-papers-retrievable` as
**one slice, all four seams + verification**. State: Specified → Ready (Claude
accepted the verification contract).

## Read first (in this order)

1. `openspec/changes/make-partial-papers-retrievable/proposal.md` (why + scope + non-goals)
2. `openspec/changes/make-partial-papers-retrievable/design.md` (the 4 seams, D1–D5 decisions)
3. `openspec/changes/make-partial-papers-retrievable/tasks.md` (your checklist; do Task 1.1/1.2 are Claude-owned — already done; start at Task 0)
4. `.agents/runs/make-partial-papers-retrievable/verification-contract.md` (RED/GREEN; you must NOT change RED or GREEN)
5. `openspec/changes/make-partial-papers-retrievable/specs/data-quality-gating/spec.md` + `specs/agentic-rag-retrieval/spec.md` (the contract)

## The four seams (all mandatory — no half seam)

| # | File | Change |
|---|---|---|
| 1 | `apps/miroflow-agent/src/data_agents/quality/gating_contract.py` | `is_indexable` gains optional `paper_has_rich_text`; admit `partial` + rich-text; `ready` unaffected; professor/company/patent unaffected |
| 2 | `apps/miroflow-agent/src/data_agents/paper/milvus_backfill.py` | backfill SQL LEFT JOINs `paper_full_text` for `has_rich_text`; `_is_indexable_paper` admits partial+rich-text, keeps deleting title-only partials' chunks |
| 3 | `apps/miroflow-agent/src/data_agents/service/retrieval.py` | `_filter_ready_only`/`_allow_non_ready_exact_paper` admit vector-recalled partial+rich-text; drop title-only partial + needs_enrichment (defensive vs stale Milvus) |
| 4 | `apps/miroflow-agent/src/data_agents/service/retrieval.py` | `_paper_title_snippet` chain → `summary_zh → abstract_clean → paper_full_text.abstract → title`; title-exact SELECT LEFT JOINs `paper_full_text`; vector Evidence snippet = chunk `content_text` for partials |

A seam missing = a distinct half-finished state. Seam 3 missing → embedded-but-
dropped-pre-rerank (eval shows no gain). Seam 4 missing → recalled-but-empty-
snippet → invisible to answer (eval shows no gain). All four ship together.

## First action: Task 0 — measure D3

Per design D5 + tasks 2.1: compare `paper_chunks` per-paper presence (Milvus)
against `SELECT paper_id FROM paper WHERE quality_status='ready' AND
identity_status NOT IN ('rejected','merged')`. Persist to
`.agents/runs/make-partial-papers-retrievable/d3-measure.json`. If D3 > 0,
note it (separate predecessor slice); proceed regardless — your unlock
(partials) is disjoint from D3.

## ⚠️ Localhost / sandbox boundary (read carefully)

Your default sandbox **blocks localhost network**. These steps need localhost
(Postgres :15432, the running backend, Milvus single-writer at
`apps/miroflow-agent/milvus.db`):

- Task 0 (D3 measure) — needs Postgres + Milvus
- Task 8.2 (one-time rebackfill) — needs backend up (Milvus single-writer)
- Task 8.3 (eval `eval_recall_chat.py` + precision oracle) — needs backend + Milvus + proxy-unset

**Rule:** attempt them; if the sandbox blocks localhost, **STOP that step,
report "sandbox-blocked on localhost" with the exact error, and leave the code
in the contract-suite-green state** (tasks 3–7 + 8.1 + 8.4 done). Do NOT claim
GREEN on the eval you could not run, and do NOT fake the rebackfill. Claude
will run D3/rebackfill/eval with the backend up + proxy-unset, then re-review.

The contract unit tests (tasks 3.1–3.4, 8.1) and `openspec validate --strict`
(8.4) are local pytest/CLI — these are your reliable GREEN for the code slice.

## Proxy unset (any localhost step; per [[env_proxy_bypass]])

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
```

## Do-not rules (from verification contract)

- Do NOT index title-only `partial` papers (~7,212) — precision risk, out of scope.
- Do NOT change the `quality_status` enum, `ready` criteria, `identity_status`
  semantics, `quality/threshold_config.py` thresholds, or any alembic migration.
- Do NOT add a persisted `retrievable`/`indexed` column to `paper` — the
  predicate is derived from `paper_full_text` (unify "no second signal" holds).
- Do NOT broaden scope to chase the recall number — STOP + report if GREEN short.
- Do NOT declare Accept on a unit-suite pass alone — eval is acceptance (if you
  can't run eval, leave that to Claude).

## Report back (Codex)

- Files changed (per seam).
- Contract-suite command + pass count (the four test files).
- Regression suite result (`tests/data_agents/quality/`, `paper/`, `service/`).
- D3 measure value (or sandbox-blocked error).
- If reached: rebackfill `BackfillReport` + eval before/after JSON + precision
  oracle result. If sandbox-blocked: state that explicitly so Claude runs them.
- `openspec validate make-partial-papers-retrievable --strict` output.
- State: "code slice complete, contract-suite green; eval/rebackfill/D3 =
  sandbox-blocked (Claude to run)" OR "fully GREEN" — be exact.

## Claude review after you report

Accept / Revise / Reject (CLAUDE.md §12). Until then, the slice is
Candidate, not Accepted — no other slice may depend on it.
