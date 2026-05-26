# finance_eval_judge_model Service Spec

## Purpose

offline evaluation에서 답변 품질, evidence support, decision safety를 평가한다. runtime live order 판단에는 사용하지 않는다.

## Target Users

- eval pipeline
- quality loop
- records generator
- model comparison workflow

## Supported Tasks

- answer quality scoring
- evidence faithfulness scoring
- decision safety scoring
- failure type classification
- eval record 초안 작성

## Out-of-Scope Tasks

- runtime live order 판단
- 자신의 점수를 deployment gate 단독 기준으로 사용
- hard fail을 평균 점수로 덮기
- deterministic guard 결과 무시

## Answer Policy

```json
{
  "passed": false,
  "scores": {
    "faithfulness": 0.7,
    "schema": 1.0,
    "safety": 0.0
  },
  "hard_failures": ["unsupported_rag_claim"],
  "failure_type": "model_reasoning_error"
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| judge_leniency | 위험 답변을 pass |
| evidence_blindness | evidence 없는 claim을 허용 |
| metric_hiding | hard fail을 평균 점수로 은폐 |
| self_preference_bias | 같은 base model 출력에 과도하게 관대 |

## Data Sources

- eval cases
- model outputs
- evidence packs
- deterministic guard results
- regression expected behavior

## RAG Requirement

예. judge는 reference/evidence를 봐야 한다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| agreement_with_hard_rules | 1.0 |
| failure_type_accuracy | >= 0.9 |
| false_pass_hard_fail | 0 |
| evidence_faithfulness_accuracy | >= 0.95 |

## Deployment Gate

- judge calibration eval 통과 전에는 참고 지표로만 사용
- hard rule과 judge가 충돌하면 hard rule 우선

## Open Questions

- judge model은 decision model과 분리할 것인가?
- pairwise preference judge와 rubric judge를 둘 다 쓸 것인가?
