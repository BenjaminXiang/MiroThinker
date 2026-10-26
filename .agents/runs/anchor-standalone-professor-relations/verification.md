# Verification: anchor-standalone-professor-relations

## 1. Root cause

- `_relationship_path` required `request.displayed_entity_ids`; a single-turn
  ``丁文伯创办的公司`` had none, so the relationship lane never ran and only the
  company-domain free-text lanes + web executed.
- With no bound entity name, `_apply_web_subject_consistency` is a no-op; Bocha's
  lookalike results (丁文波, 广州文伯化工) were answered as 丁文伯.
- Bocha recall for ``丁文伯 专利`` returned 丁文博/丁文胜/其它发明人; the local
  patent lane returned generic patents with `inventors: []`, which the selector
  claimed and cited even though the answer text came from web evidence.

## 2. Changes

- `serving_pack_loader.create_local_entity_resolver`: exact-name resolver over the
  audited lookup view (professor/company, one canonical id only; same-name
  multi-owner declines).
- `canonical_v2_chat._standalone_anchor` + `attach_named_entity_resolver`: a
  single-turn relation query with no displayed entity is planned with the resolved
  entity as its displayed anchor. The runner attaches the resolver after building
  the chat adapter.
- `knowledge_serving_isolated._DualWebLaneAdapter`: optional DeepSeek Search
  second leg (`deepseek=`) used when `CHAT_LLM_PROFILE=deepseek*` and the resolved
  profile key is present; otherwise the pre-existing Bocha+Serper pair is kept.
  Provider order/queries/merge/trace are driven by `self._provider_order`.
- `knowledge_serving_isolated._answer_selector`: for ``<person>有哪些专利`` queries,
  local patent items are eligible only when the person's name appears in their
  evidence text; unrelated local patents no longer leak handles into citations.

## 3. Unit tests

New:

- `apps/admin-console/tests/test_standalone_anchor.py` (3): professor→company,
  company→founder, unrelated/ambiguous decline.
- `apps/miroflow-agent/tests/data_agents/providers/test_deepseek_search.py` (2):
  normalization and missing-key refusal.
- `test_knowledge_serving_isolated.py`:
  `test_dual_web_lane_uses_deepseek_second_leg_when_configured`,
  `test_selector_drops_unrelated_local_patent_for_named_person_query`.

Results:

- New tests: 7 passed.
- `test_knowledge_serving_isolated.py` + `test_web_lane_resilience.py` +
  `test_dual_web_lane_provider_timeouts.py`: 324 passed.
- `test_canonical_v2_chat_http_adapter.py` + `test_canonical_v2_turn_trace_hook.py`:
  138 passed, 1 pre-existing failure
  (`test_s11a_post_chat_uses_release_bound_canonical_v2_without_legacy_sql`,
  expected wording `暂未能确认问题中的` vs current `暂时没有找到直接对应的信息`);
  reproduced at HEAD with the three production files stashed, so not caused by
  this change.

## 4. Live customer-site evidence (PID after final restart; `/api/health` 200)

- ``丁文伯创办的公司是哪家``
  - plan: `lanes=[relationship, web]`, `domains=[company]` (anchored professor);
  - relationship lane: 1 candidate; web: 4 (subject-consistency filtered);
  - answer: 深圳无界智航科技有限公司，担任创始人；citation
    `local-source-08f0d53d00dda3a8` (company handle);
  - no 丁文波 / 千信科技.
- ``丁文伯有哪些专利``
  - plan: patent domain, exact/structured/lexical/vector/web; web 88;
  - answer: 申请号 202410612834.1《一种基于无线光通信的目标检测与识别系统和方法》，
    发明人含丁文伯；并引用清华官网“授权或公开发明专利15项”；
  - citations: 12 web-source only — no unrelated `local-source-*` patent handles;
  - no 丁文博 / 丁文胜 as 丁文伯.
- Regression:
  - ``介绍清华的丁文伯`` → profile answer with official + web citations;
  - ``他参与创立了哪些企业`` (same session) → 无界智航, local company handle;
  - ``无界智航的创始人是谁`` → 丁文伯 (company→professor anchor);
  - ``深圳有哪些机器人公司`` → normal list answer, no behavior change;
  - ``丁文伯教授的研究方向`` → normal profile answer.

## 5. Service / rollback

- Service `active`, `/api/health` 200 after the final restart.
- Rollback: restore the customer copies
  `knowledge_serving_isolated.py.bak-namedanchor-20261023-1055`,
  `serving_pack_loader.py.bak-namedanchor-20261023-1055`,
  `canonical_v2_chat.py.bak-namedanchor-20261023-1055`,
  `complete_candidate_runner.py.bak-namedanchor-20261023-1055`; remove
  `providers/deepseek_search.py` (or leave it unused); restart.

