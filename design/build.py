#!/usr/bin/env python3
"""Assemble the static prototype pages: src/layout.html + src/partials/* + src/pages/*.html -> design/*.html.

A page file starts with `key: value` lines, then a line containing only `---`, then the page body.
An optional line containing only `===extra===` splits off markup that goes after the footer (sheets, dialogs)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def read(path):
    return path.read_text(encoding="utf-8")


def cur(html, nav):
    return re.sub(r"\{\{cur:(\w+)\}\}", lambda m: ' aria-current="page"' if m.group(1) == nav else "", html)


def main():
    layout = read(SRC / "layout.html")
    parts = {name: read(SRC / "partials" / f"{name}.html") for name in ("header", "footer", "tabbar", "search", "backtop")}
    sprite = read(SRC / "partials" / "sprite.svg")
    built = []
    for page in sorted((SRC / "pages").glob("*.html")):
        head, body = read(page).split("\n---\n", 1)
        meta = {}
        for line in head.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        extra = ""
        if "\n===extra===\n" in body:
            body, extra = body.split("\n===extra===\n", 1)
        html = layout
        for key, value in parts.items():
            html = html.replace("{{%s}}" % key, cur(value, meta.get("nav", "")))
        html = html.replace("{{sprite}}", sprite)
        for key in ("title", "desc", "page"):
            html = html.replace("{{%s}}" % key, meta.get(key, ""))
        html = html.replace("{{body}}", body).replace("{{extra}}", extra)
        left = re.findall(r"\{\{[^}]+\}\}", html)
        if left:
            print("unresolved in", page.name, left, file=sys.stderr)
        (ROOT / page.name).write_text(html, encoding="utf-8")
        built.append(page.name)
    print("built:", ", ".join(built))


if __name__ == "__main__":
    main()
