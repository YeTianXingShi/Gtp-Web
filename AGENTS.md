# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: Main entrypoint, initializes Flask via `gtpweb.app_factory.create_app()`.
- `gtpweb/`: Core backend package.
  - `blueprints/`: Flask blueprints — `auth`, `admin`, `chat`, `conversation`, `documents`, `bootstrap`, `spa`.
  - `ai_providers.py`: Multi-provider model integration (OpenAI, Google Gemini, Anthropic Claude) — model options, message format conversion.
  - `openai_stream.py`: OpenAI Responses API streaming wrapper.
  - `db.py`: SQLite layer (7 tables: conversations / messages / message_attachments / token_usage / documents / audit_logs / revoked_refresh_jti).
  - `app_factory.py`: Application factory — creates AI clients with `max_retries=0`.
  - `auth_jwt.py`: JWT dual-token system with `pwd_ver` for password-change invalidation.
  - `token_tracking.py`: Token usage recording and aggregation.
  - `audit.py`: Audit log writer + reader (login, chat, conversation, config, logo actions).
  - `user_store.py`: User CRUD with `enabled`, `api_keys`, `profile`, `pwd_ver`.
  - `attachments.py`: Attachment storage + history message reconstruction from DB `parsed_text`.
  - `runtime_state.py`: Hot-reloadable runtime settings (`MAX_CONTEXT_MESSAGES`, etc.).
- `frontend/`: React 18 + Vite + TypeScript + Ant Design SPA.
  - `src/api/`: API client layer with auto JWT injection and 401 refresh replay.
  - `src/pages/ChatPage/`: Chat UI — Topbar, Sidebar, MessageList, Composer.
  - `src/pages/AdminPage/`: 8-tab admin panel — Dashboard, Users, Usage, Documents, Models, Config, Logo, Audit.
  - `src/hooks/useChatStream.ts`: SSE stream manager with throttled setState, onDone/onError callbacks.
  - `src/components/AuthImage.tsx`: JWT-authenticated image loader (blob URL).
- `config/`: Configuration templates (`models.jsonc`, `users.example.json`, `env.example/`).
- `data/`: Runtime data — SQLite db, uploads, documents, logo, tutorial.
- `tests/`: Automated test suite (`unit/` and `integration/`).

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: Create virtual environment.
- `pip install -r requirements.txt -r requirements-dev.txt`: Install dependencies.
- `cd frontend && pnpm install && pnpm build && cd ..`: Build frontend.
- `cp -R config/env.example config/env && cp config/users.example.json config/users.json`: Initialize config.
- `python app.py`: Start server on `0.0.0.0:8000`.
- `pytest`: Run backend tests.
- `cd frontend && pnpm typecheck`: Frontend type check.

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, type hints for new functions.
- Flask routes: `snake_case`.
- Frontend: TypeScript strict, `camelCase`, Ant Design components.
- API response: `{ "ok": true/false, ... }`; SSE events: `type` (`delta`, `reasoning`, `usage`, `done`, `error`).
- All user-facing text in Chinese; code identifiers in English.

## Domain-Specific Patterns
- **File parsing**: All non-image files are parsed to Markdown via MarkItDown at upload time. Parsed text stored in `message_attachments.parsed_text`. All providers receive `type: "text"` — no provider-specific file handling.
- **Per-user API keys**: `api_keys: {openai?, google?, claude?}` in user record. Chat blueprint creates temporary override client per request.
- **Hot-reload**: `HOT_RELOADABLE_ENV_KEYS` in `runtime_state.py`. Adding new keys here enables live config updates.
- **Context limit**: `MAX_CONTEXT_MESSAGES` (default 20) limits history messages sent to AI. Configurable via env, hot-reloadable.
- **Password invalidation**: `pwd_ver` field auto-increments on password change. JWT tokens carry `pwd_ver`; refresh rejects mismatched versions.
- **Audit logging**: `log_audit()` called on login, chat, conversation CRUD, config save, logo update. Actions searchable by username and type.
- **Schema migrations**: `ALTER TABLE ADD COLUMN` in `db.init_db()`. Never re-create tables.
- **Logo**: Custom logo stored at `data/logo.png`, served via `/api/logo` (public, no auth). Falls back to `static/dist/logo.png`.

## Testing Guidelines
- Tests use `_FakeOpenAI` (with `_FakeFiles`), `_FakeGoogleClient`, and no-op Claude builder in `tests/conftest.py`.
- New providers need corresponding mocks.
- Run `pytest` before commits; ensure new features have tests.

## Commit & PR Guidelines
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`.
- Never commit: `config/env/`, `config/users.json`, `data/`, `frontend/node_modules/`, `static/dist/`.

## Agent Collaboration Rules
- 所有面向用户的输出文字使用中文，代码标识符与命令保持原样。
- 每次完成修改后自动执行 Git 提交，提交信息遵循 Conventional Commit 风格。
