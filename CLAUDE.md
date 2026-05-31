# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 后端：初始化环境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp -R config/env.example config/env && cp config/users.example.json config/users.json

# 前端：初始化 + 构建
cd frontend && pnpm install && pnpm build && cd ..

# 运行（前端 dist 已构建后，Flask 同源服务 SPA + API）
python app.py  # http://127.0.0.1:8000

# 开发模式（前端独立热更新 + 后端 API）
python app.py             # 终端 1：后端 8000
cd frontend && pnpm dev   # 终端 2：前端 5173（vite proxy 把 /api/* 转发到 8000）

# 测试
pytest              # 全部后端测试
cd frontend && pnpm typecheck  # 前端类型检查
```

无 Python linter 配置，遵循 PEP 8。前端用 ESLint flat + Prettier。

## 架构概览

**前后端分离应用**：
- 后端：Flask API-only + SQLite + JWT 鉴权 + SSE 流式响应
- 前端：React 18 + Vite 5 + TypeScript + Ant Design 5（独立项目，构建产物输出到 `static/dist/`）

### 请求流

```
浏览器 (SPA)
   ↓  Authorization: Bearer <access_token>
Flask Blueprint 路由
   ↓
业务逻辑层 → AI Provider (OpenAI/Google/Claude) → SSE 响应流
   ↓
