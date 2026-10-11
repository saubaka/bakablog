"""Phase-one theme contract, without changing the existing motion protocol."""
import re
from pathlib import Path

import pytest


@pytest.mark.parametrize("path", ["/", "/blog/", "/bakaadmin", "/admin/"])
def test_theme_is_local_and_loaded_after_legacy_styles(client, path):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    assert html.index("styles/app.css") < html.index("styles/small-window-theme.css")
    assert html.index("styles/small-window-theme.css") < html.index("styles/notifications.css")
    assert "small-window-theme.css?v=1.49.0" in html


def test_final_theme_declares_project8_tokens():
    css = (Path(__file__).parents[1] / "app/static/styles/small-window-theme.css").read_text()
    for declaration in (
        "--line-blue: #ebf3fa;", "--line-blue-strong: #d9e8f6;",
        "--silver-mist: var(--line-blue);", "--blue-200: #e5f0fa;",
        "--radius-control: 13px;", "--radius-card: 20px;",
        "--radius-panel: 28px;", "--space-4: 16px;",
    ):
        assert declaration in css
    assert "--action-blue-ink: var(--graphite-blue);" in css
    primary = re.search(r"\.button--primary \{([^}]+)\}", css).group(1)
    assert "background: var(--surface) !important;" in primary
    assert "color: var(--graphite-blue) !important;" in primary
    assert "stroke-dasharray:" not in css  # Physical tracing belongs to phase two.
    assert "@import" not in css


def test_themed_stylesheet_is_served_locally(client):
    response = client.get("/static/styles/small-window-theme.css")
    assert response.status_code == 200
    assert "text/css" in response.content_type


def test_outline_geometry_and_sidebar_position_are_not_overridden_by_icons():
    css = (Path(__file__).parents[1] / "app/static/styles/small-window-theme.css").read_text()
    outline = re.search(r"\.motion-child-control > svg\.motion-outline \{([^}]+)\}", css).group(1)
    assert "width: 100% !important;" in outline
    assert "height: 100% !important;" in outline
    assert "html.is-motion-ready body .admin-sidebar.motion-line-target" in css
    assert "position: sticky;" in css
    assert "position: fixed;" in css
