"""The one place where names and default copy live.

Nothing else in the code base spells out the site name, the author or a default sentence. The settings table overrides these
values (the admin edits them), so renaming the site is a settings change, never a code change. Keep the copy short and
specific; no "welcome to my digital garden" lines.
"""
from __future__ import annotations

SITE_NAME = "saubakaの博客"
SITE_NAME_EN = "Baka Blog"
AUTHOR_NAME = "sau_baka"
TAGLINE = "不是笨蛋！！"
SITE_DESCRIPTION = "写代码，记日常，偶尔拍点照片。"
AUTHOR_BIO = "写代码的人，偶尔画画，经常发呆。喜欢把东西做得安静一点——颜色浅一点，线条细一点，字号刚刚好。"
LANGUAGE = "zh-CN"
TIMEZONE = "Asia/Shanghai"

# ---- vocabularies shared by validation, the admin UI and the public API ----------------------------------------------------
MOODS = {
    "happy": "开心", "energy": "元气", "calm": "平静", "sleepy": "犯困", "think": "思考",
    "moved": "感动", "sulk": "小委屈", "sick": "生病中", "party": "庆祝", "daze": "发呆",
}
TAG_COLORS = ("sky", "rose", "mist", "white")
POST_STATUSES = ("draft", "published", "unlisted", "private")
MOMENT_VISIBILITIES = ("public", "unlisted", "private")
PAGE_TEMPLATES = ("plain", "wide", "sidebar")
CARD_STYLES = ("auto", "cover", "side", "note", "quote")
SERIES_STATUSES = ("ongoing", "finished")
THEMES = ("default", "sky", "sakura", "fog")
MOTION_LEVELS = ("full", "soft", "off")
CODE_THEMES = ("frost", "blossom", "fog")
DOODLES = ("star", "heart", "sparkle", "flower", "paw", "wave", "loop")
# icon ids of the hand-drawn sprite (design/src/partials/sprite.svg); stickers on categories, tags and nav items use them
ICONS = (
    "home", "book", "chat", "smile", "search", "menu", "more", "close", "arrow-r", "arrow-l", "arrow-u", "arrow-d", "link",
    "calendar", "clock", "tag", "folder", "copy", "check", "image", "star", "pin", "external", "list", "bulb", "alert",
    "heart", "quote", "code", "mail", "info", "sliders", "sparkle", "grid", "rows", "moon",
)
HOME_BLOCK_TYPES = ("hero", "featured", "latest_posts", "latest_moments", "notice")
# modules the home page used to have (the shelf, the "about me" card and its "now" note, removed 2026-10-28): a stored row of one of these types is ignored, never shown or saved again
RETIRED_HOME_BLOCKS = ("shelf", "about", "now")
NAV_REGIONS = ("top", "mobile", "footer")
NAV_KINDS = ("route", "page", "category", "tag", "series", "link", "action")
NAV_ACTIONS = ("search", "more", "top")
MOBILE_NAV_MAX = 5
# fixed routes a "route" nav item may point to
ROUTES = ("/", "/blog", "/moments", "/archive", "/search")

# ---- settings groups: defaults (the settings table stores only what the admin changed) ---------------------------------------
DEFAULT_SETTINGS: dict[str, dict] = {
    "site": {
        "name": SITE_NAME,
        "name_en": SITE_NAME_EN,
        "tagline": TAGLINE,
        "description": SITE_DESCRIPTION,
        "language": LANGUAGE,
        "timezone": TIMEZONE,
        "logo_media_id": None,
        "favicon_media_id": None,
    },
    "author": {
        "name": AUTHOR_NAME,
        "bio": AUTHOR_BIO,
        "avatar_media_id": None,
        # {"label": "发邮件", "kind": "mail" | "link", "url": "..."}
        "links": [],
    },
    "appearance": {
        "theme": "default",
        "decor": {"tape": True, "doodles": True},
        "motion": "full",
        "code_theme": "frost",
        "texts": {
            "not_found_title": "这一页走丢了",
            "not_found_text": "是我把它弄丢了，还是你输错了地址？（先说好，才不是我的错。）",
            "error_title": "服务器打了个盹",
            "error_text": "不是你的问题，过一会儿再来试试。",
        },
    },
    "seo": {
        "title": "",
        "description": "",
        "keywords": [],
        "share_image_media_id": None,
        "robots_extra": "",
        "sitemap": {"moments": True, "pages": True, "taxonomy": True},
    },
    "footer": {"icp": "", "copyright": "", "text": SITE_DESCRIPTION},
    "stats": {"enabled": True},
    "backup": {"enabled": True, "hour": 3, "keep": 14},
}

DEFAULT_HOME_BLOCKS: list[dict] = [
    {"type": "hero", "enabled": True, "config": {
        "note": "近况 · 正在把博客重新画一遍",
        "intro": "这里是我的小窝：博客里放认真写的文章，动态里放碎碎念和随手拍的照片。没有评论区——想说什么，请发邮件。",
        "buttons": [
            {"label": "读博客", "url": "/blog", "style": "fill"},
            {"label": "看动态", "url": "/moments", "style": "line"},
        ],
        "doodles": ["star", "heart", "sparkle"],
    }},
    {"type": "notice", "enabled": False, "config": {"text": "", "starts_at": None, "ends_at": None}},
    {"type": "featured", "enabled": False, "config": {"title": "精选", "mode": "auto", "post_ids": [], "count": 3}},
    {"type": "latest_posts", "enabled": True, "config": {
        "title": "最近的文章", "intro": "写得慢，但每一篇都认真改过三遍。", "count": 6, "layout": "mixed",
    }},
    {"type": "latest_moments", "enabled": True, "config": {
        "title": "最近的动态", "intro": "碎碎念、照片、链接，想到什么发什么。", "count": 3,
    }},
]

# (label, kind, target, sticker)
DEFAULT_NAV: dict[str, list[tuple[str, str, str, str | None]]] = {
    "top": [
        ("首页", "route", "/", "home"),
        ("博客", "route", "/blog", "book"),
        ("动态", "route", "/moments", "chat"),
        ("归档", "route", "/archive", "calendar"),
        ("关于", "page", "about", "smile"),
    ],
    "mobile": [
        ("首页", "route", "/", "home"),
        ("博客", "route", "/blog", "book"),
        ("动态", "route", "/moments", "chat"),
        ("搜索", "action", "search", "search"),
        ("更多", "action", "more", "more"),
    ],
    "footer": [
        ("首页", "route", "/", "home"),
        ("博客", "route", "/blog", "book"),
        ("动态", "route", "/moments", "chat"),
        ("归档", "route", "/archive", "calendar"),
    ],
}
