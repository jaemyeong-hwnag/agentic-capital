# 상세 기술 리서치: 데이터 구조, 벡터 DB, 언어, 데이터베이스, AI 프레임워크

> 조사일: 2026-03-13 | 최신 2025-2026 벤치마크 및 권장사항 기반

---

## 1. 데이터 구조 (Data Structures)

### 1.1 성격 특성 벡터 표현 (Personality Trait Vectors)

**권장: Dense Vectors (밀집 벡터)**

| 모델 | 차원 | 구성 요소 |
|------|------|-----------|
| Big Five (OCEAN) | 5D | Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism |
| HEXACO | 6D | Honesty-Humility, Emotionality, Extraversion, Agreeableness, Conscientiousness, Openness |
| Prospect Theory | 4D | loss_aversion (λ), risk_aversion_gains (α), risk_aversion_losses (β), probability_weighting (γ) |
| **통합 성격 벡터** | **15D** | Big5(5) + HEXACO(6) + Prospect Theory(4) |

**구현 방식:**
```
personality_vector = {
    # Big Five: 각 0.0~1.0 연속값
    "openness": 0.82,
    "conscientiousness": 0.45,
    "extraversion": 0.71,
    "agreeableness": 0.33,
    "neuroticism": 0.58,

    # HEXACO: 각 0.0~1.0 연속값
    "honesty_humility": 0.67,
    "emotionality": 0.42,
    ...

    # Prospect Theory: 실수값
    "loss_aversion": 2.25,      # λ (일반적 범위: 1.5~3.0)
    "risk_aversion_gains": 0.88, # α (0~1)
    "risk_aversion_losses": 0.88, # β (0~1)
    "probability_weighting": 0.61 # γ (0~1)
}
```

**Dense Vector를 선택하는 이유:**
- 성격 특성은 연속적 스펙트럼이므로 밀집 벡터가 자연스러움
- 15차원은 매우 낮은 차원이므로 메모리/성능 부담 없음
- 코사인 유사도로 에이전트 간 성격 유사도 직접 계산 가능
- 2025년 연구(arxiv:2503.15497)에서 Big Five를 벡터로 매핑하여 AI 에이전트 의사결정에 직접 활용하는 접근법 검증됨
- Mind-over-Model (MoM) 프레임워크: 성격 특성을 trait space의 벡터로 추상화, 심리학 모델에 구애받지 않는 범용 매핑

**Sparse Vector는 불필요한 이유:**
- Sparse vector는 수천~수만 차원의 희소 데이터(예: 텍스트 BM25)에 적합
- 15D 성격 벡터는 모든 차원이 의미 있는 값을 가지므로 dense가 최적

### 1.2 에이전트 관계/계층 구조 (Graph Structures)

**권장: Python NetworkX (인메모리) + PostgreSQL (영속화)**

```
조직 구조 그래프:
    CEO
    ├── Senior Analyst (승진된 직원)
    │   ├── Analyst A
    │   └── Analyst B
    ├── Senior Analyst
    │   ├── Analyst C
    │   └── Analyst D (신규 채용)
    └── Junior Analyst E
```

**구현 선택지 비교:**

| 옵션 | 장점 | 단점 | 적합도 |
|------|------|------|--------|
| **NetworkX** | Python 네이티브, 빠른 그래프 알고리즘, 메모리 내 처리 | 영속성 없음 | 높음 (주요 선택) |
| **Neo4j** | 강력한 쿼리, GraphRAG 지원, 관계 모델링 | 별도 서버 운영 필요, 오버킬 | 중간 (향후 확장용) |
| **PostgreSQL adjacency list** | 기존 DB 활용, 단순함 | 복잡한 그래프 쿼리 불편 | 높음 (영속화용) |

**권장 조합:** 런타임에는 NetworkX로 그래프 연산 수행, PostgreSQL에 관계 데이터 영속화. 에이전트 수가 수백 명 이하이므로 Neo4j는 오버킬.

