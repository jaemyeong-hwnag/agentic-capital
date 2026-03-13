# 기술 스택

## 핵심 설계 원칙

> 이 프로젝트는 **롤플레잉 시뮬레이션**이다. 모든 에이전트는 최대 자율성을 가지며, 유일한 목적은 **돈을 버는 것**, 유일한 제약은 **자산/자본**이다.
> 에이전트 소통 언어/포맷은 **AI 친화적이면 자유** (영어, 바이너리, 벡터, 커스텀 프로토콜 등).
> 모든 기록은 **논문 참고 가능 수준**으로 수집한다.

---

## 요약

| 구분 | 확정 기술 | 이유 |
|------|----------|------|
| 프로그래밍 언어 | **Python 3.12+** | AI 생태계 표준, 금융 라이브러리, I/O 바운드 프로젝트 |
| AI 프레임워크 | **LangGraph v1.0** | 상태 기반 그래프 워크플로우, 금융 AI 검증됨 (JP Morgan, TradingAgents) |
| 에이전트 메모리 | **A-MEM 방식** + **Mem0** | Zettelkasten 동적 메모리 네트워크, multi-hop 추론 2x 향상 |
| 메인 DB | **PostgreSQL 16 + TimescaleDB** | 정형 + 시계열 단일 서버, 논문급 히스토리 보관 |
| 벡터 DB | **pgvector** (초기) → **Qdrant** (확장) | SQ int8 양자화, float16 저장 |
| 상태 관리 | **Redis 7+** | 감정 상태, 단기 기억, 이벤트 스트림 |
| 분석 | **DuckDB + Parquet** | 오프라인 분석, 백테스팅, 논문 데이터 추출 |
| AI 모델 | **Gemini 3.1 Pro & Flash** | Pro: 핵심 의사결정 / Flash: 반복 판단 |
| LLM 프롬프트 포맷 | **TOON + YAML + Markdown** | 토큰 40-60% 절감, 정확도 최적 |
| 에이전트 간 통신 | **MessagePack** | JSON 대비 30% 작은 페이로드, 스키마 불요 |
| 임베딩 | **Google text-embedding-004** (768D) | float16 저장, Matryoshka 256D 축소 가능 |

---

## 자료구조

### 성격 벡터 (Personality Vector)

15차원 Dense Vector, float32 저장 (크기가 작아 양자화 불필요):

| 모델 | 차원 | 파라미터 |
|------|------|---------|
| Big 5 (OCEAN) | 5D | 개방성, 성실성, 외향성, 우호성, 신경증 |
| HEXACO | 6D | Big5 + 정직-겸손성 |
| 전망 이론 | 4D | 손실회피, 위험선호, 확률가중, 참조점의존 |

- 경험에 따라 **실시간 변동** → 변동 이력 전부 DB 기록
- 각 파라미터 0~100 정규화

### 에이전트 계층 구조 (Agent Hierarchy)

- **런타임**: NetworkX 인메모리 그래프
- **영속화**: PostgreSQL 인접 리스트
- 구조는 고정이 아님 — CEO(또는 권한 보유자)가 자율적으로 변경

### 시계열 데이터 (Time-Series)

- **런타임**: pandas/polars DataFrame + Arrow RecordBatch
- **영속화**: TimescaleDB hypertable (Gorilla 압축 chunk)
- **아카이브**: Parquet (S3/로컬)

### 이벤트 큐 (Event Queue)

- **시뮬레이션**: Python `heapq` 우선순위 큐 + 타입화된 이벤트 dataclass
- **분산 메시징**: Redis Streams

### 메모리 임베딩 (Memory Embedding)

- **차원**: 768D (Google text-embedding-004), 확장 시 Matryoshka 256D 축소
- **저장 정밀도**: float16 (50% 메모리 절감, <1% 정확도 손실)
- **인덱스 양자화**: SQ int8 (검색 3.66x 가속)
- **계층적 메모리** (A-MEM + AgentOS 참고):
  - Working Memory → Redis (최근 5-10개)
  - Episodic Memory → Qdrant 벡터 (구체적 경험)
  - Semantic Memory → PostgreSQL 요약 (축적된 지식)
  - Procedural Memory → 코드/프롬프트 템플릿 (투자 전략)

---

## 데이터 포맷

### LLM 프롬프트 (에이전트 ↔ LLM)

| 용도 | 포맷 | 효과 |
|------|------|------|
| 거래 내역, 포트폴리오, 시장 데이터 | **TOON** | 토큰 40-60% 절감, 정확도 73.9% |
| 에이전트 상태, 성격, 설정 | **YAML** | 최고 LLM 이해도 (62.1%) |
| 시장 분석, 경험 요약 | **Markdown** | 토큰 34-38% 절감 |

