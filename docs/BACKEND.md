# 后端说明（阶段 P1，随 P2 小幅更新）

Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · SQLite（WAL + FTS5）· Pydantic 2 · markdown-it-py · nh3 · Pillow。
接口清单见 [API.md](API.md)，设计取舍见 [PLAN.md](PLAN.md) 第 6 节。

## 跑起来

```bash
cd backend
make venv                      # 用 uv 建 .venv 并装依赖（Python 3.12）
make dev                       # http://127.0.0.1:5000 ，开发模式会自动建库 / 升级；首次运行在终端打印一次性安装口令
make seed OWNER=me PASSWORD='一个足够长的密码'   # 往空站里灌示例内容（文章、动态、图片、页面）和一个管理员
make check                     # ruff + 全部测试（约 560 个，十几秒）
```

没有 `make` 时：`.venv/bin/flask --app app run --debug`、`.venv/bin/python -m pytest`。
生产用 gunicorn：`gunicorn -w 2 --threads 4 wsgi:app`（部署脚本在阶段 P5）；`make serve` 在 http://127.0.0.1:5300 用同样的方式跑，更接近线上。

### 试一试（没有前端也能玩）

```bash
curl -s http://127.0.0.1:5300/api/posts?per=2 | python3 -m json.tool | head -40      # 公开接口，浏览器里直接打开也行
open http://127.0.0.1:5300/                       # 先 `cd frontend && npm run build`（见 FRONTEND.md）才是完整的前台；没有构建产物时是不带样式的语义化 HTML + 完整的 SEO 标签

# 首次安装：开发模式下口令同时写在 backend/data/setup-token.txt（0600；创建管理员后自动删除）
TOKEN=$(cat backend/data/setup-token.txt)
curl -s -c jar.txt -X POST http://127.0.0.1:5300/api/admin/auth/setup -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\",\"username\":\"me\",\"password\":\"一个足够长的密码\"}"     # 响应里有 csrf_token
CSRF=…                                            # 把上一步的 csrf_token 填进来
curl -s -b jar.txt -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' -X POST http://127.0.0.1:5300/api/admin/posts \
  -d '{"title":"第一篇","content_md":"你好，**世界**。","status":"published"}'
```

验收一台正在跑的服务（先核对版本和构建号，再看页面、头部、权限、并发写入）：
`python backend/scripts/live_check.py http://127.0.0.1:5300`（只读）；加 `--owner 用户名 --password 密码 --write` 还会登录并实际写一遍，之后清理。

## 配置（环境变量，前缀 `BLOG_`；开发时可写在 `backend/.env`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `BLOG_ENV` | `development` / `production` / `testing` | `development` |
| `BLOG_SECRET_KEY` | 签名预览链接用；**生产必须设置，≥ 32 个字符** | 开发 / 测试自动生成并保存在 `data/.dev-secret` |
| `BLOG_DATA_DIR` | 数据目录：`blog.sqlite`、`media/`、`backups/` | `backend/data` |
| `BLOG_DB_PATH` | 单独指定数据库文件 | `$DATA_DIR/blog.sqlite` |
| `BLOG_SITE_URL` | 规范域名（`https://…`，无末尾斜杠）；订阅、站点地图、`canonical` 用它 | 空 = 用请求自己的主机名 |
| `BLOG_FRONTEND_DIST` | 前端构建目录（`public.html` / `admin.html` / `assets/`） | `<仓库>/frontend/dist`，不存在就用内置最小外壳 |
| `BLOG_MAX_UPLOAD_MB` | 单张图片上限 | 12 |
| `BLOG_COOKIE_SECURE` | 会话 Cookie 加 `Secure` | 生产默认 true |
| `BLOG_TRUST_PROXY` | 前面有几层反向代理（才会采信 `X-Forwarded-*`） | 0 |
| `BLOG_SETUP_TOKEN` | 预置首次安装口令（给自动化部署用） | 不设则随机生成并打印一次 |
| `BLOG_LOG_LEVEL` | 日志级别 | INFO（测试 WARNING） |
| `BLOG_BUILD` | 构建号（也可由部署脚本写进 `backend/BUILD`） | `dev` |

数据库路径、版本号、构建号都显示在 `GET /api/health` 和后台“系统状态”里——验收时先核对“正在跑的是不是我以为的那一份”。

## 命令

```
flask --app app init-db                  建库 / 升级到最新结构（生产在部署脚本里显式运行）
flask --app app setup-token              （还没有管理员时）重新生成一次性安装口令
flask --app app seed-demo [--owner …]    给空站灌示例内容（仅开发）
flask --app app backup [--label x]       立即备份（部署脚本用 --label pre-deploy）
flask --app app restore 文件 [--yes]     用一份备份替换全部数据（先停服务；先自动留一份 pre-restore；后台打不开时的救命通道）
flask --app app doctor                   自检：配置、数据库版本、目录可写、磁盘、前端三个外壳文件；有问题退出码为 1（部署脚本用它）
flask --app app maintenance [--job x]    维护任务（systemd 定时器每 5 分钟调用，不带 --job 时只在到点时做事）
flask --app app routes-table             列出所有路由
alembic -x db=/路径 upgrade head         手动迁移任意一个库
python scripts/dump_samples.py           重新生成 docs/api-samples/
```

## 结构

