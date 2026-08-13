## ADDED Requirements

### Requirement: Follow-up elaborations SHALL continue the prior subject

The chat layer SHALL recognize natural elaboration phrasings (有没有/还有/能不能 + 更/再 +
详细/具体/深入/展开, bounded length) as continuation intent, so a follow-up like
`有没有更详细的信息` keeps the conversation context instead of falling to the no-context
fallback. The 更/再 degree word SHALL directly follow the opening hedge, so enumeration
(`有哪些详细的论文`) and expansion requests (`还有哪些`, `有没有类似的`) stay excluded; turns
with an explicit named subject SHALL still be excluded via `has_explicit_named_subject`.
(Shipped: `27d0231`.)

#### Scenario: an elaboration follow-up binds the prior subject
- **GIVEN** turn 1 established a subject (canonical or web-only)
- **WHEN** turn 2 is `有没有更详细的信息`
- **THEN** the turn is treated as continuation and the answer deepens the prior subject
  rather than answering with the no-context fallback

#### Scenario: enumeration and expansion requests stay excluded
- **GIVEN** a prior subject exists
- **WHEN** the follow-up is `有哪些详细的论文` or `还有没有类似的`
- **THEN** it is NOT treated as continuation elaboration of the prior subject

#### Scenario: an explicit named subject overrides the soft subject
- **GIVEN** a stored soft subject anchor
- **WHEN** the follow-up names a different explicit subject
- **THEN** the explicit subject wins and the soft anchor does not bind the turn

### Requirement: A soft subject anchor SHALL bind web-only subjects, on continuation and on fresh turns

The chat layer SHALL bind web-only subjects with a session-persisted soft subject anchor:
when the first turn's subject is not in the canonical store (web-only answer), it SHALL
persist a `soft_subject_name` on the committed session (preferring the subject extracted
from the user query; a single web entity handle's display name as fallback, rejecting
news-headline shapes) and inject it as `QueryPlanningRequest.soft_context_subject` on
continuation turns, so web-lane views are prefixed with the subject, clarification yields
when the soft anchor resolves the referent, and the turn stays continuation (not
topic_switch) so prior web evidence carries over. (Shipped: `27d0231`.)

On fresh or explicit-subject turns with no continuation anchor and no canonical ids from
prior context, the chat layer SHALL derive the soft subject from the current query using
the same query-first extractor (`_search_view`), so the web-lane gate, authority-seeking
views, multi-branch guidance, and prose correction engage on THIS turn. The derived value
SHALL anchor only the current turn's planning/serving/answer: the session-directive
(topic_switch) decision SHALL keep receiving the continuation-only value. Guarded
(non-empty, ≤30 chars, not whole-query echo, no question/negation shapes) queries that
fail the guards SHALL NOT derive. A stored continuation anchor SHALL always win over
derivation. (Shipped: `d3c8ff0`.)

#### Scenario: web-only subject persists and binds the next turn
- **GIVEN** turn 1 answered about a web-only subject (no canonical entity)
- **WHEN** turn 2 is an elaboration follow-up
- **THEN** the planning request carries `soft_context_subject` and the web-lane views are
  prefixed with the subject

#### Scenario: fresh-turn org-level query derives the soft subject
- **GIVEN** a fresh session (no stored anchor, no canonical ids)
- **WHEN** the query is `介绍一下国际先进技术应用推进中心`
- **THEN** the planning request carries `soft_context_subject = 国际先进技术应用推进中心`
  and authority-seeking views fire from turn 1

#### Scenario: continuation anchor wins over derivation
- **GIVEN** a stored soft subject anchor AND an elaboration follow-up
- **WHEN** the planning request is built
- **THEN** it carries the stored anchor name, not a re-derived value

#### Scenario: derived subject does not flip session-transition semantics
- **GIVEN** a mid-session explicit org switch with no stored anchor
- **WHEN** the session directive is computed
- **THEN** it sees the continuation-only value (None) and the topic_switch decision is
  identical to pre-derivation behavior

#### Scenario: echo and negation queries do not derive
- **GIVEN** queries like `国际先进技术应用推进中心怎么样` (whole-query echo) or
  `不包括国际先进技术应用推进中心的介绍` (negation)
- **WHEN** derivation is attempted
- **THEN** no soft subject is injected

### Requirement: Web evidence SHALL be ranked by dual-provider corroboration and a three-tier subject-consistency gate

