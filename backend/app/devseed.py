"""Development sample content: `flask --app app seed-demo`.

Enough to see every public page filled in (several posts in a series, moments with pictures and a link card, a page, a pinned item,
a draft and a scheduled post). The polished demo content is written in phase P4; this is only so the front end has something real to
draw while it is being built. Pictures are drawn with Pillow in the soft pastel palette, so no files have to be shipped.
"""
from __future__ import annotations

import io
from datetime import timedelta

from PIL import Image, ImageDraw
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Config
from app.models import Media, Post
from app.services import media as media_service
from app.services import moments, pages, posts, taxonomy
from app.timeutil import utcnow

SKY = (230, 241, 252)
ROSE = (253, 238, 243)
MIST = (239, 242, 246)
LINE = (195, 220, 244)
WHITE = (255, 255, 255)
ROSE_LINE = (242, 198, 216)


# ---- pictures ---------------------------------------------------------------------------------------------------------------------------
def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def picture(kind: str, w: int = 1200, h: int = 800) -> bytes:
    img = Image.new("RGB", (w, h), SKY if kind != "evening" else ROSE)
    d = ImageDraw.Draw(img)
    if kind == "sky":
        d.ellipse((w * 0.7, h * 0.12, w * 0.7 + 150, h * 0.12 + 150), fill=ROSE, outline=ROSE_LINE, width=4)
        d.polygon([(0, h), (0, h * 0.78), (w * 0.35, h * 0.7), (w * 0.7, h * 0.8), (w, h * 0.72), (w, h)], fill=(217, 233, 249))
    elif kind == "evening":
        d.ellipse((w * 0.4, h * 0.35, w * 0.4 + 260, h * 0.35 + 260), fill=(249, 224, 234))
        d.ellipse((w * 0.4 + 60, h * 0.35 + 60, w * 0.4 + 200, h * 0.35 + 200), fill=(242, 198, 216))
        d.rectangle((0, h * 0.72, w, h), fill=MIST)
    elif kind == "desk":
        d.rectangle((0, h * 0.72, w, h), fill=(230, 234, 240))
        d.rounded_rectangle((w * 0.28, h * 0.3, w * 0.7, h * 0.7), 24, fill=WHITE, outline=LINE, width=4)
        d.rectangle((w * 0.32, h * 0.36, w * 0.66, h * 0.6), fill=SKY)
        for i in range(3):
            d.rounded_rectangle((w * 0.34, h * (0.4 + i * 0.05), w * (0.5 - i * 0.04), h * (0.42 + i * 0.05)), 6, fill=LINE)
        d.rounded_rectangle((w * 0.78, h * 0.52, w * 0.86, h * 0.72), 12, fill=ROSE, outline=ROSE_LINE, width=4)
    elif kind == "tea":
        d.ellipse((w * 0.2, h * 0.55, w * 0.8, h * 0.78), fill=ROSE, outline=ROSE_LINE, width=4)
        d.pieslice((w * 0.22, h * 0.3, w * 0.78, h * 0.9), 0, 180, fill=WHITE, outline=ROSE_LINE, width=4)
        for k in range(3):
            d.ellipse((w * (0.38 + k * 0.1), h * 0.5, w * (0.38 + k * 0.1) + 70, h * 0.5 + 70), fill=WHITE, outline=ROSE_LINE, width=3)
        img = img.convert("RGB")
    elif kind == "hills":
        for i, c in enumerate(((217, 233, 249), (195, 220, 244), (230, 241, 252))):
            d.polygon([(0, h), (0, h * (0.6 + i * 0.12)), (w * 0.3, h * (0.5 + i * 0.1)), (w * 0.6, h * (0.65 + i * 0.1)), (w, h * (0.55 + i * 0.1)), (w, h)], fill=c)
    return _png(img)


