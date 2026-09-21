# 文件路线 → 候选嵌入槽位：部署侧的一半（2026-09-22，分支 `delivery/docker`）

上一轮（第 4 组未验证项）的延续。本轮唯一目标：让**文件路线**喂到候选（第三方网关）
嵌入槽位，与页面路线（`v2-admin-identity-native` 的 `mirror_env_vars`）对称。

## 一句话规则

**一个 key 文件 → 两个槽位；优先级 显式环境变量 > 管理页受管凭据 > key 文件**
（显式设置就一个字节都不动；受管凭据里有 embedding key 就让服务启动时自己投影到两个槽位；
否则把文件投影到 `CANONICAL_V2_EMBEDDING_API_KEY`，v1 槽位 `SGLANG_API_KEY` 保持"按文件直读"）。

## 事实链复核（动手前逐环节核对）

| 环节 | 事实 | 复核方式 |
|---|---|---|
| 候选路由怎么读凭据 | 只认环境变量：`_GATEWAY_EMBEDDING_API_KEY_ENV = "CANONICAL_V2_EMBEDDING_API_KEY"`、`_load_gateway_embedding_api_key()` = `os.environ.get(...).strip()` | `embedding-switch-line` @ `knowledge_build_isolated.py:8354-8360`（读源码） |
| 候选 bundle 声明的槽位 | `"api_key_source": "env:CANONICAL_V2_EMBEDDING_API_KEY"`，`provider=dashscope-native`，`base_url=https://maas.qianwenaiapi.com/api/v1` | `.worktrees/embedding-switch-line/.agents/runs/embedding-model-switch-v2/qwen3.7-text-embedding-flash-embedding-bundle-v1.json` |
| 甲方走的那条路 | `install-site.sh` 收 4 个 key **文件**；`compose.yaml` 把 `.sglang_api_key` 挂到容器内 `/opt/mirothinker/.sglang_api_key` | 本分支 `deploy/docker/{install-site.sh,compose.yaml}` |
| 谁把文件变成环境变量 | **没人**：`entrypoint.sh` 原文零命中（`grep -n "SGLANG_API_KEY\|CANONICAL_V2_EMBEDDING_API_KEY" deploy/docker/entrypoint.sh` → 空） | 本分支 |
| v1 槽位怎么读文件 | `load_local_api_key()`：`API_KEY → OPENAI_API_KEY → SGLANG_API_KEY → .sglang_api_key`（cwd/父目录） | `providers/local_api_key.py:8-11` |
| 页面那一半（不重复做） | `SecretSpec(env_var="SGLANG_API_KEY", mirror_env_vars=("CANONICAL_V2_EMBEDDING_API_KEY",))` + `apply_to_environ()` 两个槽位都填、"已存在即跳过" | `.worktrees/v2-admin-identity-native/.../managed_secrets.py:156-170`、测试 `tests/canonical_v2/test_managed_secrets_store.py:238-268` |

⇒ 结论：事实链成立。文件路线的站点（一键安装的标准动作）在 v2 下候选嵌入路由**零凭据**，
且向量道 fail-open ⇒ **静默**降级。

## 行为级 RED（改前，stub 观测子进程）

把未改的 `entrypoint.sh` 复制一份、**只**把 `START_SCRIPT` 一行指向 stub（stub 打印它
继承到的槽位），key 文件在位：

```
[stub] CANONICAL_V2_EMBEDDING_API_KEY=<空>      ← 文件在、但候选槽位拿不到
[stub] SGLANG_API_KEY=<空>                       ← 正常：v1 槽位按文件直读，不看环境变量
[stub] 文件 v1 槽位可读=是
```

（`raw/00-RED-behavior.log`；`sk-fake-red-only-9999` 是本轮临时生成的**假值**，不是任何真凭据。）

同一 stub、同一文件，改完后再跑：

```
[entrypoint] 嵌入凭据投影：key 文件 → CANONICAL_V2_EMBEDDING_API_KEY（已设置；v1 槽位 SGLANG_API_KEY 仍按文件直读）
[stub] CANONICAL_V2_EMBEDDING_API_KEY=sk-fake-red-only-9999
```

## 改了什么

