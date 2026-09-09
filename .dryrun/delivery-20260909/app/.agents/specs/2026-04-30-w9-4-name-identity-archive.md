---
title: "W9-4: Round 7.17 name-identity 清除量化日志归档"
date: 2026-04-30
owner: claude
status: ready-for-codex
audience: codex（实施）
wave: Wave 9
gap: "#9"
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_solutions:
  - docs/solutions/data-quality/name-identity-gate-round-7-17-2026-04-18.md
---

# W9-4: Round 7.17 name-identity 清除量化日志归档

## 1. Goal

Round 7.17 的 name-identity gate（双语姓名身份校验）已落地（`professor/name_identity_gate.py` + `scripts/run_name_identity_scan.py`）。我们之前 plan 中提到 "178/557 污染清除" 的数字，但**没有量化日志归档**——重新跑一次 scan 没有可对比的"前一次结果"，导致：

- 数字无法验证（声称 178/557 但仓库里没有这次扫描的输出）
- 无法做"哪些教授被 reject 了" 这种追溯
- 后续如果再跑 scan，无法对比"上次哪些是新增 / 哪些是稳定"

本 spec 让 `run_name_identity_scan.py` 输出结构化 JSONL 到 `docs/source_backfills/`，每次 scan 自动归档，建立可重复的量化基线。

## 2. Non-goals

- **不**改 `name_identity_gate.py` 的核验逻辑（gate 已稳定，本 spec 仅扩输出能力）
- **不**重新跑 scan 然后用新数字覆盖历史的 178/557（历史声明保持，作为 plan / commit message 中的非验证性背景；本 spec 起的归档是从今往后的）
- **不**实现增量 scan（每次都全量扫；增量是后续 wave 的事，需先有版本化的 audit table）
- **不**改 pipeline_issue 的写入（仅扩 stdout/JSONL 输出）

## 3. User-visible behavior

- 新增 CLI 选项 `--json-output PATH`：scan 过程中每处理一个 professor 实时 append 一行 JSONL 到 PATH
- 新增 CLI 选项 `--archive`：**等价于** `--json-output docs/source_backfills/round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl`，自动按当天日期生成文件名
- scan 结束后在 stderr 打印 `archived to <path>` 提示
- 日志最后一行是 summary aggregate（`{"summary": true, "examined": N, "rejected": N, ...}`）
- 不影响现有 stdout 行为（"Examined: %d" 等仍然打印）
- `docs/source_backfills/README.md` 增条目，说明文件用途与字段

## 4. Affected paths

```
MODIFY:
  apps/miroflow-agent/scripts/run_name_identity_scan.py
    + add --json-output / --archive flags
    + 在 main() 主循环中 emit JSONL
    + 完成后 emit summary line

  docs/source_backfills/README.md
    + 增条目"name-identity-clear-YYYY-MM-DD.jsonl"

CREATE:
  apps/miroflow-agent/tests/scripts/test_run_name_identity_scan_archive.py
    + 测试 --json-output / --archive flag 行为

NEW DATA FILE（运行 scan 后自动生成，本 spec 内不预先创建）:
  docs/source_backfills/round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl
```

## 5. Architecture / Data flow

```
psql (miroflow_real or miroflow_test_mock)
        ↓
   _load_rows(institution_filter)
        ↓
   batch_verify_name_identity(candidates, llm_client)  ← name_identity_gate
        ↓
   for (row, decision) in zip(...):
        ↓
   stats.examined += 1
   if decision.rejected:
       stats.rejected += 1
       if --apply: insert pipeline_issue + maybe clear name_en
   →→→ NEW: emit JSONL line（include row + decision + action_taken + run_id + timestamp）
        ↓
   全部处理完后:
   →→→ NEW: emit summary line（{"summary": true, ...stats}）
        ↓
   close JSONL file，print "archived to <path>" 到 stderr
```

## 6. Interface contracts

### 6.1 CLI 接口扩展

```python
# scripts/run_name_identity_scan.py 既有参数:
#   --institution / --apply / --auto-clear-threshold / --confirm-real-db / --database-url
# 新增:
parser.add_argument("--json-output", type=Path, default=None,
    help="Stream per-professor decisions as JSONL to this path. Append mode.")
parser.add_argument("--archive", action="store_true",
    help="Equivalent to --json-output docs/source_backfills/round-7-17-name-identity-clear-{today}.jsonl. "
         "Mutually exclusive with --json-output.")
```

### 6.2 JSONL 行格式

**Per-professor 行**：

