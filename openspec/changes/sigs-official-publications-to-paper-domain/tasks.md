## 1. Parser Regression

- [x] 1.1 Add Ahmed SIGS RED regression covering author-prefixed numbered citations.
- [x] 1.2 Add regression coverage proving official publication extraction is not truncated to a fixed top-N.
- [x] 1.3 Implement SIGS author-prefixed citation splitting so `clean_title`, `authors_text`, `venue_text`, and `year` are correct.
- [x] 1.4 Add LLM-assisted extraction fallback tests for variable SIGS and cross-institution citation formats with source-span validation.

## 2. Paper-Domain Bridge

- [x] 2.1 Add bridge tests proving more than five official page publications are resolved/upserted/linked.
- [x] 2.2 Add bridge guard/tests preventing malformed author-list titles from reaching external title resolution.
- [x] 2.3 Implement bridge guard and ensure `professor_paper_link` uses `link_status='verified'`, `is_officially_listed=true`, and page-tier evidence.
- [x] 2.4 Wire homepage paper ingest and CLI to optionally use the validated LLM publication extractor.
- [x] 2.5 Add Crossref, Semantic Scholar, and DBLP title-level resolver cascade before arXiv/web fallback, with conservative confidence tests and DBLP canonical-source storage support.
- [x] 2.6 Add shared homepage fetch fast-fail/raw-text fallback so blocked profile pages do not require school-specific paper parsing code.
- [x] 2.7 Run shared homepage paper ingest automatically after successful admin-triggered full seed runs, and preserve official source-page roles on same-URL homepage discoveries.
- [x] 2.8 Ensure shared homepage paper ingest writes source-page evidence for second-hop publication pages and preserves `professor_paper_link.evidence_page_id`.
- [x] 2.9 Move LLM-assisted homepage publication extraction into a shared paper module and wire admin full-seed follow-up to use it without putting LLM work back in the seed write loop.
- [x] 2.10 Add SYSU cross-institution parser/adapter guardrails for SIC partial-representative-output headings and AM stale HTTP seed fallback.
- [x] 2.11 Keep paper homepage parsing and title enrichment in shared modules by default: filter tab/student/link-label parser noise centrally, route CJK and large official lists through shared multi-source title resolution, and expose an explicit fast-mode flag for disabling arXiv title search.
- [x] 2.12 Preserve legitimate papers whose titles discuss patents while still filtering actual patent records, accept short labeled `profile_raw_text` publication sections in the shared parser, and filter HIT JSON roster placeholder records before discovery writes.
- [x] 2.13 Harden shared paper title cleaning and title-quality guards for SUSTech and SUAT reference-like page fragments while preserving legitimate short and `Code`-containing paper titles.
- [x] 2.14 Add bounded resolver controls for large title-enrichment batches so OpenAlex, DBLP, and arXiv title search can be disabled without changing default single-title behavior.
- [x] 2.15 Add SZU BigData publication-page discovery and CMS/footer noise guards so seed 5 dry-runs stop sending site navigation and publish-time fragments to title resolution.
- [x] 2.16 Preserve context-supported short publication titles in homepage ingest while continuing to block author-list, person-name, patent-record, and footer-navigation false positives.
- [x] 2.17 Ensure title-resolution cache hits respect provider-disable switches so disabled OpenAlex, DBLP, or arXiv sources cannot be reused from old cache rows during bounded runs.
- [x] 2.18 Harden shared paper title-quality guards for SZU material-page metric, grant, patent-section, and truncated-reference fragments while preserving legitimate fuel-cell titles that look like capitalized author prefixes.
- [x] 2.19 Add a shared homepage recursion page ledger so personal/lab homepage and second-hop publication-page outcomes are auditable across schools without moving school-specific crawler logic into paper parsing.
- [x] 2.20 Add shared professor-identity and profile-title safety guards so non-person CUHK/SZTU/SYSU/SZU pollution cannot create or migrate verified paper links.
- [x] 2.21 Add a true read-only page-only title-enrichment planning mode before running broad resolver-backed migration batches.
- [x] 2.22 Reject publisher-series-volume fragments such as `Springer LNCS 3483` before title resolution while preserving legitimate long paper titles.
- [x] 2.23 Reject adjacent SZU metric, grant, award, and publication-tail fragments such as `IF: 6.578 (JCR1)` and `66(2), 696-706. 中科院大类 2 区， IF = 6.8` before resolver calls.
- [x] 2.24 Harden the shared paper title-quality guard for cross-seed pollution found during runtime audit, including venue-only proceedings lines, metadata/page tails, patent records, profile/service snippets, metric/ranking snippets, section labels, and short author fragments.
- [x] 2.25 Harden shared reference-like title cleaning and title-quality guards for seed-37/19/29 rollout findings, including contribution prefixes, `etc.` prefixes, venue/download/coauthor tails, profile/honor prose, venue headings, project/funding text, and service/committee prose.
- [x] 2.26 Strip short trailing venue abbreviations and single-author prefixes in the shared reference-like title cleaner and canonical paper writer so cleaned titles reach both detail pages and retrieval indexes.
- [x] 2.27 Harden shared reference-like title cleaning and title-quality guards for seed 9/29/35/5 audit findings, including `[C/OL]//` citation tails, venue/year download tails, trailing `with <authors>` notes, quote-plus-abbrev journal tails, standalone section/media labels, venue-only fragments, DOI/date rows, issue/page rows, CJK joint-lab/project rows, and author-list citation tails.
- [x] 2.28 Harden shared title-quality guards for subagent-audited patent/chapter/profile-navigation/citation-tail defects while preserving legitimate hyphenated, `and`-joined, and math/materials paper titles.
- [x] 2.29 Harden shared title-quality guards for SYSU seed 36 contact, teaching-supervision, talent-program, and honor/profile fragments before resolver calls, while preserving legitimate vision and engineering paper titles.
- [x] 2.30 Harden shared title-quality guards for HITSZ seed 20 project, biography, author-list, mojibake, venue-only, citation-tail, and author-tail residue before resolver calls while preserving legitimate Nano/materials titles.
- [x] 2.31 Correct the SZU CSSE seed 5 roster-card fallback mapping for `zc=5` so assistant professors are not written as researchers before downstream profile and paper collection.
- [x] 2.32 Allow SUSTech professor-owned `faculty.sustech.edu.cn` individual profile pages into shared homepage paper ingest while preserving root/list/noise blocks.
- [x] 2.33 Add UESTC YJSJY profile/readiness guardrails and UESTC/SZTU homepage-publication parser fixes for split emails, narrative research topics, star-bulleted papers, aggregate-only no-fabrication, and semicolon quoted-paper lists.
- [x] 2.34 Persist explicitly labeled teacher-maintained personal homepage URLs from official profiles as owned source pages with recursion ledger evidence, without making those pages primary identity evidence.

