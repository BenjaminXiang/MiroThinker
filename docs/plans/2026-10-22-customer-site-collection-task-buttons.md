# 客户现场：其余采集更新按钮启用（2026-10-22）

关联 OpenSpec：`enable-customer-site-collection-task-buttons`
关联前序：`2026-10-22-customer-site-company-news-job.md`

## 1. 问题

`/jobs` 页面除「企业新闻采集」外的采集按钮：

- 企业官网产品重抓：可点，但默认输入 XLSX 不在客户包内，立即失败；
- 论文检索回填 / 摘要回填 / DOI 校验：可点，但采集库只有企业表，0 条空跑；
- 教授主页重爬 / 论文增量：可点，但采集库没有教授、没有主页记录，0 条空跑；
- 论文检索回填还缺 `paper-search-mcp` 依赖。

产品要求（2026-10-22）：其余采集按钮也要能点、能跑出结果。

## 2. 方案

- 从 serving pack 的 `lookup_document` 回填一批真实数据到采集库：
  - `paper` 500 行（200 缺摘要、200 缺中文摘要、100 待 DOI 校验）；
  - `professor` 200 行 + `source_page` 200 行 + `professor_seed` 185 行。
- 企业产品：从 `company` 生成 200 行输入 XLSX（sheet `sheet1`）。
- 安装 `paper-search-mcp==0.1.4`。
- 给 6 个非新闻采集任务加单次上限：50/20/50/100/20/10。
- 重启服务，让 `/jobs` 加载新 argv。

## 3. 验收

- 6 个脚本逐一 `--limit 1`（或实际 `--limit 5`）跑通，exit 0，且有处理条数。
- 7 个采集按钮全部 `available=true`；3 个 ops 仍禁用；导入/Seed 仍是跳转链接。
- `/api/health`、`/main`、`/chat` 200；serving candidate DB/pack/index 未动。

## 4. 回滚

- 恢复 `jobs.py.bak-limit-*`；删除生成的 XLSX；删除 `canonical_source='manual'` 的回填行和
  pilot 教授；卸载 `paper-search-mcp`；重启。
- 采集库之外不动。

## 5. 不在本次范围

- `ops-milvus-backfill` / 预演 / 检索自检：需要构建期 PostgreSQL 和索引工具链；
- 3 个上传导入：需要可写构建库和上传台账；
- 2 个 Seed 刷新：需要 Seed 控制台 DB。
