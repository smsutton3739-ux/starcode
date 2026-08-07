"""Portable column types.

The production target is PostgreSQL (JSONB + pgvector). The test suite runs on SQLite so
that `pytest` needs no services. These shims pick the right implementation per dialect
without the models having to care.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import JSON, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class JSONBType(TypeDecorator):
    """JSONB on Postgres, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class VectorType(TypeDecorator):
    """pgvector `vector(N)` on Postgres; JSON-encoded float list elsewhere.

    Similarity search uses the pgvector operators when available and falls back to an
    in-process cosine scan otherwise (see `app.knowledge.rag`).
    """

    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int = 384, **kwargs: Any) -> None:
        self.dimensions = dimensions
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector

                return dialect.type_descriptor(Vector(self.dimensions))
            except ImportError:  # pragma: no cover - pgvector always present in prod image
                return dialect.type_descriptor(Text())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        if isinstance(value, str):
            return json.loads(value)
        return list(value)


__all__ = ["JSONBType", "VectorType"]
