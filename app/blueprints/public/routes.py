"""Public demonstration routes for the stage-three skeleton."""

from __future__ import annotations

import os
import re
from pathlib import Path

from flask import (
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from app.blueprints.public import public_bp
from app.extensions import db
from app.services.backup import database_path
from app.services.content import (
    DIALOG_SHADOW_CHOICES,
    DIALOG_STYLE_CHOICES,
    GLOBAL_FONT_CHOICES,
    PAGE_TRANSITION_CHOICES,
)
from app.services.migrations import migration_head

MEDIA_PATH_PATTERN = re.compile(
    r"(?:originals|thumbnails)/[0-9a-f]{32}\.(?:jpg|png|webp)", re.IGNORECASE
)


@public_bp.get("/components/")
def components():
    return render_template(
        "public/components.html",
        transition_choices=PAGE_TRANSITION_CHOICES,
        dialog_style_choices=DIALOG_STYLE_CHOICES,
        dialog_shadow_choices=DIALOG_SHADOW_CHOICES,
        font_choices=GLOBAL_FONT_CHOICES,
    )


@public_bp.get("/empty/")
def empty_state():
    return render_template("public/empty.html")


@public_bp.get("/out/")
def external_link_notice():
    from app.services.external_links import ExternalLinkError, classify_destination

    try:
        link = classify_destination(request.args.get("url", ""))
    except ExternalLinkError as error:
        return render_template("errors/400.html", message=str(error)), 400
    response = render_template("public/external_link.html", link=link)
    return (
        response,
        200,
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@public_bp.get("/demo/flash/<category>/")
def flash_demo(category: str):
    allowed = {"success", "info", "warning", "error"}
    selected = category if category in allowed else "info"
    flash("这是一条来自Flask服务端的状态通知。", selected)
    return render_template("public/components.html")


@public_bp.get("/demo/error/<int:status_code>/")
def error_demo(status_code: int):
    if status_code not in {404, 500}:
        abort(404)
    abort(status_code)


@public_bp.get("/healthz")
def healthcheck():
    response = jsonify(
        {
            "status": "ok",
            "service": "cloudtrace",
            "stage": 9,
            "version": current_app.config["APP_VERSION"],
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@public_bp.get("/readyz")
def readiness_check():
    try:
        db.session.execute(db.text("SELECT 1"))
        if current_app.config["ENV_NAME"] == "production":
            revision = db.session.execute(
                db.text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
            expected_revision = migration_head()
            if revision != expected_revision:
                raise RuntimeError(
                    f"database migration mismatch: current={revision}, head={expected_revision}"
                )
        data_path = database_path()
        uploads_path = Path(current_app.instance_path) / "uploads"
        if not os.access(data_path.parent, os.W_OK) or not os.access(uploads_path, os.W_OK):
            raise RuntimeError("instance storage is not writable")
    except Exception:
        db.session.rollback()
        current_app.logger.error("readiness check failed", exc_info=True)
        response = jsonify({"status": "unavailable", "service": "cloudtrace"})
        response.headers["Cache-Control"] = "no-store"
        return response, 503
    response = jsonify(
        {
            "status": "ready",
            "service": "cloudtrace",
            "version": current_app.config["APP_VERSION"],
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@public_bp.get("/robots.txt")
def robots():
    from app.services.seo import get_seo_settings

    seo = get_seo_settings()
    lines = ["User-agent: *"]
    if seo.index_site:
        lines.append("Allow: /")
        lines.extend(f"Disallow: {path}" for path in seo.robots_disallow)
    else:
        lines.append("Disallow: /")
    if seo.enable_sitemap:
        lines.append(f"Sitemap: {current_app.config['SITE_URL']}/sitemap.xml")
    body = "\n".join(lines) + "\n"
    response = Response(body, content_type="text/plain; charset=utf-8")
    response.cache_control.public = True
    response.cache_control.max_age = 3600
    return response


@public_bp.get("/media/<path:filename>")
def media_file(filename: str):
    from app.services.access import get_access_policy, hotlink_is_allowed

    if not MEDIA_PATH_PATTERN.fullmatch(filename):
        abort(404)
    policy = g.get("access_policy") or get_access_policy()
    if not hotlink_is_allowed(request.referrer or "", policy):
        abort(403)
    return send_from_directory(
        Path(current_app.instance_path) / "uploads",
        filename,
        max_age=31_536_000,
        conditional=True,
        etag=True,
    )
