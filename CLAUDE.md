# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指导。

## 常用命令

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run granian --interface asgi --host 0.0.0.0 --port 8000 --workers 1 app.main:app

# 运行测试
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/test_tool_calls_live.py -v

# Docker
docker compose up -d
```

## 架构

Grok2API 是一个 FastAPI 网关，将 Grok Web 能力以 OpenAI 兼容和 Anthropic 兼容的 API 形式对外暴露。它管理一个 Grok 账号池，具备配额追踪、负载均衡和多协议支持。

### 层次结构

**Products**（`app/products/`）— API 接入层
- `openai/` — `/v1/chat/completions`、`/v1/images/*`、`/v1/videos/*`、`/v1/responses`
- `anthropic/` — `/v1/messages`
- `web/` — 管理 UI 和 WebUI（账号/配置/缓存管理）

**Control**（`app/control/`）— 业务逻辑层
- `account/` — 账号生命周期、配额窗口、存储后端（local/Redis/MySQL/PostgreSQL）
- `model/registry.py` — 包含层级/能力元数据的主模型列表
- `proxy/` — Cloudflare clearance 调度

**Dataplane**（`app/dataplane/`）— 运行时执行层
- `account/` — 内存账号表、同步循环、选择器、租约/反馈
- `proxy/` — 代理池、选择器、会话适配器
- `reverse/` — 核心反向管道：`executor.py` 执行 7 个步骤（plan → account → proxy → serialize → execute → classify → feedback）
  - `protocol/` — Grok 专用协议处理器（chat、image、video、auth、usage）
  - `transport/` — HTTP、WebSocket、gRPC-Web、Imagine WS、LiveKit

**Platform**（`app/platform/`）— 基础设施层
- `config/` — TOML/Redis/SQL 配置后端，通过 `snapshot.py` 支持热重载
- `auth/middleware.py` — API Key 验证
- `logging/`、`storage/`、`runtime/`、`net/`

### 关键设计决策

**反向管道**（`app/dataplane/reverse/executor.py`）：所有请求都经过固定的 7 步管道。修改请求处理逻辑前必须先理解此文件。

**账号池**：账号分层（basic/super/heavy）。`app/dataplane/account/selector.py` 根据模型层级和配额可用性选择账号。配额窗口按模式划分（auto/fast/expert/heavy）。

**Leader 选举**：只有一个 worker 运行重量级的 `AccountRefreshScheduler`。使用建议性文件锁（`.scheduler.lock`）——Unix 上用 fcntl，Windows 上始终为 leader。

**配置层级**：`config.defaults.toml` → 后端覆盖（TOML/Redis）→ `GROK_*` 环境变量（最高优先级）。变更检测每次请求只调用一次 `stat()`。

**多 worker 同步**：所有 worker 运行轻量级账号目录同步循环（`ACCOUNT_SYNC_INTERVAL`，默认 30s）。只有 leader 运行配额刷新。

### 关键文件

| 文件 | 用途 |
|------|------|
| `app/main.py` | 应用工厂、lifespan 启动序列、中间件 |
| `app/dataplane/reverse/executor.py` | 7 步反向管道 |
| `app/dataplane/reverse/protocol/xai_chat.py` | Grok 聊天协议 + 流式传输 |
| `app/control/account/models.py` | 账号和配额数据模型 |
| `app/control/model/registry.py` | 所有支持的模型及层级/能力信息 |
| `app/platform/config/snapshot.py` | 不可变配置视图、变更检测 |
| `config.defaults.toml` | 所有默认配置值 |

## 模型列表

完整列表见 `app/control/model/registry.py`。

### Chat

| 模型名 | 模式 | 账号层级 |
|--------|------|----------|
| `grok-4.20-0309-non-reasoning` | fast | basic+ |
| `grok-4.20-0309` | auto | basic+ |
| `grok-4.20-0309-reasoning` | expert | basic+ |
| `grok-4.20-0309-non-reasoning-super` | fast | super+ |
| `grok-4.20-0309-super` | auto | super+ |
| `grok-4.20-0309-reasoning-super` | expert | super+ |
| `grok-4.20-0309-non-reasoning-heavy` | fast | heavy+ |
| `grok-4.20-0309-heavy` | auto | heavy+ |
| `grok-4.20-0309-reasoning-heavy` | expert | heavy+ |
| `grok-4.20-multi-agent-0309` | heavy | heavy+ |
| `grok-4.20-fast` | fast | basic+（优先选最高层级账号） |
| `grok-4.20-auto` | auto | basic+（优先选最高层级账号） |
| `grok-4.20-expert` | expert | basic+（优先选最高层级账号） |
| `grok-4.20-heavy` | heavy | heavy+（优先选最高层级账号） |

### Image

| 模型名 | 账号层级 | 说明 |
|--------|----------|------|
| `grok-imagine-image-lite` | basic+ | 轻量图像生成 |
| `grok-imagine-image` | super+ | 标准图像生成 |
| `grok-imagine-image-pro` | super+ | 高质量图像生成 |
| `grok-imagine-image-edit` | super+ | 图像编辑 |

### Video

| 模型名 | 账号层级 | 说明 |
|--------|----------|------|
| `grok-imagine-video` | super+ | 视频生成 / 视频拓展 |

## 配置

运行时配置位于 `${DATA_DIR}/config.toml`（默认 `./data/config.toml`）。主要配置节：`app`、`features`、`proxy`、`retry`、`account.refresh`、`chat`/`image`/`video` 超时。

环境变量（`.env`）：`ACCOUNT_STORAGE`（local|redis|mysql|postgresql）、`DATA_DIR`、`LOG_DIR`、`SERVER_WORKERS`。

## 已知问题与修复

**curl_cffi 浏览器指纹版本不支持**（`ImpersonateError: Impersonating chromeXXX is not supported`）：
curl_cffi 只支持特定 Chrome 版本。若配置的 `user_agent` 中包含比 curl_cffi 更新的 Chrome 版本号，`_resolve_browser` 会拼出不支持的字符串（如 `chrome147`）导致报错。

修复位置 `app/dataplane/proxy/adapters/session.py`：新增 `_clamp_chrome()`，启动时从 `BrowserType` 枚举读取所有支持的版本列表，将任何不支持的版本向下取最近可用版本（如 Chrome/147 → `chrome146`）。`headers.py` 复用同一函数。此修复具有前向兼容性——curl_cffi 新增更高版本支持后自动生效，无需改配置。

若未配置含新版本号的 `user_agent`，也可直接在 `[proxy.clearance]` 中设置 `browser = "chrome146"` 作为简单替代方案。

## 测试

实时测试需要运行中的服务器和环境变量中的有效凭据。SQL 后端测试（`test_sql_engine_factory.py`）是自包含的。
