# C1 专利↔公司关系重投影 — 执行日志（2026-09-15）

- 分支/worktree：`.worktrees/c1-relationship-reprojection`（`chore/c1-relationship-reprojection`，
  基线 `data/p4-serving-pack-rebuild@1ee824a7`）
- 关联变更：`patent-company-relationship-reprojection`
- 证据：`.agents/runs/c1-relationship-reprojection/`（verification-contract / verification / 重放脚本与 JSON）
- 用户裁定（2026-09-15，需求缺口规划 §10 C1）：**文档层直扫＝服务期权威，保持不动；
  关系层重投影属数据线任务；D0 增加"两存储口径"断言防再漂移。**

## 一、问题

run15 封包（`serving-pack-run15-sealed`）里同一件事有两个口径：

| 存储 | 口径 | run15 实测 |
|---|---|---|
| 文档层（专利 `applicants[].canonical_company_id`） | 行 / 专利 / 公司 | **7,614 / 7,042 / 960** |
| 关系层（`relationships.json` → `patent_has_applicant`） | 边 / 专利 / 公司 | **123 / 123 / 49** |

差 ~62 倍。服务期因为走"文档层直扫"，用户暂时看不到这个缺口，但
`relationships.json` 同时被包加载器、路径资格（`company_to_patent` /
`patent_to_company`）和管理台关系列表读取——任何"关系遍历"类需求都会继承一张
完成度 1.7% 的图。

## 二、查到了什么（根因）

**投影层不是凶手。** run15 的投影结果写着 `patent_has_applicant`
候选 123 / 接纳 123 / 拒绝 0，一条 reason code 都没有；构建期还有一道硬断言
（`knowledge_build_isolated.py:7159`）保证"接纳数 = 链接数 + 种子数"，
而 run15 是 10,897 = 10,773 + 124。**也就是说种子阶段只产出了 124 个种子
（123 条专利申请 + 1 条教授任职）**，投影把收到的东西全投影了。

**根因：种子阶段读的是"原始落地行"，不是"映射后的对象全集"。**

1. `_typed_relationship_seeds` 用 `row.payload["id"]` 建对象索引
   （`knowledge_build_isolated.py:6491-6495`，改前）。
2. 只有 `s12a-released-objects-full-v1` 这一路的 payload 是"释放对象"形状
   （`_stage_and_land` 只对它拆 `payload_json`，`:9354-9361`）。
3. 另外 12 路补充源保留原始域形状：`p4-patent-full-v1.jsonl` 的 id 键叫
   `patent_id`（`_p4_patent_record`，`:4409-4417`），`p4-company-full-v1.jsonl`
   叫 `company_name`（`:4317`）。**它们全都没有 `payload["id"]`，因此一个都进不了
   对象索引。**
4. 这些记录其实早就有"释放对象"形状——`_merge_p4_created_rows`
   （`:4731`，构造器表 `:4428-4433`）为每条合成的释放对象 payload，并存进
   `row_by_object`（`:4938`；公司回填同理 `:3816`；发布库对象 `:5610`）。
   但 `row_by_object` 只往"映射后权威"里传，从没回过关系投影。
5. 于是 3 条专利申请种子通道全部缩到了 5,561 个 released_objects 对象上：
   - 通道 1（已解析申请人绑定）：`bound_object_id = source_object_by_canonical.get(...)`
     取不到就 `continue`（`:6677-6684`）；
   - 通道 2（`core_facts.company_ids`）：只有发布库专利有该字段；
   - 通道 3（申请人姓名→释放公司名解析）：公司名索引同样只有发布库公司。

**证据链闭合**：run15 的 123 条边里 **122 条**的 `evidence_metadata.match_kind`
是 `resolved_binding`（通道 1），另一条来自 `core_facts.company_ids[0]`。
而在 run15 数据上统计："专利和公司**两端**都恰好在 released_objects 里的绑定对"
正好是 **122** 对。数字对上，因果成立。

## 三、修了什么

