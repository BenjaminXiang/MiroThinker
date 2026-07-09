# Review — layer-d-multi-turn-context, task group 1 (eval runner + fixtures)

- **Date:** 2026-07-09
- **Slice:** tasks 1.2–1.3 (runner + synthesized dialogs); task 1.4 (RED run) blocked on
  backend availability — explicitly out of the implementer's hands per handoff.
- **Builder:** Codex. **Reviewer:** Claude.
- **Decision: Accept (with two reviewer fixes applied inline)**

## Checked against the handoff

| Criterion | Verdict |
|---|---|
| Session stickiness (per-group cookie, fresh per group) | ✓ `_run_group` builds one `httpx.Client(cookies={miroflow_chat_session: …})` per group; uuid suffix per group |
| turn_group grouping, heads first | ✓ `_ordered_group_turns`; S5 3-turn chain keeps yaml follow-up order |
| Proxy hygiene | ✓ `_prepare_loopback_env` unsets 8 vars + sets no_proxy (also honors project memory); `trust_env=False` on the client |
| Scoring parity with eval_full_testset | ✓ same `_TERM_RE`/`_STOP`/`_hit` semantics |
| Routing assertions | ✓ `expected_query_type` (str or list) + `expected_set_derived` membership check against prior displayed IDs |
| Prior-set tracking | ✓ `_displayed_ids_by_domain` from citations + payload list keys; updates each turn → chaining (S5-F2 checks against F1's companies) |
| No production-code edits | ✓ diff limited to scripts/ + new fixture; test_cases.yaml untouched |
| Fixture golds not invented | ✓ heads reuse test_cases.yaml golden entities (qid27/3/24); traversal follow-ups routing-assertion-only as instructed |
| Error rows / failure notes | ✓ per-turn try/except → error row; per-case failure_notes; summary with per-assertion tallies |

## Reviewer fixes applied (Claude, inline)

1. `_collect_source_like_ids`: restricted to entity-ID-shaped strings
   (PROF/COMP/PAPER/PAT prefixes) and skips `*url*` keys — the original collected any
   string under source-ish keys (`source_url`, `source_label`), which would false-fail
   `set_derived` on every existing payload shape. Verified by direct invocation.
2. S3-F / S4-F `expected_query_type` widened to
   `[G_ambiguous_clarification, C_cross_domain_clarification]` — spec D2 says reuse an
   existing clarification shape; both literals exist in chat.py.

## Scored-case count vs the contract line (clarification recorded)

Deliverable has **18 scored follow-ups** (8 yaml + 10 synthesized — S5 contributes 2 turns,
S6 split into 4 chip rows). The user-approved accept line was "≥12/14". Mapping that
preserves the approved line exactly:

- **Chip matrix = the 4 S6 rows** — must be **fully green** (that clause was separate in
  the approved GREEN).
- **The other 14 scored cases** (8 yaml + S1-F, S2-F, S3-F, S4-F, S5-F1, S5-F2) — **≥12/14**.

Verification contract updated to state this mapping.

## Follow-ups (non-blocking)

- `set_derived` remains a generic membership check; tighten to the mapping payload shape
  once task group 4 defines it (noted by builder, agreed).
- Task 1.4 (RED baseline) requires the deployed backend on :18188 — owner: user (env
  credentials live only in their shell; eval_env.sh harvests from the running process).
