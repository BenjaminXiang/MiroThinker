# Tasks: enforce-never-refuse-contracts

## 2.1 Wording contracts

- [x] 2.1.1 Rewrite `_soft_fallback_answer_text` to the never-refuse contract
       form (subject-first, confirmed facts, named coverage gap, actionable
       step); unit tests from verbatim P2 transcripts (G2 forbidden family).
- [x] 2.1.2 Deflection guard: detect external-database recommendation
       patterns with zero patent evidence → rewrite to gap-naming form;
       unit tests from the G4 verbatim form (建议访问国家知识产权局).
- [x] 2.1.3 Subject-carrying: rewritten texts always name the anchor or the
       query's named subject (no "这一机构名称"-family entity-less forms in
       rewritten output).

## 2.2 Lane-failure semantics

- [x] 2.2.1 Detect web-lane-unavailable at the answer boundary from evidence
       traces (all provider attempts errored/timed out, zero web results);
       negative world claims over such turns are rewritten to
       网络检索暂不可用 + retained evidence.
- [x] 2.2.2 Synthesis prompt contract lines added to the prose renderer.

## Verification (per .agents/runs/enforce-never-refuse-contracts/)

- [x] V1 Replay with fault injection (invalid Bocha key): web-only subject
      turns answer 网络检索暂不可用, no 未找到该机构; trace token matches.
- [x] V2 Full seven-session replay: stable lines unchanged (G1/G3/G5 still
      RED — their roots are Phase 3/4), G2/G6 PASS held, G4 wording
      assertions improved (deflection banned).
