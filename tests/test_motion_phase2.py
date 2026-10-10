"""Structural contracts, supplemented by the browser motion lifecycle probe."""
from pathlib import Path


def test_geometry_uses_local_dimensions_and_closed_path():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    geometry = script.split("const configureMotionOutline =", 1)[1].split("const motionTargetRegistry", 1)[0]
    assert "getBoundingClientRect" not in geometry
    assert "outline.clientWidth || target.clientWidth" in geometry
    assert "outline.clientHeight || target.clientHeight" in geometry
    assert "motionGeometryKey" in geometry
    assert "`H ${point(center)} Z`" in geometry
    assert "setAttribute('vector-effect'" not in script
    assert "part?.endsWith('%')" in script


def test_runtime_has_shared_roots_and_explicit_lifecycle():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    for fragment in (
        "const motionObservers = new Map()", "data-motion-scroll-root",
        "root: scrollRoot", "target.contains(doc.activeElement)",
        "window.CloudtraceMotion =", "window.addEventListener('pagehide', disposeMotion)",
        "motionMutation?.disconnect()", "motionResizeObserver?.disconnect()",
        "systemReducedMotion.removeEventListener", "motionQueueTimers.clear()",
        "motionPreferenceObserver.observe(root", "doc.fonts?.ready",
        "releaseTimers.clear()", "releaseTimers.delete(control)",
    ):
        assert fragment in script


def test_shared_timeline_overlaps_content_instead_of_serial_waiting():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    assert "surfaceEnd: .78, textStart: .06, textEnd: .86" in script
    assert "lineEnd: .82" in script
    assert "progress, .04, .82, 'control'" in script
    assert "motionQueueTimers" in script
    assert "timeline.token += 1" in script
    assert "createMotionTimeline(owner, progress)" in script


def test_phase2_preview_matches_the_actual_runtime():
    html = Path("app/templates/admin/content/transitions.html").read_text(encoding="utf-8")
    assert "(20, '开始浮现')" in html
    assert "(82, '轮廓闭合')" in html
    assert "(38, '主线完成')" not in html
    css = Path("app/static/styles/small-window-theme.css").read_text(encoding="utf-8")
    assert "@keyframes small-window-control-release" in css
    assert "html.is-motion-ready[data-motion=\"reduce\"]" in css


def test_saved_outline_color_is_applied_outside_the_settings_page():
    script = Path("app/static/scripts/app.js").read_text(encoding="utf-8")
    assert "componentMotionColor: '--component-motion-color'" in script
    assert "CSS.supports('color', root.dataset[key])" in script
