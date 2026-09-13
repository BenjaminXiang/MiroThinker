# Tasks: harden-deterministic-subject-layer

## 3.4 Headline anchor guard (P1 root — first slice)

- [x] 3.4.1 `is_headline_shaped_name` detector (source-suffix / event-verb /
       sentence-scale) + unit REDs on the G1 verbatim headline and real
       entity names as negatives.
- [x] 3.4.2 Sanitize extension: headline-shaped WEB anchors dropped;
       previous anchor retained when present; else soft subject carries.
       Unit REDs: G1-form session (headline anchor does not survive commit),
       real-company web anchor survives.

## 3.3 Expansion base = session subject (P6)

- [x] 3.3.1 Expansion-family turns bind the session subject into planning
       inputs (displayed ids / soft subject) exactly as deepening turns;
       RED: G5-form session — expansion turn carries 优必选 as base, answer
       subject not 微众银行.

## 3.1 Echo-guard relaxation (P3)

- [x] 3.1.1 Bare entity-name query = subject statement; no clarification
       loop. RED from the P3 verbatim (bare name opening → follow-up).

## 3.2 Type-aware referent handling (P4)

- [x] 3.2.1 Personal referent over org-anchored session → typed
       clarification or person-scoped answer; synthesis subject-type check.
       RED from G3 verbatim (他有哪些论文).
- [x] 3.2.2 Residual on the deployment line (2026-09-13): port of the
       personal-pronoun × anchor-type guard (`513858e0`, branch
       data/p4-serving-pack-rebuild, never merged) + interpreter check ③
       symmetric typed-referent / anchor-domain rejection. Under the
       current pack T1 anchors a canonical company, so 3.2.1's no-anchor
       branch no longer engaged and G3 T2 free-retrieved junk papers.
       Evidence: serving worktree `replay-g3-fix-20260913/` (T2
       clarification_only, 1.0 s) and full gate `replay-full-20260913/`
       — 6/7 sessions, G3 both turns PASS; unit RED→GREEN (5 failing
       before, focused suites 42/188 green); note
       `.agents/runs/harden-deterministic-subject-layer/verification-3.2.2.md`
       in the serving worktree.

## 3.5 / 3.6 Close

- [x] 3.5 P7 verification note (G6 stands; product contract recorded).
- [x] 3.6 Full replay suite green-run vs Phase 2 outcomes; R1 merge prep
      (P1+P2+P3 package → release/customer-test) per Epic.
