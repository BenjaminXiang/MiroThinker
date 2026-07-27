# S12B Task 12.2 Verification

## Status

Candidate on 2026-07-26. Task 12.2 implementation and its objective checks are complete. Answer
quality is intentionally not accepted here; the real-runtime workbook replay and badcase repair
remain owned by Tasks 12.3 and 12.4.

## Candidate identity

- Release: `candidate-s12b-20260726-r5`
- Build run: `s12b-build-20260726-r5`
- PostgreSQL: explicit disposable `127.0.0.1:55455/miroflow_candidate_s12b_20260726_r5`
- Source manifest content hash:
  `6603f3f961d69ef40d34258ea583134255b632c048902356ba243245a1acf2ad`
- Serving bundle content hash:
  `887689cc3805267e69dc73ae0b0e11ce9021444ccc5719b5edf803e812858df1`
- Envelope canonical content hash:
  `abe56cc3b81e3b569fb68977bf845a1ef0e23e1583273be5d23323ff3b40b560`
- Envelope raw SHA-256:
  `d93ce8aac7da7591c461f96b52fd6e5c295bad6ad8c2f4e73adc69a791745808`

## Population and relationship audit

- Landing records: 5,561; identity decisions: 3,776; canonical decisions: 21,993; typed gaps:
  5,874.
- Public projections: Company 1,037; Paper 251; Patent 1,931; Professor 557.
- Relationships: 328 total: 251 `professor_attributed_to_paper`, 76
  `patent_has_applicant`, and 1 `professor_company_role`.
- Vector points: 4,333. Lookup documents: 3,776. Professor intentionally has separate identity and
  research vector views, so vector and lookup totals differ while both exact expected manifests
  equal their physical contents with no missing, extra, stale, or cross-release identity.
- Active release is absent before and after the build. Original PostgreSQL remains paused. Original
  Milvus hash remains `43ef203e...67cc` and was not opened by the Candidate path.

## Runtime evidence

- The content-addressed bundle loads the exact release into the accepted planner/read/answer chat
  adapter and does not discover or mutate an active pointer.
- The app is running on `0.0.0.0:18188`; `/api/health` and `/chat` return HTTP 200.
- A real `POST /api/chat` for `介绍一下丁文伯` returned HTTP 200 with the bound r5 release and
  structured evidence/citations. Its answer selected unrelated Patent material. This is preserved
  as a Task 12.3 badcase and prevents any answer-quality acceptance claim from this slice.
- A broad Company query and the exact-name-only form exercised the same real UI/API path and failed
  closed with structured 409 errors. Browser rendering showed the error without overlap or console
  errors. Screenshot: `/var/tmp/canonical-v2-s12b-r5-chat.png`.

## Focused checks

- Four-domain, relationship, serving-bundle, relationship-integrity, and identity-persistence owner
  matrix: `12 passed in 13.02s` with `pytest -n 12`.
- Admin runner and exact chat adapter: `8 passed in 12.22s` without xdist (the Admin environment
  does not install the xdist plugin).
- Focused Ruff and Pyright checks passed during implementation. Final changed-surface static and
  OpenSpec checks are recorded under Task 12.4.

## Preserved failure evidence

- r3 exposed missing relationship-type installation and unresolved Professor patent references.
- r4 exposed deferred-trigger ordering during identity persistence.
- r5 recovery exposed a blanket relationship-store rejection of an extended registry with no
  internal endpoints. Each defect received a focused regression and shared-boundary repair; failed
  resources and evidence remain intact.

## Remaining work

Tasks 12.3-12.6 remain open. No promotion, active-pointer change, production Cutover, archive,
destructive cleanup, commit, Push, or PR occurred.
