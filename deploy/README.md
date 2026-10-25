# 部署（阶段 P5）

目标：一台 Debian 12 的小机器，nginx（或 OpenResty）在前面收 https，gunicorn 在 `127.0.0.1:8080` 跑 Flask，数据是一个 SQLite 文件加一个图片目录。
**更新是一条命令，失败会自己回滚，备份能被证明可以恢复。**

## 这里有什么

| 文件 | 作用 |
|---|---|
| `deploy.sh` | 在你的 Mac 上运行：测试 → 构建 → 打包 → 上传 → 在服务器上安装 → 从外面再看一遍 |
| `remote-update.sh` | 在服务器上运行（`deploy.sh` 会上传并启动它）：备份、停、换代码、迁移、自检、启动、检查、**失败自动回滚** |
| `rollback.sh` | 手动退回上一版（`--data` 连数据一起退回部署前的备份） |
| `restore-drill.sh` | 恢复演练：把备份恢复到一个临时副本里，对照清单检查，不碰线上数据 |
| `rehearse.sh` | 在本机的临时目录里完整排练：首次安装、更新、停服务失败及四种发布失败、恢复演练（不需要服务器） |
| `bakablog.service` | systemd 单元（gunicorn，带沙箱：只能写数据目录） |
| `bakablog-maintenance.service` / `.timer` | 每 5 分钟跑一次维护任务（到点才做事：每日备份、每日清理、定时发布的维护） |
| `production.env.example` | 环境文件模板（`/etc/bakablog/production.env`，root，0600） |
| `nginx-site.conf.example` | 反向代理示例（压缩、真实 IP 与协议、上传大小） |

## 服务器上的样子

```
/opt/bakablog/
  current/      当前版本：backend/ frontend/dist/ deploy/ docs/ RELEASE（root:bakablog，目录 750 / 文件 640）
  previous/     上一版（手动回滚用）
  venv          指向 venvs/<依赖哈希> 的符号链接（Python 环境不能搬家，所以每份依赖各有自己的目录；切换 = 改链接，回滚 = 改回去）
  venvs/        Python 3.12 环境，每份 requirements.txt 一个（依赖变了才新建，在旁边进行，不影响正在跑的站点；保留最近两个）
  python/ tools/  uv 管理的解释器、uv 本身
/var/lib/bakablog/        数据：blog.sqlite  media/  backups/（bakablog:bakablog，750）
/etc/bakablog/production.env   环境变量（root，0600）
```

## 第一次

1. **准备机器**（一次）：Debian 12，能 `ssh HOST` 用密钥登录（root，或有免密 sudo 的用户）。
   ```bash
   apt install -y nginx rsync curl python3 python3-venv gawk
   ```
   域名解析到这台机器；防火墙放行 80 / 443；`certbot` 或你自己的方式拿证书。
2. **nginx**：把 `nginx-site.conf.example` 复制到 `/etc/nginx/sites-available/bakablog`，改域名和证书路径，链接到 `sites-enabled/`，`nginx -t && systemctl reload nginx`。
3. **第一次部署**：
   ```bash
   deploy/deploy.sh HOST --url https://你的域名
   ```
   脚本会在服务器上建 `bakablog` 账号、目录、Python 环境、systemd 单元，并生成 `/etc/bakablog/production.env`（带随机密钥）后**停下来**让你改：至少 `BLOG_SITE_URL=https://你的域名`。改完再跑一次同样的命令。
4. **创建管理员**：一次性口令是部署脚本生成并写进 `/etc/bakablog/production.env` 的 `BLOG_SETUP_TOKEN`（只有 root 能读：`sudo grep BLOG_SETUP_TOKEN /etc/bakablog/production.env`；它不会出现在部署输出或日志里）。打开 `https://你的域名/admin/setup`，口令 + 用户名 + 密码。之后这个页面永久关闭，那一行可以删掉。**口令和密码不要发给任何人（包括聊天）**。
5. 开启二次验证（后台 → 账号与安全），并**下载一份备份放在别处**（后台 → 备份与迁移）。

### 放在 1Panel 的 OpenResty 和 Cloudflare 后面时的注意点

如果 80 / 443 由 1Panel 管理的 OpenResty 容器（host 网络）占着：`/opt/1panel/www/conf.d/` 里的每个 `.conf` 都会被它加载，容器是 host 网络，所以代理地址 `http://127.0.0.1:8080` 就是宿主机上的应用。可以照 `openresty-blog.saubaka.com.conf.example` 手写一个站点配置（它不会出现在 1Panel 的“网站”列表里；想在界面里管理，就在 1Panel 里建同样设置的反向代理网站）。改配置前先备份 `conf.d`，`nginx -t` 通过后再热重载。要点：

