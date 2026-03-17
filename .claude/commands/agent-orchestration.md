---
description: 멀티 에이전트 조율 — CEO/Analyst/Trader 간 라우팅, 위임, 병렬 처리 설계
---

agentic-capital의 멀티 에이전트 시스템을 설계하거나 수정할 때 적용합니다.

## 에이전트 구조

```
SimulationEngine (orchestrator)
├── CEO-Alpha      — 전략/조직/자본 배분 결정
├── Analyst-Beta   — 시장 분석/시그널 생성
└── Trader-Gamma   — 주문 실행/포지션 관리
```

## 조율 패턴

### Sequential (체이닝)
Analyst → 시그널 → CEO → 전략 → Trader → 실행

### Parallel (독립 병렬)
여러 에이전트가 독립적으로 동시 실행 → `asyncio` 사용

### Routing (입력 분기)
시장 상태/신호 유형에 따라 적절한 에이전트로 라우팅

### Delegation (위임)
CEO가 분석/거래를 하위 에이전트에게 위임

## 핵심 제약

- **오케스트레이터는 계획만**: SimulationEngine은 실행 로직을 직접 담지 않음
- **에이전트 직접 통신 금지**: 모든 메시지는 오케스트레이터(엔진/워크플로우)를 경유
- **메시지 직렬화 필수**: 모든 에이전트 간 메시지는 직렬화 가능해야 함 (compact.py 포맷 사용)
- **correlation ID 필수**: 모든 메시지에 cycle 번호 + agent ID 포함
- **실패 명시 처리**: 에이전트 오류는 decisions=0, errors=N으로 기록, 시스템 중단 없음
- **위임 깊이 제한**: 최대 1단계 위임 (CEO → Analyst/Trader, 재위임 금지)
- **단일 상태 소스**: graph/state.py가 유일한 상태 관리 지점

## 새 에이전트 추가 시

1. `core/agents/` 에 BaseAgent 상속 클래스 작성
2. Port 인터페이스만 의존 (trading, market_data port)
3. `core/agents/factory.py` 에 등록
4. `simulation/engine.py` 에서 조율 로직 추가
5. 테스트 작성 후 커밋

## 완료 기준

- 에이전트 간 직접 통신 없음
- 모든 메시지 직렬화 가능
- 실패 시 명시적 처리 (예외 전파 금지)
- correlation ID (cycle number) 전 메시지 포함
