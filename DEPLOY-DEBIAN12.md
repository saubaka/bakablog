# Debian 12 与其他 Linux 部署教程

本教程对应 baka blog `1.31.1` 和 `bakagate 1.1.0`。默认仓库：

```text
https://github.com/saubaka/bakagateway.git
```

正式结构：

```text
浏览器 → HTTPS 443 → Nginx → 127.0.0.1:动态端口 → Gunicorn → Flask
```

Gunicorn不会监听公网地址。`bakagate`默认尝试本地8080端口；发现占用时自动选择其他端口，保存并展示当前端口，同时重写、检查和重新加载Nginx。

## 1. 支持范围

- Debian 12、Ubuntu及其衍生系统：APT。
- Fedora、RHEL、CentOS Stream、Rocky Linux、AlmaLinux：DNF。
- Arch Linux、Manjaro：Pacman。
- openSUSE Leap/Tumbleweed、SLES：Zypper。
- x86-64或ARM64、glibc、systemd。
- Python 3.11–3.14。发行版默认Python过旧时，需先从该发行版可信软件源安装兼容版本。

Alpine/musl、非systemd系统和其他CPU架构不会被自动部署脚本接受。

## 2. 一键部署脚本

仓库根目录提供`deploy-linux.sh`。首次部署：

```sh
curl -fsSLo deploy-linux.sh https://raw.githubusercontent.com/saubaka/bakagateway/main/deploy-linux.sh
sudo sh deploy-linux.sh
```

脚本会：

1. 检查root权限、Linux发行版和CPU架构。
2. 使用当前发行版包管理器安装Git和CA证书包。
3. 将仓库克隆到`/opt/bakagateway/current`；已有仓库只允许无本地改动的fast-forward更新。
4. 从仓库选择`linux-x64`或`linux-arm64`自包含二进制。
5. 安装`/usr/local/bin/bakagate`，随后进入交互部署。

只安装管理程序而不立即部署：

```sh
sudo sh deploy-linux.sh --manager-only
```

自定义分支、仓库和目录：

```sh
sudo sh deploy-linux.sh \
  --repo https://github.com/saubaka/bakagateway.git \
  --branch main \
  --project-dir /opt/bakagateway/current
```

脚本拒绝HTTP仓库、危险的宽泛系统目录、无效分支以及包含本地改动的已有工作树，不会使用强制重置覆盖服务器文件。

## 3. 手工安装bakagate

发行文件：

```text
dist/bakagate/linux-x64/bakagate
dist/bakagate/linux-arm64/bakagate
```

手工安装：

```sh
sudo install -o root -g root -m 0755 ./bakagate /usr/local/bin/bakagate
cd /opt/bakagateway/current
sudo bakagate --install
```

安装流程会创建`bakablog`系统账户、Python虚拟环境、生产配置、数据库迁移、systemd服务、Nginx配置、日志轮转和定时清理任务。

## 4. 本地端口自动切换

当前端口保存在：

```text
/etc/bakagate/bakagate.conf   LOCAL_PORT=...
/run/bakablog/port            当前启动使用的端口
```

端口范围为1024–65535。系统每次启动`bakablog.service`前，会由`bakagate --prepare-port`执行以下操作：

1. 尝试绑定`127.0.0.1:当前端口`。
2. 若被占用，从下一个端口开始寻找可用端口。
3. 原子更新管理配置、运行时端口文件、Gunicorn启动文件和Nginx upstream。
4. 运行`nginx -t`，通过后重新加载Nginx。
5. 以`bakablog`低权限账户启动Gunicorn。

因此手动启动、重启、开机自启及systemd故障恢复都不会因旧端口被其他程序占用而永久失败。

执行`sudo bakagate`后，面板会显示：

```text
本地端口：127.0.0.1:8080（由 bakablog 使用）
```

服务停止时若端口被其他进程占用，会显示“启动时将自动切换”。机器可读状态：

```sh
bakagate --status-json
```

返回`local_host`、`local_port`和`port_state`。

## 5. 域名和Cloudflare Origin CA证书

在Cloudflare控制台为唯一业务域名创建Origin CA证书，将PEM证书与私钥上传到服务器。运行：

```sh
sudo bakagate --configure-edge
```

管理器验证：

- 精确域名，不接受协议、端口、路径、通配符、IP或单段主机名。
- 证书签发者必须是Cloudflare Origin CA。
- 证书必须覆盖当前域名并至少还有七天有效期。
- 私钥必须完整并与证书公钥匹配。

通过后保存：

```text
/etc/bakagate/tls/cloudflare-origin.pem   0644
/etc/bakagate/tls/cloudflare-origin.key   0600
```

本版本按要求不下载、不检查也不限制Cloudflare IPv4/IPv6网段。Origin CA证书是服务端证书，不是客户端身份证明，因此它本身不能证明请求一定来自Cloudflare；如果服务器443端口对公网开放，知道源站地址的客户端仍可能尝试直接连接，只是普通浏览器不会信任Origin CA证书。需要更严格来源控制时，应另行使用防火墙或Authenticated Origin Pulls。

Nginx仍会拒绝80端口业务页面、未知TLS Host和非配置域名。应用SQLite访问策略也会同步绑定为唯一HTTPS域名。

## 6. 服务与开机自启

```sh
sudo bakagate --start
sudo bakagate --stop
sudo bakagate --restart
sudo bakagate --toggle-startup
sudo bakagate --doctor
```

systemd服务启用`Restart=on-failure`。关闭开机自启不影响当前进程；停止当前服务也不会自动改变开机自启设置。

## 7. 日志保存与清理

日志位于`/var/log/bakablog/`：

- `access.log`、`error.log`：Gunicorn。
- `service.log`：systemd服务输出。
- `nginx-access.log`、`nginx-error.log`：Nginx。

默认每天轮转、单文件最大50MiB、保留14份和14天，并由`bakagate-log-maintenance.timer`每天补充清理。菜单第8项可调整天数、份数和单文件上限。

```sh
sudo bakagate --maintain-logs
```

只清理本服务的已轮转日志，不删除活动日志、数据库、上传或备份。

## 8. 验收

```sh
sudo bakagate --doctor
sudo systemctl status bakablog --no-pager
sudo systemctl status bakagate-log-maintenance.timer --no-pager
sudo nginx -t
sudo bakagate --status-json
```

用状态JSON中的端口执行本机健康检查：

```sh
curl http://127.0.0.1:当前端口/healthz
curl -I https://你的域名/
```

确认`ss -lntp`中的Gunicorn只监听`127.0.0.1`，不得监听`0.0.0.0`或`::`。

## 9. 更新

再次运行：

```sh
sudo sh deploy-linux.sh
```

脚本只执行安全的fast-forward更新；随后`bakagate --install`会保留生产密钥、数据库和日志策略，更新依赖、迁移、服务和代理配置。如果仓库存在本地修改，脚本会停止并要求维护者先处理，不会覆盖。

更新前仍应创建并验证站点备份。真实证书、私钥、生产密钥和Cookie不得提交到仓库。
