## ADDED Requirements

### Requirement: SIGS official publication entries are parsed as full paper candidates

The system MUST parse every official SIGS professor-page publication entry into a paper candidate whose `clean_title` is the paper title rather than an author list. Author-prefixed and numbered citation formats MUST preserve listed authors, venue text, year, source URL, and direct PDF URL when present.

The system MAY use LLM-assisted extraction for SIGS and other variable professor-page citation formats, but only after deterministic code locates the official publication section. LLM fallback MUST be available across institutions when rule parsing yields suspicious titles or low-recall citation sections, not only for one SIGS hostname. LLM output MUST be validated against source spans before any candidate enters the paper-domain bridge.

Source headings such as "Representative Publications" or `代表性论文` MUST be treated only as provenance labels. The system MUST NOT infer that these publications are the professor's representative works.

#### Scenario: Ahmed author-prefixed SIGS citation

- **GIVEN** Ahmed Elazab's SIGS official profile page contains `1- M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab*. Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images, Engineering Applications of Artificial Intelligence, 164, 113260, 2026`
- **WHEN** homepage publication extraction runs for the page
- **THEN** the extracted publication has `clean_title` equal to `Robust attention transfer neural networks for diagnosis of Alzheimer's disease from structural magnetic resonance images`
- **AND** `authors_text` contains `M. Abdelaziz` and `A. Elazab`
- **AND** `venue_text` contains `Engineering Applications of Artificial Intelligence`
- **AND** `year` is `2026`

#### Scenario: Official list is not truncated

- **GIVEN** a SIGS official profile page lists more than five official publication entries under a publication section
- **WHEN** homepage publication extraction runs
- **THEN** every parseable official publication entry is returned
- **AND** no fixed per-professor paper count cap is applied by the extractor

#### Scenario: LLM extraction is source-grounded

- **GIVEN** a SIGS official publication section contains citation formats that vary across professors
- **WHEN** LLM-assisted publication extraction is enabled for the post-collection bridge
- **THEN** the LLM receives only the official publication-section text
- **AND** each accepted item has a `source_span` from the page text
- **AND** `title`, `authors_text`, `venue_text`, `year`, and identifiers are accepted only when grounded in that `source_span`
- **AND** invalid or hallucinated items are not sent to title resolution

#### Scenario: Cross-institution low-quality rule extraction uses the same fallback

- **GIVEN** a non-SIGS official professor page has a publication section whose rule-parsed candidates contain suspicious author-list titles or whose citation-rich section yields fewer than three parsed papers
- **WHEN** an LLM extractor is configured for homepage publication extraction
- **THEN** the system attempts the same source-grounded LLM fallback used for SIGS
- **AND** accepted items still require source-span grounding
- **AND** invalid or hallucinated items are dropped before paper-domain title resolution

### Requirement: SIGS official publications bridge to canonical paper domain

The system MUST bridge extracted official SIGS professor-page publications through the paper-domain ingest path after professor seed recollection. For each parseable listed publication, the bridge MUST attempt title resolution, upsert a canonical `paper` row, and create or update a verified `professor_paper_link` with `is_officially_listed=true`.

The bridge MUST NOT run external title resolution synchronously inside the professor seed recollection main loop.

The bridge MAY enable LLM-assisted publication extraction as a post-collection option. That option MUST not be part of the professor seed recollection main loop.

The bridge's title resolver MUST use a conservative multi-source title cascade. Official professor-page entries remain the relationship evidence, while external sources only resolve or enrich paper metadata. The resolver MUST try OpenAlex, Crossref, Semantic Scholar, DBLP, arXiv, and optional web search in order, skipping rate-limited or failing sources without blocking later sources. A result MUST NOT be accepted unless normalized title similarity and available year/author hints meet the resolver confidence threshold.

Large title-enrichment batches MAY disable slow or rate-limited title-search providers such as OpenAlex, DBLP, or arXiv for that run. These switches MUST be explicit, recorded in run scope or report metadata, and MUST NOT change the default resolver behavior for single-title or ordinary homepage-ingest resolution.

Page-only title-enrichment backfill MUST provide a true read-only planning mode. In planning mode it MUST read candidate rows and report local title-quality counts and samples without opening pipeline runs, calling external resolver providers, committing transactions, or writing any paper/link/pipeline state.

