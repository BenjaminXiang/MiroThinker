# Handoff — layer-d-multi-turn-context, task group 5: narrowing mechanisms

> Claude → Codex. One Ready slice. Groups 2 (coref) + set-traversal (3 rule-routing/4 exec)
> Accepted. This delivers the **three narrowing mechanisms + selector** so set-narrowing
> follow-ups use the right mechanism per predicate type.

## Contract

- OpenSpec: `openspec/changes/layer-d-multi-turn-context/` — spec requirement "Narrowing
  selects its mechanism by predicate type" + scenarios (chip deterministic / open-LLM
  audited / unknown-vs-unsatisfied / topic preserved).
- Verification contract: `.agents/runs/layer-d-multi-turn-context/verification-contract.md`.
- RED evidence this slice fixes: `red-notes.md` **M2** (qid4, qid10, S6B-F — 在深圳 sent to
  semantic retrieval → junk/not-in-set) and **M7** (qid5 — open predicate → unknown refusal).
- ADR-011 D6; glossary root `CONTEXT.md` (chip/open/topic predicates, coverage statement).

## Current seam (code-verified)

`_handle_d_narrowing` (api/chat.py:4964) is the single entry — it calls
`_lookup_narrowed_results` (chat.py:2088) which runs `retrieve(topic) ∩ allowed_ids`. That is
the **topic** mechanism. This slice keeps it as the fallback and inserts two mechanisms
before it, chosen by a deterministic selector. Fetch-by-id helpers exist:
`_lookup_company_by_id` (2354), `_lookup_professor_by_id` (2230); patent/paper by-id lookups
are via `_lookup_patent`/`_lookup_paper` (title/query param also accepts an id — verify, or
add a thin by-id variant). Per-domain fields available: professor→`institution`; patent→
`grant_date`, `filing_date`, `applicants_raw`, `patent_type`; paper→`year`. Company has no
region column surfaced in `_lookup_company_by_id` — VERIFY the company table for a region/
registered_address column; if absent, the region predicate for company uses
canonical/registered name prefix (深/深圳) and notes the basis (the platform is Shenzhen-local
so the predicate is near-tautological — that is fine, state it).

## Scope

### A. Chip-predicate detector (pure, services/chat_context.py)
`detect_chip_predicate(query, domain) -> ChipPredicate | None`. Closed table, 4 kinds:
- **region**: 在深圳 / 总部深圳 / 深圳的 / 在XX (XX = city). param = city token (default 深圳).
- **recency**: 近两年 / 近N年 / 2024年 / 近一年. param = (kind, N or year).
- **grant_status**: 已授权 / 已授权的 / 授权的. (patent only)
- **applicant_type**: 申请人是企业 / 申请人为公司 / 申请人类型. param = type (企业).
Return kind + param + which domain it applies to (some kinds are domain-specific — e.g.
grant_status only patent; region applies to professor/company). If the predicate kind is
N/A for `domain`, return None (falls through to next mechanism). Pure; unit-test the table.

### B. Per-domain chip-predicate evaluator (api/chat.py or chat_context.py)
`evaluate_chip_predicate(domain, member_row, predicate) -> (verdict: bool|None, basis: str)`.
- verdict True = satisfies, False = does not satisfy, None = 信息缺失 (field empty/absent).
- Field mapping per (domain, kind):
  - region/professor: `institution` contains city → True; empty → None.
  - region/company: region column OR name prefix 深圳市比/深圳 → True; verify column; if no
    signal → None (NOT False).
  - recency/paper: `year >= cutoff`; missing year → None. recency/patent: `filing_date` year.
  - grant_status/patent: `grant_date` non-empty (or legal_status granted) → True; only
    `filing_date` no grant → False (明确未授权, not None). empty both → None.
  - applicant_type/patent: `applicants_raw` matches 企业/公司/有限公司 → True; only 个人/大学 →
    False; empty → None.
- basis string explains the verdict per member ("张三 — 清华大学深圳国际研究生院 → 在深圳").

### C. Chip-narrowing handler (replaces topic path when a chip predicate matches)
New path in `_handle_d_narrowing` (or a sibling `_handle_chip_narrowing`):
- Fetch member rows by ID for `domain` (reuse by-id helpers; cap to the set).
- Evaluate predicate per member → list of (member, verdict, basis).
- Render: coverage statement ("上轮 N 个{label}中，M 个在深圳，K 个不在/信息缺失") + per-member
  basis lines; satisfy-members listed first with citations.
