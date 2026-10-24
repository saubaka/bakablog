"""Whole-site Markdown export and import.

Export: one zip. posts/*.md, pages/*.md and moments/*.md are Markdown with a front matter header; media/ holds the largest stored picture of
every image that is used (the original upload is not kept, only the WebP versions) and media/manifest.json describes them.

Import: that same zip, or a zipped Hexo / Hugo / Jekyll content folder (YAML or TOML front matter, relative picture paths). Everything arrives
as drafts (private moments) unless the caller asks to keep the status in the files. Nothing from the archive is ever written to disk by its
own path: members are read into memory and used as bytes, so a hostile archive (../ paths, huge sizes, a zip bomb) cannot reach the file system.
"""
from __future__ import annotations

import json
import posixpath
import re
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import IO, Any
from urllib.parse import unquote

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import defaults, paths
from app.config import Config
from app.errors import ApiError
from app.models import Category, Media, Moment, Page, Post, Series
from app.services import media as media_service
from app.services import moments, pages, posts, taxonomy
from app.services.slug import slugify, unique_slug
from app.timeutil import as_utc, iso, local, utcnow, zone

MAX_FILES = 6000
MAX_TOTAL_BYTES = 600 * 1024 * 1024          # everything, unpacked
MAX_MEMBER_BYTES = 40 * 1024 * 1024          # one file (a picture the library would refuse anyway is larger than this)
MAX_TEXT_BYTES = 2 * 1024 * 1024             # one Markdown file
MAX_RATIO = 200                              # unpacked / packed, per member: more than this is a bomb
MAX_WARNINGS = 60
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MD_EXT = (".md", ".markdown", ".mdown", ".mkd")


# ---- front matter ---------------------------------------------------------------------------------------------------------------
def _scalar_out(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)     # a JSON string is a valid YAML double-quoted scalar


def dump_front_matter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(_scalar_out(v) for v in value)}]")
        else:
            lines.append(f"{key}: {_scalar_out(value)}")
    lines.append("---")
    return "\n".join(lines)


def _strip_comment(text: str) -> str:
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text


def _scalar_in(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        try:
            return json.loads(text)
        except ValueError:
            return text[1:-1]
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _split_flow(text: str) -> list[str]:
    parts, buf, quote = [], "", ""
    for ch in text:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def parse_yaml(lines: list[str]) -> dict[str, Any]:
    """The small part of YAML that front matter uses: `key: value`, quoted strings, [a, b] and `- item` lists, | and > blocks, # comments."""
    out: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#") or raw[0] in " \t":
            continue
        m = re.match(r"^([^\s:#][^:]*?)\s*:(?:\s+(.*))?$", raw.rstrip())
        if not m:
            continue
        key = m.group(1).strip().strip("\"'")
        rest = _strip_comment((m.group(2) or "").strip())
        if rest[:1] in ("|", ">"):
            block: list[str] = []
            while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i].strip())
                i += 1
            out[key] = ("\n" if rest[0] == "|" else " ").join(block).strip()
        elif rest == "":
            items: list[Any] = []
            while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t-"):
                line = lines[i].strip()
                i += 1
                if line.startswith("- ") or line == "-":
                    items.append(_scalar_in(_strip_comment(line[2:])))
            out[key] = items or None
        elif rest.startswith("[") and rest.endswith("]"):
            out[key] = [_scalar_in(p) for p in _split_flow(rest[1:-1])]
        else:
            out[key] = _scalar_in(rest)
    return out


def split_front_matter(text: str, warnings: list[str] | None = None, where: str = "") -> tuple[dict[str, Any], str]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    fence = lines[0].strip() if lines else ""
    if fence not in ("---", "+++"):
        return {}, text
    for end in range(1, len(lines)):
        if lines[end].strip() == fence:
            block, body = lines[1:end], "\n".join(lines[end + 1:])
            if fence == "---":
                return parse_yaml(block), body
            try:
                return tomllib.loads("\n".join(block)), body
            except tomllib.TOMLDecodeError:
                if warnings is not None:
                    warnings.append(f"{where}: 文件开头的 TOML 属性读不懂，已当作没有。")
                return {}, body
    return {}, text