```json
{
  "professor_id": "PROF-XXXXXXXXXXXX",
  "canonical_name": "张三",
  "canonical_name_en_before": "Wang Wu",
  "institution": "南方科技大学",
  "source_url": "https://...",
  "decision": "rejected",
  "confidence": 0.12,
  "reason": "canonical_name 与 candidate_name_en 不一致：'张三' vs 'Wang Wu'",
  "action_taken": "issue_filed_and_name_en_cleared",
  "apply_mode": true,
  "scan_started_at": "2026-04-30T07:21:33Z",
  "examined_index": 17
}
```

字段定义：

- `decision`: `"accepted"` 或 `"rejected"`（来自 `NameIdentityDecision.accepted`）
- `confidence`: 0.0–1.0 浮点；LLM gate 返回值
- `reason`: gate 提供的拒绝理由（accepted 时为空字符串）
- `action_taken`: 4 个枚举值之一：
  - `"none"` - decision = accepted（无操作）
  - `"would_file_issue"` - decision = rejected & dry-run（未应用）
  - `"issue_filed"` - rejected & --apply & 阈值不达标（仅 file issue 不 clear）
  - `"issue_filed_and_name_en_cleared"` - rejected & --apply & 阈值达标（file issue + clear）
  - `"would_clear"` - rejected & dry-run & 阈值达标（理论会 clear 但 dry-run）
- `apply_mode`: 与 `--apply` 对齐
- `scan_started_at`: 整次 scan 启动时间（同一次 scan 所有行相同）
- `examined_index`: 在本次 scan 中的处理顺序（1-based）

**Summary 行**（最后一行）：

```json
{
  "summary": true,
  "scan_started_at": "2026-04-30T07:21:33Z",
  "scan_finished_at": "2026-04-30T07:23:02Z",
  "duration_seconds": 89,
  "institution_filter": null,
  "apply_mode": true,
  "examined": 557,
  "rejected": 178,
  "issues_inserted": 178,
  "clear_updates": 178,
  "would_clear": 0,
  "auto_clear_threshold": 0.5,
  "database_dsn_host": "localhost:15432",
  "database_name": "miroflow_real"
}
```

DSN 必须只暴露 host + database name，**不**包含密码或完整 URL。

### 6.3 文件命名

- `--archive` flag → `docs/source_backfills/round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl`
  - 日期使用 UTC 当天（避免时区问题）
  - 同一天多次跑会 append（不覆盖）—— 符合 streaming 语义
- `--json-output PATH` 直接 append 到指定路径
- 同一文件 reopen 用 `mode='a'`（append），允许多次 scan 累积

### 6.4 source_backfills/README.md 新增条目

```markdown
- `round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl`: Round 7.17 name-identity gate scan 量化日志，
  每行记录一个被处理的教授决定（accepted / rejected / cleared / etc）。最后一行为 summary aggregate。
  使用方式：`scripts/run_name_identity_scan.py --apply --archive` 自动归档。
  字段定义见 `.agents/specs/2026-04-30-w9-4-name-identity-archive.md` §6.2。
```

## 7. Invariants

1. JSONL 文件 mode 必须是 append（不 truncate），避免 race condition 覆盖历史
2. 每个 professor 的行必须 emit 在该 professor 处理完成（apply / dry-run 决定后）才写，**绝不**预 emit
3. summary 行**必须**在所有 per-professor 行之后；如 scan 中途崩溃则没有 summary（消费方应判 last_line.summary == True 来识别完整 scan）
4. DSN host + db name 可写入；password / userinfo 部分**绝不**写
5. `--json-output` 与 `--archive` 互斥（参数冲突时 exit 2）
6. JSONL 编码统一 UTF-8 + ensure_ascii=False（中文姓名直出）
7. 已有 stdout 行为不破坏（"Examined: %d" 等仍打印）；JSONL 是**附加**输出
8. 不依赖 OpenAI/网络（gate 用本地 Gemma-4 LLM）；本 spec 不引入新的外部依赖

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| `--archive` 时 `docs/source_backfills/` 不存在 | mkdir parents=True；不报错 |
| 同一文件已存在（同日重复 scan） | append；不覆盖 |
| scan 中途 KeyboardInterrupt | 已写的行保留；summary 行不写；下次 scan 用同文件继续 append |
| `--json-output` 路径不可写（权限） | exit 2 + stderr 报错 |
| `decision.reason` 为 None | 写为空字符串 `""` |
| `row.source_url` 为 None | 写为 null（JSON null） |
| 无教授匹配 institution filter | summary 行 examined=0；rejected=0；正常退出 0 |
| `--archive` 与 `--json-output` 同时给 | exit 2 + stderr 提示互斥 |
| `--archive` 在非 UTC 时区机器上跑 | 文件名使用 `datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")` |

