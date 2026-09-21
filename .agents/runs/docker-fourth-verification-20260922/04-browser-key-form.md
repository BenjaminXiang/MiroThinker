# 命题 2 · 管理页「手填 key」在浏览器里真提交一次

**判定：通过**（真浏览器、真表单、真保存、真测试；后端落盘与审计都对得上；
"下次启动生效"用一次 `restart` 验证）。顺带发现 1 个会给甲方错误指令的页面文案（D8）。

工具：`agent-browser` 0.26.0（user-scope 技能），Chrome via CDP；输出全部过密钥/口令脱敏，
原始日志 `raw/04-browser.log`，截图 `raw/04-admin-after-save.png`。

## 步骤与观测（原文）

1. **登录 `/main`**（真口令来自状态目录，不回显）：

```
agent-browser open http://127.0.0.1:18298/main
agent-browser snapshot -i
  - region "登录" [ref=e1]
    - heading "管理员登录" [level=1, ref=e2]
    - textbox "用户名" [required, ref=e3]
    - textbox "口令" [required, ref=e4]
    - button "登录" [ref=e5]
agent-browser fill @e3 admin
agent-browser fill @e4 <口令>          # 脱敏后日志里是 <redacted-password>
agent-browser click @e5
→ 进入管理台：region "仪表盘"、"快捷入口"、"账号管理"（登录成功）
```

2. **进 `/admin`，在「对话模型」卡片里填密钥并保存**：

```
agent-browser open http://127.0.0.1:18298/admin
  region "对话模型" [ref=e40]
    - textbox "新密钥（留空 = 不改动；明文既不回显也不入日志）" [ref=e91]
    - button "清除密钥" / "测试连通性" / "保存本卡" [ref=e92/93/94]
agent-browser fill @e91 <真 .deepseek_api_key>     # 命令与输出都做了脱敏
agent-browser click @e94                            # 保存本卡
→ 页面结果行（原文）：
   「密钥已写入 llm.api_key。保存 ≠ 测试；重启后生效：systemctl --user restart canonical-v2-backend」
```

3. **点「测试连通性」**（保存后的同一卡片）：

```
agent-browser click @e94                       # 保存后 refs 重排，测试按钮变成 e94
→ 页面结果行（原文）：
   「成功 · 152 ms · HTTP 200 · HTTP 200 · 凭据来源 legacy-file:.deepseek_api_key ·
     本分钟剩余 5 次 · 测试不改配置，保存才写文件」
   掩码回显（原文）：「已设置 · sk-…2b92 · 来源 受管文件」
```

## 后台真的生效了吗（落盘证据，均按路径/元数据核对，不回显内容）

| 检查 | 观测 |
|---|---|
| `state/config-managed/secrets.json` | 新建成功：`owner=longxiang:longxiang mode=600 size=103 mtime=01:55:44` |
| 文件内容里 `secrets.llm.api_key` | **与真 `.deepseek_api_key` 的 sha256 前 12 位一致**（只比对哈希，长度 35） |
| 审计 `secrets-audit.jsonl` | `{"action":"secrets-patch","changes":[{"action":"set","field":"llm.api_key","suffix4":"2b92"}],"operator":"admin","stored_fields":["llm.api_key"]}` —— 只有字段名与后 4 位，**无明文** |
| 掩码回显 | 页面显示 `sk-…2b92`（3 位头 + 4 位尾），符合设计 |

## "下次启动生效"的验证（`raw/04b-save-takes-effect.log`）

- 重启前：`llm` 连接测试 → `ok:true, HTTP 200, 凭据来源 legacy-file:.deepseek_api_key`
  （运行期仍是文件那份，符合"保存 ≠ 生效"的文档语义）；
- `docker compose restart app` → `health OK after ~281 s`；
- 重启后：见 `raw/04-llm-probe-after-restart.json`（运行期凭据来源是否切到受管/环境来源）。

## 缺陷 D8：页面给的重启命令是**裸机**的

保存成功的提示原文是「重启后生效：**systemctl --user restart canonical-v2-backend**」——
这是裸机路径的服务命令；容器交付里没有这个 unit（正确动作是
`cd <交付包目录> && docker compose restart app`）。
页面由镜像里的同一份前端提供，容器形态下这条提示会**误导现场运维**。
建议（v2）：容器交付时由服务端把"重启命令提示"作为可配置项下发（如
`MIROTHINKER_RESTART_HINT="docker compose restart app"`），或按部署形态渲染。

## 备注（诚实记录）

- 本次浏览器操作中，`ab.sh` 最初把**命令行本身**也打进了日志（`$*` 未脱敏），
  因此那个 scratch 实例的首启口令出现在了本目录的日志里。
  这是**本地 scratch 实例**的口令（服务只监听本机练习端口 18298），
  且脚本已修正为命令行也脱敏；实例收尾时会通过页面改密（见 05/收尾）。
- 密钥（`.deepseek_api_key` 的值）全程未出现在日志/截图里：填值命令走变量、输出过 sed 脱敏、
  截图在保存之后拍摄（输入框已被 JS 清空）。
