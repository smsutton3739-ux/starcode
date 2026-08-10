"""Seed the reference corpus.

    python -m app.workers.seed_cli

Idempotent: existing rows are updated in place rather than duplicated, so this is safe
to run on every deploy.
"""

from __future__ import annotations

import sys

from app.core.logging import configure_logging, get_logger
from app.db.session import session_scope
from app.knowledge.seed import seed_all

logger = get_logger(__name__)


def main() -> int:
    configure_logging()
    try:
        with session_scope() as db:
            summary = seed_all(db)
    except Exception as exc:  # noqa: BLE001
        logger.exception("seed.failed", error=str(exc))
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1

    print("Reference corpus seeded:")
    for key, value in summary.items():
        print(f"  {key.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
