# Acceptance: correct-paper-tier2-overmerge-view-b

A change is accepted only when ALL of the following hold.

## Flip primitive + script
- [x] `flip_paper_canonical` reverses the alias (journal→conf deleted, conf→journal written),
      promotes the journal (`confirmed/ready`), demotes the conf (`merged/rejected`), un-rejects the
      journal link (clean evidence, no migration suffix), rejects the conf link. Idempotent re-run
      is a no-op. (8 fake-conn unit tests green.)
- [x] `--dry-run` prints the 4-step plan + exact link disposition; `--apply --confirm-real-db`
      executes under a real `run_id`; the stricter gate blocks ANY `miroflow_real` access without
      `--confirm-real-db`. (Dry-run ran clean for #1; `false_action_count=0`.)

## Tier-3 criterion (prospective)
- [x] Candidate SQL excludes DOI-conflict groups (≥2 distinct publisher DOIs); whitelists
      arxiv/ssrn/egusphere preprint DOIs. Verified by unit tests: a publisher-DOI-conflict group is
      excluded; a preprint↔published pair stays eligible. Existing `test_run_paper_exact_title_dedup`
      still green (6/6).

## Operational #1
- [x] After apply: alias `PAPER-3E13FAE7D789 → PAPER-64D7A39FC25B` present (reason
      `exact_title_dedup_canonical_correction`); journal `PAPER-64D7A39FC25B` `confirmed/ready`;
      conf `PAPER-3E13FAE7D789` `merged/rejected`; `prof→journal` link `verified` with
      `match_reason='homepage_title_resolution'` (no suffix); `prof→conf` link rejected. (DB-verified.)
- [x] Retrieval spot-check: online `/api/chat` query → routed `A_paper_profile` → journal
      (`PAPER-64D7A39FC25B`) returned ×3; conf absent; J indexable=True, C indexable=False.
      (No Milvus refresh needed — J's chunks present from pre-merge indexing.)

## #7 + #13
- [x] **#7 decision: KEEP AS-IS (no flip).** DB abstracts for `PAPER-0A3117FF4FC6` (NYAS 2007) and
      `PAPER-5F47A16E07AD` (CTO 2008) are near-identical (same opening sentence, same content, same
      5 authors: Franceschi, Ge, Xiao, Roca, Jiang; title differs by case only). They are the **same
      review article published twice** (NYAS proceedings → Cells Tissues Organs journal), NOT two
      distinct papers. The current merge is a correct View-B keep-one state (NYAS canonical/ready;
      CTO hidden). No action.
- [x] **#13 deferred.** `PAPER-7A80609AE22B` (LNCS conf 2008, `confirmed/partial`, not retrievable)
      vs `PAPER-9B500BAC9CB5` (Formal Methods 2010, `merged`, no abstract). Flip has zero retrieval
      impact — neither version is ready; the journal version also lacks an abstract, so flipping
      wouldn't make it retrievable. Deferred until the journal version is enriched.

## Invariants
- [x] No schema/enum/`_is_indexable_paper`/A–G/`_VALID_DOMAINS`/evidence-shape change.
- [x] `uv run pytest tests/scripts/test_run_paper_overmerge_flip.py tests/scripts/test_run_paper_exact_title_dedup.py -n0` → 14 passed; `ruff` clean.
- [x] `openspec validate correct-paper-tier2-overmerge-view-b --strict` exits 0.

## Evidence
- `.agents/runs/correct-paper-tier2-overmerge-view-b/evidence.md` — dry-run plan, flip counts, post-state query, online retrieval spot-check, #7 abstracts, #13 deferral.