| 文件 | 改动 |
|---|---|
| `deploy/docker/entrypoint.sh` | ① 新增"嵌入凭据投影"段（三档优先级，只打印名字与是否已设置）；② 新增 `MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1` 凭据收据模式（**子进程**打印，只有真正 export 的变量才会出现；打印后退出，不启动服务）；③ `MIROTHINKER_EMBEDDING_KEY_FILE` 覆盖点（默认 `/opt/mirothinker/.sglang_api_key` = compose 挂载点）；④ **D6 修复**：状态目录不可写的诊断不再建议 `user: "0:0"`，改为"重跑 install-site.sh / chown 到数据属主"+明确警告不要跑成 root |
| `apps/miroflow-agent/tests/canonical_v2/test_deploy_entrypoint_embedding_projection.py` | 新增 5 条测试（见下） |
| `deploy/docker/CONFIG-GUIDE.md` | §2 密钥表补一句：同一个 `.sglang_api_key` 同时喂 v1 自建端点槽位与候选网关槽位（v2 站点不必再填第二个文件） |

不动：`compose.yaml`、`install-site.sh` 的落地逻辑、任何读侧代码（读侧的不对称是设计，不能放宽）。

## 新增测试（5 条，全部先 RED 后 GREEN）

```
cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_deploy_entrypoint_embedding_projection.py -q
→ 5 passed
```

| 测试 | 钉住什么 |
|---|---|
| `test_file_route_fills_both_authority_slots` | **链式**：文件 → 真 entrypoint → **子进程**环境里候选槽位"已设置"；同一文件用真 `load_local_api_key` 读出（v1 槽位不退） |
| `test_explicit_environment_wins_over_the_key_file` | 显式环境变量优先：走"已显式设置"分支、**不走**文件分支 |
| `test_managed_page_credential_owns_the_slot_over_the_key_file` | 页面写过 embedding key 时投影留给服务（收据显示候选槽位"空"+ 受管分支日志），避免把管理页换的 key 在候选槽位钉死 |
| `test_absent_key_file_degrades_without_failing` | 三档都空 ⇒ 退出码 0 + 如实诊断（不许 fail-closed） |
| `test_receipt_reports_the_v1_file_tier_without_printing_it` | 收据能看出"文件这一档在不在"，且**任何假 key 值都不出现在 stdout/stderr** |

定向套件（含邻域）：`uv run pytest tests/canonical_v2 -k "managed or embedding or deploy or secrets" -q`
→ **8 passed**（我的 5 条 + `test_fast_boot` / `test_knowledge_build_isolated` / `test_serving_pack_loader`），1755 deselected。

## 容器内机制级验收（原始命令与输出见 `raw/05-container-acceptance.log`）

换 entrypoint（仍是**只给文件**、未设任何环境变量的现场）→ `docker compose restart app`
（281 s）→ 三项检查：

```
# ① 容器边界：收据模式（docker compose exec -T app env MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 /usr/local/bin/mirothinker-entrypoint）
[entrypoint]   环境槽位 SGLANG_API_KEY=空
[entrypoint]   环境槽位 OPENAI_API_KEY=空
[entrypoint]   环境槽位 API_KEY=空
[entrypoint]   环境槽位 CANONICAL_V2_EMBEDDING_API_KEY=已设置
[entrypoint]   key 文件 /opt/mirothinker/.sglang_api_key=已设置（v1 槽位按文件直读，不需要环境变量）
收据 exit=0

# ② 运行中的服务进程自己的环境（pid 26 = /opt/mirothinker/.venv/bin/python3 …serve_s12e_port）
  进程环境 SGLANG_API_KEY=空
  进程环境 API_KEY=空
  进程环境 OPENAI_API_KEY=空
  进程环境 CANONICAL_V2_EMBEDDING_API_KEY=已设置      ← 投影真的进到服务进程

# ③ 显式环境变量优先（注入一个假值，只打印判定）： 
[entrypoint] 嵌入凭据投影：CANONICAL_V2_EMBEDDING_API_KEY 已显式设置 —— 不动（环境变量优先）

# 启动日志里的那一行（全量 grep，非 --tail）：
app-1  | [entrypoint] 嵌入凭据投影：key 文件 → CANONICAL_V2_EMBEDDING_API_KEY（已设置；v1 槽位 SGLANG_API_KEY 仍按文件直读）
```

**无回归证据**（改动前后同一条探针）：

| 探针 | 改前（上一轮 `raw/04-embed-final.json`） | 改后（`raw/05-embed-after-projection.json`） |
|---|---|---|
| 嵌入连接测试（v1 槽位） | `ok:true / HTTP 200 / api_key_source=legacy-file:.sglang_api_key` | **同上，逐字一致** |
| 对话模型连接测试（页面档位） | `ok:true / 200 / managed-file(env:DEEPSEEK_API_KEY)` | **同上**（`raw/05-llm-after-projection-retry.json`） |

## 端到端（不归本轮）

见 `02-v2-handoff.md`：判据、谁验、以及两条**会让"只给文件"仍然不通**的跨线风险
（受管 `embedding_base_url` 覆盖优先级、CONFIG-GUIDE §4 与该行为的措辞冲突）。