# ---- export -------------------------------------------------------------------------------------------------------------------
@dataclass
class _Pictures:
    session: Session
    cfg: Config
    names: dict[int, str] = field(default_factory=dict)
    manifest: list[dict] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def use(self, media_id: int | None) -> str | None:
        """The path of this picture inside the archive (relative to a post: ../media/...), or None when it cannot be exported."""
        if not media_id:
            return None
        if media_id in self.names:
            return self.names[media_id]
        media = self.session.get(Media, media_id)
        if media is None or not media.variants:
            return None
        biggest = max(media.variants, key=lambda v: int(v["size"]))
        path = media_service.media_path(self.cfg, media.hash, int(biggest["size"]))
        try:
            data = path.read_bytes()
        except OSError:
            self.missing.append(media.filename or str(media.id))
            return None
        stem = slugify(posixpath.splitext(media.filename or "")[0]) or "image"
        name = f"{media.id}-{stem}.webp"
        self.files[f"media/{name}"] = data
        self.manifest.append({"file": f"media/{name}", "id": media.id, "filename": media.filename, "alt": media.alt, "caption": media.caption,
                              "width": media.width, "height": media.height, "animated": media.animated})
        self.names[media_id] = f"../media/{name}"
        return self.names[media_id]

    def rewrite(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            path = self.use(int(m.group(1)))
            return f"({path}" if path else m.group(0)
        return re.sub(r"\(media:(\d+)", sub, text)


def _date(value: datetime | None) -> str | None:
    return iso(value) if value else None


def export_zip(session: Session, cfg: Config, tz_name: str) -> IO[bytes]:
    """The archive as an open binary file (closed, and so deleted, when the response is done)."""
    pics = _Pictures(session, cfg)
    entries: dict[str, str] = {}

    for post in session.scalars(select(Post).where(Post.deleted_at.is_(None)).order_by(Post.id)):
        meta = {
            "title": post.title, "slug": post.slug, "date": _date(post.published_at or post.created_at), "updated": _date(post.updated_at),
            "status": post.status, "category": post.category.name if post.category else None, "tags": [t.name for t in post.tags],
            "series": post.series.title if post.series else None, "series_order": post.series_order if post.series else None,
            "summary": None if post.summary_auto else post.summary, "cover": pics.use(post.cover_media_id), "cover_alt": post.cover_alt,
            "pinned": True if post.pinned else None, "featured": True if post.featured else None,
            "card_style": post.card_style if post.card_style != "auto" else None,
            "toc": False if not post.show_toc else None, "reading_time": False if not post.show_reading_time else None,
            "author_card": True if post.show_author_card else None,
            "seo_title": post.seo_title, "seo_description": post.seo_description, "canonical": post.canonical_url,
        }
        entries[f"posts/{post.slug}.md"] = f"{dump_front_matter(meta)}\n\n{pics.rewrite(post.content_md or '').rstrip()}\n"

    for page in session.scalars(select(Page).where(Page.deleted_at.is_(None)).order_by(Page.id)):
        meta = {"title": page.title, "slug": page.slug, "date": _date(page.published_at or page.created_at), "updated": _date(page.updated_at),
                "status": page.status, "template": page.template, "seo_title": page.seo_title, "seo_description": page.seo_description}
        entries[f"pages/{page.slug}.md"] = f"{dump_front_matter(meta)}\n\n{pics.rewrite(page.content_md or '').rstrip()}\n"

    for moment in session.scalars(select(Moment).where(Moment.deleted_at.is_(None)).order_by(Moment.id)):
        shown = [(pics.use(m.media_id), m.alt or "") for m in moment.media]
        shown = [(path, alt) for path, alt in shown if path]
        card = moment.link_card or {}
        meta = {"date": _date(moment.published_at), "visibility": moment.visibility, "mood": moment.mood, "tags": [t.name for t in moment.tags],
                "pinned": True if moment.pinned else None, "images": [p for p, _ in shown], "image_alts": [a for _, a in shown] if any(a for _, a in shown) else None,
                "link_url": card.get("url"), "link_title": card.get("title"), "link_description": card.get("description")}
        day = local(moment.published_at, tz_name).strftime("%Y-%m-%d")
        entries[f"moments/{day}-{moment.id}.md"] = f"{dump_front_matter(meta)}\n\n{pics.rewrite(moment.content_md or '').rstrip()}\n"

    readme = (
        "# 导出的内容\n\n"
        "- `posts/` 文章，`pages/` 页面，`moments/` 动态：每个文件是 Markdown，开头 `---` 之间是属性（front matter）。\n"
        "- `media/` 用到的图片（站点只保存 WebP 版本，这里是其中最大的一档），`media/manifest.json` 记录每张图的原文件名、替代文字、尺寸。\n"
        "- 文章里的图片写成相对路径 `../media/…`；导入回这个博客时会重新上传并换回图片库的引用。\n"
        "- 回收站里的内容、访问统计、账号和设置不在其中（那些用“备份”）。草稿、私密的内容在其中，状态写在属性头里。\n"
    )
    if pics.missing:
        readme += "\n## 缺少的图片文件\n\n" + "\n".join(f"- {name}" for name in sorted(set(pics.missing))) + "\n"

    out = tempfile.TemporaryFile()  # noqa: SIM115 - handed to the response, which closes it
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", readme)
        for name, text in entries.items():
            zf.writestr(name, text)
        for name, data in pics.files.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_STORED)       # already WebP
        zf.writestr("media/manifest.json", json.dumps(pics.manifest, ensure_ascii=False, indent=1))
    out.seek(0)
    return out


