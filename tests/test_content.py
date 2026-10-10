from __future__ import annotations

from datetime import UTC, datetime

from app.extensions import db
from app.models import (
    CustomPage,
    HomeModule,
    Moment,
    NavigationItem,
    PersonalSkill,
    Post,
    Project,
    SiteProfile,
    SiteSetting,
    SocialLink,
)
from app.services.blog import render_markdown
from app.services.cache import home_content_cache


def _home_post(author_id: int, title: str, slug: str) -> Post:
    markdown = f"## {title}\n\n这是用于首页内容状态验收的正文。"
    html, toc, minutes = render_markdown(markdown)
    return Post(
        title=title,
        slug=slug,
        summary=f"{title}的摘要",
        content_markdown=markdown,
        content_html=html,
        toc_html=toc,
        status="published",
        published_at=datetime.now(UTC),
        reading_minutes=minutes,
        author_id=author_id,
    )


def test_home_has_empty_solo_and_ready_content_states(app, client, admin_user):
    empty_home = client.get("/").get_data(as_text=True)
    assert "content-state--empty" in empty_home
    with app.app_context():
        db.session.add(_home_post(admin_user, "第一篇首页手记", "home-note-one"))
        db.session.commit()
        home_content_cache.clear()
    solo_home = client.get("/").get_data(as_text=True)
    assert "content-state--solo" in solo_home
    with app.app_context():
        db.session.add(_home_post(admin_user, "第二篇首页手记", "home-note-two"))
        db.session.commit()
        home_content_cache.clear()
    ready_home = client.get("/").get_data(as_text=True)
    assert "content-state--ready" in ready_home
    assert "第一篇首页手记" in ready_home
    assert "第二篇首页手记" in ready_home


def test_home_replaces_only_legacy_default_titles_without_mutating_storage(app, client):
    client.get("/")
    with app.app_context():
        posts_module = HomeModule.query.filter_by(module_key="posts").one()
        posts_module.title = "最近写下的东西"
        db.session.commit()
        home_content_cache.clear()

    legacy_home = client.get("/").get_data(as_text=True)
    assert "最近文章" in legacy_home
    assert "最近写下的东西" not in legacy_home
    with app.app_context():
        assert HomeModule.query.filter_by(module_key="posts").one().title == "最近写下的东西"

        posts_module = HomeModule.query.filter_by(module_key="posts").one()
        posts_module.title = "我的文章"
        db.session.commit()
        home_content_cache.clear()

    custom_home = client.get("/").get_data(as_text=True)
    assert "我的文章" in custom_home


def test_home_omits_empty_moment_and_gallery_region_for_every_admin_ordering(app, client):
    """Empty daily modules do not reserve a large placeholder region."""

    def render(*, moments: bool, gallery: bool, gallery_first: bool) -> str:
        with app.app_context():
            moments_module = HomeModule.query.filter_by(module_key="moments").one()
            gallery_module = HomeModule.query.filter_by(module_key="gallery").one()
            moments_module.is_enabled = moments
            gallery_module.is_enabled = gallery
            moments_module.sort_order, gallery_module.sort_order = (
                (60, 50) if gallery_first else (50, 60)
            )
            db.session.commit()
            home_content_cache.clear()
        response = client.get("/")
        assert response.status_code == 200
        return response.get_data(as_text=True)

    client.get("/")  # materialise the default module rows

    for gallery_first in (False, True):
        both = render(moments=True, gallery=True, gallery_first=gallery_first)
        assert "home-daily" not in both

    moments_only = render(moments=True, gallery=False, gallery_first=False)
    assert "home-daily" not in moments_only

    gallery_only = render(moments=False, gallery=True, gallery_first=False)
    assert "home-daily" not in gallery_only

    neither = render(moments=False, gallery=False, gallery_first=False)
    assert "home-daily" not in neither


