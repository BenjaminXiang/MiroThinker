# 重建触发器等热路径修复（reduce-rebuild-validation-cost 第 1 步）

- 日期：2026-09-15
- 分支/worktree：`.worktrees/rebuild-trigger-fix`（`perf/rebuild-trigger-fix`，基线 `data/p4-serving-pack-rebuild` @ `1ee824a7`）
- 对应分析文档：[2026-09-14 重建成本分析](./2026-09-14-rebuild-cost-analysis.md) §5 / §11 / §12
- 目标：run16 前把「一次重建 20 小时」里最大的那块（单次 COMMIT 12h40m）消掉，语义不变、不放宽 fail-closed。

## 做了什么

1. **定位并实测确认**：run15 的 12h40m 全部来自 `validate_field_human_review_binding`
   的第一段——每插一行 `canonical_decision_assertion`，就对 42.3 万行
   `canonical_decision` 做一次无索引 `EXISTS`（副本库实测 **41.9 ms/行**，
   与 09-14 分析里的 42.8 ms 一致）。
2. **补了 6 个部分索引**（`method = 'human_review'` 的等值 + JSONB review_case 表达式），
   让这些判定从全表扫描变成索引查找；重建场景里这些索引是**空**的，因此判定近乎免费。
3. **三个 review 绑定校验函数加 release 级守卫**：当"本次插入所在 release 既没有
   已评审决策、也没有指向它的评审 case"时直接 `RETURN NEW`——这是这三个函数里
   **每一条拒绝分支的必要条件**，所以结果不变、只是不再做无用功。
4. **同型清理（pattern-repair）**：同样形态的 relationship / identity 绑定校验一起修；
   逐条实测其余 row 级触发器，把"同病"和"不同病"分开记录（见下）。
5. **Python 侧两处逐实体全扫描**：`canonical_identity_resolution.py` 的断言集分组
   改成一次遍历建索引（`validate_request` 的 `assertion_ids_by_source`、
   `_has_evidence_bound_internal_identifier` 改成查 `(source_id, field_path)` 索引）。

## 关键实测数字（全部在副本库上）

副本：`CREATE DATABASE miroflow_tgfix_probe TEMPLATE miroflow_candidate_v2_20260913_r1`（5.8 GB）。
生产数据目录与在线 serving 库全程未写。

| 判定点 | run15 规模事件数 | 修前 | 修后 |
|---|---|---|---|
| field 评审绑定 第①段（`canonical_decision_assertion`） | 846,986 | **41,900 µs/行 ⇒ ≈9.9 h**（与 12h40m 同量级） | **28.7 µs/行 ⇒ ≈24 s** |
| field 评审绑定（`canonical_decision` 挂载） | 423,493 | 46 µs/行 | 22 µs/行 |
| relationship 评审绑定 第①段 | 21,546 | 2,086 µs/行 | 26 µs/行 |
| identity 评审绑定（9 个挂载表） | ≈53.2 万 | 6,083 µs/行 ⇒ ≈54 min | 22 µs/行 ⇒ ≈12 s |
| 入域判定 owner 校验 | 424,440 | 1.67 µs/行 | 1.5 µs/行（本就命中索引，**不是**同类病） |
| `validate_identity_resolution_release`（14 个挂载表） | ≈50 万 | 1,647,000 µs/行 | 未改（**不同病**，见下） |
| `validate_field_temporal_binding` | 1,270,479 | 153 µs/行 ⇒ ≈54 min | 159 µs/行（索引本就命中，残值来自 selected 证据 join） |

`EXPLAIN ANALYZE`（副本库，同一字面量）：field 判定 **43.061 ms → 0.015 ms**（2870×），
relationship **4.807 ms → 0.008 ms**，identity **7.717 ms → 0.038 ms**。

**守卫 vs 索引，到底谁在起作用**：把 6 个索引删掉、只留守卫，每行代价回到
42,884 µs（≈修前）。也就是说这一步的钱**全部是索引省下来的**，守卫本身不省时间——
它的价值是让"什么情况下可以不查"变得显式、可评审。设计文档按事实这么写，不夸大守卫。

## 发现（run16 之前值得知道的）

- **入域判定不是同类病**（实测 1.67 µs/行，已有主键索引）——分析文档 §11 的猜测被数据否掉，
  不必改。
- **`validate_identity_resolution_release` 是另一类病**：它把"整个 release 的身份拓扑"
  这件事按**行**重推（14 个挂载表、约 50 万次）。副本库探针给 1.65 s/行，按此推算
  身份阶段要 20 h 以上——但 run15 分阶段时间戳（`identity_resolution_run` 02:28 →
  `relationship_projection_run` 18:55，中间还夹着 12h40m 的那次 COMMIT）根本装不下，
  所以探针在这里**未被证明可信**（真实插入窗口里数据可能还没铺满）。结论：记为本片
  **最大未解结构性风险**，run16 先加管线内计时，再谈改法；不是加索引能解决的。
- **`validate_field_temporal_binding`** 1.27 M 次触发、153 µs/行（≈54 min）：索引部分已经便宜，
  残值是逐行重算 selected 证据的时间精度，属"粒度类"候选，与上一条同一工作流。

## 怎么验证

- 修前/修后都在副本库上取数：`measure-before-after.jsonl`（每行 JSONL 一条实测）、
  `explain-analyze-before.txt` / `explain-analyze-after.txt`（原始计划与耗时）。
- **行为等价**：`test_canonical_decision_postgres.py` 的"已评审 release"用例（真实
  `human_review_resolution` 载荷）用证据插件把 pin 到的 `C2_0008` 提到 **head（C2_0014）**
  重跑，7 个相关用例全过（含"往已评审字段插断言必须被拒"和并发迟到边那条竞态用例）；
  随后全量 4 个真库套件也在 head 上跑过（见 `pytest-head-revision.txt`）。
  没评审决策时同样的插入正常提交（守卫跳过路径，已由 100/2000 行探针实测）。
- **迁移可逆**：`alembic upgrade C2_0014` 1.5 s；`downgrade C2_0013` 后
  `check_function_bodies.py` 证明函数体**逐字节回到 C2_0007**（空白归一化后 token 级一致），
  每行代价也回到 40,438 µs；再 upgrade 回守卫版。未改写任何历史迁移。
- **Python 侧**：新回归测试把断言集遍历次数钉住（RED：4 源 5 次 / 32 源 33 次；GREEN：1 次），
  identity 合同套件 58 项全绿。

## 影响哪些问题

- 消掉 09-14 分析里最大的一块（§11.2 的单次 COMMIT 12h40m）：按副本库实测推算，
  同一提交量级从 ≈10 h 降到 **≈24 s**（run16 在真实管线里复测）。
- 顺手把 identity / relationship 两族同类逐行扫描压到同一量级（≈54 min → ≈12 s、≈45 s → <1 s）。
- 留下两条**明确的未做项**：`validate_identity_resolution_release` 的粒度改造、
  `validate_field_temporal_binding` 的残值优化，都要 run16 的管线内计时来定优先级。
