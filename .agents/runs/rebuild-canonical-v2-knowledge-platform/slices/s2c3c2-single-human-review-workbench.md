# Slice Contract: s2c3c2-single-human-review-workbench

## Status

Candidate at `2026-07-24`. The slice entered Ready and In Progress on `2026-07-24` and replaces the
rejected two-human/per-family-50 S2C3C2 policy by explicit owner decision. Implementation-only and
browser evidence is complete; no real attributable submitted decision round has run, so Task 2.8
remains unchecked.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `2.8`
- Parent slice: Accepted `s2c3-claim-level-oracle-review`
- Replaces: Rejected/Superseded `s2c3c2-external-human-review`
- Immutable packet: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-packet-v1.json`
- Packet content SHA-256:
  `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`

## Goal

Provide a Candidate-integrated review workbench through which one attributable human can decide the
exact 29 contract candidates, 23 evidence-gap exclusions, and 60 pre-frozen blind calibration probes,
then produce independently verifiable review evidence without writing Canonical PostgreSQL or
opening Milvus.

## Non-goals

- No human decision, label, rationale, identity, judge authorization, or Task 2.8 acceptance is
  invented by an agent, model, fixture, or fake judge.
- No login/identity-provider product, multi-reviewer workflow, separate frontend framework, or
  production deployment is introduced.
- No Task 8.1, 8.8, 9.8, 12.2-12.6, release promotion, Cutover, archive, Commit, Push, or PR.
- No mutation or reinterpretation of the Accepted v1 packet, builder, test, corpus, manifest,
  snapshots, or historical review evidence.

## Allowed scope

- Versioned review policy, observation bank, deterministic 29+23+60 workload, export schema,
  validator, reviewed-v2 application tool, focused tests, and evidence under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/`.
- A separate Candidate review-enabled FastAPI factory/router, one deep `ReviewWorkspace` module,
  dedicated SQLite ledger, explicit launcher, and static `/review` HTML/CSS/JavaScript under
  `apps/admin-console/`, with focused interface/HTTP/UI tests.
- This slice contract, the owning claim-level OpenSpec rule, acceptance/verification evidence, and
  the approved workbench design/change-log entries needed to keep the policy traceable.
- One future real human round and explicitly authorized real evidence-bounded judge run after the
  implementation reaches Candidate.

## Forbidden changes

- Do not connect to, start, enter, migrate, repair, replay, or write original `pgtest`; do not mount
  original Postgres volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- Do not open or write `apps/miroflow-agent/milvus.db`; do not read or write an active release.
- Do not use Canonical PostgreSQL or Milvus for workbench state; only explicitly configured
  dedicated SQLite review state is allowed.
- Do not expose judge results, response hashes, agreement, or a derivable model signal before all 60
  human labels are final and sealed.
- Do not make task selection depend on judge output, add labels to chase a passing score, or let a
  failed round be rewritten.
- Do not check Task 2.8 or any downstream task/acceptance item from fake-judge or implementation-only
  evidence.
- Do not touch S12A implementation/evidence or unrelated dirty worktree content.

## Expected unchanged behavior

- The Accepted packet raw SHA-256 remains
  `222777219026218d9a6308c62c0238613761ef83ae90497c3a0cfa785bce7d2e`; its content SHA-256 remains
  `d4aa2a74cd09956f01fcff9b774a55fc0627a412eb604c0de0be46ebd5bf2ffb`.
- Existing Candidate consumer factories and route contracts remain unchanged unless the caller
  explicitly selects the new review-enabled factory.
- Existing S2C hard-case, snapshot, evidence-bounded judge, and no-model-memory invariants remain
  normative.
- Original PostgreSQL stays paused, original Milvus stays unopened, and active release pointers do
  not change.

## Human workload and gates

- One reviewer supplies all 112 final human actions: 29 contract decisions, 23 exclusion decisions,
  and 60 calibration labels.
- Calibration quotas are exactly 20 claim/evidence, 10 identity/entity, 10
  context/relationship, 10 safety/Web, and 10 insufficiency/assessment.
- A passing round has exactly 60 valid pairs, agreement `>= 0.80`, at least 10 human `supported`
  labels, at least 10 human `unsupported` labels, at least five mechanically marked critical probes
  labelled human-`unsupported`, and zero critical false accepts.
- A non-accepting `review_evidence` audit export may preserve current submitted feedback at any
  review state and must account for missing tasks. Before sealing it exposes no judge-result or
  derivable model-result field. Only an independently validated, gate-passing `acceptance_candidate`
  export may feed reviewed-v2 application.

## Required checks

- Deterministic workload build/rebuild, canonical raw/content hashes, exact 29+23+60 accounting,
  five-stratum quotas, distinct request hashes, and tamper/fail-closed tests.
- Real SQLite interface tests for registration/resume, drafts, append-only decisions, supersession,
  optimistic revision, idempotency, restart, blindness, gate calculation, and both export modes.
- Fake-judge E2E for supported/unsupported, malformed, timeout, cross-wire, low agreement, critical
  false accept, and passing outcomes; fake evidence is implementation-only.
- FastAPI contract tests for strict schemas, same-origin mutations, secure session attribution,
  stable errors, no hidden model fields, download identity, and review-route isolation.
- Browser walkthrough for registration/resume, all task types, autosave/reload/stale-tab behavior,
  blind calibration and post-seal reveal, blocked/passing summaries, export, keyboard focus, and
  desktop/narrow layouts with no console/network failures.
- Independent export validation/application tests that reject `review_evidence`, missing/cross-wired
  decisions, hash drift, failed gates, or changed v1 inputs before output creation.
- Ruff, Pyright, relevant existing Candidate/S2C regressions, strict OpenSpec validation,
  `git diff --check`, protected-source hash/scope checks, and independent review with zero open
  Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md` with exact commands, results,
  policy/workload/source/export hashes, fake-versus-real judge identity, browser evidence, review
  findings, and unchanged original-source/active-release state.
- This slice status: `In Progress` -> `Candidate` only after the implementation checks pass;
  `Candidate` -> `Accepted` only after the real attributable round and owner acceptance pass.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md` with implementation and,
  separately, real-human acceptance evidence. Task/acceptance checkboxes stay open until that latter
  gate.

## Stop conditions

- Any packet/source/workload identity mismatch, unknown task/requirement/snapshot, insufficient
  fixture-only observation bank, or non-deterministic workload.
- Any request for a model/agent to act as the human reviewer, use model output in task selection, or
  reveal judge output before sealing.
- Any dependency on Canonical PostgreSQL, Milvus, active release mutation, original source access,
  a generic database URL, or a production-like target.
- Any need to change public Candidate behavior outside the explicit review-enabled factory or to
  broaden OpenSpec beyond Task 2.8.
- Any attempt to apply a `review_evidence` export or an unvalidated/failed
  `acceptance_candidate` export.

## Done means

The workbench, workload, fake-judge E2E, export validator, and browser flow are Candidate. No human
decision is invented, and Task 2.8 remains open until one real attributable round passes.

## Rollback note

Before human use, remove or disable the unaccepted workbench and v2 workload while leaving every v1
artifact byte-identical. After human use, code may be disabled but the dedicated SQLite ledger and
content-addressed exports remain attributable evidence and are retained or archived; no Canonical
database/index rollback is required because this slice never writes them.
