"""Local image validation and thumbnail generation."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage


class MediaValidationError(ValueError):
    """Raised when an uploaded file is not a safe supported image."""


@dataclass(frozen=True)
class StoredImage:
    filename: str
    thumbnail_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int


FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


def store_image(upload: FileStorage) -> StoredImage:
    if not upload.filename:
        raise MediaValidationError("请选择要上传的图片。")

    root = Path(current_app.instance_path)
    temp_dir = root / "tmp"
    upload_dir = root / "uploads"
    original_dir = upload_dir / "originals"
    thumbnail_dir = upload_dir / "thumbnails"
    for directory in (temp_dir, original_dir, thumbnail_dir):
        directory.mkdir(parents=True, exist_ok=True)

    temp_path = temp_dir / f"upload-{uuid4().hex}.tmp"
    upload.save(temp_path)
    try:
        size_bytes = temp_path.stat().st_size
        if size_bytes <= 0:
            raise MediaValidationError("上传文件为空。")
        if size_bytes > int(current_app.config["MAX_MEDIA_FILE_SIZE"]):
            raise MediaValidationError("图片超过单文件大小限制。")

        Image.MAX_IMAGE_PIXELS = int(current_app.config["MAX_IMAGE_PIXELS"])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(temp_path) as probe:
                    image_format = str(probe.format or "").upper()
                    probe.verify()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise MediaValidationError("图片像素尺寸过大。") from None
        except (UnidentifiedImageError, OSError, SyntaxError):
            raise MediaValidationError("文件不是可识别的图片。") from None

        if image_format not in FORMATS:
            raise MediaValidationError("仅支持 JPEG、PNG 和 WebP 图片。")

        extension, mime_type = FORMATS[image_format]
        token = uuid4().hex
        relative_name = f"originals/{token}{extension}"
        thumbnail_name = f"thumbnails/{token}.webp"
        output_path = upload_dir / relative_name
        thumbnail_path = upload_dir / thumbnail_name

        with Image.open(temp_path) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
            width, height = image.size
            _save_sanitized(image, output_path, image_format)
            thumbnail = image.copy()
            thumbnail.thumbnail(
                tuple(current_app.config["MEDIA_THUMBNAIL_SIZE"]), Image.Resampling.LANCZOS
            )
            if thumbnail.mode not in {"RGB", "RGBA"}:
                thumbnail = thumbnail.convert("RGBA" if "transparency" in thumbnail.info else "RGB")
            thumbnail.save(thumbnail_path, format="WEBP", quality=82, method=4)

        return StoredImage(
            filename=relative_name,
            thumbnail_filename=thumbnail_name,
            mime_type=mime_type,
            size_bytes=output_path.stat().st_size,
            width=width,
            height=height,
        )
    finally:
        temp_path.unlink(missing_ok=True)


def delete_stored_image(filename: str, thumbnail_filename: str) -> None:
    upload_root = (Path(current_app.instance_path) / "uploads").resolve()
    for relative in (filename, thumbnail_filename):
        candidate = (upload_root / relative).resolve()
        if upload_root in candidate.parents:
            candidate.unlink(missing_ok=True)


def _save_sanitized(image: Image.Image, output_path: Path, image_format: str) -> None:
    if image_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(output_path, format="JPEG", quality=88, optimize=True, progressive=True)
    elif image_format == "PNG":
        if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
            image = image.convert("RGBA")
        image.save(output_path, format="PNG", optimize=True)
    else:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        image.save(output_path, format="WEBP", quality=88, method=4)
