from __future__ import annotations

from app.extensions import db
from app.models import SiteSetting
from app.services.seo import get_seo_settings


def test_seo_admin_settings_render_in_public_head_and_robots(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/appearance/seo/",
        data={
            "site_title": "云迹测试站",
            "title_separator": "·",
            "default_description": "一段可以被搜索服务读取的浅色站点介绍",
            "default_keywords": "云迹,博客",
            "author_name": "sau_baka",
            "default_og_image": "/static/images/avatar-placeholder.svg",
            "og_locale": "zh_CN",
            "twitter_card": "summary_large_image",
            "social_handle": "@cloudtrace",
            "index_site": "y",
            "follow_links": "y",
            "enable_sitemap": "y",
            "enable_feed": "y",
            "enable_structured_data": "y",
            "schema_type": "Person",
            "robots_disallow": "/admin/",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SEO设置" in response.get_data(as_text=True)

    page = logged_in_client.get("/").get_data(as_text=True)
    assert 'name="description" content="一段可以被搜索服务读取的浅色站点介绍"' in page
    assert 'property="og:site_name" content="云迹测试站"' in page
    assert "google-site-verification" not in page
    assert "msvalidate.01" not in page
    assert 'type="application/ld+json"' in page
    robots = logged_in_client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /admin/" in robots
    assert "Sitemap:" in robots


def test_seo_service_uses_local_sqlite(app):
    with app.app_context():
        db.session.add(SiteSetting(setting_key="seo_site_title", setting_value="SQLite SEO"))
        db.session.commit()
        assert get_seo_settings().site_title == "SQLite SEO"


def test_global_themed_controls_and_image_studio_are_loaded(client):
    page = client.get("/").get_data(as_text=True)
    assert "scripts/ui-global.js" in page
    assert "data-image-crop-dialog" in page
    script = client.get("/static/scripts/ui-global.js").get_data(as_text=True)
    assert "enhanceSelect" in script
    assert "data-animated-upload" in script
    assert "is-save-action" in script
