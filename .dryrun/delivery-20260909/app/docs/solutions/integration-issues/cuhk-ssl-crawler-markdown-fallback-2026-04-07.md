---
title: "CUHK(SZ) Crawler: SSL Fallback to Jina Reader Markdown Extraction"
date: "2026-04-07"
category: integration-issues
module: src/data_agents/professor
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "Professor pipeline V3 discovers 0 professors from all CUHK(SZ) departments"
  - "Python requests.get() fails with [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] for *.cuhk.edu.cn"
  - "Jina reader fallback returns markdown instead of HTML, silently bypassing HTML extractors"
  - "No errors in logs — generic extractor silently returns empty list for CUHK page structure"
root_cause: wrong_api
resolution_type: code_fix
tags:
  - cuhk-shenzhen
  - ssl-tls
  - jina-reader
  - markdown-fallback
  - professor-crawler
  - site-specific-extractor
  - dual-format-parsing
---

# CUHK(SZ) Crawler: SSL Fallback to Jina Reader Markdown Extraction

## Problem

CUHK(SZ) (Hong Kong Chinese University, Shenzhen) teacher-search pages returned 0 professors in the professor pipeline V3. Two independent failures compounded: (1) no site-specific HTML extractor existed for CUHK's non-standard page structure, and (2) Python's TLS stack cannot negotiate with `*.cuhk.edu.cn` servers, so `fetch_html_with_fallback()` silently falls back to Jina reader which returns markdown — but the extractor only handled HTML.

## Symptoms

- `discover_professor_seeds()` returns 0 professors for all CUHK(SZ) seeds (SSE, SAI, SDS, MED)
- Discovery status: `"unresolved"` with `reason="no_professor_entries_found"` for every CUHK seed URL
- No errors or exceptions in logs — silent empty result
- `[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE]` in debug logs from `requests.get()` for `*.cuhk.edu.cn`
- `curl` works fine for the same URLs — the SSL issue is specific to Python's ssl module
- Jina reader fallback succeeds but returns markdown content (prefixed with `Title:` and `Markdown Content:`)

## What Didn't Work

1. **Generic recursive discoverer**: The generic extraction pipeline in `extract_roster_entries()` tries `_extract_card_links()`, `_extract_generic_profile_links()`, and `_extract_markdown_profile_links()` — all fail because:
   - Card extraction requires CSS class tokens `{"t-name", "name"}` — CUHK uses `list-title`
   - Generic profile extraction requires path hints (`/teacher/`, `/faculty/`, `.htm`) — CUHK profile URLs like `https://myweb.cuhk.edu.cn/cuishuguang` have none

