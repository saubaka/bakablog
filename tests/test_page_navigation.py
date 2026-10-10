"""Phase-four contracts: same-shell enhanced navigation and page modules."""
import re
from pathlib import Path

from app import shell_digest

ROOT = Path(__file__).parents[1]


def _attr(html: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', html)
    assert match, name
    return match.group(1)


def test_public_pages_share_one_shell_fingerprint(client):
    pages = ["/", "/blog/", "/moments/", "/projects/", "/gallery/", "/links/", "/guestbook/", "/about/", "/search/"]
    signatures, themes = set(), set()
    for path in pages:
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert '<meta name="cloudtrace-navigation" content="enhanced">' in html
        assert 'data-navigation-region="site"' in html
        signatures.add(_attr(html, "data-shell-signature"))
        themes.add(_attr(html, "data-theme-signature"))
    assert len(signatures) == 1 and len(themes) == 1
    search = client.get("/search/").get_data(as_text=True)
    assert 'data-body-class="search-body"' in search
    assert search.count("scripts/search.js") == 1


def test_admin_pages_share_shell_and_editors_stay_native(logged_in_client):
    signatures = set()
    for path in ["/admin/", "/admin/posts/", "/admin/moments/", "/admin/appearance/dialogs/", "/admin/system/about/"]:
        response = logged_in_client.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert 'data-navigation-region="admin"' in html
        assert '<meta name="cloudtrace-navigation" content="enhanced">' in html
        signatures.add(_attr(html, "data-shell-signature"))
    assert len(signatures) == 1
    editor = logged_in_client.get("/admin/posts/new/").get_data(as_text=True)
    assert '<meta name="cloudtrace-navigation" content="native">' in editor


def test_shell_digest_ignores_current_markers_and_csrf_only():
    base = '<a class="x" href="/a">A</a><input type="hidden" name="csrf_token" value="one">'
    current = '<a class="x is-current" href="/a" aria-current="page">A</a><input type="hidden" name="csrf_token" value="two">'
    assert shell_digest(base) == shell_digest(current)
    assert shell_digest(base) != shell_digest(base.replace("/a", "/b"))


def test_navigation_runtime_is_safe_and_reversible():
    runtime = (ROOT / "app/static/scripts/page-navigation.js").read_text(encoding="utf-8")
    app_script = (ROOT / "app/static/scripts/app.js").read_text(encoding="utf-8")
    base = (ROOT / "app/templates/layouts/base.html").read_text(encoding="utf-8")
    for contract in (
        "new DOMParser().parseFromString", "script:not([type=\"application/json\"])", "controller?.abort()",
        "ticket !== token", "history.pushState", "popstate", "scrollRestoration", "confirmLeave",
        "location.assign", "location.reload", "X-Cloudtrace-Navigation", "cloudtrace:navigated", "unmount()",
    ):
        assert contract in runtime, contract
    assert "innerHTML" not in runtime and "eval(" not in runtime
    assert base.index("scripts/page-navigation.js") < base.index("scripts/app.js")
    assert "CloudtracePage" in app_script and "shouldHandle(target, link)" in app_script
    modules = re.findall(r"pageModule\('([a-z-]+)'", app_script)
    assert {"update-center", "appearance-settings", "runtime-metrics", "article-reading", "editor-and-comments"} <= set(modules)
    for path, name in (("search.js", "global-search"), ("site-management.js", "site-management"),
                       ("ui-global.js", "ui-global-forms"), ("human-check.js", "human-check")):
        assert f"CloudtracePage.define('{name}'" in (ROOT / "app/static/scripts" / path).read_text(encoding="utf-8").replace('"', "'")
