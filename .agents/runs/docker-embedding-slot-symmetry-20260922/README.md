# 文件路线 → 候选嵌入槽位（2026-09-22，分支 `delivery/docker`）

上一轮（第 4 组未验证项）的延续：本轮只做一件事 —— 让**文件路线**也能喂到候选（第三方网关）
嵌入槽位，与页面路线（`v2-admin-identity-native` 的 `mirror_env_vars`）对称。

| 文档 | 内容 |
|---|---|
| `01-slot-symmetry.md` | 文件路线 → 候选槽位：事实链复核、优先级规则、行为级 RED/GREEN、改动清单、5 条新测试、容器内机制级验收 |
| `02-v2-handoff.md` | 端到端**不归本轮**：判据（可直接照抄的命令）、谁验、R1/R2 的处置记录 |
| `04-l1-l2-and-packaging-check.md` | **L1 的带行号判决（CLI 赢 ⇒ 非阻塞）**、L2 修复（探针模型 id 取自随包 bundle）、出包自检 `check-delivery-consistency.py` 的硬/软两档与实测三段 |
| `03-preset-embedding-endpoint.md` | 交付预置里的 v1 时代嵌入端点/模型：两个字段的事实结论（带行号）、预置怎么改与为什么、5 条新测试、容器证据、**其它 v1 遗留清单（L1-L7，只列）** |
| `raw/00-RED-behavior.txt` | 行为级 RED（文件在、候选槽位空）与修好后同一 stub 的对照 |
| `raw/05-container-acceptance.txt` | 真实容器：收据模式 + **运行中服务进程**环境 + 显式环境变量优先 + 无回归（v1 槽位/页面档位） |
| `raw/06-preset-fix.txt` | 交付预置换掉后：生效端点来源由"受管覆盖"→`release-bundle-default`（同一实例，连接测试仍 200） |
| `raw/08-precedence-mutation.txt` | L1 判红演示：把 runner 的优先级反过来 ⇒ 守卫测试红（另两条仍绿） |
| `raw/09-packaging-check.txt` | 出包自检三段实测 + L2 的判红演示（指向修前安装器 ⇒ 2 failed） |
| `raw/03-D6-diagnosis.txt` | D6 修复验证（隔离容器：root:root 0700 状态目录 → exit 78 与新诊断文案） |

改的机制文件：`deploy/docker/entrypoint.sh`（投影 + 凭据收据 + D6）、
`deploy/docker/site-config/managed-settings.json`（删掉 v1 时代的嵌入地址/模型两个键）、
`deploy/docker/CONFIG-GUIDE.md`（§2 一个文件喂所有嵌入道 + §4 "地址可改、身份不可改"重写）、
`apps/miroflow-agent/tests/canonical_v2/`（新增 2 个测试文件、共 10 条）。

**证据里出现的 `sk-fake-…` 之类全部是本轮临时生成的假值**；未使用、未打印任何真密钥。
