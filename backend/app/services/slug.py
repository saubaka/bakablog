"""Slugs: URL names for posts, pages, tags, categories and series; anchors for headings."""
from __future__ import annotations

import re
import unicodedata

from pypinyin import Style, lazy_pinyin
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.paths import RESERVED_PAGE_SLUGS

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 80


def slugify(text: str, *, max_len: int = SLUG_MAX) -> str:
    """"SQLite 备份：我差点…" -> "sqlite-bei-fen-wo-cha-dian…" (Chinese by pinyin, everything else lower-case ASCII)."""
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    parts: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            parts.append(buf)
            buf = ""

    for ch in text:
        if _CJK.match(ch):
            flush()
            syllable = lazy_pinyin(ch, style=Style.NORMAL, errors="ignore")
            if syllable:
                parts.append(re.sub(r"[^a-z0-9]", "", syllable[0].lower()))
        elif ch.isascii() and ch.isalnum():
            buf += ch
        else:
            flush()
    flush()
    slug = "-".join(p for p in parts if p)
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0] if "-" in slug[:max_len] else slug[:max_len]
    return slug.strip("-")


def heading_slug(text: str) -> str:
    """Anchor ids keep the Chinese words (valid in HTML5 and in URLs): "为什么直接复制 文件" -> "为什么直接复制-文件"."""
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w-]", "", text, flags=re.UNICODE).replace("_", "-")
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:60].strip("-") or "section"


def unique_slug(session: Session, model, base: str, *, exclude_id: int | None = None, fallback: str = "item",
                reserved: frozenset[str] = frozenset()) -> str:
    """base, base-2, base-3 ... the first one no other row of `model` uses."""
    base = (base or fallback).strip("-") or fallback
    base = base[:SLUG_MAX].strip("-") or fallback
    candidate = base
    n = 2
    while True:
        taken = candidate in reserved
        if not taken:
            q = select(model.id).where(model.slug == candidate)
            if exclude_id is not None:
                q = q.where(model.id != exclude_id)
            taken = session.scalar(q) is not None
        if not taken:
            return candidate
        suffix = f"-{n}"
        candidate = base[: SLUG_MAX - len(suffix)].rstrip("-") + suffix
        n += 1


def is_valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug)) and len(slug) <= SLUG_MAX


def is_reserved_page_slug(slug: str) -> bool:
    return slug in RESERVED_PAGE_SLUGS
