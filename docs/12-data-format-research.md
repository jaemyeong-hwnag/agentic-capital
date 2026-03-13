# AI-Friendly Data Formats & Structures Research

> AI 멀티 에이전트 투자 시뮬레이션을 위한 데이터 포맷 및 구조 최적화 연구
> 조사일: 2026-03-13

---

## 1. 데이터 직렬화 포맷 비교 (Serialization Formats)

### 1.1 포맷별 벤치마크 종합

| 포맷 | 직렬화 속도 | 역직렬화 속도 | 페이로드 크기 | 스키마 필요 | LLM 호환 |
|------|------------|-------------|-------------|-----------|---------|
| **JSON** | 느림 (7,045 ns/op) | 느림 | 가장 큼 | 없음 | 최고 |
| **MessagePack** | 빠름 | 빠름 | JSON 대비 ~30% 작음 | 없음 | 불가 (바이너리) |
| **Protocol Buffers** | 빠름 | 빠름 (1,827 ns/op) | **가장 작음** | 필수 (.proto) | 불가 |
| **FlatBuffers** | 빠름 | **최고 (81 ns/op)** | 작음 | 필수 (.fbs) | 불가 |
| **CBOR** | MessagePack 대비 ~2x 빠름 | 빠름 | MessagePack과 유사 | 없음 | 불가 |
| **Apache Avro** | 중간 | 중간 | 작음 | 필수 (.avsc) | 불가 |
| **Arrow IPC** | **최고 (zero-copy)** | **최고 (zero-copy)** | 큼 (비압축) | 내장 스키마 | 불가 |
| **TOON** | JSON 수준 | JSON 수준 | JSON 대비 40-60% 작음 | 내장 스키마 | **최고** |

> 출처: DEV Community Go 벤치마크, Medium Atomic Architect 벤치마크 (2025)

### 1.2 용도별 최적 포맷 권장

#### LLM 프롬프트 구성 (Prompt Construction)
- **1순위: TOON (Token-Oriented Object Notation)**
  - JSON 대비 40-60% 토큰 절감, 정확도 73.9% vs JSON 69.7%
  - 반복적 테이블형 데이터 (거래 내역, 포트폴리오 등)에 특히 효과적
  - GPT-5 Nano에서 99.4% 정확도 달성하면서 46% 토큰 절감
  - 2025년 10월 출시, 15+ 언어 구현 (Python, TypeScript, Rust 등)
- **2순위: YAML** — 중첩 구조 데이터에서 가장 높은 LLM 이해도 (GPT-5 Nano: 62.1%, Gemini Flash Lite: 51.9%)
- **3순위: Markdown** — 가장 토큰 효율적 (JSON 대비 34-38% 절감), 비정형+정형 혼합에 적합

#### 에이전트 간 통신 (Agent-to-Agent Communication)
- **내부 통신: MessagePack 또는 CBOR**
  - 스키마 없이 JSON과 동일한 구조, 30% 작은 페이로드
  - CBOR: IETF 표준, AWS IoT Core 네이티브 지원
  - MessagePack: 더 넓은 라이브러리 생태계
- **고성능 경로: FlatBuffers**
  - Zero-copy 역직렬화로 81ns/op 달성 (Protobuf 대비 4.3x 빠름)
  - 에이전트 상태 동기화 등 초저지연 필요 시
- **분산 시스템: Protocol Buffers**
  - 가장 작은 페이로드, gRPC 네이티브 통합
  - 스키마 진화 지원으로 버전 관리 용이

#### DB 저장 (Storage)
- **정형 데이터: PostgreSQL 네이티브 (JSONB + typed columns)**
- **시계열: TimescaleDB compressed chunks** (아래 섹션 3 참조)
- **벡터: pgvector/Qdrant 네이티브 포맷** (아래 섹션 2 참조)
- **분석용 직렬화: Apache Parquet** — 열 기반 압축, Arrow 생태계 통합