Before a page-only title enters external title resolution, the shared paper title-quality guard MUST reject non-paper page fragments such as journal metric snippets, journal metric tails appended to citation fragments, grant/project funding lines, award/service/professional-history lines, patent-section labels, profile/service labels, publisher-series-volume fragments, and truncated one-word reference fragments. The same guard MUST preserve plausible academic titles even when the first words are capitalized technical phrases that could superficially resemble author names.

Before a reference-like title is persisted or sent to retrieval indexing, the shared title cleaner MUST strip short trailing venue abbreviations and citation-page residue such as `Nat`, `Sci`, `Commun`, `PNAS`, and `Light, Sci` when they appear as detached suffixes. It MUST also strip a leading single-author token before an article-style English paper title when the token is clearly citation residue. The canonical paper writer MUST use this cleaner so stored `paper.title_clean`, detail API responses, chat answers, and Milvus chunks use the cleaned title while retaining raw-title provenance separately.

For admin-triggered full professor seed runs, a successful roster/profile run MUST enqueue or run the shared homepage paper ingest bridge for that same seed with professor-owned homepage pages included. Preview and sample seed runs MUST NOT run the full paper bridge automatically. The follow-up MUST remain in the shared paper ingest path rather than in school-specific roster crawlers.

SUSTech `faculty.sustech.edu.cn` source selection MUST include professor-owned personal pages when the URL is an individual slug page such as `/chenxf/` or the matching `?tagid=<slug>&iscss=1&snapid=1` profile form. The same filter MUST continue to reject the faculty host root, roster/list pages, navigation pages, and non-professor noise before homepage paper ingest.

The admin seed registry API MUST accept and display seed-run failure classes emitted by controlled collection workflows, including operator-stopped `manual_interruption` runs. A historical or latest manual-interruption pipeline run MUST NOT make `/api/seeds`, `/api/seeds/{id}`, or admin seed triggering fail with response-model validation errors.

When a source page URL is first recorded as an official profile or official publication page, later same-URL personal homepage or lab homepage discoveries MUST NOT downgrade the stored `source_page.page_role`. This preserves the evidence tier used by the shared paper bridge.

Homepage publication links written by the shared bridge MUST preserve source-page traceability. When a listed publication comes from a professor homepage or a same-root second-hop publication page, the bridge MUST resolve or create the corresponding professor-owned `source_page` row and store its `page_id` in `professor_paper_link.evidence_page_id`. The bridge MUST NOT create professor source pages for arbitrary cross-site publication URLs.

The shared homepage paper ingest bridge MUST durably record recursion outcomes for professor-owned homepage pages and same-root second-hop publication-page candidates. Each non-dry-run ingestion MUST record whether a page was processed, produced zero extractable publications despite detected publication sections, failed fetch, or was skipped for safety such as leaving the professor-owned site root. Dry-run ingestion MUST NOT write this ledger.

The shared homepage paper ingest bridge and title-enrichment backfill MUST enforce professor-identity safety before writing or migrating verified paper relations. Rows whose professor identity is an obvious non-person label, whose profile title is a publication/patent/body fragment, or whose source profile is otherwise known to be crawler pollution MUST be skipped or filed for review before publication extraction, resolver calls, paper upsert, link migration, or `professor_paper_link` verification. This guard MUST be shared across schools and must not be implemented as a CUHK-only paper parser.

Paper topic-search chat responses MUST deduplicate retrieval chunk hits by canonical paper ID before presenting answers, citations, and structured payload objects. When duplicate chunks for the same paper are retrieved, the response MUST keep one paper object and prefer the stronger score/snippet metadata.

Paper topic-search and retrieval surfaces MUST NOT present paper rows whose `quality_status` or `identity_status` is `rejected`. This exclusion MUST still apply when a caller explicitly disables the ready-only quality filter for a fallback search. For paper topic chat, the system MUST first request ready paper candidates; it MAY fall back to non-ready non-rejected candidates only when no ready candidates are found, and fallback answers MUST keep the existing caveat behavior.

Paper retrieval exact-title normalization MUST support natural Chinese question forms where the paper-domain word appears before the title, such as `论文 <title> 的摘要是什么`, as well as suffix forms such as `<title> 这篇论文主要讲什么`. These query decorations MUST be stripped before exact-title lookup so ready papers can be retrieved by their titles.

When a paper exact-title candidate is non-rejected and has a source-grounded snippet from `summary_zh` or a real abstract, the retrieval service MAY return it even if `quality_status='partial'` and the default ready-only quality filter is enabled. This exception MUST apply only to conservative exact-title candidates. Partial title-only paper rows and ordinary semantic ANN paper candidates MUST remain filtered by the default ready-only gate.

