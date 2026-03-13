# 기술 스택 의존성 정리

## Python 패키지

### Core

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `python` | 3.12+ | 런타임 |
| `langgraph` | ^1.0 | 에이전트 워크플로우 프레임워크 |
| `langchain-core` | ^0.3 | LangGraph 의존, 체인/프롬프트 |
| `langchain-google-genai` | latest | Gemini LLM 연동 |
| `mem0ai` | latest | 에이전트 메모리 통합 레이어 |
| `asyncio` | stdlib | 비동기 에이전트 동시 실행 |
| `pydantic` | ^2.0 | 데이터 모델, 스키마 검증 |

### Database

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `asyncpg` | latest | PostgreSQL 비동기 드라이버 |
| `sqlalchemy` | ^2.0 | ORM, 마이그레이션 |
| `alembic` | latest | DB 마이그레이션 관리 |
| `redis` | ^5.0 | Redis 비동기 클라이언트 (`redis.asyncio`) |
| `qdrant-client` | latest | Qdrant 벡터 DB 클라이언트 |
| `duckdb` | latest | 분석용 인프로세스 OLAP |
| `pgvector` | latest | PostgreSQL 벡터 확장 Python 바인딩 (pgvectorscale 호환) |

### Data & Serialization

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `pandas` | ^2.0 | 데이터프레임, 시계열 처리 |
| `polars` | latest | 고성능 데이터프레임 (대량 분석) |
| `numpy` | ^1.26 | 성격 벡터, 수치 연산 |
| `pyarrow` | latest | Arrow IPC, Parquet 읽기/쓰기 |
| `msgpack` | latest | MessagePack 직렬화 (에이전트 통신) |
| `pyyaml` | latest | YAML 파싱 (에이전트 상태) |
| `orjson` | latest | 고속 JSON 직렬화 |

### Finance

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `ccxt` | latest | 통합 암호화폐 거래소 API (Binance, Upbit 등) |
| `yfinance` | latest | Yahoo Finance 시장 데이터 |
| `alpaca-py` | latest | Alpaca 미국 주식 API |
| `python-kis` | latest | 한국투자증권 Open API (async 네이티브, 타입 힌트 완전) |
| `ta` | latest | 기술적 분석 지표 (RSI, MACD 등) |

### AI / Embedding

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `google-generativeai` | latest | Gemini API (LLM + 임베딩) |
| `tiktoken` | latest | 토큰 카운팅 |
| `networkx` | latest | 에이전트 계층 구조 인메모리 그래프 |

### Monitoring & Logging

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `structlog` | latest | 구조화된 로깅 (JSON 포맷) |
| `langsmith` | latest | LangGraph 트레이싱, 디버깅 |

### Dev / Test

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `pytest` | ^8.0 | 테스트 프레임워크 |
| `pytest-cov` | latest | 커버리지 리포트 |
| `pytest-asyncio` | latest | 비동기 테스트 |
| `ruff` | latest | 린터 + 포매터 |
| `mypy` | latest | 타입 체크 |
