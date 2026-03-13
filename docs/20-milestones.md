# 마일스톤

## 배포/실행 원칙

> **사용자 설정은 `.env` + 자산/자본만.** 나머지(전략, 종목, 조직, 인사, 리서치)는 전부 AI 자율 운영.

```
실행 흐름:
1. .env 설정 (API 키, DB 접속)
2. initial_capital 설정
3. `agentic-capital` 실행
4. AI가 자율적으로 조직 구성 → 전략 수립 → 투자 시작
```

---

## 전체 로드맵

```
M1 프로젝트 기반 ✅  → M2 Core 엔진 ✅    → M3 에이전트 시스템  → M4 트레이딩 연동
(프로젝트 셋업)         (DB + 메모리)         (성격 + 의사결정)      (Adapter + 실행)

    → M5 시뮬레이션    → M6 Paper Trading → M7 실거래
      (멀티에이전트)      (모의투자 검증)      (라이브)
```

| 마일스톤 | 상태 | 완료율 |
|----------|------|--------|
| M1 프로젝트 기반 | ✅ 완료 | 100% |
| M2 Core 엔진 | ✅ 완료 | 100% |
| M3 에이전트 시스템 | ✅ 완료 | 100% (13/13) |
| M4 통신 + 어댑터 | ⬚ 부분 구현 | 85% (11/13, Phase1 100%) |
| M5 시뮬레이션 | ✅ 완료 | 100% (12/12) |
| M6 Paper Trading | ⬚ 부분 구현 | 11% (1/9) |
| M7 실거래 | ⬚ 미착수 | 0% |

---

## M1: 프로젝트 기반 셋업 ✅

> 개발 환경, 프로젝트 구조, CI/CD 기반

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 1.1 | pyproject.toml 생성 (전체 의존성) | `pyproject.toml` | ✅ |
| 1.2 | src 디렉토리 구조 설계 | `src/agentic_capital/` | ✅ |
| 1.3 | Docker Compose 작성 (PG + Redis) | `docker-compose.yml` | ✅ |
| 1.4 | .env.example 생성 | `.env.example` | ✅ |
| 1.5 | Alembic 초기 설정 | `alembic/`, `alembic.ini` | ✅ |
| 1.6 | pytest 설정 + 기본 테스트 | `tests/`, `conftest.py` | ✅ |
| 1.7 | ruff + mypy 설정 | `pyproject.toml` lint 섹션 | ✅ |
| 1.8 | GitHub Actions CI | `.github/workflows/ci.yml` | ✅ |

### 완료 기준

- [x] `pip install -e ".[dev]"` 정상 설치
- [x] `docker compose up` → PG + Redis 정상 기동
- [x] `pytest` 실행 가능 (빈 테스트 통과)
- [x] `ruff check` + `mypy` 통과
- [x] Alembic 초기 설정 완료

---

## M2: Core 엔진 (DB + 메모리) ✅

> 데이터 레이어, 메모리 시스템, 기본 인프라

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 2.1 | SQLAlchemy ORM 모델 정의 (16 테이블) | `infra/models/*.py` | ✅ |
| 2.2 | Alembic 마이그레이션 (초기 스키마) | `alembic/versions/` | ✅ |
| 2.3 | TimescaleDB hypertable 설정 | 마이그레이션 스크립트 | ✅ |
| 2.4 | pgvector 확장 + HNSW 인덱스 | 마이그레이션 스크립트 | ✅ |
| 2.5 | Redis Working Memory 구현 | `core/memory/working.py` | ✅ |
| 2.6 | Episodic Memory 구현 (pgvector Phase 1) | `core/memory/episodic.py` | ✅ |
| 2.7 | A-MEM Zettelkasten CRUD 구현 | `core/memory/amem.py` | ✅ |
| 2.8 | Semantic Memory 구현 | `core/memory/semantic.py` | ✅ |
| 2.9 | AI 포맷 변환기 (TOON, NumeroLogic, Markdown-KV) | `formats/*.py` | ✅ |
| 2.10 | DB 통합 테스트 (실제 PG/Redis) | `tests/integration/` | ✅ |

### 구현 현황