The shared reference-like title cleaner MUST recover real paper titles from source-page citation tails such as `[C/OL]//...`, venue/year download suffixes such as `-- Bioinformatics, 2020 [ Paper ] [ Software ]`, trailing `, with <authors>` notes, quote-plus-abbreviated-journal tails such as `" J. Am`, and known detached journal names such as `BMC biology` or `Communications in Computational Physics`. The shared title-quality guard MUST still reject terminal non-paper fragments such as standalone section/media labels, venue-only fragments, journal date/DOI rows, issue/page rows, CJK joint-lab/project rows, and author-list citation tails before resolver calls.

The shared title-quality guard MUST reject additional subagent-audited non-paper title defects before resolver calls, including patent application-number records, English patent method/device records, CJK patent/system-research records, incomplete book-chapter fragments, paper-list profile-navigation snippets, and citation tails that still contain detached venue article numbers or volume/page/year suffixes. The same guard MUST preserve plausible academic paper titles with hyphenated technical phrases, `and`-joined scientific concepts, or math/materials terms that superficially resemble person-name lists.

#### Scenario: Ahmed paper bridge writes verified links

- **GIVEN** Ahmed Elazab's SIGS official profile page has parseable official publication entries
- **WHEN** the post-collection homepage paper ingest bridge runs for Ahmed
- **THEN** each parseable official publication is eligible for `resolve_paper_by_title`
- **AND** each resulting paper is upserted into `paper`
- **AND** a `professor_paper_link` row is written with `link_status='verified'`
- **AND** the link has `is_officially_listed=true`
- **AND** the link records `prof_homepage_tier2` or `prof_homepage_tier3` according to the stored page role

#### Scenario: Malformed author-list title is blocked before resolver

- **GIVEN** publication parsing returns a candidate whose `clean_title` looks like an author list and lacks a real paper title
- **WHEN** the homepage paper ingest bridge processes the candidate
- **THEN** the bridge does not call external title resolution for that candidate
- **AND** it records a diagnostic pipeline issue for the malformed publication

#### Scenario: Title resolver cascades across multiple metadata sources

- **GIVEN** a clean official-page publication title is not confidently resolved by OpenAlex
- **WHEN** `resolve_paper_by_title` runs for the bridge
- **THEN** it attempts Crossref title search before Semantic Scholar, DBLP, arXiv, and optional web search
- **AND** it attempts Semantic Scholar before DBLP, arXiv, and optional web search when Crossref is missing or below threshold
- **AND** it attempts DBLP before arXiv and optional web search when Crossref and Semantic Scholar are missing or below threshold
- **AND** a rate-limited or failing source returns no candidates without blocking later sources
- **AND** author-list-like titles remain below the confidence threshold and are not accepted automatically

#### Scenario: Paper retrieval strips prefix-style Chinese exact-title questions

- **GIVEN** a ready paper has title `Non-Iridium Based Electrocatalyst for Durable Acidic Oxygen Evolution Reaction in Proton Exchange Membrane Water Electrolysis`
- **WHEN** `RetrievalService.retrieve` is called for paper domain with query `论文 Non-Iridium Based Electrocatalyst for Durable Acidic Oxygen Evolution Reaction in Proton Exchange Membrane Water Electrolysis 的摘要是什么`
- **THEN** the exact-title candidate lookup uses the paper title without the `论文` prefix or `的摘要是什么` suffix
- **AND** the ready paper is returned as a `paper_title_exact` candidate

#### Scenario: Paper retrieval strips suffix-style Chinese exact-title questions

- **GIVEN** a ready paper has title `Environmental Exposure and Childhood Atopic Dermatitis in Shanghai`
- **WHEN** `RetrievalService.retrieve` is called for paper domain with query `Environmental Exposure and Childhood Atopic Dermatitis in Shanghai 这篇论文的摘要`
- **THEN** the exact-title candidate lookup uses the paper title without the `这篇论文的摘要` suffix
- **AND** the ready paper is returned as a `paper_title_exact` candidate with a `summary_zh` snippet when available

#### Scenario: Partial exact-title paper with grounded summary remains retrievable