def test_profile_and_personal_items_are_managed(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/profile/",
        data={
            "display_name": "小岚",
            "headline": "独立开发者与写作者",
            "location": "杭州",
            "email": "hello@example.com",
            "short_bio": "把复杂的事情慢慢整理清楚。",
            "bio_markdown": "## 你好\n\n这是我的详细介绍。",
            "resume_url": "/pages/resume/",
            "avatar_media_id": "0",
        },
        follow_redirects=True,
    )
    assert "个人资料已经保存" in response.get_data(as_text=True)
    logged_in_client.post(
        "/admin/profile/items/",
        data={
            "item_type": "skill",
            "title": "Python",
            "subtitle": "开发技能",
            "description": "",
            "level": "92",
            "sort_order": "1",
            "is_visible": "y",
        },
    )
    logged_in_client.post(
        "/admin/profile/items/",
        data={
            "item_type": "social",
            "title": "GitHub",
            "subtitle": "https://example.com/profile",
            "description": "",
            "level": "80",
            "sort_order": "2",
            "is_visible": "y",
        },
    )
    with app.app_context():
        assert db.session.scalar(db.select(SiteProfile)).display_name == "小岚"
        skill = db.session.scalar(db.select(PersonalSkill))
        assert skill.level == 92
        skill_id = skill.id
        assert db.session.scalar(db.select(SocialLink)).url == "https://example.com/profile"
    logged_in_client.post(
        f"/admin/profile/items/skill/{skill_id}/edit/",
        data={
            "item_type": "skill",
            "title": "Python 与 Flask",
            "subtitle": "开发技能",
            "period": "",
            "description": "",
            "level": "95",
            "sort_order": "1",
            "is_visible": "y",
        },
    )
    about = logged_in_client.get("/about/").get_data(as_text=True)
    assert "小岚" in about
    assert "Python 与 Flask" in about
    assert "GitHub" in about


def test_unsafe_social_link_is_rejected(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/profile/items/",
        data={
            "item_type": "social",
            "title": "危险链接",
            "subtitle": "javascript:alert(1)",
            "description": "",
            "level": "80",
            "sort_order": "0",
            "is_visible": "y",
        },
        follow_redirects=True,
    )
    assert "链接必须是站内绝对路径" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(SocialLink)) is None


def test_project_workflow_and_public_visibility(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/projects/new/",
        data={
            "title": "云朵清单",
            "slug": "cloud-list",
            "summary": "一个轻盈的本地清单项目。",
            "content_markdown": "## 项目缘起\n\n使用 Flask 构建。",
            "tech_stack": "Flask, SQLite",
            "project_url": "https://example.com/demo",
            "repository_url": "",
            "cover_media_id": "0",
            "status": "published",
            "is_featured": "y",
            "sort_order": "1",
        },
        follow_redirects=True,
    )
    assert "项目作品已经保存" in response.get_data(as_text=True)
    public = logged_in_client.get("/projects/cloud-list/")
    assert public.status_code == 200
    assert "项目缘起" in public.get_data(as_text=True)
    with app.app_context():
        project = db.session.scalar(db.select(Project).where(Project.slug == "cloud-list"))
        project_id = project.id
        assert project.published_at is not None
    logged_in_client.post(f"/admin/projects/{project_id}/delete/")
    assert logged_in_client.get("/projects/cloud-list/").status_code == 404
    logged_in_client.post(f"/admin/projects/{project_id}/restore/")
    assert logged_in_client.get("/projects/cloud-list/").status_code == 200


def test_draft_project_is_hidden(app, logged_in_client):
    logged_in_client.post(
        "/admin/projects/new/",
        data={
            "title": "秘密项目",
            "slug": "secret-project",
            "summary": "",
            "content_markdown": "尚未完成",
            "tech_stack": "Python",
            "project_url": "",
            "repository_url": "",
            "cover_media_id": "0",
            "status": "draft",
            "sort_order": "0",
        },
    )
    assert logged_in_client.get("/projects/secret-project/").status_code == 404
    assert "秘密项目" not in logged_in_client.get("/projects/").get_data(as_text=True)


