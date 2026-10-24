# 前台说明（阶段 P2）

Vue 3.5 · Vue Router 4 · Vite 7 · TypeScript 5.9（`vue-tsc` 严格检查）· Vitest · Playwright（Chromium + WebKit）。
后端的接口和外壳契约见 [API.md](API.md)，设计取舍见 [PLAN.md](PLAN.md)，原型见 `design/`。后台前端是同一个工程里的第二个入口，见 [ADMIN.md](ADMIN.md)。

## 跑起来

```bash
cd frontend
npm install                 # 所有依赖都是精确版本（.npmrc: save-exact）
npm run build               # 类型检查 → vite build（public / admin / preview 三个入口）→ scripts/postbuild.mjs → frontend/dist/
                            #   Flask 在启动时找 frontend/dist/public.html；有了它，所有公开地址都由 Vue 接管
make -C ../backend serve    # http://127.0.0.1:5300 （改了 dist 后要重启一次，之后每次构建会被自动读到）
npm run dev                 # Vite 开发服务器 http://127.0.0.1:5173，/api /media /feed … 代理到 :5300；热更新
```

检查：

```bash
npm run check               # vue-tsc + ESLint + Vitest（187 个单元测试，不需要服务器）
npm run qa                  # 浏览器检查，Chromium + WebKit 各一遍；需要服务器在 :5300 且有示例内容（flask --app app seed-demo）
npm run qa:webkit           # 只跑 WebKit（Safari 引擎）
BB_URL=http://127.0.0.1:5300 BROWSER=webkit node qa/fx.mjs     # 单跑某一项
npm run shots -- /tmp/out all 390,768,1280                      # 全页截图（动效关闭）：qa/shots.mjs
```

## 结构

```
frontend/
  public.html               Vite 入口 = 服务端要填的外壳：三个标记（<!--bb:head--> <!--bb:data--> <!--bb:ssr-->）各出现一次
  admin.html preview.html   后台的两个入口（见 ADMIN.md）；三个入口共用 vendor / common 两个 chunk，样式表各用各的
  vite.config.ts            构建（vendor 单独成块）、开发代理、没有扩展名的地址回退到 public.html
  scripts/postbuild.mjs     boot.js 压缩并加内容哈希；校验标记；校验 CSP（没有内联脚本 / 样式 / 事件）；体积预算；前台不能引到后台代码，前台与后台的样式表互不渗透
  src/
    ui/css/                 tokens base components layout pages fx（一个 @layer 顺序，没有任何层外的规则）
    ui/sprite.svg           手绘图标 / 涂鸦 / 心情贴纸（i-* d-* mood-*）
    ui/components/          Icon Doodle Mood Sprite NavLink（只管长相，不认识业务）
    fx/                     滚动动效：math（纯函数）text（分词）engine（引擎）directive（v-fx）FxText Phrase domsplit
    shared/                 types（接口形状）api（fetch 与错误）format（日期，按站点时区）cover（生成封面）clipboard
    public/
      boot.js               <head> 里的第一个脚本：主题 / 代码主题 / 装饰开关 / 动效档位 / 两个“先藏起来”的保护类
      main.ts               读首屏数据 → 引擎初始化 → 路由 → 挂载
      router.ts data.ts     路由表；每次导航先把数据取回来（见下），再换页面
      state.ts head.ts      站点设置与当前页面的状态；每次导航后更新 title / description / canonical / robots
      layout/               顶栏 底栏 抽屉 页脚（只有版权 / 备案号一行）搜索浮层 回到顶部
      components/           卡片 列表行 分页 动态气泡 正文容器（ProseView）目录 阅读进度 灯箱 …
      pages/                Home（home/ 下是各个模块）PostList Post Archive Moments MomentPage PageView Search NotFound ErrorPage
  tests/                    Vitest（happy-dom）
  qa/                       Playwright 检查（见下）
```

## 数据怎么来的

