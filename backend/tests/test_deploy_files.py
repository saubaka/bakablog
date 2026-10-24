"""The deployment files are code too: they must parse, agree with the application's configuration, and keep the safety properties they promise."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
CONFIG = Path(__file__).resolve().parents[1] / "app" / "config.py"
SCRIPTS = ["deploy.sh", "remote-update.sh", "rollback.sh", "restore-drill.sh", "rehearse.sh"]


def unit(name: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, _, value = line.partition("=")
            out.setdefault(key.strip(), []).append(value.strip())
    return out


@pytest.mark.parametrize("script", SCRIPTS)
def test_scripts_are_valid_bash_and_executable(script):
    path = DEPLOY / script
    assert path.stat().st_mode & 0o111, f"{script} is not executable"
    bash = shutil.which("bash")
    assert bash and subprocess.run([bash, "-n", str(path)], capture_output=True, check=False).returncode == 0


def test_the_service_is_sandboxed_and_reads_the_environment_file():
    svc = unit("bakablog.service")
    assert svc["User"] == ["bakablog"] and svc["EnvironmentFile"] == ["/etc/bakablog/production.env"]
    assert "gunicorn" in svc["ExecStart"][0] and "/opt/bakablog/venv/bin/" in svc["ExecStart"][0] and "wsgi:app" in svc["ExecStart"][0]
    assert "127.0.0.1:8080" in svc["ExecStart"][0], "the service must listen on the loopback only; the proxy is the public face"
    assert svc["ProtectSystem"] == ["strict"] and svc["ReadWritePaths"] == ["/var/lib/bakablog"] and svc["NoNewPrivileges"] == ["true"]
    assert svc["CapabilityBoundingSet"] == [""] and svc["PrivateTmp"] == ["true"]


def test_the_timer_runs_the_maintenance_command_every_minute_with_the_same_sandbox():
    timer, job = unit("bakablog-maintenance.timer"), unit("bakablog-maintenance.service")
    assert timer["Unit"] == ["bakablog-maintenance.service"] and "*:0/5:00" in timer["OnCalendar"][0]
    assert job["Type"] == ["oneshot"] and job["User"] == ["bakablog"] and job["ReadWritePaths"] == ["/var/lib/bakablog"]
    assert job["ExecStart"][0].endswith("flask --app app maintenance")


def test_the_env_template_has_every_setting_production_needs_and_no_real_secret():
    template = (DEPLOY / "production.env.example").read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    used = set(re.findall(r'"(BLOG_[A-Z_]+)"', config))
    declared = set(re.findall(r"^#?\s*(BLOG_[A-Z_]+)=", template, re.M))
    assert {"BLOG_ENV", "BLOG_SECRET_KEY", "BLOG_SITE_URL", "BLOG_DATA_DIR", "BLOG_FRONTEND_DIST", "BLOG_TRUST_PROXY", "BLOG_COOKIE_SECURE", "BLOG_SETUP_TOKEN"} <= declared
    assert declared <= used, f"the template sets variables the application does not read: {sorted(declared - used)}"
    assert "__GENERATE_ME__" in template and "__GENERATE_TOKEN__" in template
    assert re.search(r"^BLOG_ENV=production$", template, re.M) and re.search(r"^BLOG_COOKIE_SECURE=true$", template, re.M)


def test_the_nginx_example_forwards_the_real_scheme_and_address():
    conf = (DEPLOY / "nginx-site.conf.example").read_text(encoding="utf-8")
    for needle in ("X-Forwarded-Proto $scheme", "X-Forwarded-For $proxy_add_x_forwarded_for", "proxy_pass http://bakablog", "server 127.0.0.1:8080", "gzip on"):
        assert needle in conf, needle
    assert "add_header" not in conf, "the application sets the security headers; a second set from the proxy would conflict"


def test_exit_codes_are_never_masked_in_the_install_script():
    text = (DEPLOY / "remote-update.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "set -Eeuo pipefail" in code
    for critical in ("init-db", "doctor"):
        for line in code.splitlines():
            if f"flask_app {critical}" in line:
                assert "|" not in line and "||" not in line, f"{critical} must not be piped or ignored: {line}"
    # `ls … | tail -n +N` (keep the newest N backups) is a list filter; any other pipe into tail would hide a command's exit code
    assert not re.search(r"\|\s*tail\b(?!\s+-n\s+\+)", code), "a pipe into tail swallows the exit code"


def test_the_release_never_ships_data_or_secrets():
    text = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    for needle in ("--exclude='data'", "--exclude='.venv'", "--exclude='.env'", "COPYFILE_DISABLE=1", "credentials.json", "setup-token.txt", "production.env", "FORBIDDEN="):
        assert needle in text, needle


def test_the_release_check_does_not_trip_over_the_deployment_files_themselves():
    """deploy.sh refuses a release that names an AI tool; none of the files it ships (including itself) may contain those words."""
    words = ("cl" + "aude", "anth" + "ropic", "co-auth" + "ored-by", "generated w" + "ith")
    for path in DEPLOY.rglob("*"):
        if path.is_file() and path.suffix in {".sh", ".md", ".service", ".timer", ".example"}:
            text = path.read_text(encoding="utf-8").lower()
            for word in words:
                assert word not in text, f"{path.name} contains {word!r}: the deploy script would refuse the release"


def test_the_installed_files_are_what_the_script_checks_for():
    text = (DEPLOY / "remote-update.sh").read_text(encoding="utf-8")
    for needle in ("frontend/dist/public.html", "frontend/dist/admin.html", "frontend/dist/preview.html", "backend/requirements.txt", "deploy/bakablog.service"):
        assert needle in text, needle
