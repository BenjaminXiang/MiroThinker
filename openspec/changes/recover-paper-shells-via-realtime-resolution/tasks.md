# Tasks: recover-paper-shells-via-realtime-resolution

> Mostly orchestration of existing scripts; new code = ingest default + residual
> marker. Staged A→D, each a dry-run→bounded-apply gate. Codex implements the
> small new code; Claude runs the operational stages (localhost DB + external
> APIs). One active writer per slice.

## 0. Verification contract

- [x] 0.1 `.agents/runs/recover-paper-shells-via-realtime-resolution/verification-contract.md`
      — behavior-affecting; new-code surface deterministic (ingest default +
      residual marker → unit tests); recovery stages operational, verified by
      dry-run yields + retrieval spot-check. Pilot-first (Stage A) is the yield
      gate.

## 1. Ingest default (prevent recurrence) — CORRECTED: no code change needed

- [x] 1.1 **Grounding correction (2026-06-29):** the `None`-default is ALREADY
      realtime. `homepage_ingest.py` budget logic:
      `resolution_budget_exhausted = (effective is not None) and (attempts >= effective)`
      → `False` when `cap=None` → `allow_realtime_resolution = True` →
      `resolve_paper_by_title(cache_only=False)`. And `_should_skip_external_title_resolution`
      always returns `False`. So **default ingest resolves realtime; it does NOT
      create shells.** The 66,578 shells were one-time artifacts of past bulk runs
      that set an explicit small `--external-resolution-max-per-professor` (budget
      exhausted → cache_only). No code fix needed; recurrence is prevented by the
      default + the recovery pass (Stage A). (The originally-specified ingest-fix
      was based on a wrong premise — verified and dropped.)
- [x] 1.2 N/A — no behavior change; existing realtime default is the recurrence
      prevention. (Codex hung on the originally-specified unnecessary fix; cancelled.)

## 2. Residual marker — new code

- [x] 2.1 `scripts/run_paper_shell_residual_mark.py`: after Stage A, for shells
      still `prof_page_only` (unresolved), emit a bounded residual list
      (`paper_id` / `title` / linked professor) under `.agents/runs/.../`. No
      state mutation that fakes content; they remain not-ready (already excluded
      from retrieval). (Optional: a lightweight `pipeline_issue` row flagging
      them as `unresolvable_shell` for audit.)
- [x] 2.2 Test: residual marker lists exactly the post-Stage-A unresolved shells;
      does not touch `quality_status`/`summary_zh`.

## 3. Stage A — realtime re-resolution (operational, pilot-first)

- [ ] 3.1 Build the candidate file: 66,578 shell `paper_id`s (`prof_page_only`,
      no abstract) → `.agents/runs/.../shell-candidates.txt`.
- [ ] 3.2 **Pilot**: `run_paper_title_enrichment_backfill --paper-id-file
      <500-sample> --cache-only=false --disable-semantic-scholar-title-search
      --disable-dblp-title-search --worker-count N` (Crossref/OpenAlex primary).
      Record yield (resolved/unresolved, by source). Confirm ~77%; tune
      rate-limits/workers.
- [ ] 3.3 **Full run**: over all 66,578 candidates, realtime, rate-limited,
      resumable via cache. Record resolved count + merge_alias writes + 0 ready
      degraded.

## 4. Stage B — summary_zh (operational)

- [ ] 4.1 `run_paper_summary_zh_backfill` over the newly-resolved papers (Stage-A
      `run_id` / `--only-missing` with new abstracts). Batched, rate-limited.
- [ ] 4.2 Spot-check: summary_zh generated only for resolved papers; no boilerplate
      injection on a sample.

## 5. Stage C — ready + index (operational)

- [ ] 5.1 `run_quality_promote --domain paper` → recovered papers (full ready
      criteria) → `ready`.
- [ ] 5.2 `run_milvus_backfill --domain paper --collection paper_chunks
      --paper-id-file <newly-ready>` (targeted rebackfill).
- [ ] 5.3 Retrieval spot-check: ≥20 newly-recovered papers retrievable via
      `paper_chunks` (self@rank0/1).

## 6. Stage D — residual + acceptance + ledger

- [ ] 6.1 Run the residual marker (task 2.1) on post-Stage-A unresolved shells;
      document the bounded residual count.
- [ ] 6.2 Collect evidence: pilot yield, Stage A/B/C counts, retrieval spot-check,
      ingest-fix + residual-marker tests.
- [ ] 6.3 `openspec/change-ledger.md` status → `in-verification`; `openspec
      validate recover-paper-shells-via-realtime-resolution --strict` exits 0.
- [ ] 6.4 Claude review against `acceptance.md`; accept / revise / reject.