#### API 페이로드 (External API)
- **외부 API: JSON** — 범용 호환성
- **내부 API: MessagePack 또는 Protobuf** — 성능 최적화
- **데이터 파이프라인: Arrow IPC** — 10K MB/s 로컬 처리량, 2000 MB/s 원격 처리량

### 1.3 프로젝트 적용 권장안

```
┌─────────────────────────────────────────────────────┐
│  LLM ↔ Agent                                        │
│  TOON (테이블형) + YAML (계층형) + Markdown (서술형)  │
├─────────────────────────────────────────────────────┤
│  Agent ↔ Agent (내부)                                │
│  MessagePack (기본) / FlatBuffers (초저지연)          │
├─────────────────────────────────────────────────────┤
│  Agent ↔ DB                                          │
│  PostgreSQL JSONB + Typed Columns                    │
├─────────────────────────────────────────────────────┤
│  분석 파이프라인                                      │
│  Arrow IPC (인메모리) → Parquet (영속화)              │
├─────────────────────────────────────────────────────┤
│  외부 API                                            │
│  JSON (호환성) / Protobuf+gRPC (고성능)              │
└─────────────────────────────────────────────────────┘
```

---

## 2. 벡터/임베딩 저장 포맷 (Vector/Embedding Storage)

### 2.1 정밀도별 비교

| 정밀도 | 바이트/차원 | 메모리 절감 | 정확도 손실 | 권장 용도 |
|--------|-----------|-----------|-----------|----------|
| **float32** | 4 bytes | 기준 | 없음 | 학습 시, 마스터 저장소 |
| **float16** | 2 bytes | 50% | <1% (거의 무시) | **기본 운영 권장** |
| **float8** | 1 byte | 75% | <0.3% | 대규모 검색 인덱스 |
| **int8 (SQ)** | 1 byte | 75% | 1-3% | 비용 최적화 |
| **binary** | 1 bit/dim | 97% | 5-15% | 1차 필터링/프리패치 |

> 출처: Hugging Face embedding-quantization 블로그, Qdrant 문서, Azure AI Search 문서 (2025)

### 2.2 임베딩 압축 기법

#### Scalar Quantization (SQ) — 권장 기본값
- float32 → int8 매핑, 4x 압축
- **모든 임베딩 모델과 호환** (OpenAI, Cohere, Gemini 등)
- 평균 3.66x 검색 속도 향상
- 99%+ 정확도 유지
- Qdrant, Weaviate, Pinecone 모두 지원

#### Product Quantization (PQ) — 고차원 대규모용
- 1024차원 벡터 → 128 바이트 (32x 압축, 97% 메모리 절감)
- 검색 속도 5.5x 향상
- SIMD 비친화적이라 SQ보다 느림
- **고차원 벡터(512D+)에서만 권장**

#### Binary Quantization (BQ) — 초대규모 1차 필터링
- 24.76x 평균 속도 향상, 28x 인덱스 크기 감소
- 정확도 손실이 크므로 반드시 rescoring 필요
- Qdrant v1.15+ 에서 1.5-bit, 2-bit BQ도 지원 (SQ와 BQ 사이의 중간 지점)

#### Matryoshka Representation Learning (MRL) — 차원 축소
- 단일 모델에서 다양한 크기의 임베딩 생성 (예: 1024D → 256D → 64D)
- 핵심 의미 정보를 벡터 앞쪽에 집중 배치
- **SMEC (2025)**: 차원 pruning 시 정보 손실 완화, 비지도학습 향상
- 80% 비용 절감 가능 (Matryoshka + 양자화 조합)

### 2.3 HNSW 파라미터 최적화

| 파라미터 | 권장 값 | 설명 |
|---------|--------|------|
| **M** | 16 (기본) → 32 (고정확도) | 노드당 최대 연결 수. 메모리 1.5-2x 오버헤드 |
| **efConstruction** | 200-400 | 인덱스 빌드 품질. 높을수록 정확하나 빌드 느림 |
| **efSearch** | 128-256 | 검색 후보 큐 크기. 높을수록 정확하나 지연 증가 |

