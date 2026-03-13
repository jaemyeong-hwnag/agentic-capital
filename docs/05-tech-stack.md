# 기술 스택 (확정)

## 최상위 원칙

> 1. **목표: 돈을 번다** — 유일한 목적, 변경 불가
> 2. **모든 것은 AI 친화적** — 최상위 규칙을 제외한 모든 설계/데이터/소통은 AI 최적화
> 3. **데이터셋 최대 최적화** — 최신 논문 기반, 토큰 효율, 정확도 극대화

---

## 확정 기술 스택

| 구분 | 기술 | 선정 근거 (논문/벤치마크) |
|------|------|------------------------|
| **언어** | Python 3.12+ | AI 프레임워크 생태계 표준, I/O 바운드 프로젝트 |
| **AI 프레임워크** | LangGraph v1.0 | 상태 기반 그래프, 금융 AI 검증 — FinCon (NeurIPS 2024), TradingAgents |
| **에이전트 메모리** | A-MEM 방식 (Zettelkasten) | multi-hop 추론 2x 향상 — A-MEM (NeurIPS 2025) |
| **메모리 통합** | Mem0 | 벡터+KV+그래프 통합, 26% 높은 정확도 |
| **메인 DB** | PostgreSQL 16 + TimescaleDB | 정형+시계열 단일 서버, Gorilla 압축 |
| **벡터 DB** | pgvector → Qdrant | float16 + SQ int8, HNSW M=16~32 |
| **상태/캐시** | Redis 7+ | Working Memory, 감정 상태, 이벤트 스트림 |
| **분석** | DuckDB + Parquet + Arrow IPC | OLAP, 백테스팅, 논문 데이터 추출 |
| **LLM** | Gemini 2.5 Pro / Flash | Pro: 핵심 의사결정, Flash: 반복 판단 |
| **임베딩** | text-embedding-3-large (1024D) | float8 양자화, Matryoshka 축소 가능 |
| **LLM 프롬프트** | TOON + Markdown-KV + YAML | 토큰 40-60% 절감 — TOON (2025) |
| **에이전트 통신** | MessagePack (기본) / C2C (확장) | 30% 작은 페이로드 / KV-cache 직접 통신 — C2C (2025) |
| **수치 표현** | NumeroLogic `{digits:value}` | 토크나이저 파편화 방지 — NumeroLogic (EMNLP 2024) |
| **금융 데이터** | StockTime 방식 (정규화+패치) | 역정규화, 비율 변환 — StockTime (2024) |
| **통신 프로토콜** | LACP 기반 (PLAN/ACT/OBSERVE/SIGNAL) | 구조화된 메시지 타입 — LACP (NeurIPS 2025) |
| **경험 학습** | REMEMBERER 방식 (Q-value + decay) | 유틸리티 기반 유지, 10% 성능 향상 — REMEMBERER (2025) |

---

## 데이터 포맷 파이프라인

```
┌─────────────────────────────────────────────────────────┐
│  LLM ↔ Agent (프롬프트/응답)                              │
│  TOON (배열/테이블) + Markdown-KV (단일 레코드)            │
│  + YAML (중첩 구조) + NumeroLogic (수치)                  │
│  → 토큰 40-60% 절감, 정확도 60.7% (CSV 44.3% 대비)       │
├─────────────────────────────────────────────────────────┤
│  Agent ↔ Agent (내부 통신)                                │
│  LACP 프로토콜: PLAN/ACT/OBSERVE/SIGNAL 메시지 타입        │
│  MessagePack 직렬화 (기본) / C2C KV-cache 전송 (확장)     │
├─────────────────────────────────────────────────────────┤
│  Agent ↔ Memory                                          │
│  A-MEM Zettelkasten 노트 (context + keywords + links)    │
│  3계층: Episodic (Qdrant) / Semantic (PG) / Procedural   │
├─────────────────────────────────────────────────────────┤
│  Agent ↔ DB (영속화)                                      │
│  PostgreSQL JSONB + typed columns                        │
│  TimescaleDB 압축 chunk (Gorilla Delta-of-Delta + XOR)   │
├─────────────────────────────────────────────────────────┤
│  분석 파이프라인                                          │
│  Arrow IPC (인메모리) → Parquet (영속) → DuckDB (분석)    │
└─────────────────────────────────────────────────────────┘
```

---

## 에이전트 아키텍처

FinCon (NeurIPS 2024), TradingAgents (2024) 구조 참고:

```
CEO Agent (전략/인사/조직 — 완전 자율)
├── Portfolio Manager (포트폴리오 구성/리밸런싱)
├── Risk Manager (리스크 평가/경고)
├── Analyst Team (CEO가 자율 구성)
│   ├── Fundamental Analyst
│   ├── Technical Analyst
│   ├── Sentiment Analyst
│   └── ... (동적 추가/제거)
└── Trader (주문 실행)

※ 위 구조는 예시. CEO가 자율적으로 전면 변경 가능.
```

---