## 3. Summary, Full-Text, And Index Follow-Up

- [x] 3.1 Verify the summary backfill path can target Ahmed or linked paper IDs with DOI metadata enrichment.
- [x] 3.2 Verify page-only papers without abstracts do not fabricate `abstract_clean` and remain enrichment/review candidates.
- [x] 3.3 Verify targeted paper Milvus refresh can be driven by linked paper IDs or changed-since after summary updates.
- [x] 3.4 Add institution-scoped paper `summary_zh` backfill support so SIGS can be processed as one bounded batch.
- [x] 3.5 Carry DOI PDF URL candidates from OpenAlex, Crossref, Semantic Scholar, and Unpaywall into summary backfill full-text extraction before skipping no-abstract papers.
- [x] 3.6 Strip Chinese exact-paper question suffixes in retrieval and chat classification so natural paper-title questions recall the intended paper.
- [x] 3.7 Allow DOI/arXiv/OpenAlex metadata enrichment during summary backfill when abstract already exists but readiness-required metadata such as venue, year, or authors is missing.
- [x] 3.8 Backfill `paper.abstract_clean` from source-grounded `paper_full_text.abstract` so frontend detail and retrieval can use full-text-derived abstracts, not only generated Chinese summaries.
- [x] 3.9 Keep canonical paper rows retryable when a generated `summary_zh` is rejected, instead of terminally setting `quality_status='rejected'`.
- [x] 3.10 Require provider abstracts to pass the usable-abstract gate before persisting them to `paper.abstract_clean`.
- [x] 3.11 Exclude unsafe professor/profile rows from page-only title-enrichment backfill before resolver calls or link migration.
- [x] 3.12 Strip paper-domain prefixes and summary suffixes in RetrievalService exact-title normalization so `论文 <title> 的摘要是什么` recalls the ready paper.
- [x] 3.13 Allow summary backfill to generate `summary_zh` from source-grounded `paper_full_text.intro` when no usable abstract exists, without treating intro as `abstract_clean` or a ready-status abstract signal.
- [x] 3.14 Allow conservative RetrievalService exact-title recall for non-rejected partial papers when the exact-title candidate has source-grounded `summary_zh` or a real abstract, while still filtering title-only partial rows under the default ready-only gate.
- [x] 3.15 Ensure rejected paper candidates are never returned from RetrievalService quality annotation, and make paper topic chat prefer ready candidates before falling back to non-ready non-rejected rows.
- [x] 3.16 Synchronize same-run PDF `intro` extraction into summary backfill source text so intro-only papers can receive grounded `summary_zh` without writing intro to `paper.abstract_clean`.
- [x] 3.17 Strip suffix-style Chinese exact-paper summary questions such as `<title> 这篇论文的摘要` in RetrievalService exact-title normalization.
- [x] 3.18 Add an explicit paper-ID batch input for Milvus paper refresh so operators can index changed papers without misusing `--resume`, whose current semantics skip listed IDs.
- [x] 3.19 Refresh professor `paper_count` and `paper_summary` from verified professor-paper links during canonical writes even when no external metrics source is present.