- **GIVEN** a non-rejected partial paper has an exact title match for the user query and a source-grounded `summary_zh`
- **WHEN** `RetrievalService.retrieve` runs with the default ready-only quality filter enabled
- **THEN** the paper is returned as a `paper_title_exact` result
- **AND** the returned snippet source is `summary_zh`
- **AND** a partial paper row with only a title and no `summary_zh` or real abstract is still filtered out

#### Scenario: Bounded title-enrichment run can skip slow providers

- **GIVEN** a large backlog of page-only papers needs title enrichment
- **WHEN** the title-enrichment backfill is run with explicit provider-disable switches
- **THEN** the resolver skips only those disabled title-search providers for that run
- **AND** the run report records which providers were disabled
- **AND** ordinary homepage ingest and single-title resolution keep their default multi-source cascade

#### Scenario: Title-enrichment planning is read-only

- **GIVEN** a seed has page-only verified paper candidates
- **WHEN** `run_paper_title_enrichment_backfill.py` runs in planning mode
- **THEN** it reads the same guarded candidate selector as the real backfill
- **AND** it reports resolver-candidate, implausible-title, and missing-title counts and samples
- **AND** it does not open a `pipeline_run`
- **AND** it does not call external resolver providers
- **AND** it does not commit or write database state

#### Scenario: Shared title-quality guard blocks page-fragment noise

- **GIVEN** page-only paper rows contain fragments such as `IF= 11.301 (JCR1)`, `IF: 6.578 (JCR1)`, `中科院大类 1 区， IF = 14.7`, `66(2), 696-706. 中科院大类 2 区， IF = 6.8`, grant amount lines, patent-section labels, publisher-series-volume fragments such as `Springer LNCS 3483`, or truncated single-word references
- **WHEN** title-enrichment backfill evaluates candidates before provider lookup
- **THEN** those fragments are rejected as implausible paper titles before resolver calls
- **AND** legitimate technical titles such as `Synergistic Proton and Oxygen Transport Optimization via Binder Engineering for High-Efficiency ORR in High-Temperature Fuel Cell` remain eligible for title resolution

#### Scenario: Runtime title-quality audit pollution is rejected

- **GIVEN** existing page/homepage-linked paper rows include non-paper fragments such as `pp. 184--192`, `IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2023`, `Sensors and Actuators B: Chemical`, Chinese patent records with `ZL` numbers, `Patent NO.` authorization records, student/profile service snippets, `Category Quartile:Q2`, `Representative Publication`, or short author fragments such as `He, GJ; Chen`
- **WHEN** homepage ingest or page-only title-enrichment backfill evaluates those titles
- **THEN** the shared title-quality guard rejects them before resolver calls or automatic relation migration
- **AND** legitimate academic paper titles with similar technical vocabulary, acronyms, or CJK content remain eligible

#### Scenario: Short venue suffixes are stripped before persistence and retrieval

- **GIVEN** a reference-like paper title is parsed as `Non-Hermitian non-equipartition theory for trapped particles Nat`
- **WHEN** canonical paper upsert or title-enrichment backfill prepares the title
- **THEN** the stored cleaned title is `Non-Hermitian non-equipartition theory for trapped particles`
- **AND** the detached `Nat` suffix is not shown in detail pages, chat answers, or Milvus-indexed title chunks
- **AND** the raw source title remains available as provenance when present

#### Scenario: Rejected papers are not surfaced by paper topic chat

- **GIVEN** paper retrieval contains a rejected candidate and a ready candidate for the same topic
- **WHEN** paper topic chat answers the query
- **THEN** the rejected candidate is excluded from matched objects and citations
- **AND** ready candidates are preferred before any non-ready fallback search
- **AND** a fallback search with the ready-only quality filter disabled still excludes rejected rows

#### Scenario: Reference-like page titles are cleaned or rejected before resolver calls

- **GIVEN** page-only paper rows contain real titles with page-reference prefixes or tails such as `etc.Energy Recovery Strategy...`, `第一作者，AGSENet...`, `Quantifying privacy vulnerability... In 99th Transportation Research Board (TRB) Annual Meeting. [download]`, or `Simple k-crashing Plan... 23rd Conference in Autonomous Agents and Multiagent Systems (AAMAS'24) Coauthors: R. Luo`
- **WHEN** page-only title-enrichment backfill prepares the resolver title
- **THEN** the shared title cleaner strips the contribution prefix, `etc.` prefix, venue/download tail, or coauthor tail before external title resolution
- **AND** the original raw title remains available as provenance rather than replacing the cleaned resolver title
- **AND** rows that are only profile, honor, venue heading, project/funding, or service/committee prose such as `Shenzhen high-level professional talent`, `Conference of the North American Chapter... (NAACL-HLT)`, `主持教育部产学研协同育人项目3项、省级教改项目3项`, or committee-role lists are rejected by the shared title-quality guard before resolver calls

