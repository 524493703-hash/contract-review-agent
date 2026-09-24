# 契析 · 五轮合同审核 Web POC

审核引擎 V2 的分层流程、证据溯源和知识库设计见 [合同审核流程 V2](docs/review-pipeline-v2.md)。

依据 `AI合同审核(销售租赁)_20260713.xlsx` 第 28、29 行重构。当前交付是独立 Web 前端 + FastAPI 后端，不依赖橘掌柜/Master Cat 插件。合同业务只分为采购合同与租赁合同；每份合同按真实上传文件依次完成最多五轮审核。

> 大模型默认走 DeepSeek 官方 OpenAI-compatible API，模型为服务端 `/models` 返回的 `deepseek-v4-pro`。密钥仅存放在本地环境文件，不写入代码仓库或日志。

## 已实现能力

| POC 模块 | 实现位置与行为 |
| --- | --- |
| 采购/租赁分流 | 上传时明确选择采购合同或租赁合同；审核规则、审批矩阵与标准条款库按类型分开 |
| 租赁标准条款库 | 将《设备租赁合同的一般性条款—2025年01版》保存为 1 个版本化知识文档、66 个条款节点和 120+ 原子命题；保留原文、条号、页码、哈希、交叉引用和数值事实 |
| 角色化 Focused Checks | 先识别合同类型和我方角色，再选择“基础租赁 + 出租方 + 叉车特种设备 + 林德2025.01”Playbook；逐项执行固定 49 个检查，不使用全合同 Top-K 代替覆盖率 |
| 四态结论与证据链 | 每项输出 `MET / UNMET / PARTIAL / NOT_MENTIONED`、原文偏移 Evidence、完整检索轨迹、风险原因和 Redline；同时列明依据文件、版本、具体条号、页码和基准原文；合同包或解析不完整时标为 `UNVERIFIABLE`，不误判为未提及 |
| 法律 RAG | 公司条款与法律依据分库存储；仅按 Check 触发，依据审核日过滤生效版本，并保存颁布机关、文号、条号、官方链接、内容哈希和本次引用关系 |
| 高风险人工门禁 | 高风险、法律触发或指定事项自动生成待确认记录；未完成确认时禁止导出对外清洁版，内部审核版仍可生成 |
| 移动端/PC 登录 | 响应式登录页、JWT、六类演示角色；支持 SSO 可信头开关 |
| 批量/单份上传 | DOC/DOCX/PDF/XLS/XLSX/TXT/图片，最多 30 份、单份 80MB；保留原件、哈希和解析状态 |
| 合同台账与全文检索 | 编号、客户、项目、合同正文统一检索，风险/状态/版本/轮次同屏 |
| 标准/非标判断 | 标准合同指纹与客户版本自动分类 |
| AI 风险审核 | 版本化知识库、Focused Checks、旧正则影子召回与 `deepseek-v4-pro` 语义裁决；模型失败时保留确定性结果 |
| 官网条款 | 公网安全校验、抓取固化、内容哈希、版本变化监测和官网条款风险补充；失败自动转人工固化任务 |
| 新老客户/历史合同 | 同客户组历史版本对照、历史放行标记与谈判建议 |
| 五轮版本审核 | R1–R5 每轮必须上传真实 Word/PDF，文件可以完全不同；每轮结果留存，最终详情累计全部版本与偏离意见 |
| 批注来源识别 | 提取 PDF/Word 作者、正文锚点与批注内容，结合员工别名、部门、本轮文件来源判断客户/同事/部门，并支持人工纠正和学习映射 |
| 风险建议处理 | 原文、建议、依据、谈判重点、置信度；每条建议可接纳/修改后接纳/拒绝，或按部门定位具体同事转批复核并留痕 |
| 人工协同 | 审核人分配、跨部门询问/答复、24 小时截止、销售谈判反馈 |
| 内外备注隔离 | 销售反馈与内部备注分字段；内部备注仅进入内部版输出 |
| 原文件回写与文档输出 | 在上传的 PDF/Word 原件定位风险、高亮并写入含建议/依据/谈判重点的评论；另提供无痕客户版和含内部备注的内部版 |
| 审批矩阵 | 按合同金额和合同类型生成法务/财务/管理层层级与 K2 草稿号 |
| 订改申请 | 自然语言新要求、原合同定位、新旧要求对照、补充协议草案 |
| 一致性复核 | 最近版本、合同编号、未处置风险和补充协议归档检查 |
| 关键字段与风险报告 | 金额、付款、主体等抽取；风险类别、客户预警、金额与处理量统计 |
| 脱敏 | 身份证、手机号、邮箱、银行卡号预览脱敏；仅授权角色可调用 |
| 邮件通知 | 审核结果进入数据库待发队列，便于接企业 SMTP/消息中心 |
| 权限与审计 | 合同管理员、法务、财务、销售、审批人、系统管理员；关键动作全量审计 |
| 可部署后端 | 远程 MySQL、Dockerfile、Compose、Caddy 同源反向代理、数据卷 |

