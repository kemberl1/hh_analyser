"""CLI entry point — manual ingestion, seed, snapshot rebuild, and backfill commands.

Usage:
    python -m app.cli ingest [--max-pages N]
    python -m app.cli seed
    python -m app.cli rebuild-snapshots
    python -m app.cli backfill [--days-back N]
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


async def cmd_rebuild_snapshots() -> None:
    """Rebuild all precomputed metric snapshots (Phase 4)."""
    from app.db.session import async_session_factory
    from app.services.snapshot_builder import build_snapshots

    print("Rebuilding metric snapshots...")
    async with async_session_factory() as session:
        result = await build_snapshots(session)

    print("\n=== Snapshot Rebuild Summary ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


async def cmd_backfill(days_back: int = 30) -> None:
    """Run the full backfill — segmented search to fetch ALL Frontend vacancies (Phase 8).

    Bypasses the hh.ru ~2000 results limit via date-based recursive segmentation.
    Uses existing RelevanceFilter to reject non-Frontend vacancies.
    """
    from app.db.session import async_session_factory
    from app.services.backfill import run_backfill
    from app.services.seed import seed_relevance_terms

    def _progress(current: int, total: int, stats: object) -> None:
        pct = round(current / total * 100, 1) if total else 0
        print(f"  [{pct:5.1f}%] {current}/{total} processed", flush=True)

    print(f"Starting backfill (days_back={days_back})...")
    print("Phase 1: Collecting vacancy IDs via segmented search...")

    async with async_session_factory() as session:
        await seed_relevance_terms(session)
        summary = await run_backfill(
            session,
            days_back=days_back,
            progress_callback=_progress,
        )

    print("\n=== Backfill Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HH Analyser CLI")
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

    # rebuild-snapshots (Phase 4)
    subparsers.add_parser(
        "rebuild-snapshots", help="Rebuild precomputed metric snapshots")

    # backfill (Phase 8)
    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Full backfill: fetch ALL Frontend vacancies via segmented search",
    )
    backfill_parser.add_argument(
        "--days-back", type=int, default=30,
        help="How many days back to search (default: 30)",
    )

    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(cmd_ingest(max_pages=args.max_pages))
    elif args.command == "seed":
        asyncio.run(cmd_seed())
    elif args.command == "rebuild-snapshots":
        asyncio.run(cmd_rebuild_snapshots())
    elif args.command == "backfill":
        asyncio.run(cmd_backfill(days_back=args.days_back))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
