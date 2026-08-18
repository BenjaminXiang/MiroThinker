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
