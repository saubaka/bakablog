"""Public site blueprint."""

from flask import Blueprint

public_bp = Blueprint("public", __name__)

from app.blueprints.public import (  # noqa: E402, F401
    blog_routes,
    content_routes,
    interaction_routes,
    routes,
    search_routes,
)
