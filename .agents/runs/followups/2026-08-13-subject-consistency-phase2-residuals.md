# Follow-up register: subject-consistency phase 2 residuals

Status: Open (registered 2026-08-13, at deploy of branch `codex/canonical-v2-s12a-ready`, HEAD `45d39dd`).
§1 CLOSED 2026-08-17: fixed by `openspec/changes/deepening-turn-anchor-carryover/`
(commits `438300a`+`0e2d247`; deployed to 18188 and probed —
`.agents/runs/deepening-turn-anchor-carryover/verification.md` § Production smoke,
evidence `prod_deepen_t*.sse` / `prod_pronoun_t*.sse`: both triggers on-subject,
no substitution, no clarification). Residual observation retained: on anchor-path
deepening turns the rewrite views stay unpinned and the subject gate can filter the
web lane to zero — fold into the §3 telemetry follow-up or a gate-recall tune.
Context: phase-2 branch (Tasks 1-11 + final-review fixes C1/I1) closed the canonical badcase pair and the stream-correction crash. This register collects everything deliberately NOT fixed in that branch, with evidence pointers. Evidence files live in `.agents/runs/followup-subject-consistency/evidence/` (uncommitted).

## 1. Deepening-turn anchor loss at plan/referent level (highest priority)

Deepening wordings beyond the canonical badcase pair still lose the entity anchor
upstream of every phase-2 mechanism: generated views come back unpinned (generic
topic views such as `具身智能布局进展`, `企业培育中心 运营模式`), retrieval goes
generic/junk, and a vector-lane record is captured as the answer subject. The
soft-subject injection (Task 10), mention test (Task 11), and stream correction
(Task 4/C1) never engage because there is no anchor left to enforce.

- Trigger A: T3 `它有哪些布局和进展` after the canonical badcase pair
  (`介绍一下 国际先进技术应用推进中心（深圳）` → `有没有更详细的信息`).
  Answer subject becomes `张天尧，哈尔滨工业大学（深圳）副教授`; 10/10 web_items
  off-topic. Evidence: `phase2_fix_probe1_badcase_t3.sse`.
- Trigger B: T2 `这个中心的企业培育情况怎么样` after a clean on-subject T1.
  Answer subject becomes `深圳前海微众银行`, truncated mid-sentence
  (`…实现全线上、无。`); 8/8 web_items junk (广州/漕河泾/新湖南).
  Evidence: `phase2_fix_probe3_deepen_t2.sse`.
- Pre-existing, NOT caused by the C1/I1 fixes: reproduced on pre-fix production
  (6af3715) — trigger B byte-identical (md5 `141ee7a1…`), trigger A same class
  with identical unpinned views and identical junk web_items.
  Evidence: `phase2_prefix_prod_probe1_r2_t3.sse`, `phase2_prefix_prod_probe3_t2.sse`.

Proposed direction: referent/anchor carry-over for org-level sessions on deepening
turns (plan-level subject binding when the turn adds no new entity), plus a
retrieval-quality tripwire when all generated views are unpinned in a session that
previously had a pinned anchor. Needs OpenSpec change + new slice; treat as the
top candidate for the next subject-consistency phase.

Related observation (same noise family): the fix-round production unqualified smoke
answer carried a professor-record leak — a final paragraph naming `李成睿，
哈尔滨工业大学（深圳）` that the model explicitly disclaimed as unrelated
(`phase2_final_prod_unqualified_t1.sse`). Vector-lane records can leak into synthesis
even without full subject capture; consider them together when scoping the next phase.

## 2. Prose truncation reaching the client

Trigger B's answer ends mid-sentence (`…实现全线上、无。`) yet was served as
`answer_style: llm_synthesized`. `_reject_truncated_prose_finish_reason` is
supposed to catch `finish_reason=length`; investigate whether the provider
omitted the flag or the stream decoder missed it. Same SSE as trigger B above.

## 3. Web-lane `unavailable` episodes have no logged cause

Production journal 2026-08-13 14:15-14:17: web lane reported `unavailable`
(0 web_items) with no serper/quota/rate-limit lines; recovered ~14:18. On pre-fix
code this degradation produced the C1 crash live (journal:
`canonical v2 stream turn failed: prose stream differs from its final answer`,
`knowledge_answer.py:2227`). Post-fix the correction path holds instead of
erroring, but the outage itself needs telemetry (provider, reason, duration).
Evidence: `phase2_prefix_prod_probe1_t1.sse` / `_t2.sse` + journal excerpt in the
retest report (`.superpowers/sdd/2026-08-12-web-answer-subject-consistency-phase2/`, fix-round notes).

## 4. Carried from the phase-2 branch final review (convert-to-followup)

- `_web_result_hits_bound_entity` is no longer called from production code
  (unit-tested only) — decide removal vs re-wiring.
- The lane view cap (4) can squeeze out Task-6 authority-seeking views on
  rewrite-heavy multi-intent queries.
- Fallback content quality (deterministic/template mode B answers) — recorded in
  the Task-8A sessions, out of phase scope.
- Selection-less stream correction (plain-str corrected wire, no selection block)
  still raises at the published-vs-final guard — pre-existing dead sub-path;
  production prompts demand the selection block (re-review M1).
- Shared-alias lookalikes (e.g. `南开国际先进研究院`) can still pass the
  identity-form gate (carried from `2026-08-11-web-lane-subject-consistency.md`).
- Official-site fetch injection (original R3) remains deferred.
