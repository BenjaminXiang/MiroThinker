# Follow-up: person-pronoun follow-up over an org-anchored session answers from the (article-title) anchor instead of clarifying

Status: **Open — recorded only, not fixed this round** (user test-and-record mode,
2026-08-17).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: `2026-08-17-followup-subject-framed-one-level-up.md` (group 1 — same
article-title anchor root), `2026-08-17-bare-name-session-subject-collapse.md`
(group 2), register §3 (telemetry).

## Problem (user-reported, verbatim)

- T1 `介绍一下 国际先进技术应用推进中心（深圳）` → correct org-framed answer
  (prefixed form; group-1 mechanism working).
- T2 `他有哪些论文` → answer QUOTES THE ARTICLE TITLE AS AN INSTITUTION NAME:
  "公开信息中未找到"**河套深圳园区打造深港科技创新聚集地 - 香港中联办**"这一机构
  名称下的具体论文列表" + rephrasing suggestions. Never-refuse violated in spirit
  again (未找到 + 请改问), and the session anchor's display_name (a park-framed
  news headline) is surfaced to the user as if it were an entity name.

## Root cause (VERIFIED at gate level, 2026-08-17, worktree HEAD `4079bbf`)

Replay of the exact session shape (web-handle anchor with the article-title
display_name, soft subject stored):

- `referent_subject_domain('他有哪些论文')` → `professor` (person) ✓
- `_planning_displayed_ids(...)` → `()` ✓ (the domain-mismatch guard correctly
  declines to bind the org anchor)
- `_referent_clarification_needed(...)` → **False** ✗ — the gate's outer condition
  is `context.active_anchor is None`; ANY anchor present (even a domain-mismatched
  web handle) suppresses clarification.

So the turn neither clarifies nor binds → free retrieval. The answer session
(candidate fork of the committed answer session) still carries
`_SessionState.active_anchor` (the article-title web handle) into synthesis, and
the prose layer resolves `他` against it → the quoted-article-title answer.

Two independent holes:

1. **Clarification gate is anchor-blind to type**: it asks "is there an anchor?"
   not "is there a TYPE-COMPATIBLE anchor for this referent?" The domain guard
   exists only in `_planning_displayed_ids`, whose failure mode is "decline to
   bind", not "force clarification".
2. **Synthesis inherits the mismatched anchor**: the forked answer session keeps
   the prior anchor regardless of referent-type compatibility; the prose layer
   happily binds the pronoun to it.

Aggravator (group-1 root cause): the anchor name is an article TITLE, which makes
the failure user-visible and absurd (an institution literally named after a
headline). With a clean org-named anchor the same hole would answer "该中心的论文"
style nonsense — wrong but less visibly broken.

## Expected behavior

`他有哪些论文` over an org-anchored session (any anchor shape: web handle, soft
subject, canonical org) → referent clarification (person ≠ org), matching the
already-tested soft-subject shape (`test_person_pronoun_over_org_soft_subject_
still_clarifies`). The accepted change's guard test covered ONLY the no-anchor
soft-subject shape; the anchored-org shape was untested — third consecutive
session-shape gap in my acceptance matrix (after group-1 framing and group-2
bare-name).

## Proposed directions (NOT executed)

- Gate fix candidate (small, deterministic): the clarification condition for
  singular referents becomes "no anchor OR no type-compatible anchor" — i.e.,
  when `referent_subject_domain(query)` is not None and mismatches the anchor's
  domain (or the session is org-soft-anchored), clarify. Add the anchored-org
  person-pronoun case as RED test.
- Synthesis-side candidate: the answer session fork should not resolve a
  person-typed referent against an org anchor (type check at the referent
  resolution site in `knowledge_answer.py`).
- Root fix remains `contextual-query-interpretation`: typed interpretation
  ({subject, aspect, operation}) makes person-vs-org mismatches a first-class
  decision instead of scattered guards.

## Evidence

- Gate-level verification output (this file's section above; run 2026-08-17).
- User transcript verbatim (above). ("国先" in transcripts is the assistant/system
  name label, not a subject chip — clarified 2026-08-17.)
