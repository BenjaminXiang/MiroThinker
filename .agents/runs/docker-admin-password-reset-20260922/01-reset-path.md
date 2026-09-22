# 忘记管理员口令：容器里的出路（2026-09-22 · 容器交付线第七轮）

现场事故：有人在 `/main` 改了口令、忘了新口令 ⇒ 登录不进去。口令只存 scrypt 加盐哈希、**永不存
明文** ⇒ 找不回，只能重置；而交付侧此前**没有任何一条可执行的出路**（`CONFIG-GUIDE.md` /
`README.md` / `README-FIRST` 里 `grep` 不到"忘记/重置"，容器镜像里也没有重置工具）。

| 产物 | 位置 |
|---|---|
| 工具（新增） | `deploy/docker/reset_admin_password.py` → 镜像内 `/usr/local/bin/mirothinker-reset-admin-password` |
| 测试（新增 10 条） | `apps/admin-console/tests/test_reset_admin_password_cli.py`（真走 `POST /api/auth/login` 与 `/api/auth/me`） |
| 镜像接线 | `deploy/docker/Dockerfile`（COPY + chmod 0755） |
| 甲方文档 | `deploy/docker/CONFIG-GUIDE.md` **§5「忘记管理员口令怎么办」**（新增，原 §5–§8 顺延为 §6–§9） |
| 运维文档 | `deploy/docker/README.md` **§5.1**（含"容器起不来"的逃生门） |
| 交付包首屏 | `deploy/docker/build-site-bundle.sh`（README-FIRST 生成块加一行指向 §5） |
| 证据 | `raw/02-container-evidence.txt`（真镜像六段）、`raw/03-pytest-mutation.txt`（四变异） |

**真调用计数 = 0**（本轮只碰本地 docker 与本地 sqlite；没有任何外呼）。

> ⚠ **必须先读这一段：我在本轮一度把活线口令改了（已定位、已修、活线现在可用）**
>
> * **发生了什么**：变异测试的配方（`03-pytest-mutation-demo.sh` 的 MUTATION-2）把工具的库路径
>   改成 `admin_auth.DEFAULT_STATE_DIR / DB_FILENAME` —— 而**开发机上这个默认值就是活线的状态目录**
>   `/var/tmp/mirothinker-canonical-v2-s12f`。于是那次变异跑测试时，每一条调用工具的测试都**真的**
>   重置了活线 admin 口令。审计表里留下 **34 条** `admin.password_reset`（actor=`cli:longxiang`、
>   detail=`mirothinker-reset-admin-password`），时间 10:49:23 / 10:49:51 / 10:52:17 / 10:53:08
>   （四次变异演示各一批）；活线 admin 的 `password_epoch` 现在是 **39**。
> * **活线现在的状态**：**可用**。当前口令 = `/var/tmp/mirothinker-canonical-v2-s12f/admin-password-reset-2026-09-22.txt`
>   （0600、属主 longxiang、17 字节、mtime 10:53:10）里的那一个 —— 我用它**做过一次**登录验证：
>   `POST http://127.0.0.1:18188/api/auth/login` ⇒ **HTTP 200（admin/admin）**，口令没有打印、
>   没有落进任何文件。**母 agent 请 `sudo cat` 该文件后用页面改成一个你自己知道的口令。**
> * **代价**：你（或现场）在 10:43 那一次重置的旧口令、以及更早的口令，全部作废；所有 admin 会话
>   已失效（epoch 递增）；审计表里多了 34 条噪声行 —— **我没有去删它们**（删也是一次写活线的动作，
>   留给你决定）。
> * **根因（两层都是我的错）**：① 变异配方指向了一个**真实存在**的路径，而不是一个不可能被写到的
>   decoy；② 测试只通过环境变量把库引到 `tmp_path`，夹具**没有**同时把模块的兜底
>   `DEFAULT_STATE_DIR` 也挪走 —— 于是"忽略环境变量的变异体"照样能摸到活线。
> * **已修（三层，全部在本轮提交里）**：① M2 改成指向 `/tmp/mutation-decoy-not-a-real-state/…`
>   （不存在 ⇒ 工具自己 exit 3，写不到任何地方）；② 测试的 `state_dir` 夹具**同时** patch
>   `admin_auth.DEFAULT_STATE_DIR` 到 `tmp_path`，并断言解析出来的库落在 `tmp_path` 里；③ 变异演示
>   脚本现在会在跑之前/之后**只读**统计活线 `admin.password_reset` 行数，一旦变化就打印 `FAIL`
>   （本轮修好后重跑：34 → 34，"没有往活线写一个字节"）。
> * 教训（写进这一条，免得下次再犯）：**这台机器上 `/var/tmp/mirothinker-canonical-v2-s12f` 是活线
>   目录**。任何"错误分支"可能落到该路径的测试/变异都必须靠 patch 模块级默认值来兜底，只 steer
>   环境变量不够。

