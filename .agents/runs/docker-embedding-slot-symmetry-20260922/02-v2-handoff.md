# 留给 v2 的端到端验收（本轮**没有**验，也不该假装验过）

本轮只做到"机制级"：文件 → entrypoint → 容器内进程环境里出现候选槽位（见 `01-slot-symmetry.md`
与 `raw/05-container-acceptance.log`）。**真正的端到端**是 v2 冷装时"只给文件 → 向量道可用"，
它需要：v2 镜像（含 `embedding-switch-line` 的候选路由）+ v2 数据面/发布包 + 候选网关可达。
⇒ **由做 v2 重打与冷装演练的那一轮负责**（本分支只保证机制在容器边界上成立）。

## 判据（照抄即可）

```bash
# 0. 前置：站点只放了 4 个 key 文件（CONFIG-GUIDE §2），没有设任何 *_API_KEY 环境变量
cd <交付包目录> && sudo ./install-site.sh          # 期望 exit 0

# 1. 容器边界：候选槽位有没有被文件喂上（名字与是否为空，无值）
docker compose exec -T app env MIROTHINKER_ENTRYPOINT_ENV_RECEIPT=1 \
  /usr/local/bin/mirothinker-entrypoint | grep CANONICAL_V2_EMBEDDING_API_KEY
#   期望：环境槽位 CANONICAL_V2_EMBEDDING_API_KEY=已设置

# 2. 服务进程真的继承到了（不是"只打印了一下"）
docker compose exec -T app sh -lc '
  pid=$(ls /proc | grep -E "^[0-9]+$" | while read p; do
          tr "\0" " " < /proc/$p/cmdline 2>/dev/null | grep -q serve_s12e_port && echo $p && break; done)
  tr "\0" "\n" < /proc/$pid/environ | grep -q "^CANONICAL_V2_EMBEDDING_API_KEY=.\+" && echo 已设置 || echo 空'
#   期望：已设置

# 3. 候选道真的可用（这一步才是"向量道没死"的正面证据；第 1、2 步只证明凭据到位）
#    候选权威 = 第三方网关，凭据槽位 CANONICAL_V2_EMBEDDING_API_KEY，维度 1024（v2 bundle 记录）
#    用 embedding-switch-line 的 .agents/runs/embedding-model-switch-v2/probe_native_query_side.py
#    或等价探针打一次 query embedding → 期望 HTTP 200 且向量维度 = bundle 的 dimension

# 4. 该站点的**有效端点**必须是候选网关地址，不能是自建端点（见下面的风险 R1）
docker compose exec -T app env | grep -c '^CANONICAL_V2_EMBEDDING_BASE_URL='   # 期望 0（未设 ⇒ 用 bundle 记录的地址）
```

## 两条跨线风险（本轮复核过、未修；v2 切包前必须先落定）

**R1（高）：受管 `embedding_base_url` 会覆盖候选 bundle 记录的网关地址。**
- 机制：`resolve_embedding_base_url(recorded)` = `os.environ["CANONICAL_V2_EMBEDDING_BASE_URL"] or recorded`
  （`knowledge_build_isolated.py:8328-8345`，两处适配器构造都走它：`:8479`、`:8559`）；
  受管设置 `extraction_endpoints.embedding_base_url` 映射到这个环境变量
  （`managed_config.py:74`）**且在管理页上可编辑**（`managed_config.py:176-178`）。
- 现状：交付包预置的受管设置里这个值 = **自建端点** `http://100.64.0.27:18005/v1`
  （`deploy/docker/site-config/managed-settings.json`，v1.1 的预置值）。
- 后果：v2 站点若原样带上这份预置，候选 bundle 的 `https://maas.qianwenaiapi.com/api/v1`
  会被覆盖 ⇒ 候选道拿**网关的 key 打自建端点**（或反之），第 3 步必然不是 200。
- 需要决定（二选一）：v2 出包时把预置值改成候选网关地址 / 或让 v2 预置**不带**这个键
  （留空 ⇒ 用 bundle 记录的地址）。两选一都行，但**必须显式决定并按判据第 4 步验证**。

**R2（中）：`CONFIG-GUIDE.md §4` 说"嵌入端点地址**不能改**（只读展示）"，与 R1 里
"地址是操作者可在页面设置的字段"不一致。** v2 的指南要按 v2 的实际语义重写这一段
（地址 = 可改的操作者字段；模型/维度 = 冻结，改需重建索引）。

## 本轮不做的事（明确边界）

- 不改任何**读侧**代码（候选 bundle 只能读它声明的槽位 —— 这是设计上的不对称，放宽会让
  第三方 bundle 拿到自建端点的 key；页面那一半已由 `v2-admin-identity-native` 修好，未重复）。
- 不动前端（D8：页面提示的重启命令是裸机 `systemctl --user …` 那一条，仍留待前端那条线）。
- 不重打 v1.1 交付件（机制改在 `deploy/docker/`，v2 重打时自动带上）。
