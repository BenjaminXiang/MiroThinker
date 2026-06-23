## Context

Root-cause **E1** (professor→paper dirty-data investigation, 2026-06-16): the LLM same-person gate `professor/paper_identity_gate.batch_verify_paper_identity` computes a verdict per `(professor, paper)` attribution and writes it to `professor_paper_link.link_status` (via `run_identity_verify_candidate_links.py`). It never promotes `paper.identity_status`. Because `paper/milvus_backfill._is_indexable_paper` excludes only `identity_status in {rejected, merged}`, wrong-attribution papers (same-name, not same-person) remain indexed and surface to users.

Current `paper.identity_status` lifecycle (Alembic V020; values `{confirmed, unverified, rejected, merged}`, default `unverified`): `confirmed` by trusted identifier resolution (OpenAlex/arXiv/DOI, `canonical_writer` + `run_paper_doi_verify`); `merged`/`rejected` for `prof_page_only` duplicates (`run_paper_title_enrichment_backfill._mark_page_only_merged` / `_reject_implausible_paper`). The LLM gate is the missing writer.

Precedent: `scripts/run_name_identity_scan.py` (dry-run default, `--apply`, JSONL per-row decisions, `_ScanStats` counts) and the professor name-gate flag-separation lesson from `docs/solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md` (one miscalibrated gate must not null a whole column irreversibly; split the flags). Risk profile here is **lower** than the professor name-gate: status transitions are reversible, whereas the name-gate nulls `canonical_name_en` via `ON CONFLICT DO UPDATE`.

Constraints (CLAUDE.md §7): preserve V001–V042 history (no migration — V020 column reused), evidence shape + `run_id` traceability, `_VALID_DOMAINS`, A–G semantics. Gate threshold (0.8) and fail-safe-to-reject semantics are unchanged.

## Goals / Non-Goals

**Goals:**
- Wire LLM-gate rejections → `paper.identity_status='rejected'` → Milvus exclusion, conservatively (only prof-page-only papers with no surviving verified link).
- Ship reversible, evidence-backed, behind an independent kill-switch flag, dry-run-first (measure blast radius before any write).

**Non-Goals:**
- Cleanup of dead `apply_identity_gate_reevaluation` (Gap A — separate).
- Promoting the ~7,297 `unverified` rows (source-gap / `doi_verify` → W0a/W2a).
- Changing gate threshold/semantics, dedup anchors, or `_is_indexable_paper`.
- Auto-merging title+year-only duplicate groups.

## Decisions

1. **Scan-driven, not ingest-inline.** Model `run_paper_identity_scan.py` on `run_name_identity_scan.py` (dry-run default, `--apply`, JSONL, counts). *Why:* the gate has only run at the row level in tests; the unverified population is large, so blast radius must be measured before writes. *Alternative rejected:* inline the writer inside `run_identity_verify_candidate_links.py` — couples relation-status writes with row-status promotion and removes the dry-run safety.

2. **Rejection guard = (no `verified` link remaining) AND `canonical_source='prof_page_only'`.** Mirrors `_reject_implausible_paper` (`run_paper_title_enrichment_backfill.py:1085`). *Why:* prof-page-only papers are exactly those whose only attribution signal is the (now-rejected) professor link; identifier-backed papers keep `confirmed` identity and must not be collateral. *Alternative rejected:* "any paper with no verified link" — too broad; would reject identifier-backed papers that merely lack a verified prof link.

3. **Mutate `identity_status` only; never terminalize `quality_status`.** *Why:* `evaluate_paper_promotion` treats `quality_status='rejected'` as terminal (non-self-healing). Keeping the rejection on `identity_status` preserves reversibility and a human-review path.

4. **Flag in the script, not the module; independent flag `PAPER_IDENTITY_GATE_ENABLED`.** *Why:* Round 7.17 lesson — operators must kill this gate alone without losing professor name-gate or paper-collector protection. Default conservative (off) until a dry-run shows a sane reject rate.

5. **Reversibility via re-scan, restoring the exact prior value.** The scan records each rejected paper's `prior_identity_status`; a later scan restores it when a `verified` link is re-established. *Why:* exact restore avoids guessing (re-deriving from identifier presence can disagree with history). *Alternative:* re-derive — rejected as lossy.

6. **Plausible-title guard on the rejection transition.** The guard adds a third condition: `is_plausible_paper_title(title_clean)` must be `True`. *Why:* the 2026-06-16 dry-run (baseline 1,519 eligible) found 92% (1,400) had parser-garbage titles (root cause C2/C3) and were `rejected` only because the broken title defeated gate matching — not wrong attribution. Rejecting them would mislabel "unverifiable due to bad title" as "wrong-attribution" and exclude correct papers from Milvus. The guard restricts the transition to the ~119 plausible-title, genuinely-attribution-questionable rows; garbage-title rows stay `unverified` for the W1b parser-cleanup change. *Alternative rejected:* apply now and let garbage rows be excluded — wrong semantics + propagates contaminated verdicts (the scan does not re-evaluate already-rejected links).

## Risks / Trade-offs

- **[Reject rate too high / false rejects]** → dry-run first; flag off by default; reject → reversible + human queue (not terminal). The guard (no verified link + prof_page_only) limits blast to already-weak-attribution rows.
- **[One paper, many professors]** → inherent mitigation: the guard requires no `verified` link across **all** links, so a paper correctly attributed to one professor is never rejected because of another.
- **[Milvus coverage drop after apply]** → requires a Milvus re-backfill; dry-run reports the would-be-excluded count first; operator runbook documents the re-backfill step.
- **[Stale `rejected` after upstream data improves]** → periodic re-scan restores; reversibility by design.
- **[Gate LLM hiccup → bulk reject]** → independent kill-switch flag + dry-run; the guard bounds blast radius to prof-page-only rows.

## Migration Plan

1. Ship the scan in **dry-run** mode; run against `miroflow_real`; review reject counts + a sampled JSONL (confidence/reasoning distribution).
2. If the reject rate is sane, enable the flag + `--apply` on a **bounded slice**; re-backfill Milvus; verify the excluded count matches the dry-run prediction.
3. Generalize; add the operator runbook to the Agentic-RAG Operating-Guide or a solutions entry.

**Rollback:** disable `PAPER_IDENTITY_GATE_ENABLED`; run a re-scan (restores `identity_status` via reversibility); re-backfill Milvus. No schema change to undo.

## Open Questions

- **Restore semantics:** store `prior_identity_status` for exact restore (lean) vs re-derive from identifier presence. Decide at task-slice time.
- **Writer location:** new small helper `paper/identity_status_writer.py` (mirrors `_reject_implausible_paper`) vs reuse `canonical_writer`. Lean: new focused helper.
- **pipeline_issue stage:** reuse the existing `identity_gate` stage from the V006 enum (no migration).
- **Post-dry-run default:** flip the flag default to on, or keep off per operator discretion — decide after the dry-run count.