1. **首屏**：服务端把外壳里的 `<!--bb:data-->` 换成 `{"path","kind","status","site","data"}`（列表页还有 `taxonomy`），`main.ts` 读完就删掉这个节点。首屏**不再多发一次请求**。
2. **之后每次导航**：路由守卫 `beforeResolve` 调 `loadRoute()`，按路由请求对应的 JSON 接口，**取回来之后才切换页面**——页面组件渲染时数据一定在，没有“加载中”状态。超过 140 ms 顶上出现一条细线。
3. 页面组件只从 **props**（`route.meta.state`）读数据，不读全局状态：页面切换有 100 ms 淡出，淡出期间旧页面不能被新数据“重画”成别的类型。
4. 只改 `#片段`（目录跳转）不重新取数据；过时的请求会被 `AbortController` 取消。换页的滚动（回到顶部、返回时恢复位置）一律是**瞬时**的（`behavior: 'instant'`，不听 `html { scroll-behavior: smooth }`）：只有 `#片段` 才滑动。否则在 WebKit 里，刚进文章就按返回，上一次“滑到顶部”的动画会在位置恢复之后继续，把列表拖回顶端（P3 复验时发现的真问题）。
5. 改过别名的旧地址：接口返回 `404 + code: "moved" + location`，前端 `replace` 到新地址；没有的地址显示 404 页（同时 HTTP 状态本来就是 404）。
6. 统计信标只在**新路径**时发（`POST /api/track`），目录跳转、筛选、翻页不算一次访问；开发服务器不发。

站点设置（`/api/site`）随首屏一起来，整个会话里不变；改了设置后访客刷新即可。

## 滚动到边缘翻页（`src/public/pull.ts`）

在一个菜单页的**最底部**继续往下滚（滚轮 / 触控板 / 手指上滑），会进入菜单里的**下一项**；在**最顶部**继续往上滚，进入**上一项**。第一项的顶部、最后一项的底部不做；不在菜单里的页面（搜索、404）没有这个功能；文章、分类页、单条动态算它们所属的菜单项（文章属于“博客”）。顺序用的是当前形态下菜单的顺序（宽屏用顶栏，手机和平板用底栏，动作和外链跳过）。

- **物理**：页面和页脚一起跟着推（`.page-stage` 的 `translate`），像拉橡皮筋：一开始 1:1，越拉越慢，最多约 120 px（`shared/spring.ts` 的 `rubber`）。推得不够就松手：弹簧弹回去，保留手的速度，最多一点点过冲。推够了（约 140 px，触屏 112 px，或快速一甩）：页面被抛出屏幕，下一页在它离开视线时已经换好（推到三成时就提前请求了它的数据：`router.ts` 的 `warmRoute`），从另一侧升上来，落定时带一点点弹性。所有运动都是弹簧（`stepSpring`，固定小步长积分，和帧率无关），没有固定时长。
- **菜单联动**：推的时候菜单里的爱心珠向目标项倾斜（`--pull-nav`），松手弹回；换页后爱心照常滑到新位置。**屏幕上没有任何提示卡片**（2026-10-24 用户要求删掉了“下一页 · 动态”这类浮出的卡片）：反馈只有页面本身的橡皮筋和爱心珠的倾斜。
- **什么算一次推**：必须从边缘开始。滚轮 / 触控板：一阵连续的滚动（包括惯性）只是普通滚动，哪怕正好滚到了底；停顿 90 ms 以上之后的下一阵才算推。触屏：手指落下时页面已经在边缘。两个相邻的滚轮格在 260 ms 内累加。
- **关掉的情况**：动效档位“关闭”或系统“减少动态效果”；搜索框、抽屉、灯箱等浮层打开；指针下有还能滚动的盒子（长代码块、文本框）；捏合缩放；正在换页。菜单始终是换页的普通办法，这个手势只是多一种。
- 换页期间 `<Transition>` 的 CSS 被关掉（`:css="!turning"`），因为旧页面这时已经看不见了，由页面自己的弹簧来做动作；新页面照常在顶部打开、依次入场。
- 检查：`qa/pull.mjs`（真实滚轮；Chromium 里还有真实触摸）、`tests/spring.test.ts`、`tests/nav-links.test.ts`。

## 滚动动效

进度的**目标值**是滚动位置的纯函数，**显示值**以有限速度追赶目标（[PLAN.md](PLAN.md) 第 3 节）：`src/fx/math.ts` 里只有算式（`target` 目标、`follow` 限速追赶、`shape` 缓动与状态），单元测试直接验证；`engine.ts` 负责测量、缓存、每帧追赶一步并写 `--fx-in` / `--fx-out` / `data-fx-state`；`ui/css/fx.css` 把这两个数字变成 `opacity / translate / scale / rotate / clip-path`。

