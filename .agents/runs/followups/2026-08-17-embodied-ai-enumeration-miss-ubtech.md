# Follow-up: domain enumeration misses the flagship company (优必选 absent from 具身智能 company list)

Status: **Open — recorded only, attribution deferred** (user test-and-record mode,
2026-08-17). User grade: 回答还行 (quality-level defect, not a hard failure).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: round-1 findings P8 + `transcripts.md` group 7; legacy-line recall-gap
family (`fix-chat-retrieval-recall-gaps`, FM1a "6 absent entities = 67% of
misses"); golden-set backlog T19/T22/T23 (concept KEY coverage).

## Problem (verbatim in transcripts.md group 7)

- Query `深圳有哪些做具身智能的公司` → on-topic, structured, no drift/refusal —
  the first basically-usable answer of the day — but the list omits the flagship
  优必选 (UBTECH), named by the user as a basic expectation.
- List members are mostly newer/smaller startups (诺因 est. 2025, 知有无界, 赛博格…);
  content shape suggests web listicle sourcing dominating the enumeration.

## Established fact (same-day internal evidence, no new probe needed)

UBTECH IS in the serving pack: group 4 T1 (`优必选科技怎么样`) returned its
canonical profile correctly. Therefore the miss is an **enumeration-path /
ranking / fusion defect**, not data absence.

## Attribution questions parked for the chain audit

1. Vocabulary mismatch: does UBTECH's canonical profile text embed strongly for
   "具身智能", or does it speak mostly 人形机器人/教育机器人? (query-side term
   view exists — did it fire and where did it rank?)
2. Enumeration candidate window / merge rank: was UBTECH retrieved-but-buried
   (the widened `_ENUMERATION_CANDIDATE_WINDOW` machinery exists for exactly this
   class — did this query qualify for the widened window?)
3. Web-lane dominance: did web listicle results (fresher, keyword-exact 具身智能)
   crowd the canonical candidates in fusion?
4. Are the listed startups canonical records at all, or web-minted entities?

## Expected behavior (for the future fix contract)

A domain enumeration of Shenzhen embodied-AI companies must surface the canonical
flagships (优必选 at minimum; plausibly 越疆/普渡-class peers), with long-tail
startups as supplement — missing the flagship is an acceptance-line failure even
when the answer is otherwise well-formed.
