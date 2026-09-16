# D9: 教授主页周期维护 — 管线设计（2026-09-07）

## 目标
周期性重抓教授主页，发现新论文/新字段，以增量批次入包。

## 架构（复用现有机制，最简路径）

```
professor_seed 表（9 所高校）
  → 适配器抓花名册页（各校 HTML 格式不同）
  → 发现新/变更教授
  → 对每个教授：抓官方主页 + 个人主页
  → 提取新论文/新字段
  → 生成 JSONL 增量批次（s12e-professor-backfill 格式）
  → 调用 build-v2.sh 增量模式 → 新服务包
```

## 种子清单（从教授池反推，2026-09-07）

| 高校 | 教授数 | 花名册 URL（待验证） |
|---|---|---|
| 深圳大学 | 1,068 | https://www.szu.edu.cn/（院系页） |
| 南方科技大学 | 981 | https://faculty.sustech.edu.cn |
| 哈尔滨工业大学（深圳） | 724 | https://faculty.hitsz.edu.cn |
| 清华大学深圳国际研究生院 | 277 | https://www.sigs.tsinghua.edu.cn |
| 中山大学（深圳） | 189 | https://sz.sysu.edu.cn |
| 深圳技术大学 | 177 | https://www.sztu.edu.cn |
| 深圳理工大学 | 145 | 待确认 |
| 北京大学深圳研究生院 | 61 | https://pkusz.edu.cn |
| 香港中文大学（深圳） | 30 | https://www.cuhk.edu.cn/zh-hk |

## 关键设计决策

### 1. 增量批次格式
复用 `s12e-professor-backfill-v1` 的 JSONL 格式：
```json
{"professor_id": "...", "name": "...", "field": "...", "value": "...", "source_url": "...", "crawled_at": "..."}
```
这确保现有合并管线（`_merge_professor_backfill_rows`）无需修改。

### 2. 花名册适配器
每所高校一个适配器（解析 HTML 提取教师列表）。归档的深大适配器
（`archive/szu-seed5-quality-20260613`）可作为模板。

### 3. 周期与调度
- **频率**：月级（学术产出更新节奏）
- **触发**：cron 或手动 `bash scripts/crawl_professors.sh`
- **增量检测**：对比上次抓取快照，只处理新增/变更

### 4. 与构建管线集成
新论文 → `p4-paper-salvage` 格式的增量 JSONL → 添加为新 source batch →
`build-v2.sh` 增量模式（需要 manifest 更新）

## 实现步骤（优先级排序）

1. **种子表创建**（在 admin-console PG 中建表 + 插入 9 行）
2. **花名册适配器**（先做深大/南科大，复用归档代码）
3. **教授主页抓取器**（逐教授抓取，提取论文/字段变更）
4. **增量批次生成器**（diff + JSONL 输出）
5. **构建集成**（新 batch ID → manifest 更新 → 增量构建）

## 依赖
- 各校花名册页可访问（需网络验证）
- 教授主页格式稳定（或适配器足够健壮）
- 增量构建管线（build-v2.sh 增量模式）

## 风险
- 花名册页改版导致适配器失效 → 需要适配器健康检查
- 教授个人主页多样性（学术主页/Google Scholar/ResearchGate）→ 优先官方主页
- 反爬虫 → 控制频率 + User-Agent + 缓存