- **Cloudflare 的 SSL 模式是“Flexible”时**，Cloudflare 是用 http 连到源站 80 端口的：这个站点**不能**做 http→https 跳转（会死循环），并且要始终告诉应用 `X-Forwarded-Proto: https`（对外的访问在 Cloudflare 边缘确实都是 https）。用 Full / Full (strict) 时，在源站配证书并按常规做跳转。
- **访客地址**：Cloudflare 的 `CF-Connecting-IP` 只在连接确实来自 Cloudflare 的地址段时才被采信（`set_real_ip_from` + `real_ip_header`；直接访问源站并伪造这个头不会生效）。没有这个，登录限速和访问统计会把所有人当成同一个 Cloudflare 地址。Cloudflare 的地址段偶尔会变，[这里](https://www.cloudflare.com/ips/)有最新列表。
- 全局的 `client_max_body_size 50m` 够图片上传；后台“用上传的备份恢复 / 导入压缩包”需要更大，示例配置里已对 `/api/admin/system/` 单独放大到 2g。
- 面板自带的 WAF 可能误拦含特殊内容（`<script>`、SQL 关键字、`../`）的文章保存请求；遇到时到 WAF 设置里给这个域名放行。
- 让 Cloudflare 到源站这一段也加密（给源站申请证书，Cloudflare 改成 Full (strict)，再把 80 改成跳转）是更稳妥的做法。

## 以后每次更新

```bash
deploy/deploy.sh HOST --url https://你的域名
```

`deploy.sh` 会：跑后端和前端的全部检查 → `npm run build`（含体积预算与 CSP 检查）→ 打包（没有数据、没有密钥、没有 `._*` 文件、没有 `.venv`；包里出现 AI 工具的名字或署名行会直接拒绝）→ 上传 → `remote-update.sh`：

1. 解包到暂存目录，清掉 macOS 的 `._*`（alembic 会把它们当迁移去 import），检查包完整、新代码能 import；
2. 需要时在旁边建新的 Python 环境，并预编译字节码（服务账号对代码树只读，不预编译的话每次启动——包括定时的维护任务——都要把整个框架从源码编译一遍，约 5 秒 CPU）；
3. 用**正在跑的这一版自己的备份**做一份 `pre-deploy` 备份（SQLite 在线备份 + 全部图片，校验过完整性），记下数据库版本；
4. 停服务（失败立即退出，不切换代码、环境或数据库）→ 换代码 → `init-db`（迁移）→ `doctor`（自检）→ 启动；
5. 检查：`/api/health` 的版本和构建号就是这一版、9 个地址都 200、首页有 `#app` 且没有没填的 `<!--bb:…-->`、后台壳带资源、响应带 CSP；
6. **任何一步失败**：停 → 代码（和 Python 环境）退回上一版 → 如果迁移已经开始，数据退回部署前的备份 → 启动 → 再确认能回答 → 报错退出。

回滚时如果也无法停服务，会停止自动恢复并报错，保留当前代码和数据，要求先人工停服务再恢复。

退出码从不被吞（没有 `cmd | tail`，没有对关键命令加 `|| true`）。

## 手动退回、恢复、演练

```bash
sudo bash /opt/bakablog/current/deploy/rollback.sh            # 只退代码（数据保留部署后新写的）
sudo bash /opt/bakablog/current/deploy/rollback.sh --data     # 数据也退回部署前（部署后写的会丢；新版改过数据库结构时用）
sudo bash /opt/bakablog/current/deploy/restore-drill.sh       # 演练：把最新备份恢复到临时副本并核对（不碰线上）
```

**灾难恢复**（后台打不开了）：先 `systemctl stop bakablog`，然后
```bash
set -a; . /etc/bakablog/production.env; set +a
cd /opt/bakablog/current/backend
sudo -E -u bakablog /opt/bakablog/venv/bin/flask --app app restore /var/lib/bakablog/backups/<文件>.tar.gz --yes
systemctl start bakablog
```
恢复会先校验（文件名白名单、不允许链接和路径穿越、校验和、完整性检查、数据库结构不能比程序新），再自动留一份 `pre-restore` 备份，所以可以反悔。
备份文件在数据目录里，**请定期把 `/var/lib/bakablog/backups/` 同步到别的机器或对象存储**（同一块盘上的备份挡不住坏盘）。

## 排练（建议每次改动这些脚本之后都跑一遍）

```bash
deploy/rehearse.sh
```

在 `$TMPDIR` 里建一个假的“服务器”，用**真的** `remote-update.sh`（`systemctl` 换成一个启停真 gunicorn 的替身）走完：不完整的包被拒绝 → 首次安装（环境文件只生成一次）→ 正常更新（不重装包、留下备份和上一版）→ 代码 import 失败（站点没被动过）→ 迁移改了表结构又失败（代码和数据都回到部署前）→ 服务能起但页面不对（回滚）→ 换了依赖的更新与它的失败回滚 → 恢复演练。它**不能**证明的：systemd 的沙箱设置在真机上是否过严、nginx 配置、证书、防火墙——这些要在第一次真部署时看。

## 排错

```bash
journalctl -u bakablog -n 100 --no-pager        # 应用日志（gunicorn 的访问和错误日志也在里面）
journalctl -u bakablog-maintenance -n 50        # 维护任务
systemctl list-timers bakablog-maintenance.timer
sudo -E -u bakablog …/flask --app app doctor    # 自检：配置、数据库版本、目录可写、磁盘、前端文件
curl -s -H 'X-Forwarded-Proto: https' http://127.0.0.1:8080/api/health
```

踩过的坑（来自上一个项目，已写进脚本）：macOS 的 `tar` 会带上 `._*` 文件（用 `COPYFILE_DISABLE=1` 并在服务器上再删一遍）；迁移和自检要在“root 读环境文件 + `runuser --preserve-environment`”下跑；检查命令不要接管道（会吞退出码）；替换数据库之前先看两边的内容；暂存的数据库副本用完要删。

## 安全备忘

- 服务以 `bakablog` 账号运行，systemd 沙箱：`ProtectSystem=strict`（只有 `/var/lib/bakablog` 可写）、`NoNewPrivileges`、`PrivateTmp`、`PrivateDevices`、空的能力集、只允许 unix / IPv4 / IPv6 套接字。
- 环境文件 `0600 root`；密钥只用来给预览链接签名。生产环境没有 `BLOG_SECRET_KEY` / `BLOG_SITE_URL` 会**拒绝启动**。
- 应用自己发 CSP / HSTS / 防嵌入 / Referrer-Policy 等头；代理不要再加一套（会冲突）。
- 登录有限速和临时锁定，所有写接口校验 CSRF 与同源；后台的会话 Cookie `HttpOnly; Secure; SameSite=Lax; Path=/api/admin`。
