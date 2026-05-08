# Issue 9 实现说明：企业标准记录模型与字段约束

本文档说明 `Issue #9` 已完成的实现内容，包括：

1. 实现了什么
2. 如何在代码中使用
3. 如何验证当前实现

当前实现位于 `apps/company-data-agent` 包中，核心文件如下：

- `src/company_data_agent/models/company_record.py`
- `tests/test_company_record.py`

---

## 一、这次实现了什么

本次实现的目标是为后续企业数据采集流水线提供一个稳定、可复用、可验证的“标准企业记录结构”，避免不同阶段各自拼接字段、各自定义约束，导致数据结构漂移。

### 1. 建立了统一的企业记录模型

当前定义了两类主记录：

- `PartialCompanyRecord`
  作用：表示流水线中间阶段的企业记录。
  适用场景：企业列表导入完成后、Qimingpian 补充后、网页抓取后，但尚未满足最终入库条件时。

- `FinalCompanyRecord`
  作用：表示已经满足最终持久化和下游消费条件的企业记录。
  与 `PartialCompanyRecord` 的关键区别是：
  - `id` 必须存在
  - `profile_summary` 必须存在
  - `profile_embedding` 必须存在
  - `completeness_score` 必须存在
  - `last_updated` 必须存在

这种拆分避免了两个常见问题：

- 中间态记录被错误地当成“可入库最终态”使用
- 为了兼容中间态，把最终态字段也做成过于宽松，导致后续无法严格校验

### 2. 建立了来源枚举

实现了 `CompanySource` 枚举，用于统一记录企业信息的来源：

- `master_list`
- `qimingpian`
- `website`
- `pr_news`
- `web_search`
- `manual`

作用是让 `sources` 字段不再依赖自由字符串，降低来源标记不一致的问题。

### 3. 建立了关键人员的嵌套结构

实现了：

- `EducationRecord`
- `KeyPersonnelRecord`

用于约束 `key_personnel` 字段的数据形状，支持如下结构：

```python
[
    {
        "name": "张三",
        "role": "CTO",
        "education": [
            {
                "institution": "南方科技大学",
                "degree": "PhD",
                "year": 2020,
                "field": "机器人学",
            }
        ],
    }
]
```

这一步的意义是把 PRD 里约定的 JSONB 结构提前固化到模型层，避免后续抓取、抽取、入库阶段对 `key_personnel` 的结构理解不一致。

### 4. 建立了字段级 invariant

当前已经为以下关键字段加入了强校验：

- `id`
  - 必须以 `COMP-` 开头
  - 不能是空后缀

- `credit_code`
  - 统一转为去空格、全大写
  - 必须是 18 位字母数字组合

- `sources`
  - 至少有一个来源
  - 自动去重，同时保留原始顺序

- `tech_tags` / `industry_tags` / `investors`
  - 自动去重
  - 自动去除空白项

- `profile_embedding`
  - 不能为空列表
  - 只能包含有限浮点数，禁止 `NaN` / `inf`

- `completeness_score`
  - 必须在 `0-100` 范围内

- `last_updated`
  - 必须是带时区的时间

这些 invariant 的核心目的不是“让模型更严格”本身，而是让后续阶段尽早失败：

- 不合法的 `credit_code` 不应该进入去重逻辑
- 无时区时间不应该进入最终持久化
- 非法向量不应该等到数据库阶段才暴露

---

## 二、怎么使用

### 1. 作为中间态记录使用

当某条企业记录只有基础字段，还没有最终摘要和 embedding 时，应使用 `PartialCompanyRecord`：

```python
from company_data_agent.models.company_record import CompanySource, PartialCompanyRecord

record = PartialCompanyRecord.model_validate(
    {
        "name": "深圳未来机器人有限公司",
        "credit_code": "91440300MA5FUTURE1",
        "sources": [CompanySource.MASTER_LIST],
        "raw_data_path": "raw/company/91440300MA5FUTURE1/master.json",
    }
)
```

适合用于这些阶段：

- 企业列表导入
- 企名片返回结果合并后的临时态
- 网页抓取字段抽取后的临时态

### 2. 作为最终记录使用

当记录已经满足入库和下游消费要求时，应使用 `FinalCompanyRecord`：

