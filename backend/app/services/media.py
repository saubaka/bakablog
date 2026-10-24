"""Picture pipeline: validate -> decode safely -> fix orientation -> strip metadata -> WebP in three sizes -> content-hash names.

What an upload goes through (the upload is never trusted):
  1. size limit, then the file's magic bytes (JPEG / PNG / GIF / WebP only; SVG, HTML, PDF ... are refused),
  2. the header is read first: pixel count and edge length are checked BEFORE anything is decoded (image bombs),
  3. full decode inside a try (truncated or corrupt files are refused), animation frame limit,
  4. EXIF orientation applied, then every piece of metadata (EXIF incl. GPS, XMP, comments) is dropped by re-encoding;
     a colour profile is converted to sRGB first so colours do not shift,
  5. WebP variants 480 / 960 / 1600 wide (never enlarged), animated pictures keep their animation (<= 960),
  6. files are named by the hash of the upload: /media/<hash>/<size>.webp is immutable and cacheable for a year.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, ImageSequence, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Config
from app.errors import ApiError
from app.models import Media, MediaRef
from app.timeutil import utcnow

log = logging.getLogger(__name__)

SIZES = (480, 960, 1600)
ANIMATED_MAX_SIZE = 960
HASH_LEN = 32
HASH_RE = re.compile(r"^[0-9a-f]{16,64}$")
FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}


@dataclass
class Inspected:
    format: str
    width: int
    height: int
    frames: int


def sniff(data: bytes) -> str | None:
    """Image format from the first bytes (the file name and the client's content type mean nothing)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def _bad(code: str, message: str, status: int = 422) -> ApiError:
    return ApiError(status, code, message)


def inspect(data: bytes, cfg: Config) -> tuple[Image.Image, Inspected]:
    """Validate without decoding pixels. Returns the opened (not yet decoded) image."""
    if not data:
        raise _bad("empty_file", "文件是空的。")
    if len(data) > cfg.max_upload_bytes:
        raise _bad("too_large", f"文件太大了（上限 {cfg.max_upload_bytes // (1024 * 1024)} MB）。", 413)
    kind = sniff(data)
    if kind is None:
        raise _bad("unsupported_type", "只支持 JPG、PNG、GIF、WebP 图片。", 415)
    try:
        im = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:  # Pillow's own guard, reached before ours for the really absurd sizes
        raise _bad("image_too_large", "图片像素太多。请先缩小再上传。", 413) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise _bad("bad_image", "图片无法读取，文件可能已损坏。") from exc
    if im.format != kind:
        raise _bad("unsupported_type", "文件内容和格式不符。", 415)
    width, height = im.size
    if width < 1 or height < 1:
        raise _bad("bad_image", "图片尺寸不对。")
    if width * height > cfg.max_image_pixels or max(width, height) > cfg.max_image_side:
        raise _bad("image_too_large", f"图片像素太多（{width}×{height}）。请先缩小再上传。", 413)
    frames = int(getattr(im, "n_frames", 1) or 1)
    if frames > cfg.max_animation_frames:
        raise _bad("too_many_frames", f"动图帧数太多（{frames} 帧，上限 {cfg.max_animation_frames}）。")
    return im, Inspected(kind, width, height, frames)


def _to_srgb(im: Image.Image) -> Image.Image:
    icc = im.info.get("icc_profile")
    if not icc:
        return im
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        mode = "RGBA" if "A" in im.getbands() else "RGB"
        return ImageCms.profileToProfile(im.convert(mode), src, dst, outputMode=mode)
    except (ImageCms.PyCMSError, OSError, ValueError):
        return im


def _normalise(im: Image.Image) -> Image.Image:
    """Orientation applied, colours in sRGB, plain RGB / RGBA, no metadata."""
    im = ImageOps.exif_transpose(im)
    im = _to_srgb(im)
    has_alpha = "A" in im.getbands() or "transparency" in im.info
    return im.convert("RGBA" if has_alpha else "RGB")


def _dominant_color(im: Image.Image) -> str:
    thumb = im.convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)
    quant = thumb.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    counts = sorted(quant.getcolors() or [], reverse=True)
    palette = quant.getpalette() or []
    if not counts:
        return "#e6f1fc"
    index = counts[0][1]
    r, g, b = palette[index * 3: index * 3 + 3]
    return f"#{r:02x}{g:02x}{b:02x}"


