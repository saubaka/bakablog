from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image

from app.extensions import db
from app.models import Category, Post, PostVersion, Tag
from app.services.blog import render_markdown


def _post(author_id: int, title: str, slug: str, status: str, published_at: datetime | None):
    html, toc, minutes = render_markdown(f"## 小标题\n\n{title} 的正文，包含 Flask 与 SQLite。")
    return Post(
        title=title,
        slug=slug,
        summary=f"{title}的摘要",
        content_markdown=f"## 小标题\n\n{title} 的正文，包含 Flask 与 SQLite。",
        content_html=html,
        toc_html=toc,
        status=status,
        published_at=published_at,
        reading_minutes=minutes,
        author_id=author_id,
    )


def _seed_posts(app, admin_user):
    with app.app_context():
        category = Category(name="代码笔记", slug="code", description="关于代码")
        tag = Tag(name="Flask", slug="flask")
        now = datetime.now(UTC)
        public = _post(admin_user, "公开的 Flask 手记", "public-note", "published", now)
        public.category = category
        public.tags = [tag]
        scheduled_due = _post(
            admin_user, "已经到点的定时文章", "due-note", "scheduled", now - timedelta(hours=1)
        )
        draft = _post(admin_user, "不能公开的草稿", "draft-note", "draft", None)
        future = _post(
            admin_user, "未来才公开", "future-note", "scheduled", now + timedelta(days=1)
        )
        deleted = _post(admin_user, "回收站文章", "deleted-note", "published", now)
        deleted.deleted_at = now
        db.session.add_all([category, tag, public, scheduled_due, draft, future, deleted])
        db.session.commit()
        return public.id


def test_markdown_rendering_sanitizes_and_builds_toc():
    html, toc, minutes = render_markdown(
        "## 安全标题\n\n<script>alert(1)</script>\n\n```python\nprint('hi')\n```"
    )
    assert "<script" not in html
    assert "alert(1)" in html
    assert "codehilite" in html
    assert "安全标题" in toc
    assert minutes == 1


def test_visual_editor_styles_survive_safe_server_sanitizing():
    html, _, _ = render_markdown(
        '<p style="text-align: center; color: #46556a; position: fixed">居中正文</p>'
        '<figure class="article-media article-media--custom" style="width: 73%">'
        '<img src="/media/originals/demo.webp" alt="云朵"></figure>'
    )
    assert "text-align: center" in html
    assert "color: #46556a" in html
    assert "position" not in html
    assert 'class="article-media article-media--custom"' in html
    assert "width: 73%" in html


def test_public_visibility_search_filters_and_archive(app, client, admin_user):
    _seed_posts(app, admin_user)
    app.config["POSTS_PER_PAGE"] = 1
    listing = client.get("/blog/")
    body = listing.get_data(as_text=True)
    assert "公开的 Flask 手记" in body
    assert "下一页" in body
    assert "不能公开的草稿" not in body
    assert "未来才公开" not in body
    assert "回收站文章" not in body
    assert "已经到点的定时文章" in client.get("/blog/?page=2").get_data(as_text=True)

    assert "公开的 Flask 手记" in client.get("/blog/?q=SQLite").get_data(as_text=True)
    assert "公开的 Flask 手记" in client.get("/blog/?category=code").get_data(as_text=True)
    assert "公开的 Flask 手记" in client.get("/blog/?tag=flask").get_data(as_text=True)
    assert client.get("/blog/category/code/").status_code == 302
    assert client.get("/blog/tag/flask/").status_code == 302
    assert "公开的 Flask 手记" in client.get("/blog/archive/").get_data(as_text=True)


def test_article_navigation_feed_sitemap_and_seo(app, client, admin_user):
    _seed_posts(app, admin_user)
    article = client.get("/blog/public-note/")
    body = article.get_data(as_text=True)
    assert article.status_code == 200
    assert "data-reading-progress" in body
    assert "data-reading-progress-fill" in body
    assert "data-reading-progress-value" in body
    assert "data-reading-progress-remaining" in body
    assert "小标题" in body
    assert 'rel="canonical"' in body

    feed = client.get("/feed.xml")
    assert feed.mimetype == "application/atom+xml"
    assert "公开的 Flask 手记" in feed.get_data(as_text=True)
    assert "不能公开的草稿" not in feed.get_data(as_text=True)
    sitemap = client.get("/sitemap.xml")
    assert "/blog/public-note/" in sitemap.get_data(as_text=True)
    assert "/blog/draft-note/" not in sitemap.get_data(as_text=True)


