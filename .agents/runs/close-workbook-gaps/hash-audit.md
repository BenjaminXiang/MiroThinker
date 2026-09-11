# 哈希审计清单（S1 · 2026-09-11）

> 只读审计（explore agent），范围：serving/pack/release 路径。目的：用户裁定
> 「证据优先 vs 一切可证明」后的**瘦身候选清单**。删除动作按 S2/S3 执行，
> 每项必须先有 boot/replay/差分三重等价证据。
> 路径：`loader`=serving_pack_loader.py；`sealer`=s12c/build_serving_pack.py；
> `idx`=index_projection.py；`serve`=knowledge_serving_isolated.py；`ctr`=contracts.py；
> `read`=knowledge_read.py；`chat`=admin-console canonical_v2_chat.py。

## 主表

| 哈希/字段 | 位置 | 防的具体故障 | 类 | 建议 | 依据 |
|---|---|---|---|---|---|
| `index_marker_sha256` | loader:146,518 | 起动错索引根/target 与包不符 | 工件完整性+版本绑定 | 保留 | 包与索引根唯一物理锚 |
| `files[marker]` | loader:554-557 | 包内 marker 副本被换 | 工件完整性 | 简删候选 | 与上行同值（×3 重复）；活根 marker 已由 `_validate_target_marker` 校验 |
| `files[lookup.sqlite3, milvus.db]` | loader:554-557 | 包内 1.75GB 字节拷贝截断/篡改 | 工件完整性 | **简删候选** | 启动打开的是 `manifest.index_root`（loader:534-545,632-642），**包内拷贝从不被读**；唯一读者是 `deploy/backup-canonical-v2.sh:34-35`（同脚本也备 index-v1）。删除=省 boot 期 1.75GB 哈希 |
| `files[relationships.json, institution_catalog.json]` | loader:559-576 | 3.3GB 载荷落盘后被改/截断 | 工件完整性 | 保留 | 唯一字节级校验；其余校验都建立在解析+重序列化之上 |
| `index_result_content_sha256` | loader:644-674 | **半封印包**（p4 绑定 vs run14 索引） | 复现证明+版本绑定 | 保留 | 实测拦下（c2-scratch-boot-failure.md 原文 traceback） |
| `index_policy_snapshot`/`index_rebuild_decisions` | loader:652-663 | 策略/重建决策掉代 | 版本绑定 | 保留（无独立哈希） | 被上行整体哈希覆盖 |
| `relationship_request_sha256` | loader:733-739 | request 与 scalars 重建不一致（C2.1p 的 `supplementary_field_values`） | 复现证明 | 保留 | 只有它能发现"scalars 未透传新字段" |
| `relationship_result_content_sha256` | loader:688-698 | 关系结果替换/跨 release | 版本绑定 | 保留 | 与 relationships.json 内值同源 |
| `candidate_projection_result_content_sha256` | loader:699-711 | 旧代候选契约被解析成新模型 | 版本绑定 | 保留 | c2-reseal-blocked.md：20 条 pydantic 错误在此暴露 |
| `internal_reference_projection_result_content_sha256` | loader:676-687 | 内部引用结果掉代 | 版本绑定 | 保留 | 与 candidate 交叉绑定 |
| `index_projection_request_sha256` | loader:799-805 | request 与 scalars 代差（第二次拒封点） | 复现证明 | 保留 | c2-seal-blocked.md 落此 |
| `institution_catalog_content_sha256` | loader:599-603 | catalog 与 manifest 不同代 | 版本绑定 | 保留(机制)/现状待定 | run14 包 catalog `entries: []`，当前防护值为零 |
| `release_verification.manifest_sha256` | ctr:1565; loader:626-630 | verification 绑到别的 manifest | 版本绑定 | 保留 | loader 强制等于 BuildManifest 同名值 |
| `build_manifest.manifest_sha256` | ctr:1507; loader:612-619 | manifest 内 47,112 个哈希被改 | 审计派生（链根） | 保留 | 唯一覆盖分节哈希者 |
| 分节哈希（ManifestSection/ProjectionManifest/IndexProjectionManifest） | ctr:1411,1451,1476 | 分节记录被改 | 审计派生 | **冻结** | 内容不在包内，服务期无独立消费者 |
| `entity_ids_sha256` | ctr:1475 | 点集漂移 | 版本绑定 | 待定 | 空投影写空串哈希（manifest 出现 6 次），对空集无鉴别力；与 content_sha256 重叠 |
| `source_batches_sha256` | ctr:1494 | 构建输入变更 | 版本绑定 | **冻结** | 服务期不校验，仅随链根 |
| sealer 侧 file_hashes/request 哈希 + dogfood 全等比较 | sealer:256-275,328-332,382-401 | 封印写错文件/封出 loader 打不开的包 | 复现证明 | 保留 | 把 C2 两次"拒封"前移到构建期 |
| `IndexProjectionPoint.embedded_content_sha256` | idx:184 | 向量点与嵌入文本脱钩 | 冗余链式 | 保留 | 物理行独立列 + point_json 同值，读回交叉校验 |
| `source_projection_content_sha256` | idx:126,182 | 点/文档与源投影脱钩 | 版本绑定 | **冻结** | 解析期自洽校验，无独立消费点 |
| `LookupProjectionDocument.lookup_content_sha256` | idx:128,160 | 检索文本被改 | 工件完整性 | 保留 | 自绑定 + C2 剥键事件中被连带暴露 |
| Receipt 4 门哈希 | idx:321-326 | 绕过 S2B 写入门的重建 | 审计派生 | **冻结** | 服务期无消费者（收据自哈希保留） |
| `RecordedServingBundle.content_sha256` | serve:205-228,5928 | bundle 换 release/被改 | 版本绑定 | 保留 | 启动链 fail-closed；C2 切换即靠此 |
| `RecordedServingInputs.authority_sha256` | serve:251,6107 | — | 冗余链式 | **简删候选** | 静态检索 `apps/` 无任何读取点（仅声明+赋值） |
| `PlanningReleaseBinding` 8 哈希 | read:685-696; loader:1390-1404 | plan 混入非本 release authority | 版本绑定 | 保留 | readi:980 区 fail-closed 校验 |
| `PlanningTrace.proposal_sha256` | read:682,4830 | — | 审计派生 | **简删候选** | 全仓仅测试断言 |
| `QueryPlanningRequest` 自哈希/`original_query_sha256` | read:327-332,361-382 | 请求被改/候选清单不符 | 复现证明 | 保留 | 自绑定校验，proposal 侧消费 |
| `RecordedPlanningProposal.request_sha256` | read:480,4629 | proposal 对错请求 | 复现证明 | 保留 | `proposal_request_mismatch` fail-closed |
| `AnswerSelectionProposal.selection_input_sha256` | knowledge_answer.py:246,1867 | 组稿对错 turn | 复现证明 | 保留 | 不符即降级 `input_binding_mismatch` |
| `ReleaseVerification` evidence_ids + `CandidateRelease.manifest_sha256` | ctr:1543,1563-1590 | 验证记录与候选不是同一次 | 版本绑定 | 保留 | knowledge_gap_feedback 交叉校验 |
| `turn:chat:sha256:` turn_id | chat:2016-2032 等 | 会话内轮次错配 | 复现证明 | 保留 | 作 planner request_id 并回校 |
| `ChatFeedbackCheckpoint.content_sha256` | chat:916-937 | 反馈绑定 turn 工件 | 审计派生 | **待定** | 唯一消费者并入 gap signal；无回读校验，内容已含另两个哈希 |
| `evidence-set:sha256:` / `turn-result:sha256:` | chat:2420-2427 | 反馈无法回溯到具体轮 | 审计派生 | 保留 | GapSignal 身份/效应绑定 |