def test_moment_workflow(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/moments/new/",
        data={
            "content_markdown": "今天把 **动态页面** 做好了。",
            "mood": "开心",
            "location": "书桌前",
            "status": "published",
            "is_pinned": "y",
        },
        follow_redirects=True,
    )
    assert "动态已经保存" in response.get_data(as_text=True)
    with app.app_context():
        moment = db.session.scalar(db.select(Moment))
        moment_id = moment.id
        assert "<strong>动态页面</strong>" in moment.content_html
    listing = logged_in_client.get("/moments/").get_data(as_text=True)
    assert "动态页面" in listing
    assert "开心" in listing
    assert logged_in_client.get(f"/moments/{moment_id}/").status_code == 200


def test_home_modules_settings_and_navigation(app, logged_in_client):
    page = logged_in_client.get("/admin/site-content/")
    assert page.status_code == 200
    page_text = page.get_data(as_text=True)
    assert "首页模块编排" in page_text
    assert "按“文案" not in page_text
    assert "站点速览" not in page_text
    assert "打开真实弹窗预览" not in page_text
    with app.app_context():
        posts_module = db.session.scalar(
            db.select(HomeModule).where(HomeModule.module_key == "posts")
        )
        module_id = posts_module.id
        assert db.session.scalar(db.select(db.func.count()).select_from(HomeModule)) == 8
    logged_in_client.post(
        "/admin/site-content/",
        data={
            "hero_title": "欢迎来到软绵绵星球",
            "hero_subtitle": "这里收藏认真生活的证据。",
            "hero_tags": "Flask / 设计 / 日常",
            "hero_status": "正在完成首页2.0",
            "hero_primary_label": "读手记",
            "hero_primary_url": "/blog/",
            "hero_secondary_label": "认识我",
            "hero_secondary_url": "/about/",
            "hero_explore_label": "看胶片",
            "hero_explore_url": "/gallery/",
            "about_now": "测试新的首页",
            "about_tools": "Flask · SQLite",
            "about_learning": "物理动效",
            "cta_title": "来留一句话吧",
            "cta_text": "每一次来访都很珍贵。",
            "cta_button_label": "去留言",
            "cta_button_url": "/guestbook/",
            "footer_text": "全部内容保存在本地",
        },
    )
    module_response = logged_in_client.post(
        f"/admin/site-content/modules/{module_id}/",
        data={
            "title": "隐藏的文章区",
            "sort_order": "20",
            "item_limit": "4",
            "style_variant": "compact",
        },
    )
    assert "section=content#home-modules" in module_response.location
    navigation_response = logged_in_client.post(
        "/admin/site-content/navigation/",
        data={
            "label": "使用说明",
            "url": "/pages/guide/",
            "location": "footer",
            "sort_order": "1",
            "is_visible": "y",
        },
    )
    assert "section=navigation#home-navigation" in navigation_response.location
    home = logged_in_client.get("/").get_data(as_text=True)
    assert "欢迎来到软绵绵星球" in home
    assert "正在完成首页2.0" in home
    assert "来留一句话吧" in home
    assert "albums" not in home
    assert "隐藏的文章区" not in home
    assert "使用说明" in home
    with app.app_context():
        assert (
            db.session.scalar(
                db.select(SiteSetting).where(SiteSetting.setting_key == "footer_text")
            ).setting_value
            == "全部内容保存在本地"
        )
        navigation = db.session.scalar(db.select(NavigationItem))
        assert navigation.location == "footer"
        navigation_id = navigation.id
    logged_in_client.post(
        f"/admin/site-content/navigation/{navigation_id}/",
        data={
            "label": "站点指南",
            "url": "/pages/guide/",
            "location": "both",
            "sort_order": "2",
            "is_visible": "y",
        },
    )
    assert "站点指南" in logged_in_client.get("/").get_data(as_text=True)


def test_home_content_and_navigation_are_separate_focused_admin_views(logged_in_client):
    content_body = logged_in_client.get("/admin/site-content/?section=content").get_data(
        as_text=True
    )
    navigation_body = logged_in_client.get("/admin/site-content/?section=navigation").get_data(
        as_text=True
    )

    assert "<h1>首页内容</h1>" in content_body
    assert "首页模块编排" in content_body
    assert "自定义导航链接" not in content_body
    assert "<h1>导航菜单</h1>" in navigation_body
    assert "自定义导航链接" in navigation_body
    assert "首页模块编排" not in navigation_body


