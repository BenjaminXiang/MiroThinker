# L4 Diagnosis — HIT(Shenzhen) total field-extraction failure (2026-06-16)

## Symptom
All 136 HIT(Shenzhen) professors: `primary_official_profile_page` has `fetched_at` set but `http_status=NULL`, `content_hash=NONE`, `title=''` — i.e. **0/136 pages have any fetched content**. Field fill-rate is 0% across every structured field (contact 4%).

## Findings (the pages ARE fetchable)
- Stored URL: `https://faculty.hitsz.edu.cn/<name>`.
- curl + httpx both succeed: `faculty.hitsz.edu.cn/<name>` → **301 redirect** → `https://homepage.hit.edu.cn/<name>` → **200**, ~18 KB, real `<title>` ("何道敬 - 哈尔滨工业大学教师个人主页"), name present in HTML.
- `httpx(follow_redirects=False)` → 301 (169 B); `httpx(follow_redirects=True)` → 200 (17,969 B).

## Root cause (two parts)
1. **Fetch bug (primary):** the crawler records `http_status=NULL` (an exception / no-response) for a URL that returns a clean 301→200. Leading hypothesis: the crawler's HTTP path does **not follow the `faculty.hitsz.edu.cn` → `homepage.hit.edu.cn` redirect** (no redirect-following code in `homepage_http.py`; httpx default `follow_redirects=False`), and the 3xx/redirect is being treated as no-usable-content or is erroring in the wrapper. The crawler already knows `homepage.hit.edu.cn` (`discovery.py:1573`, `_is_hit_seed`), so the canonical target exists — it's the redirect-follow that's broken.
2. **JS-rendered substantive data (secondary):** the 200 server HTML contains only the name + minimal labels (`研究方向` ×1, `邮箱` ×1, `@` ×1). **No** papers / education / work_experience / 职称 / 个人简介 in the static HTML → those are JS-rendered or on sub-pages.

## L4 fix (two parts)
- **(a) Fix the fetch:** follow the `faculty.hitsz.edu.cn` → `homepage.hit.edu.cn` redirect (or canonicalize the seed URL to `homepage.hit.edu.cn` at discovery). Recovers the static profile basics (name, research-directions label, email, page title) for all 136 — moves them off 0%.
- **(b) Substantive fields:** `homepage.hit.edu.cn` loads papers/education/work via JS → either find the page's XHR/data API (mirror the SIGS `teacher_api` precedent) or render via Playwright / follow publication & education sub-pages. Needed for papers/education/work — not solved by (a) alone.

## Next
- (a) is small + high-value (unblocks 136 profs from 0%). Implement first.
- (b) needs one more probe: inspect `homepage.hit.edu.cn/<name>` network calls / HTML for a data API or sub-page links.

## Probe result (2026-06-16) — L4(b) is tractable via a structured `.do` API + AES

`homepage.hit.edu.cn` is a **Java/Struts `.do`-API** jQuery/Bootstrap site (NOT a JS SPA). Substantive data is loaded by AJAX to `.do` endpoints with **AES-encrypted `?d=<payload>`** params; `scripts/utils/cjsUtils.js` (~1.3 KB) holds `CryptoJS.AES.encrypt/decrypt` (key/IV extractable). No server-rendered profile data, no inline data blobs.

Relevant endpoints (from `home-teacher-show.js` / `base.js` / page HTML):
- `showHP.do` — "show Home Page" — the **full-profile display endpoint** (research/papers/overview in one call). In-page reference.
- `SysTeacherBackgound/queryTeacherBackgoundAll.do` — **teacher background = education + work_experience** (maps directly to our `education`/`work_experience`/`academic_position`).
- `TeacherWhite/queryWhiteTeachersById.do`, `queryForParameter.do` — teacher identity/info.
- Publications: most likely returned by `showHP.do` (full profile); a dedicated paper module name not in the two JS files grepped (TBD, abbrev pinyin like `CgWz`/`Lw`).

**Tractability:** L4(b) = a **HIT `.do` adapter** that (1) replicates the AES `?d=` request (key from `cjsUtils.js`), (2) calls `showHP.do` + `SysTeacherBackgound/queryTeacherBackgoundAll.do`, (3) decrypts + maps to `professor_fact`/papers. This mirrors the SIGS `teacher_api` precedent — a structured per-teacher data API, strictly better than scraping the static HTML.

## Updated L4 plan (a + b as one HIT adapter)
- **(a) Fetch fix:** follow `faculty.hitsz.edu.cn` → `homepage.hit.edu.cn` 301 redirect (or canonicalize seed URL) — unblocks 136 profs from 0%, recovers static basics.
- **(b) HIT `.do` adapter:** AES-replicated calls to `showHP.do` (full profile + papers) + `SysTeacherBackgound/queryTeacherBackgoundAll.do` (education/work) → structured fields + papers. Mirror SIGS adapter; reusable for any `homepage.hit.edu.cn` teacher.
- Systemic note: the crawler follows redirects **nowhere** (`homepage_http.py`) — fixing (a) may also recover other 0-content redirect-only seeds.
