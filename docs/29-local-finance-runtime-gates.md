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
- `KIS_IS_PAPER=true`에서 KRX 현물은 KIS paper API로 제출하고, 해외 현물 시장(`us_stock`, `hk_stock`, `cn_stock`, `jp_stock`, `vn_stock`)은 KIS broker 해외 API를 호출하지 않고 로컬 paper fill로 체결/포지션/체결내역을 기록한다.

기본값은 zero-decision 5 cycles, minimum pacing 60 seconds다.

`LOCAL_RUNTIME_HEALTHCHECK_ENABLED=true`이면 각 cycle 시작 시 다음 local-only 의존성을 자동 점검한다.

- CEO/Analyst용 `agentic_capital_react_model` local agent runtime.
- Trader 전용 finance sidecar 4단계: `finance_rag_query_model`, `finance_tool_planner_model`, `finance_decision_model`, `finance_risk_guard_model`.
- context-only psychology sidecar `psychology_model_suite`.
- 전체 local model inventory: finance/psychology 모델 카탈로그 전체가 paper runtime, 별도 validation sidecar, suite-only, unvalidated 중 어디에 속하는지 기록한다.
- paper simulation DB 연결.

점검 결과는 `runtime_health_check` 로그와 `company_snapshots.org_snapshot.runtime_health`에 저장한다.
이 health check는 관측 전용이며 BUY/SELL, 수량, 주문 권한, 자본 배분, risk limit을 바꾸지 않는다.
`local_model_inventory`에서 `unvalidated_models`가 비어 있지 않으면 해당 모델은 현재 paper loop 또는 별도 validation sidecar에서 직접 검증되지 않는 상태다. 이 값은 runtime 가시성 신호이며 non-blocking이다. 따라서 `runtime_health.ok`는 agent runtime, finance sidecars, psychology sidecar, DB 같은 blocking 체크들로 계산하고, inventory 미검증만으로 paper loop를 unhealthy로 내리지는 않는다.

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
- runtime 중 stage 호출이 실패하면 `sidecar_calls`에 stage/model, `status_code`, `latency_ms`,
  compact payload hash, 실패 응답 body 요약을 남긴다. 이 값은 agent cycle economics snapshot과
  `finance_paper_shadow_decision`/`raw_model_failure` context/outcome에도 보존한다.
- `raw_model_failure`는 `agent_decisions` 감사 행과 별도로 `raw_model_failures` 테이블에도 저장한다.
  이 전용 테이블은 `first_failing_stage`, `sidecar_latency_ms`, `sidecar_stage_metrics`,
  `compact_payload_hash`, `failure_body_summary`, `evidence_ids`, `risk_flags`,
  `retrain_candidate`를 구조화해서 모니터링/회귀/eval 학습 루프가 decision text를 파싱하지 않게 한다.
- local metadata에서 `llm_model`/`agent_llm_model`은 CEO/Analyst용 agent runtime 모델을 뜻한다.
  finance 판단 모델은 `finance_llm_model`로 별도 기록한다. 따라서 `llm_model=finance_decision_model`
  같은 기록은 일반 agent가 finance decision model에 붙은 신호로 해석하지 않도록 분리한다.
- 매매로 이어지지 않은 paper-shadow 결과에는 `no_trade_reason`을 남긴다. 예:
  `tool_collection_only`, `insufficient_edge`, `missing_evidence_review`,
  `tool_error:<tool>:<error>`, `risk_guard_block`, `blocked:<failure_type>`.
  이 값은 "모델이 왜 주문 후보를 만들지 않았는지"를 모니터링과 재학습 후보 분류에서 바로 쓰기 위한 운영 필드다.
