# C1 别名闭包（alias closure）实施规划 — 2026-09-13

> change-id: `close-workbook-gaps`（C1 "alias closure" 切片）
> 证据基础：`alias-projection-gap-20260913.md`（包侧 4.8% vs 源侧 99.8%）
> 执行 worktree：`.worktrees/data-rebuild`（分支 `data/p4-serving-pack-rebuild`，
> run14 包的实际构建线）；serving worktree 只做验收探针，不改构建码。

## 0. 定性回顾（为什么是构建侧）

- 检索侧别名通道（verbatim alias / normalized_name / 短名压实 + 唯一性守卫
  + 扇出上限 `_ENTITY_LINK_MAX_FORM_FANOUT = 4`）**已存在且 fail-safe**：
  歧义命中时不绑定、回退正常车道。
- 缺口在数据：包内 342/7,089（4.8%）公司有别名；`ByteDance Ltd.` 的
  `aliases=[]`，而 p4 源数据它的 `project_name = "字节跳动"`。
- 构建链无任何代码读取 `project_name`。查询侧不做模糊联想（补丁）；本地
  确实没有的实体继续走 web 补全。

## 1. 数据链路现状（已实测，行号 = data-rebuild 副本）

```text
retained released objects (s12 线)
  → selected_by_object[object_id] = selected        # :5543
p4 batch rows (p4-company-full-v1.jsonl, 6,514 行)
  → _p4_company_record(payload)                     # :4265（builder）
      · 读 company_name/industry/business/… ；
      · core = {name, normalized_name}，不读 project_name  ← 丢点
  → _merge_p4_created_rows                          # :4667（5572 处调用）
      · 按 name_key 命中 overlap["company"] → _p4_company_field_merge  # :4170
        （fill-empty；_P4_COMPANY_FILL_FIELDS=team/product/website/address）
      · 未命中 → 新建（core_facts 路径）
投影白名单已允许 "core_facts.aliases"              # :815
projection 读 core_facts.aliases（存在才投影）      # :2712-2720
字段合并写入 selected 的字段会进最终投影（同字证据：run14 包内
ByteDance 的 product_description = p4 product_summary，tech_tags = p4 business）
```

**实测**：p4 全部 6,514 家公司在包内按名存在（无一漏）；其中 6,504 行有可用
`project_name`（≠ company_name），10 行同名无需别名；全部走**字段合并**路径
（不是新建路径）——所以修复必须落在 `_p4_company_field_merge`，只在
`_p4_company_record` 里改会漏掉全部存量公司。

## 2. 变更点（代码级）

### A1 `_p4_company_record`（:4265）

- 读 `project_name = _p4_optional_string(payload.get("project_name"))`；
- 过滤：为空 / == `name`（casefold 比较）/ 长度 < 2 → 不产出；
- 产出：`core["aliases"] = [project_name]`（新建路径完整性）与
  `selected["aliases"] = [project_name]`（字段合并路径的 fill 源）。

### A2 `_p4_company_field_merge`（:4170）— 别名并集

- `assign()` 是"空则填"的**标量**语义，别名是列表，需要独立分支：
  - `fill.get("aliases")` 非空列表时：existing 别名 ∪ fill 别名，
    规范化（strip）、casefold 去重、剔除 == name/normalized_name、长度 ≥2；
  - 合并后追加字段断言 `assertion:{object_id}:p4fill:aliases`
    （与其它 p4fill 字段同构，进 decision/lineage）；
  - `filled` 计数与统计保持原口径（并集发生即计 1）。
- 不加入 `_P4_COMPANY_FILL_FIELDS`（保持常量语义纯净）。

### A3 规范化/过滤（小 helper，或内联）

- 仅做：strip / 长度≥2 / casefold 比较去重与自名剔除。
- **不做**泛词词表过滤（实测 6,504 个 project_name 中粗筛只命中 1 条且多为
  假阳性，如"普智城市"是真实品牌）；真正的风险形态（歧义扇出）由 serving
  既有守卫兜底。

### A4 冲突与报告（不阻断）

- 实测全量仅 **9 个形态被 2 家公司共享**（如 乐聚机器人 → 乐聚(深圳)机器人 +
  乐聚智能——真实品牌家族；另有少量噪声如 优脉英才/安特保）。
- 9 ≤ serving 扇出上限 4，**保留并报告**；由 serving 唯一性守卫保证歧义不误绑。

## 3. 测试（TDD，RED 先行）

- `test_p4_company_field_merge.py`（已有 `_merge` 助手）新增：
  1. 合并写入：existing 无别名 + fill 带别名 → union 出现、断言记录；
  2. 并集去重：existing 已有别名与 fill 重复（含大小写差异）→ 只保留一份；
  3. 自名剔除：alias == name → 不写入；
  4. 非列表 fill（None/str）→ 不崩、不写。
