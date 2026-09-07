# D8: 论文归属验证管线 — 设计（2026-09-08）

## 问题
从教授主页抓取的论文中，可能混入非该教授的作品（爬虫噪声）。
用户要求：这部分可以删除，但**必须通过 web search 等方式验证**。

## 三类论文人群

| 人群 | 特征 | 处理 |
|---|---|---|
| ✅ 正确归属 | 主页列出 + 元数据匹配 | 保留 |
| ⚠️ 疑似误挂 | 主页列出但元数据不匹配 | **web search 验证后决定** |
| ❌ 确认误挂 | web search 证实非该教授作品 | **删除（有证据）** |

## 疑似信号（触发验证的条件）

1. **作者名不匹配**：论文 DOI/arXiv 元数据中的作者列表不包含该教授名
2. **机构不匹配**：论文作者机构与教授所在机构不一致
3. **领域偏离**：论文研究领域与教授研究方向完全无交集
4. **同名歧义**：教授姓名是常见中文名（如"李明"、"王伟"）
5. **主页上下文弱**：论文出现在列表页而非个人发表页

## 验证流程（web search）

```
疑似论文 → 构造验证查询
  → "论文标题" + "教授名"           → 搜索结果中有教授机构页面？
  → "论文标题" + "DOI" + "author"    → 元数据中作者列表？
  → "论文标题" site:教授机构域名      → 机构官方页面确认？
→ 三条通道投票：
   2/3 确认 → 保留
   2/3 否定 → 删除（记录证据）
   不确定   → 保留 + 标记 needs_review
```

## 实现架构（复用现有 web 通道）

```python
class PaperAttributionVerifier:
    """Verify paper-professor attribution via web search."""

    def identify_suspicious(self, professor, paper) -> bool:
        """Check suspicion signals (metadata match, domain overlap)."""
        ...

    def verify(self, professor, paper) -> Verdict:
        """Web search verification (3-channel voting)."""
        # Reuse the existing Bocha/Serper dual web lane
        # Reuse the web snapshot machinery for evidence capture
        ...

    def execute(self, paper_link) -> Action:
        """Keep / Remove / Flag for review."""
        ...
```

## 数据流

```
professor_paper_links 表
  → identify_suspicious() → 疑似列表
  → verify() (web search) → 验证结果 + 证据
  → execute() → 保留 / 删除 / 标记
  → 输出：verified_attribution_report.json
```

## 与现有系统的集成

| 组件 | 复用方式 |
|---|---|
| Web 搜索 | Bocha/Serper 双通道（`_DualWebLaneAdapter`） |
| 网页快照 | 现有 web snapshot 机制（证据保全） |
| DOI 元数据 | CrossRef API（`doi.org/handle`）或 OpenAlex |
| 决策记录 | 复用 `PolicyDecision` 结构（审计链） |

## 关键设计决策

1. **验证而非启发式删除**：绝不因信号 alone 删除论文——必须有 web search 证据
2. **保守默认**：不确定时保留（宁可多留不错删）
3. **证据保全**：每次验证的搜索结果、网页快照、决策理由都存档
4. **增量执行**：不一次性验证全部 18,655 条链接——按怀疑度排序，逐批处理

## 工作量估算

- 验证器核心：~200 行（信号检测 + 搜索 + 投票）
- 证据存储：~100 行（快照 + 决策记录）
- 批处理调度：~50 行
- **总计：~350 行 Python + 测试**

## 前置条件

- Web search API 可用（Bocha/Serper key 已在 .env）
- CrossRef/OpenAlex API 可访问（DOI 元数据）
- 教授-论文链接数据（`prof_paper_link` 表，18,655 条）
