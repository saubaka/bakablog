from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.api import (
        admin_auth,
        admin_moments,
        admin_pages,
        admin_posts,
        admin_site,
        admin_system,
        admin_taxonomy,
        health,
        media,
        public,
    )

    for module in (health, public):
        app.register_blueprint(module.bp)
    app.register_blueprint(media.public)
    for module in (media, admin_auth, admin_posts, admin_moments, admin_pages, admin_taxonomy, admin_site, admin_system):
        app.register_blueprint(module.bp)

    from app.seo import feeds, spa

    app.register_blueprint(feeds.bp)
    app.register_blueprint(spa.bp)  # last: the catch-all for public addresses
