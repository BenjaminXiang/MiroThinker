# 容器交付线 · 第七轮：忘记管理员口令的出路（2026-09-22）

现场事故起的头：有人在 `/main` 改了口令、忘了新口令 ⇒ 登录不进去；口令只存 scrypt 哈希、
找不回，而交付侧（镜像与三份文档）此前**没有任何"重置"的说明或工具**。

| 文档 | 内容 |
|---|---|
| `01-reset-path.md` | **主文档**：母 agent 那张表的逐行复核（带行号）、选定的重置形状与"不用重启"的依据、工具做了什么（含"库不存在必须拒绝，否则会新建空副本"这个坑）、10 条测试 + 四轮变异、真镜像六段证据、"初始口令到底有没有交给甲方"的结论 |
| `raw/02-container-evidence.txt` | 真镜像（v1.1）六段：播种 → 持连接进程上跑重置（同一实例立刻看到新口令）→ 宿主侧权限/属主 → 判红（只挂工具不挂状态目录 ⇒ exit 3 且不新建空库）→ 逃生门（`docker compose run` 实测）→ `--status` 只读 |
| `raw/03-pytest-mutation.txt` | 10 条测试的"有没有牙"：基线 10/10 绿；四处变异分别红 1 / 9 / 1 / 2 条，每处都命中预期的那条；变异后工具 sha256 还原一致；**并且**脚本现在会只读核对活线审计行数（34 → 34，未再写活线） |

> ⚠ **本轮出过一次事故并已修复**：变异配方 MUTATION-2 曾把库路径改回 `DEFAULT_STATE_DIR`
> （= 开发机上的活线状态目录）⇒ 变异跑测试时**真的重置了活线 admin 口令 34 次**。
> 活线现在可用（口令在 `/var/tmp/mirothinker-canonical-v2-s12f/admin-password-reset-2026-09-22.txt`，
> 已验证登录 200）；修复见 `01-reset-path.md` 顶部那段（decoy 路径 + 夹具 patch `DEFAULT_STATE_DIR`
> + 演示脚本的活线审计行数核对）。

改的机制文件（本轮）：
`deploy/docker/reset_admin_password.py`（新增 → 镜像内 `mirothinker-reset-admin-password`）、
`deploy/docker/Dockerfile`（COPY + chmod）、
`apps/admin-console/tests/test_reset_admin_password_cli.py`（新增 10 条）、
`deploy/docker/CONFIG-GUIDE.md`（新增 §5，原 §5–§8 顺延）、
`deploy/docker/README.md`（§5.1）、
`deploy/docker/build-site-bundle.sh`（README-FIRST 加一行指向 §5）。

边界：**活线 18188 上出过一次事故（见上）**：变异配方一度把库路径指回活线状态目录，重置了活线口令 34 次；已修复、活线现在可用（口令在活线状态目录当天的 admin-password-reset 文件里）。其余 docker 操作都在 scratch 状态目录与一次性容器里；
真调用 0 次。