**Neo4j 고려 시점:** 에이전트 간 복잡한 관계 추적(멘토링, 경쟁, 협업 이력)이나 GraphRAG 기반 메모리 검색이 필요해지면 도입 검토. Neo4j는 2025년에 에이전트 아키텍처와의 통합(NeoConverse)을 적극 개발 중.

### 1.3 시계열 데이터 구조 (Time-Series)

**시장 데이터:**
```
market_tick = {
    "timestamp": datetime,     # 밀리초 정밀도
    "symbol": str,             # "AAPL", "BTC-USD"
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": int,
    "indicators": {            # 기술적 지표 (선택)
        "rsi_14": float,
        "macd": float,
        "bollinger_upper": float
    }
}
```

**포트폴리오 추적:**
```
portfolio_snapshot = {
    "timestamp": datetime,
    "agent_id": str,
    "total_value": float,
    "cash": float,
    "positions": [
        {"symbol": str, "quantity": int, "avg_cost": float, "current_value": float}
    ],
    "daily_pnl": float,
    "cumulative_return": float
}
```

**권장 자료구조:**
- Python `pandas.DataFrame` (런타임 분석)
- TimescaleDB hypertable (영속 저장, 시간 기반 파티셔닝 자동화)
- DuckDB (배치 분석 / 백테스팅)

### 1.4 이벤트 큐 / 시뮬레이션 이벤트 (Event Queue)

**권장: Python `heapq` 기반 Priority Queue + Redis Streams**

```python
import heapq
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(order=True)
class SimulationEvent:
    scheduled_time: datetime
    priority: int = field(compare=True)      # 0=highest
    event_type: str = field(compare=False)   # "MARKET_UPDATE", "EVALUATE", "HIRE", "FIRE"
    payload: dict = field(compare=False)

# 일일 이벤트 루프 예시
event_queue = []
heapq.heappush(event_queue, SimulationEvent(
    scheduled_time=datetime(2026, 3, 13, 9, 0),
    priority=0,
    event_type="MARKET_OPEN",
    payload={"date": "2026-03-13"}
))
heapq.heappush(event_queue, SimulationEvent(
    scheduled_time=datetime(2026, 3, 13, 16, 0),
    priority=1,
    event_type="DAILY_EVALUATION",
    payload={"evaluator": "ceo_agent"}
))
```

**이벤트 유형 및 우선순위:**

| 우선순위 | 이벤트 | 설명 |
|----------|--------|------|
| 0 (최고) | MARKET_UPDATE | 시장 데이터 갱신 |
| 1 | TRADE_EXECUTION | 매매 주문 실행 |
| 2 | DAILY_EVALUATION | CEO의 일일 성과 평가 |
| 3 | HIRE / FIRE | 인사 이벤트 |
| 4 | PERSONALITY_DRIFT | 성격 변화 (장기) |

**Redis Streams 활용:** 분산 환경이나 에이전트 간 비동기 메시지 전달에 Redis Streams 사용. 단일 프로세스 시뮬레이션에서는 `heapq`로 충분.

### 1.5 에이전트 메모리 임베딩 (Memory Embeddings)

**권장: 768D 또는 1536D dense embeddings**

| 임베딩 모델 | 차원 | 용도 | 비용 |
|-------------|------|------|------|
| OpenAI `text-embedding-3-small` | 1536D | 고품질 시맨틱 검색 | $0.02/1M tokens |
| OpenAI `text-embedding-3-large` | 3072D | 최고 품질 (필요 시) | $0.13/1M tokens |
| Sentence-Transformers `all-MiniLM-L6-v2` | 384D | 무료, 로컬 실행 가능 | 무료 |
| Google `text-embedding-004` | 768D | Gemini 생태계 호환 | $0.00625/1M chars |

**메모리 계층 구조 (Mem0 아키텍처 참고):**

