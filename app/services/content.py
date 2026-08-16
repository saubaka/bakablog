"""Personal content, project and configurable-site helpers."""

from __future__ import annotations

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
    "page_transition_color_start": "#eaf6ff",
    "page_transition_color_middle": "#f9fbff",
    "page_transition_color_end": "#fceef6",
}

DIALOG_STYLE_CHOICES = (
    ("soft", "柔和圆角"),
    ("glass", "轻透玻璃"),
    ("paper", "纸张卡片"),
    ("compact", "紧凑浮层"),
    ("cloud", "云朵气泡"),
    ("outline", "轻线留白"),
)
DIALOG_STYLE_VALUES = frozenset(value for value, _label in DIALOG_STYLE_CHOICES)
DIALOG_SHADOW_CHOICES = (
    ("none", "无阴影"),
    ("light", "轻柔"),
    ("soft", "标准"),
    ("deep", "深层悬浮"),
)
DIALOG_SHADOW_VALUES = frozenset(value for value, _label in DIALOG_SHADOW_CHOICES)
DIALOG_APPEARANCE_DEFAULTS = {
    "dialog_style": "soft",
    "dialog_color_start": "#ffffff",
    "dialog_color_end": "#fff1f7",
    "dialog_accent": "#7eaed0",
    "dialog_radius": "30",
    "dialog_width": "510",
    "dialog_backdrop_blur": "6",
    "dialog_shadow": "soft",
}

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
    ("hero", "欢迎来到我的小世界", 10, 1, "feature"),
    ("posts", "最近写下的东西", 20, 3, "feature"),
    ("projects", "正在发生的小项目", 30, 3, "showcase"),
    ("moments", "最近的生活碎片", 40, 3, "timeline"),
    ("gallery", "装进胶片里的光", 45, 6, "filmstrip"),
    ("about", "关于这个小小星球", 50, 5, "collage"),
    ("links", "相邻的小小星球", 60, 6, "cards"),
    ("cta", "要不要再坐一会儿？", 70, 1, "feature"),
)

HOME_MODULE_LABELS = {
    "hero": "首屏欢迎区",
    "posts": "精选文章",
    "projects": "项目展柜",
    "moments": "生活时间线",
    "gallery": "相册胶片",
    "about": "关于我拼贴",
    "links": "友链与留言",
    "cta": "页尾邀请",
}

HOME_MODULE_ADMIN_META = {
    "hero": {
        "description": "首页最上方的欢迎区、个人头像、此刻状态和三个行动按钮。",
        "source": "下方“首屏内容与按钮”",
        "layout": "固定首屏布局",
        "title_editable": False,
        "quantity_label": None,
        "styles": (),
    },
    "posts": {
        "description": "展示最新公开文章；第一篇为主卡，其余为旁侧小卡。",
        "source": "已发布文章",
        "layout": "精选文章舞台",
        "title_editable": True,
        "quantity_label": "文章数量",
        "styles": (),
    },
    "projects": {
        "description": "展示公开项目作品，可选择横向展柜或规则卡片布局。",
        "source": "已发布项目",
        "layout": "可切换布局",
        "title_editable": True,
        "quantity_label": "项目数量",
        "styles": (
            ("showcase", "横向展柜"),
            ("cards", "卡片网格"),
            ("stack", "层叠作品"),
        ),
    },
    "moments": {
        "description": "以便签时间线展示最近公开的生活动态。",
        "source": "已发布动态",
        "layout": "便签时间线",
        "title_editable": True,
        "quantity_label": "动态数量",
        "styles": (),
    },
    "gallery": {
        "description": "从已发布相册中提取最近照片，形成横向胶片。",
        "source": "已发布相册照片",
        "layout": "横向胶片",
        "title_editable": True,
        "quantity_label": "照片数量",
        "styles": (),
    },
    "about": {
        "description": "组合个人资料、当前状态和技能进度，形成关于我拼贴。",
        "source": "个人资料与技能",
        "layout": "关于我拼贴",
        "title_editable": True,
        "quantity_label": "技能数量",
        "styles": (),
    },
    "links": {
        "description": "展示已审核且启用的友链，并附带最近留言入口。",
        "source": "精选友链与留言",
        "layout": "友链与留言双栏",
        "title_editable": True,
        "quantity_label": "友链数量",
        "styles": (),
    },
    "cta": {
        "description": "首页最下方的行动邀请，标题、说明和按钮在下方单独维护。",
        "source": "下方“页尾邀请与页脚”",
        "layout": "固定页尾邀请",
        "title_editable": False,
        "quantity_label": None,
        "styles": (),
    },
}

HOME_SETTING_DEFAULTS = {
    "hero_title": "把生活写成一册软绵绵的手账。",
    "hero_subtitle": "这里收藏编程、设计和生活里的微小闪光。",
    "hero_tags": "Flask开发 / 设计练习 / 生活记录",
    "hero_status": "正在把这颗小星球装饰得更可爱",
    "hero_primary_label": "读最新文章",
    "hero_primary_url": "/blog/",
    "hero_secondary_label": "认识我",
    "hero_secondary_url": "/about/",
    "hero_explore_label": "随机漫游",
    "hero_explore_url": "/gallery/",
    "about_now": "认真完善这座个人网站",
    "about_tools": "Flask · SQLite · 原生CSS",
    "about_learning": "更细腻的交互与叙事设计",
    "cta_title": "要不要在云朵上留个脚印？",
    "cta_text": "可以继续慢慢读，也可以写下一句话。每一次来访都会让这颗小星球更完整。",
    "cta_button_label": "去留言簿",
    "cta_button_url": "/guestbook/",
    "footer_text": "使用 Flask 与本地资源搭建",
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
