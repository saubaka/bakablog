# 阶段四开发、初始化与运维说明

## 首次安装与初始化

```powershell
.\scripts\bootstrap.ps1
.\scripts\init-site.ps1 -Username admin -DisplayName "站点管理员"
```

第二条命令会执行数据库迁移、同步内置权限，并通过隐藏输入提示设置管理员密码。密码至少需要 12 个字符，项目不会提供默认生产密码。

离线安装仍使用：

```powershell
.\scripts\bootstrap.ps1 -Offline
```

本地 `wheelhouse` 已包含当前 Windows、Python 3.14 环境所需的阶段四依赖。更换 Python 小版本、操作系统或 CPU 架构后，应重新下载匹配的 wheel。

## 开发运行

```powershell
.\scripts\dev.ps1
```

访问 `http://127.0.0.1:5000/bakaadmin`，使用初始化时创建的超级管理员登录。

## 数据库迁移

应用升级后执行：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app db upgrade
```

修改模型并确认属于当前阶段后，开发者可生成迁移：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app db migrate -m "说明"
```

迁移文件必须纳入源码，并经过空实例升级测试。不要使用 `db.create_all()` 替代生产迁移。

## 管理员维护

创建新管理员或安全重置现有管理员密码：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app create-superadmin
```

同步内置权限：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app seed-permissions
```

网站没有访客注册入口，管理员账号只能在拥有服务器本地命令行权限时创建。

## 完整性检查与备份

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:app db-check
.\scripts\backup.ps1
```

备份文件默认写入 `instance/backups/`，同时包含一致的 SQLite 快照、`uploads/` 媒体文件和版本清单。

恢复前停止 Waitress/Gunicorn 与所有后台任务，然后执行：

```powershell
.\scripts\restore.ps1 -Archive "instance\backups\cloud-diary-时间.zip"
```

恢复命令先验证归档路径和数据库完整性，再创建 `pre-restore-safety.zip` 安全副本，然后替换数据库与媒体目录。恢复后应再次运行 `db-check` 并启动应用抽查媒体文件。

## 实例目录迁移

数据库、媒体和备份默认保存在项目 `instance/`。可通过绝对路径放到独立本地磁盘：

```powershell
$env:CLOUD_DIARY_INSTANCE_PATH="D:\cloud-diary-instance"
```

数据库必须位于应用所在单机的本地磁盘，不应放到网络共享盘，也不能由多台应用服务器同时写入。

## 生产启动

```powershell
$env:CLOUD_DIARY_ENV="production"
$env:CLOUD_DIARY_SECRET_KEY="部署专用的长随机密钥"
.\.venv\Scripts\python.exe -m flask --app wsgi:app db upgrade
.\scripts\serve.ps1 -Port 8080
```

生产密钥不可写入源码或提交到版本控制。生产 Cookie 只通过 HTTPS 发送，因此公开部署应配置本机反向代理和有效证书。
