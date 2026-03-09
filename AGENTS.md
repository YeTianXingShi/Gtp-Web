# Repository Guidelines

## Project Structure & Module Organization
- `app.py`: Flask backend entrypoint. Handles auth, conversation/message APIs, SQLite persistence, and OpenAI SDK streaming calls.
- `templates/`: Server-rendered pages (`login.html`, `chat.html`).
- `static/`: Frontend assets (`chat.js`, `login.js`, `style.css`).
- `config/`: Configuration templates (`users.example.json`). Keep real `users.json` local only.
- `data/`: Runtime database location (`chat.db`), generated at runtime.
- `.env.example`: Environment variable template for local setup.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: Create and activate the virtual environment.
- `pip install -r requirements.txt`: Install backend dependencies.
- `cp .env.example .env && cp config/users.example.json config/users.json`: Initialize local config.
- `python app.py`: Start local server on `http://127.0.0.1:8000`.
- `python3 -m py_compile app.py`: Quick syntax check before committing.

## Coding Style & Naming Conventions
- Python: follow PEP 8, 4-space indentation, and add type hints for new/changed functions.
- Flask routes and helper functions: `snake_case`.
- JavaScript: use `const`/`let`, `camelCase`, and keep DOM IDs descriptive (`conversation-list`, `new-conv-btn`).
- API response shape should remain stable: JSON endpoints use `{ "ok": true/false, ... }`; streaming uses SSE events with `type` (`delta`, `done`, `error`).

## Testing Guidelines
- Current repository does not include a committed test suite.
- Minimum pre-PR checks:
  - `python3 -m py_compile app.py`
  - Manual smoke test: login, create/select conversation, send a message, verify streamed output and persisted history after refresh.
- If adding tests, place them under `tests/` and use `pytest` with filenames like `test_*.py`.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history, e.g. `feat: ...`, `fix: ...`, `docs: ...`.
- Keep commits focused and logically grouped (backend, frontend, docs).
- PRs should include:
  - What changed and why
  - Config/env changes
  - Verification steps performed
  - UI screenshots/GIFs for frontend changes

## Security & Configuration Tips
- Never commit secrets or local runtime data (`.env`, `config/users.json`, `data/chat.db`).
- Treat `AI_BASE_URL` as API root (commonly ending in `/v1`) and store credentials only in environment variables.
