# 客户现场：上传 Excel 材料，入库后可查（2026-10-22）

关联 OpenSpec：`enable-customer-site-excel-upload`

## 1. 问题

「数据导入」页依赖构建期 PostgreSQL，客户服务节点不可用；用户上传的 Excel 材料无法进入
可检索库。系统已有 manual recall 旁路：运营确认的文档会切块、向量化写入
`var/manual-recall-v1/manual-recall.json`，serving 的向量召回会即时合并。但它只接受
PDF/DOCX/TXT/MD，不接受 Excel。

## 2. 方案

- 企业文档上传支持 `.xlsx`：`openpyxl` 读活动 sheet，第一行当表头，每行拼成
  `字段: 值；...` 文本块，最多 24,000 字符。
- 预览返回 `media_kind=xlsx`、`row_count`、`chunk_count`、文本；运营确认后沿用现有
  `ManualRecallStore.add_upload` 切块/嵌入/落盘。
- serving 与 admin 共用同一个 `ManualRecallStore` 实例，确认后向内存追加 points，
  下一次提问即可召回，无需重建索引或重启。
- 前端「上传文档」输入接受 `.xlsx`。

## 3. 边界

- 这是“资料级入库 + 立即可查”，不是把每一行写进 `company`/`patent`/`professor` 结构化表。
- 单次最多 24k 字符；大表需拆分或按企业上传。
- 不依赖 `DATABASE_URL`、不重建 serving pack、不改索引。

## 4. 验收

- 2 行企业 Excel 预览：`row_count=2`，文本含 `公司名称: ...`。
- 确认后 `manual-recall.json` 新增 points；管理员文档列表可查。
- **chat 自动召回已通过（2026-10-23，第 4 轮）**：产品名/公司名问法均能答出上传内容并带
  `local-source-*` 引用；不相关问法不受影响，撤销后内容消失。详见执行日志第 4 轮。
- 15 个 manual recall API 测试中 13 通过、2 个既有环境/校验测试失败（与 XLSX 无关）。

## 5. 回滚

恢复 `canonical_v2_manual_recall.py` / `browse.html` 的 `.bak-xlsx-*`，重启；如需撤销测试文档，
调用 `POST /company-documents/{doc_id}/revert`。
