---
title: "M1: Identity Gate v2 — CJK+pinyin variants + ORCID shortcut"
type: feat
status: active
date: 2026-04-23
milestone: M1 (deferred post-eng-review until post-M2; executing now as last 003 brick)
origin:
  - docs/plans/2026-04-20-003-agentic-rag-execution-plan.md  # §M1
depends_on:
  - 80acd19  # M2.4 Phase A — professor_orcid table + writer
---

# M1 — Identity Gate v2

## Overview

Replace the single-`name` prompt in `paper_identity_gate` with a multi-variant representation (CJK + Latin + pinyin + initials) so the LLM can correctly match same-person papers across name renderings. Plus ORCID shortcut: when a candidate paper's authors include the prof's ORCID, auto-accept without burning an LLM call.

001 §4.2 identified ~47% prof-paper reject rate driven by CJK↔Latin mismatch. This milestone fixes the non-homepage path (OpenAlex/arxiv author discovery). Homepage-authoritative path (M2.1→M2.4) bypasses the gate entirely.

Shipping without live eval set (003 §M1.4 deferred) because:
1. The eval set needs hand-labeled ground truth — infeasible in a single session
2. The reinforcing existing regression test + 5 new unit test scenarios prove the behavior
3. Operator can measure delta after dogfood by comparing before/after accept rates on real batches

## Requirements Trace

- **R1** (003 §M1.1): `NameVariants` frozen dataclass with `zh`, `en`, `pinyin`, `initials`, `all_lower`.
- **R2** (003 §M1.1): `resolve_name_variants(canonical_name, canonical_name_zh, canonical_name_en)` builds variants via pypinyin (CJK → pinyin) + initials heuristic (en name → "J. Doe").
- **R3** (003 §M1.2): `paper_identity_gate` prompt renders all variants; rule 7 added: "authors containing any variant = name match".
- **R4** (003 §M1.3): ORCID shortcut — if a candidate paper's authors include the prof's ORCID, accepted=True confidence=1.0 without LLM call.
- **R5** (derived): pypinyin added to `apps/miroflow-agent/pyproject.toml`.
- **R6** (derived): `ProfessorContext` gains `name_variants` field (additive — default None, backward compat for existing callers).
- **R7** (derived): `_PaperIdentityCandidate` gains `authors_orcid` list field (empty default) for ORCID check.

## Scope Boundaries

**In scope:**
- `apps/miroflow-agent/pyproject.toml` — add `pypinyin`
- `apps/miroflow-agent/src/data_agents/professor/name_variants.py` — new module
- `apps/miroflow-agent/src/data_agents/professor/identity_verifier.py` — add `name_variants: NameVariants | None = None` to `ProfessorContext`
- `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py` — prompt render + ORCID shortcut
- Tests

**Out of scope:**
- M1.4 eval set — needs hand-labeled data
- Populating `professor_orcid` table — separate backfill (OpenAlex author_id_picker already fetches ORCID; threading it to a writer is a different milestone)
- Mass re-run of identity gate on existing papers — operator action after M1 ships

## Key Technical Decisions

- **CJK→pinyin via pypinyin** (Layer 1 — standard lib, added as dep).
- **Initials heuristic**: for "Jianquan Yao" produce ["J. Yao", "J.Q. Yao"]; surname is the last Latin token.
- **Case-insensitive token matching**: all variants lowered for downstream comparison.
- **ORCID shortcut short-circuits LLM**: detected at the candidate-filter step before batching — candidates with author-ORCID match get a pre-populated `PaperIdentityDecision(accepted=True, confidence=1.0, reasoning="ORCID match")` and are excluded from the LLM batch.
- **Backward compat**: `ProfessorContext.name_variants` defaults None; callers that don't set it get prior-session behavior. New callers (any future orchestrator) pass the resolved variants.
- **Shortcut is opt-in via ORCID field on candidate**: if `_PaperIdentityCandidate.authors_orcid` list is empty, no shortcut. Callers (OpenAlex author discovery) pass ORCID strings when available.

## Implementation Units

- [ ] **Unit 1: `name_variants.py` + pypinyin dep**

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/professor/name_variants.py`
- Modify: `apps/miroflow-agent/pyproject.toml` (add `pypinyin`)
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_name_variants.py`

**Approach:**
- `@dataclass(frozen=True, slots=True) class NameVariants`: zh: str | None, en: str | None, pinyin: str | None, initials: tuple[str, ...], all_lower: tuple[str, ...]
- `resolve_name_variants(canonical_name, canonical_name_zh, canonical_name_en) -> NameVariants`:
  - zh = canonical_name_zh if provided else (canonical_name if contains CJK chars else None)
  - en = canonical_name_en if provided else (canonical_name if Latin-only else None)
  - pinyin = zh → pypinyin.lazy_pinyin(zh, style=Style.NORMAL) joined by space (lowercased)
  - initials from en: "Jianquan Yao" → ["J. Yao", "J.Q. Yao"] — first initial + surname, all initials + surname
  - all_lower = unique tuple of all variant forms lowercased
  - Handle empty/None inputs gracefully — return NameVariants with Nones / empty tuples