## Excel 第 28、29 行验收映射

| 原 POC 行 | 本项目对应实现 |
| --- | --- |
| 第 28 行 · 条款审核准确度 | 标准/客户版本分类；租赁标准条款逐条偏离；同客户历史合同与历史放行；标准条款外风险；原 PDF/Word 高亮评论；后续轮次继承人工结论；R5 汇总全部版本与偏离意见 |
| 第 29 行 · 人工审核功能 | 接纳/修改后接纳/拒绝；转批与分配；跨部门条款询问及状态；客户反馈与内部备注分层；原文件批注版、客户无痕清洁版、内部审核版分别下载 |

## 技术架构

```text
浏览器 / React Web
        │  /api
        ▼
FastAPI :8000 ── 文档结构化 ── 角色化 Playbook（49 Checks）
        │                         │
        │                  混合检索 + 确定性规则 + DeepSeek
        │                         │
        ▼                         ▼
SQLite / MySQL      Evidence → 四态 → 法律 RAG → Risk → Redline → 人工门禁
```

后端默认可用 SQLite 本地运行；生产使用 MySQL。上传原件和导出文件放在持久卷，结构化数据进入数据库。

## 目录

```text
app/                         独立 Web 演示页与接口回归
backend/app/                 FastAPI 应用、模型、权限和业务接口
backend/app/services/        文档解析、规则、大模型、官网抓取、脱敏、导出
backend/scripts/init_mysql.py 远程 MySQL 幂等初始化
backend/tests/               后端自动化测试
deploy/Caddyfile             同源代理配置
compose.yml                  生产编排
deploy/backend-server.md     后端服务器部署说明
.env.example                 无密钥配置模板
```

## 本地启动

项目已创建本地 Conda 环境 `.conda`。如需重建：

```powershell
conda create -p .\.conda python=3.12 -y
.\.conda\python.exe -m pip install -r backend\requirements.txt
npm ci
```

启动后端（默认 SQLite）：

```powershell
$env:PYTHONPATH = "backend"
.\.conda\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

另开终端启动前端：

```powershell
npm run dev
```

访问 `http://localhost:3001`。API 文档为 `http://localhost:8001/docs`。

演示账号统一密码：`Poc@2026`。

| 角色 | 用户名 |
| --- | --- |
| 合同管理员 | `contract.admin` |
| 法务审核 | `legal.reviewer` |
| 财务专家 | `finance.expert` |
| 销售 | `sales.owner` |
| 审批人 | `approver` |
| 系统管理员 | `system.admin` |

## 配置远程 MySQL 与 DeepSeek API

复制配置模板，不要提交真实密钥：

```powershell
Copy-Item .env.example .env
```

在 `.env` 设置：

```dotenv
DATABASE_URL=mysql+pymysql://contract_user:<URL编码后的密码>@mysql.example.internal:3306/contract_review_poc?charset=utf8mb4
JWT_SECRET=<至少32字节随机值>
LLM_API_URL=https://api.deepseek.com
LLM_API_KEY=<DeepSeek API Key>
LLM_MODEL=deepseek-v4-pro
FOCUSED_CHECK_MODEL=deepseek-v4-pro
LEGACY_RULE_MODE=shadow
```

首次初始化 MySQL（脚本不保存凭据）：

```powershell
$env:MYSQL_HOST = "mysql.example.internal"
$env:MYSQL_PORT = "3306"
$env:MYSQL_USER = "contract_user"
$env:MYSQL_PASSWORD = "<数据库密码>"
$env:MYSQL_DATABASE = "contract_review_poc"
.\.conda\python.exe backend\scripts\init_mysql.py
```

数据库采用固定双库结构：日常运行及部署只使用 `contract_review_poc`，全部业务数据按实体保存在该库的不同表中；完整端到端验收只使用 `contract_review_test`。`scripts/live_acceptance.py` 每次运行前会重建 `contract_review_test`，不会再按时间创建新的数据库，也不会修改或清空 `contract_review_poc`。可通过 `TEST_DATABASE_NAME` 调整测试库名，但名称必须以 `_test` 结尾且不得与正式库同名。

