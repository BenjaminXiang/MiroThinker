# Canonical V2 Human Review Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Candidate-integrated `/review` workbench that lets one attributable human review
29 contracts, decide 23 evidence-gap exclusions, blindly label 60 evidence-bounded calibration
probes, and export independently verifiable review evidence without touching Canonical PostgreSQL or
Milvus.

**Architecture:** A separate review-enabled Candidate shell injects one deep `ReviewWorkspace` module
behind a thin FastAPI router. The module owns immutable packet/workload verification, SQLite event
persistence, judge-result blindness, gate calculation, and canonical export. Static HTML/CSS/JS is a
same-origin renderer; a run-local validator independently replays export checks without trusting the
UI or SQLite state.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, stdlib `sqlite3`, existing OpenAI-compatible client,
static HTML/CSS/JavaScript, pytest/TestClient, agent-browser, Ruff, Pyright, OpenSpec.

**Repository constraint:** Do not create a commit. Existing S12A changes are user-owned and must be
preserved. Task 2.8 remains unchecked until a real human round passes; Tasks 8.1, 8.8, and 9.8 remain
untouched.

---

## File structure

### Change and run artifacts

- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/claim-level-acceptance/spec.md`
  — version the single-human/five-stratum calibration policy.
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md` — record the new
  gate without checking Task 2.8.
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md` — bind the
  v2 policy/workload/export identities and original-source no-write invariant.
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md` — record the owner
  policy replacement and implementation Candidate evidence.
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-external-human-review.md`
  — mark the old two-human Ready slice Rejected by owner policy.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-single-human-review-workbench.md`
  — exact Ready slice contract.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-policy-v2.json`
  — canonical policy and strata.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-observation-bank-v2.jsonl`
  — 60 frozen judge requests sourced from structured Canonical V2 fixture objects.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-observation-bank-v2-provenance.json`
  — independently frozen 60-row source/locator/projection audit anchor; normal workload writes only
  verify it and never regenerate it.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/build_review_workload_v2.py`
  — deterministic 29+23+60 workload builder.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_review_workload_v2.py`
  — workload RED/GREEN and tamper tests.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-workload-v2.json`
  — generated content-addressed workload.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/validate_review_export_v2.py`
  — independent export validator and future application input.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_validate_review_export_v2.py`
  — validation and fail-closed tests.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/apply_review_export_v2.py`
  — future application of a valid real export into new reviewed-v2 artifacts.
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_apply_review_export_v2.py`
  — synthetic accepted-export application tests.

### Candidate implementation

- Create: `apps/admin-console/backend/services/canonical_v2_review.py` — deep `ReviewWorkspace`
  module with private SQLite ledger, policy evaluation, and judge seam.
- Create: `apps/admin-console/backend/api/canonical_v2_review.py` — strict HTTP adapter.
- Modify: `apps/admin-console/backend/canonical_v2_deps.py` — app-state workspace getter only.
- Modify: `apps/admin-console/backend/main.py` — separate review-enabled shell/factory while preserving
  the Accepted existing factory signature and route graph.
- Create: `apps/admin-console/backend/static/review.html` — semantic three-pane shell.
- Create: `apps/admin-console/backend/static/review.css` — focused/responsive layout.
- Create: `apps/admin-console/backend/static/review.js` — safe same-origin command/render client.
- Create: `apps/admin-console/scripts/run_canonical_v2_review.py` — explicit `0.0.0.0` launcher.

### Tests

- Create: `apps/admin-console/tests/test_canonical_v2_review_workspace.py`.
- Create: `apps/admin-console/tests/test_canonical_v2_review_http.py`.
- Create: `apps/admin-console/tests/test_canonical_v2_review_ui.py`.
- Modify only if required by the new separate factory:
  `apps/admin-console/tests/test_canonical_v2_consumer_migration.py` — preserve the original factory's
  exact route contract; assert review routes only on the new factory.

---

### Task 1: Replace the old review policy and create a Ready slice

