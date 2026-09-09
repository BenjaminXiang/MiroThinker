# Acceptance: deepening-turn-anchor-carryover

## Acceptance criteria

1. **Trigger B (register §1, probe3 T2).** After a web-only org-level turn establishes
   `国际先进技术应用推进中心（深圳）`, the turn `这个中心的企业培育情况怎么样`:
   - the planning request carries `soft_context_subject = 国际先进技术应用推进中心（深圳）`;
   - the turn is NOT a clarification and NOT a topic switch;
   - the committed session still holds the soft subject afterwards.
2. **Trigger A (register §1, probe1 T3).** After the badcase pair, `它有哪些布局和进展`:
   - answers about the carried subject (planning request carries the subject) instead of
     clarifying or free-retrieving;
   - a vector-lane canonical record leaked into a prior turn's answer does not become the
     session anchor and does not bind this turn.
3. **Anchor-capture guard.** On soft-anchored turns that planned no canonical ids:
   - a canonical anchor whose name does not match the subject is dropped from the committed
     receipt (journal line present);
   - a matching canonical anchor and any web handle are kept;
   - turns with planned canonical ids are untouched.
4. **No regression in referent semantics.** Person pronouns over an organization-level soft
   subject still clarify; explicit named subjects still win over carried anchors; expansion
   requests (`还有哪些`) stay non-binding; set-referent and referent-history behavior
   unchanged (existing suites green).
5. **View-pin invariant.** Whenever `soft_context_subject` is present, every rewrite view
   text contains the subject (missing-append re-pin), and the journal marker fires when a
   re-pin was needed.
6. **Regression oracles.** miroflow-agent `tests/canonical_v2/` (excluding the known
   pre-existing baseline failure), admin-console adapter/referent-history/anchor-clarification
   suites, chat UI node tests all green; ruff clean on touched files.

## Honest scope

- Production deploy/smoke on 18188 is explicitly NOT in this slice's acceptance; the
  followup register §1 item stays open until a post-deploy probe confirms the fix live.
- Register §2 (prose truncation) and §3 (web-lane `unavailable` telemetry) remain open.
- The register's "related observation" (professor-record paragraph leak into synthesis
  beyond anchor capture) is reduced but not eliminated by the anchor-capture guard.