脚本幂等执行：只创建缺失数据库/表和首次演示数据，不删除已有业务数据。

## Docker 部署

服务器安装 Docker 24+ 与 Compose v2 后，克隆仓库并创建生产配置：

```bash
git clone https://github.com/524493703-hash/contract-review-agent.git
cd contract-review-agent
cp .env.example .env
# 编辑 .env，至少替换 DATABASE_URL、JWT_SECRET、INITIAL_PASSWORD、
# CORS_ORIGINS 和 LLM_API_KEY；不要提交 .env。

docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8080/api/ready
```

默认监听服务器所有网卡的 `8080` 端口，其他计算机可访问 `http://<服务器IP>:8080`。如需改端口，例如改为 80：

```bash
APP_PORT=80 docker compose up -d
```

同时需要在云服务器安全组/系统防火墙中放行实际使用的 TCP 端口。Caddy 将 `/api/*` 转发给后端，其他请求交给前端，因此浏览器不需要跨域配置。上传与导出保存在 `contract_files` 数据卷。

更新版本：

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

生产建议：

- 将 8080 放到 HTTPS 入口之后，或给 Caddy 配置正式域名证书；
- 为数据库账户限制到业务库权限和服务器来源 IP；
- 使用至少 32 字节随机 `JWT_SECRET`；
- 首次启动前修改 `INITIAL_PASSWORD` 并保持 `DEMO_MODE=false`；
- 将 `LLM_API_KEY` 作为容器 secret/环境变量注入；
- 企业 K2/OA、SMTP 和 SSO 的实际地址由现有草稿号、待发队列和可信头适配点接入。

## 验证

```powershell
$env:PYTHONPATH = "backend"
.\.conda\python.exe -m pytest backend\tests -q
npm test
```

测试覆盖：样例风险命中、标准/非标分类、版本差异、SSRF 防护、敏感信息脱敏、登录与权限、上传、真实审核写库、建议处置、DOCX 导出、报告、知识库、审计，以及前端生产构建与服务端渲染。

前端构建生成 `dist/standalone/server.js`，生产容器不复制项目根目录的完整 `node_modules`。`npm audit --omit=dev` 为 0；完整构建树仍报告 Vinext 间接依赖 `image-size` 的 2 项公告。Vinext 会把该包追踪进 standalone，但本前端未使用 Next 图片优化接口，合同图片只由 FastAPI 解析，不会进入该 Node 解析器。上线前仍应跟随 Vinext 后续修复版本升级。

## 主要 API

- `POST /api/contracts/upload`：批量上传与解析
- `POST /api/contracts/{id}/review`：审核当前已上传轮次并回写原 PDF/Word
- `GET /api/contracts/{id}/review-runs/{run_id}/annotated`：下载本轮原文件批注版
- `PATCH /api/document-comments/{id}/source`：人工纠正批注来源并学习作者映射
- `GET /api/standard-clauses`：按合同类型读取结构化标准条款
- `GET /api/knowledge/structured`：读取版本化知识文档、66 个条款节点及原子命题
- `GET /api/playbooks/active`：读取当前角色化 Playbook、49 个检查项及覆盖报告
- `GET /api/review-runs/{run_id}/focused-checks`：读取逐项四态结论、Evidence、检索轨迹、法律依据、Redline 和人工确认状态
- `GET /api/legal-authorities?as_of=YYYY-MM-DD`：按日期读取当时有效的法律知识版本
- `PATCH /api/focused-check-results/{id}/confirm`：确认单个高风险检查项
- `POST /api/review-runs/{run_id}/confirm-high-risk`：批量确认本轮待确认事项
- `PATCH /api/suggestions/{id}`：审核建议决策
- `GET /api/contracts/{id}/versions/compare`：版本差异
- `GET /api/contracts/{id}/consistency`：签署/归档一致性检查
- `GET /api/contracts/{id}/redacted-preview`：授权脱敏预览
- `POST /api/contracts/{id}/approvals/prepare`：审批矩阵与 K2 草稿号
- `POST /api/change-requests`：订改申请和补充协议草案
- `GET /api/reports/overview`：历史风险报告
- `GET /api/audit-logs`：审计追溯

完整、可交互的接口说明在后端 `/docs`。
