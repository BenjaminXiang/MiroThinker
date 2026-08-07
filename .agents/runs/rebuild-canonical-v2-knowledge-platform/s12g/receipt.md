# S12G Candidate Receipt

## Status

Candidate — not Accepted and not authorized for Cutover.

## Scope delivered

- Responsive framework-free `国先检索助手` behavior across the approved 13 viewport matrix.
- IME-safe input, streaming scroll intent, accessible return-to-latest, and responsive branding.
- Progressive safe `answer_chunk` delivery before the complete final `answer` and terminal `done`.
- Public SSE/DOM structure protection, retry isolation, and server-observed pre-commit cancellation.
- Explicit Grid row placement for all four shell regions, preventing hidden-demo auto-placement drift.
- Compatibility profiles `gemma4.local` and `ark.local` now use
  `https://star.sustech.edu.cn/service/model/qwen36/v1` and `qwen3.6-35b-a3b`.

## Runtime provenance

- Worktree: `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation`
- Branch: `codex/canonical-v2-s12a-ready`
- Candidate URL: `http://127.0.0.1:18188/chat`
- Background wrapper PID at verification: `3484842`
- Uvicorn PID at verification: `3484845`
- Health: HTTP 200, `{"status":"ok"}`
- Candidate release: `candidate-s12f-20260801-v1`
- Serving pack: `/var/tmp/mirothinker-canonical-v2-s12f/serving-pack`

## Verification evidence

- Admin chat HTTP/UI: `310 passed in 142.48s`.
- Native JavaScript behavior: `80 passed, 0 failed`.
- Changed-file Ruff: passed.
- Strict OpenSpec validation: passed.
- `git diff --check`: passed.
- Self-test browser artifact:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts/20260806T083020.138878Z-94d5afd4`
  — passed, no defect codes; all positive and negative oracle fixtures behaved as expected.
- Production browser artifact:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/artifacts/20260806T083022.950988Z-cb010abd`
  — passed, no defect codes; one HTTP 200 request; 273 events with 266 progressive chunks, one
  final answer, and one terminal done; chunks reconstructed the final answer exactly; 13 viewports
  passed.

## Boundaries and remaining gates

- Answer semantics and retrieval quality were intentionally frozen and excluded from this UI/transport
  closeout. Recent uncommitted content-normalizer changes were not loaded into the verified runtime and
  are not certified by this receipt.
- No physical iPhone or Android smoke was run; desktop Chromium emulation is not native validation.
- Task 12.5 remains open for direct user acceptance.
- Task 12.6 remains open; no promotion, Cutover, archive, cleanup, or active-pointer change occurred.
- Task 9 provenance was not asserted: both
  `task9_provenance_certified` and `evidence_eligible_without_task9_receipt` remain `false`.
