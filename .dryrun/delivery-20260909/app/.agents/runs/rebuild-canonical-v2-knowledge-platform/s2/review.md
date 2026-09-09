# S2 Review: Corpus, Baseline, and Acceptance Thresholds

## Status

Explicit user approval was recorded at `2026-07-11T15:10:32Z`. Task 2.5 and S2 tasks 2.1–2.5 are
Accepted. Task 2.6/S2B backup-and-restore verification remains a separate mandatory gate before
task 3.2 or any Canonical V2/landing write.

## Frozen evidence

- Source inventory: 48 source/family records, SHA-256
  `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`.
- Regression corpus: 40 cases (25 workbook + 15 PRD), SHA-256
  `f2656e8c2f0803452af18fa0d478eec1b1e1b94eaa97ef48d06d0828401297da`.
- Challenge corpus: 12 cases (one user-reviewed badcase + 11 controlled variations), SHA-256
  `ee46c677af668131fb8da568fabd6386659f3287d0bdb0fd740f7069497f6f9f`.
- Corpus manifest SHA-256:
  `dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088`.
- Baseline report SHA-256:
  `c31b1c240ecc96661cf0b6c3057f02e631f34fcfae7356bb6f827cb5695352a1`.
- Threshold candidate SHA-256:
  `15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0`.
- Accepted threshold registry SHA-256:
  `bce20bf959ba8a2b0997fe2bc1d71e5f727b857a2e374990cf76085c1e13b5cc`.

## Ground-truth policy

The workbook's answers and key points are user-confirmed, case-specific reference ground truth with
row provenance. They are valuable expected responses for those 25 questions, but are not a general
answer template or the sole product oracle. Workbook row 12 explicitly marks its old answer
inaccurate; that response is preserved as a known bad response, and its key points define the
correction constraint.

PRD-derived and controlled-variation cases are accepted as observable behavior contracts under this
ground-truth policy. They do not contain generated factual answers and are not silently promoted to
factual gold. The corpus manifest retains its generation-time Candidate state and immutable hash;
this review is the acceptance record rather than a rewrite of the frozen corpus bytes.

## Baseline interpretation

- Current measured: deterministic A-G fallback intent classification is `100/100` on the committed
  100-case fixture. This does not measure the provider-backed classifier, retrieval, rewriting, or
  answers.
- Current unavailable: retrieval reach, Recall@K, Precision@K/rank, grounded answer support,
  Universal Web, multi-turn, latency, provider calls, and cost. The recovery public schemas are empty
  and no verified Milvus copy or accepted canonical release exists.
- Legacy only: recall `30/41`, Paper recall `16/17`, reviewed answer accuracy `10/19`, multi-turn
  `1/18`, and retrieval p95 `5.7089s`. These values used changed V042/index/corpus/scorer/provider
  conditions and cannot be compared directly with Canonical V2.
- Legacy precision is not a number: its artifact captured candidates, its four-case label file is a
  scaffold, and zero listed false positives does not establish Precision@K or rank quality.

## Threshold candidate

The registry contains 83 independently addressable metrics:

- 24 PRD minima, unchanged and already fixed by their authoritative source;
- 25 user-confirmed/OpenSpec hard invariants, including complete backup/restore, zero wrong identity,
  zero unsupported material claims, zero protected-slot loss, exact release/index parity, Universal
  Web invocation behavior, and query-time identity read-only behavior;
- 34 calibrated product-effect gates approved against the exact Candidate hash above.

The calibrated values are:

