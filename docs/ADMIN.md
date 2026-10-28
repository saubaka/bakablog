# 后台说明（阶段 P3）

后台是同一个前端工程里的第二个入口：Vue 3 SPA，路径 `/admin/…`，由 Flask 把 `frontend/dist/admin.html` 原样交给浏览器（那是一个静态外壳，里面没有任何数据），之后全部通过 `/api/admin/…` 工作。
接口见 [API.md](API.md)，前台见 [FRONTEND.md](FRONTEND.md)，设计取舍见 [PLAN.md](PLAN.md) 第 5 节。

## 跑起来

```bash
cd frontend
npm run build                        # 同时构建 public / admin / preview 三个入口
make -C ../backend serve             # http://127.0.0.1:5300/admin   （首次：日志里有一次性安装口令，在 /admin/setup 创建管理员）
npm run dev                          # http://127.0.0.1:5173/admin   热更新；/api 等代理到 :5300（BLOG_API 可改）
```

浏览器检查**不要对着自己的站点跑**（它们会创建、修改、恢复数据）。用单独的一套数据：

```bash
scripts/qa-instance.sh start         # 建一份示例数据 + 随机密码的管理员（密码在 backend/data-qa/credentials.json，0600，git 忽略，不会打印），gunicorn 跑在 :5310
cd frontend
npm run qa:admin                     # = zsh qa/admin.sh：admin-pages + admin-audit + admin-flows，Chromium 和 WebKit 各一遍
node qa/admin-flows.mjs              # 单跑某一项；BROWSER=webkit 换引擎
scripts/qa-instance.sh reset         # 不要了就删掉
```

## 结构

```
frontend/
  admin.html                 外壳：只有 <div id="app"> 和入口脚本（没有内联任何东西）
  preview.html               “预览”框里的页面（见下）
  src/admin/
    main.ts                  取站点主题 → 检查登录状态 → 路由 → 挂载
    api/client.ts            fetch 的唯一出口：JSON 进出、写操作带 X-CSRF-Token、统一的 AdminError、401 跳登录、CSRF 过期自动换一次
    api/media.ts             上传（带进度）与缩略图地址
    auth.ts router.ts        登录状态；路由表（每个路由有 title，守卫处理“要安装”“要登录”）
    layout/                  Shell（骨架）SideNav（侧栏药丸）TopBar TabBar（手机底栏）CommandPalette（⌘K）
    pages/                   每个后台页一个文件，路由里按需加载（每页一个 chunk）
      home/                  首页配置的模块表单（BlockForm）与模块清单（blocks.ts）
    editor/                  MarkdownEditor（文本域 + 纯函数变换）PreviewPane（服务端渲染）RevisionDrawer linediff textedit CoverPicker
    ui/                      Modal Drawer Menu Field Segmented SwitchField TagInput MediaPicker MediaField IconPicker TableWrap PreviewFrame Spark
                             ConfirmHost/confirm.ts ToastHost/toast.ts sortable.ts（拖拽 + 键盘排序）AdminSprite（后台专用图标）
    css/                     index.css（入口）shell.css（骨架）kit.css（组件）pages.css（各页）—— 都在 @layer 里
  src/preview/               预览框里的小应用：main.ts PreviewApp.vue protocol.ts
```

- **样式**：与前台同一套令牌（`ui/css/tokens base components prose fx`），再加自己的三个文件，类名一律 `adm-` 前缀。`postbuild.mjs` 保证两边**互不渗透**：后台的样式表里不能出现前台的 `.site-header` / `.tabbar`（它们会改写后台元素），前台与预览里不能出现 `.adm-`。
- **没有滚动入场**：后台不做滚动动效（`fx.init('off')`），共用的 `v-fx` 在这里是空指令。动效只有：药丸滑动、抽屉 / 对话框、分组展开。
- **数据只通过 props / 局部状态**，没有全局数据仓库；分类 / 标签 / 系列的列表是个小缓存（`taxonomy.ts`），设置分组是 `settings.ts`。

## 重要的约定

**认证与安全**
- 会话 Cookie `bb_session`（HttpOnly，`Path=/api/admin`）；页面里只有 CSRF 令牌（在内存里，刷新后用 `/auth/me` 取回）。
- 401 → 清掉登录状态、跳 `/admin/login?next=…`（登录框自己的 401 不触发）；403 且 `code: csrf` → 取新令牌重发**一次**。
- CSP 与前台一样严（`script-src 'self'; style-src 'self'`），只多放行 `img-src blob:`（上传预览）和 `frame-src 'self'`（预览框）。整个工程没有内联脚本 / 样式；样式绑定都走 CSSOM（Vue 的 `:style`），不会被 CSP 拦。
- `v-html` 只用在服务端渲染并清洗过的 HTML（编辑器预览、动态正文）和我们自己的图标文件上，`tests/source-rules.test.ts` 里有白名单。

