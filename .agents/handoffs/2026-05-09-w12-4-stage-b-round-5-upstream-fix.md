---
title: "Codex handoff Round 5 — W12-4 Stage B: SIT/SZTU 上游 fix（section detection + vocab）"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md  # spec §0/§1/§11 已被本 handoff §0 / §6 / §11 替换覆盖
prior_handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes-path-a.md
prior_reviews:
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop1.md  # DSN
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop2.md  # subagent shell proxy
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop3.md  # codex sandbox network
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop4-diagnosis-success.md  # ←  authorizes this round
diagnosis_input: logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md
mode: claude-prepares-data → codex-implements-upstream-fix → claude-validates
estimated_effort: 0.5 day (codex side)
---

# Codex handoff Round 5 — W12-4 Stage B 上游 fix

> **核心变化**：Round 4 的 diagnosis 推翻了 spec §0 的假设。9/10 SIT/SZTU 样本是 **section detection 失败**，不是 content extraction 失败。Round 5 **授权扩展 `_find_publications_sections` 和 `_PUBLICATIONS_HEADING_KEYWORDS`**——这是前几轮明令禁止的，但现在有 diagnosis 数据支持。
>
> Codex round 4 的 stop 是高质量的——这就是 spec §11 stop condition 设计要的反馈循环。

## 0. Goal（替换原 spec §1 表格 + Round 4 baseline 修订）

让 SIT (suat-sz.edu.cn) + SZTU (sztu.edu.cn) 的 CMS 模板能正确识别 publications section。具体：

```
原 spec §0 假设：section ✓ extraction ✗
实测推翻：     section ✗ in 9/10 SIT/SZTU samples（diagnosis.md per-sample 表）

修订 acceptance：
- 7 个 fixable SIT/SZTU 样本：≥ 5 papers
- 1 个 SZTU hsee 样本（0352）：≥ 4 papers（HTML 只有 4 篇）
- 1 个 SIT swyxgcxy 样本（2E2F）：regression-guard，保持 5 papers
- 5 个 working 样本（Tsinghua × 2、SYSU bme/ise/eco-working × 3）：保持 papers > 0
- 排除 2 个 unsalvageable：
    PROF-0AD6B7854B29（SZTU sgim，HTML 只有 prose 描述）
    PROF-056CEBB2980A（SZTU bs，HTML 只有 profile metadata）

总：≥ 12/15 fixable samples 有 papers > 0；其中 ≥ 7 个达到 ≥ 5 papers
```

## 1. 必读源文档（按顺序）

1. **`logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md`** — Round 4 Codex 写的 per-sample DOM 证据（**这是改 parser 的圣经**）
2. **`.agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop4-diagnosis-success.md`** — Claude 对 Round 4 的 review，包含 V1–V6 失败分类
3. `logs/.../baseline.md` — 17 真实样本 + 修订后的 acceptance（§0 已 inline）
4. `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py` — 当前 parser
5. `apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py` — vocab（这次允许扩展）

## 2. 失败模式分类（diagnosis 总结）

| 类型 | 触发条件 | 修复路径 | 样本 |
|---|---|---|---|
| **V1 vocab gap** | h*tag 文本不在 vocab 内（如 `学术成果`） | 扩 vocab + 嵌套深查找 | PROF-019A |
| **V2 styled paragraph heading** | `<p><strong>vocab</strong></p>` 命中 vocab 但容器是 p/strong | 扩展 section detection 识别 styled paragraph | PROF-0210, 02D4, 02DD, 0AD6（partial） |
| **V3 CMS title block** | `<div class="tit">vocab</div>` CMS 模板 | 扩展 section detection 识别 CMS title divs | PROF-00FD, 162E, 0352（partial） |
| **V4 trailing punctuation** | vocab 末尾全角冒号 `：` 或半角 `:` | 容忍末尾标点 | 多个 |
| **V5 unsalvageable** | HTML 中无 publications | 排除 | PROF-0AD6, 056C |
| **V6 only 4 papers** | HTML 实际只 4 篇 | acceptance 接受 ≥4 | PROF-0352 |

## 3. 实施流程

