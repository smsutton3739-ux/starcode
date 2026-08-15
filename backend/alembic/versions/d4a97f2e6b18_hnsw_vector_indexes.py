"""Replace the IVFFlat vector indexes with HNSW

The IVFFlat indexes were created by the initial migration, which runs against empty
tables. IVFFlat partitions the vectors into `lists` clusters at build time and, by
default, a query probes exactly one of them — so an index built on no rows, declared with
`lists = 100`, and then filled with 96 chunks put roughly one row in each cluster and
returned one or two results for a query that should have returned twenty.

Nothing failed. `ORDER BY embedding <=> :q LIMIT 20` returned two rows instead of twenty,
the API returned a short list, and semantic search looked like it worked while quietly
missing almost everything. On SQLite — where the whole test suite runs — retrieval takes
an in-process cosine scan instead, so no test ever touched this path.

HNSW has no build-time clustering: it can be created on an empty table, it maintains
itself as rows are inserted, and it needs no `lists`/`probes` tuning as the corpus grows.
That removes the failure mode rather than re-tuning it — a `lists` value correct for a
100-row corpus is wrong by the time the corpus is 100,000.

Index names are unchanged, so alembic's exclusion list in env.py still covers them.

Requires pgvector 0.5.0 or newer for HNSW. Supabase, Render and the pgvector Docker image
all ship well past that; if an older server is in play the create will fail loudly here
rather than silently degrade at query time, which is the right way round.

Revision ID: d4a97f2e6b18
Revises: c7e83b1d4a52
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d4a97f2e6b18"
down_revision: str | None = "c7e83b1d4a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_analysis_embeddings_embedding")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analysis_embeddings_embedding "
        "ON analysis_embeddings USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_analysis_embeddings_embedding")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding "
        "ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analysis_embeddings_embedding "
        "ON analysis_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 50)"
    )
