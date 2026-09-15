# E2E 记录 · 配置中心密钥与连通性测试（scratch 18297）

> 采集时间：2026-09-15T17:40:03+08:00；脚本：`.agents/runs/config-center-secrets-and-tests/e2e-scratch-18297.sh`（可重放）
> scratch 配置目录：`/tmp/p13-config-center-scratch`；scratch 端口：admin 18297 / mock 18298；未触碰 18188。
> 真端点调用计数：**1 次**（embedding 100.64.0.27:18005，第 8 节）；其余全部打到本地 mock。
> 说明：本片实现期间的早期冒烟另用真实 Bocha 主机（pinned host，无法改写）以假密钥试过 **2 次**，均返回 HTTP 401（端点可达、凭据被拒绝），无计费风险，已如实计数（见 verification.md）。

```text

=== 0. start local mock transport (18298) + scratch admin server on 18297 ===
admin pid=1776826  mock pid=1776724
health: {"status":"ok"}

=== 1. page and W1 surfaces still answer (no regression) ===
GET /admin         -> 200
GET /config        -> 200
GET /system-status -> 200
POST providers hc  -> 200

=== 2. secrets before any write (read-only view, masks only) ===
GET /secrets -> 200
   bocha.api_key: configured=True mask=sk-…9eb1 origin=legacy-file:.bocha_api_key adopted=False
   rerank.api_key: configured=False mask=None origin=None adopted=False
plaintext in body? 0

=== 3. set a fake key from the page (PATCH) — never echoed ===
PATCH /secrets -> 200
   bocha.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False
   rerank.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False
plaintext in response? 0
file mode: 600  (0600 expected)
value present in the managed file (the carrier)? 2
plaintext in audit? 0
audit line: {"action": "secrets-patch", "at": "2026-09-15T09:39:54.313048+00:00", "changes": [{"action": "set", "env_var": "BOCHA_API_KEY", "field": "bocha.api_key", "suffix4": "beef"}, {"action": "set", "env_var": "CANONICAL_V2_RERANK_API_KEY", "field": "rerank.api_key", "suffix4": "beef"}], "operator": "e2e-operator", "stored_fields": ["bocha.api_key", "rerank.api_key"]}

=== 4. masked echo after write ===
GET /secrets -> 200
   bocha.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False
   rerank.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False
   restart_required: 修改后需重启服务生效（服务启动时读取受管文件，不做热加载）

=== 5. connectivity test BEFORE saving, with unsaved endpoint + key (local mock, 1 call) ===
POST /connections/test (rerank -> mock, unsaved values) -> 200
{
  "connection": "rerank",
  "label": "Rerank 模型端点",
  "ok": true,
  "latency_ms": 1,
  "http_status": 200,
  "detail": "HTTP 200",
  "used": {
    "api_key_source": "request",
    "base_url": "http://127.0.0.1:18298",
    "model": "qwen3-reranker-8b"
  },
  "rate": {
    "per_minute_limit": 6,
    "min_interval_seconds": 1.0,
    "remaining": 5
  },
  "restart_required": null
}
plaintext in response? 0
mock calls served: 2 (includes the 1 readiness probe)
MOCK-CALL path=/reject status=401 auth=no
MOCK-CALL path=/v1/rerank status=200 auth=yes

=== 6. rate limit: an immediate second test is rejected without another call ===
POST /connections/test (again) -> 429
{
  "detail": {
    "error": "rate_limited",
    "connection": "rerank",
    "retry_after_seconds": 1
  }
}

=== 7. failure path: mock answers 401 → 'endpoint reachable, credential rejected' ===
POST /connections/test (rerank -> mock/reject) -> 200
{
  "connection": "rerank",
  "label": "Rerank 模型端点",
  "ok": false,
  "latency_ms": 2,
  "http_status": 401,
  "detail": "HTTP 401：端点可达，凭据被拒绝",
  "used": {
    "api_key_source": "managed-file",
    "base_url": "http://127.0.0.1:18298/reject",
    "model": "qwen3-reranker-8b"
  },
  "rate": {
    "per_minute_limit": 6,
    "min_interval_seconds": 1.0,
    "remaining": 5
  },
  "restart_required": null
}

=== 8. real-endpoint probe: exactly ONE call, embedding 100.64.0.27:18005 ===
POST /connections/test (embedding, real endpoint) -> 200
{
  "connection": "embedding",
  "label": "Embedding 模型端点",
  "ok": false,
  "latency_ms": 5,
  "http_status": 401,
  "detail": "HTTP 401：端点可达，凭据被拒绝",
  "used": {
    "api_key_source": "none",
    "base_url": "http://100.64.0.27:18005/v1",
    "model": "Qwen/Qwen3-Embedding-8B"
  },
  "rate": {
    "per_minute_limit": 6,
    "min_interval_seconds": 1.0,
    "remaining": 4
  },
  "restart_required": null
}

=== 9. clear, then set again ===
PATCH clear -> 200
   bocha.api_key: configured=True mask=sk-…9eb1 origin=legacy-file:.bocha_api_key adopted=False
PATCH set again -> 200
   bocha.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False

=== 10. restart the scratch service: adoption happens at startup, not hot ===
--- before restart (the running process has not read the new value) ---
GET /secrets -> 200
   bocha.api_key: configured=True mask=sk-…beef origin=managed-file adopted=False
--- after restart (new pid=1777616) ---
GET /secrets -> 200
   bocha.api_key: configured=True mask=sk-…beef origin=managed-file adopted=True

=== 11. plaintext leakage sweep (responses, logs, audit, page) ===
sentinel in server log : 0
sentinel in audit file : 0
sentinel in /admin html: 0
sentinel in /secrets   : 0
sentinel in /config    : 0

=== 12. a new switch written from the page + the read-only policy ===
PATCH /config serving.{web_topical_floor,rerank_timeout_seconds} -> 200
   changed: ['serving.rerank_timeout_seconds', 'serving.web_topical_floor']
PATCH /config serving.full_verify (display-only) -> 422
{
  "detail": "field is display-only on the admin page: serving.full_verify: 启动全量校验：开启会把启动从秒级拉到分钟级，必须由服务单元决定（只读展示）"
}
PATCH /config serving.not_a_field -> 422
{
  "detail": "field is not in the managed settings whitelist: serving.not_a_field"
}
POST /connections/test (llm without endpoint) -> 200
{
  "connection": "llm",
  "label": "LLM 档位（本地/校内）",
  "ok": false,
  "latency_ms": 0,
  "http_status": null,
  "detail": "端点不合法：endpoint is not configured",
  "used": {
    "api_key_source": "legacy-file:.sglang_api_key",
    "base_url": null,
    "model": null
  },
  "rate": {
    "per_minute_limit": 6,
    "min_interval_seconds": 1.0,
    "remaining": 5
  },
  "restart_required": null
}

=== 13. restart adopts file-owned switches (env untouched, env still wins) ===
restarted (new pid=1778181)
settings file serving section:
{
  "full_verify": null,
  "mount_receipt_path": null,
  "rerank_max_documents": null,
  "rerank_timeout_seconds": 2.5,
  "turn_debug_dir": null,
  "web_topical_floor": false
}
env override still wins over the file for a pinned var (CANONICAL_V2_RERANK_TIMEOUT_SECONDS=9.0):
   settings applied: ('serving.web_topical_floor',)
   settings skipped (env wins): ('CANONICAL_V2_RERANK_TIMEOUT_SECONDS',)
   adopted env var: BOCHA_API_KEY,CANONICAL_V2_RERANK_API_KEY,CANONICAL_V2_WEB_TOPICAL_FLOOR
   web floor -> 0 | rerank timeout -> 9.0

E2E done.
```
