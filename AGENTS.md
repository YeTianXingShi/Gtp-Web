# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: The main entrypoint that initializes the Flask application using `gtpweb.app_factory`.
- `gtpweb/`: Core application package containing business logic, database interactions, and configuration.
  - `blueprints/`: Flask blueprints for grouping routes (`auth`, `admin`, `conversation`, `chat`).
  - `ai_providers.py`: Multi-provider AI model integration (OpenAI, Gemini).
  - `db.py`: SQLite database interaction layer.
  - `app_factory.py`: Application factory pattern for creating the Flask app instance.
- `templates/`: Server-rendered HTML pages (`login.html`, `chat.html`, `admin.html`).
- `static/`: Frontend assets (`chat.js`, `login.js`, `admin.js`, `style.css`).
- `config/`: Configuration files and templates (`models.jsonc`, `users.example.json`, `env.example/`).
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
- API response shape should remain stable: JSON endpoints use `{ "ok": true/false, ... }`; streaming uses SSE events with `type` (`delta`, `done`, `error`).

## Testing Guidelines
- The repository includes a comprehensive test suite under `tests/`.
- Pre-PR checks:
  - Run all tests using `pytest`.
  - Ensure all new features or bug fixes include corresponding unit or integration tests.
  - Manual smoke test: login, create/select conversation, send a message, verify streamed output and persisted history after refresh.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history, e.g. `feat: ...`, `fix: ...`, `docs: ...`.
- Keep commits focused and logically grouped (backend, frontend, docs).
- PRs should include:
  - What changed and why
  - Config/env changes
  - Verification steps performed
  - UI screenshots/GIFs for frontend changes

## Security & Configuration Tips
- Never commit secrets or local runtime data (`config/env/`, `config/users.json`, `chat.db`).
- Treat API base URLs as API roots (commonly ending in `/v1`) and store credentials only in environment variables.

## Agent Collaboration Rules
- 所有面向用户的输出文字必须使用中文（包含进度更新、最终回复、说明文档、提交说明等），代码标识符与命令保持原样。
- 每次完成修改后都需要自动执行一次 Git 提交，提交信息遵循 Conventional Commit 风格并准确描述本次改动。