**주의**: HNSW 인덱스 규모가 커질수록 RAG 품질이 저하됨 (recall degradation).
- **해결책**: Oversampling + Rescoring, 파티션 분할, 하이브리드 검색 (HNSW + 키워드)

### 2.4 프로젝트 적용 권장안 (에이전트 메모리)

```
성격 벡터 (15D):      float32 저장 (크기가 작아 양자화 불필요)
메모리 임베딩 (768D+): float16 저장 + SQ int8 인덱스 (Qdrant)
대규모 확장 시:       Matryoshka 768D→256D 축소 + SQ int8
1차 필터링:          Binary Quantization → Rescoring
```

---

## 3. 시계열 데이터 포맷 (Time-Series)

### 3.1 포맷/DB 벤치마크 (OHLCV 시장 데이터)

| DB/포맷 | 평균 쿼리 시간 | 쓰기 처리량 | 압축률 | 적합 용도 |
|---------|-------------|-----------|-------|----------|
| **QuestDB** | 25ms | 높음 | 높음 | 실시간 OHLCV 쿼리 1위 |
| **KDB+** | 109ms | 매우 높음 | 높음 | 금융 업계 표준, 결정론적 저지연 |
| **ClickHouse** | 547ms | 매우 높음 | 매우 높음 | 대규모 분석, 집계 |
| **TimescaleDB** | 1,021ms | 중간 | 높음 | PostgreSQL 호환, 범용성 |
| **PostgreSQL** | 3,493ms | 중간 | 낮음 | 기준선 |

> 출처: timestored.com 벤치마크, QuestDB 비교 (2025)

### 3.2 저장 포맷 비교

| 포맷 | 인메모리 | 디스크 | 스트리밍 | 분석 | 상호운용성 |
|------|---------|-------|---------|------|-----------|
| **Arrow IPC** | **최고** | 중간 | 좋음 | **최고** | 매우 높음 |
| **Parquet** | 불가 | **최고** | 불가 | 좋음 | 매우 높음 |
| **TimescaleDB 압축** | N/A | 좋음 | N/A | 좋음 | PostgreSQL |
| **InfluxDB Line Protocol** | N/A | 좋음 | **최고** | 중간 | InfluxDB |

- **InfluxDB 3.0**: Arrow 생태계 기반으로 재설계, Parquet 영속 저장 + Arrow 인메모리
- **TimescaleDB 2.25 (2026.01)**: ColumnarIndexScan 도입, 압축 chunk에서 집계 가속

### 3.3 압축 알고리즘

#### Gorilla 압축 (Facebook, 2015 — 현재도 업계 표준)
- **타임스탬프**: Delta-of-Delta 인코딩
  - 96%의 타임스탬프를 1비트로 압축 (일정 간격 데이터)
  - 금융 시장 데이터의 정규 간격에 매우 효과적
- **값(가격 등)**: XOR 인코딩
  - 연속 값의 XOR 차이 저장, 유효 비트만 기록
  - LZ 기반 압축 대비 40x 빠른 디코딩
- **Chimp (2022 VLDB)**: Gorilla 개선, 역방향 디코딩 지원으로 최근 데이터 쿼리 가속

#### Delta-of-Delta
- 일정 간격 시계열에 최적 (틱 데이터, 분봉 등)
- 대부분의 차이가 0이 되어 극단적 압축

#### Simple-8b + XOR 확장
- Prometheus, InfluxDB 등에서 사용
- 역방향 스캔 지원으로 "최근 N분" 쿼리 최적화

### 3.4 프로젝트 적용 권장안

```
실시간 스트리밍:    TimescaleDB hypertable (이미 선택됨, 적합)
                   → 압축 chunk 활성화 (Gorilla 계열 자동 적용)
인메모리 분석:      Arrow RecordBatch (pandas/polars 통합)
오프라인 백테스팅:  DuckDB + Parquet (이미 선택됨, 적합)
장기 아카이브:      Parquet (S3/로컬) — 열 기반 압축 최적
```

