# 客户现场迁移方案（Kimi session 恢复版）

> **来源与状态**：本文件是从 Kimi Code session `bae3b90e`（2026-08-13/14，
> `.kimi-code/sessions/wd_mirothinker_f4e14fb44614/session_bae3b90e-c4ab-4741-949c-915bef9617d3`，
> 主 wire 第 2388–2603 行）逐字恢复的迁移规划记录。原会话产出 10 步路线图与
> 第 1–5 步的详细展开后中断，**第 6–10 步从未产出**；本文忠实保留已产出内容，
> 未补写缺失步骤（缺失部分在文末列为待续项）。恢复时间 2026-08-17。
>
> 迁移对象：canonical-v2 生产栈（本文写作时生产 HEAD 为 `45d39dd` 一线；
> 执行前需按当时 HEAD 复核路径与清单）。

## 客户现场约束（会话中确认）

- 数据政策：949M 数据（教授/企业信息）**接受整体搬迁**；
- 现场**无 GPU，必须使用 LLM API**；
- 可以访问互联网；目标机 Ubuntu，有 root。

## 生产栈盘点（会话结论）

整套系统 = 代码 worktree（~6.7G）+ 数据目录（949M）+ 启动门槛文件（1.3G）+ 4 个密钥文件。
查询期外部依赖只有三类：LLM/embedding/rerank（全部指向学校基础设施）、Bocha/Serper（外网）、
反代在第三台机器（dbg21 nginx）。

**总策略：原样搬运运行态，不重建索引**——索引在客户现场从头重建从未验证过。

## 10 步路线图

1. 确认目标机条件（决定分支）— 已完成（见上节约束）
2. 本机打包三批货
3. 目标机基础环境
4. 数据落位与校验
5. 模型端点改造（关键路径）
6. 密钥与启动参数 — **未产出**
7. 首启冒烟 — **未产出**
8. 反代与对外发布 — **未产出**
9. 守护与日常运维 — **未产出**
10. 回退预案与验收 — **未产出**

## 关键决策记录（会话中三轮问答定案）

### 1.3G 启动门槛文件是什么

- 它是**老系统的生产向量库本体**：Milvus Lite 单文件 `apps/miroflow-agent/milvus.db`（1.3G）。
- 现在服务的 949M 新库由老库迁移、逐条比对、验收产生；发布时把老库 sha256 冻结进验收清单
  （4 份控制 JSON），启动参数再钉一遍（`--accepted-original-milvus-path` + 两个哈希）。
  清单标注 `hash_only_never_opened`：**只验哈希，从不打开**，纯粹是血统证明。

### 老库还需要吗（实测结论）

- **完全不用**：进程实测（lsof 全系统零句柄）+ 代码实测（查询路径四个源文件对老库引用为零；
  唯一认识它的代码在构建/门禁模块，仅启动时校验一次）。查询流量 100% 走新库
  （`/var/tmp/mirothinker-canonical-v2-s12f/index-v1/`：milvus.db 140M + 向量矩阵 223M + 查询表 59M）。

### 摘掉 1.3G 的可行性（已定案：摘）

- 生产走 `--serve-existing --serving-pack` 快速路：组包函数第一行 `del value` 直接忽略启动配置，
  三个 `--accepted-original-milvus-*` 参数在服务路径上**零消费**；门禁真检查只在构建路径
  （`create_builder`）上跑。
- **改法（约 30 行 + 测试，随迁移分支带走，需过一次代码评审）**：
  - runner argparse：三个参数改为构建模式必填、服务模式（`--serve-existing --serving-pack`）免填；
  - 配置校验对缺省值兼容（现状只做路径唯一性算术，无文件 I/O）；
  - `s12g/serve-18188-command.sh` 删掉三个参数；
  - 单测：服务模式无这三个参数可启动；构建模式缺参数仍拒绝。
- 不削弱任何运行时安全检查（该路径本就不检查此文件）；构建期门禁原样保留。

## 第 2 步：本机打包（三批货，总计约 3G）

- **代码包（~2G）**：整个 worktree 打 tar，排除 `.venv`（目标机重建）、`htmlcov/`、`report.html`、
  `.tmp-chat-responsive/`；`.git` 是指针文件直接打包。上述 runner 小改先进这个包。
