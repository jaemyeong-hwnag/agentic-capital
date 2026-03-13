# 마일스톤

## 전체 로드맵

```
M1 프로젝트 기반    → M2 Core 엔진     → M3 에이전트 시스템  → M4 트레이딩 연동
(프로젝트 셋업)       (DB + 메모리)        (성격 + 의사결정)      (Adapter + 실행)

    → M5 시뮬레이션    → M6 Paper Trading → M7 실거래
      (멀티에이전트)      (모의투자 검증)      (라이브)
```

---

## M1: 프로젝트 기반 셋업

> 개발 환경, 프로젝트 구조, CI/CD 기반

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 1.1 | pyproject.toml 생성 (전체 의존성) | `pyproject.toml` |
| 1.2 | src 디렉토리 구조 설계 | `src/agentic_capital/` |
| 1.3 | Docker Compose 작성 (PG + Redis) | `docker-compose.yml` |
| 1.4 | .env.example 생성 | `.env.example` |
| 1.5 | Alembic 초기 설정 | `alembic/`, `alembic.ini` |
| 1.6 | pytest 설정 + 기본 테스트 | `tests/`, `conftest.py` |
| 1.7 | ruff + mypy 설정 | `pyproject.toml` lint 섹션 |
| 1.8 | GitHub Actions CI | `.github/workflows/ci.yml` |

### src 디렉토리 구조 (안)

```
src/agentic_capital/
├── __init__.py
├── main.py                    # 엔트리포인트
├── config.py                  # 환경변수, 설정
│
├── core/                      # CORE — 비즈니스 로직
│   ├── agents/                # 에이전트 정의
│   │   ├── base.py            # BaseAgent ABC
│   │   ├── ceo.py
│   │   ├── portfolio_manager.py
│   │   ├── analyst.py
│   │   ├── trader.py
│   │   └── factory.py         # 에이전트 생성 팩토리
│   │
│   ├── personality/           # 성격 시스템
│   │   ├── models.py          # 15D 성격 벡터, VAD 감정
│   │   ├── drift.py           # 성격 변동 로직
│   │   └── emotion.py         # 감정 시스템
│   │
│   ├── memory/                # 메모리 시스템
│   │   ├── working.py         # Redis Working Memory
│   │   ├── episodic.py        # Qdrant Episodic Memory
│   │   ├── semantic.py        # PG Semantic Memory
│   │   └── amem.py            # A-MEM Zettelkasten 노트
│   │
│   ├── organization/          # 조직 시스템
│   │   ├── roles.py           # 동적 직급
│   │   ├── permissions.py     # 권한 위임/회수
│   │   └── hr.py              # 인사 (채용/해고/승진)
│   │
│   ├── decision/              # 의사결정
│   │   ├── pipeline.py        # 데이터 수집 → 판단 → 실행
│   │   ├── prompts.py         # LLM 프롬프트 템플릿
│   │   └── reflection.py      # Reflection, 성격 변동 트리거
│   │
│   └── communication/         # 에이전트 통신
│       ├── protocol.py        # LACP 메시지 타입
│       ├── serializer.py      # MessagePack 직렬화
│       └── bus.py             # 메시지 버스 (Redis Stream)
│
├── ports/                     # PORT — 인터페이스 (ABC)
│   ├── trading.py             # TradingPort ABC (매수/매도/잔고)
│   ├── market_data.py         # MarketDataPort ABC (시세/OHLCV)
│   └── llm.py                 # LLMPort ABC (추론/임베딩)
│
├── adapters/                  # ADAPTER — 교체 가능 구현체
│   ├── trading/
│   │   ├── kis.py             # 한국투자증권 (python-kis)
│   │   ├── binance.py         # Binance (ccxt)
│   │   ├── upbit.py           # Upbit (ccxt)
│   │   ├── alpaca.py          # Alpaca (alpaca-py)
│   │   └── paper.py           # Paper Trading (시뮬레이션)
│   │
│   ├── market_data/
│   │   ├── yahoo.py           # Yahoo Finance (yfinance)
│   │   ├── exchange.py        # 거래소 시세 (ccxt)
│   │   └── kis_market.py      # KIS 시세
│   │
│   └── llm/
│       ├── gemini.py          # Google Gemini
│       └── openai.py          # OpenAI (대안)
│
├── infra/                     # 인프라 (DB, 캐시)
│   ├── database.py            # SQLAlchemy async engine
│   ├── redis.py               # Redis async client
│   ├── qdrant.py              # Qdrant client
│   └── models/                # SQLAlchemy ORM 모델
│       ├── agent.py
│       ├── trade.py
│       ├── organization.py
│       ├── memory.py
│       ├── market.py
│       └── simulation.py
│
├── graph/                     # LangGraph 워크플로우
│   ├── state.py               # 그래프 상태 정의
│   ├── nodes.py               # 노드 (분석/판단/실행)
│   ├── edges.py               # 엣지 (조건부 라우팅)
│   └── workflow.py            # 그래프 조립
│
├── simulation/                # 시뮬레이션 엔진
│   ├── engine.py              # 메인 시뮬레이션 루프
│   ├── clock.py               # 시뮬레이션 시간 관리
│   └── recorder.py            # 논문급 기록기
│
└── formats/                   # AI 친화적 데이터 포맷
    ├── toon.py                # TOON 포맷 변환
    ├── numerologic.py         # NumeroLogic 수치 표현
    └── markdown_kv.py         # Markdown-KV 변환
```