```
에이전트 메모리 시스템:
├── Short-term Memory (단기 기억)
│   ├── 구현: Redis 또는 인메모리 Rolling Buffer
│   ├── 용도: 최근 시장 동향, 오늘의 거래 내역, 현재 감정 상태
│   ├── 보존 기간: 현재 세션 / 최근 N개 상호작용
│   └── 포맷: JSON 키-값 (빠른 접근)
│
├── Long-term Memory (장기 기억)
│   ├── 구현: Vector DB (Qdrant / ChromaDB)
│   ├── 용도: 과거 투자 경험, 학습된 패턴, 시장 교훈
│   ├── 보존 기간: 영구
│   ├── 포맷: 768D~1536D 벡터 임베딩
│   └── 검색: 코사인 유사도 기반 시맨틱 검색
│
├── Episodic Memory (에피소드 기억)
│   ├── 구현: PostgreSQL + 벡터 임베딩 참조
│   ├── 용도: 특정 사건의 구조화된 기록 ("2025년 3월 대폭락에서 손실 경험")
│   └── 포맷: 구조화 데이터 + 임베딩 ID 참조
│
└── Graph Memory (관계 기억) [선택적]
    ├── 구현: NetworkX 또는 Neo4j
    ├── 용도: "A 에이전트의 추천으로 B 종목 매수", "CEO가 경고한 섹터"
    └── 포맷: 엔티티-관계 트리플
```

**Mem0 적용 권장:** Mem0는 벡터 스토어 + 키-값 스토어 + 그래프 DB를 통합하는 오픈소스 메모리 레이어로, 2025년 벤치마크에서 OpenAI 메모리 시스템 대비 26% 높은 정확도, 91% 낮은 지연시간, 90% 토큰 비용 절감을 달성. Qdrant, Chroma, PGVector를 백엔드로 지원.

---

## 2. 벡터 데이터베이스 비교

### 2.1 종합 비교표

| DB | 언어 | 라이선스 | 최대 벡터 수 | 지연시간 (1M 벡터) | Python 통합 | 비용 | 이 프로젝트 적합도 |
|----|------|----------|-------------|-------------------|-------------|------|-------------------|
| **Qdrant** | Rust | Apache 2.0 | 수십억+ | ~10ms | 우수 | 무료(셀프) / 관리형 | **최고** |
| **ChromaDB** | Python/Rust | Apache 2.0 | ~10M | ~15ms | 최고 | 무료 | **높음 (프로토타입)** |
| **pgvector** | C | PostgreSQL | ~100M | ~20ms | 우수(SQLAlchemy) | 무료 | **높음 (통합 DB)** |
| **Milvus** | Go/C++ | Apache 2.0 | 수십억+ | ~5ms | 우수 | 무료(셀프) / Zilliz Cloud | 중간 (오버킬) |
| **Weaviate** | Go | BSD-3 | 수십억+ | ~10ms | 우수 | 무료(셀프) / 관리형 | 중간 |
| **Pinecone** | 관리형 | 상용 | 무제한 | ~10ms | 우수 | $70+/월 | 낮음 (비용) |
| **FAISS** | C++/Python | MIT | 수십억+ | ~1ms | 우수 | 무료 | 중간 (DB 기능 부족) |

### 2.2 이 프로젝트를 위한 분석

**에이전트 수:** 초기 10~50명, 최대 수백 명
**벡터 수 예상:** 에이전트당 수천 개 메모리 = 총 수만~수십만 벡터
**스케일:** 소규모 (100M 벡터 미만)

이 규모에서 Milvus, Weaviate, Pinecone은 **오버킬**. FAISS는 DB 기능(메타데이터 필터링, 영속성)이 부족.

### 2.3 권장: 단계별 접근

**Phase 1 (프로토타입):** ChromaDB
- 설치 없이 `pip install chromadb`로 즉시 시작
- 인메모리 또는 로컬 파일 영속화
- LangChain/LlamaIndex 네이티브 통합
- 2025년 Rust 코어 리라이트로 4배 성능 향상

