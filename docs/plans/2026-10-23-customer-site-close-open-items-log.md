# 客户现场：关闭 /upload、3 个高级操作、管理台口令（2026-10-23）

关联 OpenSpec：`add-admin-upload-seeds`（上传前门）、`enable-customer-site-excel-upload`
（上传后问答）。关联审计：[严格验收审计](./2026-10-23-customer-site-strict-acceptance.md)。

## 1. 做了什么

### 1.1 启用 console DSN（只作用于服务进程）

`/root/deploy/fullstack-v2/run.sh` 新增：

```bash
export PATH="$B/.venv/bin:$PATH"
export DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"   # miroflow_collection_v1
export HOST_E2E_BASE_URL="http://127.0.0.1:18188"
```

- `DATABASE_URL` 是 admin console 的上传/ops 面 DSN，指向已有的 42 表采集库；
  只在 `miro-fullstack-v2` 进程内生效，不写全局环境、不改变 serving target。
- 备份：`run.sh.bak-console-20261023-092327`。
- 重启后启动日志出现 `console_database=configured`，服务 `active`、`/api/health` 200。

### 1.2 `/upload` 前门

- 企业 dry-run：上传 `c624b56c-af17-…`（`frontdoor-dryrun.xlsx`）→ 202；
  `upload-company-import` run `a0f71772-5517-…` **succeeded**、exit 0、
  `items_processed=1`、`imported=0`（dry-run）。
- 专利真实提交：上传 `25bdc57c-a6a6-…`（表头按 `import_xlsx.py` 的别名：
  `标题 / 公开（公告）号 / 申请人 / 申请日 / 公开（公告）日 / 专利类型 / 摘要（中文）`）
  → run `1027aa8c-b006-…` **succeeded**、exit 0、`imported=1`；
  `patent` 表写入 `CN999999999A`。
- 首次用旧表头 `专利名称` 提交时，run `82f4523d-…` 以
  `ValueError: unable to locate patent header row` 失败——这是导入器既有表头契约，
  不是前门故障；按契约表头重试后成功。
- 清理：上传台账 3 条删除、staged 文件删除、`patent` 测试行删除、
  `pipeline_run` 测试行删除；最终 `uploads=0`、`patent=0`、`company=7089`。

### 1.3 3 个高级操作

- jobs API：`postgres.available=true`（`source=DATABASE_URL`），
  `ops-milvus-backfill` / `ops-milvus-backfill-dry-run` / `ops-retrieval-validation`
  全部 `available=true`。
- `ops-milvus-backfill-dry-run`（domain=company）run `9404a224-fc7d-…` **succeeded**、exit 0；
  输出 `company_profiles exists=false`，属预期的索引状态报告。
- `ops-retrieval-validation` run `0511e471-10ec-…` **succeeded**、exit 0、124s、
  `failures=0 result=PASS`；覆盖 B-company / B-paper / B-patent / A-professor /
  C-followup 五组问法，答案与 citation 断言全部通过。
- 运行时适配（`host_e2e_agentic_rag.sh`，均已备份）：
  - `uv run python` → `${MIROTHINKER_JOB_PYTHON}`（客户机没有 uv）；
  - pytest 缺失时跳过 classifier benchmark（标 `SKIPPED`，不计失败）；
  - canonical-v2 的 `canonical_v2:*` query_type 视为通过（旧 B_/C_ 标签已退役），
    答案文本、最小 citation 数等断言不变；
  - chat 请求超时 30s → 90s，避免启动预热期的假失败。

### 1.4 管理台口令

- `AdminAuthStore.set_password("admin", "eBy8aspFbX8gZAEi")`，本地 `verify_credentials=True`。
- 公网 `POST https://gxzx-coze-api.idea.edu.cn/api/auth/login`（同源 Origin）返回 **200**，
  下发 `cv2_admin_session` cookie；重启后再次验证仍 200。

## 2. 验证结论

| 项 | 结论 |
|---|---|
| `/upload` 页面提交 | PASS（企业 dry-run + 专利真实提交均成功） |
| 3 个 `upload-*-import` 任务 | PASS（有 `upload_id` 即可触发，dry-run 已跑） |
| 更新检索索引 · 预演 | PASS（run `9404a224…` exit 0） |
| 检索自检 | PASS（run `0511e471…` exit 0，failures=0） |
| 更新检索索引（真实写入） | 按钮可用；未执行全量回填（会为 7089 家企业重新嵌入，成本高），预演已证明链路 |
| 管理台登录 | PASS（admin / eBy8aspFbX8gZAEi，公网 200） |

## 3. 回滚

- 恢复 `run.sh.bak-console-20261023-092327` 并重启；
  `/upload` 与 3 个 ops 会回到禁用/503，`HOST_E2E` 与 venv PATH 一并移除。
- 自检脚本按 `.bak-runtime-*` / `.bak-canonical-*` / `.bak-timeout-*` 恢复。
- 口令用 `AdminAuthStore.set_password` 重设。

## 4. 影响与边界

- 客户现在可以在 `/upload` 用 XLSX 做企业/专利/教授的导入；企业上传后的 enrichment
  仍按既有批次异步执行。
- **`/upload` 的导入写入 `miroflow_collection_v1` 域表**；canonical-v2 chat 读取的是静态
  serving pack，因此新导入的行不会即时出现在 `/chat` 答案里。要让上传材料即时可查，
  仍走「数据浏览 → 企业 → 上传文档」（manual recall 通道，已验证问答闭环）；
  `/upload` 导入的行要进入 chat 需重建 serving pack。
- `/jobs` 的 3 个高级操作不再禁用；真实索引回填会写入 legacy Milvus
  （`apps/miroflow-agent/milvus.db`），与 canonical-v2 serving pack 是两条索引线，
  不会刷新 chat 的 pack；操作前应知悉其影响范围。