### 완료 기준

- [ ] `pip install -e ".[dev]"` 정상 설치
- [ ] `docker compose up` → PG + Redis 정상 기동
- [ ] `pytest` 실행 가능 (빈 테스트 통과)
- [ ] `ruff check` + `mypy` 통과
- [ ] Alembic `alembic upgrade head` 가능

---

## M2: Core 엔진 (DB + 메모리)

> 데이터 레이어, 메모리 시스템, 기본 인프라

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 2.1 | SQLAlchemy ORM 모델 정의 (전체 테이블) | `infra/models/*.py` |
| 2.2 | Alembic 마이그레이션 (초기 스키마) | `alembic/versions/` |
| 2.3 | TimescaleDB hypertable 설정 | 마이그레이션 스크립트 |
| 2.4 | pgvector 확장 + HNSW 인덱스 | 마이그레이션 스크립트 |
| 2.5 | Redis Working Memory 구현 | `core/memory/working.py` |
| 2.6 | Qdrant Episodic Memory 구현 | `core/memory/episodic.py` |
| 2.7 | A-MEM Zettelkasten 노트 구현 | `core/memory/amem.py` |
| 2.8 | Semantic Memory 구현 | `core/memory/semantic.py` |
| 2.9 | AI 포맷 변환기 (TOON, NumeroLogic, Markdown-KV) | `formats/*.py` |
| 2.10 | DB 통합 테스트 (실제 PG/Redis) | `tests/integration/` |

### 완료 기준

- [ ] 전체 스키마 마이그레이션 적용
- [ ] 메모리 CRUD (Working/Episodic/Semantic) 동작
- [ ] A-MEM 노트 생성 + 링크 + 검색 동작
- [ ] TOON/NumeroLogic 포맷 변환 동작
- [ ] 테스트 커버리지 80%+

---

## M3: 에이전트 시스템

