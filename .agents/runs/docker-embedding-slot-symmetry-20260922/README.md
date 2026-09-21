# 文件路线 → 候选嵌入槽位（2026-09-22，分支 `delivery/docker`）

上一轮（第 4 组未验证项）的延续：本轮只做一件事 —— 让**文件路线**也能喂到候选（第三方网关）
嵌入槽位，与页面路线（`v2-admin-identity-native` 的 `mirror_env_vars`）对称。

| 文档 | 内容 |
|---|---|
| `01-slot-symmetry.md` | 事实链复核、优先级规则、行为级 RED/GREEN、改动清单、5 条新测试、容器内机制级验收 |
| `02-v2-handoff.md` | 端到端**不归本轮**：判据（可直接照抄的命令）、谁验、以及两条跨线风险（R1 端点覆盖优先级 / R2 指南措辞） |
| `raw/00-RED-behavior.txt` | 行为级 RED（文件在、候选槽位空）与修好后同一 stub 的对照 |
| `raw/05-container-acceptance.txt` | 真实容器：收据模式 + **运行中服务进程**环境 + 显式环境变量优先 + 无回归（v1 槽位/页面档位） |
| `raw/03-D6-diagnosis.txt` | D6 修复验证（隔离容器：root:root 0700 状态目录 → exit 78 与新诊断文案） |

改的机制文件：`deploy/docker/entrypoint.sh`（投影 + 凭据收据 + D6）、
`apps/miroflow-agent/tests/canonical_v2/test_deploy_entrypoint_embedding_projection.py`（新增 5 条）、
`deploy/docker/CONFIG-GUIDE.md`（§2 一句：一个文件喂所有嵌入道 + 排障命令）。

**证据里出现的 `sk-fake-…` 之类全部是本轮临时生成的假值**；未使用、未打印任何真密钥。
