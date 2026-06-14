# Design: paper-pipeline-cleanup

## Scope

This change removes the active legacy discovery surface left behind by
the page-first paper/patent flow. It is intentionally separate from
enrichment improvements so the codebase first stops offering the wrong
entry points.

## Discovery vs enrichment boundary

Allowed:

- parse Publications sections from professor Tier 2 / Tier 3 pages;
- resolve a page-declared paper candidate by DOI, arXiv id, title, or
  page-only fallback;
- enrich an already-discovered canonical row with metadata from
  OpenAlex, Crossref, Semantic Scholar, or arXiv.

Forbidden:

- querying any external literature database by professor name,
  institution, or author profile to generate the paper candidate list;
- keeping scripts that present hybrid/S2 discovery as an active release
  pipeline;
- importing retired discovery functions in production code.

## Cleanup strategy

1. Survey callers with `rg`.
2. Move any useful DOI metadata helpers behind enrichment names.
3. Rewrite or remove production callers.
4. Keep compatibility wrappers only if they raise `DeprecationWarning`
   and are not imported by production code.
5. Add a regression test that scans production source for forbidden
   imports/calls.

## Tests

The guard test should fail when these symbols appear in production
source outside explicitly allowed compatibility modules:

- `discover_professor_paper_candidates_from_hybrid_sources`
- `discover_professor_paper_candidates_from_crossref`
- Semantic Scholar author-profile discovery imports
- Google Scholar profile discovery imports
- ORCID paper discovery imports
- CV PDF discovery imports as a paper-list discovery source

## Rollback

The page-first ingest path remains intact. If cleanup breaks an
operational script, restore the script from git and mark it as legacy
outside the production path rather than reconnecting it to mainline.
