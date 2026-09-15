# 基线固化：2026-09-15（F1+F2 上线后的 18188）

用途：**所有"过度设计消除片"（R9）的出口对照基线**。任何消除片合并前必须先对齐本基线；
不对齐即视为回退（规则见 `docs/plans/2026-09-15-requirements-gap-plan.md` §9.3）。

## 代码点（回滚锚点）

- 服务线（18188 运行）：`codex/canonical-v2-s12a-ready` @ `2fe4c16c`（F1 `4e1d93a7` 之后合并 F2）
- 数据线：`data/p4-serving-pack-rebuild` @ `1ee824a7`
- 包/索引：run15 sealed pack + `/var/tmp/mirothinker-data-v2/index-v2`（未变）

## 门禁与探针（本目录即证据）

| 项 | 结果 | 证据文件 |
|---|---|---|
| replay 门（活线 18188，G1–G7） | **7/7 ALL PASS** | `replay-f2-report.json` |
| 探针 `字节跳动` | 答案含 "ByteDance Ltd."；wall **9.92s / 10.53s**；citations 1 | `f2-summary.json` |
| 探针 `优必选有哪些专利` | **32 条本地 CN 引用**；wall 15.47s | `f2-summary.json` |
| 清单 `深圳有哪些做具身智能的公司` | citations 12；wall 20.59s | `f2-summary.json` |
| 用户案例 `详细介绍一下 国先中心（深圳）` | 答案完整、引本地企业；web 轨 `succeeded / 0 条`（`web_items=[]`） | `guoxian-f2.txt` |
| 启动 | boot-to-health **721s**；挂载收据复用（`verification: receipt`，mount 320s） | 日志条目 51/52 |

## 消除片的出口规则（每片必过，缺一不许合并）

1. replay 门 7/7；
2. 两个逐字探针（`字节跳动`→ByteDance Ltd.；`优必选有哪些专利`→32 CN）；
3. 用户案例（`国先中心`→答案完整、web 项符合当期预期）；
4. TTFT 不劣于上表（实体 ≤14s / 引用密集 ≤25s 量级）；
5. 无新增启动失败（对照 journal）；
6. 回滚资产在（合并点提交 + 一键回滚命令）。
