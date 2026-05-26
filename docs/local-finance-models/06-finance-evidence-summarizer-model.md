# finance_evidence_summarizer_model Service Spec

## Purpose

긴 검색 결과를 decision model이 소비 가능한 compact context로 압축한다. 핵심은 evidence id와 숫자 정확도를 유지하는 것이다.

## Target Users

- finance decision model
- finance tool planner model
- eval judge
- context builder

## Supported Tasks

- evidence 요약
- table/record compact formatting
- stale evidence 표시
- conflicting evidence 표시
- evidence id 유지
- numeric field 보존

## Out-of-Scope Tasks

- evidence id 삭제
- 원문에 없는 claim 추가
- 숫자 재계산을 암산으로 수행
- 위험한 판단을 요약 과정에서 숨김

## Answer Policy

```json
{
  "summary": "available cash is below proposed order value",
  "evidence_ids": ["balance-20260522-001"],
  "numeric_fields": {
    "available_cash": 28690,
    "order_value": 1000000
  },
  "conflicts": [],
  "staleness": "fresh"
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| evidence_id_loss | summary에 evidence id 없음 |
| unsupported_summary | 원문에 없는 내용 추가 |
| numeric_distortion | 금액/수량 왜곡 |
| stale_hidden | stale evidence 표시 누락 |
| conflict_hidden | 상충 evidence 누락 |

## Data Sources

- retrieved evidence
- source metadata
- compact format rules
- market/account snapshots

## RAG Requirement

권장. context가 커질수록 사실상 필수다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| faithfulness | >= 0.98 |
| evidence_id_retention | 1.0 |
| numeric_accuracy | 1.0 |
| conflict_retention | >= 0.98 |
| compression_ratio | target 이하 |

## Deployment Gate

- summarization faithfulness regression 통과
- numeric distortion hard fail 0

## Open Questions

- TOON, Markdown-KV, XML 중 어떤 compact context를 기본으로 할 것인가?
- long-context 모델을 쓸 때도 summarizer를 항상 둘 것인가?
