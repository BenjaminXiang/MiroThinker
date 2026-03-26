# Issue 13 实现说明：Skeleton 导入与导入报告

本文档说明 `Issue #13` 已完成的内容，包括：

1. 实现了什么
2. 如何使用
3. 如何验证

核心代码位于：

- `src/company_data_agent/importer/skeleton_import.py`
- `tests/test_skeleton_import.py`

---

## 一、这次实现了什么

这次实现把前面三层能力真正接起来了：

- `#11` 的主数据表解析结果
- `#12` 的 identity 规则
- `#9` 的企业记录模型

最终产出的是：

- dedup 后的 skeleton company records
- 稳定的导入报告

### 1. 把解析行变成 skeleton records

`SkeletonImporter` 会把 `MasterListParseResult.rows` 转成 `PartialCompanyRecord`，并为每家公司补齐：

- `id`
- `credit_code`
- `name`
- `registered_address`
- `industry`
- `sources`
- `raw_data_path`

这意味着从 `#13` 开始，主数据表不再只是“解析出来的行”，而是已经进入公司记录体系。

### 2. 按规范化后的 `credit_code` 去重

导入阶段的 distinct key 是规范化后的 `credit_code`。

如果同一批输入里出现同一家公司多行，当前实现会：

- 聚合同一个 identity
- 按稳定规则合并字段
- 只产出一条 skeleton record

### 3. 支持和已有记录做 deterministic merge

如果导入时传入 `existing_records`，当前实现会：

- 以已有记录为 baseline
- 用主数据表的非空基础字段覆盖 `name` / `registered_address` / `industry`
- 保留已有记录中不属于主数据表的其他字段
- 合并 `sources`

这样后续增量导入不会把已有 skeleton / enrichment 信息误清空。

### 4. 导入报告不再是口头描述，而是代码产物

当前会生成：

- `created_count`
- `updated_count`
- `skipped_count`
- `failed_count`
- `actions`
- `failures`

也就是说 docs / PRD 里提到的：

```text
新增 N 条、更新 N 条、失败 N 条
```

现在已经有了实际实现。

### 5. 行级错误继续保留，不中断成功导入

解析阶段遗留下来的 `MasterListParseError` 会进入最终导入报告。

另外，如果某一行在导入阶段才暴露出 identity 问题，比如：

- `credit_code` 非法

也会被记录为失败，而不是让整批导入中止。

---

## 二、怎么使用

### 1. 基础用法

```python
from company_data_agent.config import ArtifactLayout
from company_data_agent.importer import SkeletonImporter
from company_data_agent.ingest import MasterListParser

parser = MasterListParser()
parse_result = parser.parse("data/shenzhen_company_list.xlsx")

layout = ArtifactLayout.model_validate({"root_dir": "artifacts/company-data-agent"})

result = SkeletonImporter().import_rows(parse_result, layout)
```

### 2. 获取 skeleton records

```python
for record in result.records:
    print(record.id, record.name, record.credit_code)
```

### 3. 获取导入报告

```python
report = result.report

print(report.created_count)
print(report.updated_count)
print(report.skipped_count)
print(report.failed_count)
```

### 4. 传入已有记录做 merge

```python
result = SkeletonImporter().import_rows(
    parse_result,
    layout,
    existing_records=existing_records,
)
```

这适用于：

- 月度重跑
- 增量导入
- 已有 skeleton 记录更新

---

## 三、合并规则

当前实现的 merge 规则是稳定且显式的：

### 1. identity

- 统一使用 `#12` 的 `normalize_credit_code()`
- `id` 使用 `generate_company_id()`

### 2. 基础字段覆盖

主数据表当前负责的基础字段是：

- `name`
- `registered_address`
- `industry`

只要新输入中该字段非空，且与 baseline 不同，就会覆盖。

### 3. provenance

- `sources` 会确保包含 `master_list`
- `raw_data_path` 使用 deterministic path

### 4. 非主表字段保留

例如已有记录里的：

- `website`
- 其他后续 enrichment 字段

不会被 skeleton import 清空。

---

## 四、怎么验证

### 1. 自动化测试

当前新增 `test_skeleton_import.py`，覆盖：

- 新记录创建
- 批内重复 `credit_code` 去重与合并
- 既有记录更新
- 既有记录无变化时的 skip
- 失败行计数
- 重跑结果稳定
- 非法 `credit_code` 变成 failure

运行方式：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

### 2. 当前验证结果

当前 package 全量结果应为：

```text
38 passed
```

包含：

- `#9` record model
- `#10` config contract
- `#11` master-list parser
- `#12` company identity
- `#13` skeleton import

---

## 五、对后续任务的直接价值

`#13` 完成后，后续能力已经有真实输入：

- `#14/#15`
  可以直接基于 skeleton records 做 Qimingpian 增强

- `#17/#18/#19`
  可以围绕已确定的 base company records 做 source discovery、抽取和 summary

- `#23`
  可以直接消费导入报告做 run reporting

换句话说，从这一步开始，企业主数据表已经不只是被“读进来”，而是已经进入了可追踪、可报告、可继续增强的 skeleton 数据形态。
