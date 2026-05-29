# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 初始化环境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp -R config/env.example config/env && cp config/users.example.json config/users.json

# 运行
python app.py  # http://127.0.0.1:8000

# 测试
pytest              # 运行全部测试
pytest tests/unit/  # 仅运行单元测试
pytest tests/integration/ -k "test_name"  # 运行单个集成测试
```

无 linter 配置（无 flake8/ruff/black），遵循 PEP 8 即可。

## 架构概览

**Flask 单进程应用**，应用工厂模式，原生 SQLite（无 ORM），SSE 流式 AI 响应，前端为纯 HTML + 原生 JS（无框架、无构建工具）。

### 请求流

```
浏览器 → Blueprint 路由 → 业务逻辑层 → AI Provider (OpenAI/Google/Claude) → SSE 响应流
                              ↓
                         SQLite (db.py) + token_usage 记录
```

### 核心模块职责

| 文件 | 职责 |
|------|------|
| `gtpweb/app_factory.py` | `create_app()` — 加载配置、初始化 DB、注册蓝图、设置三家 AI 客户端工厂 |
| `gtpweb/config.py` | 从 `config/env/*.env` 分组加载配置；`ENV_DIR` / `MODEL_CONFIG_FILE` 可覆盖（测试用） |
| `gtpweb/db.py` | SQLite 初始化 + 手动 schema 迁移（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN`） |
| `gtpweb/runtime_state.py` | 运行时设置热重载；`HOT_RELOADABLE_ENV_KEYS` 白名单控制哪些键无需重启即可更新 |
| `gtpweb/ai_providers.py` | 三家 provider 的模型选项解析、消息格式转换（OpenAI / Google `build_google_contents` / Claude `build_claude_messages`）|
| `gtpweb/openai_stream.py` | 封装 OpenAI Responses API / `chat.completions` SSE，提取文本/推理增量 |
| `gtpweb/blueprints/chat.py` | `/api/chat/stream` — SSE 流式入口，三个 provider 的流式分支处理 |
| `gtpweb/attachments.py` | 附件校验 + 文档解析（docx/xlsx/xls/txt）+ DataURL 编码 |
| `gtpweb/token_tracking.py` | Token 用量记录与查询（按用户 / 按时间范围 / 按模型） |
| `gtpweb/audit.py` | 审计日志记录与查询（管理员关键操作追溯） |
| `gtpweb/user_store.py` | 用户 CRUD，支持 `enabled` 启禁用与每用户 `api_keys` 字段 |

### API 端点速查

| 蓝图 | 路由 | 说明 |
|------|------|------|
| auth | `GET /chat`, `GET /tutorial`, `POST /api/login`, `POST /api/logout` | 认证 + 聊天页 + 教程页 |
| conversation | `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/<id>`, `GET /api/me/usage` | 会话 CRUD + 当前用户用量 |
| chat | `POST /api/chat/stream`, `POST /api/chat/retry/stream` | SSE 流式对话（OpenAI / Google / Claude） |
| documents | `GET /api/documents`, `GET /api/documents/<id>/download`, `POST/PUT/DELETE /api/admin/documents[/<id>]` | 文档下载中心 |
| admin | `GET /admin`, `GET/POST/PATCH/DELETE /api/admin/users[/<username>]`, `GET /api/admin/dashboard`, `GET /api/admin/token-usage`, `GET /api/admin/audit-logs`, `POST /api/admin/config-files/*` | 6 Tab 管理面板（仪表盘/账号/用量/文档/配置/审计） |

### 数据库 Schema（6 张表）

- `conversations`：`id, username, title, model, reasoning_effort, thinking_level, last_response_id, created_at, updated_at`
- `messages`：`id, conversation_id (FK CASCADE), role, content, reasoning, status, created_at`
- `message_attachments`：`id, message_id (FK CASCADE), file_name, file_path, mime_type, kind, parsed_text, created_at`
- `token_usage`：`id, username, conversation_id (FK SET NULL), message_id (FK SET NULL), model, provider, input_tokens, output_tokens, created_at`
- `documents`：`id, title, category, file_path, file_name, file_size, mime_type, uploaded_by, created_at, updated_at`
- `audit_logs`：`id, username, action, target_type, target_id, detail, ip_address, created_at`

### AI Provider 接入

支持三家 provider，前端模型 ID 格式：`openai:gpt-5.5` / `google:gemini-3-pro-preview` / `claude:claude-sonnet-4-20250514`。

| Provider | SDK | 流式 API | Usage 字段位置 |
|----------|-----|---------|----------------|
| OpenAI | `openai` | `responses.create()`（推理模型）/ `chat.completions.create()` | `response.completed` 事件 / 末尾 chunk（需 `stream_options={"include_usage": True}`） |
| Google | `google-genai` | `generate_content_stream()` | 每个 chunk 的 `usage_metadata` |
| Claude | `anthropic` | `messages.stream()` 上下文管理器 | `message_start`（input）+ `message_delta`（output）|

**每用户独立 Key**：用户记录可在 `api_keys` 字段配置 `{openai, google, claude}`，`chat.py` 在请求开始时检查并临时创建覆盖客户端。

### 配置分组（`config/env/`）

| 文件 | 关键变量 |
|------|---------|
| `app.env` | `APP_SECRET_KEY`, `PORT`, `FLASK_DEBUG`, `MAGIC_LOGIN_SECRET` |
| `openai.env` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `google.env` | `GOOGLE_BASE_URL`, `GOOGLE_API_KEY` |
| `claude.env` | `CLAUDE_BASE_URL`, `CLAUDE_API_KEY` |
| `storage.env` | `CHAT_DB_FILE`, `UPLOAD_DIR` |
| `attachments.env` | `MAX_UPLOAD_MB`, `ALLOWED_ATTACHMENT_EXTS` |
| `logging.env` | `LOG_LEVEL`, `LOG_FILE`, `LOG_TO_STDOUT` |

模型定义在 `config/models.jsonc`（JSONC 格式，支持注释）。Claude 模型默认留空，配好 API Key 后通过管理后台「配置管理」Tab 添加即可启用。

### 数据目录

- `data/chat.db`：SQLite 数据库
- `data/uploads/<username>/<conversation_id>/`：聊天附件
- `data/documents/`：文档中心存储的 SOP/通知文档
- `data/tutorial.md`：使用教程内容（Markdown，可在管理后台编辑）

### 测试架构

`tests/conftest.py` 中的 `app_builder` fixture 允许自定义 `ENV_DIR` / `MODEL_CONFIG_FILE` 路径，并通过 monkeypatch 注入伪造的 OpenAI / Google / Claude 客户端，无需真实 API Key 即可做集成测试。新增 provider 时需要在 conftest 中补充对应 mock。

## 协作规范

- 所有面向用户的输出（注释、提交信息、说明文档）使用**中文**，代码标识符与命令保持原样。
- 提交信息遵循 Conventional Commits：`feat:`, `fix:`, `docs:`, `refactor:` 等。
- 不要将 `config/env/`, `config/users.json`, `data/*.db`, `data/documents/`, `data/uploads/` 提交到 git（已在 `.gitignore` 中）。
- 新增数据库字段：在 `db.py` 的 `init_db()` 中用 `ALTER TABLE ADD COLUMN` 增量迁移，不要重建表。
- 新增 hot-reloadable env：在 `runtime_state.py` 的 `HOT_RELOADABLE_ENV_KEYS` 白名单中加入。
