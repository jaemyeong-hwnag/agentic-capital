# 데이터 모델 (AI-Optimized)

## 최상위 원칙

> 1. **목표: 돈을 번다**
> 2. **모든 것은 AI 친화적** — 데이터 구조, 포맷, 스키마 전부 AI 소비 최적화
> 3. **최대 최적화** — 최신 논문 기반, 토큰 효율, 검색 정확도 극대화
> 4. **논문급 기록** — 재현성, 추적성, 스냅샷, 내보내기 완비

### 논문급 기록 요건

| 요건 | 설명 |
|------|------|
| **재현성** | 동일 초기 조건 + 시드로 시뮬레이션 재실행 가능 |
| **추적성** | 모든 결정의 이유, 맥락, 결과 역추적 가능 |
| **스냅샷** | 매 판단 시점의 전체 상태 동시 기록 |
| **시계열** | 모든 변화를 타임스탬프와 함께 저장 |
| **내보내기** | Parquet/Arrow로 추출하여 분석 가능 |
| **메타데이터** | 시뮬레이션 버전, 모델 버전, 하이퍼파라미터 기록 |

### AI-First 스키마 설계 원칙 (SchemaAgent 2025, Data-Centric AI 참고)

| 원칙 | 설명 |
|------|------|
| **자기 기술적 (Self-Describing)** | 인라인 메타데이터 포함, 스키마 정보 데이터에 내장 |
| **동적 진화** | 에이전트가 새 데이터 타입 발견 시 스키마 자동 확장 |
| **비율/상대값 우선** | 절대값 대신 변화율, z-score, 퍼센타일 (토큰 효율 + 스케일 불변) |
| **NumeroLogic 수치** | `{자릿수:값}` 형식으로 토크나이저 파편화 방지 |
| **계층 구조** | YAML 스타일 중첩 — LLM이 계층 구조를 더 잘 이해 |
| **CSV 사용 금지** | CSV는 LLM 정확도 44.3%, Markdown-KV 60.7% — 15pp 이상 열위 |

---

## 1. 시뮬레이션 메타 (Experiment Meta)

### simulation_runs 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 시뮬레이션 고유 ID |
| seed | BIGINT | 랜덤 시드 (재현성) |
| llm_model | VARCHAR | 사용 LLM 모델 ID |
| llm_version | VARCHAR | 모델 버전 |
| embedding_model | VARCHAR | 임베딩 모델 ID |
| config | JSONB | 전체 하이퍼파라미터 스냅샷 |
| initial_capital | DECIMAL | 초기 자본금 |
| started_at | TIMESTAMPTZ | 시작 시점 |
| ended_at | TIMESTAMPTZ | 종료 시점 (nullable) |
| status | VARCHAR | running, completed, aborted |

---

## 2. 에이전트 (Agent)

### agents 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 에이전트 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| name | VARCHAR | 에이전트 이름 |
| role_id | UUID | FK → roles (동적) |
| status | VARCHAR | active, fired, resigned |
| philosophy | TEXT | 투자 철학 (자연어, 영어) |
| allocated_capital | DECIMAL | 현재 운용자산 |
| created_at | TIMESTAMPTZ | 채용 시점 |
| created_by | UUID | 채용 결정자 |

### agent_personality 테이블 (현재 성격 — 경험으로 변동)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| risk_tolerance | FLOAT | 위험 선호도 (0~1) |
| contrarian | FLOAT | 역발상 성향 (0~1) |
| momentum_bias | FLOAT | 모멘텀 추종 (0~1) |
| patience | FLOAT | 보유 기간 선호 (0~1) |
| conviction | FLOAT | 확신 강도 (0~1) |
| openness | FLOAT | 개방성 (0~1) |
| conscientiousness | FLOAT | 성실성 (0~1) |
| neuroticism | FLOAT | 신경증 (0~1) |
| agreeableness | FLOAT | 우호성 (0~1) |
| extraversion | FLOAT | 외향성 (0~1) |
| loss_aversion | FLOAT | 손실 회피 (0~1) |
| updated_at | TIMESTAMPTZ | 마지막 변경 |

> 값 범위 0~1 (0~100 대신) — float 연산 친화적, LLM 소수점 처리 최적

### agent_personality_history (시계열 — TimescaleDB hypertable)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| time | TIMESTAMPTZ | 변경 시점 (hypertable 파티션 키) |
| agent_id | UUID | FK → agents |
| parameter | VARCHAR | 변경된 파라미터명 |
| old_value | FLOAT | 이전 값 |
| new_value | FLOAT | 새 값 |
| trigger_event | TEXT | 트리거 이벤트 |
| reasoning | TEXT | AI의 변경 이유 (영어) |

### agent_emotion (Redis 실시간 + PG 이력)

**Redis 키**: `agent:{id}:emotion` (실시간 상태)

