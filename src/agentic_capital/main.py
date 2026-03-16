"""Entrypoint for Agentic Capital simulation."""

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

        # Run in thread to avoid nested event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
        logger.info("migrations_applied")
    except Exception:
        logger.warning("migrations_skipped_db_may_not_be_available")


async def run() -> None:
    """Run the Agentic Capital simulation."""
    await run_migrations()

    logger.info(
        "starting_simulation",
        initial_capital=settings.initial_capital,
        seed=settings.simulation_seed,
        log_level=settings.log_level,
        kis_paper=settings.kis_is_paper,
    )

    from agentic_capital.simulation.engine import SimulationEngine

    engine = SimulationEngine()
    await engine.start()


def main() -> None:
    """CLI entrypoint."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("simulation_interrupted")
        sys.exit(0)
    except Exception:
        logger.exception("simulation_crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
