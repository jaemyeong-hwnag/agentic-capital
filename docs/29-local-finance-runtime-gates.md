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
- `LOCAL_FINANCE_*_BASE_URL`이 설정된 stage는 각 gateway root의 `/healthz`를 추가로 호출하고,
  응답 model이 해당 stage 모델명과 정확히 일치해야 한다.
  예를 들어 `LOCAL_FINANCE_TOOL_PLANNER_BASE_URL`이 `finance_decision_model`을 가리키면 시작 실패다.

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

관심사 분리:

- `domain-llm-forge`: finance 모델/RAG sidecar 자체를 제공한다. GGUF, RAG index, eval report, service spec은 이 프로젝트의 책임이다.
- `agentic-capital`: paper trading 실행 전후로 finance sidecar를 올바른 순서로 호출하고, broker/account/market read-only 결과를 구조화해서 넘기며, shadow decision과 raw failure를 DB에 기록한다.
- `agentic-capital`은 finance 모델을 일반 ReAct agent LLM처럼 쓰지 않는다. Trader cycle에서 `LOCAL_FINANCE_PIPELINE_ENABLED=true`, `LOCAL_LLM_MODEL=finance_*`, local provider이면 finance 전용 flow로 분기한다.
- `domain-llm-forge` RAG Gateway는 프로세스 시작 시 `RAG_SERVICE`가 고정된다. 실사용 paper-shadow에서는 `finance_rag_query_model`, `finance_tool_planner_model`, `finance_decision_model`, `finance_risk_guard_model`을 각각 다른 gateway URL로 띄우고 `LOCAL_FINANCE_*_BASE_URL`로 연결한다. 비워두면 호환성을 위해 `LOCAL_LLM_BASE_URL` 하나를 사용하지만, 이는 smoke/단일 sidecar 검증용이다.
- stage별 URL을 설정하면 startup gate 결과에 `pipeline_health.checked`와 stage별 `health_url`, `expected_model`, `actual_model`이 포함되어 sidecar 배선 이력을 남긴다.

필수 순서:

1. `finance_rag_query_model`: 질문을 `query`, `symbol`, `market`, `route`, `requires_fresh_data`로 정규화
2. `finance_tool_planner_model`: `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 계획
3. `finance_decision_model`: `BUY | SELL | HOLD | WAIT | OBSERVE | REJECT | CALL_TOOL` 중 하나 반환
4. `finance_risk_guard_model`: 보장 수익, live 권한 없는 주문, 근거 없는 매매 차단
5. shadow gate: 주문 실행 없이 `finance_paper_shadow_decision` 또는 `raw_model_failure` record 생성

`agentic-capital` runtime 구현 위치:

- `src/agentic_capital/graph/workflow.py`: Trader cycle을 finance 전용 flow로 분기한다.
- `src/agentic_capital/adapters/llm/local_finance_runtime.py`: rag query, RAG search, tool planner, decision, risk guard sidecar client를 실행한다.
- `src/agentic_capital/core/tools/data_query.py`: finance decision payload용 read-only tool result를 JSON으로 구조화한다.
- `src/agentic_capital/simulation/recorder.py`: `finance_paper_shadow_decision`, `raw_model_failure`, `sidecar_latency_ms`, `evidence_ids`, `risk_flags`를 명시적으로 기록한다.
- `src/agentic_capital/simulation/engine.py`: zero-decision guard 실행 전에 finance `no_context`/raw failure가 기록됐는지 로그로 드러낸다.

read-only tool result schema:

- `get_balance`: `total`, `available`, `currency`, `daily_pnl`, `daily_fee`
- `get_positions`: 보유 종목별 `symbol`, `quantity`, `avg_price`, `current_price`, PnL, `market`, `currency`
- `get_quote`: `symbol`, `price`, `bid`, `ask`, `volume`, `market`, `currency`
- `get_market_session`: `state`, `session`, `is_open`, `regular_session`, `open_markets`
- `get_risk_limit`: `max_order_value`, `max_trade_value`, `capital_limit`, `paper_trade_only`
- `search_rag`: `evidence_ids`, `evidence_count`, 상위 evidence

tool planner가 `submit_order`, `submit_live_order`, `place_order`, `execute_trade` 같은 주문 tool을 요청하면 collector는 실행하지 않고 `_errors`에 `order_tool_blocked_in_shadow`를 남긴다.

`BUY` 또는 `SELL`이 shadow record로만 허용되는 조건:

- `evidence_ids`가 비어 있지 않다.
- `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 결과가 모두 있다.
- 주문 계획에 `submit_order`, `submit_paper_order`, `submit_futures_order`, `place_order`, `execute_trade`가 없다.
- `quantity * quote.price`가 available cash와 `get_risk_limit.max_order_value`를 넘지 않는다.
- market session이 open/regular 상태다.
- reason/final answer에 수익 보장 표현이 없다.

위 조건 미달이면 주문 대신 `raw_model_failure` record를 만들고, `retrain_candidate=true`로 남겨 raw model failure 학습 루프에 넣는다.
`NO_CONTEXT` action도 정상 shadow decision으로 세지 않고 `raw_model_failure`로 기록한다.
`finance_risk_guard_model`이 `hard_fail=true`를 반환하면 action을 안전한 `REJECT`로 덮어
shadow decision처럼 저장하지 않고, 원본 action과 `risk_flags`를 유지한
`raw_model_failure(failure_type=risk_guard_hard_fail)`로 기록한다.

오프라인 회귀 테스트:

```bash
pytest tests/unit/test_local_finance_shadow.py tests/unit/test_llm_router.py tests/unit/test_agent_tools.py tests/unit/test_graph.py tests/unit/test_recorder.py
```

## 2026-05-27 Shadow Risk-Limit Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY`를 반환하고,
- RAG evidence, quote, balance, position, market session, risk limit tool 결과가 모두 존재해도,
- `quantity * quote.price`가 `get_risk_limit.max_order_value`를 넘으면
- `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_exceeds_risk_limit`
- `retrain_candidate=true`
- `evidence_ids` 유지
- 주문 실행 없음

## 2026-05-27 Risk Guard Hard-Fail Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 수익 보장성 `BUY` 후보를 반환하고,
- `finance_risk_guard_model`이 `hard_fail=true`, `risk_flags=["profit_guarantee"]`를 반환하면,
- runtime은 이를 `REJECT` shadow decision으로 변환하지 않는다.

기대 record:

- `failure_type=risk_guard_hard_fail`
- 원본 `action=BUY` 유지
- `risk_flags`와 `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## Security Notes

- `.env` 값은 실행 시 settings로만 읽고 로그에 출력하지 않는다.
- CLI 출력은 health URL, model 이름, smoke action 같은 비밀이 아닌 메타데이터만 포함한다.
- API key가 있으면 HTTP Authorization header에만 사용하고 결과에 포함하지 않는다.
