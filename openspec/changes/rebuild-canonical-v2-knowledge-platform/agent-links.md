# Agent and Slice Links

## Ownership

- OpenSpec owns behavior, scope, acceptance, and verification intent.
- Each slice has one active writer.
- Independent review owns Candidate-to-Accepted promotion.
- No subagent or parallel writer is authorized by this artifact.

## Slice dependency chain

1. S1 database-target safety — first Ready slice after spec/user approval.
2. S2 read-only inventory/baseline/threshold freeze — depends on S1 Accepted.
3. S3 interface/database foundation — depends on S2 Accepted.
4. S4 immutable landing — depends on S3 Accepted.
5. S5 assertions/identity/fusion — depends on S4 Accepted.
6. S6 typed domains/relationships/eligibility — depends on S5 Accepted.
7. S7 candidate release/Milvus — depends on S6 Accepted.
8. S8 query orchestration — depends on S7 Accepted.
9. S9 grounded answer/session — depends on S8 Accepted.
10. S10 gap/operations — depends on S9 Accepted.
11. S11 consumer migration/legacy removal — depends on S10 Accepted.
12. S12 full isolated candidate acceptance — depends on S11 Accepted.

Later slices remain Specified until the predecessor is Accepted. A slice may be decomposed further
when its contract remains independently testable, reviewable, and reversible.
