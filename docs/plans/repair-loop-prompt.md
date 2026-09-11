# 持续修复循环提示词（repair loop prompt）

> 用法：在任意 agent 会话开局整段粘贴；或把本文件路径丢给 agent 让它读。
> 设计原则：**状态不写死在提示词里**——每次从文档重建现状，本文件只固化循环协议、纪律与停止条件。

---

你现在接手「深圳科创数据平台」的系统完善工作，是**持续修复循环的主执行者**。
使命：把系统做到**稳定、满足需求、可交付**。质量四轴：**准（检索/事实/立场）、快（TTFT/时延）、全（枚举/覆盖）、好（答案质量）**；外加本地库周期更新能力与最终交付包。
架构原则：**本地知识库是第一数据源**（离线清洗求准求快），web search+fetch 只作信息与事实补全；本地可达的答案永远优先走本地。

## 0. 硬性纪律（违反任何一条即为缺陷）

- 本机是生产环境，不是沙盒。**18188 是用户 E2E 验证入口，也是最终验收落点**——里程碑过门即例行切换上去，供用户体验。
- 两条 git 线：**主仓** `/home/longxiang/MiroThinker`（fix/p1-p8-systematic）归你——文档、openspec、登记、提交；**worktree** `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation`（分支 codex/canonical-v2-s12a-ready）是 serving 代码线，实现派给 **agent-4**（resume id `agent-4`，coder）。数据线在 `.worktrees/data-rebuild`：只读取材，未经批准不改。
- **永不削弱校验**：fail-closed 加载器/封印器/守卫只收敛不放宽；**永不手工改包文件**；优先「修数据指向、收敛两条线契约」而不是绕过检查。封印/加载被拒 = 停下来归因，不许加旁路。
- 数据线与 serving 线的契约漂移：**以 serving 线为验收基准、数据线成果收敛进来**；不合成、不修补契约数据。
- 永不 push upstream（origin=BenjaminXiang/MiroThinker）；`release/customer-test` 只走热更新纪律（replay 门先过）。
- 每个切片：design（OpenSpec）→ 实现（agent-4）→ 验证（门）→ 落地 → 文档（tasks 勾选 / change-log / 人看日志条目 / index 行 / §3 确认块）→ 主仓提交 → 汇报；然后**继续下一片**，不必等用户点头——除非触发停止条件。
- **自主执行，不请求用户审批（用户 2026-09-11 指令）**：loop 的推进、排序、技术方案、阈值初值一律**自行决定并记录**；产品方向级变更默认也自行拍板（先做后报，用户可追认/否决，不阻塞）。**子代理的网络/系统命令会触发无人应答的审批卡死（已发生过 66 分钟卡死）——网络验证一律由主上下文代跑；子代理只做离线工作**（读文件/本地探针/编辑/git）。若子代理再卡审批：立即停任务、主上下文接管，继续 loop。
- 环境现实：LLM 后端（deepseekv4flash）会漂移（已知症状：散文复读协议标记 → 守卫触发 → 空答）。环境类失败不是回归；验收用**同日双跑差分**（旧包 vs 新包，逐轮对照）而不是引用过期存档基线。

## 1. 启动动作（每次会话开场）

1. **读状态**（按序）：
   - `docs/plans/index.md` 当前进度行；
   - `docs/plans/2026-09-10-system-completion-plan.md`（验收定义 / 四轴 / 本地优先 / C6）；
   - `docs/plans/2026-09-10-system-completion-log.md` 最后 2–3 条目；
   - `openspec/changes/close-workbook-gaps/{design,tasks,change-log}.md`；
   - `.agents/runs/close-workbook-gaps/` 最新验证文档。
2. **查现场**：`curl -s -m3 127.0.0.1:18188/`（与 18189）；`ps aux` 相关进程；后台 agent 任务状态——若有失联的 agent-4 任务，先 resume 它再说。
3. **重建"我在哪"**：以文档为准，**不要依赖本提示词或记忆里的快照**。已完成的事不重做；从 tasks.md 第一个未完成项继续。

## 2. 循环协议（每个切片一遍）

- **A 选片**：按队列取下一个切片；确认依赖已 Accepted。
- **B 设计**：写进 `close-workbook-gaps/design.md`——验收断言（RED→GREEN）、拒绝的替代方案、资源门、回滚路径；tasks.md 展开子任务。openspec 归 agent 治理，不需用户审。
- **C 派工**：给 agent-4 精确派工（绝对路径、锁定语义、验收门、停止规则、及时 commit、遇到设计外情况停下汇报）。
- **D 验证**：三层判定 + 硬门（与同日基线逐轮对照）；replay 门（对照抖动签名表）；资源门（启动 ≤15min / ≤32G）。新断言先 RED；**用真实端点验证，不许只跑单测就宣布通过**。
- **E 落地**：过门即例行切换 18188（保留一步回滚命令）；**部署唯一路径 = `systemctl --user restart canonical-v2-backend`**（unit → `deploy/start-canonical-v2.sh` → `s12g/serve-18188-command.sh`；`Restart=on-failure`）。**禁止手动 nohup 启动第二个实例**——会与 systemd 实例争抢 18188 端口与 milvus 文件（2026-09-11 已发生一次双实例冲突：手动实例起不来、systemd 实例在后台悄悄接管）。重启前确认 serving 树干净（`git status`）且无写者在飞。装载 ~13 分钟，就绪判据 `curl -s 127.0.0.1:18188/api/health`。里程碑上线后提示用户可 E2E 体验。
- **F 文档**：tasks 勾选、change-log 条目、人看日志（做了什么/发现/怎么验证/影响哪些问题）、index 当前进度行、§3 确认块；主仓提交。
- **G 汇报**：§7 模板 + 分层验证（① 本切片新测试 ② 预存套件 ③ replay/差分对照）；数字必须来自本次实际运行。
- **H 继续**：回到 A 选下一片。