def _few_colors(im: Image.Image) -> bool:
    """Flat illustrations, screenshots and logos compress better (and cleaner) as lossless WebP."""
    return im.convert("RGBA").getcolors(maxcolors=2048) is not None


def _plan(width: int) -> list[tuple[int, int]]:
    """[(label, actual width)]: 480 / 960 / 1600, never wider than the picture itself, no duplicates."""
    out: list[tuple[int, int]] = []
    seen: set[int] = set()
    for size in SIZES:
        w = min(size, width)
        if w in seen:
            continue
        seen.add(w)
        out.append((size, w))
    return out


def _encode_static(im: Image.Image, lossless: bool) -> bytes:
    buf = io.BytesIO()
    if lossless:
        im.save(buf, "WEBP", lossless=True, quality=90, method=4)
    else:
        im.save(buf, "WEBP", quality=82, method=4)
    return buf.getvalue()


def _static_variants(im: Image.Image, width: int, height: int, lossless: bool) -> list[tuple[int, int, int, bytes]]:
    out = []
    for label, w in _plan(width):
        h = max(1, round(height * w / width))
        frame = im if w == width else im.resize((w, h), Image.Resampling.LANCZOS)
        out.append((label, w, h, _encode_static(frame, lossless)))
    return out


def _animated_variants(source: Image.Image, width: int, height: int) -> list[tuple[int, int, int, bytes]]:
    out = []
    frames_info = [(f.convert("RGBA"), int(f.info.get("duration", 100) or 100)) for f in ImageSequence.Iterator(source)]
    loop = int(source.info.get("loop", 0) or 0)
    for label, w in _plan(width):
        if label > ANIMATED_MAX_SIZE:
            continue
        h = max(1, round(height * w / width))
        frames = [fr if w == width else fr.resize((w, h), Image.Resampling.LANCZOS) for fr, _ in frames_info]
        buf = io.BytesIO()
        frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=[max(20, d) for _, d in frames_info], loop=loop,
                       quality=75, method=3)
        out.append((label, w, h, buf.getvalue()))
    return out


# ---- storage ----------------------------------------------------------------------------------------------------------------------
def media_dir(cfg: Config, media_hash: str) -> Path:
    return cfg.media_dir / media_hash[:2] / media_hash


def media_path(cfg: Config, media_hash: str, size: int) -> Path:
    return media_dir(cfg, media_hash) / f"{size}.webp"


def _write_files(cfg: Config, media_hash: str, variants: list[tuple[int, int, int, bytes]]) -> None:
    folder = media_dir(cfg, media_hash)
    folder.mkdir(parents=True, exist_ok=True)
    for label, _w, _h, payload in variants:
        target = folder / f"{label}.webp"
        tmp = folder / f".{label}.webp.tmp"
        tmp.write_bytes(payload)
        os.replace(tmp, target)


def delete_files(cfg: Config, media_hash: str) -> None:
    folder = media_dir(cfg, media_hash)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
        with contextlib.suppress(OSError):
            folder.parent.rmdir()  # the two-letter folder, when it is empty now


@dataclass
class Processed:
    hash: str
    mime: str
    width: int
    height: int
    size_bytes: int
    color: str
    animated: bool
    variants: list[tuple[int, int, int, bytes]]


