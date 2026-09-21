# 命题 3 · 真 root（sudo）下的安装

**判定：通过（修完 2 个 root 专属缺陷之后）**；v1.1 现货交付包在 sudo 下**装不完**
（先 exit 11，再 exit 13），根因与修复见下。

环境：`sudo -n true` 通过（longxiang uid 1004，免密）；site root 新目录
`/var/tmp/mirothinker-fourth-verify-20260922`（SITE_ROOT 前缀，不碰真实
`/var/tmp/mirothinker-data-v2` 与活线状态目录）；端口 18298；PG 卷
`mirothinker-pgdata-fourth-v11`；交付包用**跨 fs 传过来的副本**
`/home/longxiang/delivery-xfer-v11/site-bundle`。

三次尝试，证据分别在 `raw/02-sudo-attempt1.txt`、`raw/02b-sudo-attempt2.txt`、
`raw/02c-sudo-attempt3.txt`：

| # | 安装器 | 材料 | 结果 | 根因 |
|---|---|---|---|---|
| 1 | v1.1 现货 | 4 个 key 用文档命令放（`sudo install -m 600`） | **exit 11**（65 s） | ① 交付包没有 `secrets/`（**D1**）⇒ 文档命令直接 `No such file or directory`；② `/tmp/mirothinker-checksums.out` 是固定路径、属于别人（**D4**）⇒ root 打不开 |
| 2 | v1.1 + 唯一 /tmp 路径 | 同上（先 `sudo mkdir -p secrets`） | **exit 13**（310 s，23 ok / 0 warn / 2 FAIL） | ③ 状态目录 `root:root 0700`（**D3**）⇒ 容器（uid 1004）入口预检 exit 78，无限重启 |
| 3 | **修好的**安装器 | 同上 | 见下（先被打断在健康之后，补跑得 exit 0） | — |

## 缺陷 D3：真 root 下宿主属主不匹配（**甲方会 100% 踩到**）

实测（attempt 2）：

```
/var/tmp/mirothinker-fourth-verify-20260922/var/tmp/mirothinker-canonical-v2-s12f
    owner=root:root mode=700                     ← 安装器 mkdir + chmod 700，属主是 root
index-v3-v2  owner=longxiang:longxiang mode=700  ← 解包时 tar 保留了包的 uid:gid（1004）
.env         owner=root:root mode=600
容器：app: status=restarting exit=78 restarts=12 oom=false
app 日志：[entrypoint] 预检失败：状态目录不可写：/var/tmp/mirothinker-canonical-v2-s12f（容器内 uid=1004）
```

容器以**数据属主 1004** 运行（.env 里 `MIROTHINKER_UID=1004`，取自 tar 的属主，
这是对的），但状态目录/密钥是 root 建的 ⇒ 容器 EACCES。这不是"配置不对"，
是**安装器在 root 下没有把宿主侧资产归一给容器 uid**。

同一根因还有第二个更隐蔽的后果：4 个密钥是 `root:root 0600`（文档第一条命令就是
`sudo install -m 600`），容器（uid 1004）**读不到**——即使状态目录修好，凭据也会
静默降级（`.sglang_api_key` 读不到 ⇒ 向量道不可用；`.deepseek_api_key` 读不到 ⇒
答案退化成模板）。本次实测：attempt 3 前两个 key 仍为 root:root 时，
`docker compose exec app test -r /opt/mirothinker/.sglang_api_key` 为 **NO**（见 02c 日志）。

**修（机制，`install-site.sh`）**：解包后即确定 `owner_uid/owner_gid`（数据属主），
在 root 安装时 `chown -R` 归一：数据根（mount-receipt / manual-recall 要可写）、
状态目录、`secrets/`、受管配置目录、日志目录；`.env` 归给发起 sudo 的操作者
（SUDO_UID），使非 sudo 的 `docker compose` 也能读。非 root 安装行为不变。

## 缺陷 D4：安装器用固定的 `/tmp` 文件名（root 与非 root 混合使用时必炸）

```
./install-site.sh: line 295: /tmp/mirothinker-checksums.out: Permission denied
  [FAIL] 校验失败，前几行差异：
install exit=11
```

真实原因不是校验和：`/tmp/mirothinker-checksums.out`、`/tmp/mirothinker-load.out` 是
**写死的路径**（Ubuntu 24.04 默认 `fs.protected_regular=2`，sticky 的 /tmp 里
不允许 root 以 O_CREAT 打开别人拥有的文件）。所以只要这台机器上**有人非 root 跑过一次**，
之后再 `sudo` 跑就必然在这里失败，而文案把人引向"包坏了"。
（现场等价情形：上一个人是普通用户、这次用 sudo；或反过来。）

**修（机制）**：改成 `mktemp`（脚本里其它地方本来就是 `mktemp`），并 `trap ... EXIT` 清理。

## 缺陷 D5：`--no-up` 是空操作

`--no-up` 只把 `DO_UP=0`（install-site.sh:56），全脚本再无任何使用 ⇒ 传了它照样
`docker compose up -d` 并等健康。用法行里公开写着这个选项，属于"文档承诺了但没实现"。

**修（机制）**：`--no-up` 时打印落地状态与起服务命令后 `exit 0`（不起容器、不等健康）。

## 缺陷 D6（诊断文案，未改）：entrypoint 的"一行修复"会建议 `user: "0:0"`

root 安装下宿主目录属主是 root，于是 entrypoint 的文案变成
`一行修复：user: "0:0"` —— 建议**把容器跑成 root**。这是治反了的方向
（真正的修法是把宿主资产 chown 给数据属主，或重跑安装器）。见 D3 修完之后，
这条文案在正常路径上不会再出现；但建议下一版把该分支文案改成
"重跑 install-site.sh（它会归一属主）"。

## 探针与首启耗时

- **第 3 次（修好的安装器）**：`docker load` 走了传送后的 `tar.gz`（`MIROTHINKER_SITE_FORCE_LOAD=1`）→
  容器起来后 `[entrypoint] 预检通过`、`mount-receipt` 写出、`manual-recall-v1` 建出、
  采集库迁移幂等 `{"revision":"V042","tables":42}`（`raw/02c-sudo-attempt3.txt`）。
- **首启耗时**（冷数据面 + 无 mount-receipt）：容器 `StartedAt=2026-09-21T17:14:55Z`，
  安装器轮询在 `…已等 7m32s` 之后拿到 `/api/health` 200 ⇒ **≈455 s**（README-FIRST 记录的是 7 分 13 秒）。
- **幂等重跑**（`raw/02d-sudo-attempt3b.txt`）：`install exit=0`、**25 ok / 0 warn / 0 FAIL**、
  全量校验 21 s + 解包 45 s + 10 件校验 41 s、健康检查**立刻通过**（boot=0s）、
  容器内验收探针 `mirothinker-verify` 全通、总耗时 109 s。
- **属主终态**：数据根 `longxiang:longxiang 755`、`index-v3-v2` `700`、状态目录 `700`、
  `secrets/` 与 4 个 key `600`、受管配置、日志目录、`.env` 都归到 `1004:1004`；
  容器内 `uid=1004 key_readable=yes state_writable=yes`；
  普通用户（非 sudo）在包里 `docker compose ps` 也能跑（`.env` 可读）。
- **后续三次重启**（反向实验的内部对照）：`health OK after 281s`（B2/C2），与文档承诺的 ≈276 s 一致。
