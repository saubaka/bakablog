"""Full-text search: SQLite FTS5 with the trigram tokenizer.

- Queries of three or more characters per term use the full-text index (works for Chinese: no word segmentation needed).
- A term of one or two characters cannot match in a trigram index, so such queries fall back to LIKE over title / summary / tags.
- Rows of the index are written whenever content is saved; the API still checks visibility against the real tables, so a stale
  index row can never leak a draft.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

KIND_CODE = {"post": 0, "moment": 1, "page": 2}
_OPEN, _CLOSE = "\x01", "\x02"
MAX_TERMS = 6


def _rowid(kind: str, ref_id: int) -> int:
    return ref_id * 4 + KIND_CODE[kind]


def upsert(session: Session, kind: str, ref_id: int, *, title: str, summary: str, body: str, tags: list[str]) -> None:
    rowid = _rowid(kind, ref_id)
    session.execute(text("DELETE FROM search_fts WHERE rowid = :r"), {"r": rowid})
    session.execute(
        text("INSERT INTO search_fts(rowid, kind, ref_id, title, summary, body, tags) VALUES (:r, :k, :i, :t, :s, :b, :g)"),
        {"r": rowid, "k": kind, "i": ref_id, "t": title, "s": summary, "b": body, "g": " ".join(tags)},
    )


def remove(session: Session, kind: str, ref_id: int) -> None:
    session.execute(text("DELETE FROM search_fts WHERE rowid = :r"), {"r": _rowid(kind, ref_id)})


def clear(session: Session) -> None:
    session.execute(text("DELETE FROM search_fts"))


def count(session: Session) -> int:
    return int(session.execute(text("SELECT count(*) FROM search_fts")).scalar() or 0)


def parse_terms(q: str) -> list[str]:
    terms: list[str] = []
    for raw in re.split(r"\s+", (q or "").strip()):
        term = raw.strip().strip('"')[:40]
        if term and term.lower() not in [t.lower() for t in terms]:
            terms.append(term)
    return terms[:MAX_TERMS]


@dataclass
class Hit:
    kind: str
    ref_id: int
    snippet: str  # safe HTML: text escaped, matches wrapped in <mark>


def _mark(raw: str) -> str:
    return html.escape(raw, quote=False).replace(_OPEN, "<mark>").replace(_CLOSE, "</mark>")


def _like_snippet(text_: str, terms: list[str], width: int = 60) -> str:
    low = text_.lower()
    hits = [(low.find(t.lower()), t) for t in terms if low.find(t.lower()) >= 0]
    if not hits:
        return _mark(text_[: width * 2])
    pos, _ = min(hits)
    start = max(0, pos - width // 2)
    piece = text_[start: start + width * 2]
    for _, t in hits:
        piece = re.sub(re.escape(t), lambda m: _OPEN + m.group(0) + _CLOSE, piece, flags=re.I)
    return ("…" if start else "") + _mark(piece) + ("…" if start + width * 2 < len(text_) else "")


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(session: Session, q: str, *, kinds: tuple[str, ...] = ("post", "moment", "page"), limit: int = 60) -> list[Hit]:
    terms = parse_terms(q)
    if not terms:
        return []
    kinds = tuple(k for k in kinds if k in KIND_CODE)
    if not kinds:
        return []
    kind_marks = ",".join(f":k{i}" for i in range(len(kinds)))
    params: dict = {f"k{i}": k for i, k in enumerate(kinds)}
    if all(len(t) >= 3 for t in terms):
        match = " ".join('"' + t.replace('"', '""') + '"' for t in terms)
        params.update(m=match, n=limit, a=_OPEN, b=_CLOSE)
        rows = session.execute(
            text(
                "SELECT kind, ref_id, snippet(search_fts, -1, :a, :b, '…', 40) AS snip FROM search_fts "
                f"WHERE search_fts MATCH :m AND kind IN ({kind_marks}) ORDER BY bm25(search_fts, 0, 0, 10.0, 4.0, 1.0, 3.0) LIMIT :n"
            ),
            params,
        ).all()
        return [Hit(r.kind, int(r.ref_id), _mark(r.snip)) for r in rows]
    # short terms: LIKE over title / summary / tags
    clauses = []
    for i, t in enumerate(terms):
        params[f"t{i}"] = f"%{_escape_like(t)}%"
        clauses.append(f"(title LIKE :t{i} ESCAPE '\\' OR summary LIKE :t{i} ESCAPE '\\' OR tags LIKE :t{i} ESCAPE '\\')")
    params["n"] = limit
    rows = session.execute(
        text(
            f"SELECT kind, ref_id, title, summary FROM search_fts WHERE kind IN ({kind_marks}) AND " + " AND ".join(clauses) + " LIMIT :n"
        ),
        params,
    ).all()
    return [Hit(r.kind, int(r.ref_id), _like_snippet(r.summary or r.title or "", terms)) for r in rows]


# ---- rebuild -----------------------------------------------------------------------------------------------------------------------
def rebuild(session: Session) -> dict[str, int]:
    """Drop the index and write it again from the content tables (the "rebuild search index" button)."""
    from app.models import Moment, Page, Post
    from app.services import moments as moments_service
    from app.services import pages as pages_service
    from app.services import posts as posts_service

    clear(session)
    counts = {"post": 0, "moment": 0, "page": 0}
    for post in session.scalars(select(Post).where(Post.deleted_at.is_(None))):
        posts_service.index(session, post)
        counts["post"] += 1
    for moment in session.scalars(select(Moment).where(Moment.deleted_at.is_(None))):
        moments_service.index(session, moment)
        counts["moment"] += 1
    for page in session.scalars(select(Page).where(Page.deleted_at.is_(None))):
        pages_service.index(session, page)
        counts["page"] += 1
    return counts
