# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: The main entrypoint that initializes the Flask application using `gtpweb.app_factory`.
- `gtpweb/`: Core application package containing business logic, database interactions, and configuration.
  - `blueprints/`: Flask blueprints for grouping routes (`auth`, `admin`, `conversation`, `chat`, `documents`).
  - `ai_providers.py`: Multi-provider AI model integration (OpenAI, Google Gemini, Anthropic Claude).
  - `db.py`: SQLite database interaction layer (6 tables: conversations / messages / message_attachments / token_usage / documents / audit_logs).
  - `app_factory.py`: Application factory pattern for creating the Flask app instance.
  - `token_tracking.py`: Token usage recording and per-user / per-model aggregation.
  - `audit.py`: Audit log writer + reader for sensitive admin actions.
  - `user_store.py`: User CRUD with `enabled` flag and per-user `api_keys` map.
- `templates/`: Server-rendered HTML pages (`login.html`, `chat.html`, `admin.html`, `tutorial.html`).
- `static/`: Frontend assets (`chat.js`, `login.js`, `admin.js`, `style.css`, `logo.png`).
- `config/`: Configuration files and templates (`models.jsonc`, `users.example.json`, `env.example/`).
- `data/`: Runtime data — SQLite db, uploaded chat attachments, downloadable documents, tutorial markdown.
- `tests/`: Automated test suite (`unit/` and `integration/`).

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: Create and activate the virtual environment.
- `pip install -r requirements.txt -r requirements-dev.txt`: Install backend dependencies, including dev packages.
- `cp -R config/env.example config/env && cp config/users.example.json config/users.json`: Initialize local config.
- `python app.py`: Start the local server on `http://127.0.0.1:8000`.
- `pytest`: Run the test suite.

## Coding Style & Naming Conventions
- Python: Follow PEP 8, 4-space indentation, and add type hints for new/changed functions.
- Flask routes and helper functions: `snake_case`.
- JavaScript: Use `const`/`let`, `camelCase`, and keep DOM IDs descriptive (`conversation-list`, `new-conv-btn`).
- API response shape should remain stable: JSON endpoints use `{ "ok": true/false, ... }`; streaming uses SSE events with `type` (`delta`, `reasoning`, `usage`, `done`, `error`).
- Avoid `innerHTML` with dynamic content in frontend code — use `textContent` and `createElement` to prevent XSS.

## Domain-Specific Patterns
- **Multi-provider streaming**: Each provider has its own stream branch in `chat.py`. When adding a new provider, also extend `ai_providers.py` (PROVIDER_*, message format conversion, delta extraction) and `runtime_state.py` (RuntimeSettings fields, hot-reload key list, client builder).
- **Per-user API keys**: User records may include `api_keys: {openai?, google?, claude?}`. The chat blueprint reads them on each request and creates a temporary client overriding the global one.
- **Hot-reload whitelist**: `runtime_state.HOT_RELOADABLE_ENV_KEYS` controls which env keys can take effect without restart. Adding new credentials/limits here saves a restart cycle.
- **Manual schema migrations**: New columns go through `PRAGMA table_info()` check + `ALTER TABLE ADD COLUMN` in `db.init_db()`. Never re-create tables.
- **Audit logging**: Sensitive admin actions (user CRUD, config save, document management) call `audit.log_audit()` with `action`/`target_type`/`target_id`/`detail`. Always include `request.remote_addr` for IP context.

## Testing Guidelines
- The repository includes a comprehensive test suite under `tests/`.
- Tests use mocked AI clients (`_FakeOpenAI`, `_FakeGoogleClient`, plus a no-op Claude builder). When adding a new provider, extend the mocks in `tests/conftest.py`.
- Pre-PR checks:
  - Run all tests using `pytest`.
  - Ensure all new features or bug fixes include corresponding unit or integration tests.
  - Manual smoke test: login, create/select conversation, send a message, verify streamed output and persisted history after refresh.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history, e.g. `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`.
- Keep commits focused and logically grouped (backend, frontend, docs).
- PRs should include:
  - What changed and why
  - Config/env changes (especially new env files like `claude.env`)
  - Verification steps performed
  - UI screenshots/GIFs for frontend changes

## Security & Configuration Tips
- Never commit secrets or local runtime data (`config/env/`, `config/users.json`, `data/chat.db`, `data/documents/`, `data/uploads/`).
- Treat API base URLs as API roots (commonly ending in `/v1` for OpenAI-compatible; Anthropic uses `https://api.anthropic.com`) and store credentials only in environment variables.
- User passwords are stored in plaintext in `users.json` — keep that file out of version control. If you ever switch to hashed storage, update `verify_user_credentials()` in `user_store.py`.

## Agent Collaboration Rules
- 所有面向用户的输出文字必须使用中文（包含进度更新、最终回复、说明文档、提交说明等），代码标识符与命令保持原样。
- 每次完成修改后都需要自动执行一次 Git 提交，提交信息遵循 Conventional Commit 风格并准确描述本次改动。