| Family | Proposed gate |
|---|---|
| Intent taxonomy | PRD overall accuracy `>= 0.90`; each A-G class independently `>= 0.80` |
| Exact retrieval, each domain | Recall@5 `>= 0.95`; Precision@1 `>= 0.95` |
| Semantic retrieval, each domain | Recall@10 `>= 0.80`; NDCG@10 `>= 0.80` |
| Structured filters, each domain | Result-set recall `>= 0.90`; protected-constraint loss remains `0` |
| Required relationship catalog | Reviewed supported/absent/insufficient-evidence scenario accounting `= 100%` |
| Supported relationship paths | Recall@10 `>= 0.80`; returned-edge precision `>= 0.90`; wrong identity remains `0` |
| Workbook reference fidelity | Key-point coverage `>= 0.80`, evaluated semantically rather than by verbatim overlap |
| Grounded answer completeness | `>= 0.80` of evidence-supported material parts; unsupported material claims remain `0` |
| LLM evaluation | Human agreement `>= 0.80` on at least 50 stratified double-reviewed samples before scale use |
| Multi-turn | Reference accuracy `>= 0.90`; topic-switch accuracy `>= 0.95`; undisplayed-set use remains `0` |
| Web quality | Web candidate Top-5 relevance `>= 0.80`; required invocation/provenance hard gates remain `100%` |
| Complex completion | Progress-signal coverage `= 100%`; p95 full answer `<= 60s`; PRD TTFT hard ceiling `<= 25s` |
| Provider/cost safety | attempts `<= 12` ordinary / `<= 20` complex; after the initial accepted real-provider baseline, p95 cost regression `<= 1.20x` on identical versions |

These are population/path evaluation gates, not per-object global readiness gates. Ordinary missing
enrichment does not hide valid exact or relationship results; it lowers applicable ranking,
discloses limitations, and creates enrichment gaps. Every domain/path fails independently, so one
strong dimension cannot mask another weak one.

## Evaluation population materialization

The frozen seed/challenge set currently has 52 cases. Multi-domain counting gives Company 30,
Professor 12, Patent 11, and Paper 7 cases. It establishes required families but does not yet satisfy
every final metric's sample minimum, especially the PRD Top-5 requirement of at least 50 reviewed
queries for Company/Paper/Patent.

S2 therefore freezes both the existing seed corpus and the population-construction contract; it
does not claim that all final labels already exist. Before an owning metric can pass, tasks 6.1,
8.1, and 9.1 must materialize versioned, hashed, human-reviewed query banks selected without seeing
candidate outputs. Required minima include 50 relevance queries per domain, 30 exact and 30 semantic
queries per domain, 20 structured-filter queries per domain, 20 cases per supported relationship
family/direction, 30 multi-turn cases, and 50 LLM-judge calibration samples. A missing population
blocks only its owning metric/slice and cannot be treated as zero or silently waived. New banks extend
the acceptance package without rewriting the frozen 52 seed cases.

## Evaluation-system decision

Do not make a separate goal merely to preserve the old evaluator. S8–S9 must implement the frozen
metric contract through interface/trace scenarios, complete reviewed relevance labels, real
Postgres/index adapters, human-calibrated LLM judges, and real-provider acceptance. Reuse a legacy
component only if it emits the required evidence without changing the oracle. Otherwise replace it.

The evaluator itself is accepted only when it can:

- reproduce the frozen corpus/hash and per-domain/path populations;
- score recall and precision independently with complete reviewed labels;
- preserve protected constraints and trace query/rewrite/lane/release/evidence/provider versions;
- calibrate LLM judge output against human double review before scale use;
- report unavailable instead of zero and prohibit cross-population comparisons;
- record latency, provider calls, monetary cost, and degradation paths.

## Approval record

The approval record was captured at `2026-07-11T15:10:32Z` from the user's statement: “批准 Task 2.5
阈值候选、corpus ground-truth policy，并接受 S2 tasks 2.1–2.5”. The accepted registry records this
statement and refuses generation if the reviewed Candidate content hash changes.

- [x] Approve the 34 calibrated values above and threshold registry
  `15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0`.
- [x] Approve the regression/challenge Candidate with the ground-truth policy above.
- [x] Accept S2 tasks 2.1–2.5 as the baseline/threshold checkpoint, while keeping task 2.6/S2B and
  every rebuild write blocked.