## A. 链式放大点（实测）

- `build_manifest.manifest_sha256` → 覆盖 manifest.json 内 **47,112** 个 sha256 值（其中 `eligibility_sets` 47,072 条）。
- `IndexProjectionResult.content_sha256` → 覆盖约 **19.6 万**嵌套哈希（51,029 points×2 + 47,071 docs×2）；正是拦下半封印包的那个点。
- 两个 request 哈希 → 覆盖 relationships.json 内 **1,843,163** 个哈希。
- 嵌套 3 层的同值链：`manifest.relationship_result_content_sha256` = `build_manifest.relationship_set.content_sha256` = relationships.json 内同值（实测均 `7f18aac9…`）。

## B. 同一内容多处存哈希（实测 run14 sealed 包）

- `7f18aac9…`（关系结果）×3；`a4e53260…`（manifest 自身）×2；marker `8848197c…`×3（manifest 字段 + files 表 + 启动命令行）；机构目录 `060cbe91…`×2；object_set 与 published projection 4/4 同值；每个 point `embedded_content_sha256` ×2（51,029×2）；空串哈希 `e3b0c442…` 在 manifest 出现 6 次。

## C. 简删风险提示（fail-closed 消费者）

- **`files[lookup.sqlite3, milvus.db]`**：消费点在 loader 启动链（boot 期读 1.75GB 做 SHA-256），且备份脚本读包内这两个文件。要动必须同时决定"包内是否还保留字节拷贝"（C2 已实测包内文件与 index-v1 逐字节一致）。
- **四类"复现证明"哈希**（index_result / 两个 request / candidate / internal-reference）：全部在启动链上 fail-closed，是 C2 拦下半封印包的消费者；字段名受 `schema_version="canonical-v2-serving-pack-v1"` 约束——**删字段=作废所有已封包，属契约级变更，不是瘦身**。
- **反证**：data-rebuild worktree 的 loader 私藏 `SERVING_PACK_SKIP_HASH_VERIFY=1`（5 处绕过）——半封印包当初能启动的 dev 后门；说明削弱校验必然被绕过。
- 口径补充：`supplementary_field_values` extra_forbidden、读侧剥 `_supplementary` 键两次真实故障是**类型校验**拦下的，不在哈希链上——瘦身哈希不触及这一类防护。

## 处置建议汇总

| 桶 | 项 | 动作 |
|---|---|---|
| **保留** | 启动链 fail-closed 全体（marker/复现证明四类/request 链/bundle/catalog/relationship bytes/plan 绑定/turn 绑定） | 不动 |
| **冻结** | 分节哈希、source_batches、source_projection、receipt 4 门、entity_ids_sha256（待定项维持冻结） | 不再增长，随 S3 复核 |
| **简删候选（先小后大）** | ① `authority_sha256`（零读者）② `PlanningTrace.proposal_sha256`（仅测试）③ `files[marker]` 重复 ④ **`files[lookup,milvus]` boot 哈希 + 包内字节拷贝**（读法/备份脚本需一起改，收益：boot 省 1.75GB 哈希） | S3 逐项执行，每项三重门 |
