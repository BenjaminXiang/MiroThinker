# Change Log — recover-paper-shells-via-realtime-resolution

- **2026-06-28** — User rejected the earlier "shells unrecoverable (URLs lost)"
  conclusion ("论文壳是必须要解决的缺口") and invoked `superpowers:brainstorming`
  to deep-think it with web search + code grounding.
- **2026-06-28** — Grounding OVERTURNED the prior conclusion:
  - Web research: Crossref `query.bibliographic` is the gold standard for
    title→DOI; OpenAlex polite pool + author/institution filters; CNKI/Wanfang/
    CQVIP have no open API (Chinese-not-in-OpenAlex = genuine residual).
  - Code: `homepage_ingest.py:2082-2104` — `allow_realtime_resolution` is
    budget-capped (`external_resolution_max_per_professor`); once exhausted,
    un-cached titles resolve `cache_only` → shell synthesized with NO realtime
    API call. 0 shells have a `resolved=False` cache entry.
  - **Empirical**: realtime `resolve_paper_by_title` (with professor
    `author_hint`) on a 30-shell sample = **23/30 = 77% hit (Crossref)**.
- **2026-06-28** — So shells are a `cache_only`/budget-capped artifact, not
  "APIs lack them". ~77% (≈51k) recoverable by running the already-built resolver
  at scale. The earlier "URL lost/unrecoverable" was wrong (assumed resolution
  was tried-and-failed; it was skipped).
- **2026-06-28** — Brainstorming: user chose (Approach 1) full recovery chain in
  one change, internally staged (A re-resolution → B summary_zh → C ready+index →
  D residual) + ingest default fix; residual ~23% accepted as bounded terminal;
  no gate relaxation / no summary_zh fabrication.
- **2026-06-28** — Created OpenSpec change `recover-paper-shells-via-realtime-resolution`
  (Epic, behavior-affecting, new capability `paper-shell-recovery`):
  `proposal.md`, `specs/paper-shell-recovery/spec.md`, `design.md`, `tasks.md`,
  `acceptance.md`, `source-links.md`, `agent-links.md`, this log.
- **Pending** — verification-contract (task 0.1), Codex small-code slices
  (ingest default + residual marker), Claude operational stages (pilot → full
  resolution → summary_zh → ready+index → residual + retrieval spot-check),
  `change-ledger.md` registration, `openspec validate --strict`.
- **2026-06-29 (implementation + correction):** Stage A launched (background,
  full realtime resolution over the 66,578 shell candidates → ~6,500 processable,
  ~3,750 recovered per the 600-sample 58% yield). Codex delivered the residual
  marker (task 2.x, 3 tests GREEN) but **HUNG on the ingest-fix** (1h8m,
  `homepage_ingest.py` unchanged) → cancelled. **Grounding correction: the
  ingest-fix (task 1.x) was based on a wrong premise** — the `None`-default is
  ALREADY realtime (`resolution_budget_exhausted` is `False` when cap=None;
  `_should_skip_external_title_resolution` always returns False). The shells were
  one-time artifacts of past explicit-small-cap bulk runs; default ingest creates
  no new shells. Task 1.x re-scoped to "no code change needed"; recurrence
  prevention = the default + the recovery pass. Residual marker retained (valid).
  Stage A still running at time of writing.
- **2026-06-29 (Stages A–D complete + honest outcome):**
  - **Stage A** (full realtime resolution, ~5.7h, 0 errors): 3,509 processable →
    **1,902 resolved** (real DOIs/arXiv/IDs, conf 0.85–1.0), 1,607 unresolved
    (residual: books/mangled titles/citation text). 1,902 merge_aliases + 1,904
    link re-points.
  - **Stage B** (`summary_zh`): 228 written → **ready 23,208 → 23,430 (+222)**.
  - **Stage C** (index): 1,287 re-indexed (222 new + ~1,065 merge-touched
    canonicals, idempotent); **retrieval spot-check 5/5 self@rank0**.
  - **+2 promote** (43 ready-eligible-by-field → only 2 pass the real gate; 41
    are gate-rejected, correctly stay not-ready). **FINAL ready 23,432.**
  - **Stage D**: residual marker (1,000-sample of the bounded residual).
  - **HONEST OUTCOME** (vs the original 51k/3,750 framing): the 1,902 resolved
    were mostly DUPLICATES of existing canonical papers (already ready/indexed);
    Stage A's main effect was **correct professor↔paper attribution** (~1,615
    merges: link re-pointed from the non-retrievable shell to the retrievable
    canonical) + **de-pollution** (duplicate shells merged out). Net NEW
    retrievable papers: **~224** (not 1,902/3,750). The recovery is real but
    modest; the bigger win is attribution/quality, not new volume.
  - Ingest-fix (task 1.x) dropped (None-default already realtime). Residual
    marker (task 2.x) delivered + verified (3 tests). Change →
    tasks-complete-not-archived; `openspec validate --strict` ✓.