**Files:**
- Modify: `docs/superpowers/specs/2026-07-24-canonical-v2-human-review-workbench-design.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/claim-level-acceptance/spec.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-external-human-review.md`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-single-human-review-workbench.md`

- [ ] **Step 1: Mark the written design approved**

Change the design status to:

```markdown
Status: User-approved on 2026-07-24; implementation in progress
```

- [ ] **Step 2: Version the normative OpenSpec calibration rule**

Replace only the last sentence of the existing LLM-judge requirement with:

```markdown
Scaled LLM judging SHALL require one versioned human-calibration policy. For
`single-human-global-stratified-v2`, one attributable human SHALL label exactly 60 pre-frozen judge
requests across the fixed claim/evidence, identity/entity, context/relationship, safety/Web, and
insufficiency/assessment strata. The sample selection SHALL be independent of judge output; judge
results SHALL remain hidden until all human labels are sealed. Acceptance SHALL require exact-match
agreement of at least `0.80`, both outcome classes, at least five human-unsupported critical probes,
and zero critical false accepts. This policy supersedes the empty v1 packet calibration templates
without mutating the packet bytes.
```

Add this unchecked acceptance item:

```markdown
- [ ] The Task 2.8 review package binds one accountable human, the exact 29 contract decisions, 23
      exclusion decisions, 60 sealed five-stratum calibration labels, authorized judge identity,
      agreement `>= 0.80`, both outcome classes, at least five human-unsupported critical probes,
      zero critical false accepts, and independently reproduced content hashes. Implementation-only
      fake-judge evidence does not satisfy this check.
```

Extend the verification contract with the exact v2 artifact names, forbidden original Postgres/
Milvus targets, and the rule that only a validated `acceptance_candidate` export may feed reviewed-v2
application.

- [ ] **Step 3: Reject the predecessor slice and create the replacement Ready contract**

The replacement contract must state:

```markdown
## Status

Ready at 2026-07-24; replaces the rejected two-human/per-family-50 S2C3C2 policy by explicit owner
decision. Task 2.8 remains unchecked.

## Done means

The workbench, workload, fake-judge E2E, export validator, and browser flow are Candidate. No human
decision is invented, and Task 2.8 remains open until one real attributable round passes.
```

- [ ] **Step 4: Validate the change before production edits**

Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`; Task 2.8, 8.1, 8.8, and 9.8 remain unchecked.

- [ ] **Step 5: Review the documentation diff without committing**

Run:

```bash
git diff -- \
  docs/superpowers/specs/2026-07-24-canonical-v2-human-review-workbench-design.md \
  openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/claim-level-acceptance/spec.md \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-external-human-review.md \
  .agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-single-human-review-workbench.md
```

Expected: only the approved policy replacement and Ready slice appear. Do not commit.

### Task 2: Build the 60-probe calibration workload

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-policy-v2.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-observation-bank-v2.jsonl`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/calibration-observation-bank-v2-provenance.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/build_review_workload_v2.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_review_workload_v2.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-workload-v2.json`

- [ ] **Step 1: Write the RED workload contract**

The focused test must require exact counts, canonical hashes, balanced probes, and no prefilled labels:

```python
def test_review_workload_v2_is_deterministic_complete_and_unlabeled(tmp_path: Path) -> None:
    first = build_workload(packet_path=PACKET, output_path=tmp_path / "first.json")
    second = build_workload(packet_path=PACKET, output_path=tmp_path / "second.json")
    assert (tmp_path / "first.json").read_bytes() == (tmp_path / "second.json").read_bytes()
    assert first["counts"] == {
        "contract_reviews": 29,
        "exclusion_reviews": 23,
        "calibration_probes": 60,
    }
    assert Counter(row["stratum"] for row in first["calibration_probes"]) == {
        "claim_evidence": 20,
        "identity_entity": 10,
        "context_relationship": 10,
        "safety_web": 10,
        "insufficiency_assessment": 10,
    }
    assert len({row["request_sha256"] for row in first["calibration_probes"]}) == 60
    assert all("human_label" not in row and "judge_decision" not in row for row in first["calibration_probes"])
```

