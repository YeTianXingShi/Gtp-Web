# Gtp-Web

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Flask](https://img.shields.io/badge/Framework-Flask-lightgrey?logo=flask)
![React](https://img.shields.io/badge/Frontend-React%2018-61DAFB?logo=react)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite)
![OpenAI](https://img.shields.io/badge/AI-OpenAI-412991?logo=openai)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-8E75B2?logo=googlegemini)
![Claude](https://img.shields.io/badge/AI-Anthropic%20Claude-CC785C)

Gtp-Web 是一个前后端分离的多用户 AI 聊天 Web 平台。支持 OpenAI、Google Gemini、Anthropic Claude 三家 AI 模型，提供流式对话、文件解析、思考强度控制、审计日志等企业级功能。

## 核心特性

- **前后端分离**：React 18 + Vite + TypeScript + Ant Design 前端，Flask API-only 后端
- **三家 AI 模型**：OpenAI（Responses API）、Google Gemini、Anthropic Claude，统一接口
- **JWT 双 Token 鉴权**：Access Token（15 分钟）+ Refresh Token（7 天 HttpOnly Cookie），密码修改后自动失效
- **思考强度控制**：支持 OpenAI Reasoning Effort、Google Thinking Level、Claude Adaptive Thinking，前端可视化切换
- **文件解析**：使用 [MarkItDown](https://github.com/microsoft/markitdown) 将 PDF/Word/Excel/CSV 等文件解析为 Markdown 文本发送给模型
- **流式交互**：基于 SSE 的实时流式输出，支持思考摘要展示
- **每用户独立 API Key**：可为每个用户配置独立的 OpenAI/Google/Claude API Key
- **用户 Profile**：支持自定义字段（工号、姓名、职位等）
- **审计日志**：记录登录、聊天、会话管理、配置修改等操作，支持按用户和动作筛选
- **后台管理**：仪表盘、账号管理、用量统计、文档管理、模型配置（可视化编辑）、配置文件、Logo 管理、审计日志
- **上下文限制**：可配置每次请求加载的最大历史消息数（默认 20 条）

---

## 快速开始

```bash
# 1. 克隆并进入目录
git clone https://github.com/YeTianXingShi/Gtp-Web.git && cd Gtp-Web

# 2. 后端依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 前端构建
cd frontend && pnpm install && pnpm build && cd ..

# 4. 初始化配置
cp -R config/env.example config/env
cp config/users.example.json config/users.json
# 编辑 config/env/*.env 填入 API Key

# 5. 启动
python app.py
```

访问 `http://0.0.0.0:8000` | 默认账号见 `config/users.json`

### 开发模式

```bash
python app.py             # 终端 1：后端 8000
cd frontend && pnpm dev   # 终端 2：前端 5173（Vite proxy 转发 /api/* 到 8000）
```

---

## 配置说明

### 环境变量 (`config/env/*.env`)

| 文件 | 关键变量 | 说明 |
|------|---------|------|
| `app.env` | `APP_SECRET_KEY`, `JWT_SECRET`, `PORT` | 应用密钥与端口 |
| `openai.env` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` | OpenAI / 兼容网关 |
| `google.env` | `GOOGLE_BASE_URL`, `GOOGLE_API_KEY` | Google Gemini |
| `claude.env` | `CLAUDE_BASE_URL`, `CLAUDE_API_KEY` | Anthropic Claude |
| `storage.env` | `CHAT_DB_FILE`, `UPLOAD_DIR` | 数据库与上传路径 |
| `attachments.env` | `MAX_UPLOAD_MB`, `MAX_CONTEXT_MESSAGES` | 上传限制与上下文消息数 |
| `logging.env` | `LOG_LEVEL`, `LOG_TO_STDOUT` | 日志配置 |

### 模型配置 (`config/models.jsonc`)

JSONC 格式，支持注释。可在后台「模型配置」Tab 中可视化编辑。

```jsonc
{
  "openai": {
    "models": [
      {
        "name": "gpt-5.4",
        "label": "GPT-5.4（增强版）",
        "reasoning": {
          "enabled": true,
          "effort": "medium",
          "effort_options": ["low", "medium", "high"],
          "summary": "auto"
        }
      }
    ]
  },
  "claude": {
    "models": [
      {
        "name": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "thinking": {
          "enabled": true,
          "include_thoughts": true,
          "effort": "medium",
          "effort_options": ["low", "medium", "high", "max"]
        }
      }
    ]
  }
}
```

### 用户配置 (`config/users.json`)

```json
{
  "users": [
    {
      "username": "admin",
      "password": "ChangeThis123",
      "is_admin": true,
      "enabled": true,
      "api_keys": {},
      "profile": {"real_name": "管理员"},
      "pwd_ver": 0
    }
  ]
}
```

- `api_keys`：每用户独立 API Key（`openai` / `google` / `claude`），为空则用全局 Key
- `profile`：自定义字段（真实姓名/工号/职位/部门等）
- `pwd_ver`：密码版本号，修改密码时自增，旧会话自动失效

---

## 项目结构

```
frontend/                  # React 前端（Vite + TypeScript + Ant Design）
  src/
    api/                   # API 调用层（apiFetch 自动 JWT + refresh）
    pages/ChatPage/        # 聊天页（Topbar + Sidebar + MessageList + Composer）
    pages/AdminPage/       # 后台（8 个 Tab）
    hooks/                 # 自定义 Hooks（useChatStream 等）
    stores/                # Zustand 状态管理
    components/            # 通用组件（Markdown 渲染、AuthImage 等）

gtpweb/                    # Flask 后端
  blueprints/
    auth.py                # JWT 登录 / refresh / logout
    chat.py                # SSE 流式对话 + 文件解析（MarkItDown）
    conversation.py        # 会话 CRUD + 消息列表 + 附件下载
    admin.py               # 后台管理（用户/配置/用量/审计/Logo）
    bootstrap.py           # SPA 启动数据 + Logo 服务
    documents.py           # 文档下载中心
    spa.py                 # 兜底服务前端 static/dist/
  ai_providers.py          # 三家 Provider 消息格式转换
  openai_stream.py         # OpenAI Responses API 封装
  auth_jwt.py              # JWT 签发/验证/撤销（含 pwd_ver）
  attachments.py           # 附件处理 + 历史消息重建
  config.py                # 配置加载
  db.py                    # SQLite 初始化 + 迁移
  runtime_state.py         # 运行时热更新
  user_store.py            # 用户 CRUD（含 profile / pwd_ver）
  audit.py                 # 审计日志
  token_tracking.py        # Token 用量统计

config/                    # 配置模板
data/                      # 运行时数据（DB / 上传 / 文档）
tests/                     # 测试（unit + integration）
```

---

## 后台管理

管理员登录后可进入 `/admin`：

| Tab | 功能 |
|-----|------|
| 仪表盘 | 会话数、用户数、今日 Token、文档数 |
| 账号管理 | 用户 CRUD、启用/禁用、Profile 编辑、API Key 配置 |
| 用量统计 | 按用户和模型分组的 Token 用量（今日/7天/30天） |
| 文档管理 | 文件上传下载中心 |
| 模型配置 | 可视化编辑模型列表和思考参数 |
| 配置文件 | 在线编辑 .env / .jsonc 配置文件（支持热更新） |
| Logo 管理 | 上传/更换/删除自定义 Logo |
| 审计日志 | 按用户名和动作筛选操作记录 |

---

## 测试

```bash
pip install -r requirements-dev.txt
pytest                              # 后端测试
cd frontend && pnpm typecheck       # 前端类型检查
```

---

## 部署

**同源部署（推荐）**：`pnpm build` → Flask 同时服务 API 与 SPA，单端口。

**Linux 启动脚本**：`bash run_linux.sh`（自动安装依赖 + 构建前端 + 启动服务）

---

## 许可证

MIT License
