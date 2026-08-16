"""Visitor privacy, rate limiting, spam checks and moderation notifications."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from flask import current_app

from app.extensions import db
from app.models import ModerationNotification
from app.security import request_fingerprint


class InteractionError(ValueError):
    """A visitor interaction is invalid or temporarily rate limited."""


def visitor_hash() -> str:
    return request_fingerprint("interaction", include_user_agent=True)


def normalize_plain_text(value: str) -> str:
    cleaned = "".join(
        character for character in value if character in "\n\t" or ord(character) >= 32
    )
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def spam_status(content: str, honeypot: str = "") -> str:
    lowered = content.casefold()
    keywords = current_app.config.get("SPAM_KEYWORDS", ())
    if honeypot or any(keyword.casefold() in lowered for keyword in keywords):
        return "spam"
    if len(re.findall(r"https?://", lowered)) > 2:
        return "spam"
    if re.search(r"(.)\1{12,}", lowered):
        return "spam"
    return "approved" if current_app.config.get("COMMENT_AUTO_APPROVE") else "pending"


def enforce_rate_limit(model, identity_hash: str) -> None:  # type: ignore[no-untyped-def]
    window = datetime.now(UTC) - timedelta(
        seconds=current_app.config["INTERACTION_RATE_WINDOW_SECONDS"]
    )
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(model)
        .where(model.ip_hash == identity_hash, model.created_at >= window)
    )
    if (count or 0) >= current_app.config["INTERACTION_RATE_LIMIT"]:
        raise InteractionError("提交得有些快，请稍后再试。")


def create_notification(target_type: str, target_id: int, message: str) -> None:
    db.session.add(
        ModerationNotification(
            notification_type="moderation",
            target_type=target_type,
            target_id=target_id,
            message=message[:255],
        )
    )
