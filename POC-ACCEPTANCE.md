# POC 验收记录

## 权威输入

- 需求：`../AI合同审核(销售租赁)_20260713.xlsx`
- 销售/服务样例：`../KSOCM_合同模板/`
- 租赁样例：`../POC合同模板（租赁）/`
- 界面参考：`../ai-contract-review/`

## 验收证据

| 验收项 | 证据 |
| --- | --- |
| 任意格式单份/批量上传 | `POST /api/contracts/upload`；解析器覆盖 DOC/DOCX/PDF/XLS/XLSX/TXT/PNG/JPG；上传页支持多选 |
| 标准/非标合同识别 | `classify_template` 与后端测试 `test_standard_classification_and_version_summary` |
| 风险条款调整、依据与谈判重点 | `review_engine.RULES`、`ReviewSuggestion`、前端 `RiskWorkspace` |
| 客户历史和标准模板对照 | `run_review` 的 previous/historical_version 与 `historical_release` |
| 官网动态条款 | `website_terms.py`、`website_terms_snapshots`、哈希变化建议 |
| 新增条款识别 | NewAPI 结构化补充发现 + 规则未命中完整性检查 |
| 五轮审核与版本痕迹 | `ReviewRun.round_no` 唯一约束、五轮上限、版本比对、轮次条 |
| 采纳/修改/拒绝 | `PATCH /api/suggestions/{id}`、决策人和备注审计 |
| 转办、询问、销售反馈 | `assign`、`Consultation`、`NegotiationRecord` 与协同工作台 |
| 内部备注不对客 | 独立 `internal_note`；仅 `internal` 导出包含内部依据 |
| 两种最终文档 | `clean` 与 `redline` DOCX，另有 `internal` 版 |
| 审批与未解决风险 | 自动审批矩阵、K2 草稿号、`consistency` 未处置风险检查 |
| 权限与审计 | 六类角色、JWT/SSO、`audit_logs` |
| 部署 | 前后端 Dockerfile、Compose、Caddy、MySQL 初始化脚本与配置模板 |
| 审核人/一致性/脱敏/通知前端入口 | 智能审核的合同选择器与“版本对比”页内操作按钮 |

## 已执行验证（2026-08-10）

- 前端生产构建及 SSR：2/2 通过。
- 后端自动化测试：6/6 通过。
- 远程 MySQL：`contract_review_poc` 初始化成功，13 张表、6 个角色、3 份初始合同。
- MasterCat/NewAPI：`工剑大模型-opus` 模型查询和 Chat Completions 成功。
- 后端大模型解析：返回 3 项结构化发现，必填字段全部有效。
- 远程端到端：登录 200、审核 200、写入第 2 轮、9 项发现，包含大模型来源。
- 远程库复核：最高审核轮次 2；已落库 8 项“大模型增强”建议。
- DOCX 输出：OpenXML 可重开，带痕迹版同时存在删除线与高亮修改文本。
- 生产运行：`dist/standalone/server.js` 实际启动并返回产品页 200；`npm audit --omit=dev` 为 0。完整构建树仍有 Vinext 间接 `image-size` 的 2 项公告，当前界面未启用该图片优化路径。
- 容器编排：Compose YAML、3 个服务、数据卷和 Caddy 路由静态校验通过；当前工作机未安装 Docker CLI，镜像需在目标服务器执行实构建。