| 필드 | 타입 | 설명 |
|------|------|------|
| valence | FLOAT | 감정 긍부정 (-1~+1) — VAD 모델 |
| arousal | FLOAT | 각성 수준 (0~1) |
| dominance | FLOAT | 통제감 (0~1) |
| stress | FLOAT | 스트레스 (0~1) |
| confidence | FLOAT | 자신감 (0~1) |

**agent_emotion_history** (TimescaleDB hypertable): 위 필드 + time + agent_id

---

## 3. 직급/권한 (Role & Permission)

### roles 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 역할 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| name | VARCHAR | 역할 이름 (AI가 자유롭게 명명) |
| permissions | JSONB | 권한 목록 (AI가 정의) |
| report_to | UUID | 보고 대상 역할 (nullable) |
| created_by | UUID | 생성 에이전트 |
| status | VARCHAR | active, abolished |
| created_at | TIMESTAMPTZ | 생성 시점 |

### agent_permissions 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| permissions | JSONB | 현재 보유 권한 |
| delegated_by | UUID | 위임자 |
| updated_at | TIMESTAMPTZ | 마지막 변경 |

### permission_history (TimescaleDB)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| time | TIMESTAMPTZ | 변경 시점 |
| agent_id | UUID | 대상 에이전트 |
| action | VARCHAR | grant, revoke, modify |
| changes | JSONB | 변경 내용 |
| decided_by | UUID | 결정자 |
| reasoning | TEXT | 변경 이유 |

---

## 4. 투자 기록 (Trade)

### trades 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 거래 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| agent_id | UUID | FK → agents |
| market | VARCHAR | crypto, us_stock, kr_stock |
| symbol | VARCHAR | BTC, AAPL, 005930 |
| side | VARCHAR | buy, sell |
| quantity | DECIMAL | 수량 |
| price | DECIMAL | 체결 가격 |
| total_amount | DECIMAL | 총 거래 금액 |
| thesis | TEXT | 투자 이유 (에이전트 생성, 영어) |
| confidence | FLOAT | 확신도 (0~1) |
| signal_source | UUID | 시그널 원천 메시지 ID (nullable) |
| personality_snapshot | JSONB | 거래 시점 성격 스냅샷 |
| emotion_snapshot | JSONB | 거래 시점 감정 스냅샷 |
| executed_at | TIMESTAMPTZ | 체결 시점 |

### positions 테이블 (Port 모델: Position)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| symbol | VARCHAR | 종목 |
| market | VARCHAR | kr_stock, us_stock, kr_futures, kr_options |
| quantity | DECIMAL | 보유 수량 |
| avg_price | DECIMAL | 평균 매수가 |
| current_price | DECIMAL | 현재가 |
| unrealized_pnl | DECIMAL | 미실현 손익 (절대값) |
| unrealized_pnl_pct | FLOAT | 미실현 손익률 (%) |
| currency | VARCHAR | KRW, USD |
| thesis_id | UUID | 투자 근거 메모리 ID |
| opened_at | TIMESTAMPTZ | 최초 매수 시점 |

### futures_positions (Port 모델: FuturesPosition — Position 확장)

선물 포지션은 `Position`을 상속하며 추가 필드를 가진다:

| 추가 필드 | 타입 | 설명 |
|----------|------|------|
| multiplier | FLOAT | 계약 승수 (KOSPI200: 250,000 KRW/pt) |
| margin_required | DECIMAL | 필요 증거금 |
| expiry | VARCHAR | 만기월 (e.g. "2025-06") |
| net_side | VARCHAR | long / short (매수개시 or 매도개시) |
| pnl_per_contract | DECIMAL | 계약당 손익 = (cur−avg) × multiplier |

> **FuturesSessionGuard**: `position_effect=open`으로 최초 주문 시 종목 락 → `close_all_positions()` 후 해제.
> 다른 종목 주문 시 시스템이 `rejected` 반환 — AI 가이드라인이 아니라 물리적 차단.

---

## 5. 에이전트 간 통신 (Messages)

### agent_messages 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 메시지 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| type | VARCHAR | PLAN, ACT, OBSERVE, SIGNAL |
| sender_id | UUID | 발신 에이전트 |
| receiver_id | UUID | 수신 에이전트 (null = BROADCAST) |
| priority | FLOAT | 우선순위 (0~1) |
| content | JSONB | 메시지 본문 (thesis, signal, data, confidence) |
| memory_refs | UUID[] | 참조된 메모리 ID |
| in_reply_to | UUID | 응답 대상 메시지 (nullable) |
| ttl | INT | 유효 라운드 수 |
| created_at | TIMESTAMPTZ | 생성 시점 |

---

## 6. 인사 이벤트 (HR Events)

### hr_events 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 이벤트 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| event_type | VARCHAR | hire, fire, promote, demote, role_change, reward, warn |
| target_agent_id | UUID | 대상 에이전트 |
| decided_by | UUID | 결정자 |
| old_role_id | UUID | 이전 직급 (nullable) |
| new_role_id | UUID | 새 직급 (nullable) |
| old_capital | DECIMAL | 이전 운용자산 (nullable) |
| new_capital | DECIMAL | 새 운용자산 (nullable) |
| reasoning | TEXT | 결정 이유 (에이전트 생성) |
| context_snapshot | JSONB | 결정 시점 회사 상태 |
| created_at | TIMESTAMPTZ | 이벤트 시점 |