The dual-channel web lane SHALL rank results returned by both providers
(`corroborating_provider_versions >= 2`, tier T0) before single-channel results, preserving
relative order within each group. When bound entity names (or the soft context subject)
are present, the lane SHALL classify each result into relevance tiers — T0 corroborated;
T1 org stem + anchor location qualifier both present (branch-qualified hit); T2 org stem
present (same organization, unqualified); T3 org stem present with a DIFFERENT location
qualifier attached (other branch); T4 only compact-alias forms hit (loose alias, the
wrong-organization channel); T5 no match — using full-name identity forms only (company
legal-suffix truncations count as full-name forms, never compact aliases). When the kept
set (T0∪T1) meets the FLOOR, the gate SHALL keep T0∪T1 first (stable), then T2, then T3,
and drop T4/T5; below the FLOOR it SHALL backfill in T2→T3→T4→T5 order so single-channel
niche subjects survive and the lane never errors out. With no bound names and no soft
subject the gate SHALL pass results through unchanged. The soft context subject SHALL be
merged into the gate's bound names but stay out of `_matched_bound_entity` so it cannot
mis-anchor to a lookalike canonical entity. (Shipped: `50c4f3a` corroboration + binary
gate; `7cad141` identity-form split + tier classifier; `6fda6b6` three-tier gate.)

#### Scenario: corroborated results rank first
- **GIVEN** web results from Bocha and Serper for the same query
- **WHEN** a result is returned by both providers
- **THEN** it ranks before single-channel results regardless of per-channel order

#### Scenario: lookalike and no-match results drop out when the floor is met
- **GIVEN** results whose kept set (T0∪T1) has at least FLOOR entries, plus a T4 loose-alias
  lookalike (e.g. 南开国际先进研究院（深圳福田） for anchor 国际先进技术应用推进中心（深圳）) and
  a T5 unrelated result
- **WHEN** the gate runs
- **THEN** the T4/T5 results are dropped and T2 (same org) results precede T3 (other branch)

#### Scenario: below-floor backfill preserves niche subjects
- **GIVEN** fewer than FLOOR T0∪T1 results
- **WHEN** the gate runs
- **THEN** results are backfilled to the FLOOR in T2→T3→T4→T5 order instead of erroring
  or returning an empty lane

#### Scenario: soft subject binds the gate on the web-only path
- **GIVEN** no canonical bound names and a soft context subject carrying （深圳）
- **WHEN** the gate runs
- **THEN** the lookalike (T4 for the soft anchor) is dropped and the branch-qualified hit
  is kept

#### Scenario: no anchor means passthrough
- **GIVEN** no bound entity names and no soft context subject
- **WHEN** the gate runs
- **THEN** the results are returned unchanged

### Requirement: Qualified anchors SHALL be pinned to their branch on the sync answer path

The sync prose renderer SHALL pin a qualified anchor to its branch: when the anchor
carries a location qualifier (from its parenthesized qualifier, or a location lexicon
term co-occurring with the org stem in the user query), the renderer SHALL treat the
answer as on-anchor only when the org stem AND the normalized qualifier co-occur in the
answer. An off-anchor answer SHALL trigger one corrective re-synthesis with a
branch-focused correction message (name the branch; attribute other-branch content
explicitly; never interrogate the user); if the retry still misses, the renderer SHALL
fall back to the deterministic evidence list rather than publish a wrong-branch
synthesis. Without a qualifier, the phase-1 identity-form mention behavior SHALL apply
unchanged. (Shipped: `50c4f3a` sync correction; `9afe730` qualifier pinning.)

#### Scenario: branch-qualified answer passes without correction
- **GIVEN** anchor 国际先进技术应用推进中心（深圳） with qualifier 深圳
- **WHEN** the synthesized answer mentions the org stem and 深圳
- **THEN** no correction is triggered

#### Scenario: other-branch answer is corrected to the anchor branch
- **GIVEN** the same qualified anchor
- **WHEN** the first synthesis answers only about the 合肥 branch
- **THEN** one corrective retry runs with a message naming 深圳, and the final answer is the
  corrected one (or the deterministic fallback if the retry still misses)

#### Scenario: correction message names the branch and forbids interrogation
- **GIVEN** a qualified anchor
- **WHEN** the correction message is built
- **THEN** it names the branch qualifier, requires explicit attribution of other-branch
  facts, and forbids asking the user for more information

### Requirement: The qualified off-anchor check SHALL test subject organization, not mere mention

On the qualified path, an answer SHALL be on-anchor only when the org stem and the branch
qualifier co-occur AND the anchor organizes the answer — the org stem appears in the
answer's first sentence OR recurs at least twice in the normalized answer. A
lookalike-organized answer that name-drops the anchor stem once mid-answer SHALL be treated
as off-anchor and corrected. The unqualified path (no location qualifier) SHALL remain a
plain identity-form mention test, byte-identical to phase 1. (Shipped: `6af3715`.)

