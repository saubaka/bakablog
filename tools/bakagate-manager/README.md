# bakagate Linux 部署与服务管理器

`bakagate` 是自包含的 Linux 管理程序，目标服务器无需安装 .NET。它支持 Debian/Ubuntu、Fedora/RHEL 系、Arch 系和 openSUSE/SLES，并要求系统使用 systemd、glibc 和 Python 3.11–3.14。

## 主要功能

- 安装或更新 Python 虚拟环境、数据库迁移、systemd、Nginx 和日志轮转。
- 启动、停止、重启服务并切换开机自启。
- Gunicorn 只监听 `127.0.0.1`。默认尝试 8080；如果端口被占用，会顺序选择其他空闲端口。
- 每次手动启动和系统开机启动前都会重新检查端口，将结果写入 `/etc/bakagate/bakagate.conf` 和 `/run/bakablog/port`，同时更新 Nginx。
- 菜单和 `--status-json` 始终显示当前本地端口及占用状态。
- Nginx 只接受一个严格校验的域名，并使用上传的 Cloudflare Origin CA 证书。
- 只校验 Origin CA 证书本身，不下载或校验 Cloudflare IPv4/IPv6 网段。
- 本地保存服务、Gunicorn 和 Nginx 日志，通过 logrotate 与 systemd timer 定时压缩和清理。

## 构建

```powershell
.\scripts\build-bakagate.ps1
```

生成：

- `dist/bakagate/linux-x64/bakagate`
- `dist/bakagate/linux-arm64/bakagate`

## 命令

```text
sudo bakagate                         打开管理菜单
sudo bakagate --install               安装或更新
sudo bakagate --start
sudo bakagate --stop
sudo bakagate --restart
sudo bakagate --toggle-startup
sudo bakagate --configure-edge        设置域名并导入/更换CA证书
sudo bakagate --maintain-logs
bakagate --doctor
bakagate --status-json
```

`--prepare-port` 是 systemd 使用的内部命令，不需要手工执行。

## 自动部署脚本

项目根目录的 `deploy-linux.sh` 默认从以下仓库部署：

```text
https://github.com/saubaka/bakagateway.git
```

```sh
sudo sh deploy-linux.sh
```

脚本会识别 CPU 架构、安装 Git/CA 基础包、克隆或安全快进更新仓库、安装对应的 `bakagate` 二进制，然后进入安装流程。已有工作树存在本地改动时会停止，不会覆盖。

证书私钥只保存在 `/etc/bakagate/tls/cloudflare-origin.key`，权限为 `0600`。Origin CA 是服务器证书而不是客户端身份证明；按用户要求，本版本不按 Cloudflare 来源网段拦截连接。
