"""baka blog Flask application factory."""

from __future__ import annotations

import gzip
import os
import re
from http import HTTPStatus
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from flask import (
    Flask,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from app.blueprints.admin import admin_bp
from app.blueprints.gateway import gateway_bp
from app.blueprints.public import public_bp
from app.config import CONFIGS, BaseConfig
from app.extensions import csrf, db, login_manager, migrate


def create_app(
    config_name: str | None = None,
    test_config: dict[str, object] | None = None,
    instance_path: str | None = None,
) -> Flask:
    """Create and configure a baka blog application instance."""

    instance_path = instance_path or os.getenv("CLOUD_DIARY_INSTANCE_PATH")
    selected_config = config_name or os.getenv("CLOUD_DIARY_ENV", "development")
    config_class = CONFIGS.get(selected_config, BaseConfig)

    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    from app.services.cache import home_content_cache, site_context_cache

    site_context_cache.clear()
    home_content_cache.clear()
    app.config.from_object(config_class)

    runtime_secret = os.getenv("CLOUD_DIARY_SECRET_KEY")
    if runtime_secret:
        app.config["SECRET_KEY"] = runtime_secret
    runtime_site_url = os.getenv("CLOUD_DIARY_SITE_URL")
    if runtime_site_url:
        app.config["SITE_URL"] = runtime_site_url.rstrip("/")
    runtime_fallbacks = os.getenv("CLOUD_DIARY_SECRET_KEY_FALLBACKS")
    if runtime_fallbacks:
        app.config["SECRET_KEY_FALLBACKS"] = [
            item.strip() for item in runtime_fallbacks.split(",") if item.strip()
        ]
    app.config["TRUST_PROXY_HEADERS"] = _environment_flag(
        "CLOUD_DIARY_TRUST_PROXY_HEADERS", bool(app.config.get("TRUST_PROXY_HEADERS"))
    )
    app.config["TEXT_COMPRESSION_ENABLED"] = _environment_flag(
        "CLOUD_DIARY_TEXT_COMPRESSION", bool(app.config.get("TEXT_COMPRESSION_ENABLED"))
    )

    instance_config = Path(app.instance_path) / "config.py"
    if instance_config.exists():
        app.config.from_pyfile("config.py", silent=False)

    if test_config:
        app.config.update(test_config)

    _ensure_instance_directories(app)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        database_path = (Path(app.instance_path) / "data" / "site.db").resolve()
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path.as_posix()}"

    _validate_production_config(app)
    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    from app.observability import configure_logging

    configure_logging(app)
    _initialize_extensions(app)
    _register_blueprints(app)
    _register_commands(app)
    _register_request_hooks(app)
    _register_template_filters(app)
    _register_context_processors(app)
    _register_error_handlers(app)
    return app


def _register_template_filters(app: Flask) -> None:
    from app.services.external_links import linkify_external_html, notice_url

    app.jinja_env.filters["linkify_external"] = linkify_external_html
    app.jinja_env.filters["external_notice_url"] = notice_url


def _ensure_instance_directories(app: Flask) -> None:
    for name in ("data", "uploads", "cache", "logs", "backups", "tmp", "updates"):
        (Path(app.instance_path) / name).mkdir(parents=True, exist_ok=True)


def _register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(gateway_bp)
    app.register_blueprint(admin_bp)


def _initialize_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.session_protection = str(app.config.get("SESSION_PROTECTION", "strong"))
    csrf.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        if not user_id.isdigit():
            return None
        user = db.session.get(User, int(user_id))
        return user if user is not None and user.can_login else None

    login_manager.login_view = "admin.login"
    login_manager.login_message = "请先登录管理后台。"


