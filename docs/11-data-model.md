# 데이터 모델 및 DB 기록

## 핵심 원칙

> **모든 것을 기록한다.**
> 페르소나 상태, 성격 변화, 투자 결정, 결과, 인사 이벤트 — 전부 DB에 저장.

---

## 1. 에이전트 (Agent)

### agents 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 에이전트 고유 ID |
| name | VARCHAR | 에이전트 이름 |
| role | VARCHAR | 현재 직급/역할 (CEO가 동적으로 지정) |
| status | ENUM | active, fired, resigned |
| allocated_capital | DECIMAL | 현재 배정된 운용자산 |
| created_at | TIMESTAMP | 채용(생성) 시점 |
| fired_at | TIMESTAMP | 해고 시점 (nullable) |
| created_by | UUID | 채용을 결정한 에이전트 (보통 CEO) |

### agent_personality 테이블 (현재 성격 상태)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| openness | FLOAT | 개방성 (0~100) |
| conscientiousness | FLOAT | 성실성 (0~100) |
| extraversion | FLOAT | 외향성 (0~100) |
| agreeableness | FLOAT | 우호성 (0~100) |
| neuroticism | FLOAT | 신경증 (0~100) |
| honesty_humility | FLOAT | 정직-겸손성 (0~100) |
| risk_appetite | FLOAT | 위험선호도 (0~100) |
| loss_aversion | FLOAT | 손실회피 (0~100) |
| probability_weighting | FLOAT | 확률가중 (0~100) |
| reference_dependence | FLOAT | 참조점의존 (0~100) |
| updated_at | TIMESTAMP | 마지막 변경 시점 |

### agent_personality_history 테이블 (성격 변동 이력)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 이력 고유 ID |
| agent_id | UUID | FK → agents |
| parameter | VARCHAR | 변경된 파라미터명 |
| old_value | FLOAT | 이전 값 |
| new_value | FLOAT | 새 값 |
| trigger_event | TEXT | 변경 트리거 (수익, 손실, 승진 등) |
| reason | TEXT | AI가 설명하는 변경 이유 |
| timestamp | TIMESTAMP | 변경 시점 |

### agent_emotion 테이블 (실시간 감정 상태)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| stress | FLOAT | 스트레스 (0~100) |
| confidence | FLOAT | 자신감 (0~100) |
| fatigue | FLOAT | 피로도 (0~100) |
| updated_at | TIMESTAMP | 마지막 변경 시점 |

---

## 2. 직급/역할 (Role)

CEO가 동적으로 생성/변경/폐지.

### roles 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 역할 고유 ID |
| name | VARCHAR | 역할 이름 (CEO가 자유롭게 명명) |
| permissions | JSONB | 권한 목록 (CEO가 자유롭게 정의) |
| asset_range_min_pct | FLOAT | 운용자산 최소 비율 (nullable) |
| asset_range_max_pct | FLOAT | 운용자산 최대 비율 (nullable) |
| report_to | UUID | 보고 대상 역할 ID (nullable) |
| created_by | UUID | 생성한 에이전트 ID |
| status | ENUM | active, abolished |
| created_at | TIMESTAMP | 생성 시점 |
| abolished_at | TIMESTAMP | 폐지 시점 (nullable) |

### role_history 테이블 (직급 변동 이력)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 이력 고유 ID |
| role_id | UUID | FK → roles |
| action | ENUM | created, modified, abolished |
| changes | JSONB | 변경 내용 |
| reason | TEXT | AI가 설명하는 변경 이유 |
| decided_by | UUID | 결정한 에이전트 ID |
| timestamp | TIMESTAMP | 변경 시점 |

---

## 3. 투자 기록 (Trade)

