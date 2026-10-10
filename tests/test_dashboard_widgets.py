from __future__ import annotations

import re
from pathlib import Path


def test_dashboard_uses_fixed_full_width_responsive_layout(logged_in_client):
    response = logged_in_client.get("/admin/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="dashboard-fixed-grid"' in body
    assert body.count('class="dashboard-widget ') == 9
    assert "全部文章" in body
    assert "已发布文章" in body
    assert "草稿文章" in body
    assert "待处理互动" in body
    assert "快捷创作" in body
    assert "最近操作" in body
    assert "本地系统状态" in body
    assert "发布完成度" in body
    assert "组件自定义" not in body
    assert "data-dashboard-widget" not in body


def test_dashboard_customization_endpoint_and_assets_are_removed(
    logged_in_client,
):
    assert logged_in_client.get("/admin/dashboard/widgets/").status_code == 404
    base = Path("app/templates/layouts/base.html").read_text(encoding="utf-8")
    assert "dashboard-builder.js" not in base
    assert not Path("app/static/scripts/dashboard-builder.js").exists()
    assert not Path("app/templates/admin/dashboard_widgets.html").exists()
    assert not Path("app/services/dashboard.py").exists()


def test_dashboard_layout_and_navigation_use_lightweight_final_css():
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert ".dashboard-fixed-grid{" in styles
    assert "grid-template-columns:repeat(12,minmax(0,1fr))" in styles
    assert ".dashboard-fixed-grid>.dashboard-widget--metric{grid-column:span 3}" in styles
    assert "@media(max-width:760px)" in styles
    assert "background-image:none!important" in styles
    assert ".admin-subnav__items>div{margin-left:12px;border-left:1px solid #e9f2f7}" in styles
    assert "will-change:grid-template-rows,opacity,transform" in styles


def test_primary_content_menus_expose_direct_children_without_third_level(
    logged_in_client,
):
    routes = (
        ("/admin/", "仪表盘", "仪表盘", 0),
        ("/admin/posts/?status=draft", "文章", "草稿", 0),
        ("/admin/taxonomy/?type=tag", "标签", "标签列表", 0),
        ("/admin/moments/?status=published", "动态", "已发布", 0),
        ("/admin/moderation/?view=comments&status=pending", "评论", "评论", 0),
    )
    for path, parent, child, open_submenus in routes:
        body = logged_in_client.get(path).get_data(as_text=True)
        assert f"<strong>{parent}</strong>" in body
        assert f"<span>{child}</span>" in body or f"<strong>{child}</strong>" in body
        assert (
            body.count('class="admin-nav-group is-open"')
            + body.count('class="admin-nav-group admin-nav-direct is-open"')
            == 1
        )
        assert body.count('class="admin-subnav is-open"') == open_submenus


def test_rendered_admin_submenus_never_wrap_a_single_entry(logged_in_client):
    body = logged_in_client.get("/admin/").get_data(as_text=True)
    submenus = re.findall(
        r'<section class="admin-subnav[^>]*>.*?</section>', body, flags=re.DOTALL
    )
    assert all(submenu.count("<a ") >= 2 for submenu in submenus)
