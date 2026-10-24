from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from app.db import db
from app.services import settings
from app.timeutil import iso, utcnow
from app.version import __version__, build_id

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    session = db()
    session.execute(text("SELECT 1"))
    response = jsonify({"ok": True, "version": __version__, "build": build_id(), "site_version": settings.site_version(session), "time": iso(utcnow())})
    response.headers["Cache-Control"] = "no-store"
    return response