#### Scenario: Seed-audit reference tails are recovered or blocked

- **GIVEN** seed audit samples include real titles with citation tails such as `[C/OL]//...`, `-- Bioinformatics, 2020 [ Paper ] [ Software ]`, trailing `, with <authors>`, quote-plus-abbreviated-journal tails, or detached journal names
- **WHEN** homepage ingest or title-enrichment backfill prepares resolver candidates
- **THEN** the shared title cleaner recovers the underlying paper title before resolver calls
- **AND** standalone section labels, media/download labels, venue-only rows, journal date/DOI rows, issue/page fragments, CJK lab/project fragments, and author-list citation tails are rejected before resolver calls

#### Scenario: Subagent-audited title-quality defects are blocked without false positives

- **GIVEN** subagent audits find page-only paper rows such as `一种萘环改性的含芴聚芳醚及其合成方法，200710124809.5`, `Method and device for monitoring a machine store`, `一种用于经皮肾镜取石术的机器人辅助穿刺系统研究`, `Microgels: Synthesis, Properties and Applications (Chapter 12`, `Full paper list available at My Goolge Scholar`, `Traffic resilience ... Reliability Engineering & System Safety, 110095`, or `Domain decomposition ... IMA J. Numer. Anal.. 41(3):2139-2185 (2021)`
- **WHEN** title-enrichment backfill evaluates them before provider lookup
- **THEN** those rows are rejected as implausible paper titles before resolver calls
- **AND** legitimate titles such as `Mini-Emulsion Fabricated Magnetic and Fluorescent Hybrid Janus Micro-Motors`, `Symmetry Breaking and Other Nonlinear Elastic Responses of Metallic Glasses Subject to Uniaxial Loading`, and `Smoothing Splines and Rank Structured Matrices: Revisiting the Spline Kernel` remain eligible for title resolution

#### Scenario: Full seed success triggers shared paper bridge

- **GIVEN** an admin background seed task finishes a full professor seed run successfully
- **WHEN** the seed task completes
- **THEN** it runs the shared homepage paper ingest for the same `seed_id`
- **AND** owned homepage pages are included
- **AND** preview or sample seed runs do not run the full paper bridge automatically
- **AND** school-specific roster crawlers do not implement their own paper title resolution or enrichment logic

#### Scenario: Manual seed interruption remains visible

- **GIVEN** a seed has a latest or historical pipeline run with `failure_class='manual_interruption'`
- **WHEN** the admin seed registry lists seeds or loads that seed detail
- **THEN** the API returns 200
- **AND** the response includes `failure_class='manual_interruption'`
- **AND** the frontend labels it as an operator interruption instead of crashing on an unknown enum value

#### Scenario: Stored official page role is not downgraded

- **GIVEN** a `source_page` URL has already been stored with `page_role='official_profile'` or `page_role='official_publication_page'`
- **WHEN** the same URL is later upserted as `personal_homepage` or `lab_homepage`
- **THEN** the stored `page_role` remains the official role
- **AND** homepage paper ingest can still map the page to the stronger evidence tier

#### Scenario: Second-hop publication page preserves relation evidence

- **GIVEN** a professor-owned homepage links to a same-root publication page
- **WHEN** the shared homepage paper ingest bridge fetches that second-hop page and extracts publications from it
- **THEN** the second-hop URL is stored as a professor-owned `source_page`
- **AND** each relation extracted from that page stores the second-hop `page_id` in `professor_paper_link.evidence_page_id`
- **AND** cross-site publication URLs are not inserted as professor source pages

#### Scenario: Homepage recursion page outcomes are auditable

- **GIVEN** a professor-owned homepage links to same-root publication pages and cross-site publication-like pages
- **WHEN** the shared homepage paper ingest bridge runs outside dry-run mode
- **THEN** it records a homepage recursion ledger row for the root page and each publication-page candidate it considers
- **AND** same-root pages with extracted publications are recorded as `processed`
- **AND** same-root pages with detected publication sections but zero extracted papers are recorded as `zero_extraction`
- **AND** failed same-root page fetches are recorded as `fetch_failed`
- **AND** cross-site publication-like pages are recorded as `skipped` with a safety reason
- **AND** dry-run mode does not write ledger rows

