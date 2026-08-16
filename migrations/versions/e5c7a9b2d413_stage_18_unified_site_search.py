"""Add a unified FTS5 index for public site search."""

from alembic import op
from sqlalchemy.exc import OperationalError

revision = "e5c7a9b2d413"
down_revision = "a12e8f4c6b90"
branch_labels = None
depends_on = None

SOURCES = {
    "post": {
        "table": "posts",
        "title": "new.title",
        "body": "coalesce(new.summary, '') || ' ' || coalesce(new.content_markdown, '')",
        "meta": "''",
    },
    "project": {
        "table": "projects",
        "title": "new.title",
        "body": "coalesce(new.summary, '') || ' ' || coalesce(new.content_markdown, '')",
        "meta": "coalesce(new.tech_stack, '')",
    },
    "moment": {
        "table": "moments",
        "title": "'动态 ' || coalesce(new.mood, '')",
        "body": "coalesce(new.content_markdown, '')",
        "meta": "coalesce(new.location, '')",
    },
    "friend": {
        "table": "friend_links",
        "title": "new.name",
        "body": "coalesce(new.description, '')",
        "meta": "coalesce(new.url, '')",
    },
    "guestbook": {
        "table": "guestbook_messages",
        "title": "'留言 ' || coalesce(new.author_name, '')",
        "body": "coalesce(new.content, '') || ' ' || coalesce(new.admin_reply, '')",
        "meta": "''",
    },
}


def upgrade() -> None:
    connection = op.get_bind()
    try:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE site_search_fts USING fts5("
            "source UNINDEXED, entity_id UNINDEXED, title, body, meta, tokenize='trigram')"
        )
        for source, config in SOURCES.items():
            table = config["table"]
            insert_sql = (
                "INSERT INTO site_search_fts(source,entity_id,title,body,meta) "
                f"VALUES('{source}',new.id,{config['title']},{config['body']},{config['meta']})"
            )
            connection.exec_driver_sql(
                f"CREATE TRIGGER site_search_{source}_ai AFTER INSERT ON {table} "
                f"BEGIN {insert_sql}; END"
            )
            connection.exec_driver_sql(
                f"CREATE TRIGGER site_search_{source}_ad AFTER DELETE ON {table} "
                "BEGIN DELETE FROM site_search_fts "
                f"WHERE source='{source}' AND entity_id=old.id; END"
            )
            connection.exec_driver_sql(
                f"CREATE TRIGGER site_search_{source}_au AFTER UPDATE ON {table} "
                "BEGIN DELETE FROM site_search_fts "
                f"WHERE source='{source}' AND entity_id=old.id; {insert_sql}; END"
            )
            connection.exec_driver_sql(
                "INSERT INTO site_search_fts(source,entity_id,title,body,meta) "
                f"SELECT '{source}',id,"
                f"{config['title'].replace('new.', '')},"
                f"{config['body'].replace('new.', '')},"
                f"{config['meta'].replace('new.', '')} FROM {table}"
            )
    except OperationalError:
        _drop_search_index(connection)


def downgrade() -> None:
    _drop_search_index(op.get_bind())


def _drop_search_index(connection) -> None:  # type: ignore[no-untyped-def]
    for source in SOURCES:
        connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS site_search_{source}_au")
        connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS site_search_{source}_ad")
        connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS site_search_{source}_ai")
    connection.exec_driver_sql("DROP TABLE IF EXISTS site_search_fts")