**전체 완료:**
- ORM 16개 테이블 + Alembic 마이그레이션 (001_initial_schema.py)
- TimescaleDB hypertable 5개 (personality_history, emotion_history, permission_history, market_ohlcv, company_snapshots)
- pgvector 확장 설치
- Redis Working Memory (observation/task/context + TTL + snapshot)
- A-MEM Zettelkasten CRUD (create/get/search/link/decay/q_value)
- Episodic Memory (experience store + cosine similarity search + reflection)
- Semantic Memory (knowledge store + search + reflection update)
- AI 포맷 변환기: TOON, NumeroLogic, Markdown-KV
- 통합 테스트 21개 (실제 PG + Redis)

### 완료 기준

- [x] 전체 스키마 마이그레이션 적용 (16 테이블 + 5 hypertable + pgvector)
- [x] 메모리 CRUD (Working/Episodic/Semantic) 동작
- [x] A-MEM 노트 생성 + 링크 + 검색 + Q-value decay 동작
- [x] TOON/NumeroLogic 포맷 변환 동작
- [x] 테스트 커버리지 93%+ (125 tests passed)

---

## M3: 에이전트 시스템

> 성격, 감정, 의사결정, 조직 자율성

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 3.1 | 10D 성격 벡터 모델 (Pydantic) | `core/personality/models.py` | ✅ |
| 3.2 | VAD 감정 모델 | `core/personality/emotion.py` | ✅ |
| 3.3 | 성격 변동 (Personality Drift) 로직 | `core/personality/drift.py` | ✅ |
| 3.4 | BaseAgent ABC 정의 | `core/agents/base.py` | ✅ |
| 3.5 | CEO Agent 구현 (인사/조직/전략 자율) | `core/agents/ceo.py` | ✅ |
| 3.6 | Analyst Agent 구현 (분석 자율) | `core/agents/analyst.py` | ✅ |
| 3.7 | Trader Agent 구현 (실행) | `core/agents/trader.py` | ✅ |
| 3.8 | 에이전트 팩토리 (동적 생성) | `core/agents/factory.py` | ✅ |
| 3.9 | 동적 직급/권한 시스템 | `core/organization/*.py` | ✅ |
| 3.10 | HR 시스템 (채용/해고/승진/강등) | `core/organization/hr.py` | ✅ |
| 3.11 | LLM 프롬프트 템플릿 (성격 주입) | `core/decision/prompts.py` | ✅ |
| 3.12 | 의사결정 파이프라인 (데이터→판단→실행) | `core/decision/pipeline.py` | ✅ |
| 3.13 | Reflection 시스템 (경험→성격변동) | `core/decision/reflection.py` | ✅ |

### 구현 현황 (v0.5.0)

**구현 완료:**
- 10D 성격 벡터 + VAD 감정 모델 + Personality Drift
- BaseAgent ABC (think/reflect 인터페이스)
- 프롬프트 템플릿: 성격/감정 YAML 주입, TOON 시세, Markdown-KV 잔고, CEO 프롬프트
- 의사결정 파이프라인: 시세→프롬프트→LLM 판단→JSON 파싱→주문 실행
- Reflection: P&L 기반 성격 변동 (손실→loss_aversion↑, 수익→openness↑)
- HR 시스템 + 직급/권한 + 에이전트 팩토리

**모든 M3 태스크 완료.**

### 완료 기준

- [x] 에이전트 생성 → 성격 벡터 할당 → 감정 초기화
- [x] CEO가 자율적으로 인사/조직/전략 결정 (LLM 기반)
- [x] 에이전트의 의사결정이 성격/감정에 영향받음
- [x] Reflection 후 성격 변동 발생
- [x] 테스트 커버리지 80%+

---

## M4: 통신 + 트레이딩 어댑터

> LACP 통신, Port/Adapter, 거래소 연동

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 4.1 | LACP 메시지 모델 (PLAN/ACT/OBSERVE/SIGNAL) | `core/communication/protocol.py` | ✅ |
| 4.2 | MessagePack 직렬화 | `core/communication/serializer.py` | ✅ |
| 4.3 | Redis Stream 메시지 버스 | `core/communication/bus.py` | ✅ |
| 4.4 | TradingPort ABC (매수/매도/잔고/포지션) | `ports/trading.py` | ✅ |
| 4.5 | MarketDataPort ABC (시세/OHLCV/뉴스) | `ports/market_data.py` | ✅ |
| 4.6 | LLMPort ABC (추론/임베딩) | `ports/llm.py` | ✅ |
| 4.7 | Paper Trading Adapter (시뮬레이션) | `adapters/trading/paper.py` | ✅ |
| 4.8 | Gemini LLM Adapter | `adapters/llm/gemini.py` | ✅ |
| 4.9 | KIS 시세 Adapter | `adapters/market_data/kis.py` | ✅ |
| 4.10 | KIS Adapter (한국투자증권) | `adapters/trading/kis.py` | ✅ |
| 4.11 | KISSession (공유 토큰 + rate limiting) | `adapters/kis_session.py` | ✅ |
| 4.12 | Binance Adapter (ccxt) | `adapters/trading/binance.py` | ⬚ Phase 2 |
| 4.13 | Alpaca Adapter | `adapters/trading/alpaca.py` | ⬚ Phase 2 |