---

## 4. 에이전트 상태 표현 (Agent State Representation)

### 4.1 단일 구조로 표현하는 에이전트 상태

연구 결과를 종합한 권장 에이전트 상태 스키마:

```python
@dataclass
class AgentState:
    # === 정체성 (고정/저빈도 변경) ===
    identity: AgentIdentity          # id, name, role, org_position

    # === 성격 벡터 (15D dense, 저빈도 변경) ===
    personality: np.ndarray          # float32[15] — OCEAN(5) + HEXACO(1) + 전망이론(4) + 추가(5)

    # === 감정 상태 (고빈도 변경) ===
    emotion: EmotionState            # valence, arousal, dominance (VAD 모델)
                                     # + stress_level, confidence, mood_trend

    # === 메모리 (동적, 계층적) ===
    working_memory: List[MemoryNote] # 현재 컨텍스트 (최근 5-10개)
    episodic_refs: List[str]         # 에피소드 메모리 참조 ID (벡터DB 키)
    semantic_summary: str            # 축적된 지식 요약 (압축)

    # === 의사결정 컨텍스트 ===
    current_portfolio: PortfolioSnapshot
    recent_performance: PerformanceMetrics
    pending_decisions: List[Decision]
```

### 4.2 표현 방식 비교

| 방식 | 장점 | 단점 | 적합 용도 |
|------|------|------|----------|
| **Flat (현재 DB 스키마)** | SQL 친화적, 인덱싱 용이 | 관계 표현 제한적 | DB 영속화, 단순 조회 |
| **계층적 (위 dataclass)** | 논리적 그룹핑, LLM 프롬프트 구성 용이 | 부분 업데이트 복잡 | 런타임 상태, 프롬프트 |
| **그래프 기반** | 에이전트 간 관계, 메모리 연결 | 복잡도 높음, 오버헤드 | 조직 구조, 메모리 네트워크 |

**권장: 하이브리드 접근**
- **DB 저장**: Flat 테이블 (현재 data model 유지)
- **런타임**: 계층적 dataclass (위 구조)
- **메모리 네트워크**: 그래프 (A-MEM 방식, Zettelkasten)
- **LLM 프롬프트**: 계층 구조를 TOON/YAML로 직렬화

### 4.3 최신 연구 기반 메모리 아키텍처

#### A-MEM (NeurIPS 2025) — Agentic Memory
- Zettelkasten 원칙 기반 동적 메모리 네트워크
- 각 메모리를 구조화된 "노트"로 저장:
  - **contextual description**: 상황 설명
  - **keywords**: 키워드 태그
  - **tags**: 분류 태그
  - **links**: 다른 메모리와의 연결
- 새 메모리 추가 시 기존 메모리의 맥락 표현 자동 업데이트 ("memory evolution")
- 복잡한 multi-hop 추론에서 기존 대비 2x 성능 향상

#### AgentOS (2025) — 운영체제 패러다임
- LLM을 "Reasoning Kernel"로 재정의
- Semantic Memory Management Unit: 의미 기반 메모리 관리
- Cognitive Memory Hierarchy: 인지적 메모리 계층 구조
- Context window를 Addressable Semantic Space로 관리

#### 메모리 계층 구조 (연구 종합)
```
┌────────────────────────────────────┐
│  Working Memory (작업 기억)         │  Redis / 인메모리
│  현재 태스크 관련 최근 기억          │  5-10 항목, 빠른 접근
├────────────────────────────────────┤
│  Episodic Memory (일화 기억)        │  벡터DB (Qdrant)
│  구체적 경험, 투자 결과              │  임베딩 + 메타데이터
├────────────────────────────────────┤
│  Semantic Memory (의미 기억)        │  PostgreSQL + 요약
│  축적된 시장 지식, 규칙              │  구조화된 텍스트
├────────────────────────────────────┤
│  Procedural Memory (절차 기억)      │  코드/프롬프트 템플릿
│  투자 전략, 분석 절차                │  버전 관리
└────────────────────────────────────┘
```