#### Scenario: Non-person profiles cannot create verified paper links

- **GIVEN** crawler output or historical rows contain professor identities such as `Highlighted News`, `Deep Bit lab`, or `Lab Introduction`
- **WHEN** homepage paper ingest or title-enrichment backfill evaluates those rows
- **THEN** the rows are skipped before external title resolution
- **AND** no canonical paper row is upserted from those rows
- **AND** no `professor_paper_link` is written or migrated to `link_status='verified'`
- **AND** the skip is visible in diagnostics or report samples

#### Scenario: Profile-title pollution blocks relation migration

- **GIVEN** a professor row has a plausible name but its title/current-position field contains publication-body or patent-inventor text such as `Modified Peptide Nucleic Acids And Their Use. Inventors: ...`
- **WHEN** homepage paper ingest or page-only title-enrichment backfill evaluates linked page-only paper candidates
- **THEN** those candidates are not treated as safe verified professor-paper evidence
- **AND** title-enrichment backfill excludes them from automatic migration
- **AND** legitimate academic titles such as `助理教授` for `BRESAR, Miha` remain accepted

#### Scenario: Patent records are not paper publications

- **GIVEN** a homepage publication candidate is an actual patent record such as `Techniques for current sensing for single-inductor multiple-output (simo) regulators US Patent 16,553,759`
- **WHEN** the shared homepage paper ingest or title-enrichment backfill title-quality guard evaluates it
- **THEN** the candidate is rejected as a paper title before resolver calls
- **AND** papers whose real scholarly titles discuss patents remain eligible when they are not patent-record metadata

#### Scenario: Paper topic-search chat results are unique by paper

- **GIVEN** Milvus returns multiple chunks for the same paper during a paper topic search
- **WHEN** `/api/chat` builds the paper-topic answer
- **THEN** each paper appears at most once in citations
- **AND** each paper appears at most once in `structured_payload.matched_objects`
- **AND** the retained row prefers the highest score and available snippet metadata

### Requirement: Enrichment and summary preserve source truth

The system MUST attempt paper metadata, abstract, summary, full-text, and paper Milvus refresh follow-up for SIGS officially linked papers using existing paper-domain scripts and services. If a resolver or full-text source provides an abstract, `abstract_clean` MAY be written and `summary_zh` MAY be generated. If no source provides an abstract, the system MUST NOT fabricate `abstract_clean`.

When DOI metadata sources provide a PDF URL but no abstract, summary backfill MUST be able to try full-text extraction from that PDF before skipping the paper. DOI-based PDF discovery MAY use provider-specific PDF fields and Unpaywall when an email is configured. Failure to fetch or parse a PDF MUST leave the paper as reviewable or enrichment-needed rather than fabricating an abstract.

When a source-grounded abstract is already available in `paper_full_text.abstract` or is extracted from a DOI-provider PDF, summary backfill MUST persist it to `paper.abstract_clean` if the canonical abstract is empty. Frontend detail pages and retrieval indexes MUST NOT depend only on generated `summary_zh` when an English source abstract exists in the full-text table.

When no usable abstract exists but `paper_full_text.intro` contains source-grounded paper text, summary backfill MAY use that intro text to generate `summary_zh`. The system MUST record the source as `paper_full_text.intro`, MUST NOT persist intro text into `paper.abstract_clean`, and MUST NOT treat intro-only rows as satisfying the abstract requirement for `quality_status='ready'`.

When summary backfill is explicitly run with DOI/arXiv/OpenAlex metadata enrichment enabled, it MUST attempt metadata completion if any readiness-required field is missing, including venue, year, authors, or abstract. Existing source-grounded abstracts MUST NOT suppress venue/year/author completion, because quality promotion and retrieval ranking depend on the complete canonical metadata.

Paper Milvus refresh MUST support an explicit include-list of changed paper IDs. Operators MUST NOT need to misuse resume/checkpoint logs as include lists, because resume semantics skip listed IDs. When a summary-backfill JSONL log is used as an include-list, only successfully written paper rows MUST be selected; rejected, skipped, and error rows MUST be excluded.

Provider abstracts MUST pass the same usable-abstract gate as canonical and full-text abstracts before they are persisted to `paper.abstract_clean`. Empty strings, punctuation-only fragments, publisher notes, venue-only metadata, author-affiliation metadata, and citation metadata MUST NOT be promoted to canonical abstracts.

