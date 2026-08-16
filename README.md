# sau_bakaの博客（baka blog）

浅蓝浅粉可爱风个人博客：Flask + Jinja2 + SQLAlchemy + 本地 SQLite，全部依赖本地提供，不使用 CDN。
本目录是一份**全新、未初始化**的完整项目副本。

## 当前状态

- 未初始化：不含虚拟环境、`instance/` 数据库、管理员账号、内容、上传与备份。
- 云门（Cloudgate）未接入：登录网关连接为空，需要时再在后台「云门 → 网关连接」配置。
- 应用版本 `1.30.6`，数据库迁移头 `f8b3c6d1a204`，默认监听 `http://127.0.0.1:5000`。

## 目录说明

| 路径 | 内容 |
| --- | --- |
| `app/` | Flask 应用：前台/后台蓝图、模板、静态资源、服务层 |
| `migrations/` | Alembic 迁移（Stage 4 至 Stage 19） |
| `scripts/` | 初始化、开发、备份、恢复、生产预检脚本 |
| `wheelhouse/` | 离线安装用的全部 wheel 依赖 |
| `deploy/` | nginx / Caddy 生产配置样例 |
| `start.bat` | Windows 纯 CMD 启动入口，不受 PowerShell 执行策略限制 |
| `.env.example` / `.env.production.example` | 环境变量样例 |

## 初始化（Windows）

要求 Python 3.12–3.14。

```powershell
Set-ExecutionPolicy -Scope Process Bypass   # 仅当前进程生效
.\scripts\bootstrap.ps1 -Offline            # 创建 .venv 并从 wheelhouse 离线安装依赖
.\scripts\init-site.ps1                     # 升级数据库并创建首个管理员 admin（交互式输入密码，至少14位）
.\scripts\dev.ps1                           # 迁移 + 系统检查 + 启动开发服务器
```

也可以双击 `start.bat`：自动补建 `.venv`、离线补齐依赖、执行迁移和系统检查后启动服务；
首次使用仍需执行一次 `site-init` 创建管理员：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app site-init
```

- 前台首页：`http://127.0.0.1:5000/`
- 管理员后台：`http://127.0.0.1:5000/admin/login/`
- 健康/就绪探针：`/healthz`、`/readyz`

## 约束与边界

- 依赖只从本地 `wheelhouse/` 离线安装；CSS、JavaScript、图标、字体、媒体全部本地提供。
- Windows 仅用于本地测试；正式部署目标为 Debian 12 + Gunicorn，样例见 `deploy/` 与 `scripts/serve.sh`。
- 默认允许任意 Host/IP 的 HTTP 访问，可在后台「站点 → 安全」收紧；误锁后可用 `local-recovery-link` 命令生成本机一次性恢复链接。
- 本目录不包含测试、文档、运行数据和任何 AI/agent 配置文件。
