# Cloudtrace macOS部署教程

本教程对应baka blog `1.36.5`。macOS适配不会删除或替换仓库中的Windows启动器、PowerShell脚本、`.exe`管理器或Windows虚拟环境；macOS始终使用单独的`.venv-macos/`。

## 1. 两种运行方式

本机查看、开发和验收使用：

```sh
./start-macos.sh
```

该入口首选监听`127.0.0.1:5010`，占用时自动改用随后20个端口中的空闲端口；使用development配置，不应直接暴露到局域网或互联网。

需要登录后自动启动、独立持久数据目录和HTTPS反向代理时使用：

```sh
./deploy-macos.sh --local --site-url https://blog.example.com
```

生产链路为：

```text
浏览器 → HTTPS反向代理或Cloudflare Tunnel → 127.0.0.1:8080 → Gunicorn → Flask/SQLite
```

Gunicorn固定监听回环地址。`CLOUD_DIARY_SITE_URL`必须是443端口上的单一HTTPS origin；脚本不会在没有TLS边界时把production服务直接暴露出去。

## 2. 系统要求

- macOS 12或更高版本，Apple Silicon或Intel处理器。
- Python 3.11–3.14；推荐使用Homebrew Python。
- 系统自带`launchctl`、`curl`，以及Git/Xcode Command Line Tools。
- 公网部署另需Caddy、Nginx或Cloudflare Tunnel之一负责TLS。

系统自带的旧版Python不满足要求时，可安装：

```sh
brew install python@3.14 git
```

也可以通过`--python /绝对路径/python3`指定已有解释器。脚本不使用`sudo`，也不会自动安装Homebrew或修改系统Python。

## 3. 本机快速启动

```sh
chmod +x start-macos.sh deploy-macos.sh scripts/macos-run.sh scripts/manage-macos.sh
./start-macos.sh
```

也可在Finder双击项目根目录的`run-local.command`。首次启动会创建`.venv-macos/`、安装`requirements.txt`、执行`flask db upgrade`与`system-check`，随后在终端打印实际访问地址；浏览器需手动打开该地址。常用选项：

```sh
./start-macos.sh --port 5050
./start-macos.sh --python /opt/homebrew/bin/python3.14
./start-macos.sh --check-only
./start-macos.sh --offline
```

离线模式严格只读取`wheelhouse/`。原生依赖必须同时匹配macOS架构和Python版本；缺少兼容wheel时脚本会停止，普通模式才允许`pip`访问已配置的软件源。

如果终端继承了`ALL_PROXY=socks5h://...`，但该Python环境尚未安装PySocks，`pip`可能提示`Missing dependencies for SOCKS support`。可以先为该Python安装PySocks，或只在这一次依赖安装命令中取消代理变量后重试；不要修改ChatGPT/Codex已经验证可用的代理配置。本项目的回环健康检查会自动绕过全局代理，避免把`127.0.0.1`请求错误发送到代理服务器。

首次打开网站时，若没有管理员，首页会自动跳转`/bakaadmin`创建向导。直接在浏览器完成初始化，无需先执行命令行建号。

## 4. LaunchAgent部署

直接使用当前检出目录：

```sh
./deploy-macos.sh \
  --local \
  --site-url https://blog.example.com \
  --port 8080
```

从官方仓库部署到默认应用目录：

```sh
./deploy-macos.sh --site-url https://blog.example.com
```

远程模式默认使用：

```text
仓库：https://github.com/saubaka/bakablog.git
代码：~/Library/Application Support/BakaBlog/current
数据：~/Library/Application Support/BakaBlog/instance
配置：~/Library/Application Support/BakaBlog/config/production.env
日志：~/Library/Logs/BakaBlog
服务：~/Library/LaunchAgents/com.saubaka.bakablog.plist
```

已有远程检出必须保持干净，更新只允许fast-forward；脚本不会`reset --hard`。现有数据库升级前会建立站点备份，然后执行迁移、绑定唯一HTTPS域名和完整系统检查。私密环境文件权限为`0600`，持久数据目录不放在Git检出中。

只做无写入预检：

```sh
./deploy-macos.sh \
  --local \
  --check-only \
  --site-url https://blog.example.com
```

安装但暂不加载LaunchAgent：

```sh
./deploy-macos.sh --local --site-url https://blog.example.com --no-start
```

## 5. HTTPS反向代理

`deploy-macos.sh`只管理应用进程，不自动修改Homebrew或系统级代理配置。以Caddy为例，代理目标必须与部署端口一致：

```caddyfile
blog.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080 {
        header_up Host blog.example.com
        header_up X-Forwarded-Host blog.example.com
        header_up X-Forwarded-Proto https
    }
}
```

如果使用Cloudflare Tunnel，同样把origin指向`http://127.0.0.1:8080`，并保留原始Host与HTTPS转发头。不要让Gunicorn监听`0.0.0.0`或`::`。

## 6. 启动、状态与日志

```sh
./scripts/manage-macos.sh start
./scripts/manage-macos.sh stop
./scripts/manage-macos.sh restart
./scripts/manage-macos.sh status
./scripts/manage-macos.sh doctor
./scripts/manage-macos.sh logs
```

LaunchAgent在当前用户登录后加载。`KeepAlive`只在进程异常退出时恢复服务；主动停止后需要再次执行`start`。`doctor`会运行依赖检查、应用系统检查，并在服务已启动时通过带可信转发头的回环请求验证`/healthz`。

## 7. 更新、备份与回退边界

macOS没有使用Linux专属的root二进制管理器和systemd请求监听器。后台仍可检查及下载经过URL、大小和SHA-256验证的更新包，但不要在macOS上依赖后台“安装/回退”按钮完成特权代码切换。

推荐更新方式是再次运行相同部署命令。远程模式会拒绝脏工作树，只执行fast-forward更新；迁移前会调用`site-backup`。手工备份和验证：

```sh
CONFIG="$HOME/Library/Application Support/BakaBlog/config/production.env"
BAKABLOG_MACOS_CONFIG="$CONFIG" ./scripts/manage-macos.sh doctor
```

站点备份保存在实例目录的`backups/`。需要回退时，应先停止LaunchAgent，切回经过验证的旧代码，再用`flask site-restore 备份文件 --yes`恢复对应数据；不要只回退数据库或只替换代码。

## 8. 验收清单

```sh
plutil -lint "$HOME/Library/LaunchAgents/com.saubaka.bakablog.plist"
./scripts/manage-macos.sh status
./scripts/manage-macos.sh doctor
lsof -nP -iTCP:8080 -sTCP:LISTEN
curl -I https://blog.example.com/
```

确认监听地址是`127.0.0.1`，公网入口为HTTPS，数据与配置没有提交到Git。macOS睡眠期间服务会暂停处理请求；需要持续公网在线的站点仍推荐部署在Debian 12服务器。
