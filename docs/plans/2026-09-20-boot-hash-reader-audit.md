# 启动期哈希的读者审计：同一个事实被重算 4 次（2026-09-20）

> 类型：审计（R8 规则①「无读者即删」/②「一处一次」的逐条落实）· 写一次
> 上游：`2026-09-20-boot-cost-attribution.md`（启动 71% 花在"序列化+算哈希"）
> 方法：用**已有的 py-spy 采样**（17,672 样本，25 Hz，scratch 实例 18199，未碰 18188）
> 把每个序列化样本归到**最内层属于本仓库的调用帧**，再对每个站点读代码问"这个值谁读"。

---

## 1. 归因结果（按调用点，占启动总时长）

| 占比 | 调用点 | 在算什么 |
|---|---|---|
| **24.4%** | `json/encoder.py:200 encode`（上方无本仓库帧） | pydantic 内部触发的编码——**构造期校验**路径 |
| **7.2%** | `serving_pack_loader.py:1818` `create_serving_pack_query_planner` | 重算 `index_projection_request_sha256` |
| **6.8%** | `complete_candidate_runner.py:799` `_compose_pack_consumer_runtime` | 重算**同一个** `index_projection_request_sha256` |
| **6.6%** | `serving_pack_loader.py:1000` `open_serving_pack_authority` | 重算 + 与 manifest 比一次 |
| **6.6%** | `serving_pack_loader.py:1966` `create_serving_pack_knowledge_read` | 重算 `relationship_request_content_sha256` |
| **6.2%** | `knowledge_read_isolated.py:978` `__init__` | 构造期对整个请求对象 dump |
| **6.1%** | `serving_pack_loader.py:919` `open_serving_pack_authority` | 重算 + 与 manifest 比一次 |
| 0.5%+0.5%+0.3%+0.3% | domain_projection / path_eligibility / candidate_projection 的 validate_* | 校验期自哈希 |

**五个"重算同一个事实"的站点合计 33.3%**，其余是构造期自哈希与 pydantic 内部编码。

## 2. 逐站点读者审计

### 站点 1/2：`open_serving_pack_authority:919 / :1000`（合计 12.7%）——**重算的值只有它自己的比较语句在读**

```python
observed_request_sha256 = _canonical_sha256(relationship_request.model_dump(mode="json"))
if observed_request_sha256 != manifest.relationship_request_sha256:
    raise ServingPackIntegrityError("... does not reproduce its recorded hash")
```

关键证据在**下游**（`complete_candidate_runner.py:1019-1023`）：handoff 真正携带的值是

```python
relationship_request_sha256=(authority.manifest.relationship_request_sha256),
index_projection_request_sha256=(authority.manifest.index_projection_request_sha256),
```

——**从 manifest 读的**。重算出来的那份，读者只有紧邻的 `if`。

它**不是毫无意义**：它的作用是"解析器漂移检测"（把 JSON 解析回对象后能不能复现封印时的对象图哈希）。
但按 R11/P2，这正是应当换成**parser/schema 版本绑定**的那一类：把解析器版本记进 pack、比对版本，
而不必把整棵对象图 dump 出来算一遍。

### 站点 3/4/5：planner / knowledge_read / consumer_runtime（合计 20.6%）——**同一个值又重算了三遍**

```python
# serving_pack_loader.py:1817-1818 (planner)
index_projection_request_sha256=_canonical_sha256(index_request.model_dump(mode="json")),
# serving_pack_loader.py:1966 (knowledge_read)
relationship_request_content_sha256=iso._canonical_sha256(relationship_request.model_dump(mode="json")),
# complete_candidate_runner.py:799 (consumer runtime)
index_projection_request_sha256=_canonical_sha256(...),
```

这三处算出的值**确实有读者**——被存进 `PlanningReleaseBinding` / `_RelationshipAuthority` /
consumer binding，请求期用于绑定校验（`knowledge_read_isolated.py:1048` 拿它跟另一个重算值比）。

但**同一个值的权威来源是 manifest**，而且站点 2 刚刚已经验过一次。所以这三处的正确形态是
**读据不重算**（R8 规则②「一处一次：最早层证明 + 收据，下游只验据不重放」）。
现在等于：**同一对哈希在启动期算了 4 遍，其中 3 遍的目的是"把结果拿去跟第 4 遍比"。**

### 站点 6/7：构造期自哈希（`_ContentModel`，21 个子类 / 317 个读者）

```python
class _ContentModel(ContractModel):
    content_sha256: str = Field(default=_ZERO_SHA256, ...)
    @model_validator(mode="after")
    def bind_content(self):
        expected = _canonical_sha256(self.model_dump(mode="json", exclude={"content_sha256"}))
        if self.content_sha256 == _ZERO_SHA256:
            object.__setattr__(self, "content_sha256", expected)
        elif self.content_sha256 != expected:
            raise ValueError("content_sha256 must bind the complete normalized value")
```

这是**真身份机制，不是过度设计**：317 个读者在请求期用它对账。但它现在**在构造时就做全量 dump**。
对"从已封印、已按文件校验过的制品里读出来"的对象，构造期的这次 dump 可以延迟到**首次被读**时再算
（惰性），语义不变（只算一次、值相同），启动期却省掉整块。

## 3. 裁定与优先级

| # | 动作 | 依据 | 预计省下（占 690s） |
|---|---|---|---|
| A | 站点 1/2 换成**解析器/模式版本绑定**（不再 dump 全图算哈希） | R11/P2 | ≈ 12.7% ≈ 88 s |
| B | 站点 3/4/5 **改为读 manifest 的收据**，不重算 | R8 规则② | ≈ 20.6% ≈ 142 s |
| C | `_ContentModel.content_sha256` 改为**惰性**（首次读时算） | R8 规则③精神 + P3 | 需单独实测（估计为剩余大头） |

A+B 合计约 **230 秒 / 690 秒**，且**不改变任何对外语义**（值与校验结论都不变）。
C 是最大的一块，但要动身份机制本身，风险更高，须单独设计 + 全量基线验证。

## 4. 必须先确认的三件事（否则会改坏）

1. **哈希的身份语义**：这些 `*_sha256` 很可能同时是 trace / 引用 / 证据标识的来源。
   换来源（manifest）或惰性化时，**必须保证同一次会话里同一个标识的值逐字节相同**，
   否则 replay 7/7 与两个逐字探针会破。
2. **删掉比较会不会放过真错误**：站点 1/2 的漂移检测能力要**替换**而不是消失——
   版本绑定必须真的能挡住"解析器改了、包没重封印"的情况，否则是把 fail-closed 变成 fail-open。
3. **封印期是否可省**：同样的重算在封印期也跑过（envelope_validate 2071s，见 G24），
   两处要一起看，不能只优化启动而把"重新算一遍"留在封印。

## 5. 建议的下一步（不是方案，是顺序）

1. 先做 **B**（读据不重算）：改动局部、语义最直白、可先影子验证。
2. 再做 **A**（版本绑定）：需要一个"解析器版本"字段进 pack manifest，属契约变更 → 走 OpenSpec。
3. **C** 单独立项：惰性化 `content_sha256`，先测"启动期到底为它 dump 了多少"（本次未单独分离），
   再决定是惰性还是"只对真正进请求路径的对象算"。
4. 每一步都跑 R9 的基线：replay 7/7 + 两个逐字探针 + TTFT 对照 + 启动耗时分段对比。
