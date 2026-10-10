"""Site-wide search appearance settings backed by local SQLite."""

from __future__ import annotations

from types import SimpleNamespace

from app.extensions import db
from app.models import SiteSetting

SEO_DEFAULTS = {
    "seo_site_title": "sau_bakaの博客",
    "seo_title_separator": "·",
    "seo_default_description": "记录代码、设计与生活",
    "seo_default_keywords": "个人博客, Flask, 设计, 生活记录",
    "seo_author_name": "sau_baka",
    "seo_default_og_image": "",
    "seo_og_locale": "zh_CN",
    "seo_twitter_card": "summary_large_image",
    "seo_social_handle": "",
    "seo_index_site": "true",
    "seo_follow_links": "true",
    "seo_index_archives": "true",
    "seo_index_taxonomies": "true",
    "seo_enable_sitemap": "true",
    "seo_enable_feed": "true",
    "seo_enable_structured_data": "true",
    "seo_schema_type": "Person",
    "seo_robots_disallow": "/admin/",
}

SEO_SCHEMA_CHOICES = (("Person", "个人站点"), ("Organization", "组织或工作室"))
SEO_TWITTER_CARD_CHOICES = (
    ("summary_large_image", "大图摘要"),
    ("summary", "紧凑摘要"),
)


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_seo_values() -> dict[str, str]:
    rows = db.session.execute(
        db.select(SiteSetting.setting_key, SiteSetting.setting_value).where(
            SiteSetting.setting_key.in_(SEO_DEFAULTS)
        )
    ).all()
    values = dict(SEO_DEFAULTS)
    values.update(rows)
    return values


def get_seo_settings(values: dict[str, str] | None = None) -> SimpleNamespace:
    values = get_seo_values() if values is None else {**SEO_DEFAULTS, **values}
    schema_type = values["seo_schema_type"]
    if schema_type not in {value for value, _label in SEO_SCHEMA_CHOICES}:
        schema_type = SEO_DEFAULTS["seo_schema_type"]
    twitter_card = values["seo_twitter_card"]
    if twitter_card not in {value for value, _label in SEO_TWITTER_CARD_CHOICES}:
        twitter_card = SEO_DEFAULTS["seo_twitter_card"]
    return SimpleNamespace(
        site_title=values["seo_site_title"],
        title_separator=values["seo_title_separator"],
        default_description=values["seo_default_description"],
        default_keywords=values["seo_default_keywords"],
        author_name=values["seo_author_name"],
        default_og_image=values["seo_default_og_image"],
        og_locale=values["seo_og_locale"],
        twitter_card=twitter_card,
        social_handle=values["seo_social_handle"],
        index_site=_as_bool(values["seo_index_site"]),
        follow_links=_as_bool(values["seo_follow_links"]),
        index_archives=_as_bool(values["seo_index_archives"]),
        index_taxonomies=_as_bool(values["seo_index_taxonomies"]),
        enable_sitemap=_as_bool(values["seo_enable_sitemap"]),
        enable_feed=_as_bool(values["seo_enable_feed"]),
        enable_structured_data=_as_bool(values["seo_enable_structured_data"]),
        schema_type=schema_type,
        robots_disallow=tuple(
            line.strip()
            for line in values["seo_robots_disallow"].splitlines()
            if line.strip().startswith("/")
        ),
    )


def save_seo_values(values: dict[str, str]) -> None:
    existing = {
        item.setting_key: item
        for item in db.session.scalars(
            db.select(SiteSetting).where(SiteSetting.setting_key.in_(SEO_DEFAULTS))
        ).all()
    }
    for key, default in SEO_DEFAULTS.items():
        value = str(values.get(key, default)).strip()
        item = existing.get(key)
        if item is None:
            db.session.add(SiteSetting(setting_key=key, setting_value=value))
        else:
            item.setting_value = value