**Phase 2 (프로덕션):** Qdrant
- Rust 기반 고성능, 필터링 기능 최강
- Docker로 간편 배포, 관리형 클라우드 옵션
- 2025년 비대칭 양자화로 24배 압축 달성
- Mem0의 기본 벡터 스토어 백엔드

**대안:** pgvector
- PostgreSQL 하나로 정형 데이터 + 벡터 검색 통합
- 별도 인프라 불필요, 운영 복잡도 최소화
- 10M 벡터 이하에서 충분한 성능
- 단점: 전용 벡터 DB 대비 필터링/검색 성능 열세

---

## 3. 프로그래밍 언어 비교

### 3.1 종합 비교

| 기준 | Python | Rust | Go | TypeScript |
|------|--------|------|----|------------|
| **AI 생태계** | 최고 (LangChain, CrewAI, PyTorch) | 성장 중 | 제한적 | 양호 (LangChain.js) |
| **금융 라이브러리** | 최고 (pandas, numpy, yfinance, zipline) | 제한적 | 제한적 | 제한적 |
| **비동기 성능** | 양호 (asyncio, GIL 제약) | 최고 (tokio) | 우수 (goroutines) | 우수 (event loop) |
| **CPU 성능** | 낮음 (인터프리터) | 최고 | 우수 | 낮음 |
| **개발 속도** | 빠름 | 느림 | 중간 | 빠름 |
| **멀티 에이전트 프레임워크** | 풍부 | 거의 없음 | 거의 없음 | 일부 |
| **러닝 커브** | 낮음 | 높음 | 중간 | 중간 |

### 3.2 성능 벤치마크 (2025-2026)

- **AI 게이트웨이 벤치마크 (10,000 RPS):** Rust/Go는 p95 지연시간 < 50ms 유지, Python(LiteLLM)은 조기에 초과 -- 3,400배 성능 차이
- **500 에이전트 시뮬레이션:** CPU 바운드 태스크에서 Python은 GIL로 인해 병렬 처리 제약, Rust는 I/O + CPU 모두 병렬 처리 가능
- **OpenAI의 선택:** Codex CLI를 TypeScript에서 Rust로 리라이트 (2025)
- **Anthropic/Google의 선택:** Claude Code, Gemini CLI는 TypeScript 유지

### 3.3 권장: Python (주 언어) + Rust (성능 크리티컬 모듈)

**Python을 주 언어로 선택하는 이유:**
1. AI/ML 생태계가 압도적으로 풍부 -- 모든 멀티 에이전트 프레임워크가 Python 우선
2. 금융 데이터 처리 라이브러리 최다 (pandas, numpy, yfinance, ta-lib, zipline)
3. 벡터 DB, LLM API, 임베딩 모델 모두 Python SDK 최우선 지원
4. 프로토타입에서 프로덕션까지 동일 언어로 전환 가능
5. 이 프로젝트의 병목은 LLM API 호출 (I/O 바운드)이므로 CPU 성능은 2차적

**Rust 도입 시점:**
- 시뮬레이션 엔진의 핵심 루프 (수백 에이전트 동시 실행)에서 Python 성능이 부족할 때
- `pyo3`/`maturin`으로 Python 확장 모듈로 작성
- 시장 데이터 처리, 포트폴리오 계산 등 CPU 집약 작업

**Go/TypeScript는 비추천:**
- Go: AI 생태계 부족, 멀티 에이전트 프레임워크 없음
- TypeScript: 금융 라이브러리 부족, AI 생태계가 Python 대비 크게 열세

---

## 4. 데이터베이스 조합

### 4.1 종합 비교