- **每一块内容都有动效**：页面上所有文字、卡片、列表行、图片、按钮、筛选条、分页、目录、页脚那一行都带 `v-fx`（`qa/coverage.mjs` 逐页检查，11 种页面 × 桌面 / 手机；漏掉任何一块就报错）。新写页面或组件时，每个有内容的块都要有 `v-fx`，不要只给页头加。
- **入场**：页面在顶部打开时，页头按 `data-fx-intro` 的序号先入场，**首屏上其余的内容紧接着从上到下、从左到右一个个入场**（`fx/engine.ts` 的 `enterInView`：`OPEN_STEP`、`OPEN_LATEST` 控制节奏，最晚 0.96 秒开始）；跟着页头稍后才到的内容（文章正文）算同一次打开（`OPEN_WINDOW` 500 ms）；之后自己冒出来的内容（筛选出新结果、加载更多）在屏幕上时有一个快速的入场（`LATE_*`）；折叠线以下的随滚动进来；前进后退恢复到滚动位置的页面没有入场。
- **出场**：滚出屏幕时随滚动出场（`out`）；离开页面时每一块内容各自向上淡出一小段（`ui/css/fx.css` 的 `.page-leave-active [data-fx]`），再换成新页面。
- **最短变化时间 `MIN_MS = 420`，而且是“软”的**：一次完整的出现或消失至少 420 ms；显示值用“带速度上限的临界阻尼跟随”（`fx/math.ts` 的 `chase`，也就是 smooth-damp）追目标：起步和停下都是渐变的（不再是“匀速突然停”），最快不超过每 420 ms 一次完整变化，从不过冲，落点精确；追赶中目标反向时从当前速度平滑掉头；慢滚时只落后“速度 × `SMOOTH`(50 ms)”那么一点，看起来是跟手的。积分用固定小步长，和帧率几乎无关；帧间隔超过 50 ms（隐藏标签页、长任务）按 50 ms 算。元素的第一张画面和获得焦点的元素直接到位。`drift` 视差不限速。
- **一个帧循环**（`shared/frame.ts`）：所有跟着滚动走的东西——动效引擎、菜单的进度针脚、右下角回到顶部的圆环、阅读线、目录当前项——都挂在同一个循环上，每帧**先全部读**（滚动位置、尺寸、矩形）、**再全部写**，所以一帧只重算一次样式；它们各自的 `requestAnimationFrame` 会交错读写、让浏览器一帧里重算好几次样式。进度类的值（`public/progress.ts`）也用同一个 `chase` 平滑，并且直接写进元素（`--p`、`stroke-dashoffset`），不经过 Vue，滚动时不会重新渲染菜单。标题的位置只在布局变化时量一次（`ResizeObserver`），滚动时只比数字。
- **动效数字不继承**（`ui/css/fx.css` 开头的 `@property`）：`--fx-in`、`--fx-out`、`--fx-d`、`--m` 登记成“不继承的数字”，每帧改它们不会让元素里面的几十个节点跟着重算样式；只有两种需要子元素读的（逐字标题的字、封面里的图）用单独写的 `--fx-tin` / `--fx-tout`（继承）。新加的动效类型如果子元素要用这些数字，也得走 `--fx-tin` / `--fx-tout`。
- **菜单的针脚**：已缝的部分是一条**实线**，用 `scale` 生长（合成器的活，不用重绘），尖端有一颗小“针头”；以前的虚线要一整截一整截地露出来，一篇文章才走 88 px，看起来就是“停很久再长一小段”。
- 要等动效到位再读数字或截图：`FX.stats().moving` 为 `false` 时才算到位（`qa/common.mjs` 的 `settled(page)` 就是这么等的）；`FX.read(el)` 同时给出显示值 `lin/lout` 和目标 `tin/tout`。调整时间只改 `math.ts` 里的 `MIN_MS`（`qa/fx.mjs` 里也有一份，要一起改）。

- 用法：`<div v-fx="'rise'">`，或 `v-fx="{ type: 'pop', intro: 2 }"`；类型 `rise fade pop slide mask draw-x draw-y spine drift text`。
- 注册与注销由指令负责；新元素在**同一个微任务里一起测量并算出第一帧**，所以新页面不会先“全亮”再淡入（`qa/fx.mjs` 的 G 项盯着这件事）。
- 标题逐字：`<FxText tag="h1" :text="…">`。**声明式渲染**（不是事后改 DOM），Vue 和引擎不会抢同一个文本节点；句子变了就是新元素。超过 32 字（手机 24 字）不拆，整块淡入。
- 普通标题保持词不被拆开：`<Phrase :text="…">`（`Intl.Segmenter` 分词，标点不落行首）。
- 服务端生成的正文（`v-html`）里的块，由 `ProseView` 在插入后一次性标记类型并登记；`h2` 用 `domsplit.ts` 拆字（这块 DOM 之后不会再被 Vue 改）。
- 动效档位：系统“减少动态效果” > `?motion=` > 访客自己的选择（抽屉里的开关，存在 `localStorage: bb:motion`）> 后台默认值。`boot.js` 和 `engine.readMode` 用同一套规则，`tests/boot.test.ts` 让两边在六种组合下对账。
- 没有 JS 时什么都可见：`fx-pending` / `boot` 这两个“先藏起来”的类是 `boot.js` 加的，不是写在 HTML 里的；脚本没启动时 2.6 秒后自动解除。

