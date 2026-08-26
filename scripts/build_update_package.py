"""Build a deterministic, validated baka blog update archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "bakagit",
    "instance",
    "node_modules",
    "obj",
    "bin",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if relative.parts[:2] in {("dist", "update-packages"), ("updates", "packages")}:
        return False
    return path.is_file()


def build(version: str, output: Path) -> dict[str, object]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must use x.y.z")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = json.dumps(
        {"schema_version": 1, "version": version}, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        info = zipfile.ZipInfo("update.json", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, descriptor)
        for path in sorted(item for item in ROOT.rglob("*") if included(item)):
            relative = path.relative_to(ROOT).as_posix()
            item = zipfile.ZipInfo(f"payload/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "url": f"https://github.com/saubaka/bakablog/releases/download/v{version}/{output.name}",
        "size": output.stat().st_size,
        "sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="default: dist/update-packages/bakablog-update-VERSION.zip",
    )
    args = parser.parse_args()
    output = args.output or ROOT / "dist" / "update-packages" / f"bakablog-update-{args.version}.zip"
    print(json.dumps({"package": build(args.version, output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