### 구현 현황 (v0.5.0)

**구현 완료:**
- KISSession: 토큰 공유, 350ms 요청 스로틀링, rate limit 자동 재시도
- KIS Trading: 잔고 조회, 포지션 조회, 주문 전송 (모의투자/실전)
- KIS MarketData: 현재가 조회, OHLCV 일봉, 주요 종목 목록
- Gemini LLM: gemini-2.5-flash 텍스트 생성 + text-embedding-004 임베딩
- Paper Trading: 로컬 시뮬레이션용 가상 트레이딩
- LACP 통신 프로토콜 + MessagePack 직렬화

**미구현 (M4 잔여 — Phase 2):**
- **M4.12 Binance Adapter**: ccxt 기반 암호화폐 거래
- **M4.13 Alpaca Adapter**: 미국 주식 거래

### 완료 기준

- [x] LACP 메시지 모델 정의
- [x] Paper Trading으로 가상 매매 가능
- [x] Gemini API 연동 (프롬프트 → 응답)
- [x] KIS 시세 + 모의투자 주문 동작 확인
- [x] Port 인터페이스로 Adapter 교체 가능 확인
- [x] 테스트 커버리지 80%+

---

## M5: 멀티에이전트 시뮬레이션

> LangGraph 기반 에이전트 워크플로우, 논문급 기록

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 5.1 | LangGraph 상태 정의 | `graph/state.py` | ✅ |
| 5.2 | LangGraph 노드 (분석/판단/실행) | `graph/nodes.py` | ✅ |
| 5.3 | LangGraph 엣지 (조건부 라우팅) | `graph/workflow.py` | ✅ |
| 5.4 | 워크플로우 그래프 조립 | `graph/workflow.py` | ✅ |
| 5.5 | 시뮬레이션 엔진 (메인 루프) | `simulation/engine.py` | ✅ |
| 5.6 | 시뮬레이션 시간 관리 (Clock) | `simulation/clock.py` | ✅ |
| 5.7 | 논문급 기록기 (Recorder) | `simulation/recorder.py` | ✅ |
| 5.8 | 멀티에이전트 동시 실행 (asyncio) | `simulation/engine.py` | ✅ |
| 5.9 | CEO 자율 조직 운영 통합 | CEO + HR + 권한 연동 | ✅ |
| 5.10 | 데이터 조회 도구 (에이전트가 자율적으로 DB/API 조회) | `core/tools/*.py` | ✅ |
| 5.11 | 회사 스냅샷 기록 | TimescaleDB hypertable | ✅ |
| 5.12 | E2E 시뮬레이션 테스트 | `tests/e2e/` | ✅ |

### 구현 현황 (v0.6.0)

**구현 완료:**
- LangGraph 워크플로우: gather_data → think → reflect → record (역할 불문 동일 구조)
- SimulationEngine: 멀티에이전트 순차 실행, 시장 시간 정보 제공 (차단 없음)
- Clock: KRX 시간 정보 제공 (AI 참고용, 시스템 제한 없음)
- Recorder: **모든** 페르소나의 모든 행위/상태/결과 기록 (예외 없음)
  - 거래 결정, HR 이벤트, 전략/조직 결정, LACP 메시지, 포지션 스냅샷
  - 역할 생성/삭제, 권한 변경, 에이전트 상태 변경
  - 회사 스냅샷 (cumulative_pnl_pct, sharpe_30d, max_drawdown_pct 포함)
- 에이전트별 DecisionPipeline + Reflection + 메모리 저장

**모든 M5 태스크 완료.**

### 완료 기준

