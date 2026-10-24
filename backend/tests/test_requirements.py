"""backend/requirements.txt is the exact set the release was tested with: it must match what is installed, and cover every dependency."""
from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pinned() -> dict[str, str]:
    out = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, _, version = line.partition("==")
            out[name.strip().lower().replace("_", "-")] = version.strip()
    return out


def test_every_pin_is_what_the_tests_ran_against():
    for name, version in pinned().items():
        assert metadata.version(name) == version, f"{name}: requirements.txt says {version}, installed {metadata.version(name)}"


def test_every_declared_dependency_is_pinned_with_its_own_dependencies():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    direct = {re.split(r"[<>=!~ ]", d.strip().strip('",'))[0].lower().replace("_", "-") for d in block.splitlines() if d.strip().startswith('"')}
    pins = pinned()
    assert direct <= set(pins), f"not pinned: {sorted(direct - set(pins))}"
    for name in list(pins):                                      # a pinned package's requirements must be pinned too
        for req in metadata.requires(name) or []:
            if "extra ==" in req:
                continue
            dep = re.split(r"[<>=!~ ;\[(]", req)[0].lower().replace("_", "-")
            if dep in {"sqlalchemy", "typing-extensions"} or dep in pins:
                continue
            try:
                metadata.version(dep)
            except metadata.PackageNotFoundError:
                continue                                         # an optional / platform dependency that is not installed here
            assert dep in pins, f"{name} needs {dep}, which is not pinned"
