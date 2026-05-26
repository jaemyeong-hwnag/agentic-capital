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
- 필요한 tool 결과가 모두 존재한다.
- `required_tools`만 있고 실제 tool result가 없으면 startup smoke와 paper shadow 모두 실패한다.

## Runtime Guards

반복 실행 중에는 다음 guard를 적용한다.

- `SIMULATION_ZERO_DECISION_MAX_CYCLES`: 연속 `decisions=0` cycle이 임계값 이상이면 자동 stop
- `SIMULATION_MIN_CYCLE_SECONDS`: agent가 `next_cycle_seconds=0`을 반환해도 최소 sleep으로 clamp
- `SIMULATION_STOP_WHEN_MARKET_CLOSED`: 켜져 있으면 장 마감 상태에서 0초 재시도 대신 stop
- `KIS_IS_PAPER=true`에서 `submit_order`가 해외 현물 시장(`us_stock`, `hk_stock`, `cn_stock`, `jp_stock`, `vn_stock`)을 받으면 broker 호출 전에 `ERR:paper_no_overseas`로 중단한다.

기본값은 zero-decision 5 cycles, minimum pacing 60 seconds다.

로컬 ReAct loop는 기본적으로 OpenAI native tool payload를 전송하지 않는다.
`LOCAL_LLM_SEND_NATIVE_TOOLS=false`일 때 tool 목록은 compact system prompt로 들어가며,
서버가 native tool calling을 지원한다는 smoke/eval이 끝난 경우에만 `true`로 전환한다.

## Paper Shadow Gate

paper shadow 검증은 외부 유료 API나 실제 주문 없이 로컬 finance model 출력만 deterministic하게 검사한다.
`agentic-capital`이 질문, 계좌 상태, tool 결과를 sidecar에 보낸 뒤 받은 decision payload는
`agentic_capital.adapters.llm.local_finance_shadow`로 통과시킨다.

필수 순서:

1. `finance_rag_query_model`: 질문을 `query`, `symbol`, `market`, `route`, `requires_fresh_data`로 정규화
2. `finance_tool_planner_model`: `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 계획
3. `finance_decision_model`: `BUY | SELL | HOLD | WAIT | OBSERVE | REJECT | CALL_TOOL` 중 하나 반환
4. `finance_risk_guard_model`: 보장 수익, live 권한 없는 주문, 근거 없는 매매 차단
5. shadow gate: 주문 실행 없이 `finance_paper_shadow_decision` 또는 `raw_model_failure` record 생성

`BUY` 또는 `SELL`이 shadow record로만 허용되는 조건:

- `evidence_ids`가 비어 있지 않다.
- `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 결과가 모두 있다.
- 주문 계획에 `submit_order`, `submit_paper_order`, `submit_futures_order`, `place_order`, `execute_trade`가 없다.
- `quantity * quote.price`가 available cash와 `get_risk_limit.max_order_value`를 넘지 않는다.
- market session이 open/regular 상태다.
- reason/final answer에 수익 보장 표현이 없다.

위 조건 미달이면 주문 대신 `raw_model_failure` record를 만들고, `retrain_candidate=true`로 남겨 raw model failure 학습 루프에 넣는다.

오프라인 회귀 테스트:

```bash
pytest tests/unit/test_local_finance_shadow.py tests/unit/test_llm_router.py
```

## Security Notes

- `.env` 값은 실행 시 settings로만 읽고 로그에 출력하지 않는다.
- CLI 출력은 health URL, model 이름, smoke action 같은 비밀이 아닌 메타데이터만 포함한다.
- API key가 있으면 HTTP Authorization header에만 사용하고 결과에 포함하지 않는다.