### 4.4 프로젝트 적용 권장안

1. **성격 벡터**: float32[15] numpy array → DB에는 개별 컬럼, 런타임에는 벡터
2. **감정 상태**: VAD(Valence-Arousal-Dominance) 3D + 추가 지표 → Redis 캐시
3. **메모리**: A-MEM 스타일 구조화 노트 → Qdrant 저장, ChromaDB 대안
4. **LLM 전달 시**: 계층 구조를 TOON (테이블형 데이터) + YAML (상태 정보)로 직렬화

---

## 5. LLM 컨텍스트 최적화 (Context Optimization)

### 5.1 포맷별 토큰 효율성 벤치마크

| 포맷 | 토큰 사용량 (JSON 대비) | LLM 정확도 | 최적 용도 |
|------|----------------------|-----------|----------|
| **TOON** | **40-60% 절감** | 73.9% (JSON 69.7%) | 테이블형, 반복 구조 |
| **Markdown** | **34-38% 절감** | 중간 (48-54%) | 토큰 효율 우선, 문서형 |
| **YAML** | ~10% 절감 | **최고 (51-62%)** | 중첩 구조, 정확도 우선 |
| **JSON** | 기준 (100%) | 중간 (43-53%) | 외부 호환성, 디버깅 |
| **XML** | ~20% 증가 | **최하 (34-51%)** | 사용하지 않음 권장 |

> 출처: improvingagents.com 벤치마크 (GPT-5 Nano, Llama 3.2, Gemini 2.5 Flash Lite)

### 5.2 용도별 포맷 전략

#### 투자 거래 데이터 → TOON
```toon
trades[3]{date,ticker,action,qty,price}
2024-03-01 AAPL buy 100 178.50
2024-03-01 GOOGL sell 50 141.20
2024-03-02 MSFT buy 200 415.30
```
vs JSON (동일 데이터):
```json
[{"date":"2024-03-01","ticker":"AAPL","action":"buy","qty":100,"price":178.50},
 {"date":"2024-03-01","ticker":"GOOGL","action":"sell","qty":50,"price":141.20},
 {"date":"2024-03-02","ticker":"MSFT","action":"buy","qty":200,"price":415.30}]
```
→ TOON이 약 50% 적은 토큰 사용

#### 에이전트 상태/성격 → YAML
```yaml
agent:
  name: Agent_Kim
  role: senior_trader
  personality:
    openness: 72
    conscientiousness: 85
    risk_appetite: 65
  emotion:
    valence: 0.6
    arousal: 0.4
    stress: 0.3
  portfolio_value: 1250000
```

#### 시장 분석 보고서 → Markdown
```markdown
## 시장 분석 요약
- **S&P 500**: +1.2% (강세)
- **변동성 (VIX)**: 18.5 (안정)
- **주요 이벤트**: FOMC 회의 (3/15)

### 포트폴리오 영향
기술주 비중 40% → 금리 인하 기대 시 긍정적
```

### 5.3 하이브리드 프롬프트 구성 전략

```
[시스템 프롬프트 — YAML]
에이전트 정체성, 성격, 역할 정의

[컨텍스트 — TOON]
최근 거래 내역, 포트폴리오 현황, 시장 데이터 (테이블형)

[메모리 — Markdown]
관련 과거 경험 요약, 시장 분석

[지시 — 자연어]
의사결정 요청, 제약 조건
```

### 5.4 추가 토큰 절감 기법

1. **약어/코드 매핑**: 자주 쓰는 필드를 약어로 (예: `conscientiousness` → `C`, `risk_appetite` → `RA`)
2. **숫자 정밀도 제한**: 불필요한 소수점 제거 (178.5000 → 178.5)
3. **차등 업데이트**: 전체 상태 대신 변경된 부분만 전달
4. **메모리 요약 압축**: R³Mem (Reversible Memory Compression) 기법 적용 가능

