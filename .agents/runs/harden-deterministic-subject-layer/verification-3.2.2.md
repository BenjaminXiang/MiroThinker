# Verification — 3.2.2 (G3 pronoun × anchor-type guard, deployment line)

Date: 2026-09-13. Worktree: `.worktrees/canonical-v2-s11-consolidation`
(branch `codex/canonical-v2-s12a-ready`, uncommitted). Serving pack:
`serving-pack-run14-sealed` (release `candidate-v2-20260819-r1`).

## Defect

G3 replay T2 「他有哪些论文」 over a session anchored on the **canonical
company** 深圳国际先进技术应用推进中心 free-retrieved 128 junk papers
(`query_type=canonical_v2:A:answer`, answer opened "你问的这篇论文是《Ultra-high
sensitivity Fabry–Perot…》"). Root causes:

1. `_referent_clarification_needed` (canonical_v2_chat.py) fires only when
   `active_anchor is None`; a present anchor was trusted regardless of type,
   and the type-checked binding (`_planning_displayed_ids`) silently refuses
   the mismatched bind — so the turn fell through to unbound retrieval.
   The guard that handled this (`513858e0`, change
   `fix-pronoun-anchor-type-guard`, Aug 28, G3 replay GREEN on its branch)
   exists only on `data/p4-serving-pack-rebuild` and was never merged here.
2. The contextual interpreter (ON on 18188) check ③ documented "personal
   referent over org-anchored session" but implemented
   `referent_domain_hint == "professor"`, so a person pronoun resolving to
   an org anchor passed validation and also skipped the deterministic gate.

## Fix (port + alignment)

- `followup_referents.has_personal_pronoun` (thin wrapper over the existing
  `_SINGULAR_PERSON_PRONOUN_PATTERN`) + a guard block at the end of
  `_referent_clarification_needed`: any 他/她 over a non-professor anchor
  clarifies, unless the query names an explicit subject or the referent
  history holds a person.
- Interpreter check ③: symmetric typed-referent × anchor-domain mismatch
  rejection (`domain is not None and domain != referent_domain_hint`).
- Contract change: adapter matrix row
  `("他有哪些代表性研究成果", True, True, False)` → `True` — an untyped
  anchor no longer satisfies a personal pronoun, consistent with
  `_planning_displayed_ids` (person→untyped-anchor bind refused).

## Evidence

### Unit (RED → GREEN)

- RED: `test_canonical_v2_pronoun_anchor_type_guard.py` (9 tests) +
  `test_query_interpreter.py` (+3) → **5 failed, 18 passed** before the fix
  (3 clarify assertions, missing `has_personal_pronoun`, interpreter
  mismatch rejection).
- GREEN: guard + interpreter + referent history **42 passed**; six focused
  files incl. adapter matrix / subject layer / G-clarification **188
  passed**; miroflow `tests/canonical_v2 -k referent` **148 passed**.

### Endpoint (18188, restarted with this code; Milvus load ~12 min)

- `replay-g3-fix-20260913/` — G3 only: T1 25.9 s PASS; T2
  `canonical_v2:G:clarification_only` (1.0 s) PASS.
- `replay-full-20260913/` — full gate: **6/7 sessions, 1 failing turn**.
  G1/G2/G3/G4/G5/G6 PASS; G7 #2/3 `required substring missing: 优必选`
  (T2 of G3: 0.7 s clarification; previous gate `replay-b1r4` was 5/7 with
  3 failures — G3 T2 + G7 #2/#3).

### G7 residual baseline (next slice, not this one)

`diagnose_g7_recall.py` over 23 archived 具身智能 turns: 优必选 recall
6/23 (rank ~37/128 when present), commit **0/23** — a recall-generation AND
commit-window defect; owned by retrieval-v2 1b.1 (wide pool / bigram residue
recall) + 1b.3 (commit-axis superset guard).

## Notes

- Oracle assessment for 1b.0c: the clarification reply passes via the
  behavior-based `clarification_only` branch; the literal-substring branch
  (教授/老师/学者/论文作者) stays as the fallback for person-scoped prose.
  The harness was not modified in this slice.
- Pre-existing lint in touched files (not introduced here): 3 × F401 in
  `canonical_v2_query_interpreter.py` / `test_query_interpreter.py`
  (identical at HEAD).
