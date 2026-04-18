# Source Backfills

本目录存放为了真实 workbook / PRD 验收而补入的可追溯 source backfill。

当前文件：
- `paper_exact_identifier_backfills.jsonl`: 精确论文标识 backfill，当前包含 `pFedGPA`。公开来源：Crossref DOI / AAAI article / arXiv。
- `patent_exact_identifier_supplement.xlsx`: 精确专利号 backfill，当前包含 `CN117873146A`。公开来源：Google Patents 页面。
- `company_workbook_critical_supplement.xlsx`: workbook 关键公司对象补点源，当前覆盖 `普渡 / 开普勒 / 云迹 / 擎朗 / 九号 / 嘉立创 / 深南电路 / 一博科技 / 迈步机器人`，并补入 `跨维 / 光轮智能 / 银河通用 / 群核科技` 这批行业路线代表厂商。
- `company_knowledge_fields.jsonl`: company serving-side 知识字段 backfill，当前覆盖 `q11-q16` 所需的 `data_route_types / real_data_methods / synthetic_data_methods / capability_facets / movement_data_needs / operation_data_needs` 等结构化字段。
- `professor_company_roles.jsonl`: professor-company 关系 backfill，当前包含 `丁文伯 -> 深圳无界智航科技有限公司` 的证据链，用于 shared-store consolidate 时补入 `company_roles`。

使用方式：
- `run_paper_release_e2e.py` 会在文件存在时自动加载 `paper_exact_identifier_backfills.jsonl`，也可通过 `--supplement-jsonl` 显式传入。
- `run_patent_release_e2e.py` 会在文件存在时自动加载 `patent_exact_identifier_supplement.xlsx`，也可通过 `--supplement-patent-input` 显式传入。
- `run_company_release_e2e.py` 会在文件存在时自动加载 `company_workbook_critical_supplement.xlsx`，也可通过 `--supplement-input` 显式传入。
- `consolidate_to_shared_store.py` 会在文件存在时自动加载 `company_knowledge_fields.jsonl` 与 `professor_company_roles.jsonl`，并在 shared-store consolidate 时补入 serving-side 结构化字段与关系。
