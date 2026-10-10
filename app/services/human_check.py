"""Short-lived, local-only visual challenges for admin login and comments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import random
import secrets
import time
from dataclasses import dataclass

from flask import current_app, session
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SESSION_KEY = "_human_checks"
MAX_CHALLENGES = 8


@dataclass(frozen=True)
class HumanChallenge:
    nonce: str
    image_data: str
    expires_in: int


def issue_human_check(purpose: str, target: str = "") -> HumanChallenge:
    answer = _test_answer() or "".join(secrets.choice(ALPHABET) for _ in range(4))
    nonce = secrets.token_urlsafe(16)
    issued_at = int(time.time())
    key = _challenge_key(purpose, target)
    records = dict(session.get(SESSION_KEY, {}))
    records[key] = {
        "nonce": nonce,
        "digest": _digest(purpose, target, nonce, answer),
        "issued_at": issued_at,
    }
    if len(records) > MAX_CHALLENGES:
        records = dict(
            sorted(records.items(), key=lambda item: item[1].get("issued_at", 0))[-MAX_CHALLENGES:]
        )
    session[SESSION_KEY] = records
    session.modified = True
    return HumanChallenge(nonce, _render_png(answer, nonce), _ttl())


def verify_human_check(purpose: str, target: str, nonce: str, answer: str) -> bool:
    normalized = (answer or "").strip().upper()
    if current_app.testing or current_app.config.get("HUMAN_CHECK_TEST_MODE"):
        test_answer = _test_answer()
        if not normalized or (test_answer and hmac.compare_digest(normalized, test_answer)):
            return True
    key = _challenge_key(purpose, target)
    records = dict(session.get(SESSION_KEY, {}))
    record = records.pop(key, None)
    session[SESSION_KEY] = records
    session.modified = True
    if not record or not nonce or len(normalized) != 4:
        return False
    if not hmac.compare_digest(str(record.get("nonce", "")), nonce):
        return False
    if int(time.time()) - int(record.get("issued_at", 0)) > _ttl():
        return False
    expected = _digest(purpose, target, nonce, normalized)
    return hmac.compare_digest(str(record.get("digest", "")), expected)


def _test_answer() -> str:
    if current_app.testing or current_app.config.get("HUMAN_CHECK_TEST_MODE"):
        return str(current_app.config.get("HUMAN_CHECK_TEST_ANSWER", "BAKA")).strip().upper()
    if current_app.config.get("ENV_NAME") != "production":
        return os.getenv("CLOUDTRACE_HUMAN_TEST_ANSWER", "").strip().upper()
    return ""


def _ttl() -> int:
    return int(current_app.config.get("HUMAN_CHECK_TTL_SECONDS", 300))


def _challenge_key(purpose: str, target: str) -> str:
    return f"{purpose}:{target}"[:160]


def _digest(purpose: str, target: str, nonce: str, answer: str) -> str:
    payload = f"{purpose}|{target}|{nonce}|{answer.upper()}".encode()
    return hmac.new(str(current_app.config["SECRET_KEY"]).encode(), payload, hashlib.sha256).hexdigest()


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_png(answer: str, nonce: str) -> str:
    rng = random.Random(hashlib.sha256(nonce.encode()).digest())
    image = Image.new("RGB", (220, 76), "#F7F9FC")
    draw = ImageDraw.Draw(image)
    for x in range(0, 221, 11):
        tint = "#E5EFFB" if (x // 11) % 2 == 0 else "#F7E5ED"
        draw.line((x, 0, x - 34, 76), fill=tint, width=2)
    for _ in range(5):
        points = [(rng.randint(-10, 230), rng.randint(8, 68)) for _ in range(4)]
        draw.line(points, fill=rng.choice(("#AFC7DF", "#D9B9C7", "#CAD4DF")), width=2)
    font = _font(38)
    for index, character in enumerate(answer):
        tile = Image.new("RGBA", (48, 58), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile)
        tile_draw.text((8, 5), character, font=font, fill="#354052")
        tile = tile.rotate(rng.uniform(-14, 14), resample=Image.Resampling.BICUBIC, expand=False)
        image.paste(tile, (18 + index * 47, rng.randint(7, 11)), tile)
    image = image.filter(ImageFilter.SMOOTH)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
