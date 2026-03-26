# Issue 12 实现说明：企业信用代码规范化与稳定 ID 生成

本文档说明 `Issue #12` 已完成的内容，包括：

1. 实现了什么
2. 如何使用
3. 如何验证

核心代码位于：

- `src/company_data_agent/identity/company_identity.py`
- `tests/test_company_identity.py`

---

## 一、这次实现了什么

这次实现把企业 identity 规则从分散的字段校验提升成了一个可复用模块，解决三件事：

- 原始 `credit_code` 的规范化
- 规范化后的 `credit_code` 校验
- 稳定 `company_id` 生成

### 1. 规范化 `credit_code`

当前 `normalize_credit_code()` 会：

- 去掉首尾空白
- 转为大写
- 去掉展示层噪声中的空格和连字符 `-`

例如：

```python
normalize_credit_code(" 9144 0300-ma5future1 ")
```

结果为：

```python
"91440300MA5FUTURE1"
```

### 2. 明确校验规则

规范化之后，`credit_code` 必须满足：

- 长度为 18
- 只能包含 `0-9A-Z`

不满足时立即抛错，而不是把坏 identity 带到去重、增强或入库阶段。

### 3. 生成稳定 `company_id`

当前 `company_id` 生成算法是：

```text
COMP-{SHA256(normalized_credit_code)[:20]}
```

以 `91440300MA5FUTURE1` 为例，当前生成结果为：

```text
COMP-9A0B2B5AB656D527B267
```

这个算法的设计目标是：

- 同一个 `credit_code` 永远生成同一个 `company_id`
- 不依赖外部 provider
- 在重跑、增量更新、并行任务中保持稳定

### 4. 提供统一入口 `CompanyIdentity`

为了让后续模块更容易使用，这次提供了：

```python
CompanyIdentity.from_raw_credit_code(...)
```

它会一次完成：

- 规范化
- 校验
- `company_id` 生成

这样后续 `#13` 不需要自己拼三步逻辑。

---

## 二、怎么使用

### 1. 只做 `credit_code` 规范化

```python
from company_data_agent.identity import normalize_credit_code

normalized = normalize_credit_code(" 9144 0300-ma5future1 ")
```

### 2. 直接生成稳定 `company_id`

```python
from company_data_agent.identity import generate_company_id

company_id = generate_company_id("91440300MA5FUTURE1")
```

### 3. 一步得到完整 identity

```python
from company_data_agent.identity import CompanyIdentity

identity = CompanyIdentity.from_raw_credit_code(" 91440300ma5future1 ")

print(identity.credit_code)
print(identity.company_id)
```

### 4. 当前 `CompanyRecord` 也已接入这套规则

这次还把 `CompanyRecord` 中的 `credit_code` 与 `id` 校验接到了共享 identity 规则上，所以：

- `credit_code` 会按统一规则规范化
- `id` 必须符合 canonical `company_id` 格式

这避免了 identity 规则在 model 和 importer 两边各写一套。

---

## 三、怎么验证

### 1. 自动化测试

新增了 `test_company_identity.py`，覆盖：

- 大小写、空格、连字符等展示噪声
- 长度错误和非法字符
- `company_id` 快照稳定性
- canonical ID 格式校验
- `CompanyIdentity.from_raw_credit_code()` 一步生成

运行方式：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

### 2. 当前验证结果

当前 package 全量结果应为：

```text
27 passed
```

其中包括：

- `#9` 的 record model 测试
- `#10` 的 config contract 测试
- `#11` 的 master-list parser 测试
- `#12` 的 identity 测试

---

## 四、对后续任务的直接价值

`#12` 完成后，后续模块已经有统一 identity 入口：

- `#13`
  可直接用来生成 skeleton 记录的 `id`

- `#14/#15`
  可复用规范化后的 `credit_code` 作为 provider 查询 key

- `#22/#23`
  可保证持久化与报表中的 company identity 稳定不漂移

这一步的意义在于，后续所有真正的采集和增强逻辑都能围绕同一套 identity 规则工作，而不是各自定义“什么叫同一家公司”。