| DB | 유형 | 강점 | 약점 | 이 프로젝트 용도 |
|----|------|------|------|-----------------|
| **PostgreSQL** | 관계형 | 범용, 안정성, pgvector 확장 | 대규모 시계열 느림 | 에이전트 프로필, 거래 기록, 조직 구조 |
| **TimescaleDB** | 시계열 (PG 확장) | PG 호환, 시계열 최적화, SQL | ClickHouse보다 분석 느림 | 시장 데이터, 포트폴리오 스냅샷 |
| **ClickHouse** | 분석 (OLAP) | 집계 쿼리 최강, 수십억 행 | 포인트 쿼리 약함, 운영 복잡 | 백테스팅, 대규모 분석 (향후) |
| **DuckDB** | 임베디드 분석 | 설치 불필요, Python 통합 | 동시성 제한, 서버 모드 미지원 | 노트북 분석, 프로토타입 |
| **MongoDB** | 문서형 | 유연한 스키마, JSON 네이티브 | 조인 약함, 트랜잭션 제약 | 에이전트 상태 (대안) |
| **Redis** | 인메모리 캐시 | 초저지연 읽기/쓰기 | 메모리 제약, 영속성 제한 | 실시간 상태, 캐시, 이벤트 스트림 |

### 4.2 벤치마크 요약 (2025-2026)

- **TimescaleDB vs PostgreSQL:** TimescaleDB는 시계열 쿼리에서 PostgreSQL 대비 약 4배 빠름
- **ClickHouse vs TimescaleDB:** ClickHouse는 집계 분석에서 약 2배 빠름, 배치 인제스트 4M rows/sec
- **DuckDB:** 임베디드 분석에서 인프라 비용 90% 절감, 개발 속도 10배 향상

### 4.3 권장: 3-tier 데이터베이스 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    데이터베이스 아키텍처                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Tier 1: PostgreSQL + pgvector (핵심 데이터)               │
│  ├── 에이전트 프로필 (성격 벡터, 직급, 성과)                   │
│  ├── 거래 기록 (트랜잭션 로그)                               │
│  ├── 조직 구조 (adjacency list)                           │
│  └── pgvector: 에이전트 메모리 벡터 (Phase 1)               │
│                                                         │
│  Tier 2: TimescaleDB (시계열 데이터)                       │
│  ├── 시장 가격 데이터 (OHLCV)                              │
│  ├── 포트폴리오 가치 추적                                   │
│  ├── 에이전트 감정/스트레스 시계열                             │
│  └── 성과 지표 시계열                                      │
│  (참고: TimescaleDB는 PG 확장이므로 동일 서버에서 운영 가능)    │
│                                                         │
│  Tier 3: Redis (실시간 상태)                               │
│  ├── 현재 시장 데이터 캐시                                  │
│  ├── 에이전트 현재 상태 (감정, 스트레스)                       │
│  ├── 시뮬레이션 이벤트 스트림                                │
│  └── 에이전트 단기 기억 (rolling buffer)                    │
│                                                         │
│  선택: Qdrant (Phase 2 벡터 DB)                           │
│  └── pgvector에서 마이그레이션 시 장기 기억 전용              │
│                                                         │
│  선택: DuckDB (분석/백테스팅)                               │
│  └── Jupyter 노트북에서 대규모 데이터 분석                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**왜 PostgreSQL + TimescaleDB 조합인가:**
- TimescaleDB는 PostgreSQL 확장이므로 **하나의 서버에서 둘 다 운영** 가능
- SQL 인터페이스 통일, 팀의 러닝 커브 최소화
- 정형 데이터와 시계열 데이터를 JOIN으로 바로 결합
- 트레이딩 플랫폼의 일반적 패턴: TimescaleDB(실시간 틱) + ClickHouse(분석)

**왜 MongoDB는 비추천인가:**
- 에이전트 프로필과 거래 기록은 관계형 모델이 더 적합 (JOIN 빈번)
- PostgreSQL의 JSONB 컬럼으로 유연한 스키마도 충분히 지원
- 별도 운영 부담 대비 이점 부족

---

## 5. AI 멀티 에이전트 프레임워크 비교

### 5.1 종합 비교

