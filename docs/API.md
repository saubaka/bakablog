# API 参考

后端（Flask）只有两类东西：**JSON 接口**（`/api/…`）和 **给浏览器的页面**（HTML 外壳 + 静态资源 + 站点地图）。真实的响应样例在
[`docs/api-samples/`](api-samples/)，由 `backend/scripts/dump_samples.py` 从一个全新的示例站生成，前端就是照它写的。
本文里每个端点都写成 `` `方法 路径` `` 的形式，`backend/tests/test_docs.py` 会核对它和真实的路由一一对应——加了路由不写文档，测试会失败。

## 1. 约定

| 项 | 约定 |
|---|---|
| 格式 | 请求和响应都是 UTF-8 JSON（`Content-Type: application/json`）；成功时直接返回资源，**没有外层信封** |
| 列表 | `{"items": […], "total", "page", "per", "pages"}`；动态用游标：`{"items", "next_cursor"}` |
| 错误 | `{"error": {"code", "message", "fields"?}}`，HTTP 状态码正确：400 格式不对、401 未登录、403 无权限 / CSRF、404 没有、409 冲突、413 太大、415 类型不支持、422 校验失败、429 太频繁 |
| 校验错误 | 422，`fields` 是 `{"字段路径": "一句话"}`，例如 `{"title": "最多 200 个字符", "items.0.target": "不存在"}` |
| 时间 | 一律 ISO 8601 的 UTC，带 `Z`：`2026-10-18T09:30:00Z`；后台编辑令牌 `updated_at` 带微秒。“某天 / 某月”由站点时区（`/api/site` 的 `timezone`）决定 |
| 缓存 | 公开 JSON：`Cache-Control: no-cache` + 弱 `ETag`，带 `If-None-Match` 得到 `304`；后台接口：`no-store`；图片：`public, max-age=31536000, immutable` |
| 图片 | 响应里的图片对象是 `{id, alt, caption, width, height, color, animated, src, srcset, full, variants[]}`；`src` 是 960 宽那档，`color` 是占位底色 |
| 链接 | 响应里的站内地址都是路径（`/blog/slug`）；绝对地址只出现在站点地图和 `seo.canonical` 里 |
| 没有 | 评论、留言、点赞、访客账号——没有对应的表，也没有对应的接口 |

### 公开地址方案

`/` 首页 · `/blog` 列表 · `/blog/{slug}` 文章 · `/category/{slug}` · `/tag/{slug}` · `/series/{slug}` · `/archive` · `/moments` · `/moments/{id}` ·
`/search` · `/{slug}` 独立页面（如 `/about`）· `/sitemap.xml` · `/robots.txt` · `/media/{hash}/{size}.webp` · `/admin…` 后台（其中 `/admin/preview-frame` 是后台“预览”用的页面：唯一允许被同源 iframe 嵌入的页面，样式与前台一致，内容由后台用 `postMessage` 送入）。
独立页面的别名不能占用这些保留词（`blog`、`moments`、`api`、`admin`……见 `app/paths.py`）。

## 2. 登录与 CSRF（后台接口）

1. 首次运行：服务器日志里打印一次性口令 → `` `POST /api/admin/auth/setup` ``（口令 + 用户名 + 密码，可附邮箱）创建唯一的管理员并登录；之后这个接口永远返回 404。
2. 登录：`` `POST /api/admin/auth/login` `` → 设置 Cookie `bb_session`（`HttpOnly`、`SameSite=Lax`、`Path=/api/admin`，生产环境 `Secure`），响应里给出 `csrf_token`。
3. 所有 **POST / PUT / PATCH / DELETE** 必须带请求头 `X-CSRF-Token: <csrf_token>`，且请求的 `Origin` / `Sec-Fetch-Site` 必须是本站；页面刷新后用 `` `GET /api/admin/auth/me` `` 重新取令牌。
4. 登录限速：同一用户名 5 次失败（15 分钟内）或同一网段 20 次失败后 `429` + `Retry-After`；开启二次验证后登录需要 `code`（动态码或一次性恢复码）。

