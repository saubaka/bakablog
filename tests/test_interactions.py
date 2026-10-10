from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.extensions import db
from app.models import (
    Album,
    Comment,
    CommentReaction,
    FriendLink,
    GuestbookMessage,
    Media,
    ModerationNotification,
    Moment,
    Photo,
    Post,
)
from app.services.friends import FriendCheckError, check_friend_url, validate_public_http_url


def _published_post(app, author_id: int) -> int:
    with app.app_context():
        post = Post(
            title="互动测试文章",
            slug="interaction-post",
            summary="测试评论",
            content_markdown="正文",
            content_html="<p>正文</p>",
            toc_html="",
            status="published",
            published_at=datetime.now(UTC),
            author_id=author_id,
            allow_comments=True,
        )
        db.session.add(post)
        db.session.commit()
        return post.id


def _image(name: str = "photo.png", size: tuple[int, int] = (80, 60)):
    stream = BytesIO()
    Image.new("RGB", size, "#b8ddff").save(stream, "PNG")
    stream.seek(0)
    return stream, name


def test_friend_application_status_and_admin_approval(app, client, logged_in_client):
    response = client.post(
        "/links/",
        data={
            "name": "蓝云小站",
            "url": "https://example.com/",
            "description": "记录独立开发与生活碎片",
            "avatar_url": "",
            "applicant_email": "hello@example.com",
            "website": "",
        },
    )
    assert response.status_code == 200
    assert "申请已收到" in response.get_data(as_text=True)
    with app.app_context():
        link = db.session.scalar(db.select(FriendLink))
        assert link.status == "pending"
        assert link.ip_hash and link.ip_hash != "127.0.0.1"
        code, link_id = link.application_code, link.id
        assert db.session.scalar(db.select(ModerationNotification)) is not None
    assert "蓝云小站" not in client.get("/links/").get_data(as_text=True).split("friend-grid")[-1]
    assert "等待审核" in client.get(f"/links/application/{code}/").get_data(as_text=True)
    logged_in_client.post(f"/admin/friends/{link_id}/approve/", data={})
    assert "蓝云小站" in client.get("/links/").get_data(as_text=True)


def test_friend_url_ssrf_rules():
    for value in ("http://127.0.0.1/", "http://localhost/", "ftp://example.com/"):
        with pytest.raises(FriendCheckError):
            validate_public_http_url(value)
    assert validate_public_http_url("https://example.com/path", resolve=False).startswith(
        "https://"
    )