- [x] 에이전트 3명으로 시뮬레이션 사이클 완주
- [x] LangGraph 워크플로우로 에이전트 실행
- [x] CEO가 자율적으로 조직 운영 (채용/해고 발생)
- [x] 에이전트 간 LACP 통신으로 시그널 교환
- [x] 모든 의사결정/거래/조직변경 DB 기록
- [x] 시뮬레이션 재현 가능 (동일 시드 → 동일 결과)
- [x] 테스트 커버리지 80%+

---

## M6: Paper Trading 검증

> 모의투자로 전체 시스템 검증

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 6.1 | Alpaca Paper Trading 연동 | 미국 주식 모의투자 | ⬚ Phase 2 |
| 6.2 | KIS 모의투자 연동 | 국내 주식 모의투자 | ✅ |
| 6.3 | 실시간 시장 데이터 통합 | WebSocket 시세 수신 | ⬚ |
| 6.4 | 에이전트 10명 스케일 테스트 | 성능/안정성 검증 | ⬚ |
| 6.5 | 모니터링 대시보드 (Grafana) | 수익률, 에이전트 상태 | ⬚ |
| 6.6 | LangSmith 트레이싱 연동 | LLM 디버깅 | ⬚ |
| 6.7 | 백테스팅 파이프라인 (DuckDB) | 과거 데이터 시뮬레이션 | ⬚ |
| 6.8 | 데이터 내보내기 (Parquet) | 논문용 데이터셋 | ⬚ |
| 6.9 | 1주일 연속 운영 테스트 | 안정성 검증 | ⬚ |

### 구현 현황 (v0.5.0)

**구현 완료:**
- KIS 모의투자 E2E 동작 확인 (토큰 → 시세 → LLM 판단 → 주문 전송)

### 완료 기준

- [ ] Alpaca Paper Trading으로 미국 주식 자동 매매
- [x] KIS 모의투자로 국내 주식 자동 매매
- [ ] 에이전트 10명 동시 운영 안정
- [ ] Grafana 대시보드에서 실시간 모니터링
- [ ] 1주일 무중단 운영

---

## M7: 실거래 (Live Trading)

> 실제 자금 투입, 운영 안정화

### 태스크

| # | 태스크 | 산출물 | 상태 |
|---|--------|--------|------|
| 7.1 | 실거래 환경 설정 (KIS/Binance/Alpaca) | 실거래 키 설정 | ⬚ |
| 7.2 | 서버 배포 (EC2 + RDS + ElastiCache) | Phase 2 인프라 | ⬚ |
| 7.3 | 백업/복구 전략 | pg_dump + WAL 아카이빙 | ⬚ |
| 7.4 | 알림 시스템 (Slack/Telegram) | 이상 감지 알림 | ⬚ |
| 7.5 | 소규모 실거래 시작 | 제한된 자본으로 시작 | ⬚ |
| 7.6 | 운영 안정화 + 모니터링 | 지속적 관찰 | ⬚ |
| 7.7 | 에이전트 확장 (50+) | Phase 3 인프라 | ⬚ |

### 완료 기준

- [ ] 실거래 자동 매매 정상 작동
- [ ] 서버 배포 + 모니터링 + 알림 구축
- [ ] 백업/복구 검증 완료

---

## 마일스톤 의존성

```
M1 ✅ ──→ M2 ✅ ──→ M3 ✅ ──→ M5 ✅ ──→ M6 ──→ M7
                │                ↑
                └──→ M4 ✅───────┘
```

- M1 → M2: 프로젝트 구조 필요
- M2 → M3: DB/메모리 기반 필요
- M2 → M4: DB 기반 필요 (Port 정의)
- M3 + M4 → M5: 에이전트 + 통신 + 어댑터 합체
- M5 → M6: 시뮬레이션 엔진 필요
- M6 → M7: Paper Trading 검증 후 실거래

---

## 현재 진행: M6 Paper Trading

**v0.9.0 — M1~M5 완료, M6 진행 중**

### 다음 작업
1. **M6.3 실시간 시장 데이터** — WebSocket 시세 수신
2. **M6.4 에이전트 10명 스케일 테스트** — 성능/안정성 검증
3. **M6.6 LangSmith 트레이싱** — LLM 호출 디버깅/모니터링
4. **M6.7 백테스팅 파이프라인** — DuckDB 기반 과거 데이터 시뮬레이션
5. **M6.8 데이터 내보내기** — Parquet 포맷 논문용 데이터셋
