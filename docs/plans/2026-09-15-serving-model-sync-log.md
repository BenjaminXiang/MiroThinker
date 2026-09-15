# 服务线模型同步：让服务包接受 D0-a 的置空字段（2026-09-15）

## 做了什么

run16 包会携带 D0-a 的"占位值 → 置空"：9 个投影字段在数据线已改为可空
（CompanyProjection：`profile_summary`、`technology_route_summary`；ProfessorProjection：
`department`、`email`、`homepage`、`paper_summary`、`patent_summary`、`profile_summary`、`title`）。

在隔离 worktree `feat/serving-model-sync`（基于服务线 `codex/canonical-v2-s12a-ready` @
`5afdb6f6`）做最小同步，三个提交：

| 提交 | 内容 |
|---|---|
| `e9f2e974` | `domain_projection_models.py` 9 字段改 `X \| None = None`（与数据线副本 `diff` 为空，逐字节一致；未引入清洗模块） |
| `eff2a793` | 新回归测试 `test_serving_projection_optional_fields.py`（6 例；fixture 取自 run15 真实记录的去标识化派生） |
| `57877ebc` | 证据笔记 `.agents/runs/serving-model-sync/verification.md` |

## 发现了什么

1. **boot 拒载机制证实**：`serving_pack_loader.py` 解析 pack 的
   `relationships.json → candidate_projection_result` 时按模型逐条校验、fail-closed；RED 运行
   4 例失败并点名 9 个字段（`ServingPackIntegrityError: ... failed typed validation`）。
2. **封印同样会撞这 9 个字段（新事实，影响切包顺序）**：sealer 解析
   `CompleteCandidateBuildEnvelope` 时把 `index_projection_request.candidate_projection_result`
   按 `CandidateProjectionResult` 校验（`index_projection.py:263-265`）。所以**运行封印的服务线树
   必须同时已含 P1（v2 sealer）与本同步**，否则 run16 包连封印都过不去。
3. **没有任何回退**：run15 包仍可装载——两次 scratch 装载（全哈希路径 336.1s / 回执路径 333.5s）
   都 OK，且模型重算的全包哈希 = run15 manifest 值 `6ad4c090…`（逐字节一致）；装载数量
   7,086 公司 / 24,520 论文 / 11,504 专利 / 3,958 教授、51,026 points、47,068 lookup docs。
4. **一处已知 None 不安全点（非本次路径）**：`index_projection.py:754`
   `projection.department.name`，仅索引物化/信封 replay 可达（数据线副本已有守卫；pack 的
   boot/查询路径不经过）。若服务线将来用 run16 形态投影做索引物化，需先修。

## 怎么验证

- RED/GREEN：`uv run pytest tests/canonical_v2/test_serving_projection_optional_fields.py` →
  改前 `4 failed, 2 passed`（错误点名 9 字段）→ 改后 `6 passed`。
- 回归：13 个服务线相关文件，改前 `4 failed, 204 passed, 2 skipped` → 改后
  `208 passed, 2 skipped`；失败集差异**只有**新增的 4 条 RED 用例。
- 未跑（并说明原因）：重的构建/读取套件（`test_knowledge_build_isolated` 等）——首次尝试在
  慢用例处 >25 分钟未完成即停（既有慢，非挂死）；读取路径改为静态复核 None 安全。

## 影响哪些问题

- 解除 run16 切包的**服务线模型闸**（原为"必做未知项"）。
- 把切包顺序钉死为：**服务线合入 P1 + 本同步 → 封印 v2 包 → 切换命令文件 + 重启 → replay/探针**；
  顺序写进 [run16 发射 Runbook](./2026-09-15-run16-launch-runbook.md) §2.1/§4。
- 对应 OpenSpec：`data-cleaning-batch1`（D0-a 的 9 字段可空）在服务线侧的承接。