```
Step 1  研读 diagnosis.md + baseline.md（5 min）
Step 2  扩 _PUBLICATIONS_HEADING_KEYWORDS：
        + "学术成果"        # SIT csce h3 文本
        + "代表性文章"      # SIT lhs/synbio div.tit
        + "代表文章"        # SZTU hsee p>strong
        # 注意：existing "代表性论文" / "论文" 等保留不动
        # 注意：vocab 扩展自动应用到所有 archetype，但因 V5/V6 不增加 false positive 风险（是否 HTML 真有 publications 是另一层）
Step 3  容忍 trailing punctuation：
        - heading regex 已经 \b 匹配；改为允许末尾 [：:、] 全角/半角标点
        - 影响最小的实现：在 `_PUBLICATIONS_HEADING_RE` 末尾加 `[:：]?$`，或更通用的预处理 strip
Step 4  扩展 _find_publications_sections 识别非 h* 容器：
        - 现有逻辑：h1-h6 / class/id 含 vocab keyword
        - 新增：`<p>` 或 `<div>` 仅当其 **strip 后纯文本** 在 vocab 集合中（即作为「standalone heading paragraph」）
        - 边界条件：必须满足以下任一才算 heading（避免 false positive）：
          (a) 元素 `<strong>` / `<b>` / `<h*>` 或样式 strong（避免抓正文段落）
          (b) 元素 class 含 'tit'/'title' 关键字
          (c) 整段 text 长度 ≤ 30 字符且整段命中 vocab（即不是嵌入在长句中）
        - 新检测的 section 的 boundary 用：从该 heading 元素往后取 sibling 直到下一个 heading-like 元素或父容器结束
Step 5  实现：
        - 修改 homepage_publications.py 的 _find_publications_sections（保持入口签名 + 现有 h*/class/id 检测路径）
        - 修改 homepage_publication_headings.py（加 vocab）
        - 不要重写策略链；现有 5 个 _extract_from_* 仍是 content 处理
Step 6  写测试：
        - tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
        - 至少 4 个 archetype × 1 fixture 测「找到 section + 提取 ≥5 papers」
        - 加 trailing punctuation 单测（用 `代表性论文：` 触发）
        - 加 V2/V3 的 styled paragraph / div.tit 微型 fixture 测试
        - 加 regression-guard 测：用 working sample（Tsinghua × 1，SYSU × 1）确认仍 papers > 0
Step 7  Sandbox-friendly 验证：
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
        cd apps/miroflow-agent
        uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v
        uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov
Step 8  17-sample sweep（pure file IO）：
        见 §8 verification command
Step 9  Commit (NO push) + 回报
```

## 4. 修改文件清单

```
修改:
  apps/miroflow-agent/src/data_agents/professor/homepage_publications.py
    - 仅 _find_publications_sections 内部扩展（识别非 h* 容器）
    - 保持公共 API 不变

  apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py
    - 加 3 个 vocab 词："学术成果"、"代表性文章"、"代表文章"
    - 调整正则容忍 trailing punctuation（最小改动）

新增:
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py

按需:
  logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis-round-5.md
    （round 5 加补的发现，可选）

不要碰:
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py（277 行 drift）
  其它 51 个 drift 文件
  extract_publications_from_html 入口
  HomepagePublication dataclass
  现有 5 个 _extract_from_* 策略（保持原样）
```

## 5. Do-not（强制约束）

- ❌ 不要触碰 `test_homepage_publications.py`（drift）
- ❌ 不要改 `extract_publications_from_html` 入口签名
- ❌ 不要改 `HomepagePublication` dataclass
- ❌ 不要重写或重命名 5 个 `_extract_from_*` 策略
- ❌ 不要做 localhost 网络访问（Path A 模式：claude 已 prefetch HTML）
- ❌ 不要 fetch 任何 homepage URL
- ❌ 不要引入 LLM / Selenium / Playwright / network-fetching 代码
- ❌ 不要动 Alembic / DB schema / classifier / chat / retrieval / admin-console
- ❌ 不要 amend 已发布的 commit
- ❌ 不要使用 `--no-verify`
- ❌ 不要 push

### 重要：vocab 扩展的边界

**只加 3 个词**：`学术成果`、`代表性文章`、`代表文章`。**不要顺手加** `研究成果`、`科研成果`、`发表文章`、`期刊文章` 这种相邻词——会污染 working sample 的 false positive 风险。如有强诉求，单独 stop 报告，不顺手做。

### 重要：non-h* container detection 的边界

只在以下 **任一** 条件满足时识别 `<p>` / `<div>`：
- (a) 元素是 `<strong>` / `<b>` / 直接子元素是 strong/b
- (b) 元素 class 包含 `tit` 或 `title` 关键字（如 `class="tit"`、`class="g-titl1"`）
- (c) 元素 text strip 后 ≤ 30 字符且整段命中 vocab

**不要**用通用规则「任何 vocab 命中的容器都算 heading」——会在 working sample 上把段落正文错认为 heading。

## 6. Stop conditions（替换原 spec §11）

原 spec §11 把「root cause is in `_find_publications_sections` or heading vocabulary」当作 stop condition。Round 5 **取消这条**——本轮就是要修这一层。

仍然是 stop conditions 的：

- §V5 之外又发现新的 unsalvageable 样本（>3 个 fixable 样本无 publication 数据）
- 扩展 section detection 后任何 working sample 退化（papers 减少）→ 这属于 false positive 控制不住
- 4 archetype 都需要 JS 渲染（lxml 拿到的是壳子）

