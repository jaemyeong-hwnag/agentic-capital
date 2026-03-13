# 설계 검증 — DB/데이터셋 AI 친화성 논문 기반 분석

## 검증 목적

현재 설계가 (1) 프로젝트에 적합한지, (2) AI 친화적인지를 2024-2025 최신 논문/벤치마크로 검증.

---

## 검증 결과 요약

| # | 항목 | 현재 설계 | 판정 | 변경사항 |
|---|------|----------|------|---------|
| 1 | Multi-DB 아키텍처 | PG + TimescaleDB + Redis + Qdrant + DuckDB | **KEEP** | 최적 polyglot persistence |
| 2 | 벡터 DB | pgvector → Qdrant | **CHANGE** | pgvector → **pgvectorscale** (10x 빠름) |
| 3 | 시계열 DB | TimescaleDB (Gorilla 압축) | **KEEP** | Phase 3에서 QuestDB 검토 |
| 4 | 데이터 포맷 | TOON + YAML + Markdown-KV + NumeroLogic | **KEEP** | 2025 최신 연구로 완전 검증됨 |
| 5 | 에이전트 메모리 | A-MEM + Mem0 + REMEMBERER | **KEEP** | 2025 서베이 논문으로 합의 확인 |
| 6 | 그래프 DB | 없음 (관계형만) | **CHANGE** | Phase 2에 **Apache AGE** 추가 |
| 7 | 직렬화 | MessagePack + LACP + C2C | **KEEP** | 스키마프리 중 최고 성능 |
| 8 | 임베딩 저장 | float8 + SQ int8 + HNSW | **KEEP** | arXiv 2025 벤치마크와 정확히 일치 |

**결론: 8개 중 6개 이미 최적, 2개 마이너 변경 (pgvectorscale, Apache AGE)**

---

## 1. Multi-DB 아키텍처

### 현재 설계
PostgreSQL 16 + TimescaleDB (메인+시계열), pgvectorscale/Qdrant (벡터), Redis 7 (상태), DuckDB (분석)

### 논문 근거

| 출처 | 발견 |
|------|------|
| **Agentic Postgres** (Tiger Data, 2025) | TimescaleDB + pgvectorscale + BM25를 단일 PG에 통합. AI 에이전트 워크로드 전용 설계 |
| **Scaling Agent Systems** (arXiv 2512.08296, 2025) | 100 에이전트 이하에서는 운영 단순성이 이론적 최적성보다 중요 |
| **Agentic AI Survey** (arXiv 2510.25445, 2025) | 크로스 에이전트 컨텍스트 공유가 핵심 — DB 개수가 아님 |

### 판정: **KEEP**

Polyglot persistence (각 DB가 최적 워크로드 담당)가 정확한 패턴. Agentic Postgres가 이 접근을 직접 검증.

---

## 2. 벡터 DB

### 현재 설계
pgvector (Phase 1) → Qdrant (Phase 2)

### 논문/벤치마크 근거

| 출처 | 발견 |
|------|------|
| **VectorDBBench** (Zilliz, 2025) | 50M 벡터: pgvectorscale 471 QPS vs Qdrant 41.47 QPS — **pgvectorscale 10x 빠름** |
| **Qdrant v1.15+** (2025) | 1.5-bit/2-bit 바이너리 양자화, 필터 검색 우수 |
| **Milvus** (35K+ stars) | 수십억 벡터 스케일용 — 에이전트 메모리(<1M)에는 과잉 |

### 판정: **CHANGE (minor)**

- Phase 1: **pgvectorscale** (pgvector 대체, drop-in, 10x 빠름)
- Phase 2: **Qdrant** 유지 (필터 검색, 고급 양자화 필요 시)
- Milvus/Weaviate/Chroma: 불필요

---

## 3. 시계열 DB

### 현재 설계
TimescaleDB (PG 확장, Gorilla 압축)

### 논문/벤치마크 근거

| 출처 | 발견 |
|------|------|
| **QuestDB 벤치마크** (2025) | TimescaleDB 대비 6-13x 빠른 입수, 16-20x 빠른 분석 쿼리 |
| **One Trading** (2025) | QuestDB를 저지연 트레이딩에 채택 |
| **TimescaleDB 2.25** (Jan 2026) | ColumnarIndexScan으로 압축 chunk 집계 가속 — 격차 축소 |