# ---- import -------------------------------------------------------------------------------------------------------------------
@dataclass
class ImportResult:
    posts: int = 0
    pages: int = 0
    moments: int = 0
    media: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, text: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(text)
        elif len(self.warnings) == MAX_WARNINGS:
            self.warnings.append("……还有更多提示没有列出。")

    def as_dict(self) -> dict:
        return {"posts": self.posts, "pages": self.pages, "moments": self.moments, "media": self.media, "skipped": self.skipped, "warnings": self.warnings}


class Archive:
    """The members of the zip by normalised path; nothing is unpacked to disk."""

    def __init__(self, zf: zipfile.ZipFile):
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise ApiError(422, "too_many_files", f"压缩包里的文件太多了（最多 {MAX_FILES} 个）。")
        total = 0
        self.zf = zf
        self.files: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = posixpath.normpath(info.filename.replace("\\", "/")).lstrip("/")
            if not name or name.startswith("..") or "/../" in f"/{name}/" or name.startswith("__MACOSX/") or posixpath.basename(name).startswith("._"):
                continue
            if info.file_size > MAX_MEMBER_BYTES or (info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1024 * 1024):
                raise ApiError(422, "archive_unsafe", "压缩包里有异常大的文件，已拒绝。")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ApiError(422, "archive_too_big", "压缩包解开后太大了。")
            self.files[name] = info
        roots = {n.split("/", 1)[0] for n in self.files}
        if len(roots) == 1 and all("/" in n for n in self.files):      # "mysite/…": drop the one wrapping folder
            prefix = f"{next(iter(roots))}/"
            self.files = {n[len(prefix):]: i for n, i in self.files.items()}
        self.by_base: dict[str, list[str]] = {}
        for n in self.files:
            self.by_base.setdefault(posixpath.basename(n).lower(), []).append(n)

    def read(self, name: str) -> bytes:
        return self.zf.read(self.files[name])

    def find_image(self, ref: str, base_dir: str, stem: str) -> str | None:
        ref = unquote(ref.split("#", 1)[0].split("?", 1)[0]).strip()
        if not ref or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", ref) or not ref.lower().endswith(IMAGE_EXT):
            return None
        tries: list[str] = []
        if ref.startswith("/"):
            bare = ref.lstrip("/")
            tries += [bare, f"static/{bare}", f"source/{bare}", f"public/{bare}", f"assets/{bare}"]
        else:
            tries += [posixpath.normpath(posixpath.join(base_dir, ref)), posixpath.normpath(posixpath.join(base_dir, stem, ref))]
            tries += [f"static/{ref}", f"source/{ref}", ref]
        for t in tries:
            if t in self.files:
                return t
        same = self.by_base.get(posixpath.basename(ref).lower(), [])
        return same[0] if len(same) == 1 else None            # a picture of that name that exists only once, wherever it lies


