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
python app.py  # http://0.0.0.0:8000

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
| `gtpweb/app_factory.py` | `create_app()` — 加载配置、注册 CORS（仅 dev）、初始化 DB、注册蓝图；SDK `max_retries=0` |
| `gtpweb/auth_jwt.py` | JWT 双 Token：`issue_tokens` 签发（含 `pwd_ver`）、`require_login` / `require_admin` 装饰器、refresh 撤销列表 |
| `gtpweb/config.py` | 从 `config/env/*.env` 分组加载配置；`JWT_SECRET` 独立配置（默认派生自 `APP_SECRET_KEY`） |
| `gtpweb/db.py` | SQLite 初始化 + schema 迁移（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN`），含 `revoked_refresh_jti` 表 |
| `gtpweb/runtime_state.py` | 运行时设置热重载；`HOT_RELOADABLE_ENV_KEYS` 白名单 |
| `gtpweb/ai_providers.py` | 三家 provider 模型选项解析、消息格式转换（仅处理 text 和 image_url 类型） |
| `gtpweb/openai_stream.py` | 封装 OpenAI Responses API SSE |
| `gtpweb/blueprints/chat.py` | `/api/chat/stream` SSE 流式入口；MarkItDown 文件解析；上下文消息数限制 |
| `gtpweb/blueprints/auth.py` | JWT 登录 / refresh（含 pwd_ver 校验）/ logout / `/api/me` |
| `gtpweb/blueprints/bootstrap.py` | `/api/bootstrap` + `/api/tutorial` + `/api/logo` |
| `gtpweb/blueprints/spa.py` | catch-all 服务前端 `static/dist/` 构建产物，必须最后注册 |
| `gtpweb/attachments.py` | 附件存储 + 历史消息重建（优先使用 DB 中的 parsed_text） |
| `gtpweb/token_tracking.py` | Token 用量记录与查询 |
| `gtpweb/audit.py` | 审计日志记录（登录/聊天/会话/配置/Logo） |
| `gtpweb/user_store.py` | 用户 CRUD（含 `enabled`、`api_keys`、`profile`、`pwd_ver`） |

### 前端结构（`frontend/`）

| 路径 | 职责 |
|------|------|
| `src/main.tsx` | 入口：QueryClientProvider + AntD ConfigProvider(zhCN) + RouterProvider |
| `src/api/client.ts` | `apiFetch` 包装：自动注入 `Authorization` 头、401 时自动 refresh 重放 |
| `src/api/chatStream.ts` | SSE 流式调用：fetch + ReadableStream + AbortController |
| `src/stores/authStore.ts` | Zustand：`accessToken`（内存）、`user`、`initialized` |
| `src/hooks/useChatStream.ts` | SSE 主控：50ms 节流 setState、30s 空闲超时、onDone/onError 回调 |
| `src/components/AuthGuard.tsx` | 启动时调 `/api/refresh` 决定路由；未登录跳 `/login` |
| `src/components/AuthImage.tsx` | 带 JWT token 的图片加载组件（blob URL） |
| `src/components/Markdown.tsx` | `react-markdown` + `remark-gfm` + `rehype-highlight` 渲染 |
| `src/pages/LoginPage.tsx` | AntD Form + Card |
| `src/pages/ChatPage/` | 聊天页：Topbar + Sidebar + MessageList + Composer + Modals |
| `src/pages/AdminPage/` | 8 Tab 后台：Dashboard / Users / Usage / Documents / Models / Config / Logo / Audit |
| `src/pages/TutorialPage.tsx` | 教程页（拉 `/api/tutorial` markdown） |

### API 端点速查

| 蓝图 | 路由 | 说明 |
|------|------|------|
| auth | `POST /api/login`, `POST /api/refresh`, `POST /api/logout`, `GET /api/me` | JWT 鉴权 |
| bootstrap | `GET /api/bootstrap`, `GET /api/tutorial`, `GET /api/logo` | SPA 启动数据 + Logo |
| conversation | `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/<id>`, `GET /api/conversations/<id>/messages`, `GET /api/conversations/<id>/export`, `GET /api/me/usage`, `GET /api/attachments/<id>/content` | 会话与消息 CRUD |
| chat | `POST /api/chat/stream`, `POST /api/chat/retry/stream` | SSE 流式对话 |
| documents | `GET /api/documents`, `GET /api/documents/<id>/download`, `POST/PUT/DELETE /api/admin/documents[/<id>]` | 文档中心 |
| admin | 用户 CRUD, dashboard, token-usage, audit-logs, config-files, auth-config, logo | 后台管理 |
| spa | `GET /<path:path>` | 兜底服务 SPA |

### JWT 双 Token 流程

| Token | 存储 | 有效期 | 用途 |
|-------|------|--------|------|
| Access | 前端 Zustand（内存） | 15 分钟 | API 请求 `Authorization: Bearer <token>`，含 `pwd_ver` |
| Refresh | HttpOnly Cookie | 7 天 | `/api/refresh` 换新 access；校验 `pwd_ver`，密码修改后失效 |

### 数据库 Schema（7 张表）

- `conversations`：`id, username, title, model, reasoning_effort, thinking_level, last_response_id, created_at, updated_at`
- `messages`：`id, conversation_id (FK CASCADE), role, content, reasoning, status, created_at`
- `message_attachments`：`id, message_id (FK CASCADE), file_name, file_path, mime_type, kind, parsed_text, created_at`
- `token_usage`：`id, username, conversation_id, message_id, model, provider, input_tokens, output_tokens, created_at`
- `documents`：`id, title, category, file_path, file_name, file_size, mime_type, uploaded_by, created_at, updated_at`
- `audit_logs`：`id, username, action, target_type, target_id, detail, ip_address, created_at`
- `revoked_refresh_jti`：`jti PK, revoked_at, exp_at`

### AI Provider 接入

前端模型 ID：`openai:<name>` / `google:<name>` / `claude:<name>`。

| Provider | SDK | 流式 API |
|----------|-----|---------|
| OpenAI | `openai` | `responses.create()` |
| Google | `google-genai` | `generate_content_stream()` |
| Claude | `anthropic` | `messages.stream()` |

所有文件附件统一由 MarkItDown 解析为 Markdown 文本后以 `type: "text"` 发送，不区分 provider。图片以 base64 data URL 发送。

### 配置分组（`config/env/`）

| 文件 | 关键变量 |
|------|---------|
| `app.env` | `APP_SECRET_KEY`, `JWT_SECRET`, `PORT`, `FLASK_DEBUG`, `FRONTEND_DEV_ORIGIN` |
| `openai.env` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `google.env` | `GOOGLE_BASE_URL`, `GOOGLE_API_KEY` |
| `claude.env` | `CLAUDE_BASE_URL`, `CLAUDE_API_KEY` |
| `storage.env` | `CHAT_DB_FILE`, `UPLOAD_DIR` |
| `attachments.env` | `MAX_UPLOAD_MB`, `MAX_ATTACHMENTS_PER_MESSAGE`, `MAX_TEXT_FILE_CHARS`, `MAX_CONTEXT_MESSAGES` |
| `logging.env` | `LOG_LEVEL`, `LOG_FILE`, `LOG_TO_STDOUT` |

### 测试架构

`tests/conftest.py` 提供：
- `app_builder` fixture：monkeypatch 注入 `_FakeOpenAI`（含 `_FakeFiles`）/ `_FakeGoogleClient` / no-op Claude
- `_AuthedClient`：包装 `test_client`，自动注入 JWT
- `logged_in_client` / `admin_client` fixture

## 协作规范

- 所有面向用户的输出使用**中文**，代码标识符与命令保持原样。
- 提交信息遵循 Conventional Commits：`feat:`, `fix:`, `docs:`, `refactor:` 等。
- 不要将 `config/env/`, `config/users.json`, `data/`, `frontend/node_modules/`, `static/dist/` 提交到 git。
- 新增数据库字段：在 `db.py` 的 `init_db()` 中用 `ALTER TABLE ADD COLUMN` 增量迁移。
- 新增 hot-reloadable env：在 `runtime_state.py` 的 `HOT_RELOADABLE_ENV_KEYS` 白名单中加入。
- 新增 API 统一加 `@require_login` 或 `@require_admin`。
- 前端 API 调用统一通过 `apiFetch` / `apiJson`。
