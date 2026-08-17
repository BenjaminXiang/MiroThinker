# 客户测试服务器：部署与热更新手册（2026-08-17）

> 双轨结构：
> - **`release/customer-test`**（GitHub）= 客户测试服务器跟踪的稳定线。只接收
>   "已验收修复的合并"，不接受任何直接开发提交。
> - **`fix/p1-p8-systematic`** = 系统性修复线（独立 worktree
>   `.worktrees/systematic-fix`），P1–P8 修复与管线重做全部在此进行，不影响
>   release，直到验收后合并。
> - 本机生产 18188 继续由 `.worktrees/canonical-v2-s11-consolidation`
>   （`codex/canonical-v2-s12a-ready`）服务。

## 一、首次部署（客户测试服务器）

按迁移方案执行：`docs/plans/2026-08-14-customer-site-migration-plan.md`
第 2–5 步（三批货打包 → 目标机环境 → 数据落位校验 → 模型端点改造）。
差异只有一点：**代码包改为从 GitHub 拉取**

```bash
git clone -b release/customer-test git@github.com:BenjaminXiang/MiroThinker.git
```

数据（serving pack，~950M）不走 git：用 `deploy/backup-canonical-v2.sh` 的
一致性备份产物，按迁移方案第 4 步落位到 `/var/tmp/mirothinker-canonical-v2-s12f/`
并逐文件校验哈希。密钥按第 2/4 步单独加密渠道传递。

## 二、热更新流程（修复后，你在客户机执行）

```bash
cd /path/to/MiroThinker
git fetch origin
git checkout release/customer-test
git reset --hard origin/release/customer-test
# 重启服务（TERM 后 systemd 自动重生，或 systemctl --user restart canonical-v2-backend）
# 健康检查： curl http://127.0.0.1:18188/api/health  → {"status":"ok"}
```

热更新只换**代码**；数据（serving pack）不随 pull 变化——新数据以新 pack
发布（rsync 落位 + 校验 + 重启），另行通知。

## 三、修复→发布的工作流（本机侧）

1. 修复在 `fix/p1-p8-systematic`（worktree `.worktrees/systematic-fix`）进行；
2. 每个修复经测试/评审验收后：
   ```bash
   git checkout release/customer-test && git merge --no-ff <修复提交或分支>
   git push origin release/customer-test
   ```
3. 通知客户机执行第二节热更新；
4. 本机生产（如需同步）：在 s11-consolidation worktree
   `git fetch && git merge origin/release/customer-test` 后重启。

## 四、当前已知问题清单（随 release 首版携带，供客户测试预期管理）

见 `.agents/runs/2026-08-17-user-testing-round-1/findings.md`（P1–P8）。
其中 P5/P8 属数据覆盖问题（serving pack 8/1 薄回填），修复走数据重建线，
与代码热更新解耦。