## 样式规则（来自过去的教训，测试盯着）

- 一个 `@layer` 顺序（`reset, tokens, base, components, layout, pages, fx, utilities`），**没有任何层外的规则**；所以组件里**不写 `<style>`**。
- 一种线色（`--line`，1px），卡片是平的（没有阴影，只有悬浮层有蓝色浅影），`<main>` 和页面标题**永远不画聚焦环**，其余控件统一画 2px `--ring`。
- 浅色为主，背景里没有深色；不做深色模式（`color-scheme: light`）。
- 严格 CSP（`script-src 'self'; style-src 'self'`）：模板里**不写 `style="…"`、不写 `onclick="…"`**；动态样式（`:style`、`el.style.setProperty`）走 CSSOM，允许。`v-html` 只能出现在五个已知文件里（正文、动态、两处搜索片段、图标精灵），多一个就测试失败，逼着复核来源。
- 断点：`760`（手机，底栏）、`1024`（卡片两列）、`1100`（没有粘性侧栏）；脚本里的数字在 `public/viewport.ts`。

## 页面与组件的约定

- 卡片网格 6 列；一张卡占 6（横躺）、3 或 2 格。`public/cards.ts` 按“一页 9 篇 = 1·2·3·2·1 行”排；平板两列时换成“一张宽卡 + 成对”；最后一行放不满就用更少、更宽的卡，**不会有半宽的孤儿卡**（单元测试对 1–30 篇、三种列数逐一验证）。
- 卡片样式：文章自己的 `card_style` 优先；`auto` 时按宽度、有没有封面、在行里第几列决定（便利贴 · 引言 · 小图卡轮着来）。没有封面的文章用标题哈希生成浅色图案。
- **菜单是一条“针线”**（`layout/ThreadNav.vue`，2026-10-24 起取代胶囊和悬浮底栏）：每个入口一颗小珠，粉色爱心珠表示“你在这里”，路由变了才沿线滑到新位置（带一点回弹）；第一次绘制、窗口缩放时直接落在当前项上。爱心下面有一段粉色针脚，随阅读进度从当前珠子缝向下一颗（最后一页缝向线尾的小结），缝完时下一颗会轻轻一跳（`public/progress.ts` 提供阅读进度，一个滚动监听服务所有用到它的组件）。位置全部由 `--n`（条目数）`--i`（当前）`--p`（已读）三个数字用 CSS 算出，不测量，所以缩放不会错位。
  - 宽屏（> 1100px）：竖线贴在页面左边缘（`.nav.thread--side`，固定定位，垂直居中）；珠子是小圆点，悬停或键盘聚焦时放大并露出图标和名字，当前页的名字在边距够宽（≥ 1360px）时一直显示在爱心旁，较窄时换页后露一下再收回。触屏的大屏（无悬停）珠子直接带图标。
  - 手机和平板（≤ 1100px）：贴底的一条栏（`.tabbar.thread--bottom`，高度 `--bar-h`，带安全区），线横着走，珠子带图标、名字在下面；「搜索」「更多」是动作珠（按钮）。回到顶部和目录按钮都抬到这条栏上方。
  - 动效：系统“减少动态效果”或站内动效选“关闭”时没有滑动、回弹和心跳；`qa/nav.mjs` 在两种形态下逐帧采样（起点在当前珠子、终点在新珠子、只有一次回弹）。
  - `design/` 里的原型保留 P0 时的胶囊样子，没有跟进。
- 路由切换：淡出旧页 → 挂载新页淡入；滚动位置等新页挂载后再恢复（返回键回到原位）；焦点移到页面标题（`tabindex=-1`，不画环）。
- 正文里的站内链接走路由，站外链接、订阅、后台地址保持普通链接（`links.ts`、`isServerPath`）；`/admin` 永远不会被前台路由接住。
- 正文里的图片是可键盘操作的按钮（Enter / 空格打开灯箱，关闭后焦点回到图片）；横向滚动的代码块 / 表格可以用 Tab 聚焦。
- 搜索：浮层（`/`、`Ctrl/⌘ K`）边输边查，方向键 + 回车；`/search?q=` 是完整结果页；最近搜过的 5 个词存在本机。

## 检查