def process(data: bytes, cfg: Config) -> Processed:
    """Everything that does not touch the database: validate, normalise, encode."""
    opened, info = inspect(data, cfg)
    try:
        animated = info.frames > 1
        if animated:
            first = _normalise(ImageSequence.Iterator(opened).__next__())
            opened.seek(0)
            variants = _animated_variants(opened, info.width, info.height)
            width, height = first.size
            color = _dominant_color(first)
        else:
            opened.load()
            lossless = info.format == "PNG" and _few_colors(opened)
            clean = _normalise(opened)
            width, height = clean.size
            color = _dominant_color(clean)
            variants = _static_variants(clean, width, height, lossless)
    except ApiError:
        raise
    except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError) as exc:
        raise _bad("bad_image", "图片无法处理，文件可能已损坏。") from exc
    if not variants:
        raise _bad("bad_image", "图片无法处理。")
    return Processed(
        hash=hashlib.sha256(data).hexdigest()[:HASH_LEN], mime=FORMAT_MIME[info.format], width=width, height=height,
        size_bytes=len(data), color=color, animated=animated, variants=variants,
    )


def _variants_json(p: Processed) -> list[dict]:
    return [{"size": label, "w": w, "h": h, "bytes": len(payload)} for label, w, h, payload in p.variants]


def clean_filename(name: str | None) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return name[:200] or "image"


def create(session: Session, cfg: Config, data: bytes, filename: str | None, *, alt: str = "", caption: str = "",
           kind: str = "image") -> tuple[Media, bool]:
    """Store an upload. Returns (media, created). The same bytes uploaded twice give back the same row (a trashed one is restored)."""
    p = process(data, cfg)
    existing = session.scalar(select(Media).where(Media.hash == p.hash))
    if existing is not None:
        if existing.deleted_at is not None:
            existing.deleted_at = None
        if not (media_path(cfg, existing.hash, existing.variants[0]["size"]).exists() if existing.variants else False):
            _write_files(cfg, p.hash, p.variants)  # files went missing: put them back
        return existing, False
    _write_files(cfg, p.hash, p.variants)
    media = Media(
        hash=p.hash, filename=clean_filename(filename), kind=kind, mime=p.mime, width=p.width, height=p.height, bytes=p.size_bytes,
        alt=alt.strip()[:300], caption=caption.strip()[:500], color=p.color, variants=_variants_json(p), animated=p.animated,
    )
    session.add(media)
    session.flush()
    return media, True


def replace(session: Session, cfg: Config, media: Media, data: bytes, filename: str | None) -> str:
    """New file, same row: references (ids) keep working. Returns the OLD hash; delete its files after the commit."""
    p = process(data, cfg)
    if p.hash == media.hash:
        return media.hash
    clash = session.scalar(select(Media.id).where(Media.hash == p.hash, Media.id != media.id))
    if clash is not None:
        raise ApiError(409, "duplicate", "媒体库里已经有这张图片了。", extra={"media_id": clash})
    _write_files(cfg, p.hash, p.variants)
    old = media.hash
    media.hash = p.hash
    media.mime, media.width, media.height, media.bytes = p.mime, p.width, p.height, p.size_bytes
    media.color, media.animated, media.variants = p.color, p.animated, _variants_json(p)
    if filename:
        media.filename = clean_filename(filename)
    media.updated_at = utcnow()
    session.flush()
    return old


def regenerate_variants(session: Session, cfg: Config, media: Media) -> bool:
    """Rebuild the smaller sizes from the largest stored one (the "regenerate thumbnails" button)."""
    largest = max(media.variants or [], key=lambda v: v["w"], default=None)
    if largest is None or media.animated:
        return False
    path = media_path(cfg, media.hash, largest["size"])
    if not path.exists():
        return False
    p = process(path.read_bytes(), cfg)
    _write_files(cfg, media.hash, p.variants)
    media.variants = _variants_json(p)
    media.color = p.color
    return True


# ---- queries and bookkeeping -------------------------------------------------------------------------------------------------------
def usage_counts(session: Session, media_ids: list[int]) -> dict[int, int]:
    if not media_ids:
        return {}
    rows = session.execute(select(MediaRef.media_id, func.count()).where(MediaRef.media_id.in_(media_ids)).group_by(MediaRef.media_id))
    return {mid: n for mid, n in rows}


def purge(session: Session, cfg: Config, media: Media) -> None:
    """Remove the row and its files for good (references in rendered content are re-rendered by the caller)."""
    old_hash = media.hash
    session.delete(media)
    session.flush()
    delete_files(cfg, old_hash)