def test_create_edit_publish_delete_and_restore(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/posts/new/",
        data={
            "title": "我的第一篇文章",
            "slug": "first-post",
            "summary": "一段摘要",
            "content_markdown": "## 正文\n\n这是一段内容。",
            "category_id": "0",
            "tags": "Flask，SQLite",
            "status": "published",
            "seo_title": "",
            "seo_description": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "文章已保存" in response.get_data(as_text=True)
    with app.app_context():
        post = db.session.scalar(db.select(Post).where(Post.slug == "first-post"))
        assert post is not None
        post_id = post.id
        assert post.status == "published"
        assert {tag.name for tag in post.tags} == {"Flask", "SQLite"}
        assert post.versions.count() == 1

    response = logged_in_client.post(
        f"/admin/posts/{post_id}/edit/",
        data={
            "title": "修改后的文章",
            "slug": "first-post",
            "summary": "修改摘要",
            "content_markdown": "## 更新\n\n更新后的内容。",
            "category_id": "0",
            "tags": "Flask",
            "status": "draft",
            "seo_title": "",
            "seo_description": "",
        },
        follow_redirects=True,
    )
    assert "新版本已经保存" in response.get_data(as_text=True)
    assert logged_in_client.get("/blog/first-post/").status_code == 404
    logged_in_client.post(f"/admin/posts/{post_id}/delete/", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Post, post_id).deleted_at is not None
    logged_in_client.post(f"/admin/posts/{post_id}/restore/", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Post, post_id).deleted_at is None


def test_autosave_versions_and_restore(app, logged_in_client, admin_user):
    post_id = _seed_posts(app, admin_user)
    response = logged_in_client.post(
        f"/admin/api/posts/{post_id}/autosave/",
        json={"title": "自动保存标题", "summary": "自动摘要", "content_markdown": "## 自动保存"},
    )
    assert response.get_json()["ok"] is True
    with app.app_context():
        post = db.session.get(Post, post_id)
        version = PostVersion(
            post_id=post.id,
            version_number=1,
            title="旧标题",
            summary="旧摘要",
            content_markdown="## 旧正文",
            status="published",
            created_by_id=admin_user,
        )
        db.session.add(version)
        db.session.commit()
        version_id = version.id
    response = logged_in_client.post(
        f"/admin/posts/{post_id}/versions/{version_id}/restore/", follow_redirects=True
    )
    assert "已恢复版本1" in response.get_data(as_text=True)
    with app.app_context():
        post = db.session.get(Post, post_id)
        assert post.title == "旧标题"
        assert post.status == "draft"
        assert post.versions.count() == 2


def test_taxonomy_and_editor_image(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/taxonomy/",
        data={
            "taxonomy_type": "category",
            "name": "设计",
            "slug": "design",
            "description": "设计手记",
        },
        follow_redirects=True,
    )
    assert "已经创建" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(Category).where(Category.slug == "design")) is not None

    stream = BytesIO()
    Image.new("RGB", (64, 48), "#cde8ff").save(stream, format="PNG")
    stream.seek(0)
    response = logged_in_client.post(
        "/admin/api/editor-image/",
        data={"image": (stream, "note.png"), "alt_text": "云朵"},
        content_type="multipart/form-data",
    )
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["markdown"].startswith('<img src="/media/')
    assert 'width="64" height="48"' in payload["data"]["markdown"]
    assert 'loading="lazy" decoding="async"' in payload["data"]["markdown"]
    assert payload["data"]["size_bytes"] > 0


def test_taxonomy_lists_and_creation_are_separate_pages(app, logged_in_client):
    categories = logged_in_client.get("/admin/taxonomy/categories/")
    category_form = logged_in_client.get("/admin/taxonomy/categories/new/")
    tags = logged_in_client.get("/admin/taxonomy/tags/")
    tag_form = logged_in_client.get("/admin/taxonomy/tags/new/")
    assert "分类列表" in categories.get_data(as_text=True)
    assert "创建分类" not in categories.get_data(as_text=True)
    assert "创建分类" in category_form.get_data(as_text=True)
    assert "标签列表" in tags.get_data(as_text=True)
    assert "创建标签" not in tags.get_data(as_text=True)
    assert "创建标签" in tag_form.get_data(as_text=True)

    created = logged_in_client.post(
        "/admin/taxonomy/tags/new/",
        data={
            "taxonomy_type": "category",
            "name": "浅蓝",
            "slug": "pale-blue",
            "description": "来自独立新建页",
        },
        follow_redirects=True,
    )
    assert "标签已经创建" in created.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(Tag).where(Tag.slug == "pale-blue")) is not None
        assert db.session.scalar(db.select(Category).where(Category.slug == "pale-blue")) is None