2. **HTML-only site-specific extractor (Codex's initial fix)**: A `_extract_cuhk_profile_links(soup)` using CSS selector `div.list-title a` was added. Unit tests passed with mock HTML. But in production, `fetch_html_with_fallback()` hits SSL failure → Playwright unavailable → Jina reader returns markdown → BeautifulSoup parses markdown, finds no `div.list-title` → returns empty list.

## Solution

### Fix 1: Site-specific HTML extractor (`roster.py`)

```python
def _extract_cuhk_profile_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for title_anchor in soup.select("div.list-title a"):
        href = str(title_anchor.get("href", "")).strip()
        name = _extract_candidate_person_name(title_anchor.get_text(" ", strip=True))
        if not name or not _is_likely_professor_name(name):
            continue
        if href:
            links.append((href, name))
    return links
```

### Fix 2: Markdown fallback extractor (`roster.py`)

```python
def _extract_cuhk_markdown_profile_links(markdown: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for label, href in _iter_markdown_links(markdown):
        parsed = urlparse(href)
        hostname = (parsed.hostname or "").lower()
        if not hostname.endswith("cuhk.edu.cn"):
            continue
        if "teacher-search" in parsed.path:
            continue
        name = _extract_candidate_person_name(label)
        if not name or not _is_likely_professor_name(name):
            continue
        links.append((href, name))
    return links
```

### Fix 3: Site-specific discoverer with pagination and dual extraction (`discovery.py`)

```python
def _discover_cuhk_seed(seed, fetch_html):
    # ...
    for page_index in range(50):  # 50-page safety cap
        page_url = _cuhk_page_url(seed.roster_url, page_index)
        html = fetch_html(page_url)
        soup = BeautifulSoup(html, "html.parser")
        profile_links = _extract_cuhk_profile_links(soup)
        if not profile_links:
            profile_links = _extract_cuhk_markdown_profile_links(html)  # Fallback
        if not profile_links:
            break
        # ... build DiscoveredProfessorSeed from profile_links ...

def _is_cuhk_seed(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("cuhk.edu.cn") and "teacher-search" in parsed.path
```

The critical dual-extraction pattern:
```python
profile_links = _extract_cuhk_profile_links(soup)      # Try HTML first
if not profile_links:
    profile_links = _extract_cuhk_markdown_profile_links(html)  # Markdown fallback
```

## Why This Works

**Structure mismatch**: The HTML extractor uses the correct CSS selector `div.list-title a` for CUHK's specific page structure, rather than the generic class tokens (`t-name`, `name`) that don't match.

**SSL/TLS content format mismatch**: Python's `ssl` module fails the TLS handshake with `*.cuhk.edu.cn` (`SSLV3_ALERT_HANDSHAKE_FAILURE`). The server likely requires cipher suites or TLS parameters that Python doesn't support (curl uses different TLS settings and works). `fetch_html_with_fallback()` catches this and falls back through: `requests` (SSL fail) → Playwright (not installed) → Jina reader (returns markdown). The dual-extraction pattern handles both formats.

**Pagination**: CUHK lists ~10 professors per page with `?page=N` Drupal pagination. The `_cuhk_page_url()` helper constructs pagination URLs, and the 50-page safety cap prevents infinite loops.

## Prevention

1. **Always implement both HTML and markdown extraction paths for site-specific discoverers.** The `fetch_html_with_fallback` chain can return either format. Pattern:
   ```python
   profile_links = _extract_site_html(soup)
   if not profile_links:
       profile_links = _extract_site_markdown(raw_content)
   ```

2. **Test with actual live URLs in E2E, not only mock HTML.** SSL/TLS incompatibilities only surface with real connections. Unit tests with mock HTML verified the HTML extractor but could not catch that HTML would never be returned in production.

3. **Audit the full `fetch_html_with_fallback` chain when adding new university support.** Check whether `requests.get()` can reach the target. If it can't (SSL errors, anti-scraping), determine which fallback provides content and ensure the extractor handles that format.

4. **Cross-validation between implementer and reviewer catches format assumptions.** The HTML-only fix passed unit tests. The markdown fallback gap was caught by tracing the actual production execution path through `fetch_html_with_fallback`.

## Verification

- **343 unit tests** pass (0 regressions)
- **E2E (CUHK(SZ), 2 schools)**: 74 discovered (from 0), 2 released, 0 blocked, all Gemma 4 200 OK
- **All 9 universities tested**: 6/9 pass at time of writing; 3 were blocked by quality gate (data sparsity, not crawler issues) — resolved by quality gate L1→L2 demotion, see `docs/solutions/logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md`

## Files Modified

| File | Change |
|------|--------|
| `src/data_agents/professor/roster.py` | `_extract_cuhk_profile_links()`, `_extract_cuhk_markdown_profile_links()`, CUHK branches in site-specific dispatch functions |
| `src/data_agents/professor/discovery.py` | `_discover_cuhk_seed()`, `_is_cuhk_seed()`, `_cuhk_page_url()`, dispatch hook, imports for `parse_qsl`/`urlencode`/`urlunparse`/`BeautifulSoup` |
| `tests/unit/data_agents/professor/test_roster.py` | Unit test for CUHK HTML extraction |
| `tests/unit/data_agents/professor/test_discovery.py` | Unit test for CUHK discovery with pagination |
| `tests/data_agents/professor/test_roster_validation.py` | Updated expected reason string from `no_professor_entries_found` to `cuhk_teacher_search_empty` |

## Related Issues

- `docs/solutions/integration-issues/gemma-4-llm-integration-proxy-and-provider-compat-2026-04-06.md` — Predecessor documenting proxy/SSL issues. Proxy clearing is a prerequisite; the CUHK SSL failure persists even after proxy is cleared. Proxy evolution: `trust_env=False` (Apr 2) → fetch cache (Apr 5) → `_clear_proxy_env()` (Apr 6) → **site-specific Jina reader fallback (Apr 7)**
- `docs/solutions/professor-pipeline-v2-deployment-patterns-2026-04-05.md` — Section 6 documents the same SSL symptom class with fetch-cache mitigation; Jina reader markdown fallback is the more robust approach for persistently-failing SSL sites
