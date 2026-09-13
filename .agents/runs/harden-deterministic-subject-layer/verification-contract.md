# Verification Contract: harden-deterministic-subject-layer

Created 2026-08-18 before production-code edits.

## Mode

- Deterministic detectors/sanitize changes: unit TDD (RED first) with the
  verbatim G1/G3/G5/P3 strings as fixtures.
- Subject-layer changes are RAG/chat-level: GREEN additionally requires the
  seven-session replay against the traced serve, with the trace journal as
  attribution evidence (anchor names, answer subjects, lanes).

## RED definitions

### RED-1 (3.4): headline anchor survives sanitize today

- Fixture: web-handle anchor display_name = 「河套深圳园区打造深港科技创新
  聚集地 - 香港中联办」 on a soft-anchored turn → current sanitize keeps it
  (web handles never dropped) → RED asserts it does NOT survive.
- Negative fixtures that must survive: 「深圳市优必选科技股份有限公司」,
  「国际先进技术应用推进中心（深圳）」.

### RED-2 (3.3): expansion turn does not bind session subject

- G5-form session (anchor 优必选) → expansion turn currently free-retrieves
  (answer subject 微众银行 in V2 trace) → RED asserts the expansion turn's
  planning inputs carry the session subject.

### RED-3 (3.1): bare-name opening clarifies

- P3 verbatim: bare institution name opening then follow-up → RED asserts no
  "指谁" clarification on either turn.

### RED-4 (3.2): person referent over org session binds article title

- G3 verbatim 「他有哪些论文」 → RED asserts person-scoped answer or typed
  clarification; article title never ships as subject.

### Replay gate (per slice and final)

- Seven-session replay on the traced serve; journal attribution: G1 turn-2
  answer subject = 国先中心 (not 河套 headline), G5 answer set = subject
  peers; stable PASS lines (G2/G4/G6) unchanged; no new degradation tokens.

## Residual slice — 3.2.2 (2026-09-13, deployment line)

Reopened because 3.2.1's shipped behavior only covers the **no-anchor**
branch: `_referent_clarification_needed` fires only when
`active_anchor is None`. Under the current pack, G3 T1 anchors a **canonical
company** handle (深圳国际先进技术应用推进中心), not a headline-shaped web
handle, so the 3.4 guard does not strip it; T2 「他有哪些论文」 then has a
present-but-mismatched anchor and free-retrieved 128 junk papers
(query_type=canonical_v2:A:answer).

The guard that handled this case (`513858e0`, change
`fix-pronoun-anchor-type-guard`) exists only on branch
`data/p4-serving-pack-rebuild` and was never merged into this line. The
contextual interpreter (ON on 18188) has the complementary defect: check ③
documented "personal referent over org-anchored session" but implemented
`referent_domain_hint == "professor"`, so a person pronoun resolving to an
org anchor passes validation and skips the deterministic gate.

### RED (unit, deployment line)

- `tests/test_canonical_v2_pronoun_anchor_type_guard.py` (new): person
  pronoun over company/paper/patent anchor must clarify; professor anchor,
  org referent, neuter referent, explicit named subject, and person-in-
  history must keep binding. Pre-fix: 4 failing (3 clarify + missing
  `has_personal_pronoun`).
- `tests/test_query_interpreter.py`: person pronoun over company anchor with
  `referent_domain_hint="company"` must be rejected; company referent over
  company anchor kept; company referent over professor anchor rejected.
  Pre-fix: 1 failing (the mismatch rejection).
- Contract change: matrix row `("他有哪些代表性研究成果", True, True, False)`
  in `test_canonical_v2_chat_http_adapter.py` moves to expected `True` — an
  untyped anchor no longer satisfies a personal pronoun (consistent with
  `_planning_displayed_ids`, which refuses person→untyped-anchor binding).

### GREEN definitions

- Unit: focused suites green (pronoun guard + interpreter + referent history
  + http adapter matrix + subject layer + G-clarification).
- Endpoint: replay `--only G3_person_pronoun` on 18188 →
  T2 `query_type=canonical_v2:G:clarification_only`, no junk paper answer;
  then the full seven-session replay re-run for the gate.

### Fix shape

- `has_personal_pronoun` (followup_referents) + guard block in
  `_referent_clarification_needed` (clarify over any non-professor anchor,
  unless explicit named subject or a person entry in the referent history) —
  direct port of `513858e0`.
- Interpreter check ③: symmetric typed-referent × anchor-domain mismatch
  rejection (`domain is not None and domain != referent_domain_hint`),
  matching the comment and spec intent.
