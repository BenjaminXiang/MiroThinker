# Web-completion track — design (2026-09-13)

Status: design draft, awaiting main-context adjudication (§5) — no code written.
Change: `close-workbook-gaps` (GAP-04 completeness) + the queued web-completion
track of `retrieval-v2-derived-index-and-fusion` (tasks.md header).
Provenance: back-fills the "agent-14 design" cited by `docs/plans/index.md:18` and
`docs/plans/2026-09-10-system-completion-log.md:1135,1142,1188`; entry 40 of that
log records that the referenced design never landed anywhere in the repo.
All line numbers are the serving worktree rev
`.worktrees/canonical-v2-s11-consolidation` (branch `codex/canonical-v2-s12a-ready`),
read-only. Every number below is quoted from an artifact read for this draft.

## 1. Problem & acceptance

`g5-t2` = `"上述企业有哪些是深圳的企业"`, turn 2 of the PCB session
(`.agents/runs/testset-baseline-20260909/anchors.py:89-95`). GT = 12 key points
(嘉立创/华秋/中信华/领智/兴森/深南电路/顺易捷/一博/则成/上达/精诚达/广州),
`key_points_ratio 0.75` → pass needs **≥9/12**. Scoring is the completeness layer:
substring hits inside the answer text (`run_testset.py:147-155`).

**Measured local ceiling = 8/12.** `results-lat3-g5-s1.json` and
`retrieval-v2-derived-index-and-fusion/off-20260913-testset-g2g5.json`, both turn 2:
`completeness hits 8 / total 12 / fails coverage:8/12<0.75`; hits = 嘉立创, 兴森,
深南电路, 顺易捷, 一博, 则成, 上达, 精诚达. The missing 4 are the out-of-pack
companies from the log-entry-31 forensics
(`docs/plans/2026-09-10-system-completion-log.md:1118`): 华秋, 中信华, 领智 (深圳),
鼎纪 (广州 — the exception captured by the key point `广州`).

| # | Acceptance | Proof |
|---|---|---|
| A1 | `g5-t2` completeness ≥9/12, every added member carrying ≥1 bound evidence item | harness run of the g5 session, ≥3 samples, same pack |
| A2 | No local-first regression: replay 7/7, testset g2 3/3, g5-t1 unchanged | `replay_fix_round1.py` + testset runner, ON vs OFF same pack |
| A3 | TTFT ≤24.5 s on the seven probe turns, completion turn included | latency probe r4, switch ON |
| A4 | Honest disclosure: each web-completed member is either backed by a validated official URL (emitted as `official-source-` card) or explicitly marked web-sourced / not in the local KB | answer-text + citation-payload assertions per §4.3 |
| A5 | B4 rules untouched: no `ChatCitation` extension, no web card type, filtering stays on fetch→snippet→claim (`design.md:825-880`) | harness `web_boilerplate` check; citation-model diff = zero |
| A6 | Degradation: provider 403/timeout/breaker-open yields a complete answer, no fabricated member, no stream error | fault injection on the completion path (1b.0b pattern) |

**What does NOT count as solved.** Substring padding — names dropped into an
"此外还有…" tail with no identity or provenance (the scorer cannot tell, so the
implementation must not chase it); calling a company Shenzhen-registered on a listicle
page; weakening the B4 adjudications; switching local lanes down to make room; and
treating "8/12 plus a disclosure" as success (option E below — honest, but fails A1).

## 2. Current behavior map

### 2.1 How web evidence is triggered, bound, and cited today

1. **Plan.** `_proposal_provider` (`knowledge_serving_isolated.py:622`) always puts
   `"web"` in `lanes`; the `WebSearchPolicy` model (`knowledge_read.py:678-684`) is
   built at `knowledge_read.py:4797-4818` — `universal` for information retrieval,
   `official_only` only with an allowed-host list.
2. **Views.** `_serving_query_views` (`:2160`) emits ≤4 views; a narrowing turn
   prefixes the search text with `(name1 OR name2 …)` from the displayed names
   (`:663-676`). Enumeration turns add one discovery round (`:1470-1490`) and one
   gap-judge refinement (`:1524-1550`).