def test_admin_post_editor_renders_visual_toolbar_and_grouped_navigation(logged_in_client):
    response = logged_in_client.get("/admin/posts/new/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "data-visual-editor" in body
    assert 'data-editor-source="true"' in body
    assert "data-image-width" in body
    assert 'data-open-dialog="editor-media-dialog"' in body
    assert "发布前检查" not in body
    assert "快捷提示" not in body
    assert "<strong>文章</strong>" in body
    assert "主题" in body


def test_admin_sidebar_opens_the_reorganized_group_for_each_blog_workflow(logged_in_client):
    destinations = (
        ("/admin/", "dashboard", "仪表盘", "仪表盘"),
        ("/admin/posts/", "articles", "文章", "全部文章"),
        ("/admin/posts/new/", "articles", "文章", "新建文章"),
        ("/admin/taxonomy/categories/", "taxonomy", "标签", "分类列表"),
        ("/admin/taxonomy/categories/new/", "taxonomy", "标签", "新建分类"),
        ("/admin/taxonomy/tags/", "taxonomy", "标签", "标签列表"),
        ("/admin/taxonomy/tags/new/", "taxonomy", "标签", "新建标签"),
        ("/admin/moments/", "moments", "动态", "全部动态"),
        ("/admin/moments/new/", "moments", "动态", "新建动态"),
        ("/admin/moderation/?view=comments&status=all", "comments", "评论", "评论"),
        ("/admin/moderation/?view=comments&status=pending", "comments", "评论", "评论审核"),
        ("/admin/moderation/?view=unread", "comments", "评论", "未读消息"),
        ("/admin/media/", "media", "媒体", "媒体"),
        ("/admin/albums/", "albums", "相册", "相册管理"),
        ("/admin/pages/", "pages", "页面", "页面总览"),
        ("/admin/pages/system/home/", "pages", "页面", "编辑首页"),
        ("/admin/menu/primary/", "menu", "菜单", "菜单管理"),
        ("/admin/menu/admin-layout/", "menu", "菜单", "管理面板编辑"),
        ("/admin/site/identity/", "site", "站点", "标题与Logo"),
        ("/admin/appearance/seo/", "site", "站点", "SEO设置"),
        ("/admin/site/footer/", "site", "站点", "页尾内容设置"),
        ("/admin/site/addresses/", "site", "站点", "网站链接"),
        ("/admin/site/security/", "site", "站点", "安全"),
        ("/admin/projects/", "projects", "项目", "项目"),
        ("/admin/appearance/interface/?section=font", "appearance", "主题", "字体"),
        ("/admin/appearance/interface/?section=hints", "appearance", "主题", "提示"),
        ("/admin/appearance/transitions/", "appearance", "主题", "动画"),
        ("/admin/appearance/dialogs/", "appearance", "主题", "弹窗与通知"),
        ("/admin/system/", "system", "系统管理", "系统状态"),
        ("/admin/audit-logs/", "system", "系统管理", "操作日志"),
        ("/admin/system/about/", "system", "系统管理", "关于"),
    )
    for path, menu_key, heading, page_title in destinations:
        response = logged_in_client.get(path)
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert f'data-menu-key="{menu_key}"' in body
        if menu_key in {"dashboard", "comments"}:
            assert 'class="admin-nav-group admin-nav-direct is-open"' in body
        else:
            assert (
                f'class="admin-nav-group is-open" data-admin-menu-group '
                f'data-menu-key="{menu_key}"' in body
            )
        assert f"<strong>{heading}</strong>" in body
        assert f"<h1>{page_title}</h1>" in body
        assert (
            body.count('class="admin-nav-group is-open"')
            + body.count('class="admin-nav-group admin-nav-direct is-open"')
            == 1
        )


def test_slug_is_unique(app, logged_in_client):
    base = {
        "title": "重复链接",
        "slug": "same",
        "summary": "",
        "content_markdown": "正文",
        "category_id": "0",
        "tags": "",
        "status": "draft",
        "seo_title": "",
        "seo_description": "",
    }
    logged_in_client.post("/admin/posts/new/", data=base)
    logged_in_client.post("/admin/posts/new/", data=base)
    with app.app_context():
        assert db.session.scalars(db.select(Post.slug).order_by(Post.id)).all() == [
            "same",
            "same-2",
        ]
