"""Tag management."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.analysis import Analysis
from app.db.models.content import Tag
from app.db.models.user import User

MAX_TAGS_PER_ANALYSIS = 20


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.strip().lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80]


def get_or_create_tag(db: Session, user: User, name: str) -> Tag | None:
    name = name.strip()[:80]
    slug = slugify(name)
    if not slug:
        return None

    existing = db.execute(
        select(Tag).where(Tag.owner_id == user.id, Tag.slug == slug)
    ).scalar_one_or_none()
    if existing:
        return existing

    tag = Tag(owner_id=user.id, name=name, slug=slug)
    db.add(tag)
    db.flush()
    return tag


def set_tags(db: Session, analysis: Analysis, user: User, names: list[str]) -> list[Tag]:
    """Replace an analysis's tags. Tags are per-owner, so two users may both have a
    'prophecy' tag without sharing it."""
    tags: list[Tag] = []
    for name in names[:MAX_TAGS_PER_ANALYSIS]:
        tag = get_or_create_tag(db, user, name)
        if tag and tag not in tags:
            tags.append(tag)
    analysis.tags = tags
    return tags


def list_tags(db: Session, user: User) -> list[Tag]:
    return list(
        db.execute(select(Tag).where(Tag.owner_id == user.id).order_by(Tag.name)).scalars().all()
    )


__all__ = ["slugify", "get_or_create_tag", "set_tags", "list_tags", "MAX_TAGS_PER_ANALYSIS"]