| 프레임워크 | 설계 패러다임 | 장점 | 단점 | 이 프로젝트 적합도 |
|-----------|-------------|------|------|-------------------|
| **LangGraph** | 그래프 기반 워크플로우 | 정밀한 상태 관리, 조건 분기, 프로덕션 수준 | 러닝 커브 높음, 복잡함 | **최고** |
| **CrewAI** | 역할 기반 팀 | 직관적 역할 부여, 빠른 프로토타입 | 세밀한 제어 부족, 확장성 제약 | **높음** |
| **AutoGen** | 대화 기반 | 그룹 토론/합의, No-code Studio | 비대화형 워크플로우에 부적합 | 중간 |
| **Agency Swarm** | 에이전시 구조 | 도구 중심 설계 | 커뮤니티 작음, 문서 부족 | 낮음 |
| **OpenAI Swarm** | 경량 핸드오프 | 극도로 단순, 교육용 | 프로덕션 미지원, 기능 제한 | 낮음 |

### 5.2 프로젝트 적합성 상세 분석

**LangGraph가 최적인 이유:**

1. **상태 관리:** 각 에이전트의 성격 벡터, 감정 상태, 포트폴리오를 State로 정밀 관리
2. **조건 분기:** CEO 평가 -> 성과 기반 분기 (승진/유지/해고) 등 복잡한 로직 표현
3. **순환 그래프:** 일일 시뮬레이션 루프 (시장 데이터 -> 분석 -> 매매 -> 평가 -> 반복)를 자연스럽게 모델링
4. **프로덕션 검증:** JP Morgan이 투자 리서치 에이전트에 LangGraph 사용 (2025)
5. **금융 분야 사례 풍부:** AlphaAgents, TradingAgents 등 다수의 투자 시뮬레이션 프로젝트가 LangGraph 채택
6. **v1.0 안정화:** 2025년 말 v1.0 출시, LangChain 에이전트의 기본 런타임

**CrewAI의 보완적 가치:**
- "CEO + 직원" 역할 부여가 CrewAI의 Crew/Agent 모델과 자연스럽게 매핑
- 빠른 프로토타입으로 컨셉 검증 후 LangGraph로 전환 가능
- CrewAI도 2025년에 그래프 기반 실행 모델 채택 추세

**AutoGen 고려 시점:**
- 에이전트 간 토론/합의가 핵심이 되는 경우 (예: 투자 위원회 시뮬레이션)
- CEO와 직원 간 자연어 대화 기반 의사결정 시뮬레이션

### 5.3 권장: LangGraph (주) + CrewAI (프로토타입)

```
Phase 1: CrewAI로 빠른 컨셉 검증
├── CEO Agent + 3~5 Employee Agents
├── 간단한 역할 부여 및 투자 시뮬레이션
└── 2~4주 내 MVP 완성

Phase 2: LangGraph로 전환
├── 정밀한 상태 그래프 구축
├── 복잡한 이벤트 루프 구현
├── 에이전트 메모리 시스템 통합
└── 프로덕션 수준 안정성
```

---

## 6. 최종 권장 아키텍처

### 6.1 기술 스택 요약

| 구분 | 선택 | 대안 |
|------|------|------|
| **주 언어** | Python 3.12+ | Rust (성능 모듈) |
| **AI 프레임워크** | LangGraph (프로덕션) | CrewAI (프로토타입) |
| **LLM** | Gemini 2.5 Pro (CEO) + Flash (직원) | Claude, GPT-4o |
| **메인 DB** | PostgreSQL 16+ | - |
| **시계열 DB** | TimescaleDB (PG 확장) | DuckDB (분석) |
| **벡터 DB** | pgvector (Phase 1) -> Qdrant (Phase 2) | ChromaDB (로컬 프로토타입) |
| **캐시/상태** | Redis 7+ | - |
| **에이전트 메모리** | Mem0 (통합 메모리 레이어) | 직접 구현 |
| **그래프 처리** | NetworkX (런타임) | Neo4j (향후 확장) |
| **임베딩 모델** | Google text-embedding-004 (768D) | OpenAI text-embedding-3-small |