Also add tamper, changed-order, missing-source-locator, duplicate-request, and insufficient-critical-
probe cases.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -q \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_review_workload_v2.py \
  -n0
```

Expected: FAIL because policy/builder/output do not exist.

- [ ] **Step 3: Implement the versioned policy and deterministic probe construction**

Use the exact policy payload:

```json
{
  "schema_version": "canonical-v2-human-calibration-policy-v2",
  "policy_id": "single-human-global-stratified-v2",
  "reviewer_count": 1,
  "sample_count": 60,
  "strata": {
    "claim_evidence": 20,
    "identity_entity": 10,
    "context_relationship": 10,
    "safety_web": 10,
    "insufficiency_assessment": 10
  },
  "minimum_agreement": 0.8,
  "minimum_supported_labels": 10,
  "minimum_unsupported_labels": 10,
  "minimum_unsupported_critical_probes": 5,
  "maximum_critical_false_accepts": 0
}
```

Materialize exactly 60 rows from structured objects in these checked-in sources:

```text
apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_grounding_contract.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_implementation_closure.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_atomic_green_contract.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_multiturn_contract.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_answer_successor_handoff.py
apps/miroflow-agent/tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py
```

Do not use YAML, reference prose, or future S8/S9 results as evidence. Each bank row validates against
these strict models; the builder computes both hashes from current source bytes and canonical request
bytes:

```python
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

class CalibrationSourceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    test_name: str
    source_sha256: Sha256

class CalibrationRequestV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["canonical-v2-human-calibration-request-v2"]
    sample_id: str
    source_identity: CalibrationSourceIdentity
    stratum: Literal[
        "claim_evidence",
        "identity_entity",
        "context_relationship",
        "safety_web",
        "insufficiency_assessment",
    ]
    requirement_kind: Literal[
        "claim_entailment",
        "identity_consistency",
        "relationship_or_context",
        "safety_or_web_policy",
        "evidence_sufficiency",
    ]
    critical_probe: bool
    as_of: datetime
    requirement: dict[str, JsonValue]
    candidate_observation: dict[str, JsonValue]
    evidence_snapshots: tuple[dict[str, JsonValue], ...]
    policy_id: Literal["single-human-global-stratified-v2"]
    request_sha256: Sha256
```

The allowed `requirement_kind` values are `claim_entailment`, `identity_consistency`,
`relationship_or_context`, `safety_or_web_policy`, and `evidence_sufficiency`. Each row copies exact
structured fixture values into requirement/observation/snapshots and records the full source-file
hash. Candidate observations are stimuli, not truth; the human label is gold. The judge model must
not author probes.

Canonical hashing helper:

```python
def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Generate and verify the exact workload**

Run:

```bash
cd apps/miroflow-agent
uv run python \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/build_review_workload_v2.py \
  --write
uv run python \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/build_review_workload_v2.py \
  --check
uv run pytest -q \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_review_workload_v2.py \
  -n0
```

Expected: builder check exits `0`; focused tests pass.

- [ ] **Step 5: Run predecessor S2C regression and inspect scope**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -q ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c -n0
git diff --check
```

Expected: Accepted S2C tests remain green; no original packet/corpus/source snapshot bytes changed.

### Task 3: Implement the deep `ReviewWorkspace` with SQLite event history

**Files:**
- Create: `apps/admin-console/backend/services/canonical_v2_review.py`
- Create: `apps/admin-console/tests/test_canonical_v2_review_workspace.py`

- [ ] **Step 1: Write interface-level RED tests**

Use only the external seam:

```python
workspace = create_review_workspace(
    packet_path=packet_path,
    workload_path=workload_path,
    state_dir=tmp_path / "state",
    export_dir=tmp_path / "exports",
    judge=RecordedJudge(decisions=judge_decisions),
    public_origin="http://review.test",
)
opened = workspace.open(
    OpenWorkspace(display_name="Reviewer Li", staff_id="r-1042")
)
assert opened.counts == ReviewCounts(contract_reviews=29, exclusion_reviews=23, calibration_probes=60)
assert opened.task.model_judgment is None
```

Cover:

- packet/workload/policy tamper before the first write;
- ASCII staff-ID normalization and invalid identities;
- register/resume/restart;
- mutable draft excluded from evidence;
- immutable final revision and explicit superseding rationale;
- stale revision and same/different idempotency payloads;
- 29 contract and 23 exclusion decision semantics;
- calibration decisions hidden before sealing;
- no `sqlite3` table or result contains an API key;
- no Canonical PostgreSQL/Milvus import or connection.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_workspace.py
```

