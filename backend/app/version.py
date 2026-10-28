"""Version and build id. The footer, /api/health and the system page show them, so "which build is running" is never a guess."""
import os
from pathlib import Path

__version__ = "0.6.0"

_BUILD_FILE = Path(__file__).resolve().parent.parent / "BUILD"


def build_id() -> str:
    """The deploy script writes backend/BUILD (or sets BLOG_BUILD); a plain checkout reports "dev"."""
    env = os.environ.get("BLOG_BUILD", "").strip()
    if env:
        return env
    try:
        text = _BUILD_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "dev"
    return text or "dev"