- `query_type="D_narrowing"` (unchanged — no new A-G class). **`skip_synthesis=True`** on
  `_build_chat_response` (same rationale as traversal: deterministic predicate, synthesis
  would override with hallucination). structured_payload: `{source_ids, narrowing_domain,
  predicate, verdicts:[{member_id,label,verdict,basis}], retrieval_evidence: [satisfy rows]}`.
  `source_ids` present so eval set_derived passes.

### D. Open-predicate LLM lane (per ADR D6 + user steer "充分利用 LLM")
When NO chip predicate matches AND `llm_synthesis_enabled()`:
- Fetch full member rows by ID (include rich fields: company products/scenarios,
  professor research_topics, paper abstract, patent abstract).
- Per member, call the synthesis LLM lane (reuse `_call_gemma_synthesis`'s client /
  `resolve_professor_llm_settings` — deepseek-v4-pro) with a structured-output instruction:
  given the member's fields + the predicate, emit `{member_id, verdict: true|false|unknown,
  evidence_field, quote}`. Batch into one LLM call over all members where feasible (one
  prompt listing all members + predicate → JSON array of verdicts); fall back to per-member
  on parse failure.
- verdicts audit-logged in `structured_payload` (under `open_predicate_verdicts`).
- Render: coverage statement + per-member verdict with quoted evidence. `skip_synthesis=True`
  (the LLM already judged; don't re-synthesize). query_type D_narrowing.
- Degradation: if `CHAT_LLM_SYNTHESIS=off`, skip this lane → fall through to topic (label
  answer 按语义相关性筛选).

### E. Selector (deterministic order, in `_handle_d_narrowing`)
```
predicate = detect_chip_predicate(query, domain)
if predicate is not None:
    return _handle_chip_narrowing(...)        # C
if llm_synthesis_enabled():
    if open_resp := _handle_open_predicate_narrowing(...):   # D
        return open_resp
return <existing topic narrowing>             # unchanged: retrieve(topic) ∩ set
```
Topic narrowing stays exactly as today (S6D 已授权 currently passes via it; the new chip
grant_status path will also handle it deterministically — either is fine, chip takes
precedence per the selector).

### F. Tests (new tests/test_chat_narrowing_mechanisms.py, env off for chip path)
- Chip detector table (4 kinds × applicable domains; N/A-domain → None).
- Evaluator matrix per domain (True/False/信息缺失 boundaries).
- Chip-narrowing render: coverage statement, per-member basis, satisfy-first, citations,
  source_ids in payload, skip_synthesis set.
- Selector order: chip beats open beats topic; classifier-off irrelevant (rule-based).
- Open-predicate lane with a MOCKED LLM (monkeypatch `_call_gemma_synthesis` or the client)
  returning structured verdicts → render + audit payload; degradation to topic when off.
- Unknown-vs-unsatisfied (empty field → 信息缺失, not counted as False).

## Non-goals (hard boundaries)

- NO classifier prompt/schema changes (still deferred).
- NO anchor-stack changes (group 6).
- NO traversal changes (group 4 done).
- NO fixture / eval-runner edits (Claude adjusts at review if needed).
- A-G taxonomy unchanged (reuse D_narrowing).
- Do NOT run the multi-turn eval or restart the backend (Claude runs eval at review; backend
  on :18188 is live — leave it).

## Environment

Unit tests: `cd apps/admin-console && unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
all_proxy ALL_PROXY no_proxy NO_PROXY && CHAT_AUGMENT_WEB=0 UV_CACHE_DIR=/tmp/mirothinker-uv-cache
uv run --no-sync pytest tests/test_chat_narrowing_mechanisms.py tests/test_chat_d_narrowing.py
tests/test_chat_set_traversal.py tests/test_chat_set_coreference.py tests/test_chat_session_persistence.py -q`
(+ any test touching `_handle_d_narrowing`/`_lookup_narrowed_results`).

## Candidate criteria

- All listed unit tests green; full chat suite no new failures.
- Diff confined to: services/chat_context.py (detector + evaluator), api/chat.py (handlers +
  selector + by-id fetch), new test file.
- Report: exact commands + output, files changed, the verified company-region column (or
  confirmed absence + fallback used), any spec-vs-code discrepancy.

## Next owner

Claude review → eval (expect qid4/10/S6B-F → region chip deterministic; qid5 → open-LLM,
data-permitting; S6D stays green; single-turn 19-case zero regression) → Accept ⇒ group 6
(anchor/clarification listing) Ready.
