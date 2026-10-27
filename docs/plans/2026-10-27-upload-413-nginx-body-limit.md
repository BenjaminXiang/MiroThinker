# 上传失败（413）：nginx 请求体上限只有 1 MB

> 现象：客户在 `/upload` 页上传 20 MB 的专利 XLSX，页面报
> `上传失败: SyntaxError: Unexpected token '<', "<html> <h"... is not valid JSON`。

## 1. 根因

浏览器把响应当 JSON 解析，但收到的是 **HTML 错误页** —— 说明请求根本没到应用。

证据（客户机 `/var/log/nginx/access.log`）：

```
10:01:35 POST /api/canonical-v2/admin/uploads/patent 413 594
10:02:37 POST /api/canonical-v2/admin/uploads/patent 413 594
```

nginx 的 `client_max_body_size` **默认只有 1 MB**，反代配置里从未设置过；
文件 20 MB → nginx 直接回 413 + HTML 页面 → 前端 `response.json()` 抛
`Unexpected token '<'`。

应用侧其实允许很大：`DEFAULT_MAX_UPLOAD_BYTES = 128 MB`
（可用 `MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES` 覆盖），所以卡点只在反代。

## 2. 修复

`/etc/nginx/snippets/gxzx-proxy.conf` 末尾追加（先备份为 `*.bak-20261027`）：

```nginx
# 上传：XLSX 可达 20MB+；应用侧上限 128MB（MIROTHINKER_ADMIN_UPLOAD_MAX_BYTES）
client_max_body_size 128m;
```

`nginx -t` 通过 → `systemctl reload nginx`（不中断服务）。

## 3. 验证

1. 20 MB 匿名请求：修复前 **413**（HTML），修复后 **401**（JSON）——请求体已被接收；
2. 真实文件 + 管理员会话 + `dry_run=true`：
   **202**，`size_bytes=20025385`、sha256 与文件一致；
3. 任务结果：`status=succeeded`，**17,963 行解析、0 失败、0 跳过**。

## 4. 为什么以前没暴露

之前验证上传用的都是小文件（KB 级），1 MB 上限碰不到；这次专利表 20 MB 才撞上。
**部署检查项**：反代的 `client_max_body_size` 必须 ≥ 应用侧上限（128 MB），
否则大文件在反代层被静默拒绝，前端只能看到一句 JSON 解析错误。

## 5. 现状

- 修复已在客户机生效（nginx 已 reload，无需重启应用）；
- 用户可以重试上传；需要真正入库时取消「干跑」勾选即可。
