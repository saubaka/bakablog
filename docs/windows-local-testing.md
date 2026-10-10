# Windows本地测试

Windows只用于Flask开发服务器测试，不作为生产部署环境。项目根目录的`start.bat`是默认启动入口。

## 1. 安全启动方式

直接双击`start.bat`，或在项目根目录的CMD中执行：

```bat
start.bat
```

该脚本只由Windows自带的`cmd.exe`解释，不调用PowerShell，不修改执行策略，不请求管理员权限，不访问网络，也不会自动打开浏览器。它只会执行这些项目内操作：

1. 核对Python版本为3.11–3.14；随附的Windows原生离线wheel推荐使用64位Python 3.14。
2. 缺少`.venv`时创建项目虚拟环境。
3. 缺少运行依赖时，仅从本地`wheelhouse`离线安装。
4. 执行SQLite数据库迁移。
5. 执行Cloudtrace系统检查。
6. 以关闭调试器和自动重载的Flask本地模式监听`127.0.0.1:5010`；占用时自动尝试随后20个端口。

只检查环境、依赖、迁移与应用状态而不启动服务器：

```bat
start.bat --check-only
```

## 2. 首次初始化管理员

若当前SQLite还没有管理员，直接启动网站并在浏览器打开实际地址；首页会自动跳转`/bakaadmin`创建向导。填写用户名、显示名称、至少14位且不包含用户名的密码，以及四位图片验证码。数据库与上传文件保存在项目`instance`目录。

## 3. 访问与停止

启动成功后打开：

- 前台：`http://127.0.0.1:5010/`
- 超级管理员入口：`http://127.0.0.1:5010/bakaadmin`
- 健康检查：`http://127.0.0.1:5010/healthz`

看到`Running on http://127.0.0.1:实际端口`即启动成功。若默认端口被占用，以启动输出的地址为准。按`Ctrl+C`停止。为减少安全风险和重复进程，默认不启用Werkzeug交互调试器与自动重载；修改代码后重新运行`start.bat`即可。

## 4. 地址与端口

默认只绑定本机地址`127.0.0.1`。如需临时修改端口，可先在同一个CMD窗口设置环境变量：

```bat
set CLOUD_DIARY_PORT=5050
start.bat
```

后台站点配置默认允许HTTP。Windows本地测试不要启用强制HTTPS，因为Flask开发服务器没有配置TLS。

若5010端口已占用，脚本会选择随后20个端口中的空闲端口；全部被占用时，再按上例指定其他端口。

## 5. 常见安全提示

- PowerShell执行策略不会影响`.bat`，因此不需要也不应使用`ExecutionPolicy Bypass`。
- 脚本不会关闭Windows Defender、SmartScreen或其他安全软件，也不会添加白名单。
- 若安全软件仍提示风险，应查看提示中的具体检测项目并保留拦截，不要关闭系统保护；本项目脚本可以直接用记事本检查，其内容不包含下载、提权、注册表修改或隐藏执行。
- 如果项目文件是从浏览器下载的压缩包，Windows可能按文件来源显示常规信誉提示；这与PowerShell执行策略不是同一问题。

## 6. 项目测试

```bat
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests
```
