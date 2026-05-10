---
change_id: paper-summary-text-contract-fix
type: bugfix (admin API contract drift)
weight: Tiny / Lite
behavior_change: true (user-facing API output changes)
code_change: yes (1-line)
adds_requirements: false (corrects existing Shared-Spec §4.2.1 contract)
created: 2026-05-10
canonical_input:
  - docs/Paper-Requirement-Review-2026-05-10.md §3.1 P3
  - docs/Data-Agent-Shared-Spec.md §4.2.1
  - docs/audits/paper-requirement-code-reconciliation-2026-05-10.md (drift item)
---

# Proposal: paper-summary-text-contract-fix

## Why

`docs/Data-Agent-Shared-Spec.md §4.2.1` and `docs/Paper-Data-Agent-PRD.md
§4.3` declare that `summary_text` (returned by the admin / chat APIs and
embedded into Milvus) MUST equal the Chinese `summary_zh` content
(per Paper Review §3.1 P3: paragraph 200-400 chars).

The admin API at
`apps/admin-console/backend/api/domains.py:753` currently aliases
`summary_text` to `row.get("abstract_clean")` — the **English original
abstract** — silently violating the contract. Audit identified this
as `paper-summary-text-contract-drift-001`.

Two existing tests
(`apps/admin-console/tests/test_data_api_paper_v011.py:172, :182`)
encode the wrong behavior, asserting `summary_text == abstract_clean`.

## What Changes

- Change `domains.py:753` from `"summary_text": row.get("abstract_clean")`
  to `"summary_text": row.get("summary_zh")`.
- Update the 2 affected tests to assert the corrected behavior:
  `summary_text` returns `summary_zh` when present; returns `None`
  when `summary_zh` is null.

## Out of scope

- No Postgres schema change (`paper.summary_text` column NOT added;
  `summary_text` is an in-memory release-time field per Paper Review
  P2/P3).
- No PRD or Shared-Spec doc edit (those already define the contract
  correctly; this change just makes the impl match).
- No Milvus rebackfill (Milvus paper_chunks already embeds the
  in-memory `PaperRecord.summary_text` value; the admin API alias is
  the only divergent surface).

## Risk

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Frontend code consumes `summary_text` as English | low | medium | grep frontend src for `summary_text` usage; if any UI depends on English, file follow-up |
| Other API endpoints have similar alias drift | low | low | grep for `abstract_clean` aliasing; only `domains.py:753` confirmed by audit |
| Tests breakage outside the 2 known cases | low | low | full pytest run after fix |

## Weight rationale

**OpenSpec Lite** (CLAUDE.md §14.2). Behavior-affecting (API output
changes) so OpenSpec required, but Tiny per §8 — single-line edit
plus 2 test updates. No specs/ delta needed: the spec contract
already exists in Shared-Spec §4.2.1; this change brings impl into
compliance.
