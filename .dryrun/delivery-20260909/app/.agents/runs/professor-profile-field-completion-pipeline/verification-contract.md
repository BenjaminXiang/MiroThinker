# Verification Contract — professor-profile-field-completion-pipeline (L4 slice: HIT)

> Per CLAUDE.md §14.7. Claude-owned. This contract covers the **L4 implementation slice** (tasks 2.1–2.2 of the change): fix the HIT(Shenzhen) total-extraction failure. The full change's broader contract will be extended per layer.

## Change & slice
- OpenSpec change: `professor-profile-field-completion-pipeline`.
- Slice: **L4 — HIT(Shenzhen) crawl/extraction fix** (tasks 2.1 diagnosis ✅, 2.2 fix).
- Diagnosis: `.agents/runs/professor-profile-field-completion-pipeline/l4-hitsz-diagnosis-20260616.md`.

## Classification
Behavior-affecting. The slice has a **deterministic surface** (redirect-follow fix; the HIT field-mapper from a fixture DOM; provenance) → unit/contract RED. The **data acquisition** (Playwright render of a live HIT page, or `{k,v,d}` API replication) is **integration/acceptance** — and is **smoke-first**: before building the adapter, confirm a rendered HIT page DOM actually contains the fields.

## L4 approach (locked)
- **L4(a) fetch fix**: the crawler follows the `faculty.hitsz.edu.cn` → `homepage.hit.edu.cn` 301 redirect (today `homepage_http.py` follows redirects **nowhere** → records `http_status=NULL`). May be scoped behind a flag if shared-path risk is high; prefer a correct default with a kill-switch.
- **L4(b) field acquisition — Playwright-first, API-fallback**:
  - **Primary: Playwright render** of `homepage.hit.edu.cn/<name>` — the page's own JS does the AES + render; scrape the rendered DOM for research_directions / papers / education / contact. Robust; generalizes to other JS-crypto faculty systems.
  - **Fallback: `{k,v,d}` API replication** — AES-CBC-Pkcs7, key/IV = random 16-char (charset `ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678`), sent as `k`/`v` params with encrypted payload `d` (scheme in `scripts/utils/cjsUtils.js` + `newUtils.js:2786`). Use only if Playwright's rendered DOM is sparse.
  - **Smoke-first**: slice 2.2a renders ONE HIT teacher page via Playwright, dumps the rendered DOM, confirms research/papers/education present. If absent → switch to API replication (and report).

## RED (must fail before implementation; deterministic)
1. `tests/.../test_homepage_http_redirect.py` — fetching a URL that 301-redirects records the FINAL `http_status` (200) and content, not `NULL`. (Repro: `faculty.hitsz.edu.cn/<n>` → `homepage.hit.edu.cn/<n>`.)
2. `tests/.../test_hit_field_mapper.py` — given a fixture rendered HIT DOM (or decrypted API JSON), the mapper extracts `research_directions`, papers, `education`/`work_experience` with source `hit_homepage` + `run_id`; non-present fields are absent (not fabricated).
3. `tests/.../test_hit_provenance.py` — no HIT-sourced field written without `source` + `run_id`.

## GREEN
- `homepage_http.py` redirect-following (flag-gated if needed).
- `professor/hit_*` extractor: Playwright render (or `{k,v,d}` API) → field mapper → `professor_fact`/papers with provenance. Mirrors the SIGS adapter precedent.
- Re-run the field-completeness audit for HIT-SZ; the 136 professors move off 0%.

## Allowed mode
Superpowers TDD on the deterministic RED (1–3). The Playwright/API acquisition + live HIT render are acceptance (smoke-first). Must not: break other schools' fetch; weaken evidence/`run_id`; write fields without provenance; auto-write low-confidence facts (→ `needs_review`). If smoke shows Playwright DOM is sparse, update this contract + switch to API replication before building further.

## Acceptance evidence (not RED)
- L4(a): a redirecting seed URL now records `http_status=200` + content (was NULL).
- L4(b) smoke: rendered DOM of ≥1 HIT teacher contains research/papers/education (or the API path returns decrypted structured data).
- Re-audit: HIT-SZ field fill-rates rise off 0%; before/after artifact saved; papers land for HIT-SZ professors (bonus: Part 2.1 for this school).

## Do-not (Codex)
- Do not modify the roster adapters (`roster.py`) — HIT roster is fine.
- Do not weaken the `professor-profile-field-extraction-integrity` contract or evidence/`run_id`.
- Do not write fields without source provenance; do not fabricate.
- Report per slice: files changed, RED→GREEN test commands + counts, smoke result (DOM-has-fields or API-decrypt success), and the re-audit delta.
