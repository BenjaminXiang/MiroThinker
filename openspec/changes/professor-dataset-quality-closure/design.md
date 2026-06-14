## Context

The previous `professor-core-profile-paper-quality` change closed the named
acceptance cases, but the real database audit still reports dataset-level
blockers:

- `ready_summary_lt_200:441`
- `missing_research_overview_zh:2510`
- `missing_professor_paper_summary:2200`
- `duplicate_verified_paper_title_year_groups:5186`

Those numbers represent different remediation classes. Some rows can be fixed
from already persisted official profile or paper-link evidence. Some require
bounded LLM translation or summarization. Some duplicate paper groups can be
merged by DOI/arXiv/title evidence, while others must remain unresolved until
there is enough public evidence. Treating all blockers as one bulk write would
make the data harder to audit and easier to corrupt.

This change defines the dataset-level closure contract that sits after the
case-level closure and before final Professor publishing/index validation.

## Goals / Non-Goals

**Goals:**

- Classify every remaining Professor/Paper blocker into deterministic buckets
  before write-mode remediation.
- Run bounded dry-runs for every automated remediation lane before writes.
- Repair short profile summaries, missing Chinese research overviews, missing
  Professor paper summaries, and duplicate verified paper links in controlled
  batches.
- Record batch-level evidence: input counts, write counts, skipped counts,
  unresolved reasons, quality-status before/after, API samples, and refresh
  selections.
- Convert records that cannot be repaired automatically into visible pipeline
  issues or residual-risk rows.
- Preserve the Professor core discovery boundary: official roster/profile pages
  seed Professors and Professor-linked papers; external providers enrich only
  those seeded paper candidates.

**Non-Goals:**

- Do not discover offline Professor papers by querying external providers with
  only a Professor name.
- Do not require hidden company, startup, or investment roles to exist in
  Professor core data.
- Do not run an unbounded all-dataset LLM/write pass without dry-run evidence.
- Do not change Agentic RAG query classification or runtime multi-source recall
  semantics.
- Do not claim final launch readiness; final validation remains owned by the
  Professor final-validation capability.

## Decisions

### 1. Use blocker buckets as the unit of planning

The closure runner should begin with a read-only audit that emits stable
blocker buckets, not just aggregate counts. Each row or duplicate group should
carry enough keys to reproduce the remediation decision: professor id, paper id
or duplicate group id, source page id or URL, blocker type, automatic
eligibility, skip reason, and proposed lane.

Alternative considered: start from the existing aggregate audit counts and
write scripts directly against broad SQL filters. That is faster but makes it
hard to explain why a specific record was written, skipped, or left blocked.

### 2. Keep remediation lanes separate

The four blocker classes need separate lanes:

- profile summary repair from persisted profile facts and official evidence;
- research overview section extraction or source-hash-keyed translation;
- Professor paper summary generation from deduplicated verified links;
- duplicate paper merge planning and title/identifier enrichment.

The orchestration may run these lanes in sequence for a batch, but each lane
needs independent dry-run and write counts. This avoids a failure in one lane
masking unrelated progress in another.

Alternative considered: create one monolithic "quality closure" command. That
would reduce operator steps but would make partial failure and rollback harder.

### 3. Require batch evidence before quality promotion

No batch should promote affected Professors to `ready` until the batch has:

- completed its write-mode remediation;
- rerun Professor quality re-evaluation;
- rerun duplicate/summary/research-overview audit checks for affected ids;
- sampled Admin Professor detail responses;
- selected affected rows for index refresh or recorded why refresh was skipped.

Alternative considered: let write scripts update quality state inline. That
risks stale quality statuses when later lanes fail or skip records.

### 4. Treat unresolved records as first-class output

Records that cannot be automatically repaired should not disappear from the
closure report. They should become pipeline issues or residual-risk rows with a
stable reason, such as missing official source text, unsafe summary input,
ambiguous duplicate merge, external provider timeout, or LLM output validation
failure.

Alternative considered: keep unresolved rows only in command logs. Logs are not
queryable enough for later audit, user-facing confidence, or reruns.

### 5. Preserve cross-domain boundaries

Professor core readiness remains independent from company/news association.
Runtime answers may use Professor, Company, News, Paper, and Patent data
together, but this closure should not attempt to scrape private or non-disclosed
company roles from Professor pages.

Alternative considered: make Professor closure fill company associations when
it sees relevant names. That couples two data domains and creates unsupported
claims for roles that many Professors do not disclose on official pages.

## Risks / Trade-offs

- [LLM variance] Generated Chinese summaries or translations can be shallow or
  inconsistent. Mitigation: use source hashes, validation gates, bounded
  batches, and issue creation for failed outputs.
- [False duplicate merges] Title/year similarity can merge unrelated papers.
  Mitigation: prefer DOI/arXiv matches, require author/venue evidence for fuzzy
  title groups, and preserve old-to-new merge aliases.
- [Provider instability] Crossref/OpenAlex/arXiv/DBLP requests can time out or
  rate limit. Mitigation: separate dry-run and write phases, cache results, and
  record provider failures without promoting affected Professors.
- [Over-strict readiness] Some records may remain blocked because source pages
  are incomplete. Mitigation: classify them as unresolved issues or accepted
  residual risks instead of silently lowering the quality bar.
- [Operational blast radius] Broad writes can touch thousands of rows.
  Mitigation: require batch sizes, per-batch verification, and rollback notes.

## Migration Plan

1. Add or extend read-only audit reporting to emit bucketed remediation
   candidates and unresolved blocker details.
2. Add dry-run modes for each remediation lane and record bounded sample output
   in the run verification file.
3. Execute write-mode batches only after dry-run evidence is recorded.
4. After each batch, rerun quality re-evaluation and affected-id audit checks.
5. Sample Admin Professor detail and Paper detail APIs for changed records.
6. Select changed Professor/Paper rows for retrieval/vector refresh and record
   skipped refresh rationale when refresh is not run.
7. Repeat until blockers are zero or every remaining blocker has a visible
   unresolved issue or accepted residual-risk row.

Rollback is operational rather than schema-based: stop the closure runner,
disable write mode, use run ids and batch reports to identify changed rows, and
restore only from recorded before/after evidence when a batch is judged unsafe.
Paper merge aliases should not be physically deleted without a recorded
counter-migration plan.

## Open Questions

- What default batch size should production operators use for LLM-backed
  summary and translation lanes?
- Should unresolved residual-risk rows be stored in `pipeline_issue`, a new
  closure report table, or both?
- Which index refresh path should be the first implementation target:
  Professor-only refresh selection or combined Professor/Paper refresh
  selection?