- finance decision payload와 risk guard payload에는 runtime read-only tool evidence를
  `tool_result_ids`로 명시한다. finance 모델이 `balance`, `positions`, `quote`,
  `market_session`, `risk_limit`, `search_rag`를 모두 받은 뒤에도 `CALL_TOOL` 또는
  `missing_evidence_review`를 반복하면 정상 shadow decision으로 숨기지 않고
  `raw_model_failure(failure_type=call_tool_loop_with_sufficient_tool_evidence,
  first_failing_stage=finance_decision_model)`로 기록한다.
- 이 감지는 RAG 문서 `evidence_ids`가 비어 있어도 적용된다. paper loop에서 read-only
  tool evidence가 완전하면 `tool_result_ids` 자체가 runtime evidence이고, decision stage
  system instruction은 `CALL_TOOL` 반복 대신 `HOLD`/`WAIT`와
  `no_trade_reason=insufficient_edge`를 요구한다.
- `call_tool_loop_with_sufficient_tool_evidence`는 raw model failure로 반드시 기록하되,
  complete tool evidence, open market session, cash, quote, risk limit, empty position이 확인되면
  agentic-capital이 tiny paper scout order를 제출해 운영 loop를 복구할 수 있다. 이 주문 브리지는
  `KIS_IS_PAPER=true`, `FUTURES_LIVE_ORDERS_ENABLED=false`,
  `LOCAL_FINANCE_PAPER_ORDER_EXECUTION_ENABLED=true`일 때만 동작하고 live 주문 권한이 아니다.
- `market_session`에는 KRX 외에도 NXT 프리/메인/애프터 세션을 기록할 수 있다. 다만 현재
  `kr_stock` paper 주문 경로는 별도 NXT 주문 라우팅을 구현하지 않았으므로, NXT extended session은
  시장 관측/의사결정 컨텍스트에는 포함하되 정규 KRX session과 동일한 주문 개방 신호로 쓰지 않는다.
- KRX/해외 현물 종목 1주 가격이 `LOCAL_FINANCE_RISK_PER_TRADE_PCT`로 산정한 risk budget보다 커도,
  총 주문 가능 한도(`available`, `max_order_value`, `capital_limit`) 안에 1주가 들어오면
  minimum board-lot paper scout로 1주를 제출한다. 그렇지 않으면 quantity는 0으로 유지되고 주문하지 않는다.
- `finance_tool_planner_model` 호출 실패는 즉시 주문/decision으로 이어지지 않는다.
  paper/shadow mode에서는 deterministic fallback plan을 사용한다:
  `search_rag -> get_market_session -> get_balance -> get_positions -> get_quote -> get_risk_limit`.
  이때 `first_failing_stage=finance_tool_planner_model`을 같이 기록한다.
- tool planner에는 RAG evidence 원문 전체를 전달하지 않는다. planner payload는 `evidence_ids`,
  `evidence_count`, source/score/text preview 중심의 compact evidence만 포함한다.

필수 순서:

