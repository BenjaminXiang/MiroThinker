# D9: Professor Homepage Maintenance — Seed List Recovery

## Institution Coverage (from professor pool, 2026-09-07)

| Institution | Professors | Likely Faculty Page URL |
|---|---|---|
| 深圳大学 | 1,068 | https://www.szu.edu.cn/ + department pages |
| 南方科技大学 | 981 | https://faculty.sustech.edu.cn |
| 哈尔滨工业大学（深圳） | 724 | https://faculty.hitsz.edu.cn |
| 清华大学深圳国际研究生院 | 277 | https://www.sigs.tsinghua.edu.cn |
| 中山大学（深圳） | 189 | https://sz.sysu.edu.cn |
| 深圳技术大学 | 177 | https://www.sztu.edu.cn |
| 深圳理工大学 | 145 | (newly established, check) |
| 北京大学深圳研究生院 | 61 | https://pkusz.edu.cn |
| 香港中文大学（深圳） | 30 | https://www.cuhk.edu.cn/zh-hk |

## Seed Recovery Status

The original `professor_seed` table is in the root-owned migration tar
(`/home/longxiang/mirothinker-migration/stage/postgres/pgdata-candidate-s12f.tar`).
Recovery requires root access to extract and restore a PostgreSQL data
directory.

**Pragmatic alternative**: reconstruct the seed list from the professor
pool's institution distribution (above) + known faculty page URLs.
The `professor-seed-management` spec defines the table schema:
`(school, department, seed_url, last_run_at, last_run_status)`.

## Next Steps
1. Create fresh `professor_seed` entries for the 9 institutions above
2. Verify each faculty page URL is accessible
3. Configure the periodic crawl schedule (monthly recommended)
4. Cherry-pick the SZU crawler from `archive/szu-seed5-quality-20260613`
