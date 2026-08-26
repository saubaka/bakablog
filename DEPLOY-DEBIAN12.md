# Cloudtrace Debian 12与Linux部署教程

本教程对应Cloudtrace `1.31.6`、`bakablog 1.3.2`和仓库：

```text
https://github.com/saubaka/bakablog
```

生产链路：

```text
浏览器 → Cloudflare HTTPS → Nginx 443 → 127.0.0.1:动态端口 → Gunicorn → Flask/SQLite
```

Gunicorn不会监听公网地址。默认尝试8080；如果端口被其他程序占用，管理器会选择下一空闲端口、保存状态、重写Nginx并重新加载，再启动应用。

## 1. 支持范围

- Debian 12、Ubuntu及其衍生系统：APT。
- Fedora、RHEL、CentOS Stream、Rocky Linux、AlmaLinux：DNF。
- Arch Linux、Manjaro：Pacman。
- openSUSE Leap/Tumbleweed、SLES：Zypper。
- x86-64或ARM64、glibc、systemd和Python 3.11–3.14。

Alpine/musl、非systemd系统和其他CPU架构不会被自动脚本接受。

## 2. Cloudflare准备

1. 将域名接入Cloudflare，在DNS中添加指向服务器的记录并按需要开启代理。
2. 在Cloudflare的“SSL/TLS → 源服务器”创建覆盖唯一业务域名的Origin CA PEM证书和私钥。
3. 使用SCP或SFTP把两份文件上传到服务器临时目录，禁止提交到Git。
4. Cloudflare SSL/TLS模式建议设为“完全（严格）”。

本项目只验证上传的Origin CA证书，不下载、检测或限制Cloudflare IPv4/IPv6网段，也不安装Authenticated Origin Pull客户端CA。

## 3. 一键部署

```sh
curl -fsSLo deploy-linux.sh https://raw.githubusercontent.com/saubaka/bakablog/main/deploy-linux.sh
sudo sh deploy-linux.sh
```

默认配置：

```text
仓库：https://github.com/saubaka/bakablog.git
分支：main
目录：/opt/bakablog/current
命令：/usr/local/bin/bakablog
```

脚本会：

1. 校验root权限、HTTPS仓库、分支、目标目录、发行版与CPU架构。
2. 安装Git和CA基础包。
3. 克隆仓库；已有仓库仅允许干净工作树的fast-forward更新，不会hard reset。
4. 选择`linux-x64`或`linux-arm64`自包含二进制。
5. 安装`bakablog`并创建`bakagate`兼容链接。
6. 进入安装流程，安装Python/Nginx/日志依赖、迁移数据库、配置证书、systemd和Nginx。

只安装管理程序：

```sh
sudo sh deploy-linux.sh --manager-only
sudo bakablog
```

自定义部署：

```sh
sudo sh deploy-linux.sh \
  --repo https://github.com/saubaka/bakablog.git \
  --branch main \
  --project-dir /opt/bakablog/current
```

## 4. bakablog管理菜单

```sh
sudo bakablog
```

菜单首页会显示：

- 应用是否安装、运行；
- 开机自启是否启用；
- Nginx状态；
- 当前`127.0.0.1`端口及其占用状态；
- 唯一域名和源站证书有效期；
- Cloudflare来源mTLS状态；
- 项目目录与日志保留策略。

直接命令：

```sh
sudo bakablog --install
sudo bakablog --start
sudo bakablog --stop
sudo bakablog --restart
sudo bakablog --toggle-startup
sudo bakablog --configure-edge
sudo bakablog --maintain-logs
sudo bakablog --doctor
bakablog --status-json
```

## 5. 动态本地端口

当前端口保存在：

```text
/etc/bakagate/bakagate.conf   LOCAL_PORT=...
/run/bakablog/port            当前启动端口
```

每次启动`bakablog.service`前，systemd调用`bakablog --prepare-port`：

1. 尝试绑定当前`127.0.0.1`端口。
2. 若被占用，从下一个端口开始寻找1024–65535范围内的空闲端口。
3. 原子更新管理配置、运行时端口、Gunicorn启动文件和Nginx代理端口。
4. 执行`nginx -t`，通过后重新加载Nginx。
5. 以`bakablog`低权限账户启动Gunicorn。

因此手工启动、重启、开机启动和systemd故障恢复都会重新确认端口，不会因旧端口被占用而永久启动失败。机器可读状态示例：

```json
{"local_host":"127.0.0.1","local_port":8080,"port_state":"service"}
```

## 6. 唯一域名与Origin CA证书

```sh
sudo bakablog --configure-edge
```

输入唯一域名、证书绝对路径和私钥绝对路径。管理器拒绝协议、端口、路径、通配符、IP和单段主机名，并验证：

- 签发者文字为Cloudflare Origin CA；
- 证书覆盖当前域名；
- 至少还有七天有效期；
- 私钥完整并与证书公钥匹配。

通过后保存：

```text
/etc/bakagate/tls/cloudflare-origin.pem  0644 root:root
/etc/bakagate/tls/cloudflare-origin.key  0600 root:root
```

Nginx的80端口直接返回444，未知TLS主机名拒绝握手，业务server只接受配置域名；Flask生产策略也会同步绑定到该HTTPS域名。

Origin CA是服务端证书，不是客户端来源证明。因为本版本按要求不检查Cloudflare网段、也不启用Authenticated Origin Pulls，所以知道源站IP的客户端仍可能构造直连请求；普通浏览器会因不信任Origin CA而报错。

## 7. 持久运行与开机自启

systemd使用`Restart=always`，进程异常或正常退出后都会恢复；`systemctl stop`仍能正常停止。

```sh
sudo bakablog --toggle-startup
systemctl is-enabled bakablog.service
systemctl status bakablog.service --no-pager
```

关闭开机自启不会停止当前进程，停止服务也不会自动更改自启设置。

## 8. 日志保存与清理

日志位于`/var/log/bakablog/`：

- `access.log`、`error.log`：Gunicorn；
- `service.log`：systemd服务；
- `nginx-access.log`、`nginx-error.log`：Nginx。

默认每天轮转，单文件达到50MiB也会轮转，最多保留14份和14天，并压缩旧日志。`bakagate-log-maintenance.timer`每天执行补充清理，`Persistent=true`保证关机期间错过的任务在下次开机补跑。

菜单第8项可调整天数、份数和文件大小。清理只匹配项目已轮转日志，不删除活动日志、SQLite、上传或备份。

## 9. 验收

```sh
sudo bakablog --doctor
sudo systemctl status bakablog.service --no-pager
sudo systemctl status bakagate-log-maintenance.timer --no-pager
sudo nginx -t
bakablog --status-json
```

读取当前端口后检查：

```sh
PORT=$(sudo awk -F= '/^LOCAL_PORT=/{print $2}' /etc/bakagate/bakagate.conf)
curl "http://127.0.0.1:${PORT}/healthz"
sudo ss -lntp | grep "127.0.0.1:${PORT}"
curl -I https://你的域名/
```

Gunicorn不得监听`0.0.0.0`或`::`。

## 10. 更新与排错

再次运行`sudo sh deploy-linux.sh`会安全更新仓库并刷新管理器、依赖、迁移和服务配置，同时保留生产密钥、SQLite实例数据和日志策略。

```sh
sudo bakablog --doctor
sudo journalctl -u bakablog.service -n 100 --no-pager
sudo tail -n 100 /var/log/bakablog/error.log
sudo nginx -T
```

真实证书、私钥、生产密钥、Cookie、数据库和上传内容不得提交到仓库。