**编辑器**（`editor/MarkdownEditor.vue`）
- 偏离计划的一点：**计划写的是 CodeMirror 6，实际用的是普通文本域 + 纯函数变换**。原因：编辑器要在输入法、撤销、手机键盘上可靠，文本域是最稳的；所有 Markdown 变换（`textedit.ts`）都是 `{value,start,end}` 上的纯函数，有单元测试，写回时用 `execCommand('insertText')` 保住浏览器自己的撤销栈。代价：没有语法高亮和行号。要换成 CodeMirror，只需要替换这一个组件，接口（`v-model`、`insertImages`、`@pick-image` …）不变。
- 预览 = 把文本发给服务端 `POST /markdown/preview`，与发布走同一条流水线，**所见即所得**，连“缺图”的警告都一样。预览里的任务框和可横向滚动的代码块与前台一样补了无障碍标注（`shared/prose.ts`）。
- 自动保存：停顿 10 秒；已有文章写到 `/autosave`（不产生版本），新文章直接存为草稿。再次打开时发现比已保存更新的暂存内容会问你要不要恢复。
- 并发：保存带 `expected_updated_at`，别处改过会返回 409，界面问你要不要覆盖（对方那一版仍在版本历史里）。离开有未保存改动的页面会提示。
- 新建与编辑复用组件，但切换记录时会重置表单、记录 ID、保存基线和计时器；旧记录的迟到请求不能填回新表单。首次保存只替换地址，保留当前编辑器。
- 保存响应按提交时的表单快照合并：仍未变化的字段接受服务端值，提交后继续输入的字段保留，并继续标记为未保存；下一次保存会带新的版本时间。

**预览框**（首页配置、导航与页脚）
- 后台页里放一个 `<iframe src="/admin/preview-frame">`；那个页面（`src/preview/`）用**真正的前台组件**画出页面，内容由后台用 `postMessage` 送进来（只认同源、只认父窗口的消息）。所以：样式与前台完全一致、手机 / 平板 / 桌面宽度真的按宽度排版（不是缩小的桌面图）、未保存的改动也能看到。
- 这是全站**唯一**允许被嵌入的页面：服务端对 `/admin/preview-frame` 单独给 `frame-ancestors 'self'` 与 `X-Frame-Options: SAMEORIGIN`，其他页面仍是 `DENY`；框里的内容整体 `inert`、链接与按钮不响应，只能用鼠标 / 触摸滚动；框本身不在 Tab 顺序里（里面没有可聚焦的东西，键盘用户专注在编辑上，预览只是旁观；框有名字，读屏会说“站点预览（只能看，不能点）”）。
- 首页预览的数据来自 `POST /api/admin/home/preview`（服务端按“访客会看到的样子”解析未保存的布局）。

**排序**（`ui/sortable.ts`）：指针（鼠标 / 触摸 / 笔）拖动；键盘在把手上按 ↑ ↓，并有读屏播报“已移到第 n 位”。松手时会补上最后一次移动（快速甩动不会丢）。

**表格**（`ui/TableWrap.vue`）：窄屏横向滚动，**只有真的在滚动时**才成为键盘停靠点（并带名字），避免多余的 Tab 停靠。

## 页面与前台内容的对应（PLAN 5.2 覆盖表，逐行）

| 前台内容 | 后台入口 | 状态 |
|---|---|---|
| 站点名 / 副标题 / 标志 / 图标 | 外观 · 站点信息 | ✓ 名称、英文名、副标题、描述、Logo、favicon、语言、时区 |
| 顶栏 / 手机底栏 / 页脚导航 | 导航与页脚 | ✓ 三个区域的条目、目标（站内页面 / 独立页面 / 分类 / 标签 / 系列 / 链接 / 动作）、贴纸、排序、显隐，手机底栏最多 5 格；备案号、版权、页脚简介；右侧实时预览 |
| 首页各模块 | 首页配置 | ✓ 5 个模块的顺序、开关、全部文案与数量、精选手选、公告起止时间；右侧实时预览；保存 / 恢复默认 |
| 文章 | 文章 | ✓ 列表（筛选：状态、分类、标签、系列、月份、关键词；排序；表格 / 卡片；行操作；批量）、编辑器（见 PLAN 5.3）、版本历史、预览链接、定时发布 |
| 分类 / 标签 / 系列 | 分类 · 标签 · 系列 | ✓ 名称、别名、描述、贴纸、颜色、排序、封面、连载状态、文章顺序、合并、清理未用标签、删除必须选改归属 |
| 动态 | 动态 | ✓ 发布框（文字、#标签、最多 9 张图可排序并写替代文字、心情、链接卡片抓取、时间、置顶、可见性）、列表筛选（月份 / 标签 / 心情 / 可见性）、行内编辑、批量 |
| 独立页面 | 页面 | ✓ 内容、模板、进顶栏 / 页脚、状态、SEO |
| 图片 | 媒体库 | ✓ 拖拽 / 多选上传（进度、失败重试）、搜索、筛选（类型、未使用、缺替代文字）、详情（替代文字、说明、使用位置、复制、替换、删除二次确认） |
| 主题 / 装饰 / 动效 | 外观 | ✓ 4 套主题预设、胶带 / 涂鸦开关、动效档位、3 套代码高亮 |
| sitemap / robots / OG | SEO | ✓ 标题 / 描述 / 关键词、默认分享图、robots 追加、sitemap 选项、重定向；规范域名只读显示（它由服务器环境变量 `BLOG_SITE_URL` 决定） |
| 404 / 500 文案 | 外观 · 文案 | ✓ |
| 关于卡片 / 社交链接 | 外观 · 作者（首页配置的“关于”里有直达链接） | ✓ 与计划略有出入：作者资料（头像、简介、链接）只在一个地方改，首页的“关于”模块只管标题与正文 |
| 公告条 | 首页配置 · 公告 | ✓ |