---

## 1. 复核母 agent 那张表（带行号；有错直说）

| 表里的事实 | 复核 | 依据 |
|---|---|---|
| 口令只存 scrypt 加盐哈希、无法找回 | **对** | `apps/admin-console/backend/services/admin_auth.py:1-8` 模块 docstring 原话 "a stored password is only ever a salted ``scrypt`` hash"；哈希参数 `:48-52`（N=2^14, r=8, p=1, dklen=32） |
| 状态目录里累积历次重置文件 | **对** | 现场状态目录实测：`admin-initial-password.txt`(9-17)、`admin-password-reset-2026-09-18.txt`、`admin-password-reset-2026-09-22.txt`（今天 10:43） |
| 重置入口是 `AdminAuthStore.set_password` | **对** | `admin_auth.py:357`（顺带：它会 `password_epoch + 1`，`:370`） |
| `store_from_environment()` 解析库与密钥路径 | **对** | `:490`；真正的解析在 `default_db_path()` `:127-140`：`CANONICAL_V2_ADMIN_AUTH_DB` → 否则 `CANONICAL_V2_ACCESS_LOG_DB` **的同目录** → 否则 `DEFAULT_STATE_DIR`（`:36` = `/var/tmp/mirothinker-canonical-v2-s12f`）；密钥 `default_key_path()` `:143-153` |
| `prepare_private_file()` 负责 0600 落盘 | **对** | `:216-238`（顺带：它**会建文件**，所以"库不存在"必须由调用方先判 —— 见 §3 的坑） |
| 容器形态：状态目录挂在哪 | **对**（补全） | `compose.yaml`：`${MIROTHINKER_STATE_DIR:-/var/tmp/mirothinker-canonical-v2-s12f}` bind 到**同一个**容器内绝对路径；库与密钥就在这个目录里 |
| 服务进程是否持有该库 | **对，实测** | 宿主 `fuser` 与 `/proc/*/fd` 扫描：多个进程持有 `/var/tmp/mirothinker-canonical-v2-s12f/admin-auth.sqlite3`（含 `-wal`/`-shm`），`admin-auth.sqlite3-wal` 今天 10:44 还在写 ⇒ WAL 模式、长连接 |
| 外部写入会不会被服务看到 | **会**（容器内实测） | `raw/02-container-evidence.txt` ②：容器里一个进程持有 store 连接，另一个进程跑重置，**同一个实例**上 `old_works=True → False`、`new_works=True`。⇒ **不需要重启服务** |
| 初始口令的交付面 | **交到了**（见 §6） | 首启播种写文件 + 打印 stdout；`install-site.sh:505/560`、`README.md:277`、`README-FIRST`、`CONFIG-GUIDE.md:176` 都指向它 |

**表的判红链也复核了**：旧口令 → `401 invalid_credentials`（`api/admin_auth.py:146-157`）、
限流 5 次锁 1 分钟（`:31` 页面文案 `static/main.html:31`；`:37` 模块常量、`:506` docstring）。

**一个表里没写、我加上的事实**：改口令会**递增 `password_epoch`**，而会话 cookie 里带着这个代次
（`admin_session.py:174`：`account.password_epoch != ticket.password_epoch ⇒ 会话作废`）⇒ 重置不仅
让旧口令失效，**旧会话也立刻失效**（页面上会被踢回登录页）。这一条写进了文档，也有测试锁住。

---

## 2. 选的重置形状，与"要不要重启"

**形状**：镜像内新增一个入口（`mirothinker-reset-admin-password`），在**容器里**跑：

```bash
cd <交付包目录>
docker compose exec app mirothinker-reset-admin-password          # 幂等；输出里没有口令
sudo cat ${MIROTHINKER_STATE_DIR}/admin-password-reset-<日期>.txt
```

为什么是"容器内 exec"而不是"宿主上跑脚本"：① 写入者与服务的 **uid 相同**（= 数据属主），
不会因为换了属主而造出服务读不动的 `-wal`/`-shm`；② 路径天然是**挂载出来的那个库**
（容器内默认解析 = `/var/tmp/mirothinker-canonical-v2-s12f/admin-auth.sqlite3`，与冻结命令文件里
`CANONICAL_V2_ACCESS_LOG_DB` 的同目录解析**同一个文件**）；③ 工具随镜像走，v2 重打自动带上
（无需在交付包里额外放脚本）。

**要不要重启：不要。** 登录是每次一个新的 SELECT；SQLite WAL 下别的连接提交的写入立刻可见
（容器内两进程实测见 §4.2）。旧口令与旧会话当场失效，直接刷新页面用新口令登即可。