---

## 6. 최신 연구 논문 참조 (2024-2026)

### 6.1 에이전트 메모리 시스템

| 논문 | 연도 | 핵심 기여 |
|------|------|----------|
| **A-MEM: Agentic Memory for LLM Agents** | 2025 (NeurIPS) | Zettelkasten 기반 동적 메모리 네트워크, multi-hop 추론 2x 향상 |
| **Memory in LLM-based Multi-agent Systems** | 2025 (TechRxiv) | MAS 메모리 메커니즘 종합 서베이, 집단 기억 개념 |
| **A Survey on the Memory Mechanism of LLM-based Agents** | 2025 (ACM TOIS) | 메모리 메커니즘 분류 체계, 실험적 비교 |
| **Episodic Memory is the Missing Piece for Long-Term LLM Agents** | 2025 (arXiv) | 장기 에이전트를 위한 에피소딕 메모리 필요성 |
| **How Memory Management Impacts LLM Agents** | 2025 (arXiv) | 메모리 관리가 에이전트 경험 추종 행동에 미치는 영향 |
| **R³Mem: Reversible Memory Compression** | 2025 | 가역적 메모리 압축으로 장기 기억 효율화 |
| **From Storage to Experience: Evolution of LLM Agent Memory** | 2026 (Preprints) | 저장→반영→경험의 3단계 메모리 진화 프레임워크 |

### 6.2 멀티 에이전트 아키텍처

| 논문 | 연도 | 핵심 기여 |
|------|------|----------|
| **SALLMA: Software Architecture for LLM-Based MAS** | 2025 | LLM MAS 전용 소프트웨어 아키텍처 |
| **Agentic AI: Architectures, Taxonomies, Evaluation** | 2026 (arXiv) | 6차원 분류 체계 (인식, 기억, 행동, 프로파일링, 계획, 반성) |
| **Large Language Model based Multi-Agents: Survey** | 2024/2025 (arXiv) | LLM MAS 진행 상황과 과제 종합 |
| **Cache-to-Cache (C2C)** | 2025 | KV-cache 기반 LLM 간 직접 의미 통신, 텍스트 생성 우회 |
| **ECON** | 2025 | 계층적 RL 기반 다중 LLM 협업, 베이지안 내쉬 균형 |
| **Cognitive Agents in Urban Mobility** | 2025 (PMC) | LLM 추론을 MAS 시뮬레이션에 통합 |
| **AgentOS** | 2025 | LLM을 Reasoning Kernel로 재정의, OS 패러다임 |

### 6.3 벡터/임베딩 최적화

| 논문/프로젝트 | 연도 | 핵심 기여 |
|-------------|------|----------|
| **Optimization of Embeddings Storage for RAG Systems** | 2025 (arXiv 2505.00105) | 양자화+차원 축소로 RAG 저장 최적화 |
| **SMEC: Rethinking Matryoshka for Retrieval Embedding Compression** | 2025 (arXiv 2510.12474) | Sequential MRL, 차원 pruning 정보 손실 완화 |
| **P-HNSW: Crash-Consistent HNSW on Persistent Memory** | 2025 (MDPI) | 영구 메모리 기반 충돌 일관성 보장 HNSW |
| **d-HNSW: Efficient Vector Search on Disaggregated Memory** | 2025 (ACM) | RDMA 기반 분산 메모리 벡터 검색 |
| **HNSW at Scale: Why RAG Gets Worse as VectorDB Grows** | 2025 (TDS) | 대규모 HNSW 리콜 저하 분석 및 해결책 |

### 6.4 데이터 포맷/직렬화

