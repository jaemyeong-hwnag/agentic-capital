"""Entrypoint for Agentic Capital simulation."""

import asyncio
import sys

import structlog
from alembic import command
from alembic.config import Config

from agentic_capital.config import settings

logger = structlog.get_logger()


def run_migrations() -> None:
    """Apply pending Alembic migrations on startup."""
    try:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
        logger.info("migrations_applied")
    except Exception:
        logger.exception("migration_failed")
        raise


async def run() -> None:
    """Run the Agentic Capital simulation."""
    run_migrations()
    logger.info(
        "starting_simulation",
        initial_capital=settings.initial_capital,
        seed=settings.simulation_seed,
        log_level=settings.log_level,
    )
    # TODO: M5 — 시뮬레이션 엔진 구현
    logger.info("simulation_not_yet_implemented")


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