Expected: collection/import failure for the absent module.

- [ ] **Step 3: Implement the three-entry interface and strict models**

Public interface:

```python
class ReviewWorkspace:
    def open(self, request: OpenWorkspace) -> WorkspaceView: ...
    def record(self, command: ReviewCommand) -> WorkspaceView: ...
    def export(self, command: ExportReview) -> ExportReceipt: ...
```

Use frozen Pydantic models with `extra="forbid"`. Keep `_SQLiteLedger`, `_load_bound_artifacts`,
`_project_current_state`, `_calibration_summary`, and `_write_canonical_export` private. SQLite uses
foreign keys, WAL, `BEGIN IMMEDIATE`, unique `(round_id, task_id, revision)` and unique idempotency
keys. Draft rows are mutable; decision-event rows are append-only.

- [ ] **Step 4: Implement state transitions and stable errors**

Required codes:

```python
class ReviewErrorCode(StrEnum):
    ARTIFACT_MISMATCH = "artifact_mismatch"
    INVALID_REVIEWER = "invalid_reviewer"
    STALE_REVISION = "stale_revision"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_DECISION = "invalid_decision"
    JUDGE_UNAVAILABLE = "judge_unavailable"
    CALIBRATION_NOT_SEALED = "calibration_not_sealed"
    EXPORT_BLOCKED = "export_blocked"
```

Calibration decisions can be superseded only before `human_labels_sealed`. Contract/exclusion
decisions can be superseded until an acceptance-candidate export locks the round.

- [ ] **Step 5: Run GREEN and restart/tamper matrix**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_workspace.py
```

Expected: all interface tests pass using real temporary SQLite.

### Task 4: Add the real judge adapter, blind sealing, and gates

**Files:**
- Modify: `apps/admin-console/backend/services/canonical_v2_review.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_review_workspace.py`

- [ ] **Step 1: Add RED tests for judge authorization and blindness**

Tests must prove:

```python
for task_id in calibration_task_ids:
    view = workspace.open(OpenWorkspace(session_token=token, task_id=task_id))
    assert view.task.model_judgment is None

sealed = workspace.record(SealCalibration(session_token=token, expected_revision=60))
assert sealed.calibration.agreement == pytest.approx(0.80)
assert sealed.task is None
```

Also assert that timeout, malformed schema, wrong request hash, external-memory use, missing judge
authorization, fewer than 10 labels in either class, fewer than five unsupported critical probes,
agreement `0.79`, or one critical false accept blocks acceptance export.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_workspace.py -k "judge or calibration"
```

Expected: new tests fail on missing authorization/sealing behavior.

- [ ] **Step 3: Implement the injected judge port and adapters**

Port:

```python
class EvidenceBoundedJudge(Protocol):
    model_id: str

    def judge(self, request: dict[str, Any]) -> dict[str, Any]: ...
```

Production adapter accepts an injected OpenAI-compatible client, uses temperature `0`, validates the
recorded decision schema, and records only model/policy/request/response hashes plus decision. The
fake adapter remains test-only. `JudgeAuthorization` binds authorizer, provider profile, model,
policy, workload, round, time, and content hash without a credential.

- [ ] **Step 4: Implement seal-once metrics**

At seal time, compute exact-match agreement, confusion matrix, stratum counts, class counts,
unsupported critical probes, and critical false accepts in one transaction. Reveal results only in
the post-seal `WorkspaceView`. Failed sealed rounds remain immutable and audit-exportable.