### 에이전트 간 통신

| 경로 | 포맷 |
|------|------|
| 기본 내부 통신 | **MessagePack** (30% 작음, 스키마 불요) |
| 초저지연 필요 시 | **FlatBuffers** (81ns/op, zero-copy) |
| 외부 API | **JSON** (범용 호환) |

### DB 저장

| 용도 | 포맷 |
|------|------|
| 정형 데이터 | PostgreSQL typed columns + **JSONB** |
| 시계열 | TimescaleDB 압축 chunk (Gorilla) |
| 벡터 | float16 + SQ int8 인덱스 |
| 분석/아카이브 | **Parquet** (열 기반 압축) |
| 인메모리 파이프라인 | **Arrow IPC** (zero-copy, 10K MB/s) |

---

## 프로그래밍 언어: Python 3.12+

- AI 생태계(LangGraph, Mem0 등)의 표준 언어
- 금융 라이브러리: `pandas`, `polars`, `numpy`, `ccxt`, `yfinance`, `ta-lib`
- 프로젝트는 **I/O 바운드** (LLM API 호출 대기)이므로 Python의 CPU 약점은 부차적
- 성능 병목 발생 시 Rust 모듈(`pyo3/maturin`)로 부분 최적화 가능
- `asyncio` 기반 비동기 처리로 다수 에이전트 동시 운용

---

## AI 프레임워크: LangGraph v1.0

| 선택 이유 | 설명 |
|----------|------|
| 상태 기반 그래프 | 에이전트의 복잡한 의사결정 흐름을 그래프로 표현 |
| 금융 AI 검증 | JP Morgan, TradingAgents 논문에서 사용 |
| 동적 워크플로우 | 에이전트가 자율적으로 실행 경로 변경 가능 |
| 체크포인트 | 에이전트 상태 스냅샷/복원으로 논문급 재현성 |

---

## 데이터베이스 상세

### PostgreSQL 16 + TimescaleDB (메인 + 시계열)

단일 서버에서 정형 + 시계열 + 벡터(pgvector):

| 용도 | 저장 대상 |
|------|----------|
| 에이전트 | 프로필, 성격 벡터, 감정, 권한 |
| 이력 | 성격 변동, 권한 변동, 직급 변동 (논문급 히스토리) |
| 투자 | 거래 기록, 포지션, 성과 |
| 인사 | 채용/해고/승진 이벤트 |
| 경영 | 의사결정 기록, 조직 변경 |
| 시장 | OHLCV (hypertable, Gorilla 압축) |
| 스냅샷 | 회사 상태, 포트폴리오 (hypertable) |

### Qdrant (벡터 DB — 확장 시)

- float16 저장 + SQ int8 인덱스
- HNSW: M=16~32, efConstruction=200~400
- A-MEM 스타일 메모리 노트 저장

### Redis 7+ (상태/캐시/메시징)

| 용도 | 기능 |
|------|------|
| Working Memory | 최근 5-10개 기억 (TTL) |
| 감정 상태 | 스트레스, 자신감, 피로도 실시간 |
| 이벤트 스트림 | Redis Streams로 에이전트 간 메시지 |
| 시장 캐시 | 실시간 가격 데이터 |

### DuckDB + Parquet (분석)

- 오프라인 분석, 백테스팅
- **논문 데이터 추출**: 전체 히스토리를 Parquet로 내보내 분석
- Arrow 생태계 통합

---

## AI 모델 운영

| 역할 | 모델 | 용도 |
|------|------|------|
| 핵심 의사결정 | Gemini 3.1 Pro | CEO/고위 경영 판단, 복잡한 전략 |
| 일반 판단 | Gemini 3.1 Flash | 투자 판단, 시장 분석, 일상 업무 |
| 임베딩 | Google text-embedding-004 | 메모리 벡터화 (768D, float16) |

### 에이전트 소통 언어

- **AI 친화적이면 어떤 형태든 자유**
- 에이전트끼리 자율적으로 최적 소통 방식 선택 가능:
  - 자연어(영어) — LLM 기본 출력, 인간 판독 가능
  - **TOON/YAML** — 구조화된 데이터 교환 시 토큰 절감
  - **MessagePack/바이너리** — 고속 대량 데이터 전송
  - **벡터 임베딩** — 의미 기반 직접 통신 (C2C 방식)
  - **커스텀 프로토콜** — 에이전트가 자율적으로 효율적 통신 규약 개발 가능
- 기준: **정확성과 효율성**, 인간 가독성은 필수 아님
- 단, 모든 통신은 **로그로 기록** (논문 재현성)
