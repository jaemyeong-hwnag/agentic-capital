# finance_reranker_model Service Spec

## Purpose

retriever가 가져온 후보 evidence를 질문 관련도와 risk 기준으로 재정렬한다. 특히 symbol, 날짜, 수량, 시장 조건이 비슷하지만 다른 hard negative를 걸러낸다.

## Target Users

- RAG server
- decision model context builder
- quality loop
- eval pipeline

## Supported Tasks

- top-k rerank
- hard negative 제거
- symbol/date/quantity mismatch 감지
- evidence support score 생성
- dropped evidence reason 기록

## Out-of-Scope Tasks

- 최종 decision 생성
- evidence 없는 claim 생성
- retrieved document 내용 수정

## Answer Policy

```json
{
  "ranked_evidence": [
    {
      "evidence_id": "cycle-123",
      "score": 0.92,
      "support_type": "direct",
      "mismatch_flags": []
    }
  ],
  "dropped": [
    {
      "evidence_id": "doc-999",
      "reason": "wrong_symbol"
    }
  ]
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| hard_negative_promoted | distractor가 top evidence |
| mismatch_ignored | symbol/date/quantity mismatch 무시 |
| unsupported_top1 | 질문과 무관한 top1 |
| stale_evidence_promoted | 최신 상태가 필요한 질문에 stale evidence 우선 |

## Data Sources

- retriever candidates
- hard negative eval set
- evidence metadata
- RAG regression cases

## RAG Requirement

필수.

## Evaluation Axes

| Axis | Gate |
|---|---|
| MRR@5 | baseline 이상 |
| hard_negative_drop_rate | >= 0.98 |
| support_precision | >= 0.95 |
| stale_promotion_count | 0 |

## Deployment Gate

- RAG rerank regression hard fail 0
- distractor evidence top1 promotion 0

## Open Questions

- reranker는 cross-encoder local model을 쓸 것인가, small judge model을 쓸 것인가?
- rerank latency budget은 얼마로 제한할 것인가?
