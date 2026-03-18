"""Entrypoint for Agentic Capital simulation.

Usage:
  python -m agentic_capital.main            # multi-agent stock trading (default)
  python -m agentic_capital.main --futures  # single-agent futures scalping
  python -m agentic_capital.main --mode futures
"""

import asyncio
import sys

import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()


async def run_migrations() -> None:
    """Apply pending Alembic migrations on startup (optional — DB may not be running)."""
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


async def run_stocks() -> None:
    """Run the multi-agent stock trading simulation."""
    await run_migrations()
    logger.info(
        "starting_simulation",
        mode="stocks",
        initial_capital=settings.initial_capital,
        seed=settings.simulation_seed,
        kis_paper=settings.kis_is_paper,
    )
    from agentic_capital.simulation.engine import SimulationEngine
    engine = SimulationEngine()
    await engine.start()


async def run_futures() -> None:
    """Run the single-agent futures scalping simulation."""
    await run_migrations()
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
    """CLI entrypoint. Pass --futures or --mode futures for futures scalping."""
    mode = "stocks"
    args = sys.argv[1:]
    if "--futures" in args or "--mode" in args and args[args.index("--mode") + 1] == "futures":
        mode = "futures"

    try:
        if mode == "futures":
            asyncio.run(run_futures())
        else:
            asyncio.run(run_stocks())
    except KeyboardInterrupt:
        logger.info("simulation_interrupted")
        sys.exit(0)
    except Exception:
        logger.exception("simulation_crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