#### Scenario: lookalike-organized answer is rejected despite a name-drop
- **GIVEN** anchor 国际先进技术应用推进中心（深圳） with qualifier 深圳
- **WHEN** the answer is organized around 中国科学院深圳先进技术研究院 and mentions
  国际先进技术应用推进中心 only once as a subordinate item
- **THEN** the check reports off-anchor and the correction path engages

#### Scenario: anchor leading the first sentence passes
- **GIVEN** the same qualified anchor
- **WHEN** the answer opens with 国际先进技术应用推进中心（深圳）…
- **THEN** the check passes

#### Scenario: framing opener with a recurring stem passes
- **GIVEN** an answer whose first sentence is a framing clause without the org stem
- **WHEN** the org stem appears at least twice in the answer
- **THEN** the check passes

#### Scenario: unqualified path keeps mention semantics
- **GIVEN** an unqualified org-level anchor
- **WHEN** the answer mentions an identity form once mid-answer
- **THEN** the check passes (phase-1 behavior)

### Requirement: Stream answers SHALL get one fail-open final-answer off-anchor correction

Because streamed chunks are irrevocable once published, the stream path SHALL, after the
stream finalizes, apply the same off-anchor check (including qualifier pinning and the
subject-organization test) and, on drift, run exactly ONE non-stream corrective retry; on
success the final `answer` event SHALL carry the corrected text (the frontend re-renders
via the existing mismatch path). On correction failure or a still-off-anchor retry, the
original streamed result SHALL stand (fail-open, with an info-level log marker); the
stream path SHALL never raise for off-anchor. An on-anchor stream SHALL make no correction
call at all. (Shipped: `2686804`.)

#### Scenario: drifted stream final answer is replaced
- **GIVEN** a streamed answer that drifted off the anchor
- **WHEN** the stream finalizes
- **THEN** one non-stream corrective retry runs and the final answer event carries the
  corrected text

#### Scenario: correction failure keeps the streamed answer
- **GIVEN** a drifted streamed answer whose retry errors or still misses
- **WHEN** the stream completes
- **THEN** the original streamed answer is returned and no exception propagates

#### Scenario: on-anchor stream makes a single call
- **GIVEN** a streamed answer that is on-anchor
- **WHEN** the stream finalizes
- **THEN** no correction call is made

### Requirement: Unqualified multi-branch anchors SHALL get prompt-level guidance

The renderer SHALL inject a situational guidance block into the system prompt
(prompt_version `canonical-v2-prose-v16`) when the anchor is an org-level name with no
location qualifier (neither parenthesized nor co-occurring in the query) AND the
retrieved claims carry other-branch qualifiers: answer the user's question fully
(headquarters and all branches are legitimate material), attribute branch-specific facts
explicitly, never refuse and never interrogate, and naturally invite the user to name a
city — integrated into the answer, not as a boilerplate appendix; if the context already
shows a branch focus, answer for that branch without guiding. When the user named a city
or no branches are detected, nothing SHALL be injected and the prompt SHALL remain
byte-identical to the unguided form. (Shipped: `fdb3e26`.)

#### Scenario: guidance injected with detected branches
- **GIVEN** an org-level anchor and claims mentioning the 合肥 and 大湾区 branches
- **WHEN** the chat request is built
- **THEN** the system prompt carries the guidance block naming the branches

