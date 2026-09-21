# 容器交付线 · 第 4 组未验证项闭环（2026-09-22，分支 `delivery/docker`）

来源：`docs/plans/2026-09-21-customer-site-migration-log.md` 第 12 轮末尾的「未验证」四条。
人类文档由父 agent 写；本目录只放**执行与证据**。

## 四条命题的结论

| # | 命题 | 结论 | 证据 |
|---|---|---|---|
| 1 | `--force-recreate` 的反向实验 | **通过（且推翻原推断）**：`restart` 就够；真正的坑是**属主**不是 inode | `03-force-recreate-experiment.md`、`raw/03-*.txt|json`、`raw/03b-restore.txt` |
| 2 | 浏览器里真提交一次 key 表单 | **通过**（登录 → 填写 → 保存 → 测试 → 下次启动真生效） | `04-browser-key-form.md`、`raw/04-browser.txt`、`raw/04-*.json`、`raw/04-admin-after-save.png` |
| 3 | 真 root（sudo）下的安装 | **通过（修完 3 个 root 专属缺陷后）**：v1.1 现货包在 sudo 下装不完 | `02-sudo-install.md`、`raw/02-sudo-attempt1.txt`、`raw/02b-sudo-attempt2.txt`、`raw/02c/02d-*.txt` |
| 4 | 跨文件系统传送后的完整链路 | **通过**：跨 fs 拷贝 → 17/17 逐文件校验 → 从副本安装/load/起服 | `01-cross-filesystem-transfer.md`、`raw/01-*.txt` |

新发现的缺陷（8 条，5 条已修机制、3 条仅报告）：见 `findings.md`。

## 复现路径（一条链）

```bash
# ① 跨 fs 传送 + 校验（/var/tmp → /home）
cp -a /var/tmp/mirothinker-site-bundle-v11 /home/longxiang/delivery-xfer-v11/site-bundle
# ② 按文档放 4 个 key（sudo install -m 600）→ sudo 安装（SITE_ROOT 前缀，端口 18298）
cd /home/longxiang/delivery-xfer-v11/site-bundle
sudo env MIROTHINKER_SITE_ROOT=/var/tmp/mirothinker-fourth-verify-20260922 \
     MIROTHINKER_SITE_PORT=18298 MIROTHINKER_SITE_PG_VOLUME=mirothinker-pgdata-fourth-v11 \
     ./install-site.sh
# ③ 反向实验 / ④ 浏览器表单：见 03*.sh 与 ab.sh（ab.sh 用法： ./ab.sh open http://127.0.0.1:18298/main）
```

## 本次演练留下的现场（未清理，供复核）

| 东西 | 位置 | 备注 |
|---|---|---|
| 传输后的交付包副本 | `/home/longxiang/delivery-xfer-v11/site-bundle`（3.4 GB） | 内含修好的 `install-site.sh`（原版留档 `install-site.v11-orig.sh`） |
| 站点根 | `/var/tmp/mirothinker-fourth-verify-20260922`（数据面 7 GB + 状态目录） | 端口 **18298**，PG 卷 `mirothinker-pgdata-fourth-v11` |
| 容器 | `mirothinker-serving-app-1` / `mirothinker-serving-db-1`（compose 项目 `mirothinker-serving`） | 收尾时 healthy；停：`cd <包> && sudo docker compose down`（数据/状态在宿主，不丢） |
| 管理台 | `http://127.0.0.1:18298/main` | 收尾时已改密；新口令在实例状态目录（见下） |

收尾动作（2026-09-22 02:1x）：在浏览器里把 admin 口令从首启口令改成新口令
（`<state>/admin-password-rotated-20260922.txt`，0600），因为首启口令在本目录的日志里出现过一次
（`ab.sh` 早期的命令行未脱敏，已就地脱敏；实例口令已轮换）。