## 3. 公开接口

| 端点 | 说明 | 参数 / 备注 |
|---|---|---|
| `GET /api/health` | 版本、构建号、`site_version`、时间 | 不缓存 |
| `GET /api/site` | 站点名、简介、作者、主题、动效默认值、导航（顶栏 / 手机底栏 / 页脚）、页脚、404 文案、心情词表 | [样例](api-samples/site.json) |
| `GET /api/home` | 首页模块（已启用、按顺序）及各自的数据，一次返回 | 模块：`hero featured latest_posts latest_moments shelf about now notice` · [样例](api-samples/home.json) |
| `GET /api/posts` | 文章列表 | `page per(1–30) category tag series q sort(new/old/views)`；有 `series` 时按系列顺序；有 `q` 时按相关度并带 `snippet` · [样例](api-samples/posts.json) |
| `GET /api/posts/{slug}` | 文章：正文 HTML、目录、上下篇、相关文章、系列导航、SEO | `?preview=<令牌>` 看草稿（`no-store` + `noindex`）；改过别名的旧地址返回 `404` + `code: "moved"` + `location` · [样例](api-samples/post.json) |
| `GET /api/archive` | 按年 / 月分组 | [样例](api-samples/archive.json) |
| `GET /api/taxonomy` | 分类、标签、系列及（公开内容的）篇数，`total_posts` 是全部公开文章数（列表页“全部”标签页用它） | [样例](api-samples/taxonomy.json) |
| `GET /api/moments` | 动态时间线 | `cursor limit(1–30) tag mood month(YYYY-MM)`；首页（无 `cursor`）额外返回 `pinned[]` 和 `meta`（月份、有动态的日子、标签、心情）· [样例](api-samples/moments.json) |
| `GET /api/moments/{moment_id}` | 单条动态（仅链接可见的也能打开，带 `noindex`） | |
| `GET /api/pages/{slug}` | 独立页面 | [样例](api-samples/page.json) |
| `GET /api/search` | 搜索 | `q`（≤100 字）`type(all/post/moment/page)`；≥3 字用全文索引，1–2 字退回标题 / 摘要 / 标签的 LIKE；`snippet` 已转义，命中处是 `<mark>` · [样例](api-samples/search.json) |
| `POST /api/track` | 匿名访问信标（`sendBeacon`，≤512 字节，`{"p": "/blog/x", "r": "来源"}`），永远 `204` | 尊重 `DNT` / `Sec-GPC`、过滤爬虫、不写 Cookie、不存地址（只存 /24 前缀的每日哈希） |

只有 `POST /api/track` 一个公开写入口，`backend/tests/test_security_inventory.py` 会盯着这件事。

## 4. 浏览器页面与静态资源

| 端点 | 说明 |
|---|---|
| `GET /` | 首页外壳 |
| `GET /{path}` | 所有公开页面和 `/admin…`：先查重定向表（301 / 302），再匹配上面的地址方案，返回前端外壳 + 服务端注入的 SEO；找不到时 `404` + 同一个外壳（Vue 画 404 页）|
| `GET /{name}` | 根目录的静态文件（`favicon.ico`、`favicon.svg`、`manifest.webmanifest`…），其余交给上一条 |
| `GET /assets/{filename}` | 前端构建产物（文件名带内容哈希，永久缓存） |
| `GET /media/{media_hash}/{size}.webp` | 图片，`size` ∈ 480 / 960 / 1600，永久缓存 |
| `GET /sitemap.xml` | 站点地图（只含公开内容；动态 / 页面 / 分类标签可在后台开关） |
| `GET /robots.txt` | 允许全站，禁止 `/api/` 与 `/admin`，追加后台配置的规则，指向站点地图 |

**前端外壳的契约**（`frontend/dist/public.html`，没有构建产物时用内置的最小外壳）：