def test_home_navigation_rejects_blank_edit_label(app, logged_in_client):
    logged_in_client.post(
        "/admin/site-content/navigation/",
        data={
            "label": "使用说明",
            "url": "/pages/guide/",
            "location": "footer",
            "sort_order": "10",
            "is_visible": "y",
        },
    )
    with app.app_context():
        item = db.session.scalar(db.select(NavigationItem))
        item_id = item.id
    response = logged_in_client.post(
        f"/admin/site-content/navigation/{item_id}/",
        data={"label": "   ", "url": "/pages/guide/", "location": "footer"},
        follow_redirects=True,
    )
    assert "导航名称不能为空" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(NavigationItem, item_id).label == "使用说明"


def test_custom_page_publication_and_navigation(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/pages/new/",
        data={
            "title": "现在",
            "slug": "now",
            "summary": "最近正在做的事情",
            "content_markdown": "## 此刻\n\n认真搭建个人网站。",
            "status": "published",
            "show_in_navigation": "y",
            "sort_order": "1",
        },
        follow_redirects=True,
    )
    assert "独立页面已经保存" in response.get_data(as_text=True)
    page = logged_in_client.get("/pages/now/")
    assert page.status_code == 200
    assert "认真搭建个人网站" in page.get_data(as_text=True)
    assert "现在" in logged_in_client.get("/").get_data(as_text=True)
    assert "/pages/now/" in logged_in_client.get("/sitemap.xml").get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(CustomPage)).show_in_navigation is True


