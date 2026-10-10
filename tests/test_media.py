from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.extensions import db
from app.models import AuditLog, Media, SiteSetting


def image_file() -> BytesIO:
    stream = BytesIO()
    Image.new("RGB", (80, 60), "#cde8ff").save(stream, format="PNG")
    stream.seek(0)
    return stream


def test_upload_and_delete_local_image(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/media/",
        data={"image": (image_file(), "cloud.png"), "alt_text": "浅蓝色云朵"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "图片已安全处理" in response.get_data(as_text=True)

    with app.app_context():
        media = db.session.scalar(db.select(Media))
        assert media is not None
        assert media.original_filename == "cloud.png"
        original = Path(app.instance_path) / "uploads" / media.filename
        thumbnail = Path(app.instance_path) / "uploads" / media.thumbnail_filename
        assert original.is_file()
        assert thumbnail.is_file()
        media_id = media.id
        public_path = media.thumbnail_filename

    public_response = logged_in_client.get(f"/media/{public_path}")
    assert public_response.status_code == 200
    public_response.close()

    response = logged_in_client.post(f"/admin/media/{media_id}/delete/", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Media, media_id) is None
        actions = db.session.scalars(db.select(AuditLog.action).order_by(AuditLog.id)).all()
        assert actions == ["media.upload", "media.delete"]


def test_invalid_image_is_rejected(app, logged_in_client):
    response = logged_in_client.post(
        "/admin/media/",
        data={"image": (BytesIO(b"not an image"), "fake.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert "不是可识别的图片" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Media)) == 0


def test_site_logo_is_local_private_filename_is_hidden_and_active_file_is_protected(
    app, logged_in_client
):
    response = logged_in_client.post(
        "/admin/site/logo/",
        data={"logo": (image_file(), "my-private-desktop-name.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "网站Logo已经更新" in response.get_data(as_text=True)

    with app.app_context():
        media = db.session.scalar(db.select(Media))
        setting = db.session.scalar(
            db.select(SiteSetting).where(SiteSetting.setting_key == "site_logo_media_id")
        )
        assert media is not None and setting is not None
        assert media.original_filename == "site-logo.png"
        assert setting.setting_value == str(media.id)
        media_id = media.id
        logo_path = media.thumbnail_filename

    home = logged_in_client.get("/").get_data(as_text=True)
    assert f"/media/{logo_path}" in home
    assert 'rel="icon"' in home

    blocked = logged_in_client.post(
        f"/admin/media/{media_id}/delete/", follow_redirects=True
    )
    assert blocked.status_code == 200
    assert "仍是网站Logo" in blocked.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Media, media_id) is not None

    removed = logged_in_client.post("/admin/site/logo/remove/", follow_redirects=True)
    assert removed.status_code == 200
    assert "恢复默认图标" in removed.get_data(as_text=True)
    with app.app_context():
        setting = db.session.scalar(
            db.select(SiteSetting).where(SiteSetting.setting_key == "site_logo_media_id")
        )
        assert setting is not None and setting.setting_value == ""