- `<!--bb:head-->` 被替换成 `<title>`、描述、规范链接、Open Graph / Twitter、JSON-LD；
- `<!--bb:data-->` 被替换成 `<script id="bb-data" type="application/json">{"path","kind","status","site","data"}</script>`——首屏数据，Vue 启动时直接用，不再多一次请求；
  `kind` ∈ `home blog post taxonomy archive moments moment page search 404 500`，`data` 与对应的 JSON 接口响应相同；
  列表页（`blog`、`taxonomy`）在 `data` 旁边多一个顶层键 `taxonomy`（= `GET /api/taxonomy`），分类标签页和标签云不用再请求一次；列表页每页 9 篇（地址里写了 `per` 则以它为准），与前台卡片网格的整行数对齐；
- `<!--bb:ssr-->` 被替换成语义化的正文副本（给爬虫、链接预览和没有 JS 的访客）。
- 页面不含任何内联脚本 / 样式，CSP 为 `script-src 'self'; style-src 'self'`（动效只通过 CSSOM 设样式）。

## 5. 后台接口（全部需要登录；写操作还需要 CSRF）

### 账号与安全

| 端点 | 说明 |
|---|---|
| `GET /api/admin/auth/status` | `{setup_required, authenticated}`，不需要登录 |
| `POST /api/admin/auth/setup` | 首次安装（一次性口令），创建管理员并登录 |
| `POST /api/admin/auth/login` | 登录（`username password code?`） |
| `POST /api/admin/auth/logout` | 退出 |
| `GET /api/admin/auth/me` | 当前用户 + CSRF 令牌 · [样例](api-samples/admin/auth-me.json) |
| `PATCH /api/admin/auth/me` | 改用户名（需要密码） |
| `POST /api/admin/auth/password` | 改密码（需要旧密码；其他设备会被登出） |
| `POST /api/admin/auth/totp/begin` | 开始设置二次验证，返回密钥和 `otpauth://` 地址 |
| `POST /api/admin/auth/totp/enable` | 用一次动态码确认并开启，返回 10 个一次性恢复码（只显示这一次） |
| `POST /api/admin/auth/totp/disable` | 关闭（需要密码） |
| `GET /api/admin/auth/sessions` | 登录会话列表（设备、网段、最近活动）· [样例](api-samples/admin/auth-sessions.json) |
| `DELETE /api/admin/auth/sessions/{session_id}` | 让某个会话下线 |
| `POST /api/admin/auth/sessions/revoke-others` | 让其他会话全部下线 |
| `GET /api/admin/auth/logins` | 登录历史 |

### 文章

| 端点 | 说明 |
|---|---|
| `GET /api/admin/posts` | 列表：`status(all/draft/published/scheduled/unlisted/private/trashed) category tag series q from to sort page per`，附各状态的计数 · [样例](api-samples/admin/posts.json) |
| `POST /api/admin/posts` | 新建；字段见 `PostIn`，只改你发送的字段；`tags` 是名字列表（不存在就当场新建） |
| `GET /api/admin/posts/{post_id}` | 全部字段（含 `content_md`、编辑器暂存 `autosave`）· [样例](api-samples/admin/post.json) |
| `PATCH /api/admin/posts/{post_id}` | 修改；可带 `expected_updated_at` 检测别处同时编辑（409）；改别名会自动登记 301 |
| `DELETE /api/admin/posts/{post_id}` | 移入回收站 |
| `POST /api/admin/posts/{post_id}/restore` | 从回收站恢复 |
| `DELETE /api/admin/posts/{post_id}/purge` | 永久删除（必须先在回收站） |
| `POST /api/admin/posts/{post_id}/duplicate` | 复制为草稿 |
| `PUT /api/admin/posts/{post_id}/autosave` | 编辑器停顿时的暂存，不改动文章本身 |
| `POST /api/admin/posts/{post_id}/preview-token` | 7 天有效的预览链接 |
| `GET /api/admin/posts/{post_id}/revisions` | 版本历史（最近 20 个） |
| `GET /api/admin/posts/{post_id}/revisions/{revision_id}` | 某个版本的内容 |
| `POST /api/admin/posts/{post_id}/revisions/{revision_id}/restore` | 恢复到某个版本 |
| `POST /api/admin/posts/batch` | 批量：`publish draft category add_tags remove_tags pin unpin feature unfeature trash restore purge regenerate_summary`（最后一个：把摘要改回“自动截取”，手写的会被替换） |

