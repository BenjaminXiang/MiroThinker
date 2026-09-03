# Embedding 模型一致性契约（入库端 ↔ 查询端）

> 结论先行：**入库与查询共用同一个模型 `Qwen/Qwen3-Embedding-8B`（4096 维），
> 服务在 tailnet 机器 `100.64.0.27:18005` 上（OpenAI 兼容接口），密钥为仓库根
> `.sglang_api_key`。一致性不是靠约定，而是靠 serving bundle 的 sha 钉扎 +
> 代码里的启动期硬校验强制保证的。任何一端换了模型/维度，服务会直接拒绝启动或拒绝回答。**

最后核验：2026-09-02（端点 `/v1/models` 实测返回该模型；代码行号以
`data/p4-serving-pack-rebuild` 分支 = 现役 serving worktree 为准）。

## 1. 模型与端点（唯一事实源）

| 项 | 值 | 出处 |
|---|---|---|
| 模型 | `Qwen/Qwen3-Embedding-8B` | bundle JSON + 端点 `/v1/models` 实测 |
| 维度 | **4096** | bundle JSON `dimension` |
| 端点 | `http://100.64.0.27:18005/v1`（tailnet 内网地址） | bundle JSON `base_url` |
| 协议 | OpenAI 兼容（`/v1/embeddings`） | bundle JSON `provider` |
| 密钥 | 仓库根 `.sglang_api_key`（27B，密钥通道迁移，永不入 git） | `providers/local_api_key.py` |
| 批次/超时 | batch 32 / 32 workers / 180s | bundle JSON |

**唯一事实源文件**（入库与查询都从它读端点与模型，不存在第二份配置）：

```
.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/qwen-embedding-bundle-v1.json
（内容含 content_sha256=05473fab…，serve 命令行 --recorded-embedding-bundle 指向它）
```

注意：查询端 embedding **不读** `.env` 里的 `LOCAL_LLM_BASE_URL`（那是 chat LLM 的，
当前=DeepSeek 在线端点）；也不依赖本机 GPU——embedding 服务跑在 100.64.0.27 那台机器上。

## 2. 一致性是怎么被强制的（三层）

**第一层：入库端写入即声明。**
构建时（`knowledge_build_isolated.py`）用 `_OpenAICompatibleEmbeddingAdapter`
（`base_url`/`model_id`/`dimension` 来自上述 bundle）产出全部向量写入 serving-pack 的
`milvus.db`；同时 `manifest.json` 记录 `policy_snapshot.embedding_model`，且
**每个向量 point 都带自己的 `embedding_model` 字段**。

**第二层：serve 启动命令行 sha 钉扎。**
现役 serve 命令（87 参，完整命令行见迁移 Release 的 `meta/serve-cmdline.*.txt`）钉死：

```
--model-version embedding=Qwen/Qwen3-Embedding-8B
--recorded-embedding-bundle …/s12c/qwen-embedding-bundle-v1.json
--recorded-serving-bundle …/serving-bundle-p4.json --recorded-serving-bundle-sha256 <sha>
```

**第三层：查询端启动期硬校验（`knowledge_read_isolated.py`）。**
`create_isolated_vector_recall_adapter`（:7000）在绑定召回时依次执行：

1. `_validate_manifest_hash` — serving pack manifest 哈希校验；
2. `expected_model_id = bundle.index_result.policy_snapshot.embedding_model`；
3. **逐点校验** release 里所有 point 的 `embedding_model` 必须等于 policy 声明（:7018）；
4. 查询用的 embedding adapter 被 `_ValidatingEmbeddingAdapter`（:261）包装，每次回答前核对：
   - adapter 的 `model_id` 必须等于 release 声明（"model differs from the release" 即抛错）；
   - 每个返回向量必须 4096 维、数值有限、非零范数；
   - **同一段文本两次 embedding 必须字节一致**（确定性校验，防端点悄悄换模型/加噪声）。

## 3. 运维与迁移红线

- **新开发机必须能访问 `http://100.64.0.27:18005/v1`**（加入同一 tailnet 或打通路由），
  并带上 `.sglang_api_key`。冒烟命令：`curl -H "Authorization: Bearer $(cat .sglang_api_key)" http://100.64.0.27:18005/v1/models` 应返回该模型。
- **模型、维度、端点三者任何一个变了** = 入库/查询不一致 = 检索全错。代码会拦住
  "查询端单方面换模型"（第三层校验抛错），但**拦不住"两端一起换、旧向量不重建"**——
  那种情况必须重跑入库构建（新 serving pack），属于数据线重建，需走 OpenSpec。
- **embedding 端点要搬迁**：改 `qwen-embedding-bundle-v1.json` 的 `base_url` 会使
  `content_sha256` 变化 → serve 命令的钉扎校验失败。正确流程：改 bundle → 重算 sha →
  更新 serve 命令行参数（serving pack 本身不用重建，向量不需要重嵌入，前提是模型与维度不变、
  仅网络地址变）。
- chat LLM 与 embedding 是两条独立链路：chat 走 `.env` 的
  `CHAT_LLM_PROFILE`/DeepSeek 在线端点，embedding 走 bundle/100.64.0.27。排查时别混。

## 4. 相关文件速查

```
apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py   # 入库端 adapter(:7601)
apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py    # 查询端校验(:261, :7000)
apps/miroflow-agent/src/data_agents/providers/local_api_key.py                 # 密钥加载(.sglang_api_key)
.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/qwen-embedding-bundle-v1.json   # 唯一事实源
.agents/runs/full-column-serving-pack-rebuild/serving-bundle-p4.json           # serve 钉扎的发布包
/var/tmp/mirothinker-data-v2/serving-pack/{manifest.json,milvus.db}            # 向量与声明
```