| 논문/프로젝트 | 연도 | 핵심 기여 |
|-------------|------|----------|
| **TOON: Token-Oriented Object Notation** | 2025 | LLM용 토큰 최적화 데이터 포맷, 40-60% 절감 |
| **Prompt Engineering for Structured Data** | 2025 (Frontiers AI / Preprints) | LLM 구조화 데이터 생성에서 프롬프트 스타일 비교 |
| **Which Nested Data Format Do LLMs Understand Best?** | 2025 | JSON vs YAML vs XML vs Markdown LLM 이해도 실험 |
| **Apache Arrow DataFusion** | 2024 (SIGMOD) | 빠른 임베딩 가능한 모듈식 분석 쿼리 엔진 |

---

## 7. 종합 권장 사항 (프로젝트 적용)

### 현재 기술 스택과의 정합성

현재 스택 (Python, LangGraph, Mem0, PostgreSQL+TimescaleDB, pgvector→Qdrant, Redis, DuckDB)은 **이미 잘 선택되어 있음**. 추가 최적화 포인트:

### 즉시 적용 가능 (Quick Wins)

| 영역 | 현재 | 권장 변경 | 예상 효과 |
|------|------|----------|----------|
| LLM 프롬프트 내 테이블 데이터 | JSON | **TOON** | 토큰 40-60% 절감, 비용 절감 |
| LLM 프롬프트 내 상태 데이터 | JSON | **YAML** | 정확도 10-20% 향상 |
| 에이전트 간 내부 통신 | JSON | **MessagePack** | 페이로드 30% 감소, 파싱 속도 향상 |
| 벡터 임베딩 저장 | float32 | **float16** | 메모리 50% 절감, 정확도 유지 |
| Qdrant 양자화 | 미설정 | **SQ int8 + oversampling** | 검색 3.66x 가속 |
| TimescaleDB 압축 | 미설정 | **압축 chunk 활성화** | 저장 공간 대폭 절감 |

### 중기 최적화 (성장 시)

| 영역 | 권장 | 시점 |
|------|------|------|
| 에이전트 메모리 | A-MEM 스타일 Zettelkasten 메모리 네트워크 도입 | 에이전트 50+ |
| 임베딩 차원 축소 | Matryoshka 768D→256D | 메모리 100K+ |
| 벡터 1차 필터링 | Binary Quantization + Rescoring | 벡터 500K+ |
| 분석 파이프라인 | Arrow IPC 기반 실시간 분석 | 시뮬레이션 고속화 필요 시 |
| 에이전트 통신 | FlatBuffers (초저지연) 또는 C2C (KV-cache 직접 통신) | 에이전트 100+ |

### 장기 아키텍처 고려 (확장 시)

- **QuestDB 도입 검토**: OHLCV 쿼리가 TimescaleDB 대비 40x 빠름 (25ms vs 1,021ms)
- **Arrow Flight**: 서비스 간 데이터 전송 표준화 (10K MB/s 로컬)
- **AgentOS 패러다임**: Context window를 Semantic Address Space로 관리
- **ECON/C2C**: 에이전트 간 직접 의미 통신으로 텍스트 직렬화 우회

---

## Sources