# ---- content ---------------------------------------------------------------------------------------------------------------------------
SQLITE_POST = """先说结论：**别用 `cp` 去备份一个正在被写入的 SQLite 数据库**。我就是这样做的，而且还成功了很多次——直到有一次没成功。

## 事情是这样的

这个站用 SQLite 当数据库：一个文件，不用另外装服务，备份起来“应该很简单”。我的第一版备份脚本只有一行：

```bash title="backup.sh"
# 每天凌晨三点跑一次
cp /var/lib/blog/site.db /var/backups/site-$(date +%F).db
```

看起来没毛病。直到某个周末我想试试恢复，发现最近一份备份**打不开**，提示 `database disk image is malformed`。

::: warn 当时的心情
手心出汗，反复刷新，怀疑是不是自己手滑把库删了。（不是，我没有手滑，是我的备份有问题。）
:::

## 为什么直接复制文件不安全

SQLite 的写入不是“一下子把文件改好”。复制的那一刻如果恰好有事务在写，你拿到的可能是写到一半的文件——页面对不上，自然打不开。

### 开了 WAL 之后更要小心

很多人（包括我）会打开 WAL 模式来提升并发。这时新写入的数据先进入 `site.db-wal`，要等“检查点”才会合并回主文件。只复制 `site.db`，就等于丢掉了还没合并的那部分。

::: tip
主文件、`-wal`、`-shm` 是一个整体。要么用 SQLite 自己提供的备份接口，要么保证复制期间没有任何写入。
:::

## 写法一：sqlite3 命令行的 .backup

最省事的做法，一行搞定，写入进行时也能得到一致的副本：

```bash title="backup.sh"
sqlite3 /var/lib/blog/site.db ".backup '/var/backups/site-$(date +%F).db'"
```

## 写法二：在 Python 里调用 backup()

应用本身是 Flask，我更想把备份写成一个函数，方便接到后台的“立即备份”按钮上。标准库里的 `sqlite3.Connection.backup` 正好够用：

```python title="backup.py"
import sqlite3


def backup(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)   # 在线备份：写入进行时也能得到一致的副本
    dst.close()
    src.close()
```

![凌晨的书桌，一台笔记本和一只杯子](media:{desk} "写这段代码的那个凌晨"){{.polaroid}}

## 写法三：VACUUM INTO

它会生成一个整理过的、体积更小的副本，还顺便做了碎片整理。需要 SQLite 3.27 以上：

```sql title="compact.sql"
VACUUM INTO '/var/backups/site-compact.db';
```

| 方法 | 要停写入吗 | 得到什么 | 适合 |
| :-- | :-: | :-- | :-- |
| `cp` 复制文件 | 要 | 原样文件（可能不完整） | 停机维护时 |
| `.backup` | 不用 | 一致的副本 | 定时任务、命令行 |
| `backup()` | 不用 | 一致的副本 | 写进应用里 |
| `VACUUM INTO` | 不用 | 整理过的更小副本 | 想顺便瘦身 |

## 恢复演练：不试一次就不算备份

> 备份文件只有被成功恢复过，才算备份。

每次备份完成后，我会马上打开副本做两件事：检查完整性，数一数关键表里的行数。

```python title="verify.py"
con = sqlite3.connect(dst_path)
ok = con.execute("PRAGMA integrity_check").fetchone()[0]
assert ok == "ok", ok
posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
print(f"完整性正常，文章 {{posts}} 篇")
```

## 我现在的做法

- [x] 用 `backup()` 做在线备份，不再 `cp`
- [x] 每次备份后立刻校验完整性
- [ ] 每月做一次真正的“恢复演练”（下个月记得！）

![下雨的窗户](media:{window})
![粉色的傍晚](media:{evening})
![远处淡蓝色的山](media:{hills})

::: love 最后
数据没丢，我也没哭。如果你也在用 SQLite，现在就去打开备份目录看一眼，真的。[^1]
:::

[^1]: 如果打开后发现备份不对，别慌，先别动原文件，从最近一份能通过校验的备份开始恢复。
"""


def fill(text: str, pics: dict[str, int]) -> str:
    """@@name@@ in a text becomes the id of that picture (so Markdown with braces, like CSS, needs no escaping)."""
    for name, mid in pics.items():
        text = text.replace(f"@@{name}@@", str(mid))
    return text


