# Tasks

## 1. Verification contract and baseline

- Create `.agents/runs/title-resolver-web-attribution-gate/verification-contract.md`
  classifying the change and selecting the RED artifact (unit tests for the gate
  predicate and the fail-closed path) and GREEN (gate passes for accepted hits,
  returns `None` for rejected hits, DB tiers unchanged).
- Record the baseline: the current web tier accepts on title-Jaccard >= 0.85
  alone at title_resolver.py:353 with `authors=()`/`year=None` at
  title_resolver.py:1372-1373.

## 2. Author extraction in `_web_hit_to_resolved`

- In `_web_hit_to_resolved` (title_resolver.py:1357), replace the hard-coded
  `authors: tuple[str, ...] = ()` (title_resolver.py:1372) with best-effort
  extraction from the hit's snippet and any structured fields the web_search
  provider returns.
- Extraction may yield `()` when no author signal is present; that is the
  expected input to the author leg of the gate.

## 3. `_author_token_jaccard` helper

- Add `_author_token_jaccard(author_hint, authors)` built on
  `_author_name_tokens` (title_resolver.py:1098) and `_normalize_author_name`
  (title_resolver.py:1105), mirroring `_title_jaccard` (title_resolver.py:419).
- Return 0.0 when either token set is empty so the author leg cannot pass on a
  missing signal.

## 4. Web-tier attribution gate at title_resolver.py:353

- At title_resolver.py:353, accept `web_match` only when:
  `(web_match.doi is not None OR web_match.arxiv_id is not None) OR
  (_title_jaccard(query_title, web_match.title) >= 0.85 AND
  _author_token_jaccard(author_hint, web_match.authors) >= 0.30)`.
- On rejection, return `None` (title_resolver.py:357) and do not cache.
- Scope the gate to the web tier only; do not touch the five DB tiers or their
  0.85 `_CONFIDENCE_THRESHOLD`.

## 5. Tests (RED before GREEN)

- Web hit with a DOI is accepted (gate passes on the identifier path).
- Web hit with an arxiv_id is accepted (gate passes on the identifier path).
- Web hit with title Jaccard >= 0.85 and author-token Jaccard >= 0.30 is
  accepted (gate passes on the title+author path).
- Web hit with title Jaccard >= 0.85, no identifier, and author-token Jaccard
  < 0.30 is rejected -> `resolve_paper_by_title` returns `None`.
- Web hit with title Jaccard < 0.85 is rejected -> returns `None`.
- Regression: the cache, OpenAlex, Crossref, arXiv, and S2 tiers are unchanged
  (a DB hit still returns regardless of the web gate).

## 6. Real evidence (dry-run)

- Dry-run the change on a sample of web-resolved papers and measure the reject
  rate (share of previously-accepted web hits that now fail closed to
  page-only).
- Inspect a sample of rejected hits to confirm they are wrong-attribution
  candidates, not legitimate matches.
- Record results in
  `.agents/runs/title-resolver-web-attribution-gate/verification.md`.

## 7. Acceptance, validate, ledger

- Run the acceptance checks in `acceptance.md`.
- Update `openspec/change-ledger.md` and `openspec/debt-register.md` if the
  change surfaces new debt (for example, a high reject rate that signals a need
  for the year-consistency open question).
