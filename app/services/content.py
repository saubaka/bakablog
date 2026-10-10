"""Personal content, project and configurable-site helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.extensions import db
from app.models import CustomPage, HomeModule, Moment, Project, SiteSetting
from app.services.blog import make_slug, render_markdown

PAGE_TRANSITION_CHOICES = (
    ("stretch", "左侧拉伸"),
    ("fade", "直接浮现"),
    ("zoom-blur", "缩放与模糊"),
    ("none", "无动画"),
)
PAGE_TRANSITION_VALUES = frozenset(value for value, _label in PAGE_TRANSITION_CHOICES)

PAGE_TRANSITION_COLOR_DEFAULTS = {
    "page_transition_color_start": "#EDF4FC",
    "page_transition_color_middle": "#F7F9FC",
    "page_transition_color_end": "#F7E5ED",
}

COMPONENT_MOTION_STYLE_CHOICES = (
    ("calm", "安静阻尼"),
    ("soft", "柔和阻尼"),
    ("snappy", "利落阻尼"),
)
COMPONENT_MOTION_STYLE_VALUES = frozenset(value for value, _label in COMPONENT_MOTION_STYLE_CHOICES)
COMPONENT_MOTION_LEGACY_STYLES = {
    "clean": "calm",
    "soft-track": "soft",
    "minimal": "snappy",
}
COMPONENT_MOTION_SOFTNESS_CHOICES = (
    ("none", "关闭柔化"),
    ("light", "轻微柔化"),
    ("soft", "柔和浮现"),
)
COMPONENT_MOTION_SOFTNESS_VALUES = frozenset(
    value for value, _label in COMPONENT_MOTION_SOFTNESS_CHOICES
)
COMPONENT_MOTION_DEFAULTS = {
    "component_motion_duration": "760",
    "component_motion_style": "soft",
    "component_motion_color": "#D4E6F3",
    "component_motion_softness": "soft",
}


def normalize_component_motion_style(value: str | None) -> str:
    """Map retired trace presets to the single-line damping profiles."""
    normalized = COMPONENT_MOTION_LEGACY_STYLES.get(value or "", value or "")
    return normalized if normalized in COMPONENT_MOTION_STYLE_VALUES else "soft"


DIALOG_SHADOW_CHOICES = (
    ("none", "无阴影"),
    ("light", "轻柔"),
    ("soft", "标准"),
    ("deep", "深层悬浮"),
)
DIALOG_SHADOW_VALUES = frozenset(value for value, _label in DIALOG_SHADOW_CHOICES)
DIALOG_APPEARANCE_DEFAULTS = {
    "dialog_accent": "#99ABCD",
    "dialog_radius": "22",
    "dialog_width": "510",
    "dialog_backdrop_blur": "6",
    "dialog_shadow": "soft",
    "toast_background": "#FFFFFF",
    "toast_text": "#354052",
    "toast_accent": "#BFD9E8",
    "toast_success": "#78B894",
    "toast_warning": "#C99A4A",
    "toast_error": "#C97676",
    "toast_radius": "28",
    "toast_duration": "5200",
}

# Lighter light-blue scheme (1.43.0): colours that sites stored while they were
# still the old defaults are treated as "never customised" and resolve to the new
# default when read. Nothing is rewritten in the database, and any other saved
# colour is respected unchanged.
LEGACY_DEFAULT_COLORS = {
    "page_transition_color_start": frozenset({"#E5EFFB"}),
    "component_motion_color": frozenset({"#91BED8", "#BFD9E8"}),
    "dialog_accent": frozenset({"#526FA6"}),
    "toast_accent": frozenset({"#91BED8"}),
}


def resolve_color_setting(name: str, stored: str | None, default: str) -> str:
    """Return the stored colour, or the current default for retired defaults."""
    if stored and stored.strip().upper() in LEGACY_DEFAULT_COLORS.get(name, ()):
        return default
    return stored if stored else default


# Top capsule notification motion (project 8 phase five). One JSON setting
# holds every type so a save is a single atomic row; a separate revision
# counter guards the whole overlay form against concurrent edits.
NOTIFICATION_TYPES = ("success", "info", "warning", "error", "loading")
NOTIFICATION_TYPE_LABELS = {
    "success": "成功",
    "info": "信息",
    "warning": "提醒",
    "error": "错误",
    "loading": "处理中",
}
NOTIFICATION_MOTION_FIELDS = (
    ("enter", "进入", 0, 3000),
    ("exit", "退出", 0, 3000),
    ("text_out", "文字退出", 0, 1000),
    ("text_in", "文字进入", 0, 1000),
)
NOTIFICATION_STACK_RANGE = (0, 1500)
NOTIFICATION_MOTION_PRESETS = {
    "fast": {"label": "快速", "enter": 520, "exit": 460, "text_out": 120, "text_in": 240, "stack": 220},
    "standard": {"label": "标准", "enter": 780, "exit": 680, "text_out": 160, "text_in": 340, "stack": 320},
    "relaxed": {"label": "舒缓", "enter": 1040, "exit": 900, "text_out": 200, "text_in": 440, "stack": 420},
}
NOTIFICATION_MOTION_SETTING = "notification_motion"
OVERLAY_REVISION_SETTING = "overlay_settings_revision"


def default_notification_motion() -> dict:
    preset = NOTIFICATION_MOTION_PRESETS["standard"]
    return {
        "schema": 1,
        "types": {
            kind: {name: preset[name] for name, _label, _low, _high in NOTIFICATION_MOTION_FIELDS}
            for kind in NOTIFICATION_TYPES
        },
        "stack": preset["stack"],
    }


def _bounded_int(value: object, low: int, high: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def parse_notification_motion(raw: str | None) -> dict:
    """Read the stored JSON; anything missing or invalid uses the default.

    Reading never writes back, so a damaged row cannot silently become the
    saved configuration.
    """
    config = default_notification_motion()
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return config
    if not isinstance(data, dict):
        return config
    types = data.get("types") if isinstance(data.get("types"), dict) else {}
    for kind in NOTIFICATION_TYPES:
        values = types.get(kind) if isinstance(types.get(kind), dict) else {}
        for name, _label, low, high in NOTIFICATION_MOTION_FIELDS:
            number = _bounded_int(values.get(name), low, high)
            if number is not None:
                config["types"][kind][name] = number
    stack = _bounded_int(data.get("stack"), *NOTIFICATION_STACK_RANGE)
    if stack is not None:
        config["stack"] = stack
    return config


def _loose_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def notification_motion_from_form(form) -> tuple[dict, list[str]]:
    """Validate the posted fields strictly; out-of-range values are errors.

    The returned config is only persisted when there are no errors. When the
    form is rejected it still carries what the administrator typed so the
    page can show the draft again instead of resetting it.
    """
    config = default_notification_motion()
    errors: list[str] = []
    for kind in NOTIFICATION_TYPES:
        for name, label, low, high in NOTIFICATION_MOTION_FIELDS:
            raw = form.get(f"notice_{kind}_{name}", "")
            number = _bounded_int(raw, low, high)
            if number is None:
                errors.append(f"{NOTIFICATION_TYPE_LABELS[kind]}通知的{label}需要是 {low}–{high} 毫秒之间的整数。")
                number = _loose_int(raw)
            if number is not None:
                config["types"][kind][name] = number
    stack = _bounded_int(form.get("notice_stack", ""), *NOTIFICATION_STACK_RANGE)
    if stack is None:
        errors.append(f"堆叠过渡需要是 {NOTIFICATION_STACK_RANGE[0]}–{NOTIFICATION_STACK_RANGE[1]} 毫秒之间的整数。")
        stack = _loose_int(form.get("notice_stack", ""))
    if stack is not None:
        config["stack"] = stack
    return config, errors


def notification_motion_json(config: dict) -> str:
    return json.dumps(config, separators=(",", ":"), sort_keys=True)


GLOBAL_FONT_CHOICES = (
    ("cloud-rounded", "云朵圆体"),
    ("candy-soft", "糖霜柔体"),
    ("playful-yuan", "软糖幼圆"),
    ("diary-serif", "手账宋体"),
    ("starlight-kaiti", "星光楷体"),
    ("neumorphic-clean", "清透拟态"),
)
GLOBAL_FONT_VALUES = frozenset(value for value, _label in GLOBAL_FONT_CHOICES)

DEFAULT_MODULES = (
    ("hero", "首页首屏", 10, 1, "feature"),
    ("posts", "最近文章", 20, 3, "feature"),
    ("projects", "项目", 30, 3, "showcase"),
    ("moments", "动态", 40, 3, "timeline"),
    ("gallery", "相册", 45, 6, "filmstrip"),
    ("about", "关于 sau_baka", 50, 5, "collage"),
    ("links", "常去的网站", 60, 6, "cards"),
    ("cta", "留言", 70, 1, "feature"),
)

LEGACY_HOME_MODULE_TITLES = {
    "posts": {"最近写下的东西"},
    "projects": {"正在发生的小项目"},
    "moments": {"最近的生活碎片"},
    "gallery": {"装进胶片里的光"},
    "about": {"关于我", "关于这个小小星球"},
    "links": {"友链与留言", "相邻的小小星球"},
    "cta": {"要不要再坐一会儿？"},
}

HOME_MODULE_DEFAULT_TITLES = {key: title for key, title, *_rest in DEFAULT_MODULES}

HOME_MODULE_LABELS = {
    "hero": "首屏介绍",
    "posts": "文章",
    "projects": "项目",
    "moments": "动态",
    "gallery": "相册",
    "about": "关于",
    "links": "友链",
    "cta": "留言",
}

HOME_MODULE_ADMIN_META = {
    "hero": {
        "description": "首页最上方的个人介绍、头像、当前重点和两个主要按钮。",
        "source": "下方“首屏内容与按钮”",
        "layout": "单一介绍表面",
        "title_editable": False,
        "quantity_label": None,
        "styles": (),
    },
    "posts": {
        "description": "展示最新公开文章；第一篇展开呈现，其余文章按行排列。",
        "source": "已发布文章",
        "layout": "编辑式文章列表",
        "title_editable": True,
        "quantity_label": "文章数量",
        "styles": (),
    },
    "projects": {
        "description": "展示公开项目；第一项为主项目，其余项目使用紧凑链接。",
        "source": "已发布项目",
        "layout": "主项目与项目索引",
        "title_editable": True,
        "quantity_label": "项目数量",
        "styles": (),
    },
    "moments": {
        "description": "以轻量时间线展示最近公开的动态。没有内容时不占据首页空间。",
        "source": "已发布动态",
        "layout": "文字时间线",
        "title_editable": True,
        "quantity_label": "动态数量",
        "styles": (),
    },
    "gallery": {
        "description": "从已发布相册中提取最近照片。没有内容时不占据首页空间。",
        "source": "已发布相册照片",
        "layout": "疏密图片网格",
        "title_editable": True,
        "quantity_label": "照片数量",
        "styles": (),
    },
    "about": {
        "description": "将个人简介与当前状态分成两个清晰区域。",
        "source": "个人资料与技能",
        "layout": "简介与事实双栏",
        "title_editable": True,
        "quantity_label": "技能数量",
        "styles": (),
    },
    "links": {
        "description": "展示已审核且启用的友链；留言入口统一放在页尾。",
        "source": "精选友链",
        "layout": "简洁友链列表",
        "title_editable": True,
        "quantity_label": "友链数量",
        "styles": (),
    },
    "cta": {
        "description": "首页最下方唯一的留言入口，标题、说明和按钮在下方维护。",
        "source": "下方“页尾邀请与页脚”",
        "layout": "页尾留言条",
        "title_editable": False,
        "quantity_label": None,
        "styles": (),
    },
}

HOME_SETTING_DEFAULTS = {
    "hero_title": "sau_baka，正在做 Cloudtrace",
    "hero_subtitle": "记录 Flask 开发、界面设计和偶尔拍下的照片。",
    "hero_tags": "Flask / 界面练习 / 日常记录",
    "hero_status": "继续完善这个个人网站",
    "hero_primary_label": "最近文章",
    "hero_primary_url": "/blog/",
    "hero_secondary_label": "认识我",
    "hero_secondary_url": "/about/",
    "hero_explore_label": "看看相册",
    "hero_explore_url": "/gallery/",
    "about_now": "完善 Cloudtrace 的内容与交互",
    "about_tools": "Flask、SQLite、原生 CSS",
    "about_learning": "前端交互与内容设计",
    "cta_title": "想说点什么？",
    "cta_text": "可以在留言簿里留下问题、建议或一句问候。",
    "cta_button_label": "去留言簿",
    "cta_button_url": "/guestbook/",
    "footer_text": "使用 Flask 与本地资源搭建",
}

LEGACY_HOME_SETTING_VALUES = {
    "hero_title": {"在代码、设计和日常之间"},
    "hero_subtitle": {"这里放着我正在做的项目、读过的东西，还有偶尔写下的几句。"},
    "hero_status": {"在做网站，也在记一些小事"},
    "hero_primary_label": {"读最新文章"},
    "hero_explore_label": {"打开相册"},
    "cta_title": {"如果你也刚好路过"},
    "cta_text": {"随便看看；有想说的话，留在留言簿里就好。"},
    "about_now": {"认真完善这座个人网站"},
    "about_tools": {"Flask · SQLite · 原生CSS"},
    "about_learning": {"更细腻的交互与叙事设计"},
}


def safe_content_url(value: str, allow_empty: bool = True) -> str:
    url = value.strip()
    if not url and allow_empty:
        return ""
    parsed = urlsplit(url)
    if url.startswith("/") or parsed.scheme in {"http", "https", "mailto"}:
        return url
    raise ValueError("链接必须是站内绝对路径，或使用 http、https、mailto 协议。")


def unique_slug(model, value: str, item_id: int | None = None) -> str:  # type: ignore[no-untyped-def]
    base = make_slug(value, "page")
    candidate = base
    counter = 2
    while db.session.scalar(
        db.select(model.id).where(model.slug == candidate, model.id != (item_id or -1))
    ):
        candidate = f"{base[:150]}-{counter}"
        counter += 1
    return candidate


def apply_project_form(project: Project, form) -> None:  # type: ignore[no-untyped-def]
    html, _, _ = render_markdown(form.content_markdown.data)
    project.title = form.title.data.strip()
    project.slug = unique_slug(Project, form.slug.data or project.title, project.id)
    project.summary = (form.summary.data or "").strip()
    project.content_markdown = form.content_markdown.data
    project.content_html = html
    project.tech_stack = (form.tech_stack.data or "").strip()
    project.project_url = safe_content_url(form.project_url.data or "")
    project.repository_url = safe_content_url(form.repository_url.data or "")
    project.cover_media_id = form.cover_media_id.data or None
    project.status = form.status.data
    project.is_featured = bool(form.is_featured.data)
    project.sort_order = form.sort_order.data or 0
    project.published_at = (
        project.published_at or datetime.now(UTC) if project.status == "published" else None
    )


def apply_moment_form(moment: Moment, form) -> None:  # type: ignore[no-untyped-def]
    html, _, _ = render_markdown(form.content_markdown.data)
    moment.content_markdown = form.content_markdown.data
    moment.content_html = html
    moment.mood = (form.mood.data or "晴朗").strip()
    moment.location = (form.location.data or "").strip()
    moment.status = form.status.data
    moment.is_pinned = bool(form.is_pinned.data)
    moment.allow_comments = bool(form.allow_comments.data)
    moment.published_at = (
        moment.published_at or datetime.now(UTC) if moment.status == "published" else None
    )


def apply_page_form(page: CustomPage, form) -> None:  # type: ignore[no-untyped-def]
    html, _, _ = render_markdown(form.content_markdown.data)
    page.title = form.title.data.strip()
    page.slug = unique_slug(CustomPage, form.slug.data or page.title, page.id)
    page.summary = (form.summary.data or "").strip()
    page.content_markdown = form.content_markdown.data
    page.content_html = html
    page.status = form.status.data
    page.show_in_navigation = bool(form.show_in_navigation.data)
    page.sort_order = form.sort_order.data or 0


def public_project_condition():  # type: ignore[no-untyped-def]
    return db.and_(Project.status == "published", Project.deleted_at.is_(None))


def public_moment_condition():  # type: ignore[no-untyped-def]
    return db.and_(Moment.status == "published", Moment.deleted_at.is_(None))


def get_home_modules():
    stored = sync_default_home_modules()
    return sorted(
        (module for module in stored if module.is_enabled),
        key=lambda module: module.sort_order,
    )


def sync_default_home_modules() -> list[HomeModule]:
    """Persist newly introduced modules without changing existing choices."""

    modules = db.session.scalars(db.select(HomeModule).order_by(HomeModule.sort_order)).all()
    existing = {module.module_key for module in modules}
    added = False
    for key, title, order, limit, style in DEFAULT_MODULES:
        if key in existing:
            continue
        db.session.add(
            HomeModule(
                module_key=key,
                title=title,
                sort_order=order,
                item_limit=limit,
                style_variant=style,
            )
        )
        added = True
    if added:
        db.session.commit()
        modules = db.session.scalars(db.select(HomeModule).order_by(HomeModule.sort_order)).all()
    return [module for module in modules if module.module_key in HOME_MODULE_ADMIN_META]


def get_setting(key: str, default: str = "") -> str:
    setting = db.session.scalar(db.select(SiteSetting).where(SiteSetting.setting_key == key))
    return setting.setting_value if setting else default


def get_settings(defaults: dict[str, str]) -> dict[str, str]:
    """Fetch several site settings in one indexed query."""

    rows = db.session.execute(
        db.select(SiteSetting.setting_key, SiteSetting.setting_value).where(
            SiteSetting.setting_key.in_(defaults)
        )
    ).all()
    values = dict(defaults)
    values.update(rows)
    return values


def set_setting(key: str, value: str) -> SiteSetting:
    setting = db.session.scalar(db.select(SiteSetting).where(SiteSetting.setting_key == key))
    if setting is None:
        setting = SiteSetting(setting_key=key)
        db.session.add(setting)
    setting.setting_value = value.strip()
    return setting