WHY_REWRITE = """旧的那个博客太重了：深色的线、灰色的阴影、一堆我自己都记不清的设置。每次打开它我都觉得是在上班。

这一次我想做得轻一点、浅一点，也安静一点。

## 我给自己定的几条规矩

- 颜色只有很浅的蓝、很浅的灰和很浅的粉，**不用任何深色**；
- 线只有一种，1px，浅到几乎看不见；
- 没有评论区，没有点赞，没有访客账号；
- 滚动时东西会轻轻进来、轻轻离开，但不能挡住你读字。

::: note 关于“重写”
不是旧的不好，是我忘了它为什么长成那样。重新画一遍，至少每一条线我都知道是谁放的。
:::

## 为什么是 Flask 和 Vue

因为我会它们，而且它们都够小。后端一个进程，数据库一个文件；前端打出来首屏大概 80 KB。放在一台最便宜的机器上，也不会喘。

![凌晨的书桌，一台笔记本和一只杯子](media:@@desk@@ "重新画的第一个凌晨")

接下来的几篇是这个系列：配色、数据备份、动效、登录。写得慢，但每一篇都会认真改三遍。"""

LIGHTER_LINES = """一条 1px 的线，颜色深一档和浅一档，整页的气质完全不同。

## 先看一条线

我把所有的线统一成了同一个颜色。卡片、分隔线、输入框，都用它：

```css title="tokens.css"
:root {
  --line: #dceaf7;        /* 全站唯一的线色 */
  --line-w: 1px;
}
.card { border: var(--line-w) solid var(--line); }
```

用了一个变量之后，“哪条线颜色不对”这类问题就从“满页找”变成了“搜一下变量名”。

## 然后是阴影

真正让线条“显深”的，其实是卡片外面那一圈灰色的阴影。去掉阴影以后，线条自己就变浅了。

::: tip 一个小检查
给自己写一个脚本：遍历页面里所有元素，找出有阴影却不是浮层的。我的这个脚本第一次跑就抓到了三处。
:::

## 圆角也是线的一部分

方方正正的“卡片”带着 1px 的浅线，看起来像一张被裁过的纸；圆角 20px 以后才像一张卡片。数字不重要，重要的是**所有的卡片用同一个数**。

> 安静不是什么都没有，是每一样东西都在它该在的地方。"""

SCROLL_MOTION = """不是“进入视野就播放”，而是进度跟着滚动位置走，倒着滚也能倒放。

## 进度是位置的函数

元素的入场进度由它在屏幕里的位置直接算出来，所以跳转、前进后退、窗口缩放之后都不会卡在半透明：

```ts title="progress.ts"
/** 0 = 还在屏幕下面，1 = 完全进来了；只依赖位置，不依赖“上一帧” */
export function enter(top: number, height: number, viewport: number): number {
  const start = viewport * 0.96   // 元素顶边到这里才开始进来
  const end = viewport * 0.62     // 到这里就完全进来了
  return Math.min(1, Math.max(0, (start - top) / (start - end)))
}
```

## 为什么不用 IntersectionObserver

它告诉你“进来了”或“出去了”，但不告诉你**进来了多少**。要做“跟着滚动走”，就得自己量；量的时候不能在滚动事件里读布局，否则每一帧都会强制重排。

- [x] 位置在滚动之外量好（尺寸变了才重量）
- [x] 每一帧只做乘法和赋值
- [x] 没有任何“上一帧的状态”，所以不会漂
- [ ] 真机上再调一次手感（下个周末）

## 减少动态效果

系统设置里选了“减少动态效果”的人，什么都不会动：内容一开始就是完整的。**动效是礼物，不是门槛。**"""

NO_COMMENTS = """想说什么可以发邮件。我想把这里做成一个安静的地方。

没有评论区，也就没有垃圾评论、没有审核、没有“沙发”。剩下的只有文章本身。

## 我想过的几种方案

| 方案 | 好处 | 我没选它的原因 |
| :-- | :-- | :-- |
| 自己做评论 | 数据在自己手里 | 要做审核、防垃圾、通知，比写文章还累 |
| 第三方评论 | 省事 | 引一堆脚本，隐私也不归我管 |
| 不要评论 | 安静 | ——（这就是答案） |

## 想联系我

文章末尾和“关于”页都有邮箱。写得长短都可以，我会回。

::: love
这个站的目标是：读的人读得舒服，写的人写得轻松。评论区两头都不讨好。
:::"""

