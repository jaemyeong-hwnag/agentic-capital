# 인프라 정리

## 아키텍처 개요

```
┌──────────────────────────────────────────────────────┐
│                    Application                        │
│  Python 3.12+ / LangGraph / Mem0                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ CEO     │ │ PM      │ │Analysts │ │ Trader  │   │
│  │ Agent   │ │ Agent   │ │ Agents  │ │ Agent   │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       └───────────┴───────────┴───────────┘          │
│                    │ MessagePack / LACP                │
├──────────────────────────────────────────────────────┤
│                    Data Layer                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │PostgreSQL│ │  Redis   │ │ Qdrant   │             │
│  │+Timescale│ │  7+      │ │ (Phase2) │             │
│  │+pgvectorscale │ │          │ │          │             │
│  └──────────┘ └──────────┘ └──────────┘             │
├──────────────────────────────────────────────────────┤
│                   External APIs                       │
│  Gemini │ Binance │ Upbit │ Alpaca │ KIS │ Yahoo    │
└──────────────────────────────────────────────────────┘
```

---

## Phase별 인프라

### Phase 1: 로컬 개발 / Paper Trading

모든 것을 **로컬 또는 Docker Compose**로 실행.

| 컴포넌트 | 구성 | 스펙 |
|---------|------|------|
| **App Server** | 로컬 Python | MacOS / Linux |
| **PostgreSQL 16** | Docker | + TimescaleDB 확장 + pgvectorscale 확장 |
| **Redis 7** | Docker | 기본 설정 |
| **Qdrant** | 불필요 (pgvectorscale 사용) | — |

#### Docker Compose 구성

```yaml
services:
  postgres:
    image: timescale/timescaledb-ha:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: agentic_capital
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/home/postgres/pgdata/data
    command: >
      postgres
      -c shared_preload_libraries='timescaledb'

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
```

#### 로컬 최소 사양

| 리소스 | 최소 | 권장 |
|--------|------|------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 20 GB SSD | 50 GB SSD |

---

### Phase 2: 단일 서버 운영

에이전트 10~50명, 실거래 시작.

| 컴포넌트 | 구성 | 스펙 | 월 비용 (예상) |
|---------|------|------|-------------|
| **App Server** | AWS EC2 / GCP VM | t3.large (2 vCPU, 8GB) | ~$60 |
| **PostgreSQL** | 동일 서버 Docker 또는 RDS | db.t3.medium (2 vCPU, 4GB) | ~$30 (RDS) |
| **Redis** | 동일 서버 Docker 또는 ElastiCache | cache.t3.micro | ~$15 |
| **Qdrant** | 동일 서버 Docker | 1GB RAM 할당 | $0 (셀프호스팅) |

#### 단일 서버 총 비용

| 항목 | 월 비용 |
|------|--------|
| 서버 (EC2 t3.large) | ~$60 |
| DB (RDS t3.medium) | ~$30 |
| Redis (ElastiCache) | ~$15 |
| Gemini API | ~$20 |
| 거래소 API | $0 (거래 수수료 별도) |
| **합계** | **~$125/월** |

---

### Phase 3: 확장 (에이전트 50+)

| 컴포넌트 | 구성 | 스펙 |
|---------|------|------|
| **App Server** | EC2 c6i.xlarge | 4 vCPU, 8GB |
| **PostgreSQL** | RDS db.r6g.large | 2 vCPU, 16GB (TimescaleDB) |
| **Redis** | ElastiCache r6g.large | 13GB |
| **Qdrant** | Qdrant Cloud 또는 EC2 전용 | 4GB RAM |
| **모니터링** | Grafana + Prometheus | EC2 또는 Grafana Cloud |

---

## 인프라 컴포넌트 상세

### PostgreSQL 16 + TimescaleDB + pgvectorscale

**역할**: 메인 DB (정형 + 시계열 + 벡터)

| 확장 | 용도 |
|------|------|
| `timescaledb` | 시계열 hypertable, 압축 chunk (Gorilla) |
| `pgvectorscale` | 벡터 저장/검색 (HNSW 인덱스) |

**핵심 설정**:
```sql
-- TimescaleDB hypertable 생성
SELECT create_hypertable('market_ohlcv', 'time');
SELECT create_hypertable('company_snapshots', 'time');
SELECT create_hypertable('agent_personality_history', 'time');
SELECT create_hypertable('agent_emotion_history', 'time');

-- 압축 정책 (7일 이상 된 데이터 자동 압축)
SELECT add_compression_policy('market_ohlcv', INTERVAL '7 days');

-- pgvectorscale 인덱스
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
```

**백업**: `pg_dump` 일일 자동 + WAL 아카이빙 (PITR)

### Redis 7+

**역할**: Working Memory, 감정 상태, 이벤트 스트림

| 데이터 구조 | 용도 |
|------------|------|
| Hash | `agent:{id}:emotion` — 실시간 감정 상태 |
| Hash | `agent:{id}:working_memory` — 최근 관찰 |
| Stream | `agent:messages` — 에이전트 간 메시지 (LACP) |
| String | `market:{symbol}:price` — 실시간 시세 캐시 |

**핵심 설정**:
```
maxmemory 1gb
maxmemory-policy allkeys-lru
```

**백업**: RDB 스냅샷 + AOF (선택)

### Qdrant (Phase 2)

**역할**: 에이전트 장기 기억 벡터 검색

| 설정 | 값 |
|------|-----|
| 벡터 차원 | 1024D |
| 양자화 | Scalar (int8) |
| 인덱스 | HNSW, m=16, ef_construct=200 |
| 디스크 | 벡터 on-disk, 인덱스 in-memory |

---

## 네트워크

### 필요 포트

| 포트 | 서비스 | 접근 |
|------|--------|------|
| 5432 | PostgreSQL | 내부만 |
| 6379 | Redis | 내부만 |
| 6333 | Qdrant | 내부만 |
| 8000 | App API (선택) | 외부 (모니터링 대시보드) |

### 아웃바운드 (외부 API)

| 대상 | 포트 | 프로토콜 |
|------|------|---------|
| generativelanguage.googleapis.com | 443 | HTTPS |
| api.binance.com | 443 | HTTPS + WSS |
| api.upbit.com | 443 | HTTPS + WSS |
| paper-api.alpaca.markets | 443 | HTTPS + WSS |
| openapi.koreainvestment.com | 443 | HTTPS |

---

## 모니터링 (권장)

| 도구 | 용도 | 비용 |
|------|------|------|
| **Grafana** | 대시보드 (수익률, 에이전트 상태, 시스템) | 무료 (셀프호스팅) |
| **Prometheus** | 메트릭 수집 | 무료 |
| **LangSmith** | LLM 트레이싱, 프롬프트 디버깅 | 무료 티어 |
| **structlog** | 애플리케이션 로그 (JSON) | 무료 |

### 핵심 모니터링 메트릭

| 카테고리 | 메트릭 |
|---------|--------|
| **비즈니스** | 총 자본, 일일 PnL, 샤프 비율, 최대 낙폭 |
| **에이전트** | 에이전트 수, 평균 감정 상태, 거래 빈도 |
| **시스템** | LLM API 지연시간, 토큰 사용량, DB 쿼리 시간 |
| **인프라** | CPU, RAM, 디스크, 네트워크 |
