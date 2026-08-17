# Canonical V2 Real-Data Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a small Canonical V2 preview built from five exact historical rows, with four browsable domains, two grounded relationships, clickable matching questions, and a real bounded Web Search lane.

**Architecture:** A run-local preview pipeline verifies and reads only the Accepted S2B SQLite restore, maps the selected rows through the existing S6/S7 typed projection/release seams, composes the existing S11 candidate app, and supplies a live Serper-backed Web lane. Static chat UI derives its demo questions from the current candidate APIs and renders current-Web evidence separately. The preview never writes an original source, production-like database/index, or active pointer and does not close Task 12.1.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite read-only URI, Canonical V2 S6/S7/S8/S9/S11 modules, FastAPI/Uvicorn, Serper `WebSearchProvider`, vanilla HTML/JavaScript, pytest, Ruff, Pyright, agent-browser.

---

## File ownership / DAG

```text
P1 manifest + exact extractor ─┐
                              ├─> P3 typed preview graph + Web Search + server
P2 generic UI questions ──────┘
                                      └─> P4 receipt + browser/API verification
```

- P1 writer owns only `preview-p1/preview-selection-manifest-v1.json`,
  `preview-p1/extract_preview_selection.py`, and its adjacent test.
- P2 writer owns only `apps/admin-console/backend/static/chat.html` and
  `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`.
- P3 writer owns only `preview-p1/build_real_data_preview.py` and its adjacent test.
- The root agent owns contracts/plans/receipts, process switching, and final review.

### Task 1: Freeze and extract the exact real-data selection

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/preview-selection-manifest-v1.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/extract_preview_selection.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/test_extract_preview_selection.py`

- [ ] Write RED tests for the exact five IDs, source size/SHA, raw payload hashes, row-set hash,
  object kinds, embedded identities, Company-Patent endpoints, Professor-Paper endpoints, and the
  fixed public-field allowlist.
- [ ] Run the exact test file and record failures for the missing extractor/manifest.
- [ ] Implement `load_selection_manifest(path)` and
  `extract_preview_selection(evidence_root, manifest_path)`: validate the Accepted S2B gate; derive
  the restore path; use `O_RDONLY|O_CLOEXEC|O_NOFOLLOW`; verify size/SHA before SQLite; connect with
  `mode=ro&immutable=1`; set `PRAGMA query_only=ON`; issue one parameterized exact-ID query per row;
  reject missing/extra/changed rows; return only allowlisted projectable payloads.
- [ ] Re-hash and re-stat after extraction, reject SQLite sidecars, and prove source bytes unchanged.
- [ ] Run:

```bash
cd .agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1
../../../../.venv/bin/pytest -q test_extract_preview_selection.py
```

Expected: all tests pass; exactly five records; no source sidecars or writes.

### Task 2: Remove fixture questions and render candidate-derived questions/Web evidence

**Files:**
- Modify: `apps/admin-console/backend/static/chat.html`
- Create: `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py`

- [ ] Write RED static/browser-contract tests proving `Robotics Co`, `陈艾达`, and
  `Evidence-bound robotics` are absent; demo buttons are built only after candidate domain and
  relationship API responses; public text uses `textContent`; current-Web evidence renders only
  safe `https://` locators.
- [ ] Implement `loadDemoQuestions()` using the existing domain list and related APIs. Generate:
  Company introduction, Company→Patent, Professor introduction, Professor→Paper, and Paper detail
  questions only when current candidate objects/relationships exist. Never fall back to IDs.
- [ ] Render `data.evidence` items with `source_nature === "current_web"` in a separate “Web Search”
  section, showing safe title/snippet/URL and never hashes or internal IDs.
- [ ] Run:

```bash
cd apps/admin-console
../../.venv/bin/pytest -q tests/test_canonical_v2_real_preview_ui.py
node -e 'const fs=require("fs");const h=fs.readFileSync("backend/static/chat.html","utf8");for(const m of h.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new Function(m[1]);'
```