- [ ] **Step 5: Run GREEN**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_workspace.py
```

Expected: full workspace suite passes.

### Task 5: Add the Candidate HTTP adapter and separate review-enabled factory

**Files:**
- Create: `apps/admin-console/backend/api/canonical_v2_review.py`
- Modify: `apps/admin-console/backend/canonical_v2_deps.py`
- Modify: `apps/admin-console/backend/main.py`
- Create: `apps/admin-console/tests/test_canonical_v2_review_http.py`

- [ ] **Step 1: Write route/factory/security RED tests**

Require:

```python
review_app = create_canonical_v2_review_app(
    review_workspace=workspace,
    public_origin="http://127.0.0.1:18189",
)
client = TestClient(review_app, base_url="http://review.test")
page = client.get("/review")
assert page.status_code == 200
assert page.headers["content-security-policy"].startswith("default-src 'none'")

session = client.post(
    "/api/review/sessions",
    headers={"Origin": "http://review.test"},
    json={"display_name": "Reviewer Li", "staff_id": "r-1042"},
)
assert session.status_code == 200
assert "HttpOnly" in session.headers["set-cookie"]
assert "SameSite=strict" in session.headers["set-cookie"]
```

Cover absent/wrong workspace `503`, missing/null/wrong Origin `403`, strict response shapes, review
routes before `/api/{path:path}`, no CORS headers, and original `_create_canonical_v2_route_shell()` /
`create_canonical_v2_candidate_app(*, runtime)` route graph unchanged.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_http.py
```

Expected: import/route failures.

- [ ] **Step 3: Implement the thin router and app-state getter**

Routes:

```text
POST /api/review/sessions
GET  /api/review/workspace
PUT  /api/review/drafts/{task_id}
POST /api/review/decisions
POST /api/review/calibration/seal
POST /api/review/exports
GET  /api/review/exports/{export_id}
```

The dependency reads only `request.app.state.canonical_v2_review_workspace`. Do not use legacy
`backend.api.review`, `backend.deps`, `_compose_operations`, PostgreSQL, or `CanonicalV2ConsumerRuntime`.

- [ ] **Step 4: Implement the separate factory without changing Accepted factories**

Internal shell construction accepts `include_review: bool`, while public predecessor functions keep
their signatures and exact routes. Add:

```python
def create_canonical_v2_review_app(
    *, review_workspace: ReviewWorkspace, public_origin: str
) -> FastAPI:
    candidate = _create_route_shell(include_review=True)
    candidate.state.canonical_v2_review_workspace = review_workspace
    return candidate
```

Register the review router before the reject-all API catch-all. Serve `/review` with CSP,
`Cache-Control: no-store`, `Referrer-Policy: no-referrer`, and `X-Content-Type-Options: nosniff`.

- [ ] **Step 5: Run GREEN plus predecessor regressions**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_http.py
uv run pytest -q \
  tests/test_canonical_v2_consumer_migration.py \
  tests/test_canonical_v2_operations_api.py
```

Expected: new routes pass only on the new factory; Accepted Candidate route tests remain green.

### Task 6: Build the three-pane static workbench

**Files:**
- Create: `apps/admin-console/backend/static/review.html`
- Create: `apps/admin-console/backend/static/review.css`
- Create: `apps/admin-console/backend/static/review.js`
- Create: `apps/admin-console/tests/test_canonical_v2_review_ui.py`

- [ ] **Step 1: Write static UI RED tests**

Require semantic regions, external assets, safe DOM, and API ownership:

```python
assert '<main id="review-workbench"' in html
assert '<aside id="review-queue"' in html
assert '<aside id="review-decision"' in html
assert '<link rel="stylesheet" href="/static/review.css">' in html
assert '<script src="/static/review.js" defer></script>' in html
assert "innerHTML" not in javascript
assert "textContent" in javascript
assert 'credentials: "same-origin"' in javascript
```

Run `node --check` from the test and assert no inline script/style, unsafe event handlers, legacy API,
hidden judge fields, Canonical writer strings, or permissive CORS code.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/admin-console
uv run pytest -q tests/test_canonical_v2_review_ui.py
```