class _Importer:
    def __init__(self, session: Session, cfg: Config, archive: Archive, tz_name: str, keep_status: bool):
        self.session, self.cfg, self.archive, self.tz, self.keep = session, cfg, archive, tz_name, keep_status
        self.result = ImportResult()
        self.cache: dict[str, int | None] = {}

    # pictures
    def picture(self, path: str | None, alt: str = "") -> int | None:
        if path is None:
            return None
        if path in self.cache:
            return self.cache[path]
        mid: int | None = None
        try:
            media, created = media_service.create(self.session, self.cfg, self.archive.read(path), posixpath.basename(path), alt=alt)
            mid = media.id
            self.result.media += 1 if created else 0
        except ApiError as exc:
            self.result.warn(f"{path}: 图片没有导入（{exc.message}）")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            self.result.warn(f"{path}: 读不出来（{exc}）")
        self.cache[path] = mid
        return mid

    def lookup(self, ref: str, base_dir: str, stem: str, alt: str = "") -> int | None:
        return self.picture(self.archive.find_image(ref, base_dir, stem), alt)

    def rewrite_images(self, body: str, base_dir: str, stem: str, where: str) -> str:
        def sub(m: re.Match) -> str:
            ref = m.group(2).strip().strip("<>")
            alt = re.sub(r"[\][]", "", m.group(1)[2:-2])
            mid = self.lookup(ref, base_dir, stem, alt)
            if mid is None and not re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*:|/)", ref) and ref.lower().endswith(IMAGE_EXT):
                self.result.warn(f"{where}: 找不到图片 {ref}，链接保持原样。")
            return f"{m.group(1)}(media:{mid}{m.group(3)}" if mid else m.group(0)
        return re.sub(r"(!\[[^\]]*\])\(\s*(<[^>]+>|[^)\s]+)((?:\s+\"[^\"]*\")?\s*\))", sub, body)

    # small helpers
    def when(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return as_utc(value)
        if not isinstance(value, str) or not value.strip():
            return None
        text = re.sub(r"^(\d{4})/(\d{1,2})/(\d{1,2})", lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", value.strip())
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone(self.tz))           # "2026-10-23 08:00" in a Hexo file means the author's own clock
        return as_utc(parsed)

    @staticmethod
    def names(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [p.strip() for p in re.split(r"[,，]", value) if p.strip()]
        if isinstance(value, list):
            out: list[str] = []
            for v in value:
                out += _Importer.names(v) if isinstance(v, list | str) else ([str(v)] if v is not None else [])
            return out
        return [str(value)]

    @staticmethod
    def first(meta: dict, *keys: str) -> Any:
        for k in keys:
            if meta.get(k) not in (None, "", []):
                return meta[k]
        return None

    def status(self, meta: dict) -> str:
        if meta.get("draft") is True or meta.get("published") is False:
            return "draft"
        if not self.keep:
            return "draft"
        wanted = str(meta.get("status") or "published").lower()
        return wanted if wanted in defaults.POST_STATUSES else "published"

    def category(self, name: str) -> int:
        found = self.session.scalar(select(Category).where(func.lower(Category.name) == name.lower()))
        return found.id if found else taxonomy.create_category(self.session, name[:60]).id

    def series(self, title: str) -> int:
        found = self.session.scalar(select(Series).where(func.lower(Series.title) == title.lower()))
        return found.id if found else taxonomy.create_series(self.session, title[:120]).id

    def slug_of(self, model: type, meta: dict, stem: str, title: str, reserved: frozenset[str] = frozenset()) -> str:
        wanted = str(self.first(meta, "slug") or "").strip()
        if not wanted:
            url = str(self.first(meta, "url", "permalink") or "").strip("/ ")
            wanted = url.rsplit("/", 1)[-1] if url else ""
        base = slugify(wanted or re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)) or slugify(title)
        return unique_slug(self.session, model, base, fallback=f"imported-{utcnow():%Y%m%d%H%M%S}", reserved=reserved)

    # one file
    def one(self, path: str) -> None:
        raw = self.archive.read(path)
        if len(raw) > MAX_TEXT_BYTES:
            self.result.skipped += 1
            self.result.warn(f"{path}: 文件太大，跳过。")
            return
        text = raw.decode("utf-8", errors="replace")
        meta, body = split_front_matter(text, self.result.warnings, path)
        base_dir, stem = posixpath.dirname(path), posixpath.splitext(posixpath.basename(path))[0]
        if stem.lower() == "readme" and not meta:
            return
        if stem.startswith("_index") or (stem == "index" and meta.get("type") == "section"):
            self.result.skipped += 1
            return
        top = path.split("/", 1)[0].lower()
        kind = str(meta.get("type") or "").lower()
        if top in ("pages", "page") or kind == "page":
            kind = "page"
        elif top == "moments" or kind == "moment":
            kind = "moment"
        else:
            kind = "post"
        snapshot = (dict(self.cache), self.result.media)       # pictures stored for a file that gets rolled back are forgotten with it
        try:
            with self.session.begin_nested():
                {"post": self.post, "page": self.page, "moment": self.moment}[kind](path, meta, body, base_dir, stem)
        except (ApiError, SQLAlchemyError) as exc:
            self.cache, self.result.media = snapshot
            raise _Skip(f"{path}: {exc.message if isinstance(exc, ApiError) else '数据库没有接受这一项'}") from exc

    def title_of(self, meta: dict, body: str, stem: str) -> tuple[str, str]:
        title = str(self.first(meta, "title") or "").strip()
        if not title:
            m = re.match(r"\s*#\s+(.+?)\s*#*\s*\n", body)
            if m:
                title, body = m.group(1).strip(), body[m.end():]
        return (title or stem.replace("-", " ").replace("_", " ").strip() or "未命名")[:200], body

    def post(self, path: str, meta: dict, body: str, base_dir: str, stem: str) -> None:
        title, body = self.title_of(meta, body, stem)
        body = self.rewrite_images(body, base_dir, stem, path)
        dated = re.match(r"^(\d{4}-\d{2}-\d{2})-", stem)
        when = self.when(self.first(meta, "date", "published_at", "created", "created_at", "pubdate", "publishDate", "published")) or (self.when(dated.group(1)) if dated else None)
        data: dict[str, Any] = {
            "title": title, "slug": self.slug_of(Post, meta, stem, title), "content_md": body.strip("\n") + "\n", "status": self.status(meta),
            "summary": str(self.first(meta, "summary", "description", "excerpt", "abstract") or "")[:1000],
        }
        if when:
            data["published_at"] = when
        cats = self.names(self.first(meta, "category", "categories"))
        if cats:
            data["category_id"] = self.category(cats[0])
        data["tags"] = self.names(meta.get("tags"))[:20]
        series = str(self.first(meta, "series") or "").strip()
        if series:
            data["series_id"] = self.series(series)
            if isinstance(meta.get("series_order"), int):
                data["series_order"] = max(1, meta["series_order"])
        cover_ref = self.first(meta, "cover", "image", "featured_image", "thumbnail", "banner", "heroImage")
        if isinstance(cover_ref, list):
            cover_ref = cover_ref[0] if cover_ref else None
        mid = self.lookup(str(cover_ref), base_dir, stem) if isinstance(cover_ref, str) else None
        if mid:
            data["cover_media_id"] = mid
            data["cover_alt"] = str(meta.get("cover_alt") or "")[:300]
        for src, dest in (("pinned", "pinned"), ("sticky", "pinned"), ("featured", "featured"), ("toc", "show_toc"), ("reading_time", "show_reading_time"), ("author_card", "show_author_card")):
            if isinstance(meta.get(src), bool):
                data[dest] = meta[src]
        if meta.get("card_style") in defaults.CARD_STYLES:
            data["card_style"] = meta["card_style"]
        for src, dest in (("seo_title", "seo_title"), ("seo_description", "seo_description"), ("canonical", "canonical_url"), ("canonical_url", "canonical_url")):
            if isinstance(meta.get(src), str):
                data[dest] = meta[src][:300]
        if data.get("canonical_url") and not re.match(r"^https?://", data["canonical_url"]):
            data.pop("canonical_url")
        posts.create(self.session, data)
        self.result.posts += 1

    def page(self, path: str, meta: dict, body: str, base_dir: str, stem: str) -> None:
        title, body = self.title_of(meta, body, stem)
        body = self.rewrite_images(body, base_dir, stem, path)
        data: dict[str, Any] = {
            "title": title, "slug": self.slug_of(Page, meta, stem, title, paths.RESERVED_PAGE_SLUGS), "content_md": body.strip("\n") + "\n", "status": self.status(meta),
            "template": meta["template"] if meta.get("template") in defaults.PAGE_TEMPLATES else "plain",
            "seo_title": str(meta.get("seo_title") or "")[:200], "seo_description": str(meta.get("seo_description") or "")[:400],
        }
        when = self.when(self.first(meta, "date", "published_at", "created"))
        if when:
            data["published_at"] = when
        pages.create(self.session, data)
        self.result.pages += 1

    def moment(self, path: str, meta: dict, body: str, base_dir: str, stem: str) -> None:
        items: list[dict] = []
        refs = meta.get("images") if isinstance(meta.get("images"), list) else []
        alts = meta.get("image_alts") if isinstance(meta.get("image_alts"), list) else []
        for n, ref in enumerate(refs):
            alt = str(alts[n]) if n < len(alts) else ""
            mid = self.lookup(str(ref), base_dir, stem, alt)
            if mid:
                items.append({"media_id": mid, "alt": alt})

        def pull(m: re.Match) -> str:                 # a picture written inside the text becomes one of the moment's pictures
            mid = self.lookup(m.group(2).strip().strip("<>"), base_dir, stem, m.group(1)[2:-1])
            if mid:
                items.append({"media_id": mid, "alt": re.sub(r"[\][]", "", m.group(1)[2:-1])})
                return ""
            return m.group(0)
        text = re.sub(r"(!\[[^\]]*\])\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)", pull, body).strip()
        visibility = "private"
        if self.keep:
            visibility = meta["visibility"] if meta.get("visibility") in defaults.MOMENT_VISIBILITIES else "public"
        data: dict[str, Any] = {"text": text, "tags": self.names(meta.get("tags"))[:20], "visibility": visibility, "auto_tags": False, "media": items[: moments.MAX_MEDIA],
                                "pinned": bool(meta.get("pinned")) if isinstance(meta.get("pinned"), bool) else False}
        if meta.get("mood") in defaults.MOODS:
            data["mood"] = meta["mood"]
        when = self.when(self.first(meta, "date", "published_at", "created"))
        if when:
            data["published_at"] = when
        if isinstance(meta.get("link_url"), str) and re.match(r"^https?://", meta["link_url"]):
            data["link_card"] = {"url": meta["link_url"], "title": str(meta.get("link_title") or "")[:200], "description": str(meta.get("link_description") or "")[:300]}
        moments.create(self.session, data)
        self.result.moments += 1


class _Skip(Exception):
    """One file could not be imported; its changes are rolled back to the savepoint and the others carry on."""


def import_zip(session: Session, cfg: Config, source: IO[bytes], tz_name: str, *, keep_status: bool = False) -> dict:
    try:
        zf = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ApiError(422, "bad_archive", "这不是有效的 .zip 压缩包。") from exc
    with zf:
        archive = Archive(zf)
        importer = _Importer(session, cfg, archive, tz_name, keep_status)
        files = sorted(n for n in archive.files if n.lower().endswith(MD_EXT))
        if not files:
            raise ApiError(422, "nothing_to_import", "压缩包里没有 Markdown 文件（.md）。")
        for path in files:
            try:
                importer.one(path)
            except _Skip as skipped:
                importer.result.skipped += 1
                importer.result.warn(str(skipped))
            except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                importer.result.skipped += 1
                importer.result.warn(f"{path}: 读不出来（{exc}）")
        return importer.result.as_dict()
