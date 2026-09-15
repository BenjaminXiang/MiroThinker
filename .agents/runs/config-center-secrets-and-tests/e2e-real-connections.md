# 真端点五连接验收记录（P13 follow-up，解析链对齐后）

> 采集时间：2026-09-15T18:26:26+08:00
> 脚本：`.agents/runs/config-center-secrets-and-tests/e2e-real-connections.sh`（可重放；`SKIP_CALLS=1` 只跑泄漏检查、零真调用）
> 运行位置：**scratch 进程**（端口 18297，受管配置目录 `/tmp/p13-real-connections/managed`），环境与活线一致（`CHAT_LLM_PROFILE=deepseekv4flash`，所有凭据环境变量均已 `env -u` 清空，因此解析必须走仓库 key 文件）。
> **18188 未重启、未触碰**：线上仍是上一版构建（本片改动需一次重启生效，见交接）。
> 真端点调用计数：bocha 1 / serper 1 / embedding 1 / llm 1，**rerank 0**（如实报告运行期未启用）＝ 本轮共 4 次；泄漏复核轮 0 次。

```text
scratch admin server pid=1968197 on 18297 (18188 untouched)

=== runtime state as the page reports it ===
  bocha     enabled=True  endpoint=https://api.bochaai.com/v1/web-search
            credential_origin=legacy-file:.bocha_api_key pending_restart=False
            note=运行期使用 provider 固定主机（https://api.bochaai.com/v1/web-search）；凭据来源 legacy-file:.bocha_api_key
  serper    enabled=True  endpoint=https://google.serper.dev/search
            credential_origin=legacy-file:.serper_api_key pending_restart=False
            note=运行期使用 provider 固定主机（https://google.serper.dev/search）；凭据来源 legacy-file:.serper_api_key
  rerank    enabled=False endpoint=-
            credential_origin=local-key:legacy-file:.sglang_api_key pending_restart=False
            note=运行期未启用：未配置 CANONICAL_V2_RERANK_BASE_URL（configured_reranker() 返回 None，服务不会调用 rerank）；如需启用请在页面填写端点并重启服务
  embedding enabled=True  endpoint=http://100.64.0.27:18005/v1
            credential_origin=legacy-file:.sglang_api_key pending_restart=False
            note=运行期 base_url 由 release embedding bundle 冻结（http://100.64.0.27:18005/v1）；凭据来源 legacy-file:.sglang_api_key
  llm       enabled=True  endpoint=https://api.deepseek.com
            credential_origin=legacy-file:.deepseek_api_key pending_restart=False
            note=运行期使用 chat profile deepseekv4flash（CHAT_LLM_PROFILE）；base_url https://api.deepseek.com；凭据来源 legacy-file:.deepseek_api_key

=== connection test: bocha (one request; rate limit sleeps between) ===
  verdict : OK | called: True | latency_ms: 351 | http: 200
  detail  : HTTP 200
  runtime : enabled= True | endpoint= https://api.bochaai.com/v1/web-search | credential= legacy-file:.bocha_api_key
  rate    : remaining this minute = 5

=== connection test: serper (one request; rate limit sleeps between) ===
  verdict : OK | called: True | latency_ms: 2703 | http: 200
  detail  : HTTP 200
  runtime : enabled= True | endpoint= https://google.serper.dev/search | credential= legacy-file:.serper_api_key
  rate    : remaining this minute = 5

=== connection test: rerank (one request; rate limit sleeps between) ===
  verdict : FAIL | called: False | latency_ms: 0 | http: None
  detail  : 运行期未启用：未配置 CANONICAL_V2_RERANK_BASE_URL（configured_reranker() 返回 None，服务不会调用 rerank）；如需启用请在页面填写端点并重启服务
  runtime : enabled= False | endpoint= None | credential= local-key:legacy-file:.sglang_api_key
  rate    : remaining this minute = 4

=== connection test: embedding (one request; rate limit sleeps between) ===
  verdict : OK | called: True | latency_ms: 25 | http: 200
  detail  : HTTP 200
  runtime : enabled= True | endpoint= http://100.64.0.27:18005/v1 | credential= legacy-file:.sglang_api_key
  rate    : remaining this minute = 3

=== connection test: llm (one request; rate limit sleeps between) ===
  verdict : OK | called: True | latency_ms: 131 | http: 200
  detail  : HTTP 200
  runtime : enabled= True | endpoint= https://api.deepseek.com | credential= legacy-file:.deepseek_api_key
  rate    : remaining this minute = 2

=== leakage sweep (no credential may appear in the response or the log) ===
  /api/canonical-v2/admin/secrets: 1 credential-shaped hits
  /api/canonical-v2/admin/config: 0 credential-shaped hits
  /admin: 0 credential-shaped hits
  server log: 0 credential-shaped hits

real-endpoint calls: bocha 1, serper 1, embedding 1, llm 1, rerank 0 (reported as not enabled)
acceptance done.
```