```
backend/app/
  __init__.py      应用工厂（配置、数据库、错误、安全头、蓝图、CLI；开发模式自动迁移；打印一次性安装口令）
  config.py  defaults.py  paths.py  version.py  timeutil.py   配置 / 站名与默认文案（唯一一处）/ 公开地址方案 / 版本 / 时间
  db.py            引擎（WAL、外键、busy_timeout）与每请求一个会话；写请求用 BEGIN IMMEDIATE，成功时提交，失败时回滚
  security.py errors.py                                      密码（scrypt）、令牌、地址前缀、安全头 / 统一的错误格式
  models/          24 张表（没有任何评论 / 留言 / 点赞 / 访客账号相关的表）
  schemas/         后台设置与首页模块的校验（Pydantic）
  services/        业务：auth posts moments pages taxonomy media markdown search stats backup trash redirects nav home settings revisions refs …
  api/             蓝图：public、admin_*（每个后台端点都过 @admin_required）、media、health
  seo/             订阅 / 站点地图 / robots，以及前端外壳的 SEO 注入（spa.py）
  jobs/            维护任务
backend/migrations/   Alembic（0001 含 FTS5 虚表和审计日志“只增不改”触发器）
backend/tests/        pytest
```

## 几条值得记住的设计

- **名字只写一处**：站点名、英文名、作者、简介和所有默认文案都在 `app/defaults.py`，运行时由后台设置覆盖；测试会扫描代码，发现别处写了站名就失败。
- **可见性集中在 `services/visibility.py`**：列表、归档、订阅、站点地图、搜索、计数全走这几个条件（`published` 且发布时间已到且不在回收站）；仅链接可见的内容能打开但不进任何列表且 `noindex`；草稿 / 私密只能通过带签名的预览链接看。
- **Markdown 只有一条流水线**（`services/markdown.py`）：保存时渲染并存 HTML；预览接口用同一个函数；nh3 白名单逐项校验标签、属性、取值和 class 名，XSS 用例见 `tests/test_markdown.py`（含 1500 条随机组合）。
- **图片永远不信任**：见 API.md 第 5 节“媒体库”；文件按内容哈希命名，永久缓存；`media_refs` 记录使用位置，替换 / 改替代文字 / 清除时自动重渲染用到它的内容。
- **登录**：首次安装口令 → 唯一管理员；密码 scrypt；会话令牌只存哈希；CSRF 令牌绑定会话；失败记录立即提交（否则失败的请求会把自己的记录回滚掉，限速就失效）。
- **搜索**：FTS5 trigram（中文无需分词）；≥ 3 字走全文，1–2 字退回 LIKE；接口再用真实的可见性条件过滤一次，过期的索引行也泄露不了草稿。
- **备份**：SQLite 在线备份 API + 全部图片 → 一个 `.tar.gz`（带 manifest 和校验和）；恢复前严格校验（只允许预期的文件名、不允许链接 / 路径穿越、校验和、完整性检查、结构版本不能比当前新），实际库版本必须与清单一致，表 / 索引 / 触发器必须符合对应迁移，外键与内容计数也要通过；所有迁移先在临时副本完成，图片数量 / 大小 / 数据库中的变体必须齐全。新备份附每个图片文件的 SHA-256；旧备份继续支持，但仍检查数量、总大小和数据库变体。全部通过后才自动做一份 `pre-restore`，切换失败会恢复切换前的数据库和图片。
- **统计**：无 Cookie、不存地址；独立访客用“每日随机盐 + 地址前缀 + 浏览器”的哈希估算，隔天盐和哈希都删除；`DNT` / `Sec-GPC`、爬虫、后台开关都生效。
- **Markdown 导出 / 导入**（`services/transfer.py`）：导出是一个 zip（`posts/ pages/ moments/` 带 front matter 的 `.md` + `media/` + `manifest.json`）；导入既收本站的导出包，也收 Hexo / Hugo / Jekyll 的内容目录（自带一个小的 YAML 子集解析器，TOML 用标准库；不新增依赖）。压缩包的成员只读进内存、永远不按它自己的路径写盘；限制文件数、总大小、单文件大小和压缩比；每个文件放在一个 SAVEPOINT 里，出错只跳过它。默认全部进草稿（动态为私密）。
- **预览页**：`/admin/preview-frame` 是唯一能被同源 iframe 嵌入的页面（`frame-ancestors 'self'`），后台的 CSP 因此多一条 `frame-src 'self'`，其余页面仍是 `DENY`。
- **链接卡片抓取**（SSRF 防护）：只允许 http(s)；域名解析一次，所有地址都必须是公网地址；连接固定到该地址；每次重定向重新检查；限大小、时间、跳转次数。

## 测试

`make test`：接口、权限、CSRF、同源、路由清单（新增公开路由必须登记）、XSS、上传校验、SSRF、搜索、备份恢复（含恶意压缩包）、迁移、SEO 注入、CLI、文档与路由一致。
每个测试从 Alembic 建好的模板库复制一份，所以迁移本身也在每次测试里被用到。单个测试超过 60 秒会被判失败（防止两个 SQLite 连接互相等待时整个测试卡住）。

## 还没做（按计划放在后面）

- 404 记录（访问最多的失效链接一键转重定向，后台优先级 P1）：需要新表和中间件，没有做；
- 部署脚本、systemd 单元、反向代理示例、备份恢复演练（阶段 P5）；
- 下一次迁移加入时，补一个“旧结构的备份恢复后自动升级”的测试（现在只有一个迁移，没法模拟旧结构）。