### 판정: **KEEP**

- Phase 1: TimescaleDB (PG 내 실행, 추가 인프라 불필요, 시뮬레이션에 충분)
- Phase 3: 실시간 틱 데이터/대규모 백테스팅 시 QuestDB 추가 검토
- KDB+: 금표준이나 프로프라이어터리/고비용 → 제외

---

## 4. AI 친화적 데이터 포맷

### 현재 설계
TOON (테이블) + Markdown-KV (단일 레코드) + YAML (중첩) + NumeroLogic (수치)

### 논문 근거

| 출처 | 발견 |
|------|------|
| **TOON** (2025) | GPT-5 Nano: 99.4% 정확도, 46% 토큰 절감. 15+ 언어 구현 |
| **NumeroLogic** (EMNLP 2024, IBM) | 덧셈 88.37% → 99.96%, 곱셈 13.81% → 28.94%. 피어리뷰 통과 |
| **Nested Data Format Study** (2025) | YAML: LLM 중첩 구조 이해 최고 (62.1%) |
| **Token-Efficient Data Prep** (The New Stack, 2025) | 하이브리드 포맷 접근 (데이터 형태별 다른 포맷) 검증 |

### 판정: **KEEP — State of the art**

TOON + YAML + Markdown-KV + NumeroLogic 조합은 2025 최신 연구가 추천하는 정확한 조합. 이를 대체할 새 포맷 미출현.

---

## 5. 에이전트 메모리 아키텍처

### 현재 설계
A-MEM (Zettelkasten) + Mem0 (통합 레이어) + REMEMBERER (Q-value decay), 4계층 (Working/Episodic/Semantic/Procedural)

### 논문 근거

| 출처 | 발견 |
|------|------|
| **A-MEM** (NeurIPS 2025) | 6개 기반 모델에서 모든 SOTA 베이스라인 초과 |
| **REMEMBERER** (2025) | 미세조정 없이 성공/실패 학습. Q-value 기반 유지 — 거래 결과에 적합 |
| **Mem0** ($24M 투자, 2025) | 26% 높은 정확도, 91% 낮은 지연, 90% 토큰 절감. Netflix, Rocket Money 채택 |
| **Memory in AI Agents** (arXiv Dec 2025) | Working/Episodic/Semantic/Procedural 4계층이 **합의된 아키텍처** |
| **SimpleMem** (arXiv Jan 2026) | 3단계 파이프라인 제안 — 너무 최신, 향후 모니터링 |

### 판정: **KEEP — 최선의 조합**

4계층 메모리 아키텍처는 2025년 12월 서베이 논문에서 합의된 구조. A-MEM + REMEMBERER + Mem0 조합이 모든 요구를 커버.

---

## 6. 그래프 DB

### 현재 설계
없음. 관계형 테이블 (roles.report_to, memories.links UUID 배열)

### 논문 근거

| 출처 | 발견 |
|------|------|
| **A-MEM 논문** | "현재 메모리 시스템은 기본 저장/검색은 가능하나, 그래프 DB 통합 시도에도 불구하고 정교한 메모리 조직이 부족" |
| **Mem0 on AWS** (2025) | Amazon Neptune (그래프 DB) + ElastiCache + 벡터 검색 조합 — 그래프 저장이 가치를 더함을 검증 |
| **Apache AGE vs Neo4j** | AGE: PG 확장으로 Cypher 지원, 추가 인프라 불필요. Neo4j: 별도 서버 필요 |

### 판정: **CHANGE — Phase 2에 Apache AGE 추가**

현재 `memories.links` (UUID 배열)은 1-hop 쿼리만 효율적. 멀티-hop 탐색 불가:
- "이 경험에서 3-hop 내 연결된 모든 메모리 찾기"
- "이 애널리스트 위 보고 체인의 모든 에이전트 찾기"

**Apache AGE** (PG 확장):
- PG 내에서 Cypher 그래프 쿼리 지원
- 관계형 테이블과 그래프 데이터를 단일 SQL로 결합 쿼리
- A-MEM Zettelkasten 링크가 자연스러운 그래프 구조
- Neo4j는 별도 인프라 오버헤드 → 제외

---

## 7. 직렬화 (에이전트 통신)

### 현재 설계
MessagePack (기본) / C2C KV-cache (확장), LACP 프로토콜

### 벤치마크 근거