## 4. Runtime Rollout

- [x] 4.1 Run Ahmed dry-run and record publication count, title correctness, resolver hits, page-only count, and issue count.
- [x] 4.2 Run Ahmed real paper/link bridge when DB and provider prerequisites are available.
- [x] 4.3 Run Ahmed summary backfill and targeted paper Milvus refresh when prerequisites are available.
- [x] 4.4 Run a random SIGS 10-professor sample and record per-professor parse/ingest/enrichment outcomes.
- [x] 4.5 Run full SIGS with a resume checkpoint after Ahmed and sample acceptance.
- [x] 4.6 Run a cross-institution parser quality audit and record non-SIGS suspicious/low-recall findings.
- [x] 4.7 Validate sampled SIGS records in both frontend detail pages and backend retrieval/chat recall after Milvus refresh.
- [x] 4.8 Deduplicate paper topic-search chat results by paper ID so multiple Milvus chunks do not produce duplicate citations or matched objects.
- [x] 4.9 Deduplicate paper topic-search chat results by normalized title so cross-source duplicate paper IDs do not produce duplicate citations or matched objects.
- [x] 4.10 Record the 2026-06-10 seed 37/38/39 summary backfill, targeted Milvus refresh, frontend detail validation, exact paper chat, and paper semantic recall evidence.
- [x] 4.11 Run bounded SUSTech and SUAT title-enrichment, summary backfill, Milvus refresh, frontend detail, retrieval, and chat validation slices without claiming all-school completion.
- [x] 4.12 Record the 2026-06-12 paper completeness audits for seed 5, seed 47, SYSU seeds, summary-backfill candidate pools, global paper coverage, and personal-homepage recursion gaps.
- [x] 4.13 Run bounded SYSU seed 42 and seed 40 title-enrichment, summary backfill, Milvus refresh, and backend detail/chat validation slices without claiming all-SYSU completion.
- [x] 4.14 Run bounded SYSU seed 36 title-enrichment, seed 19 summary backfill, seed 42 follow-up title-enrichment, summary backfill, Milvus refresh, frontend detail, and backend chat validation slices without claiming all-school completion.
- [x] 4.15 Run bounded SZU seed 15 title-enrichment, summary backfill, Milvus refresh, and backend detail/chat validation without claiming all-SZU completion; record seed 35 and personal-homepage recursion as blocked follow-up slices.
- [x] 4.16 Run bounded SUSTech seed 9 exact-pilot title-enrichment, summary backfill, Milvus refresh, frontend detail, and backend chat validation without claiming all-SUSTech completion.
- [x] 4.17 Record bounded seed-41 and SUSTech seed-9 no-write/no-enrichment outcomes as rollout risks, and stop unsafe broad writes when providers or candidate quality do not meet acceptance gates.
- [x] 4.18 Verify the pollution guard with CUHK seed 35 regression fixtures and record why broad title enrichment remains blocked or becomes safe.
- [x] 4.19 Run a bounded cross-seed high-confidence summary backfill, targeted Milvus refresh, frontend detail check, RetrievalService recall, and chat validation without claiming broad paper completion.
- [x] 4.20 Fix recollection-readiness handling for historical non-scalar `seed_id` JSON values and record the seed 24 preview/sample/full recollection plus sparse-paper-ingest outcome without claiming paper completion.
- [x] 4.21 Validate the intro-only paper summary slice through backend detail, RetrievalService exact-title recall, chat exact-paper routing, and targeted Milvus refresh without claiming broad paper completion.
- [x] 4.22 Accept `manual_interruption` seed-run failure classes in admin seed API/frontend contracts so seed 5 and the seed registry remain visible and triggerable after an operator-stopped run.
- [x] 4.23 Run bounded CUHK(SZ) seed 7 title-enrichment, summary backfill, targeted Milvus refresh, backend detail, RetrievalService recall, and chat validation without claiming all-CUHK(SZ) completion.
- [x] 4.24 Run bounded SZU seed 14 title-enrichment, summary backfill, targeted Milvus refresh, backend detail, RetrievalService recall, and chat validation without claiming all-SZU completion.
- [x] 4.25 Run bounded SYSU seed 37 title-enrichment, summary backfill, targeted Milvus refresh, backend detail, RetrievalService recall, and chat validation without claiming all-SYSU completion.
- [x] 4.26 Re-run SYSU seed 37 second-batch planning/dry-run after the shared title-cleaning hardening and record whether it is safe for a bounded write.
- [x] 4.27 Run seed-6 canary summary backfill, targeted Milvus refresh, backend detail, RetrievalService exact/semantic recall, paper topic chat, and frontend detail validation without claiming all-CUHK(SZ) completion.
- [x] 4.28 Clean the 15 observed short-venue-title polluted ready papers in the live DB, refresh their Milvus chunks, and validate detail/chat/retrieval surfaces on the cleaned data.
- [x] 4.29 Run the current source-grounded missing-summary batch, refresh changed paper chunks, and validate partial exact-title detail/retrieval/chat/frontend behavior without fabricating abstracts or ready status.
- [x] 4.30 Run the CUHK seed 35 first-30 canonicalization follow-up for six Crossref-resolved papers, backfill available summaries, refresh targeted paper chunks, and validate RetrievalService exact-title recall for ready and intro-summary partial papers without claiming broad seed completion.
- [x] 4.31 Record the 2026-06-12 global paper-gap audit and seed 9/29/35/5 no-write planning checks as the next broad rollout queue.
- [x] 4.32 Run the 2026-06-12 SZU seed 15 bounded 100-paper title-enrichment slice, summary backfill, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SZU completion.
- [x] 4.33 Run the 2026-06-12 SYSU seed 42 low-risk summary-first slice, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SYSU completion.
- [x] 4.34 Run the 2026-06-12 SYSU seed 38 bounded 100-paper title-enrichment canary, summary backfill, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SYSU completion.
- [x] 4.35 Run the 2026-06-12 SYSU seed 39 low-risk summary-first slice, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SYSU completion.
- [x] 4.36 Run the 2026-06-12 SYSU seed 36 guarded 100-paper title-enrichment slice, summary backfill, single-paper Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SYSU completion.
- [x] 4.37 Run the 2026-06-12 SZU seed 14 follow-up bounded 100-paper title-enrichment slice, summary backfill, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SZU completion.
- [x] 4.38 Run the 2026-06-12 HITSZ seed 20 guarded no-write planning check, then process only the already-resolved safe abstract-backed subset through summary backfill, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-HITSZ completion.
- [x] 4.39 Run the 2026-06-13 SUAT seed 29 bounded title-enrichment slice, summary backfill, targeted Milvus refresh, backend detail/chat validation, RetrievalService exact-title recall, and frontend detail validation without claiming all-SUAT completion.
- [x] 4.40 Record the 2026-06-13 seed 24 source-limited no-paper finding and the seed 5/seed 47 crawler/parser improvements as follow-up prerequisites before rerunning those school slices.