3. **Search + fetch.** `_DualWebLaneAdapter` (`:998`): Bocha + Serper per view with
   cache read-through, one transport retry, breaker and quota (`_provider_search`
   `:1062`); `_enrich_with_page_text` (`:1419`), fetch depth 8 on enumeration turns
   else 2 (`:1506-1514`).
4. **Subject gate.** `_apply_web_subject_consistency` (`:854`) tiers results with
   `_web_result_relevance_tier` (`:2430`); once ≥`_WEB_SUBJECT_CONSISTENCY_FLOOR = 3`
   (`:851`) results match a *bound* entity, every unmatched (tier 5) result is dropped
   (`record_gate_drop` at `:927`).
5. **Evidence binding.** Each kept result becomes an `EvidenceItem` with
   `source_nature="current_web"` hardcoded (`:1594`), `source_authority="official"`
   only when the host ends with a `request.web_policy.allowed_domains` entry
   (`:1600-1606`), `claim_binding.subject_id = canonical_id or object_id` (`:1608-1613`).
   `_matched_bound_entity` (`:2501`) binds only to `request.bound_entity_ids`, else the
   candidate is `identity_kind="web_only"`, `resolution_state="unresolved"` (`:1631-1634`).
6. **Handles.** `knowledge_read.py:8127-8189`: a candidate without `canonical_id`
   becomes a `WebEntityHandle` (`:3304-3317`) whose `display_name` is the **page title**
   and whose `domain` is `request.domains[0]` (`_web_domain`, `:790`) — and only if it
   has a web snapshot, a session id, and `current_web` evidence; otherwise it is filed
   `unresolved_identity` and dropped (`:8148-8152`).
7. **Answer.** The member-coverage sentence (`knowledge_answer.py:1339-1372`) names only
   `CanonicalEntityHandle` company handles; the degraded fallback self-labels
   (`knowledge_answer.py:1520-1541`).
8. **Cards.** `_public_citations`
   (`apps/admin-console/backend/services/canonical_v2_chat.py:2407-2495`): the evidence
   must bind to a handle in `_PUBLIC_DOMAINS` (`:72`); a `current_web` item with no
   validated official URL (`_official_evidence_url` `:893-909`, requiring
   `source_authority == "official"`; else a host match against official hosts derived
   from the same handle's local evidence, `_current_web_url_for_official_hosts`
   `:919-935`) hits `continue` — **no card at all**.

### 2.2 Why this cannot reach the four out-of-pack companies (mechanism)

- **The narrowing turn only searches the displayed set** — views become
  `("<the 64 displayed names> OR …") 上述企业 深圳`, so the lane can only re-confirm
  turn 1's displayed companies.
- **The subject gate removes everything else**: a page about 华秋 matches no bound
  entity and, with ≥3 anchor hits present, is dropped (`:851-890`). Observed on
  `g5-t2`: the web lane runs 6.4 s and commits **zero** web handles
  (`turn-debug/turn-debug-l2rSgYIkP0sW-02.json`: 64 committed ids, all `company-c-…`);
  the out-of-pack names appear in neither `committed_names` nor `recalled_handles` —
  reproduced in all 11 sessions of that query (`turn-debug/turn-debug-*-02.json`).
- **On turn 1 the names exist only as page titles.** The lane recalls them —
  `{"kind": "web", "domain": "company", "display_name": "几款主流PCB软件比较 - 华秋电路"}`
  (`turn-debug-ErYF9kTLSE0n-01.json`) — but as `unresolved` web handles carrying a page
  title, and in the one run that committed web handles at all
  (`turn-debug--A6zaQLdSs0I-01.json`, 2 of 66) both were official pages of *local*
  companies. So the next turn's universe (`planned_displayed_ids`, 63-64 canonical ids)
  can never contain them.
- **Even a committed web-only company has no channel to the user**: not the member
  coverage sentence (canonical handles only, `knowledge_answer.py:1344-1352`), not a
  card (`canonical_v2_chat.py:2455-2460`), because a listicle host gives
  `source_authority="web_search"`.
- **The pack physically lacks the 4 companies** (log entry 31: "12 家 GT 里本地只有
  4-5 家"), so no local lane or `深南电路`-class fix (registered-address witness,
  `7241bfdc`) can help.

The gap is a **missing channel**, not a recall-tuning gap: nothing turns a web page
naming a company into a *member* with identity and provenance, and nothing carries
such a member into the next turn's universe.

