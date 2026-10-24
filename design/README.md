# saubakaの博客 · 设计样张（阶段 P0）

静态样张：令牌、组件、涂鸦、滚动动效引擎原型，以及首页 / 博客 / 文章 / 动态 / 归档 / 404 几张页面。
没有后端，页面里的文字和图片都是示例。完整规划见 [`../docs/PLAN.md`](../docs/PLAN.md)。

## 看样张

```bash
cd design
python3 serve.py 5200        # 不缓存的本地服务器
```

浏览器打开 <http://127.0.0.1:5200/>（总览页，带检查清单）。想用手机真机看：`BB_HOST=0.0.0.0 python3 serve.py 5200`，手机和电脑连同一个 Wi-Fi，打开 `http://<电脑的局域网地址>:5200/`（看完记得停掉）。右下角「设计面板」可切换配色预设（糖霜 / 晴空 / 樱花 / 云雾）和动效强度（标准 / 轻柔 / 关闭）；
地址后加 `?motion=off`、`?motion=soft` 也行。系统开启「减少动态效果」时动效自动关闭。

| 页面 | 文件 | 内容 |
| --- | --- | --- |
| 总览 | `index.html` | 所有页面入口、请你看什么的清单 |
| 首页 | `home.html` | 开场、最近文章、最近动态、书架、关于 |
| 博客 | `blog.html` | 分类标签页、搜索、排序、卡片 / 列表切换（可真的点） |
| 文章 | `post.html` | 目录、代码块、提示块、表格、图集、系列、上下篇 |
| 动态 | `moments.html` | 时间线、气泡、心情、链接卡片、图片排版、灯箱 |
| 归档 | `archive.html` | 按年月的时间线 |
| 404 | `404.html` | 走丢了 |
| 设计系统 | `components.html` | 配色（实时对比度）、线条、字体、全部组件、图标 |
| 动效实验室 | `fx-lab.html` | 每种动效的数值、逐字折行测试、「运行自检」 |

## 改样张

`src/` 里是源文件，`python3 build.py` 把 `src/layout.html`、`src/partials/`、`src/pages/` 拼成上面的 `*.html`。
样式分层顺序固定在 `css/tokens.css` 顶部（`reset, tokens, base, components, layout, pages, fx, utilities`），所有规则都放进某一层。
站点名、英文名、作者、简介只在 `js/data.js` 和 `src/partials/` 里各出现一次。

## 不能破的规则

- 只有一种线色 `--line`（1px），卡片是平的，只有浮层（抽屉、弹窗、提示）才有带蓝调的阴影。
- 页面里没有深色块，最深的颜色只用于文字；所有预设都是浅色。
- `<main>` 永远不画焦点环，其余控件用统一的焦点环。
- 滚动动效的**目标**是「滚动位置的函数」，不是一次性动画，所以不会卡在半透明；**显示**的进度以有限速度追赶目标（一次完整出现或消失至少 420 ms），所以大幅度跳转、甩动都不会瞬间出现或消失，慢慢滚则逐帧紧跟。

## 自动检查

```bash
export CHROME="$HOME/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
export NODE_PATH="$PWD/../frontend/node_modules"      # 用前端工程里装好的 playwright（先在 frontend/ 里 npm install）
./qa/all.sh          # 全部（约 10 分钟）
```

单项脚本都在 `qa/`：`overflow.js`（横向溢出与控制台）、`lines-audit.js`（线色、阴影、方角卡片）、`contrast-audit.js`（四个预设的文字对比度）、
`focus-audit.js`（键盘焦点与 `<main>` 无焦点环）、`nav-audit.js`（导航指示器只滑一次）、`text-audit.js`（标题分词不被拉开）、
`fx-audit.js`（动效公式、单调性、缩放、减少动态效果、无 JS、每帧耗时）、`selftest.js`（动效实验室自检）。
截图：`node qa/screens.js <输出目录> <页面> <宽度> <滚动位置列表|auto> [query]`。

目前只在 Chromium 里跑过；WebKit / Safari 需要人工在真机或 Safari 里确认（尤其是 `fx-lab.html` 的逐字折行测试）。
