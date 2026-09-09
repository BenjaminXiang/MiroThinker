---
title: "W9-4: name-identity scan JSONL 归档"
date: 2026-04-30
owner: codex
spec: .agents/specs/2026-04-30-w9-4-name-identity-archive.md
slice: 1 of 1（单 slice）
status: ready
---

# W9-4 handoff（单 slice 即可完成）

## CRITICAL — codex CLI 代理

任何 codex CLI 调用前：

```bash
export https_proxy=http://100.64.0.14:10003
export HTTPS_PROXY=http://100.64.0.14:10003
```

不设这个 proxy 会 hang。这与 python pipeline 用的 `100.64.0.15:7893`（CLEAR）是两个不同的 proxy。

## Read order

1. **本 handoff**
2. `.agents/specs/2026-04-30-w9-4-name-identity-archive.md` — 完整 spec；§6 给出 CLI / JSONL 字段定义
3. `apps/miroflow-agent/scripts/run_name_identity_scan.py` — 现有 284 行 script
4. `apps/miroflow-agent/src/data_agents/professor/name_identity_gate.py` — 看 NameIdentityDecision 实际字段名
5. `docs/source_backfills/README.md` — 现有 backfill 条目格式

## Files

**MODIFY**:
- `apps/miroflow-agent/scripts/run_name_identity_scan.py`
  - 加 `--json-output` 与 `--archive` 两个 flag（互斥）
  - main() 主循环加 emit JSONL append
  - 完成后 emit summary line
  - DSN 解析时只暴露 host + db name，不带密码

- `docs/source_backfills/README.md`
  - 增 `round-7-17-name-identity-clear-YYYY-MM-DD.jsonl` 条目（spec §6.4 给了模板）

**CREATE**:
- `apps/miroflow-agent/tests/scripts/test_run_name_identity_scan_archive.py`
  - 6 个测试（spec §12 evidence 列了）

**RUN（生成数据归档）**:
- 对 `miroflow_real` 跑一次完整 scan + archive：
  ```bash
  https_proxy 与 100.64.0.15:7893 都不要设（这是 python script，需直连）
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
  cd apps/miroflow-agent
  uv run python scripts/run_name_identity_scan.py \
    --confirm-real-db \
    --apply \
    --archive \
    --auto-clear-threshold 0.5
  ```
  验证产出 `docs/source_backfills/round-7-17-name-identity-clear-{今日 UTC date}.jsonl`，最后一行 `summary: true`

**注意**：实际跑 scan 是 codex 的运维步骤，不属于代码改动；产出数据文件 commit 进 git。

## Do-not rules

- ❌ 不动 `name_identity_gate.py`（gate 已稳定）
- ❌ 不动 `pipeline_issue` 表的写入逻辑
- ❌ 不动 现有 stdout 行为（"Examined: %d" 等仍打印）
- ❌ DSN 中**绝不**写入密码或 userinfo 部分
- ❌ 不要让旧 CLI 调用方式破坏（`--json-output` / `--archive` default 必须是 None / False）
- ❌ 不要在 dry-run 模式下写 pipeline_issue（保持现有行为）

## 实施提示（spec 已覆盖，这里强调易错点）

1. JSONL 文件 mode = `'a'`（append），**不**用 `'w'`
2. `--archive` 互斥 `--json-output`：用 `argparse` 的 mutually_exclusive_group
3. 日期使用 UTC：`datetime.now(timezone.utc).strftime("%Y-%m-%d")`
4. `ensure_ascii=False` 让中文姓名直出
5. summary 行**仅**在 scan 完整结束后 emit；如 KeyboardInterrupt 不应 emit
6. 测试中 mock `batch_verify_name_identity` 返回固定 decisions，避免依赖真实 LLM

## Tests / checks

```bash
cd apps/miroflow-agent

# 单测
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/scripts/test_run_name_identity_scan_archive.py \
  -n0 --no-cov

# 现有 scan 测试不破坏
DATABASE_URL_TEST=$DATABASE_URL_TEST uv run pytest \
  tests/scripts/ \
  -k "name_identity" \
  -n0 --no-cov

# 烟测：dry-run 对 test DB（不需 LLM 真实可达；mock 即可）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
DATABASE_URL=$DATABASE_URL_TEST uv run python scripts/run_name_identity_scan.py \
  --institution "南方科技大学" \
  --json-output /tmp/w9-4-smoke.jsonl
test -f /tmp/w9-4-smoke.jsonl
tail -1 /tmp/w9-4-smoke.jsonl | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert d.get('summary'), 'last line not summary'; print('OK')"

# 真实归档（对 miroflow_real，单独跑）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
DATABASE_URL=$DATABASE_URL uv run python scripts/run_name_identity_scan.py \
  --confirm-real-db --apply --archive --auto-clear-threshold 0.5
ls docs/source_backfills/round-7-17-name-identity-clear-*.jsonl
```

## Done criteria

1. ✅ `--json-output` / `--archive` 两个 flag 已加；互斥；行为符合 spec §6
2. ✅ 6 个单测全过
3. ✅ 现有 scan 调用不破坏（旧 CLI 仍可用）
4. ✅ 对 `miroflow_real` 跑 1 次归档；产出文件 ≥ 1 行 + summary 行；入 git
5. ✅ `docs/source_backfills/README.md` 更新条目
6. ✅ DSN 中无密码暴露（grep 归档文件确认无 `miroflow:miroflow` 字符串）

## Stop conditions

- `NameIdentityDecision` 字段名与 spec §6.2 不符（如 `accepted` 改为 `is_accepted` 等）→ 报告差异，按实际字段适配后继续
- `_load_rows` 在 test DB 上空集（institution filter 太严）→ 用更宽 filter 或先 seed 测试数据
- `miroflow_real` 上跑 scan 异常（LLM gate 失败 / DB 连接失败）→ stop，报错给 claude review
- 归档文件 > 10MB → stop，可能有逻辑错误（一次 scan 不应这么大）

## Report format（按 AGENTS.md §9）

```text
Summary: <2 行>

Changed files:
- scripts/run_name_identity_scan.py: 加 --json-output/--archive 流式输出
- docs/source_backfills/README.md: 新条目
- tests/scripts/test_run_name_identity_scan_archive.py: 6 测试
- docs/source_backfills/round-7-17-name-identity-clear-YYYY-MM-DD.jsonl: 归档（数据）

Verification:
- pytest test_run_name_identity_scan_archive.py: <N passed>
- 现有 name_identity 测试回归: <N passed>
- 烟测 dry-run: 文件生成 + summary 行 OK
- 真实归档对 miroflow_real: examined=N rejected=M issues_inserted=K cleared=L

Risks/notes:
- <实际归档数字与历史 178/557 是否一致；不一致原因>
- <DSN 暴露 grep 确认>
- <文件大小>
```