- **数据包（~950M）**：先手动跑 `deploy/backup-canonical-v2.sh`（对全部 sqlite 含 milvus.db 做在线
  一致性备份——直接拷活库有损坏风险，必须用备份产物）；从 `/md1/backups/canonical-v2/<最新快照>`
  打包 `serving-pack/`、`index-v1/`、两个 sidecar sqlite（access-logs / corrections，含 WAL）、
  `manual-recall-v1/`；`staging-v1/`（构建残留）不带。
- **密钥包（几 KB）**：`.sglang_api_key`、`.bocha_api_key`、`.serper_api_key` +
  `canonical-v2-basic-auth.txt`，单独走加密渠道，落位后 chmod 600。
- 每包附 `sha256sum` 清单，第 4 步逐文件校验；rsync/scp 或 U 盘均可。

## 第 3 步：目标机基础环境（约半天）

- **布局**：创建同名用户、保持原绝对路径（代码树、`/var/tmp/mirothinker-canonical-v2-s12f/`、
  密钥放代码根上级）。路径写死在 `s12g/serve-18188-command.sh`，同构布局一处不用改；
  不同构则只改这一个文件。
- **安装**：uv 官方脚本 → 解代码包 → `uv sync`（自动拉 Python 3.12 + 重建 .venv）；
  `uv run playwright install chromium` + `sudo ... install-deps chromium`（要 root）；
  `sudo loginctl enable-linger <用户>`（systemd --user 脱离登录存活）。
- **明确不需要**：GPU、Postgres、docker、node（PG 只在构建期用；Playwright 自带 node；
  LLM/embedding/rerank 全走远程 API）。
- **已知坑**：`/var/tmp` 可能被 systemd-tmpfiles 定期清理——第 9 步用固定数据目录或
  tmpfiles 豁免解决，先按原路径落位。

## 第 4 步：数据落位与校验

- 解到 `/var/tmp/mirothinker-canonical-v2-s12f/` 保持原结构。
- 逐文件 `sha256sum -c`；五个关键大文件单独复核：`serving-pack/milvus.db`、
  `index-v1/milvus.db`、`vector_matrix.npz`、`lookup.sqlite3`、`relationships.json`。
  哈希不符重传，不带伤启动。
- 全部归服务用户；**milvus.db 属主不能是 root**（milvus_lite 以用户身份启动，同目录写锁）。
- 已决定摘掉 1.3G 老库（runner 小改随代码包），此步无门槛文件。
- 密钥放代码根**上级目录**（解析向上逐级找），chmod 600（顺手把原 0644 收紧）。

## 第 5 步：模型端点改造（关键路径，建议最先做）

三个查询期依赖全指向学校基础设施且**代码级写死**（LLM 在 profile 表硬钉、embedding/rerank
硬编码默认值，环境变量在服务路径上不生效），必须动代码：

- **Embedding 是硬约束**：索引按 Qwen3-Embedding-8B（4096 维）构建，查询向量必须同模型同维，
  否则 949M 索引整体作废。选能托管同模型的 API（硅基流动、阿里云百炼均有）。
- **LLM 可换同档模型**（如 Qwen 系 API 版），但有质量回归风险——全套提示词按现模型调过，
  换模型后用冒烟会话实际验。
- **Reranker 同理**，尽量同模型（Qwen3-Reranker-8B 有托管）。
- **改法**：profile 表新增现场 profile（base_url/model/key 环境变量名）；embedding/rerank
  两处默认值改成读环境变量；`CHAT_LLM_PROFILE` 指向新 profile。改动小但行为面，过一次评审。

## 待续（恢复时需补齐）

- 第 6 步：密钥与启动参数
- 第 7 步：首启冒烟
- 第 8 步：反代与对外发布
- 第 9 步：守护与日常运维（含 /var/tmp 清理豁免）
- 第 10 步：回退预案与验收

执行前另需复核：runner 摘门槛小改尚未实现（本文件只是方案）；生产 HEAD 已从 `45d39dd`
推进（2026-08-17 起为 `438300a`+，含 deepening-turn-anchor-carryover），打包与启动脚本
按当时状态核对。
