"""Independent public search page and asynchronous result endpoint."""

from __future__ import annotations

from flask import current_app, jsonify, make_response, render_template, request

from app.blueprints.public import public_bp
from app.services.search import normalize_search_mode, normalize_search_query, search_site


def _request_values() -> tuple[str, str, int, int]:
    query = normalize_search_query(request.args.get("q", ""))
    mode = normalize_search_mode(request.args.get("mode", "strict"))
    page = max(1, request.args.get("page", 1, type=int))
    per_page = int(current_app.config["SEARCH_RESULTS_PER_PAGE"])
    return query, mode, page, per_page


@public_bp.get("/search/")
def search():
    query, mode, page, per_page = _request_values()
    results = search_site(query, mode, page, per_page)
    return render_template("public/search.html", results=results)


@public_bp.get("/search/api/")
def search_api():
    query, mode, page, per_page = _request_values()
    response = make_response(jsonify(search_site(query, mode, page, per_page).as_dict()))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response