## 3. Options

**A — answer-layer mention mining.** On narrowing/enumeration turns, mine company
mentions from the previous turn's web evidence + answer prose (reusing
`_company_names_from_web_text`, `:3213`) and append the pack-external ones as a
completion sentence; fusion only in the answer layer. *Pros:* smallest change, no
handle plumbing. *Cons:* mentions come from titles/snippets with no identity or city
attribution — i.e. the padding failure mode of §1 unless a verification step is added,
at which point it is B placed worse; nothing enters the session universe, so the
next-turn re-bucketing has to re-derive from prose.

**B — lane-level completion lane (recommended).** A bounded, separately-triggered web
*completion* lane runs when a universe/narrowing/coverage gap is detected, searches the
missing member names, verifies each against official evidence, and emits one evidence
item per verified member; the answer renders them after the local members with the
disclosure clause. Local lanes are untouched. *Pros:* names get identities and
provenance; verified members can join the session universe so the narrowing turn can
re-bucket them (Shenzhen / not); reuses the existing lane, handle, limitation and
budget machinery; the trigger keeps it off the common path. *Cons:* touches candidate/
handle construction in the read layer, and needs the subject-consistency gate exempted
for exactly the jobs it owns.

**C — extend the supplemental probe pipeline.** A `member_completion` job kind beside
the constraint-seeded discovery (`:4080-4135`), reusing `probe()`, judge batching
(`:2916`) and the cap `_SUPPLEMENTAL_PROBE_MAX_COMPANIES = 6` (`:2910`). *Pros:* least
new surface — budget, retry, cost units and degradation exist. *Cons:* supplemental
jobs are scoped to *material parts* (person/relation/theme); "member of the asked-for
list" does not map onto one without a contract change of its own.

**D — official-only web policy for the narrowing turn.** Widen the turn's policy to
`official_only` with a registry/company-site host list, reusing the existing filter
(`knowledge_read.py:7716-7740`: keep only `source_authority=="official"` items within
`allowed_domains`). *Pros:* A4 becomes automatic. *Cons:* alone it changes nothing —
the view text is still the displayed set (`:663-676`), so the right pages are never
requested; useful only as a **component** of B.

**E — honest-only (do nothing).** Keep 8/12 and disclose the shortfall (the existing
coverage sentence): correct, but fails A1 — the fallback profile if B is rejected.
Citing web evidence without a validated official URL, or adding a web card type, is
rejected outright (`design.md:831-855`).

## 4. Recommended design (Option B)

### 4.1 Placement and mechanism

New module `apps/miroflow-agent/src/data_agents/canonical_v2/web_completion.py`:

- `build_completion_jobs(*, query, evidence_set, prior_turn_text, catalog)` — trigger
  + target-name extraction (§4.2).
- `WebCompletionRunner` — one provider search per member name through the existing
  plumbing (a thin call into `_DualWebLaneAdapter._provider_search`, `:1062`, so cache,
  retry, breaker and quota are shared), ≤1 page fetch per member
  (`providers/page_fetch.py`), returning `CompletionFinding(member_name, evidence,
  official_url | None)`.
- Serving wiring: one `EvidenceItem` per verified member with
  `source_nature="current_web"` (the closed set is **not** extended), `lane="web"`,
  `adapter_version="canonical-v2-web-completion-v1"`, `claim_binding` on the member's
  own object id, plus one `WebEntityHandle` per member (`origin_lane="web"`,
  `provider_version` tag `web-completion-v1` so the harness can count them). No new
  citation type, no `ChatCitation` field change.
- Answer layer: a second clause in the member-coverage path
  (`knowledge_answer.py:1339-1372`) for web-completed members; local clause untouched.

### 4.2 Trigger (when web completion opens)

Deterministic, evaluated after the read phase. Turn shape must be enumeration/narrowing
(`_ENUMERATION_QUERY_MARKERS` present, `:2894`, or the turn carries
`displayed_entity_names`); one gap condition must hold:

- *G-a universe gap* — the lane pool names ≥1 company absent from the pack (membership
  check over `_company_names_from_web_text` output, `:3213`); the turn-1 case (华秋 in
  a page title).