## 메모리 아키텍처

A-MEM (NeurIPS 2025), FinMem (2024), REMEMBERER (2025) 종합:

| 계층 | 저장소 | 내용 | 유지 정책 |
|------|--------|------|----------|
| **Working** | Redis | 현재 태스크, 최근 5-10개 관찰 | TTL 자동 만료 |
| **Episodic** | Qdrant (벡터) | 구체적 경험: {context, action, outcome, q_value} | 유틸리티 기반 decay (REMEMBERER) |
| **Semantic** | PostgreSQL | 축적된 지식, 시장 이해, 투자 원칙 | Reflection 트리거 업데이트 |
| **Procedural** | 코드/프롬프트 | 투자 전략, 분석 절차, 의사결정 규칙 | 주기적 증류 (distillation) |

### 메모리 노트 구조 (A-MEM Zettelkasten)

```yaml
memory_note:
  id: "ep_4821"
  context: "RSI divergence on AAPL, volatile_bullish regime, VIX={2:22}"
  keywords: [rsi_divergence, aapl, earnings_catalyst]
  tags: [technical_signal, high_conviction]
  links: [ep_3912, ep_4103]  # 유사 과거 경험
  q_value: 0.78
  embedding: float8[1024]
```

---

## 임베딩 최적화

| 설정 | 값 | 근거 |
|------|-----|------|
| 모델 | text-embedding-3-large | 금융 도메인 포함, Matryoshka 지원 |
| 차원 | 1024D (기본) → 256D (축소 시) | SMEC (2025): 축소 시 정보 손실 완화 |
| 저장 정밀도 | float8 | 4x 압축, <0.3% 정확도 손실 |
| 인덱스 | HNSW, M=16~32, efConstruction=200~400 | 표준 권장값 |
| 양자화 | SQ int8 + oversampling | 검색 3.66x 가속, 99%+ 정확도 |

---

## 금융 데이터 표현

StockTime (2024) + NumeroLogic (EMNLP 2024) 기반:

### 원칙
- **절대값 대신 비율 변화** (토큰 효율 + 스케일 불변)
- **역정규화 (Reversible Instance Normalization)** 적용
- **패치 단위** (5일 윈도우) 처리
- **NumeroLogic** 수치 표현: `{자릿수:값}`

### 예시 (TOON 포맷)
```
@prices[5](ticker,date,open_pct,high_pct,low_pct,close_pct,vol_ratio)
AAPL,2025-03-10,+0.3,+1.2,-0.5,+0.8,1.1x
AAPL,2025-03-11,-0.2,+0.4,-1.1,-0.7,0.9x
AAPL,2025-03-12,+1.1,+2.3,-0.1,+2.1,1.8x
```

---

## 에이전트 간 통신 프로토콜

LACP (NeurIPS 2025) 기반:

### 메시지 타입

| 타입 | 용도 |
|------|------|
| **PLAN** | 전략/의도 공유 |
| **ACT** | 도구 호출, 주문 실행 |
| **OBSERVE** | 결과/상태 보고 |
| **SIGNAL** | 투자 시그널 (BUY/SELL/HOLD) |

### 메시지 구조
```yaml
msg:
  type: SIGNAL
  from: analyst_tech
  to: pm_alpha
  priority: 0.85
  content:
    thesis: "AAPL bullish divergence on RSI, earnings in 5d"
    signal: BUY
    confidence: 0.72
    data:
      ticker: AAPL
      indicator: RSI_14
      current: {2:34}
      catalyst: earnings
    refs: [ep_4821, sem_112]
  meta:
    ts: 1710340800
    ttl: 3
```

---

## 논문 참조 목록

| 논문 | 연도 | 적용 영역 |
|------|------|----------|
| FinCon | NeurIPS 2024 | 에이전트 조직 구조 (Manager-Analyst) |
| TradingAgents | 2024 | 멀티 에이전트 투자 프레임워크 |
| A-MEM | NeurIPS 2025 | Zettelkasten 에이전트 메모리 |
| REMEMBERER | 2025 | Q-value 기반 경험 유지/삭제 |
| FinMem | 2024 | 계층적 금융 메모리 |
| StockTime | 2024 | LLM용 시계열 토큰화 |
| NumeroLogic | EMNLP 2024 | LLM 수치 표현 최적화 |
| TOON | 2025 | LLM용 토큰 최적화 직렬화 |
| LACP | NeurIPS 2025 | 에이전트 통신 프로토콜 |
| C2C | 2025 | KV-cache 기반 의미 통신 |
| SMEC | 2025 | Matryoshka 임베딩 압축 |
| CER | ICLR 2025 | 문맥적 경험 리플레이 |
| Generative Agents | UIST 2023 | 에이전트 성격/관찰/반성/계획 |
| MarketSenseAI 2.0 | 2025 | 멀티모달 금융 에이전트 |
| FinRobot | 2024 | Financial Chain-of-Thought |
| SchemaAgent | 2025 | AI 기반 스키마 생성 |
