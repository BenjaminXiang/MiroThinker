# B4 范围界定（只读，2026-09-11）——引用底线 + web 污染过滤

> 依据：explore agent-11 只读报告（本节所引工作区为 serving worktree）。B4 实施前需先裁定
> 三个口径（见 §5），并按 D0 模式做一次 9 轮逐段丢卡探针。

## 1. 引用装配链（file:line）

- 证据项 `EvidenceItem`（lane/source_nature/source_locator/claim_binding）由 read 层产出
  （web：`serving:1537-1613`；本地：`read:2267/3305/3902/7010/7077/7153`）。
- `Citation` 契约仅带 evidence_id/source_nature/source_locator/observed_at/web_snapshot_id/
  retrieved_at（**无 title/snippet**）：`answer:317-323`；构造函数 `answer:797-806`。
- answer 层只对"被准入 claim 引用到的证据"发引用（`answer:2084-2092` → `TurnResult`）。
- 卡片层（唯一落点，admin-console）：先校验 `evidence_id ⊆ read retained`
  （`chat:2149-2155`，**不能凭空造引用**）；`_public_citations` `chat:2224-2299`：
  - B1 本地卡（worktree 独有；主仓 HEAD 无此分支，diff 24 行）：`chat:2272-2285` —
    lane==relationship 且无 URL → `local-source-<sha(handle_id)[:16]>`（url=None）；
  - 有 URL → `official-source-<sha(url)[:16]>`（`chat:2287-2298`）。

## 2. 引用底线挂钩点

- **Hook A（推荐，最小面）**：`chat:2272` 的 `lane != "relationship"` 判定改为
  "任意本地证据（source_nature ∉ {current_web, supplemental_web}）且句柄属公开域"
  → 发 URL-less 卡。不碰检索/提示词；上限受 retained 校验约束（不会造引用）。
- **Hook B（answer 层）**：`answer:2084-2092` 把锚点自身本地证据并入 retained——影响面
  更大；纯 web 回答**不该**走此路（诚实语义）。

## 3. web 污染过滤

- 现役 `CITATION_FORBIDDEN_PATTERNS`（`anchors.py:205-217`）**只被测试 harness 消费**，
  生产零消费者；且卡片契约无 title/snippet、canonical 通路从不产生 `type=="web"` 卡
  → **该断言近乎空转**（全部存档 citations_web==0 已核）。
- 生产可复用载体：`claim_text_is_raw_dump` + `_DETERMINISTIC_RAW_DUMP_MARKERS`
  （`answer:1314-1336`，消费点 `serving:5902-5907`、`answer:1363`）；其模板集与 GAP-08
  的 404/JS 模式不同，需扩表。
- 真实污染入口：provider 原始 snippet（含 JS 片段）→ `_enrich_with_page_text`
  （`serving:1413-1455`，抓取正文直替 snippet，无逐行过滤）→ `_semantic_text`
  （`serving:4152-4159`）→ web 句柄 label（原始标题）。
- 应拦层：①抓取/抽取层（`page_fetch.py` 已有 `_DROP_TAGS`，div 形态漏网）；
  ②snippet→claim 层（`serving:5906` 钩子，扩模板集）；③URL/硬错误页候选阶段丢/降权。
  卡片层拦不了（契约缺字段）。

## 4. 风险面

- 下限不得造假：无本地依据轮走诚实降级（`answer:1305-1307` + 缺口句），不发本地卡。
- **口径风险**：harness 把一切 `type != "web"` 记 local，含 official-source 卡
  → 纯 web 轮也能满足 local_citations ≥1；建议按 `local-source-` 前缀判定或显式定义。
- `r"404"` 误伤重（数字/日期/slug）；登录模式须保持词组级（勿加裸"登录"）。
- 过滤只作用于引用/claim 通道，**不得作用于答案正文**（链接类问题需保留 URL）。

## 5. B4 待裁口径（实施前锁死）

1. **GAP-08 判定口径**：扩展 `ChatCitation` 契约（补 title/snippet 或 web 类卡）vs
   把断言改挂答案文本/证据 payload——后者零契约变更但判定面变化。
2. **本地卡口径**：Hook A 的"本地证据"边界 + harness 的 local 判定改为
   `local-source-` 前缀。
3. **第一步**：按 D0 模式做 9 轮逐段丢卡探针（区分 answer 层 citations 空 vs adapter
   层丢卡），再落 Hook A；g1-t1/g17-t2 需 B5 后复跑补测。

## 6. 验收对齐（9 锚定轮，最近实测）

- 已 PASS：g17-t1（16 本地卡）。只差引用层：g17-t2（精确道本地证据无 URL 不发卡 → Hook A 可闭）。
- 双红（内容+引用）：g1-t2、g4-t1、g4-t2、g6-t1、g7-t1。部分：g8-t1（有 1 卡，差 completeness）。
- 需复跑补测：g1-t1、g17-t2（B5 后无覆盖）。
