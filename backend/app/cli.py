"""CLI entry point for Phase 2 — manual ingestion and seed commands.

Usage:
    python -m app.cli ingest [--max-pages N]
    python -m app.cli seed
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


async def cmd_ingest(max_pages: int | None = None) -> None:
    """Run the full ingestion pipeline."""
    from app.db.session import async_session_factory
    from app.services.ingestion import run_ingestion

    async with async_session_factory() as session:
        # Ensure relevance_terms are seeded
        from app.services.seed import seed_relevance_terms

        await seed_relevance_terms(session)

        summary = await run_ingestion(session, max_pages=max_pages)

    print("\n=== Ingestion Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


async def cmd_seed() -> None:
    """Seed reference data (relevance_terms, etc.)."""
    from app.db.session import async_session_factory
    from app.services.seed import seed_relevance_terms

    async with async_session_factory() as session:
        count = await seed_relevance_terms(session)

    print(f"Seeded {count} relevance terms.")


def main() -> None:
    parser = argparse.ArgumentParser(description="HH Analyser CLI (Phase 2)")
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands")

    # ingest
    ingest_parser = subparsers.add_parser(
        "ingest", help="Run vacancy ingestion pipeline")
    ingest_parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max search pages to crawl (default: from config)"
    )

    # seed
    subparsers.add_parser("seed", help="Seed reference data (relevance_terms)")

    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(cmd_ingest(max_pages=args.max_pages))
    elif args.command == "seed":
        asyncio.run(cmd_seed())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
