"""Alembic environment.

The database URL always comes from the application settings, never from alembic.ini, so
there is exactly one place credentials are configured and no chance of a migration run
pointing somewhere the app is not.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.models import Base

# Imported for the side effect of registering pgvector's `vector` type with SQLAlchemy.
# Without it, reflecting a PostgreSQL database warns "Did not recognize type 'vector'",
# the embedding columns come back as NullType, and every comparison involving them is
# made on incomplete information.
try:  # pragma: no cover - PostgreSQL only; SQLite deployments never install pgvector
    import pgvector.sqlalchemy  # noqa: F401
except ImportError:
    pass

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Indexes created by raw DDL in the migrations rather than declared on a model.
#:
#: SQLAlchemy's `Index()` cannot express `USING ivfflat (embedding vector_cosine_ops)
#: WITH (lists = 100)`, so these are issued as literal SQL. That leaves them present in
#: the database and absent from the model metadata, which is exactly what autogenerate
#: reports as an index to be dropped.
#:
#: The report is a false positive, and acting on it would delete the indexes that make
#: vector search fast — the check would go green by removing the thing it was meant to
#: protect. They are excluded from comparison instead, and remain owned by the migration
#: that creates them.
RAW_DDL_INDEXES = frozenset(
    {
        "ix_knowledge_chunks_embedding",
        "ix_analysis_embeddings_embedding",
    }
)


def include_object(object_, name, type_, reflected, compare_to):
    """Decide whether autogenerate should compare a database object."""
    # pgvector's own objects belong to the extension, not to this schema.
    if type_ == "table" and name in {"vector"}:
        return False
    if type_ == "index" and name in RAW_DDL_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            # Batch mode so ALTER operations work on SQLite too, which matters for
            # local development against a file database.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