文章状态：`draft`（草稿）· `published`（已发布；`published_at` 在未来就是“定时”）· `unlisted`（仅链接可见，`noindex`）· `private`（仅管理员）。

### 动态

| 端点 | 说明 |
|---|---|
| `GET /api/admin/moments` | 列表：`visibility tag mood month q trashed page per` |
| `POST /api/admin/moments` | 新建：`text`（`#标签` 自动识别并移出正文，`auto_tags=false` 关闭）`mood tags media[≤9] link_card pinned visibility published_at` |
| `GET /api/admin/moments/{moment_id}` | 读取 |
| `PATCH /api/admin/moments/{moment_id}` | 修改 |
| `DELETE /api/admin/moments/{moment_id}` | 移入回收站 |
| `POST /api/admin/moments/{moment_id}/restore` | 恢复 |
| `DELETE /api/admin/moments/{moment_id}/purge` | 永久删除 |
| `POST /api/admin/moments/{moment_id}/duplicate` | 复制为私密动态 |
| `POST /api/admin/moments/batch` | 批量：`trash restore purge public unlisted private` |
| `POST /api/admin/moments/link-preview` | 粘贴网址：服务端抓取标题 / 描述 / 图标（防 SSRF：只允许 http(s)、公网地址、固定连接、限大小限时）|

### 媒体库

| 端点 | 说明 |
|---|---|
| `POST /api/admin/media` | 上传（`multipart/form-data`，字段 `file`，可附 `alt` `caption`）；一次一个文件；同样的内容返回同一条 |
| `GET /api/admin/media` | 列表：`q kind unused alt(=missing，还没写替代文字的) trashed sort page per` |
| `GET /api/admin/media/{media_id}` | 详情 + 使用位置 |
| `PATCH /api/admin/media/{media_id}` | 改替代文字 / 说明 / 文件名（用到它的内容会重新渲染） |
| `POST /api/admin/media/{media_id}/replace` | 换文件，保持 id 和所有引用 |
| `GET /api/admin/media/{media_id}/usage` | 使用位置列表 |
| `DELETE /api/admin/media/{media_id}` | 移入回收站；仍在使用时要 `?force=1`（否则 409 并列出使用位置） |
| `POST /api/admin/media/{media_id}/restore` | 恢复 |
| `DELETE /api/admin/media/{media_id}/purge` | 永久删除文件（用到它的内容显示“图片缺失”占位） |

上传的处理：校验文件头（只收 JPEG / PNG / GIF / WebP）→ 先读头检查像素数和边长（防图片炸弹）→ 解码 → 应用 EXIF 方向 → 转 sRGB → 去掉全部元数据（含定位）→ 生成 480 / 960 / 1600 三档 WebP（不放大；动图保留动画，≤ 960）→ 以内容哈希命名。

### 整理：分类、标签、系列