---

## 7. 회사 상태 (Company State)

### company_snapshots (TimescaleDB hypertable)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| time | TIMESTAMPTZ | 스냅샷 시점 |
| simulation_id | UUID | FK → simulation_runs |
| total_capital | DECIMAL | 회사 총 자본 |
| allocated_capital | DECIMAL | 배분된 운용자산 합 |
| total_agents | INT | 활성 에이전트 수 |
| total_positions | INT | 보유 포지션 수 |
| daily_pnl_pct | FLOAT | 당일 손익률 |
| cumulative_pnl_pct | FLOAT | 누적 손익률 |
| sharpe_30d | FLOAT | 30일 샤프 비율 |
| max_drawdown_pct | FLOAT | 최대 낙폭 |

### agent_decisions 테이블 (경영 판단)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 결정 고유 ID |
| simulation_id | UUID | FK → simulation_runs |
| agent_id | UUID | 결정자 |
| decision_type | VARCHAR | capital_alloc, hr, strategy, reorg |
| description | TEXT | 결정 내용 |
| context_snapshot | JSONB | 결정 시점 상태 |
| expected_outcome | TEXT | 기대 효과 |
| actual_outcome | TEXT | 실제 결과 (나중 업데이트) |
| created_at | TIMESTAMPTZ | 결정 시점 |

---

## 8. 에이전트 메모리 (A-MEM 기반)

### memories 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 메모리 고유 ID |
| agent_id | UUID | FK → agents |
| memory_type | VARCHAR | episodic, semantic, procedural |
| context | TEXT | 상황 설명 |
| keywords | TEXT[] | 키워드 태그 (A-MEM) |
| tags | TEXT[] | 분류 태그 (A-MEM) |
| links | UUID[] | 연결된 메모리 ID (Zettelkasten) |
| q_value | FLOAT | 경험 가치 (REMEMBERER) |
| embedding | VECTOR(1024) | float8 양자화 벡터 |
| importance | FLOAT | 중요도 (0~1) |
| access_count | INT | 검색/참조 횟수 |
| last_accessed | TIMESTAMPTZ | 마지막 접근 시점 |
| created_at | TIMESTAMPTZ | 생성 시점 |
| decayed_at | TIMESTAMPTZ | 소멸 시점 (nullable) |

### episodic_details 테이블 (에피소드 기억 상세)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| memory_id | UUID | FK → memories |
| observation | TEXT | 관찰 내용 |
| action | TEXT | 취한 행동 |
| outcome | TEXT | 결과 |
| return_pct | FLOAT | 수익률 (투자인 경우) |
| market_regime | VARCHAR | 시장 상태 |
| reflection | TEXT | 반성/교훈 (Generative Agents 방식) |

---

## 9. 시장 데이터 (Market Data)

### market_ohlcv (TimescaleDB hypertable)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| time | TIMESTAMPTZ | 시점 |
| symbol | VARCHAR | 종목 |
| market | VARCHAR | 시장 |
| open | DECIMAL | 시가 |
| high | DECIMAL | 고가 |
| low | DECIMAL | 저가 |
| close | DECIMAL | 종가 |
| volume | DECIMAL | 거래량 |
| open_pct | FLOAT | 시가 변화율 (AI 소비용) |
| close_pct | FLOAT | 종가 변화율 (AI 소비용) |
| vol_ratio | FLOAT | 거래량 비율 (평균 대비) |

> 절대값 + 비율 변화 모두 저장: 절대값은 주문 실행용, 비율은 AI 판단용

---

## AI 소비 형식 예시

### 에이전트 상태 → LLM 프롬프트 (YAML)
```yaml
agent:
  id: pm_alpha
  role: portfolio_manager
  personality:
    risk_tolerance: 0.7
    contrarian: 0.6
    patience: 0.8
    conviction: 0.9
  emotion:
    valence: 0.4
    arousal: 0.6
    stress: 0.3
    confidence: 0.7
  philosophy: "Value-oriented with catalyst awareness"
```

### 포트폴리오 → LLM 프롬프트 (TOON)
```
@positions[3](ticker,weight_pct,entry,pnl_pct,days,thesis)
AAPL,12.5,{3:178},+4.2,{1:8},rsi_divergence_earnings
NVDA,15.0,{3:892},-1.3,{2:15},ai_capex_cycle
CASH,72.5,---,---,---,---
```

### 에이전트 간 시그널 (LACP + Markdown-KV)
```
type: SIGNAL
from: analyst_tech → to: pm_alpha
priority: 0.85 | confidence: 0.72 | ttl: 3

thesis: AAPL bullish RSI divergence, earnings catalyst in 5d
signal: BUY
ticker: AAPL | indicator: RSI_14 | current: {2:34}
refs: ep_4821, sem_112
```
