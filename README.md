# Gtp-Web MVP

简化版多用户 AI Chat Web：

- 预置账号登录（账号与管理员权限来自 JSON 配置）
- 固定模型列表（服务端配置，前端按来源分组选项）
- 聊天记录持久化在后端 SQLite（按账号隔离）
- 流式输出（SSE）
- 会话搜索（按标题与消息内容）
- 会话删除、导出（JSON/TXT）与重命名
- 支持图片与文件输入（图片 + 常见文本文件 + Word/Excel 解析）
- 内置后台管理（管理员可管理用户与多个配置文件）
- 同时支持 OpenAI/OpenAI 兼容接口 与 Google Gemini 官方 `google-genai` SDK

## 0. 后端结构

- `app.py`: 启动入口（保持 `python app.py` 不变）
- `gtpweb/app_factory.py`: Flask 应用装配
- `gtpweb/blueprints/auth.py`: 认证与登录页面路由
- `gtpweb/blueprints/admin.py`: 后台管理路由
- `gtpweb/blueprints/conversation.py`: 会话管理路由
- `gtpweb/blueprints/chat.py`: 聊天流式路由
- `gtpweb/routes.py`: 路由注册兼容层（薄封装）
- `gtpweb/config.py`: 环境配置与模型/账号加载
- `gtpweb/db.py`: SQLite 连接与建表
- `gtpweb/attachments.py`: 附件校验与文档解析
- `gtpweb/openai_stream.py`: SSE 与 OpenAI 兼容错误解析
- `gtpweb/ai_providers.py`: 多来源模型注册与 Gemini 请求转换
- `gtpweb/utils.py`: 通用工具函数

## 1. 安装

```bash
cd Gtp-Web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置

```bash
cp -R config/env.example config/env
cp config/users.example.json config/users.json
```

然后编辑：

- `config/env/app.env`
  - `APP_SECRET_KEY`: Flask 会话密钥
  - `USERS_FILE`: 用户配置文件路径
  - `PORT`: Web 服务端口
  - `FLASK_DEBUG`: 调试开关
- `config/env/openai.env`
  - `OPENAI_BASE_URL`: OpenAI 或兼容网关 API 根地址，例如 `https://api.openai.com/v1`
  - `OPENAI_API_KEY`: OpenAI 或兼容服务密钥
  - `OPENAI_MODELS`: OpenAI 来源模型列表，逗号分隔
- `config/env/google.env`
  - `GOOGLE_BASE_URL`: Gemini API 根地址；留空时使用官方默认地址
  - `GOOGLE_API_KEY`: Gemini API Key
  - `GOOGLE_MODELS`: Gemini 模型列表，逗号分隔
  - `GOOGLE_INCLUDE_THOUGHTS`: 是否返回 thought summaries（`1/0`）
  - `GOOGLE_THINKING_LEVEL`: Gemini 3 系列优先使用的 thinking 强度，建议 `low/high`（Pro）或 `minimal/low/medium/high`（Flash）
  - `GOOGLE_THINKING_BUDGET`: Gemini 2.5 系列可选的 thinking token 预算；当前项目仅在模型命中 `gemini-2.5*` 时传递，Gemini 3 系列建议留空
  - `GOOGLE_THINKING_MODEL_PATTERNS`: 哪些 Gemini 模型启用 thought summaries，逗号分隔，支持 `*` 通配
- `config/env/storage.env`
  - `CHAT_DB_FILE`: 聊天记录数据库文件路径（默认 `./data/chat.db`）
  - `UPLOAD_DIR`: 附件存储目录（默认 `./data/uploads`）
- `config/env/attachments.env`
  - `MAX_UPLOAD_MB`: 单文件最大大小（默认 `15`）
  - `MAX_ATTACHMENTS_PER_MESSAGE`: 单次消息最大附件数量（默认 `5`）
  - `MAX_TEXT_FILE_CHARS`: 文本类附件最大读取字符数
  - `ALLOWED_ATTACHMENT_EXTS`: 严格白名单扩展名（逗号分隔，未命中直接拒绝）
- `config/env/logging.env`
  - `LOG_LEVEL`: 日志等级（`DEBUG/INFO/WARNING/ERROR`，建议 `DEBUG` 获取完整链路）
  - `LOG_FILE`: 主日志文件路径（默认 `./logs/app.log`，会自动创建目录并轮转）
  - `LOG_MAX_BYTES`: 单日志文件最大字节（默认 `10485760`）
  - `LOG_BACKUP_COUNT`: 日志轮转保留份数（默认 `5`）
  - `LOG_TO_STDOUT`: 是否同时输出到控制台（`1/0`）
- `config/users.json`
  - 预置登录账号、密码和管理员权限
  - 推荐结构：`{"users":[{"username":"admin","password":"...","is_admin":true}]}`

补充说明：