> 성격, 감정, 의사결정, 조직 자율성

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 3.1 | 15D 성격 벡터 모델 (Pydantic) | `core/personality/models.py` |
| 3.2 | VAD 감정 모델 + Redis 실시간 동기화 | `core/personality/emotion.py` |
| 3.3 | 성격 변동 (Personality Drift) 로직 | `core/personality/drift.py` |
| 3.4 | BaseAgent ABC 정의 | `core/agents/base.py` |
| 3.5 | CEO Agent 구현 (인사/조직/전략 자율) | `core/agents/ceo.py` |
| 3.6 | Analyst Agent 구현 (분석 자율) | `core/agents/analyst.py` |
| 3.7 | Trader Agent 구현 (실행) | `core/agents/trader.py` |
| 3.8 | 에이전트 팩토리 (동적 생성) | `core/agents/factory.py` |
| 3.9 | 동적 직급/권한 시스템 | `core/organization/*.py` |
| 3.10 | HR 시스템 (채용/해고/승진/강등) | `core/organization/hr.py` |
| 3.11 | LLM 프롬프트 템플릿 (성격 주입) | `core/decision/prompts.py` |
| 3.12 | 의사결정 파이프라인 (데이터→판단→실행) | `core/decision/pipeline.py` |
| 3.13 | Reflection 시스템 (경험→성격변동) | `core/decision/reflection.py` |

### 완료 기준

- [ ] 에이전트 생성 → 성격 벡터 할당 → 감정 초기화
- [ ] CEO가 조직 구조를 자율 변경 (직급 생성, 권한 위임)
- [ ] 에이전트의 의사결정이 성격/감정에 영향받음
- [ ] Reflection 후 성격 변동 발생 + DB 기록
- [ ] 테스트 커버리지 80%+

---

## M4: 통신 + 트레이딩 어댑터

> LACP 통신, Port/Adapter, 거래소 연동

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 4.1 | LACP 메시지 모델 (PLAN/ACT/OBSERVE/SIGNAL) | `core/communication/protocol.py` |
| 4.2 | MessagePack 직렬화 | `core/communication/serializer.py` |
| 4.3 | Redis Stream 메시지 버스 | `core/communication/bus.py` |
| 4.4 | TradingPort ABC (매수/매도/잔고/포지션) | `ports/trading.py` |
| 4.5 | MarketDataPort ABC (시세/OHLCV/뉴스) | `ports/market_data.py` |
| 4.6 | LLMPort ABC (추론/임베딩) | `ports/llm.py` |
| 4.7 | Paper Trading Adapter (시뮬레이션) | `adapters/trading/paper.py` |
| 4.8 | Gemini LLM Adapter | `adapters/llm/gemini.py` |
| 4.9 | Yahoo Finance Adapter | `adapters/market_data/yahoo.py` |
| 4.10 | KIS Adapter (한국투자증권) | `adapters/trading/kis.py` |
| 4.11 | Binance Adapter (ccxt) | `adapters/trading/binance.py` |
| 4.12 | Alpaca Adapter | `adapters/trading/alpaca.py` |

### 완료 기준

- [ ] LACP 메시지 송수신 동작
- [ ] Paper Trading으로 가상 매매 가능
- [ ] Gemini API 연동 (프롬프트 → 응답)
- [ ] 시장 데이터 수집 (Yahoo Finance)
- [ ] Port 인터페이스로 Adapter 교체 가능 확인
- [ ] 테스트 커버리지 80%+

---

## M5: 멀티에이전트 시뮬레이션

> LangGraph 워크플로우, 시뮬레이션 엔진, 논문급 기록

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 5.1 | LangGraph 상태 정의 | `graph/state.py` |
| 5.2 | LangGraph 노드 (분석/판단/실행) | `graph/nodes.py` |
| 5.3 | LangGraph 엣지 (조건부 라우팅) | `graph/edges.py` |
| 5.4 | 워크플로우 그래프 조립 | `graph/workflow.py` |
| 5.5 | 시뮬레이션 엔진 (메인 루프) | `simulation/engine.py` |
| 5.6 | 시뮬레이션 시간 관리 (Clock) | `simulation/clock.py` |
| 5.7 | 논문급 기록기 (Recorder) | `simulation/recorder.py` |
| 5.8 | 멀티에이전트 동시 실행 (asyncio) | `simulation/engine.py` |
| 5.9 | CEO 자율 조직 운영 통합 | CEO + HR + 권한 연동 |
| 5.10 | 자연 선택 (수익 기반 생존) | `simulation/engine.py` |
| 5.11 | 회사 스냅샷 기록 | TimescaleDB hypertable |
| 5.12 | E2E 시뮬레이션 테스트 | `tests/e2e/` |