```python
from datetime import UTC, datetime

from company_data_agent.models.company_record import CompanySource, FinalCompanyRecord

record = FinalCompanyRecord.model_validate(
    {
        "id": "COMP-91440300MA5FUTURE1",
        "name": "深圳未来机器人有限公司",
        "credit_code": "91440300MA5FUTURE1",
        "profile_summary": "一家聚焦手术机器人与智能控制系统的深圳科技企业，面向医院与科研机构提供核心机器人平台能力。",
        "profile_embedding": [0.1, 0.2, 0.3],
        "sources": [CompanySource.MASTER_LIST, CompanySource.WEBSITE],
        "completeness_score": 78,
        "last_updated": datetime(2026, 3, 21, 16, 0, tzinfo=UTC),
        "raw_data_path": "raw/company/91440300MA5FUTURE1/final.json",
    }
)
```

适合用于这些阶段：

- 最终质量校验后
- PostgreSQL / JSONL 持久化前
- 提供给下游 Phase 1 教授采集前

### 3. 嵌套结构的使用方式

`key_personnel` 允许直接传字典，Pydantic 会自动解析为强类型对象：

```python
record = PartialCompanyRecord.model_validate(
    {
        "name": "深圳未来机器人有限公司",
        "credit_code": "91440300MA5FUTURE1",
        "sources": [CompanySource.WEBSITE],
        "raw_data_path": "raw/company/91440300MA5FUTURE1/website.json",
        "key_personnel": [
            {
                "name": "张三",
                "role": "CTO",
                "education": [
                    {
                        "institution": "南方科技大学",
                        "degree": "PhD",
                        "year": 2020,
                        "field": "机器人学",
                    }
                ],
            }
        ],
    }
)
```

这样后续代码可以直接访问：

```python
record.key_personnel[0].education[0].institution
```

而不必在业务逻辑层手工判断 JSON 结构是否完整。

---

## 三、怎么验证

### 1. 自动化测试

当前已经为 `Issue #9` 实现了 9 个测试，覆盖：

- 最小合法中间态记录
- 最终态记录的必填 invariant
- 非法 `credit_code`
- 非法 `id`
- 越界 `completeness_score`
- 无时区 `last_updated`
- 非法 embedding 数值
- 嵌套 `key_personnel` 结构
- 空 `sources`

在 `apps/company-data-agent` 目录下运行：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

当前验证结果：

```text
9 passed
```

### 2. 手工验证建议

除了自动化测试，建议在交接或 code review 时手工确认以下几点：

#### 验证点 A：中间态与最终态是否真正分离

检查以下行为是否符合预期：

- `PartialCompanyRecord` 允许缺少 `profile_summary`
- `FinalCompanyRecord` 不允许缺少 `profile_summary`

这可以防止后续实现把临时态误入库。

#### 验证点 B：来源与标签字段是否去重且顺序稳定

例如：

```python
sources=[CompanySource.MASTER_LIST, CompanySource.WEBSITE, CompanySource.MASTER_LIST]
```

应输出为：

```python
[CompanySource.MASTER_LIST, CompanySource.WEBSITE]
```

这保证后续合并逻辑是确定性的。

#### 验证点 C：非法输入是否在模型层被拦截

建议重点检查：

- `credit_code="bad-code"`
- `profile_embedding=[0.1, float("nan")]`
- `last_updated=datetime(2026, 3, 21, 16, 0)`

这些输入都应该在模型构造阶段失败，而不是延迟到更后面的阶段。

---

## 四、当前实现的边界

这次完成的是“标准记录模型”和“字段 invariant”，还没有进入以下内容：

- 配置 schema 与 artifact path contract
- 企业列表导入
- `credit_code` 到 `COMP-*` 的确定性 ID 生成算法
- Qimingpian client
- 网页抓取与字段抽取
- `profile_summary` 生成
- embedding provider 对接
- completeness_score 计算
- PostgreSQL / JSONL 持久化

也就是说，这次完成的是后续所有任务都会依赖的“数据结构底座”，不是完整采集链路。

---

## 五、对后续任务的直接价值

这次实现会直接降低后续任务的复杂度：

- `#11/#12/#13`
  可以直接把导入后的记录落到 `PartialCompanyRecord`

- `#14/#15/#18`
  可以围绕统一字段结构写 provider normalization 和 extraction 逻辑

- `#19/#20/#21/#22`
  可以明确依赖 `FinalCompanyRecord` 的最终字段约束，而不是重复写校验逻辑

换句话说，后续 issue 不需要再争论“企业记录最终长什么样”，只需要在这个固定 contract 上继续补实现。
