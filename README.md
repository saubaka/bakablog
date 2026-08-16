# sau_bakaの博客（baka blog）

一个浅蓝浅粉浅色系的可爱风个人网站，使用 Python、Flask 和 SQLite 构建。这里可以发布博客手记、展示项目作品、记录生活动态、整理相册，也提供友链、留言簿和覆盖全站内容的搜索，并配有功能完整的单人管理后台。

所有样式、脚本、图标、字体、依赖包都随项目本地提供，不依赖 CDN 或任何强制云服务。

> 本目录是项目的一份全新副本：尚未初始化，没有数据库、管理员账号和任何内容，登录网关（云门）也未接入。按下面的步骤即可从零开始使用。

## 主要功能

- **博客**：可视化文章编辑器、草稿与定时发布、置顶推荐、版本恢复、分类与标签、月度归档、Atom 订阅与站点地图。
- **个人内容**：个人资料与技能、项目作品展示、生活动态、相册瀑布流与灯箱。
- **互动**：友链申请与审核、文章评论、留言簿；公开互动带限流、蜜罐和敏感词防护。
- **全站搜索**：独立的 `/search/` 页面，统一检索文章、项目、动态、友链和留言。
- **管理后台**：单管理员模式，包含仪表盘、内容管理、站点设置、主题外观（字体、页面动画、弹窗样式）、操作日志、备份与恢复。

## 初始化（Windows）

需要 Python 3.12–3.14。

方式一：双击 `start.bat`，自动创建虚拟环境、从本地 `wheelhouse/` 离线安装依赖并完成数据库迁移，然后创建管理员：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app site-init
```

方式二：使用脚本逐步初始化（首次使用需在当前进程临时放开执行策略）：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1 -Offline    # 创建虚拟环境并离线安装依赖
.\scripts\init-site.ps1             # 初始化数据库并创建管理员 admin
.\scripts\dev.ps1                   # 迁移 + 系统检查 + 启动服务
```

创建管理员时按提示输入至少 14 位的密码。完成后访问：

- 前台首页：`http://127.0.0.1:5000/`
- 管理后台：`http://127.0.0.1:5000/admin/login/`
- 健康/就绪探针：`/healthz`、`/readyz`

## 技术说明

- 服务端：Flask 应用工厂 + Blueprint 模块化结构，Jinja2 服务端渲染。
- 数据库：本地 SQLite（WAL、外键、繁忙超时），结构迁移由 Alembic/Flask-Migrate 管理。
- 前端：本地 CSS 与原生 JavaScript 渐进增强，内置细腻的物理动效，并完整支持“减少动态效果”和低性能设备降级。
- 安全：CSRF、登录限流、安全响应头、请求指纹（不记录原始 IP）、数据库与媒体联合备份及恢复前安全副本。

## 部署与更多

- Windows 环境用于本地运行；正式部署目标为 Debian 12 + Gunicorn，配置样例位于 `deploy/`，Linux 启动脚本为 `scripts/serve.sh`。
- 默认允许任意 Host/IP 的 HTTP 访问，需要收紧时在后台“站点 → 安全”中配置；如果误锁导致无法访问，可用 `local-recovery-link` 命令生成本机一次性恢复链接。
- 环境变量样例见 `.env.example` 与 `.env.production.example`。