| 检查 | 文件 | 盯什么 |
|---|---|---|
| 类型 | `npm run typecheck` | 接口样例（`docs/api-samples`）赋给 `shared/types.ts`：服务端删字段 / 改名，这里编译就失败 |
| 单元 | `tests/*.test.ts` | 动效算式、分词、日期、卡片规划、导航高亮、路由守卫、数据加载、`<head>`、`boot.js` 与引擎对账、接口样例、图标词表（服务端能发的每个图标 / 心情都有图）、源码规则（层、CSP、`v-html` 白名单、没有第三方地址） |
| 溢出 + 控制台 | `qa/overflow.mjs` | 11 种页面 × 6 个宽度（320 … 1440）：不横向溢出、没有报错 |
| 线与阴影 | `qa/lines.mjs` | 非悬浮元素没有阴影、边框只有 `--line` / `--rose-line`、没有方角“卡片”；也扫开着搜索浮层的状态 |
| 对比度 | `qa/contrast.mjs` | 渲染后的每段文字，4 套主题 + 3 套代码高亮，低于 4.5:1（大字 3:1）失败 |
| 聚焦环 | `qa/focus.mjs` | 键盘走遍每个停靠点都是 2px 环；`<main>` 与标题没有环；导航后焦点在标题；有自检（把旧 bug 放回去必须被抓到） |
| 菜单的爱心珠 | `qa/nav.mjs` | 竖线与横线两种形态：首屏直接落在当前珠子、一次导航一次移动、终点准确、只有一次回弹 |
| 标题断词 | `qa/text.mjs` | 词的 span 不是 flex / grid 项，相邻词不出缝 |
| 滚动动效 | `qa/fx.mjs` | A 任意位置 / 跳转 / 甩动与独立重算一致；B 单调；C 缩放后仍对；D 减少动态效果；E 无 JS；F 6 倍降速的每帧耗时 ≤ 10 ms（仅 Chromium）；G 切页不闪 |
| CSP + 网络 | `qa/csp.mjs` | 页面与交互状态里没有 CSP 违规、没有请求别的主机、响应头带 CSP |
| 无障碍 | `qa/a11y.mjs` | axe-core WCAG 2.1 A / AA：严重和关键问题为 0 |
| 加载速度 | `qa/perf.mjs`（`npm run qa:perf`） | 手机宽度、Slow 4G（1.6 Mbit/s、150 ms 往返）、4 倍降速 CPU、冷缓存、文本经 gzip 代理（模拟 nginx）：6 种页面各 3 次取中位数，LCP ≤ 2.0 s、CLS ≤ 0.05；同时报告 FCP、请求数、线上字节、长任务（只有 Chromium：要用 DevTools 协议；没用 Lighthouse，指标与浏览器 API 相同）。当前：LCP 0.96–1.47 s、CLS 0.000、每页 107–166 KB |
| 流程 | `qa/flows.mjs` | 12 条真人操作：导航、返回恢复位置、目录跳转、复制、灯箱、搜索、筛选分页、动态、404、手机底栏与抽屉、统计信标 … |

已知的局限：WebKit 下 Tab 默认不聚焦链接（Safari 的行为），所以聚焦环审计在 WebKit 里只覆盖按钮和表单；完整的键盘遍历以 Chromium 为准。**真实 Safari 与手机仍需要你亲自过一遍**（Playwright 的 WebKit 与 Safari 同源但不是同一个构建）。

## 体积（首屏，gzip）

JS 约 80 KB（预算 90）：`vendor`（Vue + Router）40 KB + 应用与共用块 40 KB + `boot.js` 0.5 KB；CSS 约 14 KB（预算 20）。（后台入口和预览框共用 `vendor` / `common`，但样式表各用各的：前台不会下载后台样式。）没有字体文件（拉丁字母用系统自带的圆体，中文用系统圆体 / 无衬线回落）。超预算 `npm run build` 直接失败。

## 加一个页面 / 一种动效 / 一个图标

- **页面**：后端加路由和 `spa.py` 里的页面描述（`kind`）→ `shared/types.ts` 加形状 → `data.ts` 的 `fetchRoute` / `fromBoot` → `state.ts` 的 `PageState` → `pages/` 写组件 → `App.vue` 的 `views` 表 → `head.ts` 的 `headFor`。TypeScript 的穷尽检查会逐个指出漏了哪一步。
- **动效类型**：`fx.css` 里写它的样子（只依赖 `--fx-in` / `--fx-out`），`directive.ts` 的 `FxType` 加名字，`qa/fx.mjs` 会自动覆盖。
- **图标**：画进 `ui/sprite.svg`（`i-名字`，24×24，`currentColor` 描边）；`public/icons.ts` 里登记；服务端要能发的话再加进 `backend/app/defaults.py` 的 `ICONS`。`tests/vocab.test.ts` 保证两边一致。
