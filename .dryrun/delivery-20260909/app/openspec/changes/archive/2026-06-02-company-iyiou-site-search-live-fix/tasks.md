## 1. Contract And Tests

- [x] 1.1 Add RED test proving Serper web search parses `organic` results from `site:data.iyiou.com` without news-query tails.
- [x] 1.2 Add RED test proving Yiou CLI wiring uses Serper web search rather than Serper news.
- [x] 1.3 Add RED test for live E2E `--live-limit`.

## 2. Implementation

- [x] 2.1 Implement `SerperSearchConnector` using `/search` and `organic`.
- [x] 2.2 Wire Yiou adapter delegation to `SerperSearchConnector`.
- [x] 2.3 Load `apps/miroflow-agent/.env` for company live-enrichment scripts.
- [x] 2.4 Update live E2E to scan a bounded company sample and report aggregate Yiou hit counts.

## 3. Live Verification

- [x] 3.1 Run focused connector and script tests.
- [x] 3.2 Run `run_company_enrichment_e2e.py --live --live-limit 20 --output -`.
- [x] 3.3 Record live hit counts and any zero-result samples.
- [x] 3.4 Validate OpenSpec strict and update acceptance evidence.

## 4. PitchHub And Context Query Expansion

- [x] 4.1 Add RED tests for XLSX description/team/project context becoming Yiou/PitchHub query terms.
- [x] 4.2 Add RED tests for PitchHub source adapter provenance and accepted detail paths.
- [x] 4.3 Add RED test proving PitchHub fetches accepted detail page text through the reader fallback after acceptance.
- [x] 4.4 Add regression coverage preventing generic product phrases from becoming standalone aliases.
- [x] 4.5 Implement PitchHub site-filter connector wiring in ingest and live E2E.
- [x] 4.6 Run focused tests, lint, and live E2E after PitchHub/context-query expansion.