SUNDAY_EVENING = """今天的傍晚像一碗粉色的汤，我看了很久。

![粉色的傍晚](media:@@evening@@ "天空的颜色一直在变"){.polaroid}

下午三点是白的，四点半开始发蓝，到了六点，边上慢慢染了一圈粉。我就坐在窗边，什么也没做，只是确认这片天色**还在**。

> 有些东西不需要被记录，看过就够了。

不过我还是把它写下来了，因为明天我大概会忘。"""

FLASK_LOGIN = """会话、限速、CSRF，一个人用的后台到底需要哪些。

## 会话

随机令牌，数据库里只存哈希。Cookie 设成 `HttpOnly`、`SameSite=Lax`，生产环境再加 `Secure`。

```python title="session.py"
import hashlib, secrets

def new_session() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)               # 只发给浏览器一次
    return token, hashlib.sha256(token.encode()).hexdigest()   # 数据库里只存这个
```

## 限速

同一个用户名连续失败五次就先歇十五分钟；同一个网段连续失败二十次也歇。注意：**失败的那次登录必须先提交，再返回错误**，否则回滚会把“失败了一次”也一起回滚掉，限速就永远数不到数。

::: warn 我踩过的坑
写接口的“出错就回滚”是个好习惯，但它和“记录失败次数”正好是反的。
:::

## CSRF

所有写接口要求一个请求头里的令牌，并且请求必须来自本站。一个人用的后台也要做：你自己也会点开别人发来的链接。"""

RAINY_COFFEE = """下雨天更容易写出 bug，这不是玄学，是咖啡洒在了键盘上。

## 雨天的开发环境

1. 一杯会凉的咖啡
2. 一扇有雨的窗户
3. 一个本来“五分钟就能改完”的 bug

![下雨的窗户](media:@@window@@)

## 结论

- 先喝咖啡，再改 bug；
- 不要一边喝咖啡一边 `git reset --hard`；
- 如果 bug 在雨停了之后自己消失了，请不要追问。"""

README_FOR_CAT = """如果猫是一个项目，它的安装说明大概是这样的。

```text title=README.md
# cat

一个自带主见的小型系统。

## 安装

买一个纸箱。（猫会自己安装。）

## 配置

没有配置文件。猫自己决定它要不要被配置。

## 已知问题

- 凌晨三点会自动运行跑酷模块，无法关闭
- 键盘上的温度传感器可能让你的文档多出几行 `jjjjjjjj`
```

## 贡献指南

不接受外部贡献。但欢迎提供零食。"""

PALETTE = """极浅的蓝、浅灰和浅粉，只有文字是深一点的墨蓝灰。

## 线

全站只有一种线色：`#dceaf7`。

## 色板

| 名字 | 用在哪里 | 色值 |
| :-- | :-- | :-- |
| 极浅蓝 | 页面背景、卡片底 | `#f7fbff` |
| 浅蓝 | 填充、选中 | `#e6f1fc` |
| 浅粉 | 点缀、重点 | `#fdeef3` |
| 墨蓝灰 | 文字 | `#46546a` |

::: tip 为什么没有深色
深色会把页面的重量压下来。要强调时我用的是**更大的字号和更多的空白**，而不是更深的颜色。
:::

![远处淡蓝色的山](media:@@hills@@)

## 对比度

浅色背景上的文字必须够清楚：正文至少 4.5:1。我把这个检查写成了脚本，每次改配色都会跑一遍，**包括四套主题**。"""