## 6. Local company→patent count (2026-10-23)

`本地知识库收录了优必选多少专利` originally ran patent-domain free-text lanes only
(exact/structured/lexical/vector all 0; web 71) and answered "no统计口径". The
company→patent relationship lane caps candidates at the plan window (128), so even
`优必选有多少专利` could not derive the true total (450 in the pack projection).

Changes:

- `serving_pack_loader.create_company_patent_counter`: counts patent lookup
  documents whose applicant carries the company canonical id; lazy audited view,
  per-company cache.
- `canonical_v2_chat._local_patent_count_response` + `attach_company_patent_counter`:
  a count-marker query (`多少/几件/数量/收录/总数/共计` + `专利`) resolves the company
  and answers deterministically with the local company citation card.
- Resolver fix: the name index matches derived short names (`优必选` from
  `深圳市优必选科技股份有限公司`); the resolver no longer requires the stored
  display term itself to be a substring.

Live evidence (fresh sessions, service active/health 200):

- `本地知识库收录了优必选多少专利` → `本地知识库收录了深圳市优必选科技股份有限公司 450 件专利`,
  citation `local-source-5ac2eb76475da877`,
  `structured_payload={"local_patent_count":450,"company_id":"company-c-c4b02d6a3e3ff20804d96024"}`.
- `优必选有多少专利` → same 450 answer.
- `优必选有哪些专利` → normal relationship+web listing, 12 local patent citations;
  count fast path did not hijack it.
- First count query paid the one-time audited-view build (~3.5 min under boot
  warm-up); subsequent queries answered in seconds.

Tests: `test_standalone_anchor.py` 5 passed (anchor 3 + count 2); serving/web
324 passed; DeepSeek provider 2 passed.

## 2026-10-26 amendment: professor consumer completeness

Deployed files (customer bundle) and md5:

| file | md5 |
|---|---|
| `knowledge_serving_isolated.py` | `c91b00776f2bf404e718bffee5a3eb97` |
| `knowledge_read_isolated.py` | `eb265b970cd49b3c3d776454aeaac66d` |
| `followup_referents.py` | `833adb7ec766113e6ccf8c4913bb1c0e` |
| `canonical_v2_chat.py` | `87840fde1906ae393764e4e0e273eb12` |
| `canonical_v2_admin.py` | `850bbb9f0e47431aa260acd549b01416` |
| `canonical_v2_answer_cache.py` | `0c90b3c0f5a24fa9b61ea129db2e9cb9` |

Live evidence:

- `丁文伯的邮箱和院系是什么` → `ding.wenbo@sz.tsinghua.edu.cn` +
  数据与信息研究院；2 local professor citations.
- `赵大锤教授的研究方向` → "没有找到公开信息"，no neighbour substitution.
- Synthetic `_semantic_text` payload → 院系/邮箱/主页/论文数/专利数/教育/
  工作/获奖/企业角色 all rendered; non-founder role "担任首席科学家".
- Cookie-jar probe `丁文伯有哪些论文` → `他的研究方向有哪些？` →
  **11.42s / 12 citations**, answers 丁文伯's research directions, no
  clarification.  The earlier false negative came from a probe without a
  cookie jar: `/api/chat` binds by `miroflow_chat_session`, not JSON
  `session_id`.
- `--mode full` golden set: 27 turns / 19 conversations, **81/120 required
  (68%)**, 0 forbidden, 0 refusal miss, 0 errors, mean 14.0s.

Not fixed in this amendment: professor→patent relationship data (pack has no
instances); professor topic enumeration (q27 still 0/4); 54% template
profile_summary dilution (index build issue, needs rebuild).

## 2026-10-26 P0 entity grounding

Deployed: `knowledge_serving_isolated.py` md5
`982b24821d1471bfa56866595f77022f`.

- Only the deterministic view carries bound subjects; llm_rewrite,
  term_expansion, and authority_seeking views are recall-only (empty bound
  entities and no soft subject).
- Professor-topic queries filter company-shaped bound names; 2-char bound
  names are not subjects.
- `_apply_web_subject_consistency` returns the lane unfiltered for
  `有哪些…教授`; other topic queries fail open when the gate would keep
  less than one third of ≥20 results and log `web_subject_gate_fallback`.
- q27 trace: web `in=76 / retained=76 / filtered=0`, `gate_drops={}`
  (before: 75/11/64 with `web_subject_consistency: 64`).
- q27 answer still `citation_count=0`: the selector skips web evidence with
  `claim_binding is None`, so the 76 web results never become claims. The
  next slice is a web discovery answer mode (topic/unbound web claims), not
  another entity-recognition patch.
