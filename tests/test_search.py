from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.extensions import db
from app.models import FriendLink, GuestbookMessage, Moment, Post, Project


def _seed_search_content(app, admin_user: int) -> None:
    now = datetime.now(UTC)
    with app.app_context():
        db.session.add_all(
            [
                Post(
                    title="星云引擎手记",
                    slug="nebula-engine",
                    summary="完整记录 Flask 搜索引擎的实现。",
                    content_markdown="使用 SQLite 建立本地全文索引。",
                    content_html="<p>使用 SQLite 建立本地全文索引。</p>",
                    toc_html="",
                    status="published",
                    published_at=now,
                    author_id=admin_user,
                ),
                Post(
                    title="不可见的星云草稿",
                    slug="hidden-nebula",
                    summary="不应进入公开搜索。",
                    content_markdown="隐藏内容",
                    content_html="<p>隐藏内容</p>",
                    toc_html="",
                    status="draft",
                    author_id=admin_user,
                ),
                Project(
                    title="星云 工作台",
                    slug="nebula-desk",
                    summary="一个可爱的本地项目面板。",
                    content_markdown="以 Flask 和 SQLite 构建。",
                    content_html="<p>以 Flask 和 SQLite 构建。</p>",
                    tech_stack="Flask · SQLite",
                    status="published",
                    published_at=now,
                ),
                Moment(
                    content_markdown="今天完成了丝滑搜索动画。",
                    content_html="<p>今天完成了丝滑搜索动画。</p>",
                    mood="开心",
                    location="书桌前",
                    status="published",
                    published_at=now,
                ),
                FriendLink(
                    name="云朵邻居",
                    url="https://example.com/",
                    description="一起记录设计和生活。",
                    status="approved",
                ),
                GuestbookMessage(
                    author_name="小星",
                    content="很喜欢这座浅蓝色的小星球。",
                    admin_reply="谢谢你的来访。",
                    status="approved",
                ),
                GuestbookMessage(
                    author_name="未公开访客",
                    content="浅蓝色隐藏留言",
                    status="pending",
                ),
            ]
        )
        db.session.commit()


def test_search_page_and_api_cover_all_public_sources(app, client, admin_user):
    _seed_search_content(app, admin_user)
    page = client.get("/search/")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "找一找站里的内容" in body
    assert 'data-search-endpoint="/search/api/"' in body
    assert "严格匹配" in body and "自由匹配" in body

    expected = {
        "Flask": {"post", "project"},
        "丝滑搜索": {"moment"},
        "云朵邻居": {"friend"},
        "浅蓝色": {"guestbook"},
    }
    for query, sources in expected.items():
        payload = client.get("/search/api/", query_string={"q": query}).get_json()
        assert {item["source"] for item in payload["items"]} == sources
        assert payload["total"] == len(sources)
    hidden = client.get("/search/api/", query_string={"q": "隐藏"}).get_json()
    assert hidden["total"] == 0


def test_search_strict_and_free_matching_have_distinct_semantics(app, client, admin_user):
    _seed_search_content(app, admin_user)
    strict = client.get(
        "/search/api/", query_string={"q": "星云工作台", "mode": "strict"}
    ).get_json()
    free = client.get(
        "/search/api/", query_string={"q": "星云工作台", "mode": "free"}
    ).get_json()
    assert strict["total"] == 0
    assert free["total"] == 1
    assert free["items"][0]["source"] == "project"
    assert free["items"][0]["url"] == "/projects/nebula-desk/"


def test_search_pagination_is_numeric_and_clamps_out_of_range(app, client, admin_user):
    now = datetime.now(UTC)
    with app.app_context():
        db.session.add_all(
            GuestbookMessage(
                author_name=f"访客{index}",
                content=f"共同关键字，第{index}条。",
                status="approved",
                created_at=now,
            )
            for index in range(10)
        )
        db.session.commit()
    app.config["SEARCH_RESULTS_PER_PAGE"] = 3
    second = client.get(
        "/search/api/", query_string={"q": "共同关键字", "page": 2}
    ).get_json()
    assert second["total"] == 10
    assert second["pages"] == 4
    assert second["page"] == 2
    assert len(second["items"]) == 3
    clamped = client.get(
        "/search/api/", query_string={"q": "共同关键字", "page": 999}
    ).get_json()
    assert clamped["page"] == 4
    assert len(clamped["items"]) == 1


def test_search_frontend_uses_debounce_animated_panel_and_global_navigation():
    script = Path("app/static/scripts/search.js").read_text(encoding="utf-8")
    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    navigation = Path("app/templates/components/site_nav.html").read_text(encoding="utf-8")
    assert "delay = 950" in script
    assert "AbortController" in script
    assert "panel.scrollHeight" in script
    assert "data-search-page" in script
    assert ".global-search-panel" in styles
    assert "height 480ms var(--spring)" in styles
    assert ".search-result-card:hover" in styles
    assert "url_for('public.search')" in navigation
    assert "public.blog') }}#blog-search" not in navigation