ABOUT = """## 你好，我是 sau_baka

写代码的人，偶尔画画，经常发呆。喜欢把东西做得安静一点——颜色浅一点，线条细一点，字号刚刚好。

站名里的 Baka 是日语里的“笨蛋”。别人这么叫我的时候我会生气，自己这么叫的时候不会。

## 这个站是做什么的

- **博客**：认真写的文章，写得慢，但每一篇都改过三遍；
- **动态**：碎碎念、随手拍的照片、看到的好链接，想到什么发什么；
- 没有评论区，没有点赞，没有追踪你的东西。

## 它是怎么搭的

后端是 Flask 加一个 SQLite 文件，前端是 Vue 3。首屏大约 80 KB，在手机上也能很快打开。后台里每一个字都可以改。

## 联系我

这里没有评论区。想说什么，请发邮件。"""

LINKS = """还没有友链。

我不太会“交换”东西，但如果你写的东西让我读了一整个下午，请发邮件告诉我：我想把它放在这里。

## 友链格式

- 站名
- 一句话介绍（别太长）
- 地址（https 的最好）"""


def seed(session: Session, cfg: Config) -> dict[str, int]:
    """Fill an empty site with sample content. Refuses when there are posts already."""
    if session.scalar(select(func.count()).select_from(Post)):
        raise RuntimeError("the site already has posts; seeding is only for an empty one")
    pics: dict[str, int] = {}
    alts = {"sky": "淡蓝色的天空", "evening": "粉色的傍晚", "desk": "凌晨的书桌", "tea": "一碗汤圆", "hills": "远处淡蓝色的山"}
    for kind, alt in alts.items():
        pics[kind] = media_service.create(session, cfg, picture(kind), f"{kind}.png", alt=alt)[0].id
    window = media_service.create(session, cfg, picture("hills", 1000, 700), "window.png", alt="下雨的窗户")[0]
    pics["window"] = window.id

    cats = {name: taxonomy.create_category(session, name, sticker=sticker) for name, sticker in
            (("代码", "code"), ("设计", "sparkle"), ("日常", "smile"), ("随笔", "quote"))}
    series = taxonomy.create_series(session, "把博客做成自己喜欢的样子", description="从配色、动效到后台，一点点把这个博客重新画一遍。")
    now = utcnow()

    def day(n: int):
        return now - timedelta(days=n)

    sqlite_body = SQLITE_POST.format(desk=pics["desk"], window=pics["window"], evening=pics["evening"], hills=pics["hills"])
    posts.create(session, {
        "title": "SQLite 备份：我差点把自己的数据弄丢", "slug": "sqlite-backup", "content_md": sqlite_body, "status": "published", "published_at": day(4), "featured": True,
        "category_id": cats["代码"].id, "tags": ["SQLite", "备份", "Flask"], "cover_media_id": pics["sky"], "series_id": series.id, "series_order": 3,
    })
    in_series = {"why-rewrite": 1, "scroll-motion": 4, "flask-login-min": 5}
    for title, slug, cat, tags, days, body in (
        ("为什么重写这个博客", "why-rewrite", "随笔", ["博客"], 62, WHY_REWRITE),
        ("把线条调浅了一点点，页面就安静了", "lighter-lines", "设计", ["CSS", "设计"], 10, LIGHTER_LINES),
        ("跟着滚动走的入场动画，我是这样做的", "scroll-motion", "代码", ["Vue", "动效"], 17, SCROLL_MOTION),
        ("为什么我不给博客加评论区", "no-comments", "随笔", ["博客"], 32, NO_COMMENTS),
        ("周末的傍晚", "sunday-evening", "日常", ["随手记"], 24, SUNDAY_EVENING),
        ("Flask 里最小的后台登录", "flask-login-min", "代码", ["Flask", "安全"], 41, FLASK_LOGIN),
        ("雨天的咖啡和 bug", "rainy-coffee", "日常", ["咖啡", "随手记"], 53, RAINY_COFFEE),
        ("给猫写的 README", "readme-for-cat", "日常", ["猫"], 69, README_FOR_CAT),
    ):
        extra = {"series_id": series.id, "series_order": in_series[slug]} if slug in in_series else {}
        posts.create(session, {"title": title, "slug": slug, "content_md": fill(body, pics), "status": "published", "published_at": day(days), "category_id": cats[cat].id, "tags": tags, **extra})
    posts.create(session, {"title": "配色和线条：把一切都调浅", "slug": "palette-and-lines", "content_md": fill(PALETTE, pics), "status": "published",
                           "published_at": day(20), "category_id": cats["设计"].id, "tags": ["设计"], "series_id": series.id, "series_order": 2})
    posts.create(session, {"title": "一份还没写完的草稿", "slug": "work-in-progress", "content_md": "写了一半：想聊聊“为什么我的待办清单总是比我长”。\n\n（先放着，今天的傍晚比较重要。）", "status": "draft", "category_id": cats["随笔"].id})
    posts.create(session, {"title": "上线那天", "slug": "launch-day", "content_md": "这是一篇定时发布的文章：到了那一天，它会自己出现在这里，不用我半夜爬起来点按钮。\n\n如果你现在能看到这段话，说明那一天已经到了。", "status": "published", "published_at": now + timedelta(days=20),
                           "category_id": cats["随笔"].id, "series_id": series.id, "series_order": 6})

    pages.create(session, {"title": "关于", "slug": "about", "status": "published", "content_md": ABOUT})
    pages.create(session, {"title": "友链", "slug": "links", "status": "published", "content_md": LINKS})

    for text, mood, tag_names, pic, ago, extra in (
        ("把博客的主色调浅了两档，终于不像在看监控大屏了。 #设计 #CSS", "energy", [], None, 0, {}),
        ("夜宵是一碗很烫的汤圆。", "happy", ["夜宵"], ["tea", "desk"], 1, {}),
        ("SQLite 官方文档里的 Backup API 那一页，我看了三遍。", "think", ["SQLite"], None, 3, {"link_card": {
            "url": "https://sqlite.org/backup.html", "title": "The SQLite Online Backup API", "description": "How to make a consistent copy of a live database."}}),
        ("今天的傍晚像一碗粉色的汤。", "calm", ["随手记"], ["sky", "evening", "hills"], 5, {}),
        ("写了三个小时的 CSS，最后只改了一个数字：1px。", "sleepy", ["CSS"], None, 9, {}),
        ("这里是动态页：碎碎念、照片、链接，想到什么发什么。不开评论，想说什么请发邮件。", "calm", [], None, 30, {"pinned": True}),
        ("有人问我站名里为什么有个“の”。因为好看，没有别的理由。", "happy", ["站名"], None, 2, {}),
        ("`inert` 这个属性真好用：一行代码让整块区域不能点、不能聚焦、读屏也跳过，再也不用自己写焦点陷阱了。", "think", ["前端"], None, 6, {"link_card": {
            "url": "https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/inert", "title": "inert - HTML: HyperText Markup Language | MDN",
            "description": "The inert attribute makes the browser ignore user input events for the element, including focus events and events from assistive technologies."}}),
        ("路过的人都停下来拍了这片傍晚。我也拍了，拍得不如他们的好。", "happy", ["随手记"], ["evening"], 7, {}),
        ("周三的咖啡太苦了，决定明天改喝茶。（这句话我每个周三都会说一遍。）", "sleepy", ["咖啡"], None, 12, {}),
        ("把后台的“发布”按钮从右上角挪到了右下角，因为拇指够得着。小事，但很开心。", "energy", ["博客", "设计"], None, 15, {}),
        ("今天什么都没做，只是看了一下午的窗外。这也算过了一天。", "calm", ["随手记"], ["sky"], 20, {}),
    ):
        data = {"text": text, "mood": mood, "tags": tag_names, "published_at": day(ago), **extra}
        if pic:
            data["media"] = [{"media_id": pics[p], "alt": media_alt(p)} for p in pic]
        moments.create(session, data)

    return {"posts": int(session.scalar(select(func.count()).select_from(Post)) or 0), "media": int(session.scalar(select(func.count()).select_from(Media)) or 0)}


def media_alt(kind: str) -> str:
    return {"tea": "一碗汤圆", "desk": "凌晨的书桌", "sky": "淡蓝色的天空", "evening": "粉色的傍晚", "hills": "远处淡蓝色的山"}.get(kind, "")
