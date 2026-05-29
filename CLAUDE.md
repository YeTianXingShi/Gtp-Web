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
浏览器 → Blueprint 路由 → 业务逻辑层 → AI Provider → SSE 响应流
                              ↓
                         SQLite (db.py)
```

### 核心模块职责

| 文件 | 职责 |
|------|------|
| `gtpweb/app_factory.py` | `create_app()` — 加载配置、初始化 DB、注册蓝图、设置日志和运行时状态 |
| `gtpweb/config.py` | 从 `config/env/*.env` 分组加载配置；`--ENV_DIR` / `--MODEL_CONFIG_FILE` 可覆盖（测试用） |
| `gtpweb/db.py` | SQLite 初始化 + 手动 schema 迁移（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN`） |
| `gtpweb/runtime_state.py` | 运行时设置热重载；`HOT_RELOADABLE_ENV_KEYS` 白名单控制哪些键无需重启即可更新 |
| `gtpweb/blueprints/chat.py` | `/api/chat/stream` — SSE 流式 AI 响应主入口 |
| `gtpweb/openai_stream.py` | 封装 OpenAI Responses API / `chat.completions` SSE，提取文本增量 |
| `gtpweb/ai_providers.py` | OpenAI / Google 客户端工厂，模型选项解析 |
| `gtpweb/attachments.py` | 附件校验 + 文档解析（docx/xlsx/xls/txt）+ DataURL 编码 |

### API 端点速查

| 蓝图 | 路由 | 说明 |
|------|------|------|
| auth | `GET /chat`, `POST /api/login`, `POST /api/logout` | 认证 + 聊天页面 |
| conversation | `GET/POST /api/conversations`, `GET/PATCH/DELETE /api/conversations/<id>` | 会话 CRUD |
| chat | `POST /api/chat/stream`, `POST /api/chat/retry/stream` | SSE 流式对话 |
| admin | `GET /admin`, `POST /api/admin/*` | 管理面板（用户/模型/环境配置） |

### 数据库 Schema（3 张表）

- `conversations`：`id, username, title, model, reasoning_effort, thinking_level, last_response_id, created_at, updated_at`
- `messages`：`id, conversation_id (FK CASCADE), role, content, reasoning, status, created_at`
- `message_attachments`：`id, message_id (FK CASCADE), file_name, file_path, mime_type, kind, parsed_text, created_at`

### 配置分组（`config/env/`）

| 文件 | 关键变量 |
|------|---------|
| `app.env` | `APP_SECRET_KEY`, `PORT`, `FLASK_DEBUG`, `MAGIC_LOGIN_SECRET` |
| `openai.env` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` |
| `google.env` | `GOOGLE_BASE_URL`, `GOOGLE_API_KEY` |
| `storage.env` | `CHAT_DB_FILE`, `UPLOAD_DIR` |
| `attachments.env` | `MAX_UPLOAD_MB`, `ALLOWED_ATTACHMENT_EXTS` |
| `logging.env` | `LOG_LEVEL`, `LOG_FILE`, `LOG_TO_STDOUT` |

模型定义在 `config/models.jsonc`（JSONC 格式，支持注释），前端模型 ID 格式：`openai:gpt-4o-mini` / `google:gemini-2.0-flash`。

### 测试架构

`tests/conftest.py` 中的 `app_builder` fixture 允许自定义 `ENV_DIR` / `MODEL_CONFIG_FILE` 路径，并通过 monkeypatch 注入伪造的 OpenAI/Google 客户端，无需真实 API Key 即可做集成测试。

## 协作规范

- 所有面向用户的输出（注释、提交信息、说明文档）使用**中文**，代码标识符与命令保持原样。
- 提交信息遵循 Conventional Commits：`feat:`, `fix:`, `docs:`, `refactor:` 等。
- 不要将 `config/env/`, `config/users.json`, `data/*.db` 提交到 git（已在 `.gitignore` 中）。