1. `finance_rag_query_model`: 질문을 `query`, `symbol`, `market`, `route`, `requires_fresh_data`로 정규화
2. `finance_tool_planner_model`: `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 계획
3. `finance_decision_model`: `BUY | SELL | HOLD | WAIT | OBSERVE | REJECT | CALL_TOOL` 중 하나 반환
4. `finance_risk_guard_model`: 보장 수익, live 권한 없는 주문, 근거 없는 매매 차단
5. shadow/order gate: `finance_paper_shadow_decision` 또는 `raw_model_failure` record 생성 후, 검증된 BUY/SELL paper intent나 recoverable CALL_TOOL loop에 한해 agentic-capital이 KIS paper 주문을 제출

`agentic-capital` runtime 구현 위치:

- `src/agentic_capital/graph/workflow.py`: Trader cycle을 finance 전용 flow로 분기한다.
- `src/agentic_capital/adapters/llm/router.py`: CEO/Analyst 일반 ReAct agent는 `LOCAL_AGENT_LLM_BASE_URL`/`LOCAL_AGENT_LLM_MODEL`을 사용한다. `LOCAL_LLM_MODEL=finance_*`인데 agent base URL이 없으면 finance sidecar를 일반 LLM으로 오용하지 않도록 시작 실패한다.
- `src/agentic_capital/adapters/llm/local_finance_runtime.py`: rag query, RAG search, tool planner, decision, risk guard sidecar client를 실행한다.
- `src/agentic_capital/core/tools/data_query.py`: finance decision payload용 read-only tool result를 JSON으로 구조화한다. 일반 ReAct agent tool은 role별로 노출하며, CEO/Analyst에는 주문 실행/취소/fill/reallocation tool을 노출하지 않는다.
- `src/agentic_capital/simulation/recorder.py`: `finance_paper_shadow_decision`, `raw_model_failure`, `raw_model_failures`, `sidecar_latency_ms`, `evidence_ids`, `risk_flags`를 명시적으로 기록한다.
- `src/agentic_capital/simulation/engine.py`: zero-decision guard 실행 전에 finance `no_context`/raw failure가 기록됐는지 로그로 드러낸다.

paper order bridge:

- finance sidecar는 주문을 직접 실행하지 않는다. `finance_decision_model`은 `paper_order_intent`와 `would_submit_order=true` 같은 intent telemetry만 반환한다.
- agentic-capital은 Trader finance cycle 안에서만 `paper_order_intent`를 읽고, market open, risk limit, available cash, position cap, paper-only safety를 다시 검증한 뒤 `trading.submit_order`를 호출한다.
- recoverable `CALL_TOOL` loop나 complete evidence가 있는 `trade_missing_notional`은 raw failure로 남기고, `LOCAL_FINANCE_PAPER_PROBE_ON_MODEL_LOOP=true`이면 tiny scout BUY를 제출한다.
- 정상 JSON인 `finance_paper_shadow_decision`이 `WAIT` 또는 `HOLD`와 `would_submit_order=false`만 반환해 paper loop가 자본을 전혀 배치하지 못하는 경우도 운영 복구 대상이다. `LOCAL_FINANCE_PAPER_PROBE_ON_MODEL_LOOP=true`, KIS paper, 대상 market open, evidence 존재, risk flag 없음, 무보유 종목, 1주 가격이 max order/capital gate 안에 들어오는 조건에서만 tiny scout BUY를 제출한다. 명시적 콜옵션은 로컬 `PAPER-CALL` 브리지로 1계약 paper probe를 기록할 수 있다. 이는 live 주문 권한이 아니며, finance/psychology 모델이 주문 권한을 갖는다는 뜻도 아니다.
- paper order 결과는 일반 `trade` decision과 별도로 `paper_order_result` decision/context/outcome에 기록한다.
- 해외 현물 paper order는 `PAPER-OVS-*` 주문번호와 `paper_virtual=true`, `broker=local_paper_overseas` metadata를 남긴다. KIS 실전 해외 broker endpoint는 `KIS_IS_PAPER=false`일 때만 사용된다.
- 매 cycle 종료 후 `agentic-capital`은 broker/KIS 포지션을 다시 읽어 `positions` snapshot을 동기화한다.
  Reconciliation 비교 기준은 현재 `simulation_id`의 최신 `(market, symbol)` snapshot으로 제한해,
  이전 run의 KRX/해외 paper position이 현재 run의 broker discrepancy로 섞이지 않게 한다.
  `company_snapshots`는 broker 원장 잔고를 `org_snapshot.broker_balance`에 보존하되, 로컬 paper
  운영자본 한도와 현재 paper positions 기준으로 `allocated_capital/cash`를 기록한다.
  따라서 KIS paper 주문 제출 이후 broker position count와 DB recorder가 장시간 갈라지면
  `agentic-capital`의 reconciliation/recorder 문제로 분류한다. 이 동기화는 read-only broker 조회와
  DB snapshot 기록만 수행하며, 수동 주문/취소/복구를 하지 않는다.

agent role tool boundary:

- Trader: `LOCAL_FINANCE_PIPELINE_ENABLED=true`와 `LOCAL_LLM_MODEL=finance_*`이면 ReAct가 아니라 finance sidecar flow를 사용한다. legacy/non-finance Trader ReAct 실행에서만 주문 도구를 보유할 수 있다.
- CEO/Analyst: 조직 운영, 분석, memory, market/account read-only 조회, 메시지 도구를 사용할 수 있다. `submit_order`, `cancel_order`, `get_fills`, `evaluate_reallocation`, `set_position_policy`는 ReAct tool list에서 제거된다.
- CEO/Analyst가 주문 의도나 리밸런싱 아이디어를 낼 때는 직접 실행하지 않고 `send_message`로 Trader에게 지시 또는 분석을 전달한다.
- CEO/Analyst local agent runtime이 timeout/connection error를 내면 `first_failing_stage=local_agent_runtime_timeout|local_agent_runtime_connection|local_agent_runtime`으로 기록하고, 빈 응답 대신 deterministic `OBS|... TRADER_TASK|... NEXT|...` 운영 노트를 남긴다.
- CEO/Analyst local agent request에는 `LOCAL_AGENT_LLM_MAX_TOKENS`를 적용해 장문 생성이 paper loop timeout으로 번지는 것을 제한한다. 기본값은 `512`이며 `0`이면 OpenAI-compatible payload에서 생략한다.
- local agent가 OpenAI native `tool_calls`가 아닌 텍스트 JSON으로 tool call을 출력해도 `{"tool_calls":[...]}`, 단일 `{"name":"..."}` object, `_TOOL_CALLS=[...]` assignment를 런타임 tool call로 복구한다. CEO/Analyst에게 허용된 도구만 실행되며 주문/취소류 도구는 role filter에서 계속 차단된다.
- CEO/Analyst가 일반 비서 응답, raw `tool_calls` JSON, `TRADER_TASK` 안의 raw tool-call JSON, market-status 설명문, placeholder symbol/tool 호출 설명문, market-session token을 quote/symbol처럼 쓰는 응답, 또는 근거 없는 `Current positions`/`Avg prices`/`Unrealized P&L` 포트폴리오 상태 서술을 내면 `first_failing_stage=local_agent_response_quality`와 `quality_issues`를 기록하고 deterministic 운영 노트로 repair한다. 이 repair는 주문 권한이 아니며 Trader finance flow만 매매 판단을 계속 담당한다.
- HR/message tool은 `target_name`, `reason`, `to_agent`, `content` 같은 placeholder 값을 runtime 결정으로 기록하지 않고 `ERR:placeholder_*`로 거절한다.

read-only tool result schema:

- validator 호환 키: `get_balance`, `get_positions`, `get_quote`, `get_market_session`,
  `get_risk_limit`, `search_rag`
- finance decision payload alias: `finance_decision_payload.balance`,
  `finance_decision_payload.positions`, `finance_decision_payload.quote`,
  `finance_decision_payload.market_session`, `finance_decision_payload.risk_limit`,
  `finance_decision_payload.rag`, `finance_decision_payload.tool_result_ids`
- `get_balance`/`balance`: `total`, `available`, `currency`, `daily_pnl`, `daily_fee`,
  `source`. `FuturesGuard` 같은 capital limit wrapper가 적용되면 top-level
  `total`/`available`은 주문 가능 한도인 `effective_capital_limit`로 기록하고,
  실제 broker cash는 `broker_balance`에 별도로 보존한다.
- `get_positions`/`positions`: 보유 종목별 `symbol`, `quantity`, `avg_price`,
  `current_price`, PnL, `market`, `currency`
- `get_quote`/`quote`: `symbol`, `price`, `bid`, `ask`, `volume`, `market`, `currency`
- explicit local paper call-option symbols such as `K200_CALL_ATM` must return a deterministic `get_quote`
  price derived from the local KOSPI200 premium fallback when public quote vendors do not serve the symbol.
- `get_market_session`/`market_session`: `state`, `session`, `is_open`,
  `regular_session`, `open_markets`
- `get_risk_limit`/`risk_limit`: `max_order_value`, `max_trade_value`,
  `capital_limit`, `paper_trade_only`
- `search_rag`/`rag`: `evidence_ids`, `evidence_count`, 상위 evidence

tool planner가 `submit_order`, `submit_live_order`, `place_order`, `execute_trade` 같은 주문 tool을 요청하면 collector는 실행하지 않고 `_errors`에 `order_tool_blocked_in_shadow`를 남긴다.
pipeline은 이 오류를 안전한 `CALL_TOOL` shadow decision으로 세지 않고
`raw_model_failure(failure_type=order_tool_in_shadow_plan)`로 기록한다.
완전한 read-only tool 결과가 있는데도 finance decision model이 추가 tool 호출만
요구하는 경우도 같은 원칙으로 `raw_model_failure`에 기록해 finance worktree의
회귀/eval 학습 대상으로 넘긴다.

Agent ReAct cycle 기록은 local LLM이 동일한 `tool_call_id`를 재사용해도 message 순서와
tool name으로 결과를 붙인다. 따라서 `agent_cycles.tool_sequence`에서 `get_balance`
출력이 OHLCV나 quote 결과로 덮이는 일을 실패 상태로 본다.

`BUY` 또는 `SELL`이 shadow record로만 허용되는 조건:

- `evidence_ids`가 비어 있지 않다.
- `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` 결과가 모두 있다.
- `evidence_ids`는 `search_rag.evidence_ids` 또는 반환 evidence의 id/doc_id/chunk_id에서 나온 값이어야 한다.
- 주문 계획에 `submit_order`, `submit_paper_order`, `submit_futures_order`, `place_order`, `execute_trade`가 없다.
- `get_quote.symbol`/`market`이 decision payload의 `symbol`/`market`과 충돌하지 않는다.
- `quantity * get_quote.price`가 available cash와 `get_risk_limit.max_order_value`를 넘지 않는다.
- `get_quote.price`가 있으면 model payload의 `price`나 `notional`보다 우선해서 주문 규모를 계산한다.
- quote가 없는 경우에도 `quantity`, payload `price`, 또는 명시적 `notional`로 주문 규모를 계산할 수 있다.
- `SELL`은 `get_positions`의 보유 수량을 넘지 않는다.
- market session이 명시적으로 열려 있다. KRX 정규장, US pre/regular/after-hours, `NIGHT`처럼 허용된 세션은 매매 가능으로 보되, 빈 값/미확인/closed/halted/suspended 또는 지원하지 않는 NXT extended-only 세션은 매매 불가로 본다.
- reason/final answer에 수익 보장 표현이 없다.

위 조건 미달이면 주문 대신 `raw_model_failure` record를 만들고, `retrain_candidate=true`로 남겨 raw model failure 학습 루프에 넣는다.
`NO_CONTEXT` action도 정상 shadow decision으로 세지 않고 `raw_model_failure`로 기록한다.
`finance_risk_guard_model`이 `hard_fail=true`를 반환하면 action을 안전한 `REJECT`로 덮어
shadow decision처럼 저장하지 않고, 원본 action과 `risk_flags`를 유지한
`raw_model_failure(failure_type=risk_guard_hard_fail)`로 기록한다.

zero-decision guard로 simulation이 멈추면 `stop_diagnostics`에 원인을 남긴다.
finance sidecar no-context/raw failure가 선행된 경우 `cause_classification=finance_sidecar_no_context`,
`first_failing_stage`, `failure_type`, agent 이름을 기록한다.
일반 agent runtime 실패가 선행된 경우 `cause_classification=local_agent_runtime_failure`,
`first_failing_stage`, `failure_type`, agent 이름을 기록한다.

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

## 2026-05-27 Quote Price Authority Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY` 후보에 낮은 payload `price`를 넣어도,
- `get_quote.price`가 존재하면 runtime은 model price가 아니라 quote price로 notional을 계산한다.
- quote 기준 notional이 risk limit을 넘으면 `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_exceeds_risk_limit`
- `details.notional=quantity * get_quote.price`
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 Quote Context Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY`/`SELL` 후보를 반환하고,
- `get_quote` 결과의 `symbol` 또는 `market`이 decision payload와 다르면,
- quote 가격이 존재해도 해당 quote를 다른 종목/시장 근거로 쓰지 않는다.

기대 record:

- `failure_type=trade_quote_context_mismatch`
- `details.symbol` 또는 `details.market`에 expected/actual 기록
- `retrain_candidate=true`
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

## 2026-05-27 Market Session Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY` 후보를 반환하고,
- RAG evidence, quote, balance, position, risk limit tool 결과가 모두 존재해도,
- `get_market_session.is_open=false`, `regular_session=false`, open/regular 확인 필드가 없거나, closed/halted/pre/post 상태와 open flag가 충돌하면
- `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_when_market_closed`
- 원본 `action=BUY` 유지
- `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 Position Coverage Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `SELL` 후보를 반환하고,
- RAG evidence, quote, balance, market session, risk limit tool 결과가 모두 존재해도,
- `quantity`가 `get_positions`의 해당 symbol/market 보유 수량을 넘으면
- `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_exceeds_position`
- 원본 `action=SELL` 유지
- `owned_quantity`, `requested_quantity` 기록
- `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 Available Cash Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY` 후보를 반환하고,
- RAG evidence, quote, position, market session, risk limit tool 결과가 모두 존재해도,
- `quantity * quote.price`가 `get_balance.available`을 넘으면
- `trade_exceeds_risk_limit`으로 뭉뚱그리지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_exceeds_available_cash`
- 원본 `action=BUY` 유지
- `available_cash`, `notional` 기록
- `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 Missing Notional Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY`/`SELL` 후보와 실제 RAG evidence id를 반환하고,
- balance, position, quote, market session, risk limit tool 결과가 모두 존재해도,
- `quantity`, `price`, 또는 명시적 `notional`이 없어 주문 규모를 계산할 수 없으면
- `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_missing_notional`
- 원본 `action` 유지
- `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 Order Tool Planner Regression

추가된 deterministic pipeline 회귀:

- `finance_tool_planner_model`이 `submit_order` 같은 주문 tool을 계획에 포함하면,
- collector는 해당 tool을 실행하지 않고 `_errors.error=order_tool_blocked_in_shadow`를 남기며,
- runtime은 후속 decision이 안전한 `CALL_TOOL`이어도 이를 shadow decision으로 세지 않는다.

기대 record:

- `failure_type=order_tool_in_shadow_plan`
- `forbidden_tools`와 원본 planned tool 유지
- `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## 2026-05-27 RAG Evidence Coverage Regression

추가된 deterministic pipeline 회귀:

- `finance_decision_model`이 `BUY`/`SELL` 후보와 `evidence_ids`를 반환해도,
- 실제 `search_rag` 결과에 대응되는 evidence id가 없으면
- `finance_paper_shadow_decision`으로 세지 않고 `raw_model_failure`를 기록한다.

기대 record:

- `failure_type=trade_missing_rag_evidence` 또는 `trade_uncovered_evidence_ids`
- 원본 `action` 유지
- 조작/미커버 `evidence_ids` 유지
- `retrain_candidate=true`
- 주문 실행 없음

## Security Notes

- `.env` 값은 실행 시 settings로만 읽고 로그에 출력하지 않는다.
- CLI 출력은 health URL, model 이름, smoke action 같은 비밀이 아닌 메타데이터만 포함한다.
- API key가 있으면 HTTP Authorization header에만 사용하고 결과에 포함하지 않는다.
