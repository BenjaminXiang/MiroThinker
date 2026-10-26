# Tasks: materialize-professor-paper-projection

- [x] 1.1 Add `professor_projection_overlay.py`: load an allowlist JSON keyed by
      professor canonical id, merge `paper_count` / `top_papers` without
      overwriting pack values, skip `duplicate_name` records, disable on
      missing/invalid files.
- [x] 1.2 Wire the overlay into the professor claim builder (`_semantic_text`),
      gated by `CANONICAL_V2_PROFESSOR_PROJECTION`; render `论文数` and up to
      three `代表作` entries.
- [x] 1.3 Unit tests: merge rules, no-overwrite, duplicate-name exclusion,
      unknown id, top-paper text, broken/missing file, env caching, and an
      end-to-end `_semantic_text` test with the overlay on and off.
- [x] 1.4 Dry-run preview against the real pack and allowlist
      (`overlay-preview.md`): allowlisted claims gain count + representative
      papers; review-bucket claims are unchanged.
- [x] 1.5 Deploy to the customer site with the flag **off**, restart, verify
      `/api/health` and one professor question are unchanged.
- [x] 1.6 Enable the flag on the customer site, run the 27-turn eval gate, and
      spot-check five professor questions; keep the flag only if the gate does
      not regress.
- [x] 1.7 Record acceptance evidence and the rollback (unset the variable, no
      file or pack change needed).
