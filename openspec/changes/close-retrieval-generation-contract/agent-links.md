# Agent Links: close-retrieval-generation-contract

## Execution workspace

- Verification contract: `.agents/runs/close-retrieval-generation-contract/verification-contract.md`
- Verification evidence: `.agents/runs/close-retrieval-generation-contract/verification.md`
- Slice A: `.agents/runs/close-retrieval-generation-contract/slices/a-oracle-red.md`
- Slice B: `.agents/runs/close-retrieval-generation-contract/slices/b-grounded-answer.md`
- Slice C: `.agents/runs/close-retrieval-generation-contract/slices/c-deterministic-paper-paths.md`
- Slice D: `.agents/runs/close-retrieval-generation-contract/slices/d-type4-hybrid.md`
- Slice E: `.agents/runs/close-retrieval-generation-contract/slices/e-type3-traversal.md`
- Slice F: `.agents/runs/close-retrieval-generation-contract/slices/f-index-parity.md`

## Portfolio

- `.agents/portfolio.md` — umbrella status and predecessor Candidate corrections.

## Ownership and sequencing

- OpenSpec owns behavior, acceptance, and RED/GREEN intent.
- One writer owns one active slice.
- Independent review owns Candidate-to-Accepted promotion.
- Only Slice A is Ready initially; a predecessor's Accepted decision is required before the next
  slice is made Ready.
- Internal checkpoints B0 -> B1 -> B2, C0 -> C1, and D0 -> D1 follow the same Candidate/review/
  immutable-hash/Accepted gate inside their top-level slice contracts.
- No session may use a later Specified slice as an Accepted dependency.
