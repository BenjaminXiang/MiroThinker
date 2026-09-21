# 留给 v2 的端到端验收（本轮**没有**验，也不该假装验过）

> **2026-09-22 更新（同日第二轮）**：本文件原来列的两条跨线风险已处理 ——
> **R1 已修**（交付预置删掉 `embedding_base_url` / `embedding_model` 两个键，见
> `03-preset-embedding-endpoint.md`；容器内实测生效端点来源由"受管覆盖"回到
> `release-bundle-default`）、**R2 已修**（`CONFIG-GUIDE §4` 按"地址可改、身份不可改"重写）。
> 因此下面判据第 4 步从"风险"变成"**必须过的验收项**"；另新增两条 v2 出包顺手要处理的遗留
> （安装器探针写死 v1 模型 id = L2；verify.sh 的打印文字 = L3，清单在 `03-…md §6`）。

本轮只做到"机制级"：① 文件 → entrypoint → 容器内进程环境里出现候选槽位（见 `01-slot-symmetry.md`
与 `raw/05-container-acceptance.txt`）；② 交付预置不再钉住 v1 时代的嵌入地址/模型
（见 `03-preset-embedding-endpoint.md` 与 `raw/06-preset-fix.txt`）。
**真正的端到端**是 v2 冷装时"只给文件 → 向量道可用"，它需要：v2 镜像（含候选路由）+
v2 数据面/发布包 + 候选网关可达。⇒ **由做 v2 重打与冷装演练的那一轮负责**。

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

# 4. 该站点的**有效端点**必须是候选网关地址，不能是自建端点（R1 已修；这条是它的验收）
docker compose exec -T app env | grep -c '^CANONICAL_V2_EMBEDDING_BASE_URL='   # 期望 0（未设 ⇒ 用 bundle 记录的地址）
#    再看管理面：GET /api/canonical-v2/admin/config 里
#      extraction_endpoints.embedding_base_url → value=None / source=default / editable=True
#      extraction_endpoints.embedding_model    → value=None / source=default / editable=False
```

## 原两条跨线风险（现已处理，保留记录）

**R1（高）：受管 `embedding_base_url` 会覆盖候选 bundle 记录的网关地址 —— 已修。**
- 机制（复核结论）：`resolve_embedding_base_url(recorded)` = `override or recorded`
  （`knowledge_build_isolated.py:8328-8345`；镜像内 `:8187`、调用点 `:8262`；
  switch 线候选适配器另有两处 `:8479`、`:8559`）；受管字段映射见 `managed_config.py:74`。
- 修法：交付预置 `deploy/docker/site-config/managed-settings.json` **删掉** `embedding_base_url`
  与 `embedding_model` 两个键（缺席 ⇒ 默认用 bundle 记录的地址；身份由发布包封印）。
- 证据：`03-preset-embedding-endpoint.md` + `raw/06-preset-fix.txt`
  （容器内 origin 由 `managed-file(env:CANONICAL_V2_EMBEDDING_BASE_URL)` → `release-bundle-default`，连接测试仍 200）。
- 顺带结论：`CANONICAL_V2_EMBEDDING_MODEL` **没有读者**（全代码库只有映射 + 一个测试的 scrub 列表），
  旧模型 id 不会进请求，只会显示在页面上。

**R2（中）：`CONFIG-GUIDE.md §4` 说"嵌入端点地址不能改"与页面可改字段矛盾 —— 已修。**
  新的措辞 = "**地址可改；身份（模型 + 维度）不可改**" + "冻身份，不冻地址"的理由 +
  "交付预置不预置地址/模型"的说明（原文见 `03-preset-embedding-endpoint.md §5`）。

## 本轮不做的事（明确边界）

- 不改任何**读侧**代码（候选 bundle 只能读它声明的槽位 —— 这是设计上的不对称，放宽会让
  第三方 bundle 拿到自建端点的 key；页面那一半已由 `v2-admin-identity-native` 修好，未重复）。
- 不动前端（D8：页面提示的重启命令是裸机 `systemctl --user …` 那一条，仍留待前端那条线）。
- 不重打 v1.1 交付件（机制改在 `deploy/docker/`，v2 重打时自动带上）。