**没有削弱限流**：限流是**服务进程内**的内存计数（`AdminLoginThrottle`，`api/admin_auth.py:39`
每个进程一个实例），本工具读都不读它；测试里专门有一条：先 5 次错误把账号锁上 ⇒ 重置 ⇒ 用**新**
口令立刻登 ⇒ 仍然 `429 locked`（证明重置没有顺手把锁定清掉）。

---

## 3. 工具做了什么（`deploy/docker/reset_admin_password.py`）

1. **解析服务在用的库**：`admin_auth.default_db_path()`（模块自己的解析，不另写一套）；`--db` 可显式覆盖。
2. **库不存在就拒绝**（exit 3），**绝不新建**：这是本轮最容易踩的坑 —— `AdminAuthStore.__init__`
   会 `prepare_private_file()` **建文件**、再 `_initialize_schema()` 建表，所以"路径写错"不会报错，
   只会安静地造出一个空库让你白改一场。工具先在构造 store 之前判存在性。
3. `AdminAuthStore.set_password()`：换哈希 + 换盐 + `password_epoch + 1`（旧会话失效）。
4. `append_audit(action="admin.password_reset")`：actor = `cli:<USER 或 uid:N>`，detail 里写明是本工具。
5. **自检**：写完立刻 `verify_credentials(新口令)` 必须为真，否则红着退出（不让操作者扑空）。
6. 新口令由模块自己的 `generate_password()` 生成（16 位、去掉 `l/1/o/0`），**只写进**状态目录里
   0600 的 `admin-password-reset-<YYYY-MM-DD>.txt`（沿用首启口令的命名与权限约定），**从不打印**；
   只打印**路径**。同一天重跑 = 覆盖今天那个文件（幂等，以最后一次为准）。
7. `--status`：只读报告（库路径/账号/口令文件清单，不打印任何内容）。

`--status` 在只有库、还没有会话签名密钥的库里会显示"会话签名密钥：（不存在）"—— 这是**对的**：
密钥在服务第一次签发会话时才建（`SessionCodec`），重置口令不需要它。

---

## 4. 能判红的检查 + 结果

### 4.1 测试（10 条，`raw/03-pytest-mutation.txt`）

夹具：`TestClient(app)` + scratch 状态目录，**只设**冻结命令文件里那一个变量
（`CANONICAL_V2_ACCESS_LOG_DB`），与真实布局一致；口令全是现场生成的临时值。

| 测试 | 锁住什么 |
|---|---|
| `reset_rotates_the_password_and_the_old_one_is_rejected` | **主判红链**：旧口令 200 → 重置 → 新口令 200、旧口令 401 `invalid_credentials`（真走登录路由） |
| `the_tool_never_prints_the_password` | 输出里没有口令（只打印路径） |
| `the_reset_file_lands_beside_the_mounted_db_at_0600` | 0600、库旁边、命名沿用约定 |
| `the_tool_targets_the_database_the_service_uses` | 改的是服务那个库；**别处的同名库一个字节没动** |
| `the_tool_refuses_a_missing_database_instead_of_creating_one` | 库不存在 ⇒ exit 3 且**不新建** |
| `a_second_run_is_idempotent` | 连跑两次都成功；epoch 1→2→3；旧的那次口令失效 |
| `the_audit_trail_records_the_reset` | 审计里有一条 `admin.password_reset`（走模块入口的证据） |
| `a_reset_invalidates_the_old_session` | 旧 cookie 在重置后过不了 `/api/auth/me`（401） |
| `the_login_route_still_locks_after_a_reset` | 锁定不被重置解除（**限流没被削弱**） |
| `status_is_read_only` | `--status` 不改库、不写文件 |

**变异测试（测试有没有牙）**：基线 10/10 绿；
拆"不打印口令" ⇒ 1 红（正是那条）；拆"库路径解析"（改用写死状态目录）⇒ 9 红；
拆"库不存在就拒绝" ⇒ 1 红（正是那条）；把 `set_password` 换成**手写 SQL**（不递增 epoch）
⇒ 2 红（会话失效 + 幂等/代次）。四轮变异后工具 sha256 与变异前一致（脚本 `trap` 还原）。

> 变异 3 第一次跑没红：锚点 `if not db_path.is_file():` 在文件里有**两处**（`--status` 与重置各一处），
> `replace(..., 1)` 改到了前一处。改成带下一行的唯一锚点后正确变红 —— 这条记在这里，免得下次再踩。

### 4.2 真镜像六段（`raw/02-container-evidence.txt`，`mirothinker-serving:v1.1`，容器身份 1004:1004 = 数据属主）

