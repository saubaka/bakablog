"""Fast public search across the site's main content types."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.extensions import db

SEARCH_SOURCES = {
    "post": ("博客", "document"),
    "project": ("项目", "project"),
    "moment": ("动态", "moment"),
    "friend": ("友链", "link"),
    "guestbook": ("留言", "message"),
}
VALID_SEARCH_MODES = {"strict", "free"}
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_WORD_PATTERN = re.compile(r"[0-9A-Za-z_]+|[\u3400-\u9fff]+", re.UNICODE)
_MARKDOWN_PATTERN = re.compile(r"[#>*_`~\[\]()]")
_SPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SearchResult:
    source: str
    source_label: str
    icon: str
    title: str
    excerpt: str
    url: str
    date: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "source_label": self.source_label,
            "icon": self.icon,
            "title": self.title,
            "excerpt": self.excerpt,
            "url": self.url,
            "date": self.date,
        }


@dataclass(frozen=True)
class SearchPage:
    query: str
    mode: str
    page: int
    per_page: int
    total: int
    pages: int
    items: tuple[SearchResult, ...]
    used_fts: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "mode": self.mode,
            "page": self.page,
            "per_page": self.per_page,
            "total": self.total,
            "pages": self.pages,
            "items": [item.as_dict() for item in self.items],
            "used_fts": self.used_fts,
        }


def normalize_search_query(value: str) -> str:
    return _SPACE_PATTERN.sub(" ", value.strip())[:100]


def normalize_search_mode(value: str) -> str:
    return value if value in VALID_SEARCH_MODES else "strict"


def search_site(query: str, mode: str, page: int, per_page: int) -> SearchPage:
    normalized_query = normalize_search_query(query)
    normalized_mode = normalize_search_mode(mode)
    safe_page = max(1, page)
    safe_per_page = min(24, max(1, per_page))
    if not normalized_query:
        return SearchPage(
            query="",
            mode=normalized_mode,
            page=1,
            per_page=safe_per_page,
            total=0,
            pages=0,
            items=(),
            used_fts=False,
        )

    tokens = _free_tokens(normalized_query)
    use_fts = _can_use_fts(normalized_query, normalized_mode, tokens)
    try:
        rows, total = _execute_search(
            normalized_query,
            normalized_mode,
            tokens,
            safe_page,
            safe_per_page,
            use_fts=use_fts,
        )
    except OperationalError:
        db.session.rollback()
        rows, total = _execute_search(
            normalized_query,
            normalized_mode,
            tokens,
            safe_page,
            safe_per_page,
            use_fts=False,
        )
        use_fts = False

    pages = math.ceil(total / safe_per_page) if total else 0
    if pages and safe_page > pages:
        safe_page = pages
        rows, total = _execute_search(
            normalized_query,
            normalized_mode,
            tokens,
            safe_page,
            safe_per_page,
            use_fts=use_fts,
        )
    items = tuple(_row_to_result(row, normalized_query, tokens) for row in rows)
    return SearchPage(
        query=normalized_query,
        mode=normalized_mode,
        page=safe_page,
        per_page=safe_per_page,
        total=total,
        pages=pages,
        items=items,
        used_fts=use_fts,
    )


def _free_tokens(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in _WORD_PATTERN.findall(query.casefold()):
        if _CJK_PATTERN.search(part):
            tokens.extend(character for character in part if _CJK_PATTERN.match(character))
        else:
            tokens.append(part)
    return tuple(dict.fromkeys(token for token in tokens if token))[:12]


def _can_use_fts(query: str, mode: str, tokens: tuple[str, ...]) -> bool:
    if mode == "strict":
        return len(query) >= 3
    return bool(tokens) and all(len(token) >= 3 for token in tokens)


def _fts_query(query: str, mode: str, tokens: tuple[str, ...]) -> str:
    values = (query,) if mode == "strict" else tokens
    return " AND ".join(f'"{value.replace(chr(34), chr(34) * 2)}"' for value in values)


def _execute_search(
    query: str,
    mode: str,
    tokens: tuple[str, ...],
    page: int,
    per_page: int,
    *,
    use_fts: bool,
) -> tuple[list[object], int]:
    params: dict[str, object] = {
        "limit": per_page,
        "offset": (page - 1) * per_page,
        "needle": query.casefold(),
        "strict_pattern": f"%{query.casefold()}%",
        "now": datetime.now(UTC),
    }
    if use_fts:
        params["match_query"] = _fts_query(query, mode, tokens)
        with_clause = (
            "WITH matches AS ("
            "SELECT source, CAST(entity_id AS INTEGER) AS entity_id, "
            "bm25(site_search_fts, 0.0, 0.0, 8.0, 3.0, 1.0) AS rank "
            "FROM site_search_fts WHERE site_search_fts MATCH :match_query"
            "), results AS ("
        )
        joins = {
            source: (
                f"JOIN matches sm ON sm.source = '{source}' AND sm.entity_id = {alias}.id"
            )
            for source, alias in {
                "post": "p",
                "project": "pr",
                "moment": "m",
                "friend": "f",
                "guestbook": "g",
            }.items()
        }
        rank = "sm.rank"
        filters = _strict_filters() if mode == "strict" else {key: "1=1" for key in joins}
    else:
        with_clause = "WITH results AS ("
        joins = {key: "" for key in SEARCH_SOURCES}
        rank = "2.0"
        filters = (
            _strict_filters()
            if mode == "strict"
            else _free_filters(tokens or (query.casefold(),), params)
        )

    union_sql = _union_sql(joins, filters, rank)
    base_sql = f"{with_clause}{union_sql})"
    total = int(
        db.session.execute(text(f"{base_sql} SELECT COUNT(*) FROM results"), params).scalar_one()
    )
    rows = db.session.execute(
        text(
            f"{base_sql} SELECT source, entity_id, slug, title, body, occurred_at, rank "
            "FROM results ORDER BY rank ASC, occurred_at DESC, entity_id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        params,
    ).all()
    return rows, total


def _strict_filters() -> dict[str, str]:
    return {
        "post": (
            "(lower(p.title) LIKE :strict_pattern OR lower(p.summary) LIKE :strict_pattern "
            "OR lower(p.content_markdown) LIKE :strict_pattern)"
        ),
        "project": (
            "(lower(pr.title) LIKE :strict_pattern OR lower(pr.summary) LIKE :strict_pattern "
            "OR lower(pr.content_markdown) LIKE :strict_pattern "
            "OR lower(pr.tech_stack) LIKE :strict_pattern)"
        ),
        "moment": (
            "(lower(m.content_markdown) LIKE :strict_pattern "
            "OR lower(m.mood) LIKE :strict_pattern OR lower(m.location) LIKE :strict_pattern)"
        ),
        "friend": (
            "(lower(f.name) LIKE :strict_pattern OR lower(f.description) LIKE :strict_pattern "
            "OR lower(f.url) LIKE :strict_pattern)"
        ),
        "guestbook": (
            "(lower(g.author_name) LIKE :strict_pattern OR lower(g.content) LIKE :strict_pattern "
            "OR lower(g.admin_reply) LIKE :strict_pattern)"
        ),
    }


def _free_filters(tokens: tuple[str, ...], params: dict[str, object]) -> dict[str, str]:
    expressions = {
        "post": "lower(coalesce(p.title,'') || ' ' || coalesce(p.summary,'') || ' ' || coalesce(p.content_markdown,''))",
        "project": "lower(coalesce(pr.title,'') || ' ' || coalesce(pr.summary,'') || ' ' || coalesce(pr.content_markdown,'') || ' ' || coalesce(pr.tech_stack,''))",
        "moment": "lower(coalesce(m.content_markdown,'') || ' ' || coalesce(m.mood,'') || ' ' || coalesce(m.location,''))",
        "friend": "lower(coalesce(f.name,'') || ' ' || coalesce(f.description,'') || ' ' || coalesce(f.url,''))",
        "guestbook": "lower(coalesce(g.author_name,'') || ' ' || coalesce(g.content,'') || ' ' || coalesce(g.admin_reply,''))",
    }
    for index, token in enumerate(tokens):
        params[f"term_{index}"] = f"%{token}%"
    return {
        source: " AND ".join(
            f"{expression} LIKE :term_{index}" for index, _token in enumerate(tokens)
        )
        for source, expression in expressions.items()
    }


def _union_sql(joins: dict[str, str], filters: dict[str, str], rank: str) -> str:
    return f"""
        SELECT 'post' AS source, p.id AS entity_id, p.slug AS slug, p.title AS title,
               coalesce(nullif(p.summary, ''), p.content_markdown) AS body,
               coalesce(p.published_at, p.created_at) AS occurred_at, {rank} AS rank
        FROM posts p {joins['post']}
        WHERE p.deleted_at IS NULL AND p.published_at IS NOT NULL
          AND p.published_at <= :now
          AND p.status IN ('published', 'scheduled') AND {filters['post']}
        UNION ALL
        SELECT 'project', pr.id, pr.slug, pr.title,
               coalesce(nullif(pr.summary, ''), pr.content_markdown),
               coalesce(pr.published_at, pr.created_at), {rank}
        FROM projects pr {joins['project']}
        WHERE pr.deleted_at IS NULL AND pr.status = 'published' AND {filters['project']}
        UNION ALL
        SELECT 'moment', m.id, '', 
               CASE WHEN trim(coalesce(m.mood, '')) = '' THEN '生活动态'
                    ELSE '动态 · ' || m.mood END,
               m.content_markdown, coalesce(m.published_at, m.created_at), {rank}
        FROM moments m {joins['moment']}
        WHERE m.deleted_at IS NULL AND m.status = 'published' AND {filters['moment']}
        UNION ALL
        SELECT 'friend', f.id, '', f.name, f.description, f.updated_at, {rank}
        FROM friend_links f {joins['friend']}
        WHERE f.status = 'approved' AND {filters['friend']}
        UNION ALL
        SELECT 'guestbook', g.id, '', '来自 ' || g.author_name || ' 的留言',
               g.content || CASE WHEN trim(coalesce(g.admin_reply, '')) = ''
                                THEN '' ELSE ' ' || g.admin_reply END,
               g.created_at, {rank}
        FROM guestbook_messages g {joins['guestbook']}
        WHERE g.status = 'approved' AND {filters['guestbook']}
    """


def _row_to_result(row: object, query: str, tokens: tuple[str, ...]) -> SearchResult:
    source = str(row.source)
    label, icon = SEARCH_SOURCES[source]
    entity_id = int(row.entity_id)
    if source == "post":
        url = f"/blog/{row.slug}/"
    elif source == "project":
        url = f"/projects/{row.slug}/"
    elif source == "moment":
        url = f"/moments/{entity_id}/"
    elif source == "friend":
        url = f"/links/#friend-link-{entity_id}"
    else:
        url = f"/guestbook/#guestbook-message-{entity_id}"
    return SearchResult(
        source=source,
        source_label=label,
        icon=icon,
        title=str(row.title),
        excerpt=_excerpt(str(row.body or ""), query, tokens),
        url=url,
        date=_date_label(row.occurred_at),
    )


def _excerpt(value: str, query: str, tokens: tuple[str, ...], limit: int = 180) -> str:
    plain = _SPACE_PATTERN.sub(" ", _MARKDOWN_PATTERN.sub("", value)).strip()
    if not plain:
        return "打开这一页查看完整内容。"
    folded = plain.casefold()
    positions = [folded.find(query.casefold())]
    positions.extend(folded.find(token) for token in tokens)
    position = min((item for item in positions if item >= 0), default=0)
    start = max(0, position - 42)
    end = min(len(plain), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(plain) else ""
    return f"{prefix}{plain[start:end].strip()}{suffix}"


def _date_label(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y.%m.%d")
    text_value = str(value or "")
    return text_value[:10].replace("-", ".") if text_value else ""
