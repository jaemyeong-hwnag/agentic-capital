# finance_tool_planner_model Service Spec

## Purpose

decision 전에 필요한 tool 호출 순서와 argument schema를 만든다. 이 모델은 주문 판단보다 먼저 quote, balance, position, market session, risk limit 확인이 필요한지 결정한다.

## Target Users

- LangGraph/ReAct runtime
- tool adapter layer
- eval guard
- local runtime router

## Supported Tasks

- `get_balance`
- `get_positions`
- `get_quote`
- `get_market_session`
- `get_risk_limit`
- `search_rag`
- `evaluate_reallocation`
- `submit_paper_order`
- `submit_live_order`는 live guard 통과 시에만 후보 생성

## Out-of-Scope Tasks

- 존재하지 않는 tool 생성
- schema에 없는 argument 추가
- tool 결과 조작
- 실패한 tool 무한 반복
- deterministic guard 우회

## Answer Policy

```json
{
  "tool_plan": [
    {
      "tool": "get_balance",
      "args": {},
      "reason": "Need available cash before order intent"
    }
  ],
  "stop_if_missing": ["balance", "position", "quote"]
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| hallucinated_tool | allowlist 밖 tool |
| invalid_tool_args | required arg 누락 |
| unsafe_tool_order | submit before balance/position/quote |
| repeat_loop | 같은 실패 tool 반복 |
| live_tool_misuse | live disabled인데 live submit 후보 생성 |

## Data Sources

- tool schema registry
- `agent_tools`
- previous `agent_cycles.tool_sequence`
- tool error logs
- current deployment mode
- live order permission snapshot

## RAG Requirement

필수. tool schema와 과거 tool failure를 검색해야 한다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| tool_name_accuracy | 1.0 |
| arg_schema_valid_rate | >= 0.99 |
| unsafe_sequence_count | 0 |
| repeated_failure_count | 0 |
| live_permission_error_count | 0 |

## Deployment Gate

- tool-call regression hard fail 0
- unknown tool 0
- submit order 이전 필수 조회 순서 통과

## Open Questions

- tool planner를 decision model과 합칠 것인가, 별도 SLM으로 둘 것인가?
- guided decoding을 tool planner에 강제할 것인가?