| 端点 | 说明 |
|---|---|
| `GET /api/admin/taxonomy/categories` | 分类（含篇数 `count` / 公开篇数 `public_count`） |
| `POST /api/admin/taxonomy/categories` | 新建 |
| `PATCH /api/admin/taxonomy/categories/{category_id}` | 修改（改别名自动 301） |
| `DELETE /api/admin/taxonomy/categories/{category_id}` | 删除；有文章时必须 `?reassign_to=` |
| `POST /api/admin/taxonomy/categories/reorder` | 排序 `{ids}` |
| `GET /api/admin/taxonomy/tags` | 标签（文章数、动态数） |
| `POST /api/admin/taxonomy/tags` | 新建 |
| `PATCH /api/admin/taxonomy/tags/{tag_id}` | 改名 / 颜色 / 贴纸 / 别名 |
| `DELETE /api/admin/taxonomy/tags/{tag_id}` | 删除 |
| `POST /api/admin/taxonomy/tags/merge` | 合并 `{source_ids, target_id}` |
| `POST /api/admin/taxonomy/tags/cleanup` | 删除没人用的标签 |
| `GET /api/admin/taxonomy/series` | 系列 |
| `POST /api/admin/taxonomy/series` | 新建 |
| `PATCH /api/admin/taxonomy/series/{series_id}` | 修改（标题、状态 `ongoing/finished`、封面…） |
| `DELETE /api/admin/taxonomy/series/{series_id}` | 删除（文章保留，只是不再属于系列） |
| `GET /api/admin/taxonomy/series/{series_id}/posts` | 系列里的文章（按顺序） |
| `PUT /api/admin/taxonomy/series/{series_id}/order` | 调整文章顺序 `{post_ids}` |

### 页面、站点配置

| 端点 | 说明 |
|---|---|
| `GET /api/admin/pages` | 页面列表 |
| `POST /api/admin/pages` | 新建（`in_nav` / `in_footer` 开关会同步导航） |
| `GET /api/admin/pages/{page_id}` | 读取 |
| `PATCH /api/admin/pages/{page_id}` | 修改 |
| `DELETE /api/admin/pages/{page_id}` | 移入回收站 |
| `POST /api/admin/pages/{page_id}/restore` | 恢复 |
| `DELETE /api/admin/pages/{page_id}/purge` | 永久删除 |
| `GET /api/admin/pages/{page_id}/revisions` | 版本历史 |
| `GET /api/admin/pages/{page_id}/revisions/{revision_id}` | 某个版本 |
| `POST /api/admin/pages/{page_id}/revisions/{revision_id}/restore` | 恢复 |
| `GET /api/admin/settings` | 全部设置分组（`site author appearance seo footer stats backup`）、默认值、可选项词表 · [样例](api-samples/admin/settings.json) |
| `PATCH /api/admin/settings/{group}` | 修改一个分组（只发要改的字段，按字段深合并；不开放自由取色） |
| `POST /api/admin/settings/{group}/reset` | 恢复默认 |
| `GET /api/admin/home` | 首页模块（没自定义过就是默认布局）· [样例](api-samples/admin/home.json) |
| `PUT /api/admin/home` | 保存整套模块（顺序、开关、配置；每种模块只能出现一次） |
| `POST /api/admin/home/reset` | 恢复默认布局 |
| `POST /api/admin/home/preview` | 预览**还没保存**的布局（返回访客会看到的数据） |
| `GET /api/admin/nav` | 三个区域的导航（没自定义过的区域是默认值）· [样例](api-samples/admin/nav.json) |
| `PUT /api/admin/nav/{region}` | 保存某区域：`top` / `mobile`（最多 5 格）/ `footer` |
| `POST /api/admin/nav/{region}/reset` | 恢复默认 |
| `GET /api/admin/redirects` | 重定向列表（`q sort(new/hits)`） |
| `POST /api/admin/redirects` | 新建（站内路径 → 站内路径或 http(s)；301 / 302；防循环） |
| `PATCH /api/admin/redirects/{redirect_id}` | 修改 |
| `DELETE /api/admin/redirects/{redirect_id}` | 删除 |

### 概览、统计、回收站、日志