def test_custom_page_uses_shared_visual_editor_and_autosaves(app, logged_in_client):
    html, _, _ = render_markdown("## 原页面\n\n原始正文。")
    with app.app_context():
        page = CustomPage(
            title="页面编辑器验收",
            slug="page-editor-check",
            summary="原始摘要",
            content_markdown="## 原页面\n\n原始正文。",
            content_html=html,
            status="draft",
        )
        db.session.add(page)
        db.session.commit()
        page_id = page.id

    response = logged_in_client.get(f"/admin/pages/{page_id}/edit/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "data-content-editor-form" in body
    assert 'data-editor-entity="页面"' in body
    assert "data-visual-editor" in body
    assert 'data-editor-source="true"' in body
    assert 'data-editor-mode="preview"' in body
    assert 'data-open-dialog="editor-media-dialog"' in body
    assert "data-image-width" in body
    assert 'data-autosave-url="/admin/api/pages/' in body
    assert "页面大纲" in body
    assert "发布与导航" in body

    autosave = logged_in_client.post(
        f"/admin/api/pages/{page_id}/autosave/",
        json={
            "title": "自动保存后的页面",
            "summary": "自动保存摘要",
            "content_markdown": "<h2>自动保存</h2><p>新的页面正文。</p>",
        },
    )
    assert autosave.status_code == 200
    assert autosave.get_json()["ok"] is True
    with app.app_context():
        saved_page = db.session.get(CustomPage, page_id)
        assert saved_page.title == "自动保存后的页面"
        assert saved_page.summary == "自动保存摘要"
        assert "新的页面正文" in saved_page.content_html


def test_page_transition_setting_is_managed_and_exposed_globally(app, logged_in_client):
    settings_page = logged_in_client.get("/admin/appearance/transitions/")
    assert settings_page.status_code == 200
    assert "左侧拉伸" in settings_page.get_data(as_text=True)
    assert "缩放与模糊" in settings_page.get_data(as_text=True)

    response = logged_in_client.post(
        "/admin/appearance/transitions/",
        data={
            "transition_style": "zoom-blur",
            "transition_duration": "1080",
            "transition_color_start": "#dff3ff",
            "transition_color_middle": "#ffffff",
            "transition_color_end": "#ffe7f1",
            "component_motion_duration": "1040",
            "component_motion_style": "snappy",
            "component_motion_color": "#8fbcd6",
            "component_motion_softness": "light",
        },
        follow_redirects=True,
    )
    assert "全站页面过渡方式已经更新" in response.get_data(as_text=True)
    assert 'data-page-transition="zoom-blur"' in logged_in_client.get("/").get_data(as_text=True)
    assert 'data-transition-duration="1080"' in logged_in_client.get("/").get_data(as_text=True)
    home = logged_in_client.get("/").get_data(as_text=True)
    assert 'data-transition-color-start="#dff3ff"' in home
    assert 'data-transition-color-middle="#ffffff"' in home
    assert 'data-transition-color-end="#ffe7f1"' in home
    assert 'data-component-motion-duration="1040"' in home
    assert 'data-component-motion-style="snappy"' in home
    assert 'data-component-motion-color="#8fbcd6"' in home
    assert "data-component-motion-accent" not in home
    assert 'data-component-motion-softness="light"' in home
    with app.app_context():
        settings = {
            item.setting_key: item.setting_value
            for item in db.session.scalars(db.select(SiteSetting)).all()
        }
        assert settings["page_transition_style"] == "zoom-blur"
        assert settings["page_transition_duration"] == "1080"
        assert settings["page_transition_color_start"] == "#dff3ff"
        assert settings["page_transition_color_middle"] == "#ffffff"
        assert settings["page_transition_color_end"] == "#ffe7f1"
        assert settings["component_motion_duration"] == "1040"
        assert settings["component_motion_style"] == "snappy"
        assert settings["component_motion_color"] == "#8fbcd6"
        assert "component_motion_accent" not in settings
        assert settings["component_motion_softness"] == "light"


def _overlay_form(page_text: str, **overrides: str) -> dict[str, str]:
    import re

    data = {
        "revision": re.search(r'name="revision"[^>]*value="(\d+)"', page_text).group(1),
        "dialog_accent": "#88b9d8",
        "dialog_radius": "36",
        "dialog_width": "620",
        "dialog_backdrop_blur": "12",
        "dialog_shadow": "deep",
        "toast_background": "#ffffff",
        "toast_text": "#354052",
        "toast_accent": "#91bed8",
        "toast_success": "#78b894",
        "toast_warning": "#c99a4a",
        "toast_error": "#c97676",
        "toast_radius": "24",
        "toast_duration": "4600",
        "notice_stack": "260",
    }
    for kind in ("success", "info", "warning", "error", "loading"):
        data.update({
            f"notice_{kind}_enter": "780",
            f"notice_{kind}_exit": "680",
            f"notice_{kind}_text_out": "160",
            f"notice_{kind}_text_in": "340",
        })
    data.update(overrides)
    return data


def test_dialog_appearance_is_categorized_managed_and_exposed(app, logged_in_client):
    import json

    settings_page = logged_in_client.get("/admin/appearance/dialogs/")
    assert settings_page.status_code == 200
    page_text = settings_page.get_data(as_text=True)
    for label in ("通知动效", "快速", "标准", "舒缓", "处理中转成功", "弹窗预览"):
        assert label in page_text
    # Retired presets whose gradients no longer reach the white surfaces.
    for label in ("轻透玻璃", "纸张卡片", "云朵气泡"):
        assert label not in page_text

    response = logged_in_client.post(
        "/admin/appearance/dialogs/",
        data=_overlay_form(page_text, notice_error_enter="1200", notice_loading_text_in="500"),
        follow_redirects=True,
    )
    assert "全站弹窗与通知设置已经更新" in response.get_data(as_text=True)
    home = logged_in_client.get("/").get_data(as_text=True)
    for attribute in ('data-dialog-accent="#88b9d8"', 'data-dialog-radius="36"', 'data-dialog-width="620"',
                      'data-dialog-backdrop-blur="12"', 'data-dialog-shadow="deep"',
                      'data-toast-background="#ffffff"', 'data-toast-duration="4600"'):
        assert attribute in home
    assert "data-dialog-style=" not in home
    with app.app_context():
        settings = {
            item.setting_key: item.setting_value
            for item in db.session.scalars(db.select(SiteSetting)).all()
        }
        assert settings["dialog_radius"] == "36"
        assert settings["overlay_settings_revision"] == "1"
        motion = json.loads(settings["notification_motion"])
        assert motion["types"]["error"]["enter"] == 1200
        assert motion["types"]["loading"]["text_in"] == 500
        assert motion["stack"] == 260
    assert "&#34;enter&#34;:1200" in home or '"enter":1200' in home


def test_dialog_settings_reject_stale_revision_and_invalid_motion(app, logged_in_client):
    page_text = logged_in_client.get("/admin/appearance/dialogs/").get_data(as_text=True)
    stale = _overlay_form(page_text)
    assert logged_in_client.post("/admin/appearance/dialogs/", data=stale).status_code == 302
    # A second tab still holds the old revision: nothing is overwritten and
    # the submitted draft stays on the page.
    conflict = logged_in_client.post(
        "/admin/appearance/dialogs/", data={**stale, "dialog_radius": "18", "notice_info_enter": "999"}
    )
    body = conflict.get_data(as_text=True)
    assert conflict.status_code == 409
    assert "在别处更新过" in body
    assert 'value="999"' in body
    with app.app_context():
        assert db.session.scalar(db.select(SiteSetting.setting_value).where(SiteSetting.setting_key == "dialog_radius")) == "36"
    fresh = logged_in_client.get("/admin/appearance/dialogs/").get_data(as_text=True)
    invalid = logged_in_client.post(
        "/admin/appearance/dialogs/", data=_overlay_form(fresh, notice_warning_exit="4000")
    )
    assert invalid.status_code == 400
    assert "提醒通知的退出需要是 0–3000 毫秒之间的整数" in invalid.get_data(as_text=True)
    assert 'value="4000"' in invalid.get_data(as_text=True)
    with app.app_context():
        revision = db.session.scalar(db.select(SiteSetting.setting_value).where(SiteSetting.setting_key == "overlay_settings_revision"))
        assert revision == "1"


def test_damaged_notification_motion_falls_back_without_writing(app, client):
    from app.services.content import set_setting

    with app.app_context():
        set_setting("notification_motion", "{not json")
        db.session.commit()
    home = client.get("/").get_data(as_text=True)
    assert "data-notice-motion=" in home and "780" in home
    with app.app_context():
        stored = db.session.scalar(db.select(SiteSetting.setting_value).where(SiteSetting.setting_key == "notification_motion"))
        assert stored == "{not json"


def test_interface_font_and_admin_menu_subtitles_are_persistent(app, logged_in_client):
    page = logged_in_client.get("/admin/appearance/interface/")
    text = page.get_data(as_text=True)
    assert page.status_code == 200
    for label in ("云朵圆体", "糖霜柔体", "软糖幼圆", "手账宋体", "星光楷体", "清透拟态"):
        assert label in text
    assert "一键关闭小标题" not in text
    hints = logged_in_client.get("/admin/appearance/interface/?section=hints")
    assert "一键关闭小标题" in hints.get_data(as_text=True)
    response = logged_in_client.post(
        "/admin/appearance/interface/?section=hints",
        data={
            "admin_menu_subtitles_visible": "y",
            "panel_descriptions_visible": "y",
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "提示与说明的显示范围已经更新" in body
    public_body = logged_in_client.get("/").get_data(as_text=True)
    assert 'data-panel-descriptions="visible"' in public_body
    assert 'data-card-descriptions="hidden"' in public_body
    assert 'data-field-descriptions="hidden"' in public_body

    response = logged_in_client.post(
        "/admin/appearance/interface/",
        data={"font_style": "playful-yuan"},
        follow_redirects=True,
    )
    assert "全局字体已经更新" in response.get_data(as_text=True)
    assert 'data-font-style="playful-yuan"' in logged_in_client.get("/").get_data(as_text=True)

    response = logged_in_client.post(
        "/admin/appearance/interface/menu-subtitles/", follow_redirects=True
    )
    assert "后台菜单小标题已关闭" in response.get_data(as_text=True)
    admin_page = logged_in_client.get("/admin/").get_data(as_text=True)
    assert "admin-menu--compact" in admin_page
    with app.app_context():
        setting = db.session.scalar(
            db.select(SiteSetting).where(SiteSetting.setting_key == "admin_menu_subtitles_visible")
        )
        assert setting.setting_value == "false"
