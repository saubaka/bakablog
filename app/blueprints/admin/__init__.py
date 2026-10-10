"""Administration blueprint."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_auth_bp = Blueprint("bakaadmin", __name__)

from app.blueprints.admin import (  # noqa: E402, F401
    blog_routes,
    content_routes,
    interaction_routes,
    routes,
    site_routes,
)
