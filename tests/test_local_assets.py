from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest

RESOURCE_PATTERN = re.compile(rb"<(?:script|img|use)[^>]+(?:src|href)=\"([^\"]+)\"")


@pytest.mark.parametrize(
    "path", ["/", "/blog/", "/projects/", "/moments/", "/about/", "/components/", "/admin/"]
)
def test_pages_do_not_reference_remote_required_assets(client, path):
    response = client.get(path)
    resources = [match.decode() for match in RESOURCE_PATTERN.findall(response.data)]
    remote = [url for url in resources if urlsplit(url).scheme in {"http", "https"}]
    assert remote == []


@pytest.mark.parametrize(
    "path",
    [
        "/static/styles/app.css",
        "/static/scripts/app.js",
        "/static/icons/sprite.svg",
    ],
)
def test_static_assets_are_served_locally(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.data
