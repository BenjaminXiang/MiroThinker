# Professor gate 降级 dry-run 复核报告（s12e）

- 数据库: `postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12c_20260726_r8`（只读事务）
- 源批次: `s12a-released-objects-full-v1`

## 现场漏斗（DB 实测）

| 阶段 | 记录数 |
| --- | ---: |
| landing.source_record (professor) | 1439 |
| knowledge.source_identity | 557 |
| knowledge.canonical_identity | 554 |
| knowledge.domain_inclusion_decision | 554 |
| professor.current_projection | 554 |

旧 gate 拒掉（1439 - source_identity 差集）: **882** 条。
脚本复现旧规则拒掉: **882** 条；与 DB 差集完全一致: **是**。

## 新规则 dry-run 分类（硬条件 = name + institution）

| 分类 | 记录数 |
| --- | ---: |
| 放行（无质量信号） | 557 |
| 放行（带质量信号，需回填候选） | 882 |
| 仍拒（缺 name/institution 或字段格式错） | 0 |

旧被拒 882 条中按新规则放行: **882** 条。

## 质量信号分布（放行但缺字段）

| 信号 | 记录数 |
| --- | ---: |
| `missing_email` | 680 |
| `missing_title` | 576 |
| `missing_department` | 160 |

注：同一记录可命中多个信号（如同时缺 department 与 title）。

## 回填候选（按 citation_count 降序，前 20）

| object_id | 姓名 | 机构 | 缺失字段 | citation_count |
| --- | --- | --- | --- | ---: |
| PROF-F7D43B28799E | 周垚 | 南方科技大学 | missing_department | 14746 |
| PROF-814BDB064B97 | 唐仙 | 清华大学深圳国际研究生院 | missing_department | 5569 |
| PROF-F65FAFD07ECB | 姚勇 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 4242 |
| PROF-A4A3D3B0C942 | Parvej Alam | 香港中文大学（深圳） | missing_email | 4236 |
| PROF-1EC0B2448E6D | 黄建华 | 香港中文大学（深圳） | missing_email | 3201 |
| PROF-8BCB9CE81A01 | 田佳峻 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 2917 |
| PROF-19535075873E | 张灿荣 | 清华大学深圳国际研究生院 | missing_department | 1913 |
| PROF-77D468AF93F5 | 孔庆磊 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 1245 |
| PROF-70F168547DAE | 高林 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 1205 |
| PROF-FF636C8A09C3 | 冯建设 | 中山大学（深圳） | missing_email | 1153 |
| PROF-A732D59BBDB0 | 徐小川 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 947 |
| PROF-C91EBBAC3D23 | 王凯旭 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 909 |
| PROF-ABBDE6D18E0E | 吴日 | 南方科技大学 | missing_department, missing_title | 845 |
| PROF-E0221A651BF9 | 朱时裴 | 哈尔滨工业大学（深圳） | missing_email | 466 |
| PROF-132D3CC74120 | 王学谦 | 清华大学深圳国际研究生院 | missing_department | 1 |
| PROF-DDD871F3EB0B | 王希林 | 清华大学深圳国际研究生院 | missing_department | 1 |
| PROF-2AD635CD3246 | 张霆廷 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 0 |
| PROF-43A86E6DA926 | 张雅鸥 | 清华大学深圳国际研究生院 | missing_department | 0 |
| PROF-77BE95F04C13 | 王博弋 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 0 |
| PROF-79257EAA1893 | 冯博文 | 哈尔滨工业大学（深圳） | missing_email, missing_title | 0 |

## 王学谦 核验

- `PROF-132D3CC74120`（王学谦，清华大学深圳国际研究生院）：新规则**放行**，信号: missing_department；此前被旧 gate 拒掉: 是

## 仍拒样例与理由（前 10）

| object_id | 姓名 | 机构 | 理由 |
| --- | --- | --- | --- |

## 实现备注

- gate 位于 `knowledge_build_isolated._selected_fields` 教授分支（非 legacy `data_agents/professor/release.py`）。
- 放行占位值（`Not supplied by the historical source.`）不参与身份键（name/institution/department/email/homepage keys）与论文作者归因签名，避免同名不同人错误合并。
- 缺字段记录同时写入 ops.knowledge_gap（`quality_signals` + affected_paths），供 Task 7 回填队列使用。