If Chinese summary generation returns an empty result or the boilerplate judge rejects the generated `summary_zh`, the system MUST clear or leave empty `summary_zh` but MUST keep the canonical paper row retryable. It MUST NOT terminally set `paper.quality_status='rejected'` solely because a summary generation attempt failed when the paper has valid official-page, DOI, OpenAlex, Crossref, DBLP, Semantic Scholar, arXiv, or full-text evidence.

Page-only papers without abstracts MUST remain in an enrichment or review-needed quality state and MUST retain diagnostic evidence explaining the missing metadata.

#### Scenario: Resolver abstract supports summary generation

- **GIVEN** a SIGS officially linked paper has resolver metadata with `abstract_clean`
- **WHEN** paper summary backfill runs for the professor or paper
- **THEN** the paper gets a source-grounded `summary_zh`
- **AND** a targeted paper Milvus refresh can include the changed paper

#### Scenario: Summary log can drive targeted Milvus refresh

- **GIVEN** a summary-backfill JSONL log contains rows with `status='written'`, `status='rejected_boilerplate'`, `status='skipped_no_usable_abstract'`, or error statuses
- **WHEN** paper Milvus refresh receives that log as an explicit paper-ID include-list
- **THEN** only paper IDs from written rows are refreshed
- **AND** rejected, skipped, and error rows are not refreshed
- **AND** resume/checkpoint skip semantics are not used for this include-list

#### Scenario: Page-only paper without abstract stays reviewable

- **GIVEN** a SIGS officially linked paper was created from page-only data and no resolver or full-text abstract is available
- **WHEN** summary and quality follow-up runs
- **THEN** `abstract_clean` remains empty
- **AND** the paper remains marked for enrichment or review
- **AND** a pipeline issue or equivalent diagnostic evidence records the unresolved metadata gap

#### Scenario: DOI PDF fallback is attempted before no-abstract skip

- **GIVEN** a linked paper has a DOI and provider enrichment returns a PDF URL but no usable abstract
- **WHEN** paper summary backfill runs with DOI metadata enrichment enabled
- **THEN** the system attempts full-text extraction from the provider PDF URL
- **AND** any extracted source-grounded abstract can support `abstract_clean` and `summary_zh`
- **AND** failed PDF extraction records an enrichment attempt and leaves the paper unsummarized

#### Scenario: Full-text abstract is promoted to canonical abstract

- **GIVEN** `paper_full_text.abstract` contains a usable source-grounded English abstract and `paper.abstract_clean` is empty
- **WHEN** paper summary backfill processes the paper
- **THEN** it persists that abstract to `paper.abstract_clean`
- **AND** the paper detail API and frontend can display the English abstract alongside `summary_zh`

#### Scenario: Full-text intro can generate Chinese interpretation without becoming an abstract

- **GIVEN** `paper_full_text.intro` contains usable source-grounded paper text but both `paper.abstract_clean` and `paper_full_text.abstract` are empty
- **WHEN** paper summary backfill processes the paper
- **THEN** it may generate `summary_zh` from the intro text
- **AND** the summary source is recorded as `paper_full_text.intro`
- **AND** `paper.abstract_clean` remains empty
- **AND** quality promotion treats the row as missing a real abstract and leaves it in a non-ready retryable status

#### Scenario: Same-run PDF intro supports summary generation

- **GIVEN** summary backfill runs with DOI metadata enrichment enabled and a provider PDF fetch returns no usable abstract but returns usable `intro` text
- **WHEN** the same paper is evaluated for Chinese summary generation in that run
- **THEN** the run uses the newly extracted intro text as the summary source without waiting for a later rerun
- **AND** the summary source is recorded as `paper_full_text.intro`
- **AND** the intro text is not written to `paper.abstract_clean`

#### Scenario: Existing abstract still allows metadata completion

- **GIVEN** a linked paper already has a source-grounded abstract and lacks a readiness-required field such as venue
- **WHEN** paper summary backfill runs with DOI metadata enrichment enabled and provider metadata supplies the missing field
- **THEN** the missing canonical metadata is persisted before summary promotion is evaluated
- **AND** the paper can be promoted to `ready` when title, year, venue, authors, abstract, and accepted `summary_zh` are all present

#### Scenario: Rejected generated summary does not reject paper evidence

