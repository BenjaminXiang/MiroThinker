# Canonical V2 real-data preview verification

## Status

Operational preview on `0.0.0.0:18188`. This closes the requested display task only; it does not mark Task 12.1 or the full historical conversion Accepted.

## Display scope

- One manifest-selected Company: 深圳森合创新科技有限公司.
- One linked Patent: 底刀调节结构及割草机器人.
- One Professor: 丁文伯.
- One linked Paper: *Keystroke dynamics enabled authentication and identification using triboelectric nanogenerator array*.
- Two verified relationships: Company→Patent and Professor→Paper.
- Dynamic questions are generated from the live candidate records and verified relationship endpoints.
- Every curated information query attempts current Web Search. HTTPS evidence is shown separately and is not written into local facts.

## Required checks

- `pytest -q test_extract_preview_selection.py test_build_real_data_preview.py` — 24 passed.
- `pytest -q tests/test_canonical_v2_real_preview_ui.py tests/test_canonical_v2_consumer_migration.py::test_s9j_static_chat_uses_typed_public_copy` — 10 passed.
- Ruff check and format check for the P1 Python files — passed.
- Ruff check for the preview UI test — passed.
- `git diff --check` for the preview UI files — passed.
- LAN, Tailscale, and loopback health, browse, and chat endpoints — HTTP 200.
- Live LAN chat probe — exact + Web lanes, 3 HTTPS current-Web evidence records.
- Browser QA — four domains, both relationships, dynamic questions, two answer paths, desktop and 390×844 mobile passed; no console or page errors.
- Public display scan — no visible raw source IDs, derived canonical/evidence IDs, 64-character hashes, `ready`, or `preview_selection_only` in list, detail, relation, or chat copy.
- Independent integrated review — Critical 0, Important 0.

## Source preservation

The selected SQLite restore remained 20,267,008 bytes, mode `0440`, SHA-256 `7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce`. No WAL, SHM, or journal sidecar exists after extraction and browser verification.

## Browser evidence

Screenshots are under `browser-evidence/screenshots/`. `browse-company-detail-sanitized-18188.png` is the post-fix 18188 evidence. `issue-detail-link-inert.png` is a superseded automation false positive: the ref was below the agent-browser viewport; scroll-into-view confirmed the application link works.

## Non-blocking observations

- An unmatched arbitrary free-form question currently falls back to the selected Company answer. The five curated demo questions are unaffected.
- The answer uses “Current Web Search evidence” while the section heading uses “current web evidence”.

## Boundaries

- This is a run-local preview adapter over a frozen five-row manifest, not the full Task 12.1 historical conversion.
- No Commit, Push, PR, production release-pointer Cutover, original-source mutation, or accepted-backup mutation was performed.