#### Scenario: no injection when the user named a city
- **GIVEN** the query names the org plus 深圳
- **WHEN** the chat request is built
- **THEN** no guidance block is injected (pin, don't guide)

#### Scenario: no injection without branch evidence
- **GIVEN** claims that mention the org only unqualified
- **WHEN** the chat request is built
- **THEN** the prompt is byte-identical to the unguided form

### Requirement: Org-level anchors SHALL get authority-seeking query views

Query planning SHALL append up to two authority-seeking view texts (`{subject} 百度百科`,
`{subject} 官网`) for the first displayed or soft-subject anchor whose name carries no
location qualifier, as `producer_kind="authority_seeking"` views carrying the request's
`soft_context_subject`, deduplicated against existing view texts, and appended last so
they never displace deterministic or term views. A user who already named the city SHALL
keep the un-broadened view set (pin, don't broaden); with no anchor, no authority views
SHALL be produced. (Shipped: `d8b0da5`.)

#### Scenario: authority views added for an org-level soft subject
- **GIVEN** a planning request with soft subject 国际先进技术应用推进中心 and an org-level
  query
- **WHEN** views are planned
- **THEN** the views include `国际先进技术应用推进中心 百度百科` and
  `国际先进技术应用推进中心 官网`, deduplicated

#### Scenario: no authority views when the city is named
- **GIVEN** anchor 国际先进技术应用推进中心（深圳） and a city-qualified query
- **WHEN** views are planned
- **THEN** no authority-seeking views are appended

#### Scenario: no anchor, no authority views
- **GIVEN** a query with no displayed entity names and no soft subject
- **WHEN** views are planned
- **THEN** no authority-seeking views are produced

### Requirement: The correction path SHALL fetch at most one authority reference page

On the correction path only, the renderer SHALL select at most one URL from the result's
`current_web` citations — preferring the first URL whose domain matches the anchor's
identity forms, else the first citation whose title (or snippet head) hits an identity
form — fetch it through the existing tiered page fetcher, and carry the text (truncated to
1200 chars) into the correction message as reference material. An anti-echo guard SHALL
reject fetched text that does not contain the anchor's org stem. Any failure (no candidate,
fetch error, empty text, guard rejection) SHALL degrade to no reference material
(fail-open); the renderer SHALL work unchanged when no page fetcher is configured.
(Shipped: `377f249`.)

#### Scenario: reference material fetched from a domain-matched URL
- **GIVEN** a citation whose URL domain matches the anchor
- **WHEN** the correction path builds its retry
- **THEN** the fetched text (≤1200 chars, containing the org stem) rides in the correction
  message

#### Scenario: off-anchor fetched text rejected by the anti-echo guard
- **GIVEN** a fetched page that does not contain the anchor's org stem (e.g. a lookalike's
  page)
- **WHEN** the guard runs
- **THEN** the material is dropped and the correction message carries no reference material

#### Scenario: fetch failure stays fail-open
- **GIVEN** a page fetcher that raises
- **WHEN** the correction path runs
- **THEN** the correction proceeds without reference material and no exception propagates

### Requirement: Degraded and off-anchor answers SHALL never refuse or interrogate

The lane SHALL answer from whatever is confirmed rather than refuse: the synthesis prompt's
degradation strategy SHALL NOT invite the user to provide more clues (prompt_version
v14→v15, then v16); degraded/deterministic-fallback texts SHALL be soft non-refusing
Chinese fallbacks; short refusal-shaped synthesized answers SHALL be rewritten into a
graceful non-refusing fallback; clarification responses SHALL remain untouched. Off-anchor
correction retry exhaustion SHALL fall back to the deterministic evidence list rather than
publish a wrong-entity synthesis. No new refusal or interrogation channel SHALL be added by
any slice of this change. (Shipped: `50c4f3a`; maintained by every phase-2 slice.)

#### Scenario: refusal-shaped synthesized answer is rewritten
- **GIVEN** a synthesized answer that is a short refusal (e.g. asking the user for more
  clues)
- **WHEN** the answer is post-processed
- **THEN** it is rewritten into a graceful non-refusing fallback

#### Scenario: deterministic fallback is non-refusing
- **GIVEN** evidence exists but synthesis fails or the correction exhausts
- **WHEN** the deterministic fallback is published
- **THEN** the text answers from the confirmed evidence without refusal or interrogation
  phrasing

#### Scenario: clarification responses are untouched
- **GIVEN** a genuine referent-clarification situation
- **WHEN** the clarification response is produced
- **THEN** the never-refuse rewriting does not alter it

### Requirement: Web lane results SHALL be exposed in the retrieval-process disclosure

The `retrieval_done` SSE event SHALL carry a backward-compatible `web_items` field listing
this turn's web lane results (`{title, url, source}`), URL-sanitized (http/https public
hosts only), de-duplicated, and capped at 10, with titles split from the web lane's
`标题：摘要` snippet packing, so the chat UI '查看检索过程' disclosure can show them and every
web-backed answer remains auditable. (Shipped: `a9b695b`.)

#### Scenario: web results listed in the disclosure
- **GIVEN** a turn with web lane results
- **WHEN** the `retrieval_done` event is emitted
- **THEN** it carries up to 10 sanitized, deduplicated `web_items` with title, url, and
  source host

## UNCHANGED Requirements
<!-- A–G query classification semantics; referent clarification/candidate (entity_id_hint)
     machinery; `_VALID_DOMAINS`; evidence shape and source traceability; commit-time anchor
     storage behavior; session-transition (topic_switch) semantics; company-entity identity
     behavior (legal-suffix truncations stay full-name forms). No schema/migration change.
     Official-site fetch injection on the hot path (original R3) remains deferred. -->