Expected: missing static files.

- [ ] **Step 3: Implement the approved A layout**

HTML contains reviewer registration, five phase buttons, queue, human-readable content/evidence,
decision form, autosave live region, summary, and export dialog. CSS uses a desktop
`180px minmax(0, 1fr) 280px` grid and stacks the decision pane below `900px`. Every interactive
element has a label and visible `:focus-visible` state.

- [ ] **Step 4: Implement safe client state and commands**

`review.js` must use:

```javascript
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new ReviewHttpError(response.status, payload);
  return payload;
}

function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
}
```

Use `createElement`, `textContent`, and `replaceChildren` only. Debounced drafts call the draft API;
final decisions carry current revision plus a stable crypto-generated idempotency key. The UI never
derives progress, agreement, or hidden model results locally.

- [ ] **Step 5: Run GREEN and syntax checks**

Run:

```bash
cd apps/admin-console
node --check backend/static/review.js
uv run pytest -q tests/test_canonical_v2_review_ui.py
```

Expected: syntax and UI contract tests pass.

### Task 7: Implement canonical export and independent validation

**Files:**
- Modify: `apps/admin-console/backend/services/canonical_v2_review.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/validate_review_export_v2.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_validate_review_export_v2.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/apply_review_export_v2.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_apply_review_export_v2.py`

- [ ] **Step 1: Write export/validator RED tests**

Test both modes:

```python
audit = workspace.export(ExportReview(session_token=token, mode="review_evidence"))
assert audit.acceptance_eligible is False

with pytest.raises(ReviewWorkspaceError, match="export_blocked"):
    workspace.export(ExportReview(session_token=blocked_token, mode="acceptance_candidate"))

validated = validate_export(
    export_path=accepted.path,
    packet_path=packet_path,
    workload_path=workload_path,
)
assert validated.content_sha256 == accepted.content_sha256
```

Add tampered event, missing revision, changed label, changed judge response, bad policy/model,
incomplete decisions, low agreement, critical false accept, path traversal, and non-accepting package
misuse cases.

- [ ] **Step 2: Run RED**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -q \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_validate_review_export_v2.py \
  -n0
```

Expected: validator missing.

- [ ] **Step 3: Implement atomic canonical export**

The workspace writes sorted compact JSON to a temporary file, flushes/fsyncs, atomically renames,
rereads, and verifies raw/content hashes before recording the export. A `review_evidence` package is
permanently non-accepting. Only `acceptance_candidate` can be consumed by future S2C application.

- [ ] **Step 4: Implement an independent validator**

The validator imports no Admin Console module and trusts only the export, frozen packet, workload,
and policy. It recomputes event-chain hashes, current revisions, exact 29/23/60 accounting,
blind-seal identity, model/policy authorization, class/critical coverage, agreement, and package hash.
It returns a frozen validated result or raises a stable validation error.

- [ ] **Step 5: Implement the future reviewed-v2 application path**

The application tool accepts only a validated `acceptance_candidate` export. It writes a new output
directory and never edits v1 files. Its reviewed manifest records 29 approved contracts, 23 accepted
exclusions, human-review/exclusion hashes, policy/workload/export hashes, and exact predecessor
identities. A synthetic accepted export test proves the tool produces deterministic v2 bytes; a
`review_evidence` export, missing decision, or changed v1 source fails before output creation.

- [ ] **Step 6: Run GREEN and cross-process verification**

Run:

```bash
cd apps/miroflow-agent
uv run pytest -q \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_validate_review_export_v2.py \
  ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/test_apply_review_export_v2.py \
  -n0
