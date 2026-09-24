# 合同审核后端服务器部署

前端已经打包为 Master Cat 插件。服务器只需要运行 FastAPI 后端、MySQL 和持久化文件卷，不需要部署 Next.js 前端。

## 1. 服务器准备

- Docker Engine 24+，以及 Docker Compose v2。
- 可访问的 MySQL 8 数据库。
- 可访问的大模型兼容接口。
- 公网环境准备域名和 HTTPS 反向代理。

## 2. 配置

在项目根目录执行：

    Copy-Item deploy/backend.env.example deploy/backend.env

Linux:

    cp deploy/backend.env.example deploy/backend.env

编辑 deploy/backend.env，至少替换：

- DATABASE_URL
- JWT_SECRET
- INITIAL_PASSWORD（仅首次初始化空数据库时使用）
- LLM_API_URL
- LLM_API_KEY
- LLM_MODEL

deploy/backend.env 不应提交到版本库或发送给插件用户。
生产环境保持 `DEMO_MODE=false`，此时账号列表接口不会向客户端返回初始化密码。

## 3. 启动

    docker compose -f compose.backend.yml up -d --build

默认监听服务器所有网卡的 8071 端口。需要修改端口时：

    BACKEND_PORT=18000 docker compose -f compose.backend.yml up -d --build

如果只允许服务器本机的 HTTPS 反向代理访问，可以改为仅监听回环地址：

    BACKEND_BIND_ADDRESS=127.0.0.1 docker compose -f compose.backend.yml up -d --build

检查状态：

    curl http://127.0.0.1:8071/api/health
    curl http://127.0.0.1:8071/api/ready

## 4. HTTPS 反向代理

Caddy 示例：

    contracts.example.com {
        encode zstd gzip
        reverse_proxy 127.0.0.1:8071
    }

直接使用 8071 端口时，应通过防火墙限制为可信来源；使用 HTTPS 反向代理时，建议只开放 443。

## 5. 配置 Master Cat 插件

1. 安装 contract-review-agent-1.1.6.mcp。
2. 在插件配置中填写 https://contracts.example.com。
3. 关闭“允许 HTTP 地址”。
4. 打开插件页面，顶部连接状态应显示服务端地址。

插件通过宿主的 network:request 权限访问服务器，不要求把服务器加入浏览器 CORS 白名单。

## 6. 数据与备份

- 合同原件和导出文件位于 Docker 卷 contract_review_data。
- 结构化业务数据位于 DATABASE_URL 指向的 MySQL。
- 备份时同时备份 MySQL 和 contract_review_data。
- 恢复后先访问 /api/ready，确认数据库连接和文件目录正常。

## 7. 更新

    git pull
    docker compose -f compose.backend.yml up -d --build

数据库结构由服务启动时的初始化逻辑维护。正式生产升级前仍建议先备份数据库。
