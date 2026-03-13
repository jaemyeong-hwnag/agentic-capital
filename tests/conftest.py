"""Shared test fixtures."""

from __future__ import annotations

import uuid

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.infra.models import Base

TEST_DATABASE_URL = "postgresql+asyncpg://agent:agent_dev_password@localhost:5432/agentic_capital_test"
TEST_REDIS_URL = "redis://localhost:6379/1"


@pytest.fixture
def default_personality() -> PersonalityVector:
    """A neutral personality vector (all 0.5)."""
    return PersonalityVector()


@pytest.fixture
def aggressive_personality() -> PersonalityVector:
    """An aggressive, risk-seeking personality."""
    return PersonalityVector(
        openness=0.8,
        conscientiousness=0.3,
        extraversion=0.9,
        agreeableness=0.2,
        neuroticism=0.7,
        honesty_humility=0.4,
        loss_aversion=0.2,
        risk_aversion_gains=0.2,
        risk_aversion_losses=0.3,
        probability_weighting=0.8,
    )


@pytest.fixture
def default_emotion() -> EmotionState:
    """A neutral emotion state."""
    return EmotionState()


# --- Integration test fixtures ---


@pytest.fixture
def simulation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def agent_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def db_session():
    """Provide a database session with savepoint-based rollback after each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)

    yield session

    # Rollback everything — no data persists between tests
    await session.close()
    await trans.rollback()
    await conn.close()
    await engine.dispose()


@pytest.fixture
async def redis_client():
    """Provide a Redis client using DB 1 (test), cleaned after each test."""
    client = aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()