- `test_knowledge_build_p4_full_column.py` 新增：
  5. `_p4_company_record` 带 `project_name` → core/selected 同时带 aliases；
  6. 同名 project_name → core/selected 均无 aliases；
  7. 无 project_name（缺字段）→ 无 aliases（不产生空列表噪声）。

## 4. 干跑报表（重建前证据）

`.agents/runs/full-column-serving-pack-rebuild/alias_dry_run.py`：

- 直接复用真实构建函数（import 同一模块），逐行过 `_p4_company_record` +
  对 stub existing 跑 `_p4_company_field_merge`；
- 产出 JSON/MD：新增别名数、覆盖公司数、自名剔除数、去重数、冲突形态表、
  抽样 20 条（品牌 ← 公司名）；
- 预期（上界）：≈6,504 家 × 1 个别名；覆盖从 342 家（4.8%）升到
  ≈6,800 家（≥96%，以重建实测为准）。

## 5. 重建与验收（boring 全量重建路线）

```text
1) s12a 候选重建（data-rebuild worktree）→ 新的 complete-candidate 信封（run15）
2) build_p4_serving_pack.sh（builder = s11 worktree s12c/build_serving_pack.py）
   → 新 pack 目录（fresh 校验保留）
3) post_build_verify.py + seal → serving-pack-run15-sealed
4) 切换 18188 systemd 的 --serving-pack 指针 → 重启（Milvus 装载 ~12 min）
5) 探针：
   a. 「字节跳动」→ 命中 ByteDance Ltd.（exact/alias 通道）；
   b. 「优必选」回归不变；重名冲突形态（乐聚机器人）不误绑、走歧义回退；
   c. replay 门 7 会话；g2/g5 测试集抽查；泛化 r5 抽查；
   d. 别名扇出守卫单测不变。
6) 回退：指针切回 serving-pack-run14-sealed + 重启，旧包不删。
```

## 6. 风险与对策

| 风险 | 评估 | 对策 |
|---|---|---|
| 身份键副作用：p4 别名进入 `existing_name_keys`（backfill 身份查找，:3660）在 p4 合并后运行 | 低（backfill 仅 700 条，用全名匹配） | 干跑报表附"经 p4 别名新增匹配的 backfill 记录数"；异常则把别名键从该查找中剔除 |
| 模糊品牌误绑 | 低（查询侧命中需文本含别名 + 唯一性判定） | 保留 serving 扇出守卫；冲突形态探针实测 |
| 包哈希/发布绑定变化 | 流程已存在 | 新 release 标记 + 旧 sealed 包保留回退 |
| 575 家不在 p4 的包内公司仍无别名 | 部分被 backfill（342 家中含）覆盖 | 重建后按实测剩余量决定是否追加补充批（alias-4，可选） |

## 7. 切片排期

- **本切片（alias-1+2，已完成部分见 change-log）**：A1/A2/A3 代码 + 7 条单测 +
  干跑报表。
- **下一切片（alias-3）**：候选重建 → 打包 → 切换 → 探针验收（按 §5 执行）。
- **可选（alias-4）**：残余补充数据批（模式同 `company_backfill.jsonl` 准入），
  仅在 alias-3 实测残余覆盖率不达标时启动。

## 执行记录 — batch1a 已完成（2026-09-13）

- **代码（data-rebuild 副本，未提交）**：
  - `_p4_company_record`：读 `project_name` → `core_facts.aliases` +
    `selected["aliases"]`（长度≥2、自名剔除）；
  - `_p4_company_field_merge`：列表别名并集（casefold 去重、自名/短形剔除、
    写 `p4fill:aliases` 断言、计 filled）；新增小助手 `_company_alias_key`。
- **测试**：`test_p4_company_field_merge.py` +4、
  `test_knowledge_build_p4_full_column.py` +3；RED 3 失败 → GREEN
  20/20（两文件）；定向 `-k company` 12 通过 + 1 环境类红
  （`test_real_boundary_rejects_nonfresh_database_before_source_read`：
  DB migration revision 信息不匹配，发生在任何源读取之前，与本次改动正交）。
- **干跑实测**（`alias_dry_run.py`，复用真实构建函数，全量 6,514 行 ×
  现包 7,089 家并集模拟，只读）：
  - `rows_with_alias_candidate = 6,504`、`rows_invalid = 0`、
    `rows_pack_miss = 0`；
  - `union_gained_companies = 6,504` →
    覆盖 **342 → 6,846（4.8% → 96.6%）**；
  - 冲突形态 **9 个**（各 2 家）≤ serving 扇出上限 4 → 保留 + 报表；
  - backfill 身份匹配副作用：**0 条**（对 700 条 backfill 记录逐一验证）；
  - 抽样：ByteDance Ltd.→字节跳动、FMC→FMC汽车、TCL华星光电→TCL华星。
  - 产物：`alias-dry-run-20260913.json`（同目录）。
- **遗留**：batch1b 重建与验收（§5 流程）未启动；环境类红与 F402 预存项
  已在 verification-contract 登记。
