# D9 Adapter Verification Notes (2026-09-08)

## SUSTech (faculty.sustech.edu.cn)
- Main page: WordPress shell, professor list loaded via JS
- WP REST API: disabled (non-JSON responses)
- retrieval/logs.js: 403 Forbidden (anti-bot)
- Department links: ?field=XX系&lang=zh (server returns same shell)
- **Conclusion**: Needs headless browser or API bypass

## HITSZ (faculty.hitsz.edu.cn)
- Returns 271 bytes (likely redirect page)
- **Conclusion**: Follow redirect or find correct URL

## PKU SZ (pkusz.edu.cn)
- Connection refused
- **Conclusion**: Check if URL is correct

## SZU CS (cs.szu.edu.cn)
- DNS resolution failure
- **Conclusion**: Domain may be different (try cse.szu.edu.cn?)

## Next Steps
1. User to verify correct URLs in browser
2. Consider headless browser (Playwright) for JS-rendered pages
3. Alternative: use each school's public API or data export if available
4. The archived SZU crawler (archive/szu-seed5-quality-20260613) may have working URLs
