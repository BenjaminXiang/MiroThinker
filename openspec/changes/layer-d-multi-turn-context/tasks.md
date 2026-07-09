# Tasks: layer-d-multi-turn-context

> Slice order per grilling: eval runner first (RED measurable), then routing+resolution,
> traversal, narrowing, anchors — each group independently reviewable/acceptable.
> Anti-half-finished rule applies: do not start a group until the previous is Accepted or
> explicitly abandoned.

## 1. Verification contract + RED baseline (eval-first)

- [ ] 1.1 Create `.agents/runs/layer-d-multi-turn-context/verification-contract.md`: RED =
      archived multi-turn baseline run; GREEN = ≥12/14 multi-turn pass AND zero single-turn
      regression (19-case set) AND chip routing matrix green; Superpowers mode = eval-first
      (unit tests supplementary)
- [ ] 1.2 Build session-sticky runner `apps/admin-console/scripts/eval_multi_turn.py`:
      group `test_cases.yaml` by `turn_group`, replay each conversation over HTTP with a
      fixed `miroflow_chat_session` cookie, score per-turn required/forbidden/coverage +
      routing assertions (query_type / structured_payload membership); proxy vars unset
- [ ] 1.3 Author the ~6 synthesized golden dialogs (fixture extension or sibling YAML):
      R2×O3 traversal (上述教授参与的企业), bare 他们, list-then-他 clarification,
      empty-set/domain-mismatch clarification, 3-turn chain (教授→企业→这些公司的专利),
      chip routing matrix rows
- [ ] 1.4 Run the runner against the live backend on current code; archive the RED baseline
      JSON under `.agents/runs/layer-d-multi-turn-context/` and record per-case failure
      modes in the run notes

## 2. Displayed-set semantics + set coreference resolution

- [ ] 2.1 Narrow `result_ids_by_domain` (chat_context.py) to displayed entities (answer
      list + citations); remove `retrieval_evidence` harvesting; update
      `_record_and_return` call sites accordingly
- [ ] 2.2 Add set-word detection to chat_context.py: explicit set referents
      (上述/这些/他们 + domain-worded 上述教授/这些公司), returning (referent-kind, domain)
- [ ] 2.3 Implement empty-set / domain-mismatch clarification response (no silent fallback,
      no global re-search); reuse existing clarification response shape — no new A-G class
- [ ] 2.4 Unit tests: displayed-only capture, set-word detection table, clarification
      paths (`CHAT_LLM_SYNTHESIS=off CHAT_QUERY_CLASSIFIER=off`)

## 3. Hybrid routing

- [x] 3.1 Rule layer: operation splitter (narrow vs cross-domain traverse) over set-word
      queries; every chip string from `_suggested_followups` must deterministically match —
      add the chip routing-matrix unit test enumerating chip strings → expected path
- [ ] 3.2 Classifier: add `referent: "set"|"entity"` output field + 2-3 set examples to
      `_CLASSIFIER_SYSTEM`; parser tolerates absent field; wire `C + referent=set` to the
      set traversal path, `C + referent=entity` unchanged
- [ ] 3.3 Precedence wiring in the dispatch: explicit set-word > singular pronoun >
      classifier referent > status quo; unit tests for precedence and for
      `CHAT_QUERY_CLASSIFIER=off` (chips still route)

## 4. Set cross-domain traversal

- [x] 4.1 Implement `_batch_related_objects(source_domain, source_ids, target_domain,
      per_source_limit=5)` looping retrieval-service `get_related_objects` (NOT the
      domains.py HTTP variant); assemble member-target mapping; truncation declared
- [x] 4.2 Deterministic renderer: target-centric projection (default; dedup + back-links +
      role_type + link_status labels) and member-centric projection (分别); mandatory
      coverage statement; full mapping into `structured_payload`
- [x] 4.3 Wire traversal answers to update `last_result_set` with displayed output entities
      (chaining); unit tests: projection rendering, coverage statement, chaining,
      payload completeness
- [ ] 4.4 Synthesis-on path: rendered mapping feeds existing LLM phrasing lane; verify
      citations/validation unaffected

## 5. Narrowing mechanisms

- [x] 5.1 Chip-predicate table: region/institution, year/recency, grant status, applicant
      type — per-domain field mapping; per-member deterministic evaluation on rows fetched
      by ID; per-member basis in answer; 信息缺失 distinguished from unsatisfied
- [x] 5.2 Open-predicate LLM lane: per-member structured verdict
      `{member_id, verdict, evidence_field, quote}` on deterministically fetched full rows;
      verdicts audit-logged in `structured_payload`; degradation to labeled
      topic-intersection when `CHAT_LLM_SYNTHESIS=off`
- [x] 5.3 Mechanism selector (deterministic order: chip table → open-LLM → topic) replacing
      the single-mechanism `_handle_d_narrowing` body; topic narrowing preserved unchanged;
      narrowing answers update the result set (chaining)
- [x] 5.4 Unit tests: predicate table per domain, selector order, unknown-vs-unsatisfied,
      degradation labeling

## 6. Anchor discipline

- [ ] 6.1 Stop pushing list citations onto the `entities` anchor stack; anchors only from
      profile/disambiguation/explicit-naming answers
- [ ] 6.2 Singular pronoun + no anchor + live same-domain set → deterministic clarification
      listing members; profile-then-他 behavior unchanged; unit tests for both

## 7. GREEN + acceptance

- [ ] 7.1 Re-run `eval_multi_turn.py` (full-on env): require ≥12/14 multi-turn pass; archive
      GREEN artifact next to the RED baseline
- [ ] 7.2 Re-run single-turn `eval_full_testset.py`: zero regression on the 19-case set
      (esp. qid14/17); archive
- [ ] 7.3 Full unit-test suite + chip routing matrix green; record exact commands + output
      in the run notes
- [ ] 7.4 Claude review Accept/Revise/Reject against this change's specs + ADR-011;
      update `.agents/reviews/` and the portfolio
