# Source Links

## Consulted

- `apps/miroflow-agent/src/data_agents/paper/title_resolver.py`
  - title_resolver.py:353 — the web-tier acceptance site
    (`web_match.match_confidence >= _CONFIDENCE_THRESHOLD`).
  - `_web_hit_to_resolved` at title_resolver.py:1357 — constructs the web
    candidate with hard-coded `authors=()` (title_resolver.py:1372) and
    `year=None` (title_resolver.py:1373); extracts DOI/arxiv_id only from
    `doi.org`/`arxiv.org` hostnames at title_resolver.py:1382-1387 as metadata,
    never as a gate.
  - `_title_jaccard` at title_resolver.py:419 — the title leg reused by the
    gate.
  - `_author_name_tokens` at title_resolver.py:1098 and `_normalize_author_name`
    at title_resolver.py:1105 — the author-tokenization primitives the new
    `_author_token_jaccard` helper is built on.
  - `_is_scholarly_link` at title_resolver.py:1350 — the scholarly-domain
    whitelist that prunes non-scholarly hosts before the gate runs (not
    modified).
  - `_search_web_by_title` at title_resolver.py:951 — the caller that iterates
    `organic` hits, filters by `_is_scholarly_link`, and selects the best
    `_web_hit_to_resolved` result.
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
  - homepage_ingest.py:2096 — the `resolve_paper_by_title` caller.
  - homepage_ingest.py:2106-2117 — the `is_page_only = resolved is None` branch
    and the `_synthesize_page_only_resolution` page-only fallback that consumes
    a `None` result.
- `apps/miroflow-agent/src/data_agents/professor/paper_identity_gate.py` — the
  LLM paper-identity verifier. Consulted to confirm it is NOT reused; the gate
  is deterministic and introduces no LLM call.
- `apps/miroflow-agent/src/data_agents/professor/name_utils.py` — consulted for
  author-normalization prior art; the gate reuses the title_resolver-local
  `_author_name_tokens`/`_normalize_author_name` instead to keep the change
  self-contained.

## Extracted

- The web tier's acceptance logic: pure title-Jaccard >= 0.85 at
  title_resolver.py:353, with `authors=()`/`year=None` in the candidate at
  title_resolver.py:1372-1373 and DOI/arxiv_id as ungated metadata at
  title_resolver.py:1382-1387.
- The `_author_name_tokens` (title_resolver.py:1098),
  `_normalize_author_name` (title_resolver.py:1105), and `_title_jaccard`
  (title_resolver.py:419) helpers reused by the new gate and
  `_author_token_jaccard` helper.
- The page-only fallback contract: `is_page_only = resolved is None` at
  homepage_ingest.py:2106 and `_synthesize_page_only_resolution` at
  homepage_ingest.py:2114.