### 6.2 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                     시뮬레이션 엔진 (Python)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Event Queue  │  │ Sim Clock   │  │ Market Data Fetcher │  │
│  │ (heapq)     │  │ (datetime)  │  │ (yfinance/API)      │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│  ┌──────▼──────────────────────────────────────▼──────────┐  │
│  │              LangGraph Orchestrator                     │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ CEO Agent│ │ Analyst A│ │ Analyst B│ │ Analyst C│  │  │
│  │  │ (Pro LLM)│ │(Flash)   │ │(Flash)   │ │(Flash)   │  │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │  │
│  │       │  Personality Vectors (15D Dense)       │        │  │
│  │       │  + Prospect Theory Parameters          │        │  │
│  └───────┼────────────┼────────────┼─────────────┼────────┘  │
│          │            │            │             │            │
│  ┌───────▼────────────▼────────────▼─────────────▼────────┐  │
│  │                  Mem0 Memory Layer                      │  │
│  │  ┌────────────┐ ┌────────────┐ ┌───────────────────┐   │  │
│  │  │Short-term  │ │Long-term   │ │Graph Memory       │   │  │
│  │  │(Redis)     │ │(Qdrant)    │ │(NetworkX)         │   │  │
│  │  └────────────┘ └────────────┘ └───────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                     데이터 레이어                               │
│  ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ PostgreSQL       │ │ TimescaleDB  │ │ Redis           │  │
│  │ + pgvector       │ │ (PG 확장)     │ │                 │  │
│  │                  │ │              │ │                 │  │
│  │ - Agent profiles │ │ - OHLCV data │ │ - Current state │  │
│  │ - Transactions   │ │ - Portfolio  │ │ - Market cache  │  │
│  │ - Org structure  │ │   snapshots  │ │ - Event stream  │  │
│  │ - Trade history  │ │ - Metrics    │ │ - Short-term    │  │
│  │                  │ │   time-series│ │   memory        │  │
│  └──────────────────┘ └──────────────┘ └─────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 6.3 05-tech-stack.md 대비 변경/보강 사항

| 항목 | 기존 (05-tech-stack) | 변경/보강 권장 |
|------|---------------------|---------------|
| 메모리 DB | Milvus 또는 pgvector | **pgvector (Phase 1) -> Qdrant (Phase 2)** + Mem0 레이어 |
| 시계열 DB | 없음 | **TimescaleDB 추가** (PG 확장, 별도 서버 불필요) |
| AI 프레임워크 | CrewAI 또는 LangGraph | **LangGraph 주력** (금융 분야 사례 풍부, JP Morgan 채택) |
| 분석 DB | 없음 | **DuckDB 추가** (백테스팅/노트북 분석) |
| 에이전트 메모리 | 명시 없음 | **Mem0 도입** (벡터+그래프+KV 통합 메모리) |
| 성격 벡터 | 명시 없음 | **15D Dense Vector** (Big5 + HEXACO + Prospect Theory) |
| 그래프 처리 | 명시 없음 | **NetworkX** (런타임 조직 구조) |

---

## 7. 참고 자료 및 출처