| 段 | 内容 | 结果 |
|---|---|---|
| ① | 用**镜像自己的** `admin_auth` 在 scratch 状态目录播种 | `db=True initial-file=True` |
| ② | 容器内：进程 A 持有 store 连接 → 子进程跑重置 → **同一实例**再读 | `old_works=True → False`、`new_works=True`、`mode=0o600 uid=1004`、`audit=['ok']`、`epoch=2` |
| ③ | 宿主侧看产物 | `admin-auth.sqlite3 -rw-------`、`admin-password-reset-2026-09-22.txt -rw-------`（属主 = 数据属主） |
| ④ | **判红**：只挂工具、不挂状态目录 | `[FAIL] 口令库不存在…` ⇒ exit 3，且容器层里**没有**被建出空库（`ls: cannot access …`） |
| ⑤ | "容器起不来"的逃生门（`docker compose run --rm --no-deps --entrypoint …`） | exit 0，读到的是挂载出来的那个库（README §5.1 那条命令**实测过**，不是纸上写的） |
| ⑥ | `--status` 只读 | exit 0，只列文件名，从不打印内容 |

**哪一半留给 v2 冷装**：② 用的是"两个进程 + 镜像自己的模块"来复现服务进程的连接语义
（省掉一次 ≈281 s 的启动）；**真站点进程**上"重置 → 新口令登录 200 / 旧口令 401"的端到端，
应由 v2 冷装那一轮在**真容器 + 真 /main 页面**上补一次（一条 curl 就够，见 §5）。

---

## 5. 文档加了什么

* **`CONFIG-GUIDE.md` §5「忘记管理员口令怎么办（唯一的出路是重置）」**（甲方视角）：
  ① 首启口令在哪（文件 + 首启日志 `docker compose logs app | grep admin-auth` + 安装器收尾提示），
  并点明"改过密后那个文件就作废，以最近一个 `admin-password-reset-<日期>.txt` 为准"；
  ② **一条命令**（`docker compose exec app mirothinker-reset-admin-password` + `cat` 那条文件）；
  ③ 重置之后（旧口令/旧会话立即失效、**不用重启**、限流不受影响也不会被解除、审计留痕）；
  ④ "改完请立刻记下"（记好之后可以删掉那个文件）。原 §5–§8 顺延为 §6–§9，内部一处
  "见 §6 最后一行"改为 §7；§9 ② 与**症状表**各加一行指向 §5（`登录一直 401` / `429 locked`）。
* **`README.md` §5.1**（运维视角）：同一条命令 + `--status` + "容器起不来"的逃生门 + 指向 §5。
* **`README-FIRST.txt`**（`build-site-bundle.sh` 生成块）：首启口令那两行下面加一句
  "**忘了口令**不用重装：一条命令重置，见 CONFIG-GUIDE.md §5"。

v2 冷装时要顺手做的（不阻塞本轮）：真容器上跑一次 §5 的一条命令 + 用新口令登 `/main` 一次
（`curl -sS -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18188/api/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"$(sudo cat …)\"}"` ⇒ 200）。

---

## 6. "初始口令在容器形态下有没有真的交给甲方"

**结论：交到了，不是黑洞** —— 但有两处值得修（一处本轮已修，一处留给你定）。

交到的三条路径（都能从宿主看到）：

1. **文件**：首启播种 `seed_initial_admin()`（`admin_auth.py:452-478`，由 `backend/main.py:88`
   在服务启动时调用）把口令写进 `<状态目录>/admin-initial-password.txt`（0600），**并且**
   往服务 stdout 打一行 `[admin-auth] first-boot administrator 'admin' password: …`
   ⇒ 容器形态下这行在 `docker compose logs app` 里；
2. **安装器收尾**：`install-site.sh:505` 与 `:560` 都打印"首启口令：`${STATE_DIR}/admin-initial-password.txt`"；
3. **文档**：`README.md:277`（`cat` 一行）、`CONFIG-GUIDE.md` §9 ②、交付包首屏 `README-FIRST.txt`。

现场证据：状态目录里 `admin-initial-password.txt` 在位（9-17 22:41，17 字节）。

**两处真正的问题**（都不是"没交"，是"交了但会误导"）：

* **作废文件没有任何标记**：改过密之后 `admin-initial-password.txt` 仍然是那个口令的明文，操作者
  第一反应就是 `cat` 它 ⇒ 401 ⇒"站点坏了"。本轮在 §5 用一个 ⚠ 段写明"它只在首启那一次有效"，
  工具的输出与 `--status` 也会提示"以最近一个 `admin-password-reset-<日期>.txt` 为准"。
  （**没有**去动 `admin-initial-password.txt` 本身：改它的语义会牵扯播种逻辑与 README，超出本轮。）
* **只在"空库首启"时播种**：如果首启时库已存在（例如状态目录被复用/拷贝），**不会**再有初始口令
  ⇒ 那种情况下唯一的出路就是本文的重置命令（现在有了）。
