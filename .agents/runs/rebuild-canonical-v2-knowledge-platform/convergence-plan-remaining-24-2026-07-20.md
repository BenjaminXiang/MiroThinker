# Canonical V2 Remaining-24 Convergence Plan — 2026-07-20

## Objective

Implement the remaining OpenSpec work in dependency order and expose a runnable Canonical V2 system
before requesting final user acceptance. Reuse already-Accepted mechanics; do not reimplement them or
add theoretical gates. Required checks plus zero open Critical/Important findings are sufficient.
Minor/YAGNI findings are recorded and do not block.

Current formal ledger: `70/80`. The persistent goal remains active. No Commit, Push, PR, Cutover,
original-source write, production-like promotion, archive, or destructive cleanup is authorized.

## Dependency path and minimum slices

### 1. S8 runtime closure

1. S8R4 — Accepted Paper-to-Professor inverse attribution traversal.
2. S8R5 — Accepted Patent-to-Company inverse applicant traversal, completing the four catalog-supported
   public relationship directions without implementing insufficient-evidence directions as facts.
3. S8C — Accepted aggregate real-read closure over the already-Accepted planner, seven-lane mechanics,
   physical/release-bound adapters, fusion/Web-handle lifecycle, sufficiency/enumeration, and bounded
   supplemental retrieval. Tasks 8.3, 8.5, and 8.7 are closed at `59/80`.
4. Task 8.1 calibration and Task 8.8 claim-level acceptance remain prepared but cannot be accepted
   until S2C/Task 2.8 supplies human-reviewed oracle authority.

### 2. S9 implementation closure — Accepted

S9I closes Tasks 9.2, 9.4, and 9.6 at `62/80` over the existing `knowledge_answer.py` mechanics:

- exact full claim binding and suppression of ungrounded proposal prose;
- evidence-relevant assessment outcome/conclusion validation and visible selector degradation;
- typed session directives instead of wording heuristics, plus safety-guidance rendering;
- one real `KnowledgeRead -> KnowledgeAnswer` vertical owner.

Task 9.8 remains the aggregate claim-level/provider/latency acceptance gate after S2C and S8.8.

### 3. S10 operations closure — Accepted

S10O closes Tasks 10.3–10.5 at `65/80`:

- durable gap/remediation linkage to offline landing/build/release/effect receipts;
- Canonical V2 gap/assertion/decision/release admin API and minimal review UI;
- end-to-end proof that Web/LLM/answer/gap flows cannot write active canonical or Milvus directly.

### 4. S11 consumer migration

Use three slices rather than rewriting every legacy file individually:

1. S11A Accepted Chat Adapter — `/api/chat` now routes through one release-bound
   `KnowledgeRead -> KnowledgeAnswer` composition root, response mapper, typed session binding, and
   immutable feedback checkpoint. The ledger remains `65/80`; receipt SHA-256 is
   `b0b1848b2a15aca7f8d1fa33587f2276b19f2c1183327a28c0bf128a864c97f3`.
2. S11B Admin/ops and writer cutover — **Accepted** at the unchanged `65/80` ledger. V2 admin reads/
   operations, explicit ingest/smoke/baseline CLIs, and default-deny legacy/index quarantine are
   bound by receipt `cee1beebe2bdb1eba3f09b06e4e3c819167bbba14d5b6d6072f1f4cbafb0a945`.
3. S11C Consumer acceptance — **Accepted** at `70/80`. HTTP/session/admin scenarios, static legacy-
   import guards, exact disposable-target broad checks, complete failure ledger, execution
   provenance, and final `C0/I0` reviews close Tasks 11.1–11.5 atomically. Receipt:
   `281b28244a9fb5043a10df4e7eaa8f4e9e9385825babdae6204a461661a99717`.

### 5. S12 isolated candidate and handoff

1. S12A Complete Isolated Candidate Builder — one deep `KnowledgeBuild` implementation owns
   inventory/verified copies, immutable landing, authority/gaps, projections, durable registry,
   fresh indexes, verification, and a content-addressed receipt. Its thin run adapter calls
   `KnowledgeBuild.build` once. Unrecoverable inputs produce typed gaps rather than fabricated facts;
   S12A closes only Task 12.1.
2. S12B Final Gate — after human-reviewed S2C contracts exist, run domain/path/query/answer/Web/
   parity/latency/cost gates, strict validation, bounded real-provider checks, rollback, and the
   aggregate recovery/gap/source/decision/release/index/benchmark evidence for Task 12.3. Task 12.5
   requires explicit user acceptance; Task 12.6 preserves the separate Cutover boundary.

## First observable product checkpoint

The earliest user-visible checkpoint, S11A, is now Accepted:

```text
POST /api/chat
  -> explicit isolated candidate release
  -> Canonical V2 validated plan
  -> exact/structured/relationship/Web evidence
  -> grounded claims/citations/limitations
  -> typed session result set
  -> user-selected Paper/Patent traversal on the same release
```

The response or development trace view should expose `release -> plan -> lanes -> evidence ->
claims` so the V2 path is directly observable and cannot be confused with the legacy fixed handler.

## External gates that are not implementation blockers

- Task 2.8/S2C human case review and second calibration review;
- approved source scope for any new targeted recollection;
- bounded real Web/LLM/provider credentials for final latency/cost evidence;
- final independent consumer review;
- Task 12.5 explicit user acceptance;
- any Task 12.6 production-like Cutover/archive/destructive-cleanup authorization.

Until their dependency point, these gates do not block independently Ready implementation work and
must not mark the global goal blocked.
