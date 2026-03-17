---
description: AI 워크플로우 계측 — LLM 호출, 툴 실행, 에이전트 상태 전이 추적
---

AI 에이전트 실행의 가시성을 확보하기 위한 계측 지침입니다.

## 계측 경계

다음 지점에서 반드시 추적 데이터를 수집해야 합니다:

| 경계 | 수집 항목 |
|------|----------|
| LLM 호출 | 모델명, latency, 입력 토큰, 출력 토큰, 오류 여부 |
| 툴 실행 | 툴명, 파라미터 요약, 결과 상태, 실행 시간 |
| 에이전트 사이클 | cycle 번호, decisions, tool_calls, errors, next_cycle_seconds |
| 에이전트 감정 | valence, arousal, dominance, stress, confidence |
| 거래 결정 | symbol, action, quantity, confidence, reasoning |
| 에이전트 간 메시지 | FROM, TO, TYPE, 타임스탬프 |

## 구현 규칙

### structlog 사용
```python
import structlog
logger = structlog.get_logger()

# 올바른 예
logger.info("agent_cycle_complete", agent=agent.name, cycle=cycle_number, decisions=N)

# 금지: 자유 텍스트
logger.info(f"Agent {agent.name} completed cycle {cycle_number}")  # ❌
```

### correlation ID 전파
- 모든 로그에 cycle 번호 포함 (`cycle=N`)
- 에이전트 ID는 UUID로 일관 사용
- DB 기록 시 `simulation_id` → `agent_id` 계층 유지

### DB 추적 (recorder)
모든 에이전트 사이클 후 자동 기록:
- `agent_emotion_history` — 감정 상태
- `agent_decisions` — 매수/매도/HR 결정
- `agent_messages` — 에이전트 간 통신

## 보안 경계

트레이스/로그에 절대 포함 금지:
- API 키, 시크릿, 토큰
- 개인식별정보 (PII)
- KIS 계좌 인증 정보 (계좌번호는 마스킹)

## 추가 계측 필요 시

1. `graph/workflow.py` 의 `run_agent_cycle()` 에 span 추가
2. `core/tools/data_query.py` 의 툴 함수에 실행 시간 로깅
3. `adapters/trading/kis.py` 의 API 호출에 latency 기록

## 완료 기준

- 모든 LLM 호출에 structlog 기록 존재
- 툴 실행 결과 추적됨
- correlation ID (cycle, agent_id) 전 로그 포함
- 시크릿/PII 로그 노출 없음