系统与其他：仪表盘、回收站（恢复 / 永久删除 / 清空）、访问统计（含总开关）、账号与安全（用户名、密码、TOTP、会话、登录记录）、备份与导入导出（立即备份 / 下载 / 删除 / 从备份或上传的文件恢复 / 自动备份设置 / Markdown 导出与导入）、日志（操作日志 + 登录记录）、系统状态与维护任务按钮、命令面板（⌘K / Ctrl+K）。

## P1 里没做的（诚实清单）

- 首页模块的“仅桌面 / 仅手机”显示。
- 404 记录（访问最多的失效链接一键转重定向）——后端没有记录它，需要先加表和中间件。
- “把页面设为首页的关于来源”。
- TOTP 的二维码：现在给**密钥文本**和一个 `otpauth://` 链接（手机上点一下就能唤起验证器），手动输入密钥所有验证器 App 都支持。
- 导出里的图片是站点保存的最大一档 WebP（原始上传文件站点本来就不保留）。

## 检查

| 检查 | 文件 | 盯什么 |
|---|---|---|
| 单元 | `tests/admin-*.test.ts` | 编辑器变换与版本对比、接口客户端（CSRF、401、错误解析、网络失败）、时间 / 体积格式、排序、侧栏与路由一致、首页模块与服务端词表一致、预览协议、正文无障碍修补、地址里的筛选；`source-rules` 覆盖后台样式的层与导入顺序、`v-html` 白名单 |
| 页面 | `qa/admin-pages.mjs` | 21 个页面 × 6 个宽度：不横向溢出、没有控制台报错 / CSP 违规 / 失败请求；axe-core WCAG 2.1 A / AA 严重与关键问题为 0 |
| 设计与键盘 | `qa/admin-audit.mjs` | 线与阴影（含浮层状态）、4 套主题的文字对比度、每个键盘停靠点的聚焦环（`<main>` 与标题无环）、侧栏药丸（首屏直接落在当前项、一次导航一次移动、无回头） |
| 流程 | `qa/admin-flows.mjs` | 28 条真人操作：登录失败与成功、⌘K、手机底栏与抽屉、写作 → 预览 → 发布 → 公开页可见、保存与版本恢复、10 秒自动保存、批量与回收站、动态、图片上传与替代文字、分类 / 标签 / 系列 / 页面、首页预览框实时变化与保存、键盘与鼠标排序、导航、外观、SEO 与重定向、统计开关、TOTP 全流程、系统任务、日志筛选、导出再导入、重新生成摘要、备份下载与删除、**从备份恢复** |
| 编辑器边界 | `qa/admin-editors.mjs` | 文章与页面的新建目标、延迟 PATCH / 首次 POST、未保存离开提示、迟到加载 / 保存响应、文章冲突重试；只创建和清理该次检查自己的 QA 草稿 |

后端另有 `tests/test_transfer.py`（Markdown 导出 / 导入：属性头方言、往返、Hexo / Hugo、恶意压缩包）与预览页头部的测试。

## 加一个后台页

`pages/Xxx.vue` → `router.ts` 加路由（带 `title`）→ `nav.ts` 加侧栏项（`tests/admin-misc.test.ts` 会检查路由、侧栏、标题三者一致）→ 要写接口形状的话加进 `types.ts`（`docs/api-samples/admin/*.json` 是它的依据）→ `qa/adminlib.mjs` 的 `ADMIN_PAGES` 里登记，让 `admin-pages` / `admin-audit` 自动覆盖。
