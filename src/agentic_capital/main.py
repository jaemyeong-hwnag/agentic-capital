"""Entrypoint for Agentic Capital simulation."""

import asyncio
import sys

import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()


async def run() -> None:
    """Run the Agentic Capital simulation."""
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


if __name__ == "__main__":
    main()
