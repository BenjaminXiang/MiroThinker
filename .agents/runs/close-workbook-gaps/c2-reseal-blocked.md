# C2.1r 重封印阻塞 — candidate_projection_result 契约代际不兼容（2026-09-10）

## 结论（一句话）

run14 包的 `relationships.json` 里 `candidate_projection_result` 是用**另一代候选投影契约**
（单数组 `projections` + `inclusion_decisions` + `counts_by_domain`，build_run_id
`p4-build-20260819-v1`，as_of 2026-09-07）封印的，部署线 loader 的
`CandidateProjectionResult` 模型（`public_domain_projections`/`person_projections`/
`technology_*`/`published_projections[7]`  typed 拆分）**无法 parse 该载荷**。
这不是 manifest 绑定失配，重封印器无法通过重算哈希修复——loader 在
`serving_pack_loader.py:699-703` 无条件用自有模型 parse 这段载荷。
**修复归数据线：用当前契约对 run14 数据重跑候选/关系投影封印，产出新 relationships.json 后，
C2.1r 重封印器（已就绪）可直接续跑。**

## 事件序列

1. C2.1r 重封印器已写出：`s12g/reseal_serving_pack.py`（worktree，449 行参考实现
   `s12c/build_serving_pack.py` 的同款 bootstrap/dogfood 写法，全程复用
   `serving_pack_loader` 内部函数与模型，source-pack/index-root 严格只读）。
2. 首次运行（日志 `.agents/runs/close-workbook-gaps/c2-reseal.log`）：
   `inputs_verified`(0.05s) → `carried_fields_verified`(0.13s) → `pack_files_copied`(8.8s) →
   **失败**：`ServingPackIntegrityError: serving pack relationships.candidate_projection_result
   failed typed validation`。
   失败点语义：重封印器按 loader 同款方式 `_parse_model(CandidateProjectionResult,
   relationships['candidate_projection_result'])`（loader 699-703 行同款），pydantic 校验拒绝。
   注意：在此之前 `internal_reference_projection_result` 和 `relationship_projection_result`
   已用当前模型 **parse 通过**——schema 失配隔离在 candidate 一段。
3. 按"语义矛盾 → 停下汇报"纪律停止；未改任何包文件，已清理半成品目录
   `serving-pack-run14-resealed/`（仅拷了 5 个文件、无 manifest，重跑要求目录不存在）。

## pydantic 错误全文（20 条，loc 去重）

- 8 条 `missing`（部署线模型必填、载荷没有）：
  `public_domain_projection_version`, `public_domain_projection_result_content_sha256`,
  `internal_reference_projection_result_content_sha256`, `public_domain_projections`,
  `person_projections`, `technology_concept_projections`, `technology_route_projections`,
  `published_projections`
- 12 条 `extra_forbidden`（载荷有、部署线模型禁止）：
  `projection_version`, `catalog_schema_version`, `catalog_version`,
  `catalog_content_sha256`, `inclusion_result`, `inclusion_result_content_sha256`,
  `approved_source_scope_manifest_sha256`, `projections`, `rejected_projections`,
  `inclusion_decisions`, `manifest`, `counts_by_domain`

## 代际对比证据

| 来源 | candidate 顶层键 | 规模 | 当前模型可 parse？ |
|---|---|---|---|
| s12f 生产包（18188 现役） | 新契约 typed 拆分 | 5,659 public_domain_projections | ✅（每日生产启动证明） |
| run9 / serving-pack / old-run12（p4 世代，三者 relationships.json 逐字节相同，sha256 3e9d3496…，2.41G） | 新契约 typed 拆分 | 32,941 public_domain_projections / person 0 / tech 0 / published 7 | ✅（实测 model_validate 通过） |
| **run14（3.09G，sha256 f6a682b5…）** | **旧契约单数组**：`projections`(47,071：company 7,089 / paper 24,520 / patent 11,504 / professor 3,958) + `inclusion_decisions`(47,071) + `rejected_projections`(0) + `counts_by_domain` + `manifest`(list) + `catalog_*` + `inclusion_result*` + `approved_source_scope_manifest_sha256`；build_run_id `p4-build-20260819-v1`，as_of 2026-09-07T15:56Z | 47,071 | ❌（20 条校验错误） |

- run14 的 `projections` **元素**字段形状与 s12f `public_domain_projections` 元素几乎相同
  （company 投影：aliases/as_of/business_scenarios/canonical_identity_id/…/registered_address 等），
  是**容器契约**不同（单数组+收录清单 vs typed 拆分+7 条 published_projections），不是字段语义大变。
- 当前数据线代码（`.worktrees/data-rebuild` 的 `candidate_projection.py:244`）与部署线
  **同为新契约**——即数据线早已迁移，run14 的 relationships.json 是旧代管线
  （build_run_id 字面量 `p4-build-20260819-v1`）对 2026-09-07 数据的产物。
- run14 载荷中**不存在** person/technology 拆分投影（顶层无相关键）；transcode 需要
  发明或另找来源，且要构造 7 条 published_projections 绑定——属于契约决策，非 builder 权限。

## 与设计的关系

design.md「Setback 2026-09-10」节预判的疑似陈旧字段（`index_result_content_sha256`、
`index_policy_snapshot`、`index_rebuild_decisions`、`index_projection_request_sha256`、
`build_manifest.published_projections`）仍是事实且重封印器都能修复；但本节揭示的是
**更深一层**：relationships.json 载荷本身的契约代际。重封印器的 dogfood 硬门设计
（"禁止手工改包文件，语义矛盾停下汇报"）正是为这种情况准备的。

## 放行条件（建议，归主上下文/数据线决定）

数据线对 run14 数据（47,071 projections，as_of 2026-09-07 或更新）用**当前契约**重跑
候选+关系投影封印，产出新的 relationships.json（其余 4 个包文件可保留），然后：
1. 重跑 `s12g/reseal_serving_pack.py`（命令同 c2-reseal.log 头部）；
2. dogfood 若暴露 `index_projection_request_sha256`/request 层失配，迭代重封印器；
3. 通过后续跑 C2.1b–e（18189 命令的 `--serving-pack` 改指 resealed 目录）。

## 现场状态

- 重封印器源码：worktree `s12g/reseal_serving_pack.py`（随本报告提交）。
- 重封印日志：主仓 `.agents/runs/close-workbook-gaps/c2-reseal.log`。
- 半成品目录已删除；source pack 与 index root 全程只读未动；18188 生产未动。
- C2.1b–e 仍阻塞。C2.1c 的 lookup 侧实测数据（可提前采信）：run14 lookup SQLite
  四域 exact-lookup 文档数 company 7,089 / paper 24,520 / patent 11,504 /
  professor 3,958 = 47,071（与设计预期一致）；绑定类指标（优必选 459 等）需
  relationships 可用后测量。
