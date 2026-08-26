# bakablog Linux部署与服务管理器

`bakablog`是Cloudtrace的自包含Linux ELF管理程序。目标服务器无需安装.NET，直接运行`sudo bakablog`即可进入中文管理菜单；`bakagate`仅保留为兼容命令。

## 功能

- 支持Debian/Ubuntu、Fedora/RHEL系、Arch系和openSUSE/SLES的systemd主机。
- 安装Python环境、迁移SQLite、生成systemd与Nginx配置。
- Gunicorn只监听`127.0.0.1`，默认端口8080；端口被占用时自动选择下一空闲端口。
- 当前端口写入`/etc/bakagate/bakagate.conf`和`/run/bakablog/port`，并显示在管理菜单和`--status-json`中。
- systemd每次启动前重新检查端口、同步Nginx并执行配置校验，避免旧端口冲突导致服务无法启动。
- 支持服务启动、停止、重启、持久运行和开机自启开关。
- 只校验上传的Cloudflare Origin CA源站证书、域名、有效期和密钥匹配，不下载或检测Cloudflare IP网段，也不启用Authenticated Origin Pulls。
- 本地保存Gunicorn、systemd与Nginx日志，通过logrotate和持久systemd timer定时轮转、压缩和清理。

## 构建

```powershell
.\scripts\build-bakagate.ps1
```

发行文件：

- `dist/bakablog/linux-x64/bakablog`
- `dist/bakablog/linux-arm64/bakablog`

构建脚本还会刷新`dist/bakagate/.../bakagate`兼容副本。

## 命令

```text
sudo bakablog                         打开管理菜单
sudo bakablog --install               安装或更新
sudo bakablog --start                 启动服务
sudo bakablog --stop                  停止服务
sudo bakablog --restart               重启服务
sudo bakablog --toggle-startup        切换开机自启
sudo bakablog --configure-edge        设置唯一域名并导入/更换Origin CA证书
sudo bakablog --maintain-logs         立即清理已轮转日志
sudo bakablog --doctor                检查部署、端口和Nginx
bakablog --status-json                输出当前端口等机器可读状态
```

`--prepare-port`是systemd内部命令。证书私钥只写入`/etc/bakagate/tls/cloudflare-origin.key`并设置为`0600`，不会显示在菜单或日志中。
