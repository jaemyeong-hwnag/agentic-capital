# 기술 스택

## 요약

| 구분 | 추천 기술 | 이유 |
|------|-----------|------|
| 프로그래밍 언어 | **Python** | AI 생태계 표준, 금융 라이브러리 풍부, I/O 바운드 프로젝트에 적합 |
| AI 프레임워크 | **LangGraph** (메인) + **CrewAI** (프로토타이핑) | 상태 기반 그래프 워크플로우, 계층적 에이전트 협업 |
| 에이전트 메모리 | **Mem0** | 벡터+KV+그래프 통합 메모리 레이어, OpenAI 대비 26% 높은 정확도 |
| 메인 DB | **PostgreSQL + TimescaleDB** | 정형 데이터 + 시계열 데이터 단일 서버 운영 |
| 벡터 DB | **pgvector** (초기) → **Qdrant** (확장) | pgvector: 추가 인프라 불요 / Qdrant: Rust 기반, 24x 압축 |
| 상태 관리/캐시 | **Redis** | 실시간 상태, 단기 기억, 이벤트 스트림 |
| 분석용 DB | **DuckDB** | 오프라인 분석, 백테스팅 |
| AI 모델 (LLM) | **Gemini 3.1 Pro & Flash** | Pro: CEO/핵심 의사결정, Flash: 일반 사원/단순 작업 |

---

## 자료구조

### 성격 벡터 (Personality Vector)

15차원 Dense Vector로 표현:

| 모델 | 차원 | 파라미터 |
|------|------|---------|
| Big 5 (OCEAN) | 5D | 개방성, 성실성, 외향성, 우호성, 신경증 |
| HEXACO | 6D | Big5 + 정직-겸손성 |
| 전망 이론 | 4D | 손실회피, 위험선호, 확률가중, 참조점의존 |

- 모든 차원이 연속적 의미를 가지므로 **Dense Vector**가 적합
- 각 파라미터 0~100 정규화 저장

### 에이전트 계층 구조 (Agent Hierarchy)

- **런타임**: NetworkX 인메모리 그래프 (CEO → 임원 → 사원)
- **영속화**: PostgreSQL 인접 리스트 (adjacency list)
- 500명 미만 규모에서 Neo4j는 오버킬

### 시계열 데이터 (Time-Series)

- **런타임**: pandas DataFrame
- **영속화**: TimescaleDB hypertable (PostgreSQL 확장)
- 시장 가격, 포트폴리오 스냅샷, 수익률 추이

### 이벤트 큐 (Event Queue)

- **시뮬레이션**: Python `heapq` 우선순위 큐 + 타입화된 이벤트 dataclass
- **분산 메시징**: Redis Streams

### 메모리 임베딩 (Memory Embedding)

- **차원**: 768D (Google text-embedding-004) 또는 1536D (OpenAI)
- **계층적 메모리 시스템**:
  - 단기 기억 → Redis (TTL 기반)
  - 장기 기억 → Vector DB (pgvector / Qdrant)
  - 에피소드 기억 → PostgreSQL (구조화된 경험 로그)

---

## 프로그래밍 언어: Python

- AI 생태계(LangChain, LangGraph, CrewAI 등)의 표준 언어
- 금융 라이브러리: `pandas`, `numpy`, `ccxt`, `yfinance`, `ta-lib`
- 프로젝트는 **I/O 바운드** (LLM API 호출 대기)이므로 Python의 CPU 약점은 부차적
- 성능 병목 발생 시 Rust 모듈(`pyo3/maturin`)로 부분 최적화 가능

---

## AI 프레임워크

| 프레임워크 | 용도 | 특징 |
|-----------|------|------|
| **LangGraph** (메인) | 프로덕션 워크플로우 | 상태 기반 그래프, 금융 AI 검증 (JP Morgan, TradingAgents), v1.0 안정판 |
| **CrewAI** (보조) | 빠른 프로토타이핑 | 역할 기반 Crew 모델이 CEO+직원 구조와 자연스럽게 매핑 |
| AutoGen | 대안 | Microsoft 개발, 코드 생성 강점이나 금융 도메인 약함 |

---

## 데이터베이스 상세

### PostgreSQL + TimescaleDB (메인 + 시계열)

단일 서버에서 두 가지 역할 수행 (TimescaleDB는 PG 확장):

| 용도 | 테이블 예시 |
|------|-----------|
| 에이전트 프로필 | `agents` (성격 벡터, 직급, 입사일) |
| 조직 구조 | `org_hierarchy` (상하관계, 팀) |
| 투자 기록 | `transactions` (매수/매도, 수량, 가격) |
| 시장 데이터 | `market_ohlcv` (시계열 hypertable) |
| 포트폴리오 | `portfolio_snapshots` (시계열 hypertable) |

### 벡터 DB

**Phase 1: pgvector**
- PostgreSQL 확장으로 추가 인프라 불요
- 1000만 벡터 미만에서 충분한 성능
- HNSW 인덱스 지원

**Phase 2: Qdrant** (확장 시)
- Rust 기반 고성능
- 비대칭 양자화로 24배 압축
- Mem0의 기본 백엔드
- 필터링 성능 최고

### Redis (상태 관리/캐시)

| 용도 | 기능 |
|------|------|
| 실시간 상태 | 각 AI의 기분, 스트레스, 현재 포지션 |
| 단기 기억 | TTL 기반 최근 대화/판단 캐시 |
| 이벤트 스트림 | Redis Streams로 에이전트 간 메시지 전달 |
| 시장 캐시 | 실시간 가격 데이터 캐싱 |

### DuckDB (분석용)

- Jupyter 노트북에서 오프라인 분석
- 백테스팅 시 대량 데이터 OLAP 쿼리
- 설치 불요 (in-process DB)

---

## 에이전트 메모리: Mem0

통합 메모리 레이어로 벡터 스토어 + KV 스토어 + 그래프 DB를 하나로 관리:

- OpenAI 메모리 대비 **26% 높은 정확도**
- **91% 낮은 지연 시간**
- **90% 토큰 비용 절감**
- LangGraph / CrewAI와 통합 가능

---

## AI 모델 운영 전략

| 역할 | 모델 | 용도 |
|------|------|------|
| CEO / 핵심 의사결정 | Gemini 3.1 Pro | 복잡한 추론, 전략 평가, 인사 결정 |
| 일반 사원 / 단순 작업 | Gemini 3.1 Flash | 반복적 투자 판단, 데이터 분석 |
| 임베딩 | Google text-embedding-004 | 메모리 벡터화 (768D) |