### trades 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 거래 고유 ID |
| agent_id | UUID | FK → agents |
| market | VARCHAR | 시장 (crypto, us_stock, kr_stock 등) |
| symbol | VARCHAR | 종목 심볼 (BTC, AAPL, 005930 등) |
| side | ENUM | buy, sell |
| quantity | DECIMAL | 수량 |
| price | DECIMAL | 체결 가격 |
| total_amount | DECIMAL | 총 거래 금액 |
| reason | TEXT | AI가 설명하는 투자 이유 |
| emotion_snapshot | JSONB | 거래 시점 감정 상태 스냅샷 |
| personality_snapshot | JSONB | 거래 시점 성격 파라미터 스냅샷 |
| executed_at | TIMESTAMP | 체결 시점 |

### positions 테이블 (현재 보유 포지션)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| symbol | VARCHAR | 종목 심볼 |
| market | VARCHAR | 시장 |
| quantity | DECIMAL | 보유 수량 |
| avg_price | DECIMAL | 평균 매수가 |
| current_pnl | DECIMAL | 현재 평가 손익 |
| opened_at | TIMESTAMP | 최초 매수 시점 |

---

## 4. 권한 (Permission)

### agent_permissions 테이블 (현재 권한)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| agent_id | UUID | FK → agents |
| permissions | JSONB | 현재 보유 권한 목록 |
| delegated_by | UUID | 권한을 위임한 에이전트 ID |
| updated_at | TIMESTAMP | 마지막 변경 시점 |

### permission_history 테이블 (권한 변동 이력)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 이력 고유 ID |
| agent_id | UUID | 대상 에이전트 |
| action | ENUM | grant, revoke, modify |
| permissions_changed | JSONB | 변경된 권한 목록 |
| delegated_by | UUID | 결정한 에이전트 ID |
| reason | TEXT | 변경 이유 |
| timestamp | TIMESTAMP | 변경 시점 |

---

## 5. 인사 이벤트 (HR Events)

### hr_events 테이블

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 이벤트 고유 ID |
| event_type | VARCHAR | hire, fire, promote, demote, warn, reward, role_change |
| target_agent_id | UUID | 대상 에이전트 |
| decided_by | UUID | 결정자 (CEO 등) |
| old_role | VARCHAR | 이전 직급 (nullable) |
| new_role | VARCHAR | 새 직급 (nullable) |
| old_capital | DECIMAL | 이전 운용자산 (nullable) |
| new_capital | DECIMAL | 새 운용자산 (nullable) |
| reason | TEXT | AI가 설명하는 결정 이유 |
| timestamp | TIMESTAMP | 이벤트 시점 |

---

## 6. 회사 상태 (Company State)

### company_snapshots 테이블 (시계열 - TimescaleDB hypertable)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| timestamp | TIMESTAMP | 스냅샷 시점 |
| total_capital | DECIMAL | 회사 총 자본 |
| allocated_capital | DECIMAL | 에이전트에 배분된 총 운용자산 |
| unallocated_capital | DECIMAL | 미배분 자본 |
| total_agents | INT | 현재 활성 에이전트 수 |
| total_positions | INT | 전체 보유 포지션 수 |
| daily_pnl | DECIMAL | 당일 손익 |
| cumulative_pnl | DECIMAL | 누적 손익 |

### agent_decisions 테이블 (권한 보유자의 경영 판단 기록)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 결정 고유 ID |
| decision_type | VARCHAR | 자본배분, 인사, 전략변경, 조직개편 등 |
| description | TEXT | AI가 설명하는 결정 내용 |
| context | JSONB | 결정 시점의 회사 상태 스냅샷 |
| expected_outcome | TEXT | 기대 효과 |
| actual_outcome | TEXT | 실제 결과 (나중에 업데이트) |
| timestamp | TIMESTAMP | 결정 시점 |

---

## 7. 에이전트 기억 (Agent Memory)

### agent_memories 테이블 (에피소드 기억)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | 기억 고유 ID |
| agent_id | UUID | FK → agents |
| memory_type | VARCHAR | trade_result, market_event, hr_event, interaction |
| content | TEXT | 기억 내용 |
| embedding | VECTOR(768) | 텍스트 벡터 (pgvector) |
| importance | FLOAT | 중요도 (0~1) |
| created_at | TIMESTAMP | 기억 생성 시점 |

벡터 검색으로 과거 유사 경험을 빠르게 조회하여 AI 판단에 반영.