def test_friend_check_connects_to_validated_ip_without_second_dns_lookup(monkeypatch):
    dns_calls = 0
    connection_targets: list[tuple[str, int]] = []

    def fake_getaddrinfo(hostname, port):  # type: ignore[no-untyped-def]
        nonlocal dns_calls
        dns_calls += 1
        address = "93.184.216.34" if dns_calls == 1 else "127.0.0.1"
        return [(2, 1, 6, "", (address, 0))]

    def fake_create_connection(target, timeout, source_address):  # type: ignore[no-untyped-def]
        connection_targets.append(target)
        raise OSError("stop before network access")

    monkeypatch.setattr("app.services.friends.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("app.services.friends.socket.create_connection", fake_create_connection)

    with pytest.raises(FriendCheckError, match="连接失败"):
        check_friend_url("http://example.com/path")

    assert dns_calls == 1
    assert connection_targets == [("93.184.216.34", 80)]


def test_album_batch_upload_and_public_lightbox(app, logged_in_client):
    created = logged_in_client.post(
        "/admin/albums/edit/",
        data={
            "title": "夏日光影",
            "slug": "summer",
            "description": "两张照片",
            "status": "published",
            "sort_order": 1,
        },
        follow_redirects=False,
    )
    assert created.status_code == 302
    with app.app_context():
        album = db.session.scalar(db.select(Album).where(Album.slug == "summer"))
        album_id = album.id
    response = logged_in_client.post(
        f"/admin/albums/{album_id}/photos/",
        data={"images": [_image("one.png"), _image("two.png", (60, 90))]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Photo)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(Media)) == 2
    page = logged_in_client.get("/gallery/summer/")
    assert page.status_code == 200
    assert page.get_data(as_text=True).count("data-image-preview data-full-src") == 2
    assert "data-global-image-lightbox" in page.get_data(as_text=True)


def test_moderation_center_has_summary_and_query_filters(logged_in_client):
    response = logged_in_client.get("/admin/moderation/?view=comments&status=pending")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    for label in ("未读消息", "评论", "留言"):
        assert label in body
    assert "举报" not in body
    assert "<h1>评论审核</h1>" in body
    assert "moderation-hub-nav" in body
    assert "moderation-status-filter" in body
    assert 'data-message-center' in body
    assert "评论互动" not in body
    assert "举报受理" not in body


def test_unread_messages_route_to_their_actionable_regions(app, logged_in_client, admin_user):
    post_id = _published_post(app, admin_user)
    with app.app_context():
        comment = Comment(
            post_id=post_id,
            author_name="跳转评论用户",
            author_type="visitor",
            content="需要从未读消息跳转的评论",
            status="pending",
        )
        message = GuestbookMessage(
            author_name="跳转留言用户",
            content="需要从未读消息跳转的留言",
            status="pending",
        )
        db.session.add_all([comment, message])
        db.session.flush()
        notices = [
            ModerationNotification(
                notification_type="new_comment",
                target_type="comment",
                target_id=comment.id,
                message="有一条新评论",
            ),
            ModerationNotification(
                notification_type="new_guestbook",
                target_type="guestbook",
                target_id=message.id,
                message="有一条新留言",
            ),
        ]
        db.session.add_all(notices)
        db.session.commit()
        notice_targets = [(item.id, item.target_type, item.target_id) for item in notices]

    inbox = logged_in_client.get("/admin/moderation/?view=unread").get_data(as_text=True)
    assert all(message in inbox for message in ("有一条新评论", "有一条新留言"))
    assert "举报" not in inbox
    expected_views = {"comment": "comments", "guestbook": "guestbook"}
    expected_prefixes = {"comment": "comment", "guestbook": "message"}
    for notice_id, target_type, target_id in notice_targets:
        response = logged_in_client.get(f"/admin/moderation/notifications/{notice_id}/open/")
        assert response.status_code == 302
        assert f"view={expected_views[target_type]}" in response.location
        assert f"#moderation-{expected_prefixes[target_type]}-{target_id}" in response.location
        with app.app_context():
            assert db.session.get(ModerationNotification, notice_id).is_read is True


def test_moderation_cards_keep_editors_collapsed_and_offer_smooth_delete_controls(
    app, logged_in_client, admin_user
):
    post_id = _published_post(app, admin_user)
    with app.app_context():
        comment = Comment(
            post_id=post_id,
            author_name="折叠评论用户",
            author_type="visitor",
            content="默认只展示的评论正文",
            status="approved",
        )
        message = GuestbookMessage(
            author_name="折叠留言用户",
            content="默认只展示的留言正文",
            status="approved",
        )
        db.session.add_all([comment, message])
        db.session.flush()
        db.session.commit()
        comment_id = comment.id
        message_id = message.id

    for view in ("comments", "guestbook"):
        body = logged_in_client.get(f"/admin/moderation/?view={view}").get_data(as_text=True)
        assert 'data-card-delete data-confirm=' in body
        assert 'data-moderation-edit-toggle aria-expanded="false"' in body
        assert 'data-moderation-editor aria-hidden="true"' in body
        assert all(label in body for label in (">通过<", ">不通过<", ">编辑<"))

    comments_body = logged_in_client.get("/admin/moderation/?view=comments").get_data(
        as_text=True
    )
    guestbook_body = logged_in_client.get("/admin/moderation/?view=guestbook").get_data(
        as_text=True
    )
    assert f'href="/blog/interaction-post/#comment-{comment_id}"' in comments_body
    assert f'href="/guestbook/#guestbook-message-{message_id}"' in guestbook_body
    assert f'id="comment-{comment_id}"' in logged_in_client.get(
        "/blog/interaction-post/"
    ).get_data(as_text=True)
    assert f'id="guestbook-message-{message_id}"' in logged_in_client.get(
        "/guestbook/"
    ).get_data(as_text=True)

    styles = Path("app/static/styles/app.css").read_text(encoding="utf-8")
    assert ".moderation-card__delete{position:absolute;z-index:3;top:50%" in styles
    assert "width:38px!important;height:38px!important" in styles
    assert ".moderation-card__front-link" in styles


def test_comment_moderation_reply_and_like(app, client, logged_in_client, admin_user):
    post_id = _published_post(app, admin_user)
    response = client.post(
        "/blog/interaction-post/comments/",
        data={
            "author_name": "小蓝",
            "email": "private@example.com",
            "website": "",
            "content": "这篇文章很有帮助",
            "parent_id": "",
            "contact": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "这篇文章很有帮助" not in response.get_data(as_text=True)
    with app.app_context():
        comment = db.session.scalar(db.select(Comment).where(Comment.post_id == post_id))
        assert comment.status == "pending"
        assert comment.email == "private@example.com"
        assert comment.ip_hash != "127.0.0.1"
        comment_id = comment.id
    logged_in_client.post(f"/admin/moderation/comments/{comment_id}/approve/", data={})
    assert "这篇文章很有帮助" in client.get("/blog/interaction-post/").get_data(as_text=True)
    client.post(f"/comments/{comment_id}/like/", data={})
    client.post(f"/comments/{comment_id}/like/", data={})
    removed_report = client.post(f"/comments/{comment_id}/report/", data={})
    assert removed_report.status_code == 404
    logged_in_client.post(
        f"/admin/moderation/comments/{comment_id}/reply/",
        data={"content": "谢谢你的认真阅读"},
    )
    with app.app_context():
        comment = db.session.get(Comment, comment_id)
        assert comment.like_count == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(CommentReaction)) == 1
        reply = db.session.scalar(db.select(Comment).where(Comment.parent_id == comment_id))
        assert reply.author_type == "staff" and reply.status == "approved"


def test_comments_require_per_entry_switch_and_moments_support_comments(
    app, client, admin_user
):
    with app.app_context():
        disabled = Post(
            title="关闭评论",
            slug="comments-disabled",
            summary="",
            content_markdown="正文",
            content_html="<p>正文</p>",
            toc_html="",
            status="published",
            published_at=datetime.now(UTC),
            author_id=admin_user,
            allow_comments=False,
        )
        moment = Moment(
            content_markdown="动态正文",
            content_html="<p>动态正文</p>",
            status="published",
            published_at=datetime.now(UTC),
            allow_comments=True,
        )
        db.session.add_all([disabled, moment])
        db.session.commit()
        moment_id = moment.id

    assert "comments-section" not in client.get("/blog/comments-disabled/").get_data(as_text=True)
    assert client.post(
        "/blog/comments-disabled/comments/",
        data={"author_name": "访客", "content": "不能提交"},
    ).status_code == 404

    detail = client.get(f"/moments/{moment_id}/")
    assert detail.status_code == 200
    assert "data-human-check" in detail.get_data(as_text=True)
    created = client.post(
        f"/moments/{moment_id}/comments/",
        data={"author_name": "访客", "content": "动态评论", "contact": ""},
    )
    assert created.status_code == 302
    with app.app_context():
        comment = db.session.scalar(db.select(Comment).where(Comment.moment_id == moment_id))
        assert comment is not None
        assert comment.post_id is None


def test_report_feature_is_absent_from_public_and_admin_surfaces(
    app, client, logged_in_client, admin_user
):
    post_id = _published_post(app, admin_user)
    with app.app_context():
        comment = Comment(
            post_id=post_id,
            author_name="待管理评论",
            author_type="visitor",
            content="原始评论内容",
            status="approved",
        )
        db.session.add(comment)
        db.session.commit()
        comment_id = comment.id

    article = client.get("/blog/interaction-post/").get_data(as_text=True)
    moderation = logged_in_client.get("/admin/moderation/?view=reports")
    removed_action = logged_in_client.post(
        f"/admin/moderation/comments/{comment_id}/resolve-report/",
        data={},
    )
    assert "举报" not in article
    assert "举报" not in moderation.get_data(as_text=True)
    assert moderation.status_code == 200
    assert removed_action.status_code == 404


def test_guestbook_moderation_reply_pin_and_block(app, client, logged_in_client):
    response = client.post(
        "/guestbook/",
        data={
            "author_name": "小粉",
            "email": "hidden@example.com",
            "content": "来云朵上留一个脚印",
            "website": "",
        },
        follow_redirects=True,
    )
    assert "来云朵上留一个脚印" not in response.get_data(as_text=True)
    with app.app_context():
        message = db.session.scalar(db.select(GuestbookMessage))
        message_id = message.id
        assert message.status == "pending"
    logged_in_client.post(f"/admin/moderation/messages/{message_id}/approve/", data={})
    logged_in_client.post(f"/admin/moderation/messages/{message_id}/pin/", data={})
    logged_in_client.post(
        f"/admin/moderation/messages/{message_id}/reply/", data={"content": "欢迎常来看看"}
    )
    public = client.get("/guestbook/").get_data(as_text=True)
    assert "来云朵上留一个脚印" in public and "欢迎常来看看" in public
    assert "hidden@example.com" not in public
    logged_in_client.post(f"/admin/moderation/messages/{message_id}/block/", data={})
    assert "来云朵上留一个脚印" not in client.get("/guestbook/").get_data(as_text=True)


def test_interaction_rate_limit(app, client):
    app.config["INTERACTION_RATE_LIMIT"] = 1
    payload = {"author_name": "限流测试", "email": "", "content": "第一条留言", "website": ""}
    client.post("/guestbook/", data=payload)
    payload["content"] = "第二条留言"
    client.post("/guestbook/", data=payload)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(GuestbookMessage)) == 1
