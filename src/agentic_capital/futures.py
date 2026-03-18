"""Standalone entrypoint for futures scalping mode.

Usage:
  agentic-capital-futures          # installed script
  python -m agentic_capital.futures
"""

import asyncio
import sys

import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()


async def _run() -> None:
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("+asyncpg", ""))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
        logger.info("migrations_applied")
    except Exception:
        logger.warning("migrations_skipped_db_may_not_be_available")

    logger.info(
        "starting_simulation",
        mode="futures_scalping",
        initial_capital=settings.initial_capital,
        kis_paper=settings.kis_is_paper,
    )
    from agentic_capital.simulation.futures_engine import FuturesEngine
    engine = FuturesEngine()
    await engine.start()


def main() -> None:
    """CLI entrypoint for futures scalping."""
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("simulation_interrupted")
        sys.exit(0)
    except Exception:
        logger.exception("simulation_crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
