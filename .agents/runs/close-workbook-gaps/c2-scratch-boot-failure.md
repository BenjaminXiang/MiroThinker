# C2.1b scratch 启动失败 — 根因分析（2026-09-10）

## 结论（一句话）

run14 serving pack（`/var/tmp/mirothinker-data-v2/serving-pack-run14/`）是**装配不一致**的包：
manifest 的索引语义绑定（`index_result_content_sha256` 等）仍是 p4（2026-08-26）铸包时的值，
绑定的是 2026-08-25 物化的索引（36,899 points / 32,941 docs）；而包内实际的
lookup.sqlite3 / milvus.db 是 2026-09-08 run14 物化（51,029 points / 47,071 docs）。
fail-closed loader 按设计拒绝加载——**loader 没有 bug，是包需要数据线重铸索引语义绑定**。

## 失败现象（原样 traceback）

```
File ".../s12a/complete_candidate_runner.py", line 1156, in main
  handoff = create_pack_handoff(config)
File ".../s12a/complete_candidate_runner.py", line 1013, in create_serving_pack_handoff
  authority = pack_authority()
File ".../s12a/complete_candidate_runner.py", line 1000, in pack_authority
  pack_loader_module.open_serving_pack_authority(
File ".../apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py", line 672, in open_serving_pack_authority
  raise ServingPackIntegrityError(
src.data_agents.canonical_v2.serving_pack_loader.ServingPackIntegrityError: serving pack index result does not reproduce its recorded hash
```

完整日志：`.agents/runs/close-workbook-gaps/c2-scratch-boot.log`。
启动方式：worktree 代码（HEAD 197b7f5）+ `s12g/serve-18189-command.sh`，端口 18189，
RSS 爬坡约 2 分钟后 fail-closed 退出，服务未就绪。

## 失败点定位

`serving_pack_loader.py:644-674`：从 index root 读出 points/lookup_documents/receipt，
与 manifest 的 `index_rebuild_decisions`、`index_policy_snapshot` 拼成
`IndexProjectionResult.model_construct(...)`，重算 canonical sha256 与
`manifest.index_result_content_sha256`（`738219cf…`）不符 → raise。

- OR 第二子句（policy_snapshot.embedding_model != manifest.embedding_model_id）已排除：两者都是 `Qwen/Qwen3-Embedding-8B`。
- 失败的是哈希子句。
- 此前的 marker 验证、receipt 绑定、collection 检查**全部通过**（receipt 只绑定 point_ids/projection manifests，不绑定 point 内容全文，所以 Sep-8 内容能通过 receipt 检查但过不了 Aug-26 的语义哈希）。

## 决定性证据

1. **同 release 四个 pack 对比**（`/var/tmp/mirothinker-data-v2/`）：

   | pack | manifest.generated_at | receipt.built_at | points/docs | index_result_sha |
   |---|---|---|---|---|
   | serving-pack | 2026-08-26 (p4-pack-20260826-v1) | 2026-08-25 | 36,899 / 32,941 | 738219cf… |
   | serving-pack-run9 | 同上 | 2026-08-25 | 36,899 / 32,941 | 738219cf… |
   | serving-pack-old-run12 | 同上 | 2026-08-25 | 36,899 / 32,941 | 738219cf… |
   | **serving-pack-run14** | **同上（Aug-26 p4）** | **2026-09-08** | **51,029 / 47,071** | **738219cf…（未更新）** |

   健康对照（现役 s12f pack）：generated_at 2026-08-03T02:20 / receipt.built_at 2026-08-03T01:51，
   同一次构建相差 ~30 分钟。run14 的 manifest 与索引物化相差 **13 天**。

2. **run14 manifest 是"半更新"的**：与 run9 manifest 对比——
   `files` 哈希已更新为 run14 实际文件（lookup c392d559…/milvus a10f4b06…，与 sha256sum 实测一致）、
   `relationship_result_content_sha256`/`candidate_projection_result_content_sha256` 已为 run14 重算；
   但 `index_result_content_sha256` 仍是 p4 旧值 `738219cf…`，`index_policy_snapshot`/
   `index_rebuild_decisions`/`index_projection_request_sha256` 原样沿用。
   即装配时重算了关系/候选绑定和文件哈希，**唯独漏了索引结果绑定**。

3. **排除包外漂移**：
   - pack 内 lookup.sqlite3/milvus.db 与 index root（`/var/tmp/mirothinker-data-v2/index-v1`）**逐字节一致**（sha256sum 相同）；index root mtime Sep 8 19:04-19:07，铸包（Sep 8 23:47 / Sep 9 14:07）后未被改动。
   - receipt.built_at = 2026-09-08T11:07:10Z 与 index root mtime 吻合。

4. **排除 serving 代码漂移**：worktree 分支 `index_projection.py` /
   `index_projection_isolated.py` / `serving_pack_loader.py` / `knowledge_build_isolated.py`
   自 2026-08-20 以来**零提交**（git log 为空）；同一 loader 每天正常启动现役 s12f pack。

## 资源测量（C2.1b 的另一半）

- 启动前 `free -g`：410G 可用（门 <16G 通过）；现役 18188 RSS 2.4G。
- scratch 进程 RSS 峰值约 14G（2.9G relationships.json 回放期间），随后 fail-closed 退出。
  因启动未成功，稳态 RSS / boot wall-time 未能测量。

## 建议的修复方向（归主上下文/数据线决定，本切片未执行）

重铸 run14 pack 的索引语义绑定：对 run14 index root 重跑 pack 封印的索引组件
（使 `index_result_content_sha256`、`index_policy_snapshot`、`index_rebuild_decisions`
绑定 2026-09-08 物化），而不是修 loader 或放宽校验。
注意：`index_projection_request_sha256` 与四个 pack 相同（76132d37…），是否也需随
run14 重算需数据线在重铸时一并确认——loader 在 index_result 检查之后还有其他绑定检查
（serving_pack_loader.py:676-740），重铸后需完整启动验证。

## 现场状态

- C2.1a 产物已提交：worktree commit `9cfdabe`（`s12g/serving-bundle-run14.json` +
  `s12g/serve-18189-command.sh`）。
- scratch 18189 进程已退出，端口空闲；scratch access-log/corrections DB 留在
  `/var/tmp/mirothinker-data-v2/*-c2-scratch.sqlite3`（无碍）。
- 现役 18188 全程未动。
- C2.1c–e 未开始（被本阻塞阻断）。