| 端点 | 说明 |
|---|---|
| `GET /api/admin/dashboard` | 统计卡、待办（久未动的草稿、即将发布、缺封面 / 摘要 / 替代文字）、最近活动、系统健康 · [样例](api-samples/admin/dashboard.json) |
| `GET /api/admin/stats` | 访问统计 `days=7/30/90`：每日访问、热门文章、来源、设备 · [样例](api-samples/admin/stats.json) |
| `GET /api/admin/trash` | 回收站（文章、动态、页面、媒体；30 天后自动清理） |
| `POST /api/admin/trash/restore` | 恢复一项 `{type, id}` |
| `DELETE /api/admin/trash/{kind}/{item_id}` | 永久删除一项 |
| `DELETE /api/admin/trash` | 清空 |
| `GET /api/admin/audit` | 审计日志（只增不改；`action` 前缀、`target_type`、分页） |

### 系统

| 端点 | 说明 |
|---|---|
| `GET /api/admin/system/status` | 版本、构建、运行时间、数据库 / 媒体 / 备份占用、磁盘、最近备份、任务结果 |
| `GET /api/admin/system/backups` | 备份列表 |
| `POST /api/admin/system/backups` | 立即备份（SQLite 在线备份 + 全部图片，一个 `.tar.gz`） |
| `GET /api/admin/system/backups/{name}/download` | 下载 |
| `DELETE /api/admin/system/backups/{name}` | 删除 |
| `POST /api/admin/system/restore` | 恢复（`{"name","confirm":"restore"}` 或上传 `file`）；在临时副本校验实际结构 / 数据 / 图片并迁移，通过后才做 `pre-restore` 并切换，切换失败回退。返回的 `manifest` 中，新备份另有 `media_sha256` 路径 → 校验和映射；旧备份没有该字段仍可恢复，但须通过数量 / 字节 / 变体检查 |
| `GET /api/admin/system/export` | 整站导出为 Markdown：一个 `.zip`，里面 `posts/ pages/ moments/` 是带 front matter 的 `.md`，`media/` 是用到的图片（站点只保存 WebP，导出其中最大一档）加 `manifest.json`；回收站里的内容不导出 |
| `POST /api/admin/system/import` | 导入 `.zip`（上传 `file`）：本站的导出包，或 Hexo / Hugo / Jekyll 的内容目录（YAML / TOML front matter、相对路径图片）。默认全部进草稿（动态为私密），`status=keep` 时保留文件里的状态；别名重复自动改名，不覆盖已有内容；一个文件出错只跳过它。返回 `{posts, pages, moments, media, skipped, warnings}` |
| `GET /api/admin/system/jobs` | 维护任务及最近一次结果 |
| `POST /api/admin/system/jobs/{name}` | 立即运行：`reindex thumbnails vacuum cache housekeeping trash` |

### 编辑器辅助

| 端点 | 说明 |
|---|---|
| `POST /api/admin/markdown/preview` | 服务端渲染预览——与发布走同一条流水线，所见即所得 |
| `POST /api/admin/utils/slug` | 由标题生成不重复的别名（中文转拼音） |

## 6. Markdown 渲染结果的约定

`posts.content_html` / `pages.content_html` / `moments.content_html` 都是**已清洗**的 HTML，前端直接放进页面，不需要再处理。可能出现的结构：

- 标题 `h2…h4` 带 `id`，目录在 `toc: [{id, text, level}]`；正文里的 `#` 一级标题会整体降一级；
- 提示块 `div.callout.callout--tip|note|warn|love`（`p.callout__title` + 内容）；
- 代码块 `div.code[data-lang] > div.code__bar(span.code__file + button.code__copy) + pre.code-pre > code.language-x`，高亮是 Pygments 的短类名（`k`、`s2`、`nf`…）；
- 图片 `figure.fig[.polaroid] > img(srcset sizes width height loading data-full data-color) + figcaption`；连续的图片 `div.gallery.gallery--2|3|4 > figure.gallery__item`；行内图片 `img.inline-img`；
- 表格包在 `div.table-wrap` 里，对齐是 `ta-left|center|right` 类；任务列表、脚注（`section.footnotes`）、`details`、`kbd`、`mark` 等；
- 站外链接带 `class="ext"`，所有链接带 `rel="noopener noreferrer"`；站外图片不会被加载，会变成 `a.extimg` 并在预览里给出警告。