### 완료 기준

- [ ] 에이전트 3~5명으로 1일 시뮬레이션 완주
- [ ] CEO가 자율적으로 조직 운영 (채용/해고 발생)
- [ ] 에이전트 간 LACP 통신으로 시그널 교환
- [ ] 모든 의사결정/거래/조직변경 DB 기록
- [ ] 시뮬레이션 재현 가능 (동일 시드 → 동일 결과)
- [ ] 테스트 커버리지 80%+

---

## M6: Paper Trading 검증

> 모의투자로 전체 시스템 검증

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 6.1 | Alpaca Paper Trading 연동 | 미국 주식 모의투자 |
| 6.2 | KIS 모의투자 연동 | 국내 주식 모의투자 |
| 6.3 | 실시간 시장 데이터 통합 | WebSocket 시세 수신 |
| 6.4 | 에이전트 10명 스케일 테스트 | 성능/안정성 검증 |
| 6.5 | 모니터링 대시보드 (Grafana) | 수익률, 에이전트 상태 |
| 6.6 | LangSmith 트레이싱 연동 | LLM 디버깅 |
| 6.7 | 백테스팅 파이프라인 (DuckDB) | 과거 데이터 시뮬레이션 |
| 6.8 | 데이터 내보내기 (Parquet) | 논문용 데이터셋 |
| 6.9 | 1주일 연속 운영 테스트 | 안정성 검증 |

### 완료 기준

- [ ] Alpaca Paper Trading으로 미국 주식 자동 매매
- [ ] KIS 모의투자로 국내 주식 자동 매매
- [ ] 에이전트 10명 동시 운영 안정
- [ ] Grafana 대시보드에서 실시간 모니터링
- [ ] 1주일 무중단 운영

---

## M7: 실거래 (Live Trading)

> 실제 자금 투입, 운영 안정화

### 태스크

| # | 태스크 | 산출물 |
|---|--------|--------|
| 7.1 | 실거래 환경 설정 (KIS/Binance/Alpaca) | 실거래 키 설정 |
| 7.2 | 서버 배포 (EC2 + RDS + ElastiCache) | Phase 2 인프라 |
| 7.3 | 백업/복구 전략 | pg_dump + WAL 아카이빙 |
| 7.4 | 알림 시스템 (Slack/Telegram) | 이상 감지 알림 |
| 7.5 | 소규모 실거래 시작 | 제한된 자본으로 시작 |
| 7.6 | 운영 안정화 + 모니터링 | 지속적 관찰 |
| 7.7 | 에이전트 확장 (50+) | Phase 3 인프라 |

### 완료 기준

- [ ] 실거래 자동 매매 정상 작동
- [ ] 서버 배포 + 모니터링 + 알림 구축
- [ ] 백업/복구 검증 완료

---

## 마일스톤 의존성

```
M1 ──→ M2 ──→ M3 ──→ M5 ──→ M6 ──→ M7
              │              ↑
              └──→ M4 ───────┘
```

- M1 → M2: 프로젝트 구조 필요
- M2 → M3: DB/메모리 기반 필요
- M2 → M4: DB 기반 필요 (Port 정의)
- M3 + M4 → M5: 에이전트 + 통신 + 어댑터 합체
- M5 → M6: 시뮬레이션 엔진 필요
- M6 → M7: Paper Trading 검증 후 실거래

---

## 즉시 시작 가능: M1

M1은 외부 의존성 없이 바로 시작 가능:

```bash
# M1.1: pyproject.toml 생성
# M1.2: src 디렉토리 구조 생성
# M1.3: docker-compose.yml 작성
# M1.4: .env.example 생성
# M1.5: Alembic 초기화
# M1.6: pytest 설정
# M1.7: ruff + mypy 설정
```