- **GIVEN** a linked paper has valid official-page or identifier evidence and a usable English abstract
- **WHEN** summary generation returns an empty value or the boilerplate judge rejects the generated Chinese summary
- **THEN** `summary_zh` remains empty
- **AND** the paper remains in a retryable non-terminal status such as `partial` or `needs_enrichment`
- **AND** retrieval and future backfills do not exclude the paper solely because that summary attempt failed

#### Scenario: Unusable provider abstract is not persisted

- **GIVEN** DOI/OpenAlex/Crossref/Semantic Scholar/DBLP/arXiv enrichment returns a provider abstract that fails the usable-abstract gate
- **WHEN** summary backfill persists metadata enrichment
- **THEN** the unusable abstract is not written to `paper.abstract_clean`
- **AND** the paper is skipped for summary generation unless another usable canonical or full-text abstract is available

### Requirement: Frontend display and retrieval quality are both acceptance gates

SIGS rollout acceptance MUST verify both user-visible display quality and backend retrieval quality. A complete-looking frontend page is not sufficient unless the refreshed professor and paper records are also indexed and retrievable through the paper/professor retrieval path used by chat and search.

#### Scenario: Frontend shows complete professor and paper records

- **GIVEN** a SIGS professor has official profile data and officially listed papers with abstracts or summaries
- **WHEN** the admin frontend opens the professor and paper detail pages
- **THEN** the professor page shows complete identity, affiliation, homepage, research/profile fields, and linked papers
- **AND** each sampled paper page shows title, authors, year or venue when available, English abstract when available, Chinese `summary_zh` when generated, quality status, and source metadata
- **AND** `summary_text` and `summary_zh` aliases do not render duplicate summary blocks

#### Scenario: Backend retrieval recalls refreshed professor and paper records

- **GIVEN** SIGS professor and paper Milvus refresh has run after homepage ingest and summary backfill
- **WHEN** retrieval or chat searches by professor name, paper title, research topic, and abstract keywords
- **THEN** the expected professor and officially linked papers appear in the top results with source traceability
- **AND** results prefer `ready` records but do not hide reviewable page-only records when the query is explicitly about that professor's official publications
- **AND** retrieval evidence includes query text, expected IDs, returned IDs/ranks, domain, and pass/fail reason

#### Scenario: Exact paper title queries ignore natural question suffixes

- **GIVEN** a user asks about an exact English paper title followed by Chinese wording such as `这篇论文是什么` or `这篇论文主要讲什么`
- **WHEN** retrieval and chat classification parse the query
- **THEN** the natural-language suffix is removed from the title candidate
- **AND** the exact paper-title fallback can recall the expected paper
- **AND** chat returns the paper-profile path with source traceability instead of a generic topic search miss

### Requirement: SIGS rollout evidence reports parse and enrichment outcomes

The system MUST report SIGS rollout statistics for Ahmed first, then a random SIGS sample, then the full SIGS set before claiming completion.

Rollout readiness and recollection planning queries MUST tolerate historical `pipeline_run.run_scope` and `pipeline_issue.evidence_snapshot` records whose `seed_id` value is not a scalar integer string. Non-scalar or non-numeric legacy values MUST be ignored for seed matching rather than aborting the all-seed readiness matrix.

#### Scenario: Ahmed acceptance report

- **WHEN** the Ahmed single-professor bridge validation completes
- **THEN** the report includes official publication count, parsed count, canonical paper count, verified link count, resolver hit count, page-only count, abstract count, `summary_zh` count, full-text count, Milvus refresh count, and failure reasons

#### Scenario: Random SIGS sample report

- **WHEN** the random SIGS sample validation completes
- **THEN** the report includes per-professor official publication count, parsed count, ingested count, verified link count, abstract count, `summary_zh` count, and failure reasons
- **AND** the report includes frontend display checks and backend retrieval checks for the sampled professors and papers

#### Scenario: Legacy non-scalar seed IDs do not abort readiness planning

- **GIVEN** historical `pipeline_run.run_scope` or `pipeline_issue.evidence_snapshot` rows contain `seed_id` values such as JSON arrays rather than scalar integer strings
- **WHEN** recollection readiness loads the seed matrix
- **THEN** those legacy rows are ignored for seed matching
- **AND** scalar integer `seed_id` rows remain eligible as latest-run or latest-issue evidence
- **AND** planning can continue to preview, sample, or full recollection for unaffected seeds