def _register_commands(app: Flask) -> None:
    from app.cli import register_commands

    register_commands(app)


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def begin_request() -> None:
        from app.security import sanitize_request_id

        g.request_id = sanitize_request_id(request.headers.get("X-Request-ID")) or uuid4().hex
        g.request_started_at = perf_counter()

    @app.before_request
    def validate_gateway_identity():  # type: ignore[no-untyped-def]
        from app.services.gateway import current_gateway_session

        g.gateway_session = current_gateway_session(validate_remote=True)
        return None

    @app.before_request
    def validate_account_session():  # type: ignore[no-untyped-def]
        from flask_login import current_user, logout_user

        from app.models import utc_now
        from app.services.auth import (
            AUTH_SOURCE_GATEWAY,
            AUTH_SOURCE_RECOVERY,
            AUTH_SOURCE_TESTING,
            current_user_session,
            current_user_session_source,
            linked_gateway_session_id,
            session_is_valid,
            touch_user_session,
        )

        if not current_user.is_authenticated:
            return None
        item = current_user_session()
        source = current_user_session_source()
        gateway_session = g.get("gateway_session")
        source_is_valid = source == AUTH_SOURCE_RECOVERY
        if source == AUTH_SOURCE_TESTING:
            source_is_valid = current_app.testing
        elif source == AUTH_SOURCE_GATEWAY:
            source_is_valid = bool(
                gateway_session is not None
                and gateway_session.id == linked_gateway_session_id()
                and gateway_session.linked_user_id == current_user.id
                and gateway_session.gateway_subject == current_user.gateway_subject
            )
        session_is_current = bool(
            item is not None
            and item.user_id == current_user.id
            and session_is_valid(item)
            and source_is_valid
        )
        if not session_is_current:
            if item is not None and item.revoked_at is None:
                item.revoked_at = utc_now()
                db.session.commit()
            logout_user()
            session.clear()
            return redirect(url_for("admin.login", next=request.path))
        if touch_user_session(item):
            current_user.last_seen_at = item.last_seen_at
            db.session.commit()
        return None

    @app.before_request
    def enforce_access_policy():  # type: ignore[no-untyped-def]
        from app.services.access import (
            get_access_policy,
            host_is_allowed,
            origin_is_allowed,
            request_hostname,
        )

        production_https = current_app.config.get("ENV_NAME") == "production"
        g.require_https = production_https
        if production_https and not request.is_secure:
            return redirect(request.url.replace("http://", "https://", 1), code=308)
        if request.endpoint in {"public.healthcheck", "public.readiness_check"}:
            return None
        if request.endpoint == "gateway.local_recovery":
            from app.services.local_recovery import request_is_loopback

            if request_is_loopback():
                return None
        policy = get_access_policy()
        g.access_policy = policy
        try:
            hostname = request_hostname(request.host)
        except ValueError:
            abort(400)
        if not host_is_allowed(hostname, policy.allowed_hosts):
            abort(400)
        if not origin_is_allowed(request.scheme, request.host, policy.bound_urls):
            abort(400)
        require_https = bool(production_https or policy.require_https)
        g.require_https = require_https
        if require_https and not request.is_secure:
            return redirect(request.url.replace("http://", "https://", 1), code=308)
        return None

    @app.before_request
    def enforce_managed_pages():  # type: ignore[no-untyped-def]
        from app.services.cache import site_context_cache
        from app.services.site_management import SYSTEM_PAGES

        endpoint = request.endpoint or ""
        if endpoint in {"public.healthcheck", "public.readiness_check"}:
            return None
        if request.method == "GET" and endpoint.startswith("public."):
            root = endpoint.rsplit(".", 1)[-1]
            root = {
                "article": "blog",
                "project_detail": "projects",
                "moment_detail": "moments",
                "album_detail": "gallery",
            }.get(root, root)
            if root in {item["key"] for item in SYSTEM_PAGES}:
                cached = site_context_cache.get_or_set(
                    f"site-context:{app.instance_path}",
                    int(app.config["SITE_CONTEXT_CACHE_SECONDS"]),
                    _build_site_context,
                )
                page = next(
                    (
                        item
                        for item in cached.get("managed_pages_config", ())
                        if item["key"] == root
                    ),
                    None,
                )
                if page is not None and not page["enabled"]:
                    abort(404)
        return None

    @app.after_request
    def apply_response_headers(response):  # type: ignore[no-untyped-def]
        duration_ms = (perf_counter() - g.get("request_started_at", perf_counter())) * 1000
        g.request_duration_ms = duration_ms
        response.headers["X-Request-ID"] = g.get("request_id", "unknown")
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        csp = (
            "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data: blob:; "
            "manifest-src 'self'; object-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'"
        )
        require_https = bool(g.get("require_https"))
        if require_https:
            csp += "; upgrade-insecure-requests"
        response.headers["Content-Security-Policy"] = csp
        if require_https and request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={int(current_app.config['HSTS_MAX_AGE'])}; includeSubDomains"
            )
        if request.path.startswith("/admin"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
            response.headers["Cache-Control"] = "no-store"
        elif request.path.startswith("/static/"):
            response.headers["Cache-Control"] = (
                "no-cache" if current_app.debug else "public, max-age=31536000, immutable"
            )
        elif response.mimetype == "text/html":
            response.cache_control.no_cache = True
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.path.startswith("/admin/")
            and response.status_code < 400
        ):
            from app.services.cache import home_content_cache, site_context_cache

            site_context_cache.clear()
            home_content_cache.clear()
        _compress_text_response(response)
        if (
            response.status_code >= 400
            or duration_ms >= float(current_app.config["SLOW_REQUEST_MS"])
            or (current_app.config.get("LOG_REQUESTS") and not request.path.startswith("/static/"))
        ):
            current_app.logger.info(
                "request method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
        return response


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_site_context() -> dict[str, object]:
        from app.services.cache import site_context_cache
        from app.services.site_management import build_primary_navigation

        cached = site_context_cache.get_or_set(
            f"site-context:{app.instance_path}",
            int(app.config["SITE_CONTEXT_CACHE_SECONDS"]),
            _build_site_context,
        )
        from flask_login import current_user

        gateway_configured = bool(cached.get("gateway_operational"))
        context = {
            "site_name": cached.get("site_name", app.config["SITE_NAME"]),
            "site_tagline": cached.get("site_tagline", app.config["SITE_TAGLINE"]),
            "system_name": app.config["SYSTEM_NAME"],
            "system_name_en": app.config["SYSTEM_NAME_EN"],
            "current_year": app.config["CURRENT_YEAR"],
            "app_version": app.config["APP_VERSION"],
            "site_url": app.config["SITE_URL"],
            "gateway_identity": g.get("gateway_session"),
            "gateway_is_admin": bool(
                current_user.is_authenticated and current_user.has_permission("admin.access")
            ),
            "primary_navigation": build_primary_navigation(
                list(cached.get("primary_menu_config", ())),
                list(cached.get("managed_pages_config", ())),
                list(cached.get("primary_menu_pages", ())),
            ),
            **cached,
        }
        context.update(
            {
                "gateway_enabled": gateway_configured,
            }
        )
        return context


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf_error(error: CSRFError):
        if request.accept_mimetypes.best == "application/json":
            return jsonify(
                {"ok": False, "error": {"code": "csrf_failed", "message": error.description}}
            ), 400
        return render_template(
            "errors/400.html", message="表单已过期或来源无效，请刷新页面后重试。"
        ), 400

    @app.errorhandler(403)
    def forbidden(error):  # type: ignore[no-untyped-def]
        if request.accept_mimetypes.best == "application/json":
            return jsonify(
                {"ok": False, "error": {"code": "forbidden", "message": "没有执行此操作的权限。"}}
            ), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):  # type: ignore[no-untyped-def]
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):  # type: ignore[no-untyped-def]
        db.session.rollback()
        current_app.logger.error(
            "unhandled request exception",
            exc_info=(type(error), error, error.__traceback__),
        )
        return render_template("errors/500.html"), 500

    @app.errorhandler(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    def request_too_large(error):  # type: ignore[no-untyped-def]
        if request.accept_mimetypes.best == "application/json":
            return jsonify(
                {
                    "ok": False,
                    "error": {"code": "request_too_large", "message": "上传内容超过限制。"},
                }
            ), 413
        return render_template("errors/400.html", message="上传内容超过站点允许的大小。"), 413


def _validate_production_config(app: Flask) -> None:
    if app.config.get("ENV_NAME") != "production":
        return
    secret_key = str(app.config.get("SECRET_KEY", ""))
    if (
        not secret_key
        or secret_key == BaseConfig.DEFAULT_SECRET_KEY
        or len(secret_key.encode()) < 32
    ):
        raise RuntimeError("Production requires a unique 32-byte CLOUD_DIARY_SECRET_KEY.")
    site_url = urlsplit(str(app.config.get("SITE_URL", "")))
    if (
        site_url.scheme != "https"
        or not site_url.hostname
        or site_url.username
        or site_url.password
        or site_url.query
        or site_url.fragment
        or site_url.path not in {"", "/"}
    ):
        raise RuntimeError("Production requires an HTTPS CLOUD_DIARY_SITE_URL origin.")


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_site_context() -> dict[str, object]:
    from app.models import CustomPage, Media, NavigationItem, SiteProfile, SiteSetting
    from app.services.content import (
        DIALOG_APPEARANCE_DEFAULTS,
        DIALOG_SHADOW_VALUES,
        DIALOG_STYLE_VALUES,
        GLOBAL_FONT_VALUES,
        PAGE_TRANSITION_COLOR_DEFAULTS,
        PAGE_TRANSITION_VALUES,
    )
    from app.services.gateway import gateway_is_enabled
    from app.services.seo import SEO_DEFAULTS, get_seo_settings
    from app.services.site_management import (
        ADMIN_NAVIGATION_SETTING,
        FOOTER_CONTENT_SETTING,
        MANAGED_PAGES_SETTING,
        PRIMARY_MENU_SETTING,
        enabled_page_shortcuts,
        load_admin_navigation,
        load_footer_content,
        load_managed_pages,
        load_primary_menu,
        public_page_customizations,
    )

    navigation_items = db.session.scalars(
        db.select(NavigationItem)
        .where(NavigationItem.is_visible.is_(True))
        .order_by(NavigationItem.sort_order)
    ).all()
    published_pages = db.session.scalars(
        db.select(CustomPage)
        .where(CustomPage.status == "published")
        .order_by(CustomPage.sort_order)
    ).all()
    profile = db.session.scalar(db.select(SiteProfile).limit(1))
    chrome_defaults = {
        "footer_text": "使用 Flask 与本地资源搭建",
        "page_transition_style": "stretch",
        "page_transition_duration": "720",
        **PAGE_TRANSITION_COLOR_DEFAULTS,
        **DIALOG_APPEARANCE_DEFAULTS,
        "global_font_style": "cloud-rounded",
        "admin_menu_subtitles_visible": "true",
        "panel_descriptions_visible": "true",
        "card_descriptions_visible": "true",
        "field_descriptions_visible": "true",
        "site_logo_media_id": "",
        "site_display_name": current_app.config["SITE_NAME"],
        "site_display_tagline": current_app.config["SITE_TAGLINE"],
        MANAGED_PAGES_SETTING: "",
        PRIMARY_MENU_SETTING: "",
        FOOTER_CONTENT_SETTING: "",
        ADMIN_NAVIGATION_SETTING: "",
        **SEO_DEFAULTS,
    }
    chrome_settings = dict(chrome_defaults)
    chrome_settings.update(
        db.session.execute(
            db.select(SiteSetting.setting_key, SiteSetting.setting_value).where(
                SiteSetting.setting_key.in_(chrome_defaults)
            )
        ).all()
    )
    transition_style = chrome_settings.get("page_transition_style", "stretch")
    if transition_style not in PAGE_TRANSITION_VALUES:
        transition_style = "stretch"
    try:
        transition_duration = max(
            300, min(2400, int(chrome_settings.get("page_transition_duration", "720")))
        )
    except (TypeError, ValueError):
        transition_duration = 720
    safe_color = lambda value, default: (  # noqa: E731
        value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value or "") else default
    )
    dialog_style = chrome_settings.get("dialog_style", "soft")
    if dialog_style not in DIALOG_STYLE_VALUES:
        dialog_style = "soft"
    dialog_shadow = chrome_settings.get("dialog_shadow", "soft")
    if dialog_shadow not in DIALOG_SHADOW_VALUES:
        dialog_shadow = "soft"
    font_style = chrome_settings.get("global_font_style", "cloud-rounded")
    if font_style not in GLOBAL_FONT_VALUES:
        font_style = "cloud-rounded"
    admin_menu_subtitles_visible = str(
        chrome_settings.get("admin_menu_subtitles_visible", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}
    panel_descriptions_visible = str(
        chrome_settings.get("panel_descriptions_visible", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}
    card_descriptions_visible = str(
        chrome_settings.get("card_descriptions_visible", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}
    field_descriptions_visible = str(
        chrome_settings.get("field_descriptions_visible", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}

    def safe_number(name: str, minimum: int, maximum: int) -> int:
        try:
            value = int(chrome_settings.get(name, DIALOG_APPEARANCE_DEFAULTS[name]))
        except (TypeError, ValueError):
            value = int(DIALOG_APPEARANCE_DEFAULTS[name])
        return max(minimum, min(maximum, value))

    seo_settings = get_seo_settings(chrome_settings)
    logo_media = None
    logo_media_id = str(chrome_settings.get("site_logo_media_id", ""))
    if logo_media_id.isdigit():
        logo_media = db.session.get(Media, int(logo_media_id))
    managed_pages = load_managed_pages(chrome_settings[MANAGED_PAGES_SETTING])
    primary_menu_pages = tuple(
        SimpleNamespace(id=page.id, slug=page.slug, title=page.title, summary=page.summary)
        for page in published_pages
    )
    return {
        "navigation_items": tuple(
            SimpleNamespace(
                label=item.label,
                url=item.url,
                location=item.location,
                open_new_tab=item.open_new_tab,
            )
            for item in navigation_items
        ),
        "navigation_pages": tuple(
            SimpleNamespace(title=item.title, slug=item.slug, summary=item.summary)
            for item in published_pages
            if item.show_in_navigation
        ),
        "site_profile": _snapshot_profile(profile),
        "site_logo": (
            SimpleNamespace(
                filename=logo_media.filename,
                thumbnail_filename=logo_media.thumbnail_filename,
                width=logo_media.width,
                height=logo_media.height,
            )
            if logo_media
            else None
        ),
        "seo_settings": seo_settings,
        "site_name": chrome_settings.get("site_display_name") or current_app.config["SITE_NAME"],
        "site_tagline": chrome_settings.get("site_display_tagline")
        or current_app.config["SITE_TAGLINE"],
        "managed_pages_config": tuple(managed_pages),
        "primary_menu_config": tuple(load_primary_menu(chrome_settings[PRIMARY_MENU_SETTING])),
        "primary_menu_pages": primary_menu_pages,
        "footer_content": load_footer_content(chrome_settings[FOOTER_CONTENT_SETTING]),
        "page_customizations": public_page_customizations(managed_pages),
        "admin_page_shortcuts": enabled_page_shortcuts(managed_pages, published_pages),
        "admin_navigation_layout": load_admin_navigation(chrome_settings[ADMIN_NAVIGATION_SETTING]),
        "seo_schema": {
            "@context": "https://schema.org",
            "@type": seo_settings.schema_type,
            "name": seo_settings.site_title,
            "url": current_app.config["SITE_URL"],
            "description": seo_settings.default_description,
            "author": seo_settings.author_name,
        },
        "footer_text": chrome_settings.get("footer_text") or chrome_defaults["footer_text"],
        "page_transition_style": transition_style,
        "page_transition_duration": transition_duration,
        "page_transition_color_start": safe_color(
            chrome_settings.get("page_transition_color_start"),
            PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_start"],
        ),
        "page_transition_color_middle": safe_color(
            chrome_settings.get("page_transition_color_middle"),
            PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_middle"],
        ),
        "page_transition_color_end": safe_color(
            chrome_settings.get("page_transition_color_end"),
            PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_end"],
        ),
        "dialog_style": dialog_style,
        "dialog_color_start": safe_color(
            chrome_settings.get("dialog_color_start"),
            DIALOG_APPEARANCE_DEFAULTS["dialog_color_start"],
        ),
        "dialog_color_end": safe_color(
            chrome_settings.get("dialog_color_end"),
            DIALOG_APPEARANCE_DEFAULTS["dialog_color_end"],
        ),
        "dialog_accent": safe_color(
            chrome_settings.get("dialog_accent"),
            DIALOG_APPEARANCE_DEFAULTS["dialog_accent"],
        ),
        "dialog_radius": safe_number("dialog_radius", 14, 42),
        "dialog_width": safe_number("dialog_width", 360, 720),
        "dialog_backdrop_blur": safe_number("dialog_backdrop_blur", 0, 30),
        "dialog_shadow": dialog_shadow,
        "font_style": font_style,
        "admin_menu_subtitles_visible": admin_menu_subtitles_visible,
        "panel_descriptions_visible": panel_descriptions_visible,
        "card_descriptions_visible": card_descriptions_visible,
        "field_descriptions_visible": field_descriptions_visible,
        "gateway_operational": gateway_is_enabled(),
    }


def _snapshot_profile(profile):  # type: ignore[no-untyped-def]
    if profile is None:
        return None
    avatar = (
        SimpleNamespace(
            filename=profile.avatar_media.filename,
            thumbnail_filename=profile.avatar_media.thumbnail_filename,
            width=profile.avatar_media.width,
            height=profile.avatar_media.height,
        )
        if profile.avatar_media
        else None
    )
    return SimpleNamespace(
        display_name=profile.display_name,
        headline=profile.headline,
        location=profile.location,
        short_bio=profile.short_bio,
        avatar_media=avatar,
    )


def _compress_text_response(response) -> None:  # type: ignore[no-untyped-def]
    if (
        not current_app.config.get("TEXT_COMPRESSION_ENABLED")
        or response.status_code != 200
        or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
        or response.headers.get("Content-Encoding")
        or not response.mimetype
        or not (
            response.mimetype.startswith("text/")
            or response.mimetype
            in {"application/javascript", "application/json", "application/xml", "image/svg+xml"}
        )
    ):
        return
    response.direct_passthrough = False
    data = response.get_data()
    if len(data) < int(current_app.config["TEXT_COMPRESSION_MIN_BYTES"]):
        return
    compressed = gzip.compress(data, compresslevel=5, mtime=0)
    if len(compressed) >= len(data):
        return
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.vary.add("Accept-Encoding")
