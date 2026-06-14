# Acceptance Evidence: prof-blocked-seed-source-remediation

Status: pending implementation.

P5 is complete only when each requirement below has current-session evidence
and the row-level E2E matrix for seed ids 5 and 25-28 is recorded.

## Requirements

| Requirement | Evidence status | Evidence |
|---|---|---|
| P5 source audit for blocked professor seeds | Verified for audit phase | 2026-05-25 no-env diagnostics covered seed ids 5 and 25-28 without DB writes. Current URLs remain blocked: seed 5 HTTP 412 with 0 Chinese chars / 0 anchors; seeds 25-28 HTTP 202 tokenized pages with 0 Chinese chars / 0 anchors. Browser probe for seed 5 failed with `net::ERR_CONNECTION_CLOSED`. |
| UESTC official mentor source coverage | Verified for UESTC rows | Official yjsjy URLs are reachable for seed ids 25-28: `yxsh=28&zydm=085400` has 157 mentor links, `085404` has 44, `085405` has 7, and `085500` has 11. The named adapter `uestc-yjsjy-mentor-roster` now resolves both yjsjy replacement URLs and original SIAS seed URLs, preserves yjsjy mentor detail URLs, and preview E2E succeeded for seed ids 25-28 with `limit=2`. |
| SZU CSSE official replacement gate | Verified as blocked with context | SZU central teacher index is official and reachable but only links to the blocked CSSE URL. AISC faculty page is official and reachable with 12 person links, but it is a research-center roster, not a full CSSE roster. SZU HR has no CSSE roster. No accepted full replacement source exists in this P5 audit, so seed 5 remains `fetch_blocked` with remediation context. |
| P5 E2E evidence matrix | Verified | Seed ids 25-28 have current-session preview E2E success rows. Seed id 5 has current-session preview E2E `fetch_blocked` evidence with refreshed issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`. |
| Previously blocked seeds are remediated before P5 completion | Verified with one approved residual block | Seed ids 25-28 are remediated through official yjsjy replacement URLs. Seed id 5 has no accepted official full-roster replacement and remains explicitly blocked. |
| Refreshed blocked evidence records source-remediation context | Verified | Seed 5 issue evidence now includes `source_remediation.decision=official_replacement_not_found`, the rejected official candidates, `accepted_replacement_url=null`, and the current run id `49cbea16-617e-4d25-bf6c-b10db1c3f6bb`. |

## Source Audit Matrix

| seed_id | current_url_status | current_shape | accepted_replacement | rejected_or_pending_sources | decision |
|---:|---|---|---|---|---|
| 5 | HTTP 412; browser `net::ERR_CONNECTION_CLOSED` | 15,570 chars, 0 Chinese chars, 0 anchors, token markers | none yet | SZU central teacher index: official gateway only; AISC faculty: official but 12-person center roster only; SZU HR: no CSSE roster | Keep auditing or refresh `fetch_blocked` if no full official roster is found |
| 25 | HTTP 202 | 2,408 chars, 0 Chinese chars, 0 anchors, token markers | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085400` | SIAS current URL remains blocked | Implement yjsjy adapter path |
| 26 | HTTP 202 | 2,459 chars, 0 Chinese chars, 0 anchors, token markers | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404` | SIAS current URL remains blocked | Implement yjsjy adapter path |
| 27 | HTTP 202 | 2,500 chars, 0 Chinese chars, 0 anchors, token markers | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405` | SIAS current URL remains blocked | Implement yjsjy adapter path |
| 28 | HTTP 202 | 2,484 chars, 0 Chinese chars, 0 anchors, token markers | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085500` | SIAS current URL remains blocked | Implement yjsjy adapter path |

## P5 E2E Matrix

Each final evidence row MUST include:

```text
seed_id, original_url, replacement_url, resolver_result, trigger_mode, command,
terminal_status, candidate_count, items_processed, items_failed,
pipeline_run_status, pipeline_issue_outcome
```

| seed_id | original_url | replacement_url | resolver_result | trigger_mode | terminal_status | candidate_count | items processed/failed | pipeline_run_status | issue outcome |
|---:|---|---|---|---|---|---:|---:|---|---|
| 5 | `https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1` | none accepted | `szu-teacher-family` | preview, limit 2 | failure / `fetch_blocked` | 0 | 0/1 | failed | refreshed issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`; source remediation decision `official_replacement_not_found` |
| 25 | `https://sias.uestc.edu.cn/rcpy/dsjs1/dzxx2.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085400` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 157 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 26 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jsjjs/jsjjs.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085404` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 44 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 27 | `https://sias.uestc.edu.cn/rcpy/dsjs1/rjgc/rjgc.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085405` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 7 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
| 28 | `https://sias.uestc.edu.cn/rcpy/dsjs1/jx/gyhlwyznzz.htm` | `https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=28&zydm=085500` | `uestc-yjsjy-mentor-roster` | preview, limit 2 | success | 11 source links; 2 diagnostic profiles | 0/0 | succeeded | historical `fetch_blocked` issue retained; no new issue |
