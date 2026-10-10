# 阶段三开发与运行说明

## 环境要求

- Windows PowerShell。
- 稳定版 Python 3.12、3.13 或 3.14。
- 项目运行不需要 Node.js，也不需要任何 CDN、云存储或外部数据库。

本次验收所在机器只有 Python 3.14.0rc2，因此测试证据来自该候选版本；正式开发和生产部署应优先使用上述范围内的稳定版 Python。

## 创建环境并安装依赖

在项目根目录运行：

```powershell
.\scripts\bootstrap.ps1
```

脚本会创建项目内的 `.venv`，安装锁定的开发依赖，并检查 Flask 路由表。若要完全从本地 `wheelhouse` 安装 Windows 依赖：

```powershell
.\scripts\bootstrap.ps1 -Offline
```

需要更新离线包时，可在联网环境运行：

```powershell
.\scripts\bootstrap.ps1 -DownloadWheels
```

`wheelhouse` 中的二进制 wheel 与 Python 小版本、操作系统和 CPU 架构有关。更换环境后应重新生成与目标环境匹配的本地包。

## 开发启动

```powershell
.\scripts\dev.ps1
```

浏览器访问 `http://127.0.0.1:5000/`。组件展示页位于 `http://127.0.0.1:5000/components/`，后台骨架位于 `http://127.0.0.1:5000/admin/`。

## Windows 生产方式启动

生产模式拒绝默认密钥。先设置仅属于当前部署的长随机密钥，再使用 Waitress：

```powershell
$env:CLOUD_DIARY_SECRET_KEY="请替换为足够长的随机密钥"
.\scripts\serve.ps1 -Port 8080
```

访问 `http://127.0.0.1:8080/`。正式公开部署时，可在本机前置反向代理处理 HTTPS；网站静态资源仍由本项目本地提供。

## 质量检查

```powershell
.\scripts\test.ps1
```

脚本依次执行 Ruff 静态检查、格式检查和 pytest 测试。单独运行测试可使用：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 目录说明

- `app/blueprints/`：前台和后台 Blueprint。
- `app/templates/`：布局、组件、前台、博客、后台和错误模板。
- `app/static/`：本地样式、脚本和 SVG 图标。
- `instance/`：本地数据库、上传、缓存、日志、备份和临时文件目录；真实运行数据不提交。
- `tests/`：应用工厂、路由、响应头和本地资源测试。
- `wheelhouse/`：可选离线 Python 包目录。
