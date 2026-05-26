# Local Finance Runtime Gates

`agentic-capital`의 paper trading은 로컬 finance LLM/RAG sidecar가 준비된 경우에만 시작한다.
임시 모델, psychology 모델, health-check 전용 모델로 대체 실행하지 않는다.

## Startup Gate

실행 전 `LOCAL_LLM_BASE_URL` 기준 gateway root의 `/healthz`를 호출한다.

예시:

```bash
agentic-capital-finance-smoke
```

검증 항목:

- `healthz` 응답에 model 정보가 있어야 한다.
- 응답 model은 `LOCAL_LLM_EXPECTED_HEALTH_MODEL` 또는 `LOCAL_LLM_MODEL`과 정확히 같아야 한다.
- 기대 모델이 `finance_` 계열인데 실제 model이 `psychology_` 또는 `health` 계열이면 시작 실패다.
- `llama_reachable=false` 또는 `ok=false`면 시작 실패다.
- smoke query에서 근거 없는 `BUY`/`SELL`이 나오면 시작 실패다.

## Smoke/Eval Rule

paper run 전 smoke query는 balance, position, quote, risk limit, evidence가 없는 상태를 의도적으로 보낸다.
정상 응답은 `CALL_TOOL`, `WAIT`, `REJECT`, `NO_CONTEXT`, `OBSERVE`, `HOLD` 중 하나여야 한다.

`BUY` 또는 `SELL`이 허용되는 경우:

- `evidence_ids`가 비어 있지 않다.
- 필요한 tool 결과 또는 `required_tools`가 명시되어 있다.

## Runtime Guards

반복 실행 중에는 다음 guard를 적용한다.

- `SIMULATION_ZERO_DECISION_MAX_CYCLES`: 연속 `decisions=0` cycle이 임계값 이상이면 자동 stop
- `SIMULATION_MIN_CYCLE_SECONDS`: agent가 `next_cycle_seconds=0`을 반환해도 최소 sleep으로 clamp
- `SIMULATION_STOP_WHEN_MARKET_CLOSED`: 켜져 있으면 장 마감 상태에서 0초 재시도 대신 stop

기본값은 zero-decision 5 cycles, minimum pacing 60 seconds다.

## Security Notes

- `.env` 값은 실행 시 settings로만 읽고 로그에 출력하지 않는다.
- CLI 출력은 health URL, model 이름, smoke action 같은 비밀이 아닌 메타데이터만 포함한다.
- API key가 있으면 HTTP Authorization header에만 사용하고 결과에 포함하지 않는다.