SQLite (db.py) + token_usage 记录
```

### 后端核心模块

| 文件 | 职责 |
|------|------|
| `gtpweb/app_factory.py` | `create_app()` — 加载配置、注册 CORS（仅 dev）、初始化 DB、注册蓝图 |
| `gtpweb/auth_jwt.py` | JWT 双 Token：`issue_tokens` 签发、`require_login` / `require_admin` 装饰器、refresh 撤销列表 |
| `gtpweb/config.py` | 从 `config/env/*.env` 分组加载配置；`JWT_SECRET` 独立配置（默认派生自 `APP_SECRET_KEY`） |
| `gtpweb/db.py` | SQLite 初始化 + schema 迁移（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN`），含 `revoked_refresh_jti` 表 |
| `gtpweb/runtime_state.py` | 运行时设置热重载；`HOT_RELOADABLE_ENV_KEYS` 白名单 |
| `gtpweb/ai_providers.py` | 三家 provider 模型选项解析、消息格式转换 |
| `gtpweb/openai_stream.py` | 封装 OpenAI Responses API / `chat.completions` SSE |
| `gtpweb/blueprints/chat.py` | `/api/chat/stream` SSE 流式入口 |
| `gtpweb/blueprints/auth.py` | JWT 登录 / refresh / logout / `/api/me` |
| `gtpweb/blueprints/bootstrap.py` | `/api/bootstrap`（取代旧 `window.__APP_CONFIG__`） + `/api/tutorial` |
| `gtpweb/blueprints/spa.py` | catch-all 服务前端 `static/dist/` 构建产物，必须最后注册 |
| `gtpweb/attachments.py` | 附件校验 + 文档解析（docx/xlsx/xls/txt） |
| `gtpweb/token_tracking.py` | Token 用量记录与查询 |
| `gtpweb/audit.py` | 审计日志记录 |
| `gtpweb/user_store.py` | 用户 CRUD（含 `enabled` 与每用户 `api_keys`） |

### 前端结构（`frontend/`）

| 路径 | 职责 |
|------|------|
| `src/main.tsx` | 入口：QueryClientProvider + AntD ConfigProvider(zhCN) + RouterProvider |
| `src/api/client.ts` | `apiFetch` 包装：自动注入 `Authorization` 头、401 时自动 refresh 重放 |
| `src/api/chatStream.ts` | SSE 流式调用：fetch + ReadableStream + AbortController |
| `src/stores/authStore.ts` | Zustand：`accessToken`（内存）、`user`、`initialized` |
| `src/hooks/useChatStream.ts` | SSE 主控：50ms 节流 setState、30s 空闲超时、错误重试 |
| `src/components/AuthGuard.tsx` | 启动时调 `/api/refresh` 决定路由；未登录跳 `/login` |
| `src/components/Markdown.tsx` | `react-markdown` + `remark-gfm` + `rehype-highlight` 渲染 |
| `src/pages/LoginPage.tsx` | AntD Form + Card |
| `src/pages/ChatPage/` | 聊天页：Topbar + Sidebar + MessageList + Composer + Modals |
| `src/pages/AdminPage/` | 6 Tab 后台：Dashboard / Users / Usage / Documents / Config(CodeMirror) / Audit |
| `src/pages/TutorialPage.tsx` | 教程页（拉 `/api/tutorial` markdown） |

### API 端点速查

| 蓝图 | 路由 | 说明 |
|------|------|------|
| auth | `POST /api/login`, `POST /api/refresh`, `POST /api/logout`, `GET /api/me` | JWT 鉴权 |
| bootstrap | `GET /api/bootstrap`, `GET /api/tutorial` | SPA 启动数据 + 教程 markdown |
| conversation | `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/<id>`, `GET /api/conversations/<id>/messages`, `GET /api/conversations/<id>/export`, `GET /api/me/usage`, `GET /api/attachments/<id>/content` | 会话与消息 CRUD（`@require_login`） |
| chat | `POST /api/chat/stream`, `POST /api/chat/retry/stream` | SSE 流式对话 |
| documents | `GET /api/documents`, `GET /api/documents/<id>/download`, `POST/PUT/DELETE /api/admin/documents[/<id>]` | 文档下载中心 |
| admin | `GET/POST/PATCH/DELETE /api/admin/users[/<username>]`, `GET /api/admin/dashboard`, `GET /api/admin/token-usage`, `GET /api/admin/audit-logs`, `GET/PUT /api/admin/config-files/*`, `GET/PUT /api/admin/auth-config` | 后台管理（`@require_admin`） |
| spa | `GET /<path:path>` | 兜底服务 `static/dist/index.html` |

所有 API 鉴权统一通过 `@require_login` / `@require_admin` 装饰器，从 `g.user["username"]` / `g.user["is_admin"]` 取认证信息。

### JWT 双 Token 流程

| Token | 存储 | 有效期 | 用途 |
|-------|------|--------|------|
| Access | 前端 Zustand（内存） | 15 分钟 | 每次 API 请求 `Authorization: Bearer <token>` 携带 |
| Refresh | HttpOnly Cookie（`Path=/api`，`SameSite=Lax`） | 7 天 | 调 `/api/refresh` 换新 access；轮转后旧 jti 进入撤销列表 |

撤销列表表 `revoked_refresh_jti(jti, revoked_at, exp_at)`，登录时顺手清理过期项。

### 数据库 Schema（7 张表）

- `conversations`：`id, username, title, model, reasoning_effort, thinking_level, last_response_id, created_at, updated_at`
- `messages`：`id, conversation_id (FK CASCADE), role, content, reasoning, status, created_at`
- `message_attachments`：`id, message_id (FK CASCADE), file_name, file_path, mime_type, kind, parsed_text, created_at`
- `token_usage`：`id, username, conversation_id (FK SET NULL), message_id (FK SET NULL), model, provider, input_tokens, output_tokens, created_at`
- `documents`：`id, title, category, file_path, file_name, file_size, mime_type, uploaded_by, created_at, updated_at`
- `audit_logs`：`id, username, action, target_type, target_id, detail, ip_address, created_at`
- `revoked_refresh_jti`：`jti PK, revoked_at, exp_at` — JWT refresh 撤销列表

### AI Provider 接入

前端模型 ID：`openai:<name>` / `google:<name>` / `claude:<name>`。

| Provider | SDK | 流式 API | Usage 字段位置 |
|----------|-----|---------|----------------|
| OpenAI | `openai` | `responses.create()` / `chat.completions.create()` | `response.completed` / 末尾 chunk |
| Google | `google-genai` | `generate_content_stream()` | 每 chunk `usage_metadata` |
| Claude | `anthropic` | `messages.stream()` 上下文管理器 | `message_start` + `message_delta` |

**每用户独立 Key**：用户记录可配置 `api_keys: {openai, google, claude}`，`chat.py` 请求开始时临时创建覆盖客户端。

### 配置分组（`config/env/`）

| 文件 | 关键变量 |
|------|---------|
| `app.env` | `APP_SECRET_KEY`, `JWT_SECRET`（可选，默认派生自 `APP_SECRET_KEY`）, `PORT`, `FLASK_DEBUG`, `FRONTEND_DEV_ORIGIN`（默认 `http://localhost:5173`） |
| `openai.env` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `google.env` | `GOOGLE_BASE_URL`, `GOOGLE_API_KEY` |
| `claude.env` | `CLAUDE_BASE_URL`, `CLAUDE_API_KEY` |
| `storage.env` | `CHAT_DB_FILE`, `UPLOAD_DIR` |
| `attachments.env` | `MAX_UPLOAD_MB`, `ALLOWED_ATTACHMENT_EXTS` |
| `logging.env` | `LOG_LEVEL`, `LOG_FILE`, `LOG_TO_STDOUT` |

模型定义在 `config/models.jsonc`（JSONC，支持注释）。

### 数据目录

- `data/chat.db`：SQLite 数据库
- `data/uploads/<username>/<conversation_id>/`：聊天附件
- `data/documents/`：文档中心存储
- `data/tutorial.md`：使用教程内容（Markdown，可在管理后台编辑）

### 部署模式

**同源部署（默认推荐）**：`pnpm build` 输出到 `static/dist/`，Flask 同时服务 API 与 SPA，单端口 8000。`run_linux.sh` 已集成 pnpm/npm 自动构建。

**独立部署（可选）**：Nginx 提供前端 + 反代 `/api/*` 到 Flask（注意 SSE 端点必须 `proxy_buffering off`），Cookie 改 `SameSite=None; Secure` + HTTPS。

### 测试架构

`tests/conftest.py` 提供：
- `app_builder` fixture：自定义 `ENV_DIR` / `MODEL_CONFIG_FILE`，monkeypatch 注入伪造 OpenAI / Google / Claude 客户端
- `_AuthedClient`：包装 `test_client`，自动注入 `Authorization: Bearer <access>`
- `logged_in_client` / `admin_client` fixture：登录后的 `_AuthedClient` 实例

新增 provider 时需要在 conftest 补充对应 mock。

## 协作规范

- 所有面向用户的输出（注释、提交信息、说明文档）使用**中文**，代码标识符与命令保持原样。
- 提交信息遵循 Conventional Commits：`feat:`, `fix:`, `docs:`, `refactor:` 等。
- 不要将 `config/env/`, `config/users.json`, `data/*.db`, `data/documents/`, `data/uploads/`, `frontend/node_modules/`, `static/dist/` 提交到 git（已在 `.gitignore` 中）。
- 新增数据库字段：在 `db.py` 的 `init_db()` 中用 `ALTER TABLE ADD COLUMN` 增量迁移，不要重建表。
- 新增 hot-reloadable env：在 `runtime_state.py` 的 `HOT_RELOADABLE_ENV_KEYS` 白名单中加入。
- 新增 API 时统一加 `@require_login` 或 `@require_admin`；从 `g.user["username"]` 取当前用户。
- 前端 API 调用统一通过 `apiFetch` / `apiJson`，不要绕过去裸 fetch，否则会失去自动 refresh。
