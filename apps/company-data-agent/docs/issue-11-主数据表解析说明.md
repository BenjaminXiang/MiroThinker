# Issue 11 实现说明：深圳企业主数据表解析

本文档说明 `Issue #11` 的真实实现内容，包括：

1. 实现了什么
2. 如何使用
3. 如何验证

核心代码位于：

- `src/company_data_agent/ingest/master_list_parser.py`
- `tests/test_master_list_parser.py`

---

## 一、这次实现了什么

这次实现的是企业数据采集链路中的第一块真实业务能力：

**把深圳企业主数据表的 CSV / Excel 输入解析成可复用的标准化行流。**

这不是文档层面的约定，而是已经可以直接调用的 parser。

### 1. 支持 CSV 和 Excel 两种输入

当前 `MasterListParser` 支持：

- `.csv`
- `.xlsx`
- `.xlsm`

这意味着后续不管企业主表来自 CSV 还是 Excel，解析入口都一致。

### 2. 产出标准化行对象，而不是原始二维表

解析结果不是裸 `dict` 列表，而是结构化输出：

- `ParsedMasterListRow`
- `MasterListParseError`
- `MasterListParseResult`

其中：

- `rows` 保存成功解析的行
- `errors` 保存逐行失败信息

这样后续 `#12/#13` 可以直接消费 `rows` 做规范化、去重和导入报告，而不需要重新读文件。

### 3. 做了 header alias 映射

当前 parser 已支持把常见中英文表头映射成统一字段：

- `企业名称` / `公司名称` / `name` / `company_name` -> `name`
- `统一社会信用代码` / `信用代码` / `credit_code` -> `credit_code`
- `注册地址` / `地址` / `registered_address` -> `registered_address`
- `行业分类` / `行业` / `industry` -> `industry`

这一步很关键，因为实际输入文件的列名不一定完全统一。如果不先做 alias 归一，后续导入阶段会被各种列名分叉拖垮。

### 4. 逐行失败，不中断整批成功数据

当前 parser 对坏行的处理方式是：

- 记录为 `MasterListParseError`
- 保留原始列内容
- 继续解析剩余有效行

这满足了 issue 的核心要求：

> malformed-row fixtures generate structured parse errors while valid rows still load

也就是说，一行坏数据不会导致整批主数据表无法读取。

### 5. 支持空白行跳过与额外列保留

当前已经实现：

- 全空白行自动跳过
- 非关键列不会丢失，会进入 `extra_columns`

例如像 `企业状态`、`notes` 这类当前未正式入库、但后面可能用于排查和补充的信息，会被保留下来，而不是在解析阶段直接丢弃。

---

## 二、输出结构说明

### 1. 成功行 `ParsedMasterListRow`

每一行成功解析后，当前至少包含这些字段：

- `row_number`
- `source_path`
- `raw_columns`
- `name`
- `credit_code`
- `registered_address`
- `industry`
- `extra_columns`

这里的设计意图是：

- `raw_columns` 用于回溯原始行数据
- 关键字段先抽出来，供后续标准化和导入逻辑使用
- 其他未映射字段进入 `extra_columns`，避免信息损失

### 2. 错误行 `MasterListParseError`

错误对象当前包含：

- `row_number`
- `source_path`
- `message`
- `raw_columns`

这样后续生成导入报告时可以准确回答：

- 哪一行失败
- 为什么失败
- 原始内容是什么

---

## 三、怎么使用

### 1. 直接解析 CSV

```python
from company_data_agent.ingest import MasterListParser

parser = MasterListParser()
result = parser.parse("data/shenzhen_company_list.csv")

print(len(result.rows))
print(len(result.errors))
```

### 2. 直接解析 Excel

```python
from company_data_agent.ingest import MasterListParser

parser = MasterListParser()
result = parser.parse("data/shenzhen_company_list.xlsx")

for row in result.rows:
    print(row.name, row.credit_code)
```

### 3. 使用成功行

```python
for row in result.rows:
    print(
        row.row_number,
        row.name,
        row.credit_code,
        row.registered_address,
        row.industry,
    )
```

### 4. 使用错误行

```python
for error in result.errors:
    print(error.row_number, error.message, error.raw_columns)
```

这就是后续 `#13` 生成“失败 N 条”的导入报告的直接输入。

---

## 四、当前支持的解析行为

### 1. 空白行跳过

如果整行都是空值，parser 会直接跳过，不计入成功，也不计入错误。

### 2. 必要字段缺失时报错

当前必要字段是：

- `name`
- `credit_code`

只要这两个字段中有任意一个为空，该行会进入 `errors`，不会进入 `rows`。

### 3. 额外列保留

例如输入中有：

- `企业状态`
- `notes`
- `备注`

这类当前没有映射为 canonical 字段的列，会保留在：

```python
row.extra_columns
```

### 4. 不支持的文件格式立即失败

比如：

- `.json`
- `.txt`

这类输入不会尝试“猜测解析”，而是立即报：

```text
unsupported master list format
```

这样可以避免错误输入被悄悄接受。

---

## 五、怎么验证

### 1. 自动化测试

当前 `Issue #11` 新增了 5 个 parser 测试，覆盖：

- CSV 正常解析
- Excel 正常解析
- 空白行跳过
- 单行错误不影响其他成功行
- 标准化输出快照一致
- 不支持格式报错

在 `apps/company-data-agent` 目录运行：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

当前结果：

```text
21 passed
```

其中包括：

- `#9` 的模型测试
- `#10` 的配置 contract 测试
- `#11` 的主数据表解析测试

### 2. 手工验证建议

建议重点看这几个点。

#### 验证点 A：不同 header 别名是否归一

例如：

- `企业名称`
- `公司名称`
- `name`

都应该最终映射到同一个 canonical 字段 `name`。

#### 验证点 B：坏行是否只影响自己

例如某行 `企业名称` 为空时：

- 这行应该进入 `errors`
- 其他合法行仍然进入 `rows`

#### 验证点 C：额外列是否保留

如果源文件里有暂时未映射字段，不应该丢失，而应该进入 `extra_columns`。

---

## 六、当前实现边界

这次实现只到“解析主数据表”为止，还没有进入：

- `credit_code` 规范化与企业 ID 生成
- 去重策略
- 导入报告汇总
- Qimingpian 增强
- 网页抓取
- 持久化

换句话说：

- `#11` 解决的是“把文件稳定读进来”
- `#12` 解决的是“把 identity 规范起来”
- `#13` 解决的是“把解析后的行变成 skeleton 记录并出报告”

这三张是按 docs 里的采集流程顺序往下落的，不是文档空转。

---

## 七、对后续任务的直接价值

`Issue #11` 完成后，后续任务已经有明确输入：

- `#12`
  直接消费 `ParsedMasterListRow.name` 和 `credit_code`

- `#13`
  直接消费 `rows` 和 `errors` 来做 skeleton import 与导入报告

因此从这一步开始，企业数据采集已经不是“只有 contract”，而是有了真正的可执行入口。