### 직렬화 포맷
- [JSON vs MessagePack vs Protobuf Benchmarks (Go)](https://dev.to/devflex-pro/json-vs-messagepack-vs-protobuf-in-go-my-real-benchmarks-and-what-they-mean-in-production-48fh)
- [Protobuf vs MessagePack vs CBOR vs FlatBuffers Benchmarked](https://medium.com/@the_atomic_architect/your-api-isnt-slow-your-payload-is-ca6d0193477c)
- [FlatBuffers vs Protobuf vs JSON Benchmarks](https://medium.com/@harshiljani2002/benchmarking-data-serialization-json-vs-protobuf-vs-flatbuffers-3218eecdba77)
- [CBOR vs MessagePack](https://cborbook.com/introduction/cbor_vs_the_other_guys.html)
- [Sufficient Serialization (2025)](https://curtislowder.com/blog/2025-08-10-sufficient-serialization/)

### TOON 포맷
- [TOON Official Site](https://toonformat.dev/)
- [TOON vs JSON: Why AI Agents Need Token-Optimized Data Formats](https://jduncan.io/blog/2025-11-11-toon-vs-json-agent-optimized-data/)
- [TOON GitHub Repository](https://github.com/toon-format/toon)
- [TOON Reduces LLM Costs (InfoQ)](https://www.infoq.com/news/2025/11/toon-reduce-llm-cost-tokens/)
- [TOON vs JSON vs YAML Token Efficiency](https://medium.com/@ffkalapurackal/toon-vs-json-vs-yaml-token-efficiency-breakdown-for-llm-5d3e5dc9fb9c)

### LLM 프롬프트 포맷
- [Which Nested Data Format Do LLMs Understand Best?](https://www.improvingagents.com/blog/best-nested-data-format/)
- [Beyond JSON: Picking the Right Format for LLM Pipelines](https://medium.com/@michael.hannecke/beyond-json-picking-the-right-format-for-llm-pipelines-b65f15f77f7d)
- [TOON vs TRON vs JSON vs YAML vs CSV Comparison](https://www.piotr-sikora.com/blog/2025-12-05-toon-tron-csv-yaml-json-format-comparison)
- [Prompt Engineering for Structured Data (Frontiers)](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1558938/full)

### 벡터/임베딩
- [Binary and Scalar Embedding Quantization (Hugging Face)](https://huggingface.co/blog/embedding-quantization)
- [Qdrant Vector Quantization](https://qdrant.tech/documentation/guides/quantization/)
- [Optimization of Embeddings Storage for RAG (arXiv)](https://arxiv.org/html/2505.00105v1)
- [Scaling Vector Search: Quantization and Matryoshka Embeddings](https://towardsdatascience.com/649627-2/)
- [SMEC: Rethinking Matryoshka for Retrieval Compression](https://arxiv.org/abs/2510.12474)
- [HNSW at Scale: Why RAG Gets Worse](https://towardsdatascience.com/hnsw-at-scale-why-your-rag-system-gets-worse-as-the-vector-database-grows/)
- [d-HNSW: Efficient Vector Search on Disaggregated Memory](https://arxiv.org/abs/2505.11783)

### 시계열
- [Time-Series Database Benchmarks 2025](https://www.timestored.com/data/time-series-database-benchmarks)
- [QuestDB vs TimescaleDB](https://questdb.com/blog/timescaledb-vs-questdb-comparison/)
- [ClickHouse vs TimescaleDB vs InfluxDB 2025](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison)
- [Gorilla Time Series Compression](https://github.com/keisku/gorilla)
- [Time Series Compression Algorithms Explained](https://www.tigerdata.com/blog/time-series-compression-algorithms-explained)
- [Apache Arrow IPC Documentation](https://arrow.apache.org/docs/format/IPC.html)

### 에이전트 메모리/아키텍처
- [A-MEM: Agentic Memory for LLM Agents (NeurIPS 2025)](https://arxiv.org/abs/2502.12110)
- [Memory in LLM-based Multi-agent Systems (TechRxiv)](https://www.techrxiv.org/users/1007269/articles/1367390/master/file/data/LLM_MAS_Memory_Survey_preprint_/LLM_MAS_Memory_Survey_preprint_.pdf)
- [A Survey on Memory Mechanism of LLM-based Agents (ACM TOIS)](https://dl.acm.org/doi/10.1145/3748302)
- [Episodic Memory for Long-Term LLM Agents](https://arxiv.org/pdf/2502.06975)
- [Agent Memory Paper List (GitHub)](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- [SALLMA: Software Architecture for LLM-Based MAS](https://robertoverdecchia.github.io/papers/SATrends_2025.pdf)
- [Agentic AI: Architectures, Taxonomies, Evaluation](https://arxiv.org/html/2601.12560v1)
- [From Storage to Experience: Evolution of LLM Agent Memory](https://www.preprints.org/manuscript/202601.0618)
- [LLM-based Multi-Agents Survey](https://arxiv.org/abs/2402.01680)