1. **种子对象全集改口径**：`_map_public_authority` 把已映射对象全集
   （`row_by_object`）返回给 `_logical_graph` → `_relationship_authority`；
   新增单一出口 `_relationship_seed_object_rows()`，种子和各处口径检查共用同一张表。
   原始落地行仍用于 `professor_company_role` 的"源用途"通道（它读的是逐记录
   payload，不是对象）。
2. **D0 防漂移断言（新增）**：`_reconcile_patent_company_bindings()`
   - 每次构建打印一行 `PATENT_COMPANY_BINDING_LEDGER`（文档层绑定行/对/专利/公司、
     种子对数、种子通道分布、无法投影数、未解释缺失数+样例）；
   - **不变量**：文档层绑定对里，只要两端都是已接纳对象，就必须有对应种子；
     否则直接 `IsolatedKnowledgeBuildError` 中断构建（"不可解释的差异 = 不许发货"）。
     只有"目标公司从未成为已接纳对象"这一类才算可解释差异，计数上报。

   即：关系层允许是文档层的**子集**，但差集必须逐条可解释；run15 那种
   "7,042 → 123 静默通过"从此不可能再发生。

## 四、怎么验证的

**① 新增单测（7 条，全绿）**
- `tests/canonical_v2/test_applicant_binding_relationship_seeds.py`（3 条）：
  映射全集→产出种子；无绑定→不产出；**原始落地行不是对象全集**（C1 的 RED 复现）。
- `tests/canonical_v2/test_patent_company_binding_reconciliation.py`（4 条）：
  全投影→不报错且台账数字正确；文档层有绑定但无种子→**中断构建**；
  公司无接纳对象→计为可解释、不中断；全集助手索引正确。

**② run15 真实数据重放（`.agents/runs/c1-relationship-reprojection/replay_patent_applicant_bindings.py`，只读）**

| 口径 | 修复前（只索引 released 行） | 修复后（映射对象全集） |
|---|---|---|
| `patent_has_applicant` 边 | **122** | **7,611** |
| 文档层绑定对缺失 | 7,489 | **0** |
| 种子通道分布 | resolved_binding 122 | resolved_binding 7,611 |
| D0 断言 | **拒绝（报错）** | 通过，`unexplained_missing = 0` |

对照 run15 实际封包 123 条（含 1 条 `company_ids` 通道边）；重放从一个
只读 pack 重建输入，所以恰好 122 条就是通道 1 的全量——与因果链一致。
预期 run16 产出的关系层口径：**边 7,611 / 公司 960 / 未解释缺失 0**。

**③ 既有套件回归**：见同目录 `verification.md`（分层证据）。

**边界**：本次**未跑全量重建**；修复随 run16 生效。服务期行为零改动——
`_direct_patent_applicant_scan`（G3-simple 文档层直扫）没碰，未重启/未触碰 18188，
`/var/tmp/mirothinker-data-v2/` 零写入（重放只读该目录 + 复制到 `/tmp` scratch）。

## 五、同类问题（sibling）检查

| 通道 | run15 | 同源？ | 处置 |
|---|---|---|---|
| `patent_has_applicant` | 123 | 是 | 本片修复（7,611） |
| `professor_company_role` | 1 | **是**（同一张公司/教授姓名索引） | 本片一并修（run16 复测） |
| `professor_attributed_to_paper` | 10,773 | 否（读 links，不经对象全集） | 不动 |
| `patent_has_inventor` / `paper_has_author` | 0 | **否**——run15 的 `internal_reference_projection_result.person_projections = 0`，根本没有人员图 | 另立变更（本次仅记录） |
| `paper_references_paper` 等 | 0 | 注册表声明、无生产者 | 出范围 |

## 六、影响哪些问题

- **C1（专利↔公司权威口径）**：数据线侧关闭；run16 用
  `PATENT_COMPANY_BINDING_LEDGER` 行复测即验收。
- **D0（防漂移机制）**：本片新增"两存储口径"构建期断言 + 台账，落地。
- **未做**：全量重建；`_ApplicantBindingMergeStats.patents_bound` 计数语义
  （它按绑定记录累加，报 7,614，真实去重后是 7,042 件专利——属误导性统计，另记）；
  `patent_has_inventor` 人员图（另立）。