## 9. Failure modes

- 主流程（gate 调用、DB 写入）失败：原行为不变（current main() 行为保留）
- JSONL 写失败（disk full / permission）：当前行 stderr 提示后跳过，scan 继续；不阻塞主流程
- summary 行写失败：stderr 警告；scan 退出码仍为主流程结果

## 10. Migration / rollback

- 无 schema 变更；纯脚本扩展
- 回滚：revert commit；旧 CLI 调用方式不受影响（新参数 default 都是 None / False）

## 11. Validation commands

```bash
cd apps/miroflow-agent

# 单测
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/scripts/test_run_name_identity_scan_archive.py \
  -n0 --no-cov

# 现有 scan 命令不破坏（dry-run 模式，对 test DB）
DATABASE_URL=$DATABASE_URL_TEST uv run python scripts/run_name_identity_scan.py \
  --institution "南方科技大学" \
  --json-output /tmp/test-scan.jsonl

# 归档模式（test DB；不要对 miroflow_real 直接跑，需 --confirm-real-db）
DATABASE_URL=$DATABASE_URL_TEST uv run python scripts/run_name_identity_scan.py \
  --institution "南方科技大学" \
  --archive

# 验证文件存在 + 最后一行是 summary
test -f docs/source_backfills/round-7-17-name-identity-clear-$(date -u +%Y-%m-%d).jsonl
tail -1 docs/source_backfills/round-7-17-name-identity-clear-$(date -u +%Y-%m-%d).jsonl | jq '.summary'
# → true
```

## 12. Expected evidence（提交时附）

- ✅ `tests/scripts/test_run_name_identity_scan_archive.py` 至少 6 个测试：
  1. `--json-output PATH` 写入正确格式
  2. `--archive` 生成正确文件名
  3. `--archive` 与 `--json-output` 互斥
  4. summary 行格式正确
  5. append 模式（同文件重复跑）
  6. DSN 不暴露密码
- ✅ 实际跑 1 次完整 scan（对 `miroflow_real` with `--confirm-real-db --apply --archive`）后归档的 JSONL 文件
- ✅ `docs/source_backfills/round-7-17-name-identity-clear-{YYYY-MM-DD}.jsonl` 入 git
- ✅ `docs/source_backfills/README.md` 更新

## 13. Assumptions

- `name_identity_gate.batch_verify_name_identity` 当前返回的 `NameIdentityDecision` 结构稳定（含 `accepted` / `confidence` / `reason` 字段；如果不是这些字段名，codex 实施时按实际字段适配）
- `_load_rows` 既有逻辑能正确工作；不动
- Gemma 4 LLM 可达（之前已测过；如不可达则脚本本身也会失败，不是本 spec 引入的新问题）

## 14. Open questions（claude 自决，2026-05-01）

- [x] **JSONL 行格式**：用 per-professor + final summary 双层结构（vs 单一 list）→ 选 streaming append（容错性更好）
- [x] **同日重复 scan 是覆盖还是 append**：append（保留所有 scan 历史，下游判 last summary 行识别完整 scan）
- [x] **是否归档 dry-run 结果**：是。dry-run 也归档（`apply_mode: false` 字段标识）；价值在于"看模型当前怎么判"
- [x] **是否需要 archived JSONL 入 git**：是。便于 review + 团队共享。文件大小约 ~100KB / 千条记录，可承受
- [x] **历史 178/557 数字怎么处理**：保留作为非验证性背景；本 spec 起的归档建立从今往后可验证基线。不重新跑去"对照"

**所有阻塞 codex 实施的决策已锁定；本 spec 状态：`ready-for-codex`**。

## 15. 与其他 spec / Shared-Spec 的衔接

- Shared-Spec §7.3 MiroThinker 验证与补采：本 spec 完成后，"重点验证对象"段加一句 "Round 7.x scan 输出统一 JSONL 归档到 `docs/source_backfills/`"
- W13-2 (E2E dogfood 归档机制)：W9-4 是它的先例；W13-2 把同模式推广到 4 域 retrieval Top-K 基准
- W9-2 (run_id wiring)：scan 脚本未来如果加 run_id 关联，本 spec 的 JSONL 可直接加 `run_id` 字段；当前不强制（scan 是独立任务，不属于 V3 pipeline run）
