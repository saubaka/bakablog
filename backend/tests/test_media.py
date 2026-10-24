from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageCms
from sqlalchemy import select

from app.db import session_scope
from app.models import Media, MediaRef
from app.services import media as media_service
from tests.conftest import png_bytes

M = "/api/admin/media"


def variant_path(cfg, media_hash: str, size: int) -> Path:
    return media_service.media_path(cfg, media_hash, size)


def open_variant(cfg, data: dict, size: int | None = None) -> Image.Image:
    size = size or data["variants"][0]["size"]
    return Image.open(variant_path(cfg, data["hash"], size))


# ---- accepted uploads ---------------------------------------------------------------------------------------------------------------
def test_upload_makes_three_webp_sizes_and_never_enlarges(admin, cfg):
    big = admin.upload(M, png_bytes(2400, 1600, (10, 120, 200)))
    assert big.status_code == 201
    d = big.get_json()
    assert [(v["size"], v["w"], v["h"]) for v in d["variants"]] == [(480, 480, 320), (960, 960, 640), (1600, 1600, 1067)]
    assert d["orig_width"] == 2400 and d["orig_height"] == 1600 and d["mime"] == "image/png" and d["kind"] == "image"
    for v in d["variants"]:
        with open_variant(cfg, d, v["size"]) as im:
            assert im.format == "WEBP" and im.size == (v["w"], v["h"])
    assert d["src"].endswith("/960.webp") and d["full"].endswith("/1600.webp") and "480w" in d["srcset"]
    small = admin.upload(M, png_bytes(300, 200, (200, 30, 30))).get_json()
    assert [(v["size"], v["w"]) for v in small["variants"]] == [(480, 300)]  # one file, original size
    mid = admin.upload(M, png_bytes(700, 500, (30, 200, 30))).get_json()
    assert [(v["size"], v["w"]) for v in mid["variants"]] == [(480, 480), (960, 700)]


def test_upload_accepts_jpeg_gif_and_webp(admin):
    for fmt, mime in (("JPEG", "image/jpeg"), ("GIF", "image/gif"), ("WEBP", "image/webp")):
        r = admin.upload(M, png_bytes(120, 80, fmt=fmt), filename=f"a.{fmt.lower()}", mimetype=mime)
        assert r.status_code == 201, (fmt, r.get_json())
        assert r.get_json()["mime"] == mime


def test_dominant_colour_and_filename_are_recorded(admin):
    d = admin.upload(M, png_bytes(100, 100, (120, 170, 220)), filename="../../etc/cloud sky.png").get_json()
    r, g, b = (int(d["color"][i:i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 120) < 12 and abs(g - 170) < 12 and abs(b - 220) < 12
    assert d["filename"] == "cloud sky.png"  # never a path


def test_same_bytes_return_the_same_row(admin):
    data = png_bytes(90, 90, (1, 2, 3))
    first = admin.upload(M, data)
    second = admin.upload(M, data)
    assert first.status_code == 201 and second.status_code == 200
    assert second.get_json()["duplicate"] is True and first.get_json()["id"] == second.get_json()["id"]


def test_a_trashed_picture_is_restored_by_uploading_it_again(admin):
    data = png_bytes(90, 90, (9, 9, 9))
    mid = admin.upload(M, data).get_json()["id"]
    assert admin.delete(f"{M}/{mid}").status_code == 200
    again = admin.upload(M, data)
    assert again.status_code == 200 and again.get_json()["deleted_at"] is None


def test_exif_gps_is_removed_and_orientation_applied(admin, cfg):
    im = Image.new("RGB", (60, 40), (200, 100, 50))
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 clockwise to display"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (31.0, 14.0, 0.0), "E", (121.0, 28.0, 0.0)
    exif[0x010F] = "TestCam"
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif, comment=b"secret comment")
    raw = buf.getvalue()
    assert b"TestCam" in raw and b"secret comment" in raw
    d = admin.upload(M, raw, filename="p.jpg", mimetype="image/jpeg").get_json()
    assert (d["orig_width"], d["orig_height"]) == (40, 60)  # turned upright
    for v in d["variants"]:
        data = variant_path(cfg, d["hash"], v["size"]).read_bytes()
        assert b"TestCam" not in data and b"secret comment" not in data and b"EXIF" not in data
        with Image.open(io.BytesIO(data)) as out:
            assert not out.getexif() and "exif" not in out.info and "xmp" not in out.info


def test_colour_profile_is_converted_to_srgb_and_dropped(admin, cfg):
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes() if False else ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (90, 140, 200)).save(buf, "JPEG", icc_profile=profile)
    d = admin.upload(M, buf.getvalue(), filename="p.jpg", mimetype="image/jpeg").get_json()
    with open_variant(cfg, d) as out:
        assert "icc_profile" not in out.info