Expected: tests and inline JavaScript parse pass.

### Task 3: Build the typed preview graph and live Web Search runtime

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/build_real_data_preview.py`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/test_build_real_data_preview.py`

- [ ] Write RED tests for one real object per public domain, complete field assertion/decision
  lineage, two exact relationship authorities, preview release/index binding, zero external active
  effect, and a Web adapter that converts a recorded Serper payload into bounded content-addressed
  `EvidenceItem` snapshots.
- [ ] Map allowlisted source fields into `SourceAssertion`, `CanonicalDecision`,
  `CurrentFieldSelection`, inclusion decisions, and `DomainProjectionRequest`; call
  `create_ephemeral_domain_projection_builder().project()` rather than directly constructing final
  projections. Missing fields remain limitations; email/office/local paths are excluded.
- [ ] Build `patent_has_applicant` from the Patent row's exact Company ID/name and
  `professor_attributed_to_paper` from the explicit link row; call the existing relationship
  projection seam and retain source row hashes as artifact evidence.
- [ ] Compose empty replayable internal-reference populations, candidate projections, pure lookup/
  index projection, ephemeral `KnowledgeBuild`, `IsolatedReleaseBundle`, and ephemeral
  `ReleasePublication.verify/promote`. Promotion is only an in-memory preview state.
- [ ] Implement a server-owned recorded planner for the five generated questions. Every information
  plan includes local exact/relationship plus `web`, `web_required=True`, and a positive universal
  `WebSearchPolicy`.
- [ ] Implement `SerperPreviewWebSearch`: call `WebSearchProvider.search(request.query)` with an
  8-second timeout and maximum three organic results; validate HTTPS locators; snapshot canonical
  title/link/snippet JSON; return `RetrievalLaneResult`. On provider error return an empty result so
  existing V2 degradation records the unavailable Web lane without dropping local evidence.
- [ ] Build grounded answer proposals from retained local/Web `EvidenceItem` bindings; no source row
  ID, SHA, raw enum, or unverified Web snippet becomes a confirmed claim.
- [ ] Compose `CanonicalV2ConsumerRuntime`, call `create_canonical_v2_candidate_app(runtime=...)`,
  and expose CLI arguments `--evidence-root --manifest --release-id --host --port --receipt`.
- [ ] Run the exact test file; then smoke start on port 18189 and assert the four real names,
  both relationships, `exact|relationship + web` traces, safe Web evidence, and no fixture names.

### Task 4: Verify, record, and switch the preview

**Files:**
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/preview-build-receipt.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/preview-p1/demo-questions.json`
- Create: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/preview-p1-real-data-candidate.md`

- [ ] Run focused pytest, Ruff check/format, `py_compile`, changed-scope Pyright, strict OpenSpec,
  inline JavaScript parse, and `git diff --check`.
- [ ] API-replay all generated questions. Assert each information turn contains a `web` retrieval
  trace; local and Web evidence remain distinguishable; Web failure returns local evidence plus a
  limitation.
- [ ] Browser-check `/browse` and `/chat` on desktop/mobile, console-clean. Capture screenshots.
- [ ] Record exact source before/after hash, selected row hashes, projection/relationship/release
  hashes, API results, Web provider status (never the key), and screenshots in the receipt.
- [ ] Obtain independent spec and code-quality review with zero Critical/Important.
- [ ] Stop the fixture preview only after 18189 passes; start the real-data preview on 18188 and
  recheck loopback/LAN/Tailscale. Do not Commit, Push, PR, promote a real pointer, or check Task 12.1.

## Rollback

Stop the real-data preview process and restore the prior disposable preview only if needed for
diagnosis. Remove only preview-owned `/var/tmp` targets and generated receipt bytes. The Accepted
restore, original sources, active pointers, OpenSpec task ledger, and remote Git state remain
unchanged.