## 7. 必报项（按本 §6 替换 prior handoff §6）

```markdown
# Codex Stage B Round 5 回报

## A. Vocab 扩展决策
- 加了哪 3 个词？是否额外加了？为什么？
- 是否调整了 trailing punctuation 处理？怎么改的？

## B. Section detection 扩展决策
- 新增的非 h* 容器识别规则（写出最终的 if 条件链）
- 为什么这种规则不会产生 false positive on working samples
- 在 17-sample sweep 上的 false positive 计数（应为 0）

## C. 修改文件清单 + LOC

## D. 17-sample before/after 表

| prof_id | archetype | before | after | 备注 |
|---|---|---:|---:|---|
| ... | ... | ... | ... | regression-guard / fix-target / unsalvageable |

## E. 测试结果
- 新单测 PASS / FAIL
- 既有 publications 单测 PASS / FAIL（不退化）
- 命令 + 输出片段 (< 30 行)

## F. Acceptance 达成情况（按 §0 修订表）
- 7 个 fixable SIT/SZTU 是否 ≥ 5 papers？x/7
- 1 个 hsee 是否 ≥ 4 papers？
- 5 个 regression-guard 是否 papers > 0？
- 总 papers > 0 的 ratio: x/15

## G. 风险 / 假设破坏
- §0 修订后假设是否成立？
- 是否触发 §6 stop condition？

## H. Sandbox / 环境
- localhost 调用次数：应为 0
- 触碰了 §5 do-not？停了吗？

## I. R3 重新评估（PRD §M2.1 R3）
- 一句话结论
```

## 8. Verification commands

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy && \
  cd /home/longxiang/MiroThinker/apps/miroflow-agent && \
  uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v && \
  uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov && \
  echo "--- 17-sample sweep ---" && \
  uv run python <<'PY'
from pathlib import Path
from src.data_agents.professor.homepage_publications import extract_publications_from_html
LOGS = Path("/home/longxiang/MiroThinker/logs/data_agents/paper/homepage_ingest_runs/2026-05-09")
EXPECT = {
    # working samples (regression-guard) — must stay > 0
    "PROF-00248146798C": ("Tsinghua SIGS", "≥1 (was 55)"),
    "PROF-008A36B6E702": ("Tsinghua SIGS", "≥1 (was 6)"),
    "PROF-0137B5E393A3": ("SYSU bme",      "≥1 (was 118)"),
    "PROF-02C529F2E940": ("SYSU ise",      "≥1 (was 10)"),
    "PROF-027B70B3BC62": ("SYSU eco-w",    "≥1 (was 20)"),
    "PROF-2E2F7D86A756": ("SIT swyxgcxy",  "≥5 (was 5, regression-guard)"),
    # nice-to-have (1 SYSU eco) - flexible
    "PROF-004A95AABE6C": ("SYSU eco-bad",  "any"),
    # FIX TARGETS — must reach ≥5
    "PROF-019A6958E272": ("SIT csce",      "≥5"),
    "PROF-0210FCABC6B8": ("SIT csce",      "≥5"),
    "PROF-00FD387949E7": ("SIT lhs",       "≥5"),
    "PROF-162E1960D66E": ("SIT synbio",    "≥5"),
    "PROF-02D420B17263": ("SZTU sgim",     "≥5"),
    "PROF-02DD067A3E0D": ("SZTU cep",      "≥5"),
    # ≥4 (HTML only has 4)
    "PROF-0352087FC634": ("SZTU hsee",     "≥4"),
    # unsalvageable — exclude
    "PROF-0AD6B7854B29": ("SZTU sgim NoData", "—"),
    "PROF-056CEBB2980A": ("SZTU bs NoData",   "—"),
    # not in baseline
    "PROF-048E64B1468A": ("SIT lhs dept page", "—"),
}
for pid, (label, target) in EXPECT.items():
    p = LOGS / f"{pid}.html"
    if not p.exists():
        print(f"{pid:18}  {label:25}  target={target:18}  ✗ HTML missing")
        continue
    html = p.read_text(encoding="utf-8")
    pubs = extract_publications_from_html(html, page_url=f"file://{p}")
    print(f"{pid:18}  {label:25}  target={target:18}  papers={len(pubs)}")
PY
```

## 9. 工作树状态

- branch: `main`
- `homepage_publications.py`: 无 drift（已验证 2026-05-09）
- `homepage_publication_headings.py`: 1 line drift（5/2 加 `代表性论文` 那次）—  无影响，本次只是再加 3 词
- `test_homepage_publications.py`: **+277 lines drift（不要碰）**
- 51 个 drift 文件分布广泛 — 严格只动 §4 列出的文件

## 10. 完工后

1. 不要 push
2. 把回报粘回，由 claude 写 final review (`stage-b-final.md`)
3. claude 跑 17-sample sweep 验证 + 跑端到端 dry-run 确认全链路