| 출처 | 발견 |
|------|------|
| **Binary Serialization Benchmarks** (Feb 2026) | MessagePack: 직렬화 속도 1위. FlatBuffers: 역직렬화 1위 (81ns/op) |
| **CBOR** (RFC 8949) | MessagePack 확장판이나 ~2x 느림 |
| **MCP** (Anthropic, 2025) | 외부 도구 통신에 JSON-RPC 사용 — 내부 에이전트 통신은 바이너리가 적합 |

### 판정: **KEEP**

MessagePack = 스키마프리 중 최고 직렬화 속도 + 30% 작은 페이로드. CBOR은 레터럴 무브, Protobuf은 스키마 정의 필요로 유연성 감소.

---

## 8. 임베딩 저장 최적화

### 현재 설계
text-embedding-3-large (1024D), float8, SQ int8 + oversampling, HNSW M=16~32

### 논문 근거

| 출처 | 발견 |
|------|------|
| **Embedding Storage Optimization** (arXiv 2505.00105, 2025) | float8: 4x 압축, <0.3% 성능 손실. float8 + PCA 조합 시 8x 압축 |
| **Binary/Scalar Quantization** (Hugging Face, 2025) | 바이너리 양자화: 32x 압축, 95%+ 정확도 — 1차 필터 + 리스코어링 용 |
| **4-bit Quantization for RAG** (arXiv Jan 2025) | 4-bit: float32 수준 품질, 8x 압축 → float8은 보수적이고 안전한 선택 |
| **SMEC** (arXiv 2025) | Matryoshka 1024D → 256D 정보 손실 완화 — 이미 문서에 반영됨 |

### 판정: **KEEP**

float8 + SQ int8 + HNSW 조합이 2025 연구 권장과 정확히 일치. 변경 불필요.

---

## 적용된 변경사항

### 변경 1: pgvector → pgvectorscale

| 항목 | 이전 | 이후 |
|------|------|------|
| Phase 1 벡터 DB | pgvector | **pgvectorscale** (PG 확장) |
| 근거 | — | VectorDBBench 2025: 10x 빠른 QPS |
| 코드 변경 | `pgvector` 패키지 | `pgvectorscale` (drop-in 호환) |

### 변경 2: Apache AGE 추가 (Phase 2)

| 항목 | 이전 | 이후 |
|------|------|------|
| 그래프 쿼리 | 없음 (UUID 배열) | **Apache AGE** (PG 확장, Cypher) |
| 근거 | — | A-MEM 논문 + Mem0 AWS 아키텍처 검증 |
| 적용 시점 | — | Phase 2 (멀티-hop 메모리 탐색 필요 시) |

---

## 참고 논문/출처 목록

| 출처 | 연도 | 검증 항목 |
|------|------|----------|
| Agentic Postgres (Tiger Data) | 2025 | Multi-DB, pgvectorscale |
| Scaling Agent Systems (arXiv 2512.08296) | 2025 | Multi-DB 아키텍처 |
| Agentic AI Survey (arXiv 2510.25445) | 2025 | 크로스 에이전트 컨텍스트 |
| VectorDBBench (Zilliz) | 2025 | pgvectorscale vs Qdrant |
| QuestDB 벤치마크 | 2025 | TimescaleDB 비교 |
| TOON (TensorLake) | 2025 | 토큰 최적화 포맷 |
| NumeroLogic (EMNLP 2024, IBM) | 2024 | 수치 표현 |
| Nested Data Format Study | 2025 | YAML 정확도 |
| A-MEM (NeurIPS 2025) | 2025 | Zettelkasten 메모리 |
| REMEMBERER | 2025 | Q-value 경험 유지 |
| Mem0 | 2025 | 통합 메모리 레이어 |
| Memory in AI Agents (arXiv Dec 2025) | 2025 | 4계층 메모리 합의 |
| SimpleMem (arXiv Jan 2026) | 2026 | 향후 참고 |
| Embedding Storage Optimization (arXiv) | 2025 | float8 검증 |
| 4-bit Quantization for RAG (arXiv) | 2025 | 양자화 검증 |
| Binary Serialization Benchmarks | 2026 | MessagePack 성능 |
| Apache AGE vs Neo4j | 2025 | 그래프 DB 비교 |
| Mem0 on AWS (Neptune) | 2025 | 그래프 메모리 검증 |