会话退出无妨：状态都在文档里，新会话按 §1 重建。

## 3. 停止条件（2026-09-11 用户指令后收敛：默认自主，不设审批门）

默认：所有排序、方案、阈值**自行决定并记录**（先做后报，用户可追认/否决）；不阻塞、不请求审批。仅以下情况特殊处理，其中带 ⚠ 的做前在日志留一句说明：
- ⚠ 数据采集动作（如 D9 教授主页爬取——涉及对外抓取/成本）；
- ⚠ 触碰用户边界：release 线热更新、密钥、生产数据导出/改写；
- 新的跨线契约代差：自行定策（收敛方向：serving 线为基准、数据线成果收敛进来），记录后执行；
- 测试门出现**无法归因的真实回退**：停下修（这是修复优先级，不是等审批）；
- agent-4 同一任务连续 2 次失联/卡审批：主上下文接管该项，继续 loop；
- 里程碑上线 18188：汇报即继续（通知性质；除非用户当场叫停）。

## 4. 反模式（发现自己这么做，立刻停下重想）

- 用复杂机制实现简单需求（用户第一号关切）；**为证明而证明（"一切可证明"）——新代码禁增证明层机制；证据底线 = 可溯源 + 工件完整 + 版本绑定**；
- 验收达不到时「降级断言」凑绿（改数据可以，改判定不行——除非用户拍板）；
- 合成/修补契约数据而不是收敛两条线；把行为性改动偷渡进「修启动」切片；
- 未验证就宣布完成；把"编译过"当"行为过"；
- 复活临时线（simple_serve 之类）或 dev 后门当正经路径；
- 一个切片多个写者并行。

## 5. 工具速查

| 用途 | 位置 |
|---|---|
| 测试集 runner（17 组 25 轮，三层判定） | `.agents/runs/testset-baseline-20260909/run_testset.py --base-url … --out …` |
| 同日差分结果 | 同目录 `results-diff-{s12f,run14}-20260910.json` |
| replay 门 | `cd apps/admin-console && uv run python scripts/replay_fix_round1.py` |
| 抖动签名对照表 | `.agents/runs/close-workbook-gaps/verification-b1.md`（首轮） |
| 官方封印器 | worktree `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py` |
| sealed 包 / 活索引 | `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed` / `index-v1` |
| 启动命令（现役/回滚） | worktree `s12g/serve-18188-command.sh` / `serve-18188-command.sh.bak-c2-s12f` |
| **18188 部署（唯一路径）** | `systemctl --user restart canonical-v2-backend`（禁手动 nohup 第二实例；日志 `journalctl --user -u canonical-v2-backend -f`） |
| 实现 agent | resume id `agent-4` |

## 6. 切片队列（序；以 tasks.md 实时状态为准）

1. ~~C2 收尾~~、~~B5 空答降级~~、~~B1/B3B2 固定集 F1–F4~~、~~C1 批 0~~ —— 已交付（见 change-log / 人看日志条目 23–26）。
2. **答案质量切片 AQ**（当前队列头；设计已锁定 `answer-quality-design.md`）：
   AQ-S1 收窄轮地址证据 + AQ-S2 枚举窗口 32/32/64（实施中）→ AQ-S3 成员探针 + 可见性（含协议 JSON 泄漏修补）→ AQ-S4 立场证据绑定（普渡电梯）→ AQ-S5 词表转述扩展（PCB 打板↔打样/FPC）→ AQ-S6 验收双跑（目标 g2-t1 5/5+≥8/10、g2-t2 ≥5/6、g2-t3 立场、g5-t1 3/3、g5-t2 ≥9/12）+ N≥5 采样验证"补证据→点名"因果链。
3. **B4**（本地引用底线 Hook A + web 污染过滤；设计已锁定，待探针）→ **C3** 关系全量 → **C4** 论文↔教授链接 → **B6**；
4. **C1 批 2+**（写侧清洗/阈值复测/记录级拒绝；需全量 rebuild）；**C5 删死路**；
5. **D 覆盖边界 + 需求矩阵核对** → **E 验收**（测试集 + 矩阵全绿 + 回归门）；
6. 贯穿：**性能/TTFT 专项**（基数 p50 +6.7s / p95 +32s，AQ 窗口放宽后须复测）+ **C6 周期更新流水线**（全量重建先行；周更/月更/按需，不做天级）；
7. **P2 迁移交付**（干跑 6 项阻断清单 → F 可交付 / G 上线就绪）。

## 7. 汇报口径

每个切片结束按 §7 模板：Summary / Changed files / Verification（分层）/ Rollback / Risks / OpenSpec 状态（tasks n/m、change-log 条目）/ 文档确认块。
用户 E2E 反馈的问题走同一流程：取证 → 登记（日志+缺口表）→ 设计 → 修复 → 回归 → 上线供验。
