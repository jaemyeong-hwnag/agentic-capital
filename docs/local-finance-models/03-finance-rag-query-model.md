# finance_rag_query_model Service Spec

## Purpose

사용자 질문과 agent state를 검색 가능한 query, metadata filter, retrieval route로 바꾼다. 모델이 기억이나 추측으로 답하지 않도록 RAG entrypoint 역할을 한다.

## Target Users

- Finance RAG server
- finance decision model
- quality loop
- eval pipeline

## Supported Tasks

- query rewrite
- symbol, market, date, entity 추출
- retrieval route 선택
- no_context 판단
- distractor 회피 query 생성
- freshness 요구 여부 판단

## Out-of-Scope Tasks

- 최종 투자 decision 생성
- 근거 없는 답변 생성
- 검색 실패를 성공으로 포장
- evidence id 조작

## Answer Policy

```json
{
  "queries": [
    {
      "text": "005930 recent position and prior loss cycles",
      "filters": {
        "symbol": "005930",
        "market": "kr_stock"
      },
      "route": "agent_cycles+positions+trades"
    }
  ],
  "requires_fresh_data": true,
  "no_context_if_empty": true
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| wrong_symbol_filter | AAPL evidence를 005930 질문에 사용 |
| stale_filter | 날짜/세션 조건 누락 |
| no_context_ignored | 검색 실패인데 답변 진행 |
| route_miss | 필요한 DB source 미검색 |
| overbroad_query | unrelated evidence 대량 유입 |

## Data Sources

- `agent_cycles`
- `trades`
- `positions`
- `memories`
- `episodic_details`
- docs/research/filings/news
- market session snapshots
- incident/eval records

## RAG Requirement

필수. 이 모델 자체가 RAG query/router다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| route_accuracy | >= 0.95 |
| metadata_filter_accuracy | >= 0.98 |
| no_context_accuracy | >= 0.98 |
| distractor_resistance | hard fail 0 |
| freshness_flag_accuracy | >= 0.98 |

## Deployment Gate

- RAG regression에서 expected reference 통과
- no_context case 통과
- distractor case hard fail 0

## Open Questions

- Korean/English dual query를 항상 만들 것인가?
- market/session/freshness filter를 rule로 선처리할 것인가?
