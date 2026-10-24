"""Flask CLI commands:  flask --app app <command>"""
from __future__ import annotations

import click
from flask import Flask


def register(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create / upgrade the database to the latest schema."""
        from app import migrate
        from app.db import database

        migrate.upgrade(database())
        click.echo(f"database is at revision {migrate.head_revision()}")

    @app.cli.command("setup-token")
    def setup_token():
        """Print a new one-time setup token (only while no administrator exists)."""
        from app.db import session_scope
        from app.services import auth

        with session_scope() as session:
            if auth.owner_exists(session):
                raise click.ClickException("an administrator already exists; setup is closed")
            token = auth.issue_setup_token(session)
        from app import write_dev_token_file
        from app.config import cfg

        write_dev_token_file(cfg(), token)
        click.echo(f"setup token: {token}")


def register_more(app: Flask) -> None:
    """Commands added in later steps of this phase (kept apart so each file stays readable)."""

    @app.cli.command("maintenance")
    @click.option("--job", type=click.Choice(["backup", "housekeeping", "trash", "reindex", "thumbnails", "vacuum", "cache"]), default=None,
                  help="Run one job now. Without it the scheduled set runs (daily backup when due, daily housekeeping and trash purge).")
    @click.option("--force", is_flag=True, help="With --job backup: make a backup even if one was made today.")
    def maintenance_cmd(job: str | None, force: bool):
        """Background chores (a systemd timer runs this every 5 minutes)."""
        from app.jobs import maintenance

        result = maintenance.run_one(app, job, **({"force": True} if force and job == "backup" else {})) if job else maintenance.run_scheduled(app)
        click.echo(__import__("json").dumps(result, ensure_ascii=False, indent=2, default=str))

    @app.cli.command("backup")
    @click.option("--label", default="manual", show_default=True, help="Lower-case letters and dashes; shows in the file name (the deploy script uses pre-deploy).")
    def backup_cmd(label: str):
        """Make a backup now."""
        from app.config import cfg
        from app.db import database
        from app.services import backup

        info = backup.create(cfg(), database(), label=label)
        click.echo(f"{info.name}  ({info.bytes} bytes)")

    @app.cli.command("restore")
    @click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=__import__("pathlib").Path))
    @click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
    def restore_cmd(archive, yes: bool):
        """Replace ALL data with a backup file (stop the service first). A "pre-restore" backup of the current data is made before anything changes."""
        from app.errors import ApiError
        from app.services import backup

        if not yes:
            click.confirm(f"Replace the posts, moments, pictures, settings and accounts with {archive.name}?", abort=True)
        try:
            result = backup.restore(app, archive)
        except ApiError as exc:
            raise click.ClickException(exc.message) from exc
        click.echo(f"restored from {result['restored_from']}; the data as it was before is in {result['safety_backup']}")

    @app.cli.command("doctor")
    def doctor_cmd():
        """Check that this installation is ready to serve (configuration, database, folders, front end). Exit status 1 = something is wrong."""
        import shutil

        from sqlalchemy import func, select

        from app import migrate
        from app.config import cfg
        from app.db import database, session_scope
        from app.models import Post
        from app.services import auth

        c = cfg()
        problems: list[str] = []

        def line(ok: bool, text: str, detail: str = "") -> None:
            click.echo(f"  {'ok  ' if ok else 'FAIL'} {text}" + (f"  ({detail})" if detail else ""))
            if not ok:
                problems.append(text)

        click.echo(f"environment {c.env}, data in {c.data_dir}")
        line(c.production or c.testing or True, "configuration loaded", f"site url {c.site_url or '(request host)'}, secure cookies {c.cookie_secure}, proxies {c.trust_proxy}")
        if c.production:
            line(c.cookie_secure, "secure cookies are on (production is served over https)")
            line(c.trust_proxy >= 1, "BLOG_TRUST_PROXY is set (behind a reverse proxy the client address and scheme come from it)")
        current, head = migrate.current_revision(database()), migrate.head_revision()
        line(current == head, "database is at the latest revision", f"{current} / {head}")
        for name, folder in (("data folder", c.data_dir), ("media folder", c.media_dir), ("backup folder", c.backup_dir)):
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".doctor-probe"
            try:
                probe.write_text("x")
                probe.unlink()
                line(True, f"{name} is writable")
            except OSError as exc:
                line(False, f"{name} is writable", str(exc))
        free = shutil.disk_usage(c.data_dir).free
        line(free > 300 * 1024 * 1024, "at least 300 MB of disk is free", f"{free // (1024 * 1024)} MB free")
        dist = c.frontend_dist
        for name in ("public.html", "admin.html", "preview.html"):
            line(bool(dist and (dist / name).is_file()), f"front end file {name} is present")
        if current == head:
            with session_scope(write=False) as session:
                posts = int(session.scalar(select(func.count()).select_from(Post)) or 0)
                click.echo(f"  info administrator: {'yes' if auth.owner_exists(session) else 'not yet (open /admin/setup)'}; posts: {posts}")
        if problems:
            raise click.ClickException(f"{len(problems)} problem(s): " + "; ".join(problems))
        click.echo("all good")

    @app.cli.command("routes-table")
    def routes_table():
        """Print every route (method, path, handler)."""
        rows = []
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
            rows.append(f"{methods:<18} {rule.rule:<60} {rule.endpoint}")
        click.echo("\n".join(rows))


    @app.cli.command("seed-demo")
    @click.option("--owner", default=None, help="Also create the administrator with this user name (development only).")
    @click.option("--password", default=None, help="Password for --owner (prompted when omitted).")
    def seed_demo(owner: str | None, password: str | None):
        """Fill an EMPTY development site with sample posts, moments, pictures and a page."""
        from app.config import cfg
        from app.db import session_scope
        from app.devseed import seed
        from app.services import auth

        if cfg().production:
            raise click.ClickException("seed-demo is for development; refusing to run in production")
        with session_scope() as session:
            try:
                counts = seed(session, cfg())
            except RuntimeError as exc:
                raise click.ClickException(str(exc)) from exc
            if owner:
                if auth.owner_exists(session):
                    click.echo("an administrator exists already; --owner ignored")
                else:
                    pw = password or click.prompt("password for the administrator", hide_input=True, confirmation_prompt=True)
                    auth.create_owner(session, owner, pw, cfg())
                    click.echo(f"administrator {owner} created")
        click.echo(f"sample content created: {counts['posts']} posts, {counts['media']} pictures")