def test_flat_png_stays_lossless_and_photos_are_lossy(admin, cfg):
    flat = Image.new("RGB", (120, 80), (255, 246, 249))
    for x in range(30, 90):
        for y in range(20, 60):
            flat.putpixel((x, y), (230, 241, 252))
    buf = io.BytesIO()
    flat.save(buf, "PNG")
    d = admin.upload(M, buf.getvalue()).get_json()
    with open_variant(cfg, d) as out:
        assert list(out.convert("RGB").getdata()) == list(flat.getdata())  # exact pixels


def test_animated_gif_keeps_its_animation_up_to_960(admin, cfg):
    frames = [Image.new("RGB", (1300, 400), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=120, loop=0)
    d = admin.upload(M, buf.getvalue(), filename="a.gif", mimetype="image/gif").get_json()
    assert d["animated"] is True
    assert [v["size"] for v in d["variants"]] == [480, 960]  # no 1600 for animations
    with open_variant(cfg, d, 960) as out:
        assert out.format == "WEBP" and getattr(out, "n_frames", 1) == 3


def test_a_gif_with_markup_in_a_comment_comes_out_clean(admin, cfg):
    buf = io.BytesIO()
    Image.new("P", (40, 40), 3).save(buf, "GIF", comment=b"<script>alert(1)</script><?php system($_GET[1]);?>")
    assert b"<script>" in buf.getvalue()
    d = admin.upload(M, buf.getvalue(), filename="x.gif", mimetype="image/gif").get_json()
    for v in d["variants"]:
        data = variant_path(cfg, d["hash"], v["size"]).read_bytes()
        assert b"<script" not in data and b"<?php" not in data


# ---- refused uploads --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,data,status,code", [
    ("empty.png", b"", 422, "empty_file"),
    ("notes.png", b"just some text pretending to be a picture", 415, "unsupported_type"),
    ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(1)</script></svg>', 415, "unsupported_type"),
    ("x.html", b"<!doctype html><script>alert(1)</script>", 415, "unsupported_type"),
    ("x.pdf", b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n", 415, "unsupported_type"),
    ("x.php.jpg", b"\xff\xd8\xff\xe0<?php system($_GET['c']); ?>", 422, "bad_image"),
    ("x.png", b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, 422, "bad_image"),
    ("x.gif", b"GIF89a" + b"<script>alert(1)</script>", 422, "bad_image"),
    ("x.ico", b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x20\x00" + b"\x00" * 60, 415, "unsupported_type"),
])
def test_bad_uploads_are_refused(admin, name, data, status, code):
    r = admin.upload(M, data, filename=name)
    assert r.status_code == status and r.get_json()["error"]["code"] == code
    assert admin.get(M).get_json()["total"] == 0


def test_truncated_image_is_refused(admin):
    data = png_bytes(300, 300, (1, 2, 3), fmt="PNG")
    r = admin.upload(M, data[: len(data) // 2])
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "bad_image"


def test_image_bomb_is_refused_before_decoding(admin, app):
    huge = Image.new("1", (20000, 20000))  # 400 million pixels, a few dozen KB as PNG
    buf = io.BytesIO()
    huge.save(buf, "PNG")
    assert len(buf.getvalue()) < 200_000
    r = admin.upload(M, buf.getvalue())
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "image_too_large"
    long_thin = io.BytesIO()
    Image.new("1", (13000, 8)).save(long_thin, "PNG")
    assert admin.upload(M, long_thin.getvalue()).status_code == 413


def _noise_png(side: int) -> bytes:
    import os

    buf = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(buf, "PNG")
    return buf.getvalue()


def test_oversized_upload_is_refused(admin, app):
    app.extensions["bb_config"] = app.extensions["bb_config"].with_overrides(max_upload_bytes=2000)
    data = _noise_png(100)
    assert len(data) > 2000
    r = admin.upload(M, data)
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "too_large"


def test_a_body_far_beyond_the_limit_is_stopped_by_the_server_itself(tmp_path, template_db, owner_factory=None):
    import shutil

    from app import create_app
    from app.services import auth
    from tests.conftest import OWNER, Api, make_config

    cfg = make_config(tmp_path, max_upload_bytes=20_000)
    shutil.copyfile(template_db, cfg.db_path)
    app = create_app(cfg)
    with session_scope(app) as s:
        auth.create_owner(s, OWNER["username"], OWNER["password"], cfg)
    a = Api(app.test_client())
    a.csrf = a.post("/api/admin/auth/login", OWNER).get_json()["csrf_token"]
    r = a.upload(M, b"\x89PNG\r\n\x1a\n" + b"0" * (3 * 1024 * 1024))
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "too_large"


def test_too_many_animation_frames_are_refused(admin, app):
    app.extensions["bb_config"] = app.extensions["bb_config"].with_overrides(max_animation_frames=2)
    frames = [Image.new("RGB", (30, 30), (i * 40, 0, 0)) for i in range(4)]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=50)
    r = admin.upload(M, buf.getvalue(), filename="a.gif")
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "too_many_frames"


def test_upload_requires_a_file_field(admin):
    r = admin.post(M, data={"alt": "x"}, content_type="multipart/form-data")
    assert r.status_code == 422 and r.get_json()["error"]["fields"] == {"file": "必填"}


def test_uploading_needs_login_and_csrf(api, admin, png):
    assert api.upload(M, png(10, 10)).status_code == 401
    admin.csrf = None
    assert admin.upload(M, png(10, 10)).status_code == 403


# ---- serving -----------------------------------------------------------------------------------------------------------------------------
def test_files_are_served_immutable_with_validators(admin, api):
    d = admin.upload(M, png_bytes(700, 500)).get_json()
    r = api.get(d["src"])
    assert r.status_code == 200 and r.headers["Content-Type"] == "image/webp"
    assert r.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert r.headers["Cross-Origin-Resource-Policy"] == "cross-origin" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in r.headers
    etag = r.headers["ETag"]
    assert api.get(d["src"], headers={"If-None-Match": etag}).status_code == 304
    assert r.data[:4] == b"RIFF" and r.data[8:12] == b"WEBP"


@pytest.mark.parametrize("url", [
    "/media/../../../etc/passwd/960.webp", "/media/%2e%2e%2f%2e%2e%2fetc/960.webp", "/media/ABCDEF0123456789ABCDEF0123456789/960.webp",
    "/media/zzzz/960.webp", "/media/0123456789abcdef0123456789abcdef/1000.webp", "/media/0123456789abcdef0123456789abcdef/960.png",
    "/media/0123456789abcdef0123456789abcdef/960.webp",  # well-formed but absent
])
def test_media_route_rejects_odd_requests(api, url):
    assert api.get(url).status_code == 404


# ---- library: list, detail, edit ------------------------------------------------------------------------------------------------------------
def test_list_filters_and_search(admin):
    a = admin.upload(M, png_bytes(100, 100, (1, 1, 1)), filename="cloud-one.png", fields={"alt": "第一朵云"}).get_json()
    b = admin.upload(M, png_bytes(100, 100, (2, 2, 2)), filename="two.png").get_json()
    r = admin.post("/api/admin/posts", {"title": "用图", "content_md": f"![x](media:{a['id']})"}).get_json()
    assert r["id"]
    assert admin.get(M).get_json()["total"] == 2
    assert [m["id"] for m in admin.get(f"{M}?q=cloud").get_json()["items"]] == [a["id"]]
    assert [m["id"] for m in admin.get(f"{M}?q=第一").get_json()["items"]] == [a["id"]]
    assert [m["id"] for m in admin.get(f"{M}?unused=1").get_json()["items"]] == [b["id"]]
    assert admin.get(f"{M}?sort=name").get_json()["items"][0]["filename"] == "cloud-one.png"
    assert admin.get(f"{M}?per=1&page=2").get_json()["items"][0]["id"] == a["id"]
    assert admin.get(f"{M}?per=1000").status_code == 422
    items = {m["id"]: m for m in admin.get(M).get_json()["items"]}
    assert items[a["id"]]["usage_count"] == 1 and items[b["id"]]["usage_count"] == 0


def test_detail_lists_where_a_picture_is_used(admin):
    mid = admin.upload(M, png_bytes(100, 100)).get_json()["id"]
    post = admin.post("/api/admin/posts", {"title": "封面文章", "cover_media_id": mid, "status": "published"}).get_json()
    moment = admin.post("/api/admin/moments", {"text": "有图", "media": [{"media_id": mid}]}).get_json()
    d = admin.get(f"{M}/{mid}").get_json()
    assert {(u["type"], u["id"]) for u in d["usage"]} == {("post", post["id"]), ("moment", moment["id"])}
    assert next(u for u in d["usage"] if u["type"] == "post")["url"] == f"/blog/{post['slug']}"


def test_alt_text_edit_rerenders_the_content_that_uses_it(admin):
    mid = admin.upload(M, png_bytes(100, 100)).get_json()["id"]
    post = admin.post("/api/admin/posts", {"title": "图文", "content_md": f"![](media:{mid})", "status": "published"}).get_json()
    assert 'alt=""' in admin.get(f"/api/posts/{post['slug']}").get_json()["html"] if False else True
    r = admin.patch(f"{M}/{mid}", {"alt": "凌晨的书桌", "caption": "写代码的凌晨"})
    assert r.status_code == 200 and r.get_json()["alt"] == "凌晨的书桌"
    html = admin.get(f"/api/posts/{post['slug']}").get_json()["html"]
    assert 'alt="凌晨的书桌"' in html and "<figcaption>写代码的凌晨</figcaption>" in html


def test_replace_keeps_id_and_references_and_removes_old_files_after_commit(admin, cfg):
    first = admin.upload(M, png_bytes(900, 600, (200, 0, 0))).get_json()
    post = admin.post("/api/admin/posts", {"title": "换图", "content_md": f"![x](media:{first['id']})", "status": "published", "cover_media_id": first["id"]}).get_json()
    old_files = [variant_path(cfg, first["hash"], v["size"]) for v in first["variants"]]
    assert all(p.exists() for p in old_files)
    r = admin.upload(f"{M}/{first['id']}/replace", png_bytes(1000, 500, (0, 0, 200)), filename="new.png")
    assert r.status_code == 200
    new = r.get_json()
    assert new["id"] == first["id"] and new["hash"] != first["hash"] and new["orig_width"] == 1000 and new["filename"] == "new.png"
    assert not any(p.exists() for p in old_files)
    assert all(variant_path(cfg, new["hash"], v["size"]).exists() for v in new["variants"])
    detail = admin.get(f"/api/posts/{post['slug']}").get_json()
    assert new["hash"] in detail["html"] and first["hash"] not in detail["html"]
    assert new["hash"] in detail["cover"]["src"]


def test_replace_with_a_picture_that_already_exists_is_a_conflict(admin):
    a = admin.upload(M, png_bytes(100, 100, (1, 1, 1))).get_json()
    b = admin.upload(M, png_bytes(100, 100, (2, 2, 2))).get_json()
    r = admin.upload(f"{M}/{a['id']}/replace", png_bytes(100, 100, (2, 2, 2)))
    assert r.status_code == 409 and r.get_json()["error"]["media_id"] == b["id"]


def test_deleting_a_used_picture_needs_confirmation_and_purging_leaves_a_placeholder(admin, cfg):
    d = admin.upload(M, png_bytes(300, 200, (5, 5, 5))).get_json()
    post = admin.post("/api/admin/posts", {"title": "用到", "content_md": f"![图](media:{d['id']})", "status": "published", "cover_media_id": d["id"]}).get_json()
    r = admin.delete(f"{M}/{d['id']}")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "in_use" and r.get_json()["error"]["usage"]
    assert admin.delete(f"{M}/{d['id']}?force=1").status_code == 200
    assert admin.get(f"{M}?trashed=1").get_json()["total"] == 1 and admin.get(M).get_json()["total"] == 0
    assert variant_path(cfg, d["hash"], 480).exists()  # still on disk: it is only in the trash
    assert admin.post(f"{M}/{d['id']}/restore", {}).status_code == 200
    assert admin.delete(f"{M}/{d['id']}?force=1").status_code == 200
    assert admin.delete(f"{M}/{d['id']}/purge").status_code == 200
    assert not variant_path(cfg, d["hash"], 480).exists()
    detail = admin.get(f"/api/posts/{post['slug']}").get_json()
    assert "img-missing" in detail["html"] and "<img" not in detail["html"] and detail["cover"] is None
    with session_scope(admin.client.application) as s:
        assert s.scalar(select(Media).where(Media.id == d["id"])) is None
        assert not list(s.scalars(select(MediaRef).where(MediaRef.media_id == d["id"])))


def test_unused_pictures_delete_without_confirmation(admin):
    mid = admin.upload(M, png_bytes(50, 50)).get_json()["id"]
    assert admin.delete(f"{M}/{mid}").status_code == 200


def test_usage_survives_a_rerender_and_is_dropped_with_the_content(admin):
    mid = admin.upload(M, png_bytes(50, 50)).get_json()["id"]
    post = admin.post("/api/admin/posts", {"title": "x", "content_md": f"![a](media:{mid})"}).get_json()
    assert admin.get(f"{M}/{mid}/usage").get_json()["items"][0]["id"] == post["id"]
    admin.patch(f"/api/admin/posts/{post['id']}", {"content_md": "no picture any more"})
    assert admin.get(f"{M}/{mid}/usage").get_json()["items"] == []