- 已不再读取旧版 `config/env/ai.env` 与 `AI_*` 变量；请统一迁移到 `openai.env` 与 `google.env`。
- 后台管理页现在会将 OpenAI 与 Google Gemini 分成两个独立配置分组展示。
- 会话内部保存的是带来源前缀的模型 ID，例如 `openai:gpt-4o-mini`、`google:gemini-2.0-flash`。
- Gemini thinking 配置建议：
  - 当前如果主要使用 `gemini-3*`，建议保持 `GOOGLE_THINKING_BUDGET=` 为空，重点调 `GOOGLE_THINKING_LEVEL`。
  - 如果使用 `gemini-2.5*`，推荐先从 `GOOGLE_THINKING_BUDGET=-1` 开始；想压延迟或成本时可尝试 `1024`，复杂推理可提高到 `4096` 或更高。
  - `GOOGLE_THINKING_MODEL_PATTERNS` 默认是 `gemini-2.5*,gemini-3*`，只有命中的模型才会开启 thought summaries。

## 3. 启动

```bash
python app.py
```

浏览器访问：`http://127.0.0.1:8000`

## 3.1 自动部署脚本

新增 `deploy.sh`，用于执行以下流程：

- 本地执行 `git push`
- 通过 SSH 连接远程服务器
- 进入配置的项目目录执行 `git pull`
- 执行停止命令
- 覆盖同步本地 `config/env` 与 `config/users.json` 到远程同路径
- 执行启动命令

准备配置文件：

```bash
cp config/deploy.example.env config/deploy.env
```

然后按需修改 `config/deploy.env`：

- `DEPLOY_HOST` / `DEPLOY_PORT` / `DEPLOY_USER` / `DEPLOY_PASSWORD`：远程服务器连接信息
- `REMOTE_DIR`：远程项目目录
- `LOCAL_GIT_BRANCH`：本地要推送的分支
- `REMOTE_GIT_BRANCH`：远程要拉取的分支
- `REMOTE_STOP_CMD`：远程停止命令
- `REMOTE_START_CMD`：远程启动命令
- `SYNC_LOCAL_CONFIG`：是否同步本地配置文件，默认 `1`
- `LOCAL_ENV_DIR` / `LOCAL_USERS_FILE`：本地配置目录与用户文件路径
- `REMOTE_ENV_DIR` / `REMOTE_USERS_FILE`：远程目标路径；默认会落到远程项目目录下同名位置

执行方式：

```bash
bash deploy.sh
```

如需指定其他配置文件：

```bash
bash deploy.sh /path/to/deploy.env
```

说明：

- 如果配置了 `DEPLOY_PASSWORD`，脚本会通过 `sshpass` 进行免交互登录，因此本机需要预先安装 `sshpass`。
- 如果清空 `DEPLOY_PASSWORD`，脚本会退回到 SSH Key 或交互式密码输入方式。
- 默认会在远程执行 `git pull` 和停止命令后，覆盖上传本地 `config/env` 与 `config/users.json`，再执行启动命令。
- `config/deploy.env` 已加入 `.gitignore`，避免将真实服务器密码提交到仓库。

## 4. 测试

```bash
pip install -r requirements-dev.txt
pytest
```

测试目录：

- `tests/unit/`: 纯函数与工具层测试
- `tests/integration/`: 蓝图接口行为测试

## 5. 后台管理

- 管理员账号同样存放在 `config/users.json`，通过 `is_admin: true` 标识。
- 管理员登录后默认进入 `/admin`，可切换编辑 `config/users.json` 与各分组环境配置文件。
- `config/users.json` 保存后立即生效；如果当前管理员在配置中被移除或取消管理员权限，系统会拒绝保存。
- 推荐使用 `config/env/*.env` 分组维护环境变量；系统会按固定分组分别展示与保存。
- 环境变量文件保存后会立即写盘，并自动热更新支持的运行项；结构性配置仍按提示决定是否重启。

## 6. 当前边界

- 账号密码为配置文件明文（MVP 版，建议后续改为哈希）
- 已支持 `.doc/.docx/.xls/.xlsx` 文档解析（`.doc` 为尽力解析，推荐 `.docx`）
- 非白名单扩展名会被后端严格拒绝
- 暂不支持会话归档/标签管理

## 7. 后续可扩展

- 接入 SQLite + 密码哈希
- 增加审计日志与配置变更历史
- 增加导出 PDF/Markdown、批量导出
- 增加更多 AI 来源（Anthropic、Azure OpenAI 等）

## 8. 常见报错排查

- 前端提示 `<!DOCTYPE html>...`：
  - 说明上游返回了 HTML 错误页，不是模型 JSON。
  - OpenAI 兼容来源先检查 `OPENAI_BASE_URL` 是否为网关 API 根地址（通常以 `/v1` 结尾）。
- Gemini 调用失败：
  - 先确认 `GOOGLE_API_KEY` 有效，且模型名称在 `GOOGLE_MODELS` 中配置正确。
  - 如果走代理或网关，再检查 `GOOGLE_BASE_URL` 是否填写正确。
  - 再确认当前 Python 环境已安装 `google-genai`。
- 查看请求追踪日志：
  - 每个请求都有 `rid=<request_id>`，响应头同步返回 `X-Request-ID`。
  - 可按 `rid` 串联排查认证、会话、聊天流与上游调用日志。
  - 日志文案已改为中文，默认按类别分文件输出到 `./logs/`：
    - `app.log`：启动与基础设施日志
    - `request.log`：请求入口/出口与耗时
    - `auth.log`：登录与登出
    - `conversation.log`：会话管理与导出
    - `chat.log`：聊天流式与附件处理
    - `error.log`：全局 `WARNING/ERROR` 汇总