### 벡터 데이터베이스
- [Best Vector Databases in 2026: A Complete Comparison Guide](https://www.firecrawl.dev/blog/best-vector-databases)
- [Vector Database Comparison 2025 - LiquidMetal AI](https://liquidmetal.ai/casesAndBlogs/vector-comparison/)
- [Vector Database Benchmarks - Qdrant](https://qdrant.tech/benchmarks/)
- [Top 9 Vector Databases as of March 2026 - Shakudo](https://www.shakudo.io/blog/top-9-vector-databases)
- [Top 5 Open Source Vector Databases for 2025](https://medium.com/@fendylike/top-5-open-source-vector-search-engines-a-comprehensive-comparison-guide-for-2025-e10110b47aa3)
- [ChromaDB vs Qdrant Comparison - Airbyte](https://airbyte.com/data-engineering-resources/chroma-db-vs-qdrant)
- [Top 6 Vector Databases 2026 - Appwrite](https://appwrite.io/blog/post/top-6-vector-databases-2025)

### AI 멀티 에이전트 프레임워크
- [LangGraph vs CrewAI vs AutoGen: Top 10 Frameworks - o-mega](https://o-mega.ai/articles/langgraph-vs-crewai-vs-autogen-top-10-agent-frameworks-2026)
- [Open Source AI Agent Frameworks Compared 2026 - OpenAgents](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared)
- [CrewAI vs LangGraph vs AutoGen - DataCamp](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen)
- [Top AI Agent Frameworks 2025 - Codecademy](https://www.codecademy.com/article/top-ai-agent-frameworks-in-2025)
- [AI Agent Frameworks Compared 2026 - Turing](https://www.turing.com/resources/ai-agent-frameworks)

### 금융 AI 시뮬레이션
- [Multi-Agent Hedge Fund Simulation with LangGraph](https://shaikhmubin.medium.com/multi-agent-hedge-fund-simulation-with-langchain-and-langgraph-64060aabe711)
- [AlphaAgents: Multi-Agent LLM for Portfolio Construction](https://github.com/vedurmaliya/alpha-agents)
- [TradingAgents: Multi-Agent Financial Trading Framework](https://github.com/TauricResearch/TradingAgents)
- [JP Morgan AI Agent with LangGraph](https://aibuilder.services/how-jp-morgan-built-an-ai-agent-for-investment-research-with-langgraph/)
- [AWS: Financial Analysis Agent with LangGraph](https://aws.amazon.com/blogs/machine-learning/build-an-intelligent-financial-analysis-agent-with-langgraph-and-strands-agents/)

### 에이전트 메모리
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
- [Mem0 AI Agent Memory Research](https://mem0.ai/research)
- [Graph Memory for AI Agents - Mem0](https://mem0.ai/blog/graph-memory-solutions-ai-agents)
- [AI Agent Memory Architecture - Redis](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [Memory for AI Agents - The New Stack](https://thenewstack.io/memory-for-ai-agents-a-new-paradigm-of-context-engineering/)

### 성격 모델 + AI
- [Big Five Personality Traits on AI Agent Decision-Making](https://arxiv.org/abs/2503.15497)
- [Joint Modeling of Big Five and HEXACO](https://arxiv.org/abs/2510.14203)
- [Psychologically Enhanced AI Agents](https://www.emergentmind.com/papers/2509.04343)
- [Agent-Based Simulation of Financial Market with LLMs](https://arxiv.org/pdf/2510.12189)
- [Prospect Theoretic Multi-Agent Reinforcement Learning](https://openreview.net/pdf/4a85065219c0b5124b9f8331410b77459b9d4573.pdf)

### 데이터베이스 벤치마크
- [ClickHouse vs TimescaleDB vs InfluxDB 2025 Benchmarks](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison)
- [ClickHouse vs TimescaleDB 2026 - Tinybird](https://www.tinybird.co/blog/clickhouse-vs-timescaledb)
- [DuckDB: Modern Analytics Database 2025](https://sanj.dev/post/duckdb-data-engineering-modern-analytics-2025)
- [Time-Series Database Benchmarks 2025](https://www.timestored.com/data/time-series-database-benchmarks)

### 프로그래밍 언어
- [Why Agentic AI Developers Move from Python to Rust - Red Hat](https://developers.redhat.com/articles/2025/09/15/why-some-agentic-ai-developers-are-moving-code-python-rust)
- [Combining Rust and Python for High-Performance AI - The New Stack](https://thenewstack.io/combining-rust-and-python-for-high-performance-ai-systems/)
- [Go vs Python AI Infrastructure Benchmarks 2026](https://dasroot.net/posts/2026/02/go-vs-python-ai-infrastructure-throughput-benchmarks-2026/)
- [Python, Go, Rust, TypeScript and AI - Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/python-go-rust-typescript-and-ai)
