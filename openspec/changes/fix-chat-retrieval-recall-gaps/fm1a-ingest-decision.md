# FM1a Ingest Decision Gate (not implemented this round)

> Per design §3.3. This is a decision record, not an implementation. The recall change does NOT
> carry ingest responsibility; this gates a separate data-pipeline workstream.

## Why a gate, not silence
6/19 missed entities are simply absent from `company` (67% of misses — diagnosis
`diagnosis-baseline.md`). The measured no-web recall ceiling is 58% (11/19); even with a fixed
Serper, web can only rescue a subset of the 6 absent entities. Data coverage is a multiplicative
factor on recall, not salvageable by retrieval logic. So this round does not implement ingest,
but records the gate so the later workstream has a clear start.

## Absent entities (quantified)
- #4 (酒店送餐机器人): 云迹科技, 九号机器人, 擎朗智能 (3 of 5 required absent).
- #13 (PCB打板): 嘉立创.
- #19 (cross-filter professor): 许晋诚, 陈功 (block FM3 routing verification too).

## Per-entity block reason
- 云迹/九号/擎朗/嘉立创: 0 rows in `company` (not ingested).
- 许晋诚/陈功: absent → FM3 routing fix is data-blocked (routing-reachable, but recall empty).

## Expected ceiling after ingest
From 58% (measured, no-web) to a theoretical value needing re-measure post-ingest. Web-augment
(`add-web-augment`), if Serper is fixed, adds on top — but web rescue and ingest are independent
paths to the same entities, so the gains are not simply additive.

## Ownership
Data-pipeline workstream, decoupled from retrieval-logic. A new OpenSpec change should be
opened when ingest is prioritized; this file is its starting point, not its substitute.
