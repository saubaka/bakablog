"""docs/API.md must describe exactly the routes the application has (no undocumented route, no documented ghost)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.version import __version__

DOCS = Path(__file__).resolve().parents[2] / "docs"


def documented() -> set[tuple[str, str]]:
    text = (DOCS / "API.md").read_text(encoding="utf-8")
    return {(m, p) for m, p in re.findall(r"`(GET|POST|PUT|PATCH|DELETE) (/[^`\s]*)`", text)}


def actual(app) -> set[tuple[str, str]]:
    out = set()
    for rule in app.url_map.iter_rules():
        if rule.rule == "/static/<path:filename>":
            continue
        path = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            out.add((method, path))
    return out


def test_every_route_is_documented_and_every_documented_route_exists(app):
    doc, real = documented(), actual(app)
    assert sorted(real - doc) == [], "routes missing from docs/API.md"
    assert sorted(doc - real) == [], "docs/API.md mentions routes that do not exist"


def test_api_samples_are_valid_json_and_current():
    samples = list((DOCS / "api-samples").rglob("*.json"))
    assert len(samples) >= 25
    for path in samples:
        json.loads(path.read_text(encoding="utf-8"))
    site = json.loads((DOCS / "api-samples" / "site.json").read_text(encoding="utf-8"))
    assert site["name"] == "saubakaの博客" and site["version"] == __version__  # regenerate with scripts/dump_samples.py when this fails


def test_the_api_document_links_to_samples_that_exist():
    text = (DOCS / "API.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\((api-samples/[^)]+)\)", text):
        assert (DOCS / target).is_file(), target