- *G-b narrowing gap* — a narrowing turn whose previous turn's committed web evidence /
  answer prose holds ≥1 pack-external company name; the `g5-t2` case.
- *G-c thin local coverage* — local `displayed_count` < 6 on an enumeration turn
  (`_SUPPLEMENTAL_PROBE_MAX_COMPANIES = 6` reference point, `:2910`).
- *G-d no-anchor class* — zero local recall for a category term: the C1 no-anchor
  branch, "无锚定类走 web 补全 + 如实告知"
  (`.agents/runs/close-workbook-gaps/c1-gate-contract-v1-proposal.md:28,185-198`;
  log entry 24). The §4.4 budget must also allow the run.

### 4.3 Evidence, identity, and citation rules (B4 + C1)

- One evidence item per completion member; `source_nature="current_web"` unchanged. A
  member's **name** must be a legal-name form, not a page title: accept only names that
  (a) pass the existing `COMPANY_NAME_PATTERN` extraction and (b) appear on a page
  whose host/snippet binds them to the asked predicate (registration city, industry).
  Otherwise the finding is `identity_resolution="title_only"` and may feed only the
  disclosure clause, never a member slot.
- **Citation** only through the existing official-URL path: the completion evidence is
  on an allowed official host (`source_authority="official"`, `_official_evidence_url`,
  `canonical_v2_chat.py:893-909`) or its handle already has local evidence with a
  matching official host scope (`:919-935`). Otherwise no card.
- **Mention without card** (needs the §5-3 ruling): the answer may name the member,
  but only inside the disclosure clause, which must say the source is public web, that
  the local KB does not hold it, and make no capability claim. Template:
  `另有 {n} 家企业（{names}）仅见于公开网络信息（{source summary}），本地知识库暂无收录，注册地等信息未经官方来源核验。`
- The B4 filters apply unchanged on the fetch→snippet→claim chain (`_DROP_TAGS` in
  `page_fetch.py`; `_DETERMINISTIC_RAW_DUMP_MARKERS` in `knowledge_answer.py`), so
  listicle/404/JS text can never reach the answer text.

### 4.4 Budget, switches, and fusion position

- Switch **off by default**: `CANONICAL_V2_WEB_COMPLETION` = `off | shadow | on`, with
  `web-completion.conf` pinned in the style of the lexical lane's `lexical-index.conf`.
- Initial budgets: ≤4 jobs/turn, 1 provider call per job (1 transport retry), ≥1 page
  fetch per job, per-job wall 2.5 s, **total completion wall 6.0 s**; judge batching
  reused (`_PROBE_JUDGE_JOBS_PER_BATCH = 8`, `:2916`) so LAT-3's serialization fix is
  not undone. The wall is charged *inside* the existing web-phase budget, never added
  on top; once exhausted the answer falls back to the disclosure clause.
- Fusion position: **answer layer, local-first.** Completion members append after local
  members, never displace or reorder them, and do not enter the claim window. They do
  join the session handle universe so the next narrowing turn can re-bucket them — the
  mechanism that makes `g5-t2` pass, and open question §5-1.
- `shadow` mode: jobs built and traced (counts, names, hosts), no evidence committed,
  no answer-text change — the calibration mode.

### 4.5 RED → GREEN acceptance plan

