# S9J Public Answer Integrity Correction Dependency Audit

## Status

Accepted dependency audit on `2026-07-21`. S9J changes no OpenSpec task checkbox and leaves the
formal ledger at `65/80`.

## Accepted dependencies

- Accepted S9I receipt SHA-256:
  `658c12f519a55d3e5ca02eea7b2a5deba36d47954fe04d9233934a434e0ac366`.
- Historical Accepted S11A receipt SHA-256:
  `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`.
- S11A's historical service and owner hashes remain immutable evidence. S9J is a separate successor
  correction and does not rewrite or call its new hashes the historical S11A acceptance bytes.
- The S11B candidate fixture is an affected in-progress consumer owner, not an Accepted dependency.
  S11B may resume only after it binds the final Accepted S9J receipt and corrected chat hashes.

## Owned behavior and files

S9J owns the answer-composition correction in `knowledge_answer.py`, its focused answer/multi-turn
owners, the corrected recorded S11A chat service/owner, and these public-copy anchors in the built-in
chat page:

- typed material-gap labels;
- bounded public continuation labels;
- safe rendering of the server answer and trace.

The same `chat.html` also contains a co-resident `preview-p1` overlay for manifest-derived real
questions, verified relationships, current-Web evidence cards, and display sanitization. Those
preview behaviors remain independently owned by `test_canonical_v2_real_preview_ui.py` and
`preview-p1/*`; S9J and S11B do not adopt their function names as formal acceptance oracles.

## Safety and state boundaries

- No schema, migration, provider policy, evidence binding, release/index manifest, active pointer,
  original PostgreSQL/Milvus/forensic source, or production-like state changes.
- The fresh browser replay used the Accepted S2B restore member read-only. Its SQLite SHA-256 stayed
  `7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce`, size `20,267,008`, mode
  `0440`, with no WAL/SHM/journal sidecar.
- Existing preview listeners on `18188` and `18189` remained available. The fresh `18190` verifier
  was stopped after evidence capture.
- No Commit, Push, PR, Archive, promotion, or Cutover occurred.

## Review conclusion

The initial independent review found one Important escaped branch: `suppress_claims` retained a
typed material gap but omitted its public sentence. The systemic repair covered blocking ambiguity,
unresolved Web traversal, and selector degradation, then froze exact no-duplicate behavior and the
base clarification/handle-resolution prompts. The final independent spec review is
`Critical=0 / Important=0 / Minor=0 / YAGNI=0`; final code/test-integrity disposition is recorded in
the S9J verification receipt.
