from __future__ import annotations

import json

from app.extensions import db
from app.services.access import save_bound_urls
from app.services.site_management import load_admin_navigation, load_primary_menu


def test_media_pages_menu_and_site_management_routes_render(logged_in_client):
    destinations = {
        "/admin/media/": "<h1>媒体</h1>",
        "/admin/albums/": "相册",
        "/admin/pages/": "页面总览",
        "/admin/pages/system/home/": "编辑首页",
        "/admin/menu/primary/": "前台顶部菜单",
        "/admin/menu/admin-layout/": "左侧菜单排列",
        "/admin/site/identity/": "标题与Logo",
        "/admin/site/footer/": "页尾内容设置",
        "/admin/site/third-party-links/": "第三方链接",
        "/admin/site/addresses/": "网站链接",
        "/admin/site/security/": "安全",
    }
    for path, expected in destinations.items():
        response = logged_in_client.get(path)
        assert response.status_code == 200
        assert expected in response.get_data(as_text=True)


def test_front_pages_only_lists_enabled_navigation_pages_and_saves_copy(app, logged_in_client):
    response = logged_in_client.get("/admin/pages/front/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "导航中的页面" in body
    assert "这里会自动同步当前在前台菜单显示的页面" in body

    saved = logged_in_client.post(
        "/admin/pages/front/",
        data={"page_key": "blog", "title": "新的博客标题", "subtitle": "新的博客副标题"},
        follow_redirects=True,
    )
    assert saved.status_code == 200
    public = logged_in_client.get("/blog/").get_data(as_text=True)
    assert "新的博客标题" in public
    assert "新的博客副标题" in public


def test_front_pages_automatically_follows_visible_primary_menu(app, logged_in_client):
    with app.app_context():
        items = load_primary_menu()
        next(item for item in items if item["target"] == "blog")["visible"] = False
        from app.services.site_management import save_primary_menu

        save_primary_menu(items)
        db.session.commit()

    body = logged_in_client.get("/admin/pages/front/").get_data(as_text=True)
    assert "博客手记" not in body


def test_system_page_text_blocks_and_enabled_state(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/pages/system/blog/",
        data={
            "label": "手记",
            "title": "新的博客标题",
            "subtitle": "新的博客副标题",
            "enabled": "y",
            "nav": "y",
            "block_id": "intro-card",
            "block_title": "置顶介绍",
            "block_content": "这是 **可编辑板块**。",
            "block_style": "note",
            "block_enabled": "intro-card",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    public = logged_in_client.get("/blog/").get_data(as_text=True)
    assert "新的博客标题" in public
    assert "可编辑板块" in public

    disabled = logged_in_client.post("/admin/pages/system/blog/toggle/")
    assert disabled.status_code == 302
    assert logged_in_client.get("/blog/").status_code == 404
    logged_in_client.post("/admin/pages/system/blog/toggle/")
    assert logged_in_client.get("/blog/").status_code == 200


def test_primary_menu_and_admin_layout_are_persisted(app, logged_in_client):
    logged_in_client.post("/admin/menu/primary/", data={"action": "create"})
    with app.app_context():
        item = next(entry for entry in load_primary_menu() if entry["id"].startswith("custom-"))
        item_id = item["id"]
    saved = logged_in_client.post(
        "/admin/menu/primary/",
        data={
            "action": "save",
            "item_id": item_id,
            "label": "温柔入口",
            "target_type": "url",
            "url": "/about/",
            "visible": "y",
        },
    )
    assert saved.status_code == 302
    assert "温柔入口" in logged_in_client.get("/").get_data(as_text=True)

    with app.app_context():
        layout = load_admin_navigation()
    layout["parents"] = list(reversed(layout["parents"]))
    reordered = logged_in_client.post(
        "/admin/menu/admin-layout/", data={"layout": json.dumps(layout)}
    )
    assert reordered.status_code == 302
    with app.app_context():
        assert load_admin_navigation()["parents"][0] == layout["parents"][0]


def test_retired_gateway_group_is_removed_from_legacy_layout(app):
    legacy = {
        "parents": [
            "dashboard",
            "articles",
            "moments",
            "comments",
            "media",
            "pages",
            "menu",
            "site",
            "projects",
            "appearance",
            "notifications",
            "system",
        ],
        "children": {"system": ["status", "gateway-settings", "audit", "about"]},
    }

    with app.app_context():
        layout = load_admin_navigation(json.dumps(legacy))

    assert layout["parents"][-1:] == ["system"]
    assert "gateway" not in layout["parents"]
    assert "gateway" not in layout["children"]
    assert layout["children"]["system"] == ["status", "audit", "about"]


def test_site_identity_footer_and_exact_origins(app, logged_in_client):
    identity = logged_in_client.post(
        "/admin/site/identity/",
        data={
            "site_display_name": "云迹测试站",
            "site_display_tagline": "本地站点管理",
        },
    )
    assert identity.status_code == 302
    identity_body = logged_in_client.get("/admin/site/identity/").get_data(as_text=True)
    assert "网站主标题" in identity_body and "上传与裁剪Logo" in identity_body
    assert "默认搜索描述" not in identity_body and "默认关键词" not in identity_body
    seo_body = logged_in_client.get("/admin/appearance/seo/").get_data(as_text=True)
    assert "默认搜索描述" in seo_body and "默认关键词" in seo_body
    footer = logged_in_client.post(
        "/admin/site/footer/",
        data={
            "description": "一座柔软的小站",
            "copyright": "内容均保存在本地",
            "footer_columns": json.dumps(
                [
                    {
                        "id": "more",
                        "title": "继续看看",
                        "links": [{"label": "关于", "url": "/about/"}],
                    }
                ]
            ),
        },
    )
    assert footer.status_code == 302
    body = logged_in_client.get("/").get_data(as_text=True)
    assert "云迹测试站" in body and "一座柔软的小站" in body

    with app.app_context():
        save_bound_urls("http://localhost\nhttps://example.test:8443")
        db.session.commit()
    assert logged_in_client.get("/", base_url="http://localhost").status_code == 200
    assert logged_in_client.get("/", base_url="http://example.test:8443").status_code == 400
    assert logged_in_client.get("/", base_url="https://example.test:8443").status_code == 200
    with app.app_context():
        save_bound_urls("")
        db.session.commit()