**Test scenarios (8):**
- resolve_name_variants("Jianquan Yao", "姚建铨", None) → zh=姚建铨, pinyin contains "yao jian quan", initials=("J. Yao", "J.Q. Yao")
- resolve_name_variants(None, "陈伟津", None) → zh=陈伟津, pinyin with "wei jin chen" or "chen wei jin" order (pin both possibilities)
- resolve_name_variants("Wenbo Ding", None, "Wenbo Ding") → en="Wenbo Ding", initials=("W. Ding", "W. Ding")  (duplicates collapsed)
- resolve_name_variants(None, None, None) → all None/empty
- resolve_name_variants("姚建铨", None, None) — inferred zh from canonical_name → populated
- resolve_name_variants("J Smith", None, None) → single initial + surname ("J. Smith")
- Compound surname 欧阳 → "ou yang xxx" pinyin (verify pypinyin default works)
- `all_lower` tuple includes zh, en, pinyin, all initials — all lowercased, no duplicates

---

- [ ] **Unit 2: `ProfessorContext` gains `name_variants` field**

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/professor/identity_verifier.py`
- Test: existing `test_identity_verifier.py` should stay green (backward compat); add 1-2 new tests for the new field.

**Approach:**
- Add `name_variants: NameVariants | None = None` to `ProfessorContext` dataclass (after existing fields).
- Existing callers (no kwarg) get None → prior behavior.
- Import NameVariants from `.name_variants`.

**Test scenarios (2):**
- `ProfessorContext(name="X", institution="Y")` — old shape still works, `name_variants is None`
- `ProfessorContext(name="X", institution="Y", name_variants=NameVariants(...))` — new field populated

---

- [ ] **Unit 3: `paper_identity_gate` prompt + ORCID shortcut**

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_paper_identity_gate.py` (existing? extend; if missing, new)

**Approach:**
- Add `authors_orcid: list[str] = field(default_factory=list)` to `_PaperIdentityCandidate`.
- New function `_extract_orcid_shortcuts(professor_context, candidates) -> tuple[list[PaperIdentityDecision], list[_PaperIdentityCandidate]]`:
  - If context has ORCID (new field) AND candidate.authors_orcid contains it → pre-decide accept.
  - Returns (shortcut_decisions, remaining_candidates).
- `batch_verify_paper_identity` applies shortcut first, batches only remaining, merges results preserving input order.
- `_build_prompt` renders all name variants when present — if `context.name_variants` is None, falls back to prior (name-only) behavior.
- Add optional `orcid: str | None = None` to `ProfessorContext` (backward compat).

**Test scenarios (5):**
- Shortcut: ORCID set on context, 2 candidates — one with matching ORCID in authors_orcid, one without. LLM called only for the one without; shortcut candidate accepted.
- Shortcut preserves input order: candidate[0] shortcut, candidate[1] LLM — returned list matches input indices.
- No ORCID on context → no shortcut; LLM called for all.
- Prompt with name_variants renders all 4 forms (zh, en, pinyin, initials) + Rule 7 about variants matching.
- Prompt without name_variants falls back to prior name-only text (backward compat).

## System-Wide Impact

- **Interaction graph:** name_variants.py new; identity_verifier.py + paper_identity_gate.py modified (additive). Existing callers unchanged.
- **Error propagation:** pypinyin errors caught and treated as "no pinyin available" (degrades to en-only or zh-only). No raises to caller.
- **Unchanged invariants:** `paper_identity_gate.batch_verify_paper_identity` signature unchanged. `ProfessorContext` field additions are additive with defaults.

## Risks

| Risk | Mitigation |
|------|------------|
| pypinyin produces unexpected output for uncommon CJK chars | Always use Style.NORMAL with default heteronym handling; unit tests cover common and compound surnames |
| Initials heuristic wrong for compound surnames in Latin ("Van Der Berg") | Test case covers; heuristic: last 1 token is surname, rest are given names. For "Van Der Berg" produces "V.D. Berg" — acceptable for LLM pattern matching |
| ORCID shortcut accepts false positive when OpenAlex has wrong ORCID attributed | Fallback: if ORCID doesn't match, LLM still evaluates. Worst case same as pre-M1. |
| Backward compat break for existing ProfessorContext constructors | All new fields have defaults; tested explicitly |
| pypinyin adds startup latency | Lazy import in name_variants.py so identity_verifier import stays fast |

## Sources & References

- Origin: 003 §M1
- Related: paper/title_resolver.py has `_SCHOLARLY_DOMAINS` style; similar token-set normalization
- pypinyin docs: https://pypinyin.readthedocs.io/