| Step | RED artifact (fails on today's tree) | GREEN assertion |
|---|---|---|
| 1 | `test_web_completion_trigger.py`: g5-t1 evidence naming 华秋 etc. + pack catalog → `build_completion_jobs` | job set = {华秋, 中信华, 领智} (+ the 广州 branch), each with a source page |
| 2 | `test_web_completion_gate_exempt.py`: same-shape completion page vs ordinary page | completion item survives; ordinary T5 still dropped — gate semantics unchanged |
| 3 | `test_web_completion_citation.py`: listicle source → no card + disclosure; allowed-host source → one `official-source-` card | zero `ChatCitation` schema diff; `_PUBLIC_DOMAINS` untouched |
| 4 | `test_web_completion_budget.py`: 403 / timeout / breaker-open fixtures | 0 members, complete answer, no stream error, `current_web_unavailable` limitation intact (`knowledge_read.py:7707`) |
| 5 | `test_web_completion_off_identity.py`: switch OFF vs pre-change tree on g5/g2/replay fixtures | byte-identical lane results and answer text — OFF is behavior-preserving |
| 6 | offline: run the g5 session ON, same pack, ≥3 samples | A1 ≥9/12; A4 = each added name has a card or the clause, asserted on answer text **and** citation payload (the scorer alone cannot tell a verified member from padding); A2 replay 7/7 + g2 3/3 |
| 7 | live A/B ON vs OFF | A3 TTFT ≤24.5 s on the probe turns; no new replay signature |

### 4.6 Rollout and rollback

`off` (shipped default) → `shadow` on the live entry for one probe round → `on` for
enumeration/narrowing turns only → full. Rollback = flip the switch to `off`; the path
is additive (no pack bytes, no migration, no citation-contract change), so rollback is
immediate and leaves no residue beyond trace files.

### 4.7 Failure modes

| Failure | Behavior |
|---|---|
| 403 / timeout / quota watermark / breaker open (`:1062-1165`) | jobs abort, 0 members, disclosure reports the shortfall, the turn still answers |
| Fetch fails, JS wall, 404 boilerplate | snippet-only evidence; B4 filters apply; a title-only name may not become a member (§4.3) |
| Polluted page (listicle, directory, aggregator) | no official URL → no card; only the disclosure clause may carry the mention; `web_boilerplate` stays silent |
| Budget exhausted mid-jobs / ambiguous identity (one name, several companies) | no partial set; drop the member, never guess; disclose the shortfall |
| Regression on local coverage | switch flip to `off` + replay gate; the lane cannot alter local lane outputs by construction |

## 5. Open questions (main-context rulings needed)

1. **Do web-completed members join the session's displayed/narrowing universe?** For
   `g5-t2` the answer must be built from the previous turn's member set; if they stay
   out, only prose mining (option A) remains and A4 weakens. Joining means a web-only
   `unresolved` handle entering `displayed_entity_ids` — a session-state semantic change.
2. **Which hosts count as "validated official"?** `allowed_web_domains` currently comes
   from the planner proposal (`knowledge_read.py:4797-4818`) and no registry catalog
   exists in `canonical_v2/catalogs/`. This one list decides whether A4 is reachable for
   华秋/中信华/领智 (own site only? plus 国家企业信用信息公示系统 / 深圳市市场监督管理局 /
   exchange filings?).
3. **Is a mention without a card allowed?** B4 forbids the *card* for URL-less web
   evidence but is silent on the answer-text mention; the C1 no-anchor ruling reads as
   yes-with-disclosure. This decides whether the 4th key point is reachable at all.
4. **Does `g5-t2` require proving the negative?** GT includes `广州` (鼎纪, the
   non-Shenzhen exception); an honest answer arguably names it too, in which case the
   lane must also cover *not-Shenzhen* members and A1 evidence must show it.
5. **Seed source for the narrowing trigger**: the previous turn's committed web
   evidence pool (deterministic and cheap — what §4.2 G-b assumes) or the answer prose
   (wider, but needs session text state)? Decides where the handoff is stored.
6. **Budget ownership**: does the completion wall ride the existing web-phase budget
   (max 6 s of it) or get its own allowance? That is the difference between g5-t1
   paying the cost and only g5-t2 doing so, i.e. whether A3 stays comfortable.

## 6. Evidence gaps found while drafting (do not invent)

- No "agent-14 design" exists in the repo; log entry 40 records the gap this file closes.
- The four out-of-pack companies have **no canonical record or legal-name artifact** I
  could read: they appear only as web page titles/prose (华秋 in
  `turn-debug-ErYF9kTLSE0n-01.json`; all four in the entry-31 forensics), so their legal
  names and registration cities are *unverified in this repo* and must come from the
  completion lane itself, not from a fixture list.
- No scoping artifact for this track exists under `.agents/runs/close-workbook-gaps/`
  (the `b4-scoping.md` / `c1-batch0-scoping.md` read-only-pass pattern was never run);
  §2 is a first-pass substitute and a proper pass should fix §4.1's insertion points.
- The §2.2 attribution rests on the LAT-2 turn-debug dumps (11 sessions) plus code
  reading; a `record_gate_drop("web_subject_consistency", …)` counter trace for `g5-t2`
  was not present in those dumps and would make it airtight.