## 5. Acceptance And Reporting

- [x] 5.1 Record OpenSpec acceptance evidence for parser tests, ingest tests, Ahmed validation, summary/index checks, and any skipped prerequisites.
- [x] 5.2 Update `tasks.md` statuses as each slice is completed.
- [x] 5.3 Report remaining failure reasons and rollout risks without claiming unverified completion.
- [x] 5.4 Record a version checkpoint for the SIGS paper parser/bridge/resolver/summary/report slice and its V024-V040 migration-chain dependency before further rollout writes.
- [x] 5.5 Record that the remaining acceptance gap is broad school-by-school rollout and verification, not the bounded SUSTech/SUAT/SIGS paper slices already verified.
- [x] 5.6 Record verification evidence for shared professor/profile pollution guards before resuming unsafe broad paper writes.
- [x] 5.7 Record verification evidence for the shared paper cleaner/quality/retrieval/summary hardening before the next broad title-enrichment write batch.
- [x] 5.8 Record verification evidence for the seed 15 bounded write slice and subagent-reported next rollout queue.
- [x] 5.9 Record verification evidence for the subagent-audited shared title-quality hardening before the next seed title-enrichment canary.
- [x] 5.10 Record verification evidence for the seed 42 summary-first slice and the Milvus URI environment correction.
- [x] 5.11 Record verification evidence for the seed 38 title-enrichment canary and post-summary retrieval readiness.
- [x] 5.12 Record verification evidence for the seed 39 summary-first slice and ready/partial source-grounded outcomes.
- [x] 5.13 Record verification evidence for the seed 36 guarded title-enrichment and summary slice, including the Milvus `--resume` misuse finding and the validated single-paper retrieval/chat/frontend path.
- [x] 5.14 Record verification evidence for the seed 14 follow-up bounded enrichment slice and the new `--paper-id-file` targeted Milvus refresh path.
- [x] 5.15 Record verification evidence for the seed 20 shared title-quality hardening, safe-summary subset, targeted Milvus refresh, frontend/detail/retrieval/chat validation, and the subagent-audited seed 5 plus all-seed paper-completeness gaps.
- [x] 5.16 Record verification evidence for the seed 29 bounded paper-ready slice, the seed 24 no-fabrication decision, the seed 5 CSSE supplement publication-entry fix, the seed 47 inline quoted Chinese publication fix, and the combined homepage-ingest/admin follow-up test evidence.
- [x] 5.17 Record verification evidence for the SUSTech `faculty.sustech.edu.cn` source-selection allowance without running mutating ingest scripts.
- [x] 5.18 Record verification evidence for institution-prefixed professor-paper and professor-topic chat routing during broad seed rollout validation.
- [x] 5.19 Record main-thread integration evidence for the UESTC/SZTU parser, personal-homepage recursion, and verified-link professor-metrics subagent patches.
- [ ] 5.20 Before archive, pass `close-retrieval-generation-contract` C0 and D1: align exact-title
  identity-only partial behavior with `retrieval-active-v1`, and replace historical ready-first topic
  fallback with one ready+active-partial-rich paper-level competition, including quality disclosure,
  terminal/semantic-title-only exclusions, regression, and latency proof.
