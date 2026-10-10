# sau_bakaの博客（baka blog）

一个浅蓝浅粉浅色系的可爱风个人网站，使用 Python、Flask 和 SQLite 构建。这里可以发布博客手记、展示项目作品、记录生活动态、整理相册，也提供友链、留言簿和覆盖全站内容的搜索，并配有功能完整的单人管理后台。

所有样式、脚本、图标、字体、依赖包和数据都随项目本地提供，不依赖 CDN 或任何强制云服务。

## 主要功能

- **博客**：可视化文章编辑器、草稿与定时发布、置顶推荐、版本恢复、分类与标签、月度归档、Atom 订阅与站点地图。
- **个人内容**：个人资料与技能、项目作品展示、生活动态、相册瀑布流与灯箱。
- **互动**：友链申请与审核、文章评论、留言簿；公开互动带限流、蜜罐和敏感词防护。
- **全站搜索**：独立的 `/search/` 页面，统一检索文章、项目、动态、友链和留言，支持严格与自由两种匹配方式，自动防抖与分页。
- **管理后台**：单管理员模式，包含仪表盘、内容管理、站点设置、主题外观（字体、页面动画、弹窗样式）、操作日志、备份与恢复，以及带实时状态的安全更新中心。
- **超级管理员专用入口**：前台不提供登录、注册或普通用户模块；唯一的本地超级管理员从`/bakaadmin`进入后台，凭据和服务端会话保存在本地SQLite。

## 快速开始（Windows）

推荐 64 位 Python 3.14，以匹配随附的 Windows 离线 wheel。直接双击项目根目录的 `start.bat`：

- 只使用 Windows CMD 和本地 Python，不修改执行策略、不提权、不联网下载；
- 首次运行会自动创建虚拟环境，并从本地 `wheelhouse/` 离线安装全部依赖；
- 每次启动前自动执行数据库迁移和系统检查，首选 `http://127.0.0.1:5010/`，端口被占用时打印实际使用的空闲端口。

首次打开脚本打印的地址，会自动进入 `/bakaadmin` 创建管理员向导；创建后再从这个入口登录。站点不提供公开登录、注册或普通用户账号。

只想检查环境而不启动服务时，可运行 `start.bat --check-only`；端口可通过 `CLOUD_DIARY_PORT` 环境变量调整。完整步骤见根目录的 [运行教程](运行教程.md)。

## 快速开始（macOS）

需要macOS 12或更高版本，以及Python 3.11–3.14。项目会单独使用`.venv-macos/`，不会删除或覆盖仓库中现有的Windows`.venv/`、`.bat`、PowerShell脚本和`.exe`文件。

Finder 双击 `run-local.command`，或在终端运行 `./start-macos.sh`。

脚本只监听`127.0.0.1`，首选端口`5010`，占用时自动寻找空闲端口；它会创建macOS专用虚拟环境、安装锁定依赖、执行数据库迁移与系统检查，然后启动本地服务。指定Homebrew Python、端口或只做检查：

```sh
./start-macos.sh --python /opt/homebrew/bin/python3.14 --port 5050
./start-macos.sh --check-only
```

`--offline`只使用`wheelhouse/`；如果仓库尚未包含当前macOS架构和Python版本需要的原生wheel，脚本会明确失败，不会偷偷联网。普通模式允许`pip`从配置的软件源补齐macOS依赖。

首次运行请打开脚本输出的实际地址，按页面向导创建管理员。详细的本机运行与停止步骤见 [运行教程](运行教程.md)。

## 技术说明

- 服务端：Flask 应用工厂 + Blueprint 模块化结构，Jinja2 服务端渲染。
- 数据库：本地 SQLite（WAL、外键、繁忙超时），结构迁移由 Alembic/Flask-Migrate 管理。
- 前端：本地 CSS 与原生 JavaScript 渐进增强，内置细腻的物理动效，并完整支持“减少动态效果”和低性能设备降级。
- 安全：CSRF、登录限流、安全响应头、请求指纹（不记录原始 IP）、数据库与媒体联合备份及恢复前安全副本。

## 部署

Debian 12仍是推荐的公网生产目标。`deploy-linux.sh`默认从`https://github.com/saubaka/bakablog.git`克隆或更新项目，并安装自包含的`bakablog`二进制管理器。管理器负责systemd持久运行与开机自启、日志轮转和定时清理、唯一域名、Cloudflare Origin CA证书、只监听`127.0.0.1`的动态本地端口，以及更新包复核、备份、迁移、健康检查和失败回退；端口占用时会自动切换并同步Nginx。完整步骤见`docs/phase-9/deployment-linux.md`。

macOS现在提供独立的`deploy-macos.sh`。它以当前登录用户安装，不使用`sudo`，把持久数据、私密环境文件和日志分别放在`~/Library/Application Support/BakaBlog/`与`~/Library/Logs/BakaBlog/`，通过`launchd`在登录后持久运行，并始终只让Gunicorn监听`127.0.0.1`。正式模式要求一个HTTPS域名并需要Caddy、Nginx或Cloudflare Tunnel完成TLS反向代理：

```sh
./deploy-macos.sh --local --site-url https://blog.example.com
./scripts/manage-macos.sh status
./scripts/manage-macos.sh doctor
```

从GitHub部署到默认macOS应用目录时，省略`--local`即可。完整的首次安装、反向代理、启动管理、日志、更新和回退边界见`docs/phase-9/deployment-macos.md`。Windows入口及兼容文件继续保留，Windows仍定位为本地运行与测试环境。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `app/` | Flask 应用：前台/后台蓝图、模板、静态资源与服务层 |
| `migrations/` | 数据库迁移 |
| `scripts/` | 初始化、开发、备份、恢复与生产预检脚本 |
| `start-macos.sh` | macOS本地启动与检查入口，使用独立`.venv-macos/` |
| `run-local.command` | macOS Finder 双击启动入口 |
| `运行教程.md` | 本目录个人版的本机一键运行步骤 |
| `deploy-macos.sh` | macOS HTTPS生产配置与LaunchAgent部署入口 |
| `wheelhouse/` | 离线安装用的本地 wheel 依赖 |
| `tests/` | 自动化测试（`pytest`） |
| `docs/` | 规划与设计记录 |
| `instance/` | 运行数据：数据库、上传、备份与日志（运行时生成） |