```

Expected: all validator tests pass without a database or UI process.

### Task 8: Add an explicit `0.0.0.0` launcher and browser walkthrough

**Files:**
- Create: `apps/admin-console/scripts/run_canonical_v2_review.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_review_http.py`

- [ ] **Step 1: Write launcher RED tests**

Assert the launcher requires explicit packet/workload/source-root/state/export/public-origin
arguments, defaults host to `0.0.0.0`, never accepts Canonical DB/Milvus arguments, and does not load
credentials into the workspace export.

- [ ] **Step 2: Implement the launcher**

CLI shape:

```text
uv run python scripts/run_canonical_v2_review.py \
  --packet ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-packet-v1.json \
  --workload ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/human-review-workload-v2.json \
  --source-root ../.. \
  --state-dir ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/state \
  --export-dir ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c/review/exports \
  --public-origin http://127.0.0.1:18189 \
  --host 0.0.0.0 \
  --port 18189
```

Judge configuration is optional for phases 1–2 and explicit for phase 3. Missing judge configuration
must visibly pause calibration rather than substitute a fake.

- [ ] **Step 3: Run HTTP/UI suites**

Run:

```bash
cd apps/admin-console
uv run pytest -q \
  tests/test_canonical_v2_review_workspace.py \
  tests/test_canonical_v2_review_http.py \
  tests/test_canonical_v2_review_ui.py
```

Expected: all pass.

- [ ] **Step 4: Walk the real page with agent-browser**

Start the launcher on `0.0.0.0:18189`, then verify with agent-browser:

```bash
agent-browser --session canonical-review open http://127.0.0.1:18189/review
agent-browser --session canonical-review snapshot -i
agent-browser --session canonical-review screenshot /tmp/canonical-review-workbench.png
```

Exercise registration, one contract approval, one exclusion decision, one draft/reload, stale-tab
conflict, pre-seal hidden model result, post-seal summary with a fake judge in an isolated test state,
and audit export. Record screenshots and browser/network/console outcomes in verification evidence.

### Task 9: Verify, review, and hand off the implementation Candidate

**Files:**
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s2c3c2-single-human-review-workbench.md`

- [ ] **Step 1: Run focused Python checks**

```bash
cd apps/admin-console
uv run pytest -q \
  tests/test_canonical_v2_review_workspace.py \
  tests/test_canonical_v2_review_http.py \
  tests/test_canonical_v2_review_ui.py
uv run ruff check \
  backend/services/canonical_v2_review.py \
  backend/api/canonical_v2_review.py \
  scripts/run_canonical_v2_review.py \
  tests/test_canonical_v2_review_workspace.py \
  tests/test_canonical_v2_review_http.py \
  tests/test_canonical_v2_review_ui.py
uv run pyright \
  backend/services/canonical_v2_review.py \
  backend/api/canonical_v2_review.py \
  scripts/run_canonical_v2_review.py
```

Expected: all exit `0`.

- [ ] **Step 2: Run S2C and Candidate boundary regressions**

```bash
cd apps/miroflow-agent
uv run pytest -q ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s2c -n0
cd ../admin-console
uv run pytest -q \
  tests/test_canonical_v2_consumer_migration.py \
  tests/test_canonical_v2_operations_api.py \
  tests/test_canonical_v2_real_preview_ui.py
```

Expected: Accepted predecessor suites remain green.

- [ ] **Step 3: Run artifact and repository checks**

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
git status --short
```

Expected: OpenSpec and diff checks exit `0`; status contains only intentional S12A plus review
workbench changes; no original source, production DB, Milvus, secret, cache, or generated vendor file.

- [ ] **Step 4: Obtain independent code and spec review**

Bind the review to exact file hashes. Resolve every Critical and Important finding, rerun affected
checks, and record final finding counts. Minor findings may remain only with explicit rationale.

- [ ] **Step 5: Mark only the implementation slice Candidate**

Record:

```markdown
Status: Candidate

The workbench implementation and fake-judge E2E pass. Task 2.8 remains unchecked because no real
human decision/export package exists. The next action is to launch `/review` and complete the one-
human round; only then may S2C3C3 application and Task 2.8 acceptance proceed.
```

Do not check Task 2.8, 8.1, 8.8, or 9.8. Do not commit.
