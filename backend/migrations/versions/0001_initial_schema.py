"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-22 21:08:21.819192
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admin_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64, collation='NOCASE'), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('totp_secret', sa.String(length=64), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), nullable=False),
    sa.Column('totp_last_step', sa.Integer(), nullable=True),
    sa.Column('recovery_hashes', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('password_changed_at', sa.DateTime(), nullable=True),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_users')),
    sa.UniqueConstraint('username', name=op.f('uq_admin_users_username'))
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('actor_name', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=48), nullable=False),
    sa.Column('target_type', sa.String(length=24), nullable=False),
    sa.Column('target_id', sa.String(length=40), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('ip_prefix', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_audit_logs_action', ['action'], unique=False)
        batch_op.create_index('ix_audit_logs_at', ['at'], unique=False)

    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('sticker', sa.String(length=32), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('show_on_shelf', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('slug', name=op.f('uq_categories_slug'))
    )
    op.create_table('device_stats',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('device', sa.String(length=12), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_device_stats')),
    sa.UniqueConstraint('day', 'device', name='uq_device_stats_day')
    )
    with op.batch_alter_table('device_stats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_device_stats_day'), ['day'], unique=False)

    op.create_table('home_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=24), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_home_blocks'))
    )
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('ip_prefix', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=200), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_login_attempts'))
    )
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.create_index('ix_login_attempts_ip_at', ['ip_prefix', 'at'], unique=False)
        batch_op.create_index('ix_login_attempts_user_at', ['username', 'at'], unique=False)

    op.create_table('media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('bytes', sa.Integer(), nullable=False),
    sa.Column('alt', sa.String(length=300), nullable=False),
    sa.Column('caption', sa.String(length=500), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.Column('variants', sa.JSON(), nullable=False),
    sa.Column('animated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("kind IN ('image','icon')", name=op.f('ck_media_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media')),
    sa.UniqueConstraint('hash', name=op.f('uq_media_hash'))
    )
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.create_index('ix_media_deleted', ['deleted_at'], unique=False)

    op.create_table('moments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('content_md', sa.Text(), nullable=False),
    sa.Column('content_html', sa.Text(), nullable=False),
    sa.Column('mood', sa.String(length=16), nullable=True),
    sa.Column('link_card', sa.JSON(), nullable=True),
    sa.Column('pinned', sa.Boolean(), nullable=False),
    sa.Column('visibility', sa.String(length=10), nullable=False),
    sa.Column('view_count', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("visibility IN ('public','unlisted','private')", name=op.f('ck_moments_visibility')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_moments'))
    )
    with op.batch_alter_table('moments', schema=None) as batch_op:
        batch_op.create_index('ix_moments_deleted', ['deleted_at'], unique=False)
        batch_op.create_index('ix_moments_published', ['visibility', 'published_at'], unique=False)

    op.create_table('nav_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('region', sa.String(length=8), nullable=False),
    sa.Column('label', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('target', sa.String(length=300), nullable=False),
    sa.Column('sticker', sa.String(length=32), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.CheckConstraint("region IN ('top','mobile','footer')", name=op.f('ck_nav_items_region')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_nav_items'))
    )
    with op.batch_alter_table('nav_items', schema=None) as batch_op:
        batch_op.create_index('ix_nav_items_region', ['region', 'sort_order'], unique=False)

    op.create_table('page_views',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('ref_id', sa.Integer(), nullable=False),
    sa.Column('views', sa.Integer(), nullable=False),
    sa.Column('uniques', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_page_views')),
    sa.UniqueConstraint('day', 'kind', 'ref_id', name='uq_page_views_day')
    )
    with op.batch_alter_table('page_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_page_views_day'), ['day'], unique=False)

    op.create_table('redirects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=300), nullable=False),
    sa.Column('target', sa.String(length=500), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('last_hit_at', sa.DateTime(), nullable=True),
    sa.Column('auto', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('status_code IN (301,302)', name=op.f('ck_redirects_status_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_redirects')),
    sa.UniqueConstraint('source', name=op.f('uq_redirects_source'))
    )
    op.create_table('referrers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('domain', sa.String(length=120), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_referrers')),
    sa.UniqueConstraint('day', 'domain', name='uq_referrers_day')
    )
    with op.batch_alter_table('referrers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_referrers_day'), ['day'], unique=False)

    op.create_table('revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.String(length=12), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_revisions'))
    )
    with op.batch_alter_table('revisions', schema=None) as batch_op:
        batch_op.create_index('ix_revisions_entity', ['entity_type', 'entity_id', 'created_at'], unique=False)

    op.create_table('settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_settings'))
    )
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=40, collation='NOCASE'), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('color', sa.String(length=8), nullable=False),
    sa.Column('sticker', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("color IN ('sky','rose','mist','white')", name=op.f('ck_tags_color')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tags')),
    sa.UniqueConstraint('name', name=op.f('uq_tags_name')),
    sa.UniqueConstraint('slug', name=op.f('uq_tags_slug'))
    )
    op.create_table('visitors',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('hash', sa.String(length=32), nullable=False),
    sa.Column('page_key', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('day', 'hash', 'page_key', name=op.f('pk_visitors'))
    )
    op.create_table('admin_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('device', sa.String(length=160), nullable=False),
    sa.Column('ip_prefix', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['admin_users.id'], name=op.f('fk_admin_sessions_user_id_admin_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_admin_sessions_token_hash'))
    )
    with op.batch_alter_table('admin_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('media_refs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.String(length=16), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], name=op.f('fk_media_refs_media_id_media'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_refs')),
    sa.UniqueConstraint('media_id', 'entity_type', 'entity_id', name='uq_media_refs_entity')
    )
    with op.batch_alter_table('media_refs', schema=None) as batch_op:
        batch_op.create_index('ix_media_refs_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_refs_media_id'), ['media_id'], unique=False)

    op.create_table('moment_media',
    sa.Column('moment_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('alt', sa.String(length=300), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], name=op.f('fk_moment_media_media_id_media'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['moment_id'], ['moments.id'], name=op.f('fk_moment_media_moment_id_moments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('moment_id', 'position', name=op.f('pk_moment_media'))
    )
    with op.batch_alter_table('moment_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_moment_media_media_id'), ['media_id'], unique=False)

    op.create_table('moment_tags',
    sa.Column('moment_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['moment_id'], ['moments.id'], name=op.f('fk_moment_tags_moment_id_moments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], name=op.f('fk_moment_tags_tag_id_tags'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('moment_id', 'tag_id', name=op.f('pk_moment_tags'))
    )
    with op.batch_alter_table('moment_tags', schema=None) as batch_op:
        batch_op.create_index('ix_moment_tags_tag', ['tag_id'], unique=False)

    op.create_table('pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('content_md', sa.Text(), nullable=False),
    sa.Column('content_html', sa.Text(), nullable=False),
    sa.Column('toc', sa.JSON(), nullable=False),
    sa.Column('template', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('seo_title', sa.String(length=200), nullable=False),
    sa.Column('seo_description', sa.String(length=400), nullable=False),
    sa.Column('seo_image_media_id', sa.Integer(), nullable=True),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("status IN ('draft','published','unlisted','private')", name=op.f('ck_pages_status')),
    sa.CheckConstraint("template IN ('plain','wide','sidebar')", name=op.f('ck_pages_template')),
    sa.ForeignKeyConstraint(['seo_image_media_id'], ['media.id'], name=op.f('fk_pages_seo_image_media_id_media'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pages')),
    sa.UniqueConstraint('slug', name=op.f('uq_pages_slug'))
    )
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.create_index('ix_pages_deleted', ['deleted_at'], unique=False)

    op.create_table('series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('cover_media_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('ongoing','finished')", name=op.f('ck_series_status')),
    sa.ForeignKeyConstraint(['cover_media_id'], ['media.id'], name=op.f('fk_series_cover_media_id_media'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_series')),
    sa.UniqueConstraint('slug', name=op.f('uq_series_slug'))
    )
    op.create_table('posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('summary_auto', sa.Boolean(), nullable=False),
    sa.Column('content_md', sa.Text(), nullable=False),
    sa.Column('content_html', sa.Text(), nullable=False),
    sa.Column('toc', sa.JSON(), nullable=False),
    sa.Column('reading_minutes', sa.Integer(), nullable=False),
    sa.Column('word_count', sa.Integer(), nullable=False),
    sa.Column('cover_media_id', sa.Integer(), nullable=True),
    sa.Column('cover_alt', sa.String(length=300), nullable=False),
    sa.Column('cover_focus_x', sa.Float(), nullable=False),
    sa.Column('cover_focus_y', sa.Float(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('series_id', sa.Integer(), nullable=True),
    sa.Column('series_order', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('pinned', sa.Boolean(), nullable=False),
    sa.Column('featured', sa.Boolean(), nullable=False),
    sa.Column('card_style', sa.String(length=8), nullable=False),
    sa.Column('show_toc', sa.Boolean(), nullable=False),
    sa.Column('show_reading_time', sa.Boolean(), nullable=False),
    sa.Column('show_author_card', sa.Boolean(), nullable=False),
    sa.Column('seo_title', sa.String(length=200), nullable=False),
    sa.Column('seo_description', sa.String(length=400), nullable=False),
    sa.Column('seo_image_media_id', sa.Integer(), nullable=True),
    sa.Column('canonical_url', sa.String(length=500), nullable=False),
    sa.Column('view_count', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("card_style IN ('auto','cover','side','note','quote')", name=op.f('ck_posts_card_style')),
    sa.CheckConstraint("status IN ('draft','published','unlisted','private')", name=op.f('ck_posts_status')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_posts_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cover_media_id'], ['media.id'], name=op.f('fk_posts_cover_media_id_media'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['seo_image_media_id'], ['media.id'], name=op.f('fk_posts_seo_image_media_id_media'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['series_id'], ['series.id'], name=op.f('fk_posts_series_id_series'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_posts')),
    sa.UniqueConstraint('slug', name=op.f('uq_posts_slug'))
    )
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.create_index('ix_posts_category', ['category_id'], unique=False)
        batch_op.create_index('ix_posts_deleted', ['deleted_at'], unique=False)
        batch_op.create_index('ix_posts_series', ['series_id', 'series_order'], unique=False)
        batch_op.create_index('ix_posts_status_published', ['status', 'published_at'], unique=False)

    op.create_table('post_tags',
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], name=op.f('fk_post_tags_post_id_posts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], name=op.f('fk_post_tags_tag_id_tags'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('post_id', 'tag_id', name=op.f('pk_post_tags'))
    )
    with op.batch_alter_table('post_tags', schema=None) as batch_op:
        batch_op.create_index('ix_post_tags_tag', ['tag_id'], unique=False)

    # Full-text search: one FTS5 table with the trigram tokenizer (works for Chinese; queries need >= 3 characters,
    # shorter ones fall back to LIKE in app/services/search.py). Rows are written by the application.
    op.execute(
        "CREATE VIRTUAL TABLE search_fts USING fts5("
        "kind UNINDEXED, ref_id UNINDEXED, title, summary, body, tags, tokenize='trigram')"
    )

    # The audit log only grows: no UPDATE at all, and nothing younger than a year can be deleted.
    op.execute(
        "CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs "
        "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_keep_year BEFORE DELETE ON audit_logs "
        "WHEN OLD.at > datetime('now', '-365 days') "
        "BEGIN SELECT RAISE(ABORT, 'audit_logs entries younger than a year cannot be deleted'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_keep_year")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update")
    op.execute("DROP TABLE IF EXISTS search_fts")
    with op.batch_alter_table('post_tags', schema=None) as batch_op:
        batch_op.drop_index('ix_post_tags_tag')

    op.drop_table('post_tags')
    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_index('ix_posts_status_published')
        batch_op.drop_index('ix_posts_series')
        batch_op.drop_index('ix_posts_deleted')
        batch_op.drop_index('ix_posts_category')

    op.drop_table('posts')
    op.drop_table('series')
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.drop_index('ix_pages_deleted')

    op.drop_table('pages')
    with op.batch_alter_table('moment_tags', schema=None) as batch_op:
        batch_op.drop_index('ix_moment_tags_tag')

    op.drop_table('moment_tags')
    with op.batch_alter_table('moment_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_moment_media_media_id'))

    op.drop_table('moment_media')
    with op.batch_alter_table('media_refs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_refs_media_id'))
        batch_op.drop_index('ix_media_refs_entity')

    op.drop_table('media_refs')
    with op.batch_alter_table('admin_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_sessions_user_id'))

    op.drop_table('admin_sessions')
    op.drop_table('visitors')
    op.drop_table('tags')
    op.drop_table('settings')
    with op.batch_alter_table('revisions', schema=None) as batch_op:
        batch_op.drop_index('ix_revisions_entity')

    op.drop_table('revisions')
    with op.batch_alter_table('referrers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_referrers_day'))

    op.drop_table('referrers')
    op.drop_table('redirects')
    with op.batch_alter_table('page_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_views_day'))

    op.drop_table('page_views')
    with op.batch_alter_table('nav_items', schema=None) as batch_op:
        batch_op.drop_index('ix_nav_items_region')

    op.drop_table('nav_items')
    with op.batch_alter_table('moments', schema=None) as batch_op:
        batch_op.drop_index('ix_moments_published')
        batch_op.drop_index('ix_moments_deleted')

    op.drop_table('moments')
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_index('ix_media_deleted')

    op.drop_table('media')
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.drop_index('ix_login_attempts_user_at')
        batch_op.drop_index('ix_login_attempts_ip_at')

    op.drop_table('login_attempts')
    op.drop_table('home_blocks')
    with op.batch_alter_table('device_stats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_device_stats_day'))

    op.drop_table('device_stats')
    op.drop_table('categories')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_logs_at')
        batch_op.drop_index('ix_audit_logs_action')

    op.drop_table('audit_logs')
    op.drop_table('admin_users')
