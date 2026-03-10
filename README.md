# Gtp-Web MVP

简化版多用户 AI Chat Web：

- 预置账号登录（账号与管理员权限来自 JSON 配置）
- 固定模型列表（服务端配置，前端只可选择）
- 聊天记录持久化在后端 SQLite（按账号隔离）
- 流式输出（SSE）
- 会话搜索（按标题与消息内容）
- 会话删除、导出（JSON/TXT）与重命名
- 支持图片与文件输入（图片 + 常见文本文件 + Word/Excel 解析）
- 内置后台管理（管理员可管理用户与多个配置文件）
- 转发到你预先配置好的 AI 服务（OpenAI 兼容 `chat.completions`）

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
- `gtpweb/openai_stream.py`: SSE 与上游错误解析
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
- `config/env/ai.env`
  - `AI_BASE_URL`: 你的 AI API 根地址，例如 `https://api.openai.com/v1`
  - `AI_API_KEY`: 你的服务密钥
  - `AI_MODELS`: 固定模型列表，逗号分隔
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
- 兼容旧模式
  - 仍支持单文件 `.env`；如需沿用旧方式，可执行 `cp .env.example .env`
- `config/users.json`
  - 预置登录账号、密码和管理员权限
  - 推荐结构：`{"users":[{"username":"admin","password":"...","is_admin":true}]}`

## 3. 启动

```bash
python app.py
```

浏览器访问：`http://127.0.0.1:8000`

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
- 管理员登录后默认进入 `/admin`，可管理用户账号，并切换编辑 `config/users.json` 与环境配置文件。
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

## 8. 常见报错排查

- 前端提示 `<!DOCTYPE html>...`：
  - 说明上游返回了 HTML 错误页，不是模型 JSON。
  - 先检查 `AI_BASE_URL` 是否为网关 API 根地址（通常以 `/v1` 结尾）。
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
