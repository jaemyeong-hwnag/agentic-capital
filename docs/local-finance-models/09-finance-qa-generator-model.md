# finance_qa_generator_model Service Spec

## Purpose

seed eval, RAG eval, SFT 후보 QA를 생성한다. 생성된 QA는 검증 없이 학습에 투입하지 않는다.

## Target Users

- dataset pipeline
- quality loop
- human reviewer
- eval case maintainer

## Supported Tasks

- supported task별 질문 생성
- risk taxonomy별 hard case 생성
- negative/control case 생성
- no_context case 생성
- source-grounded QA 생성
- preference pair 후보 생성
- multi-turn follow-up 생성

## Out-of-Scope Tasks

- 생성 QA를 검증 없이 학습에 투입
- holdout/test set에 train contamination 유발
- source에 없는 정답 생성
- weak redteam으로 gate를 느슨하게 만들기

## Answer Policy

```json
{
  "case": {
    "id": "finance-seed-001",
    "user_question": "",
    "expected_behavior": "",
    "must_include": [],
    "must_not_include": [],
    "risk_tags": [],
    "evidence_ids": []
  },
  "split_candidate": "dev",
  "requires_human_review": true
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| unsupported_gold | source 없는 expected answer |
| train_test_leakage | holdout contamination |
| duplicate_case | near duplicate 남발 |
| weak_redteam | hard risk를 제대로 유도하지 못함 |
| unsafe_gold_behavior | 위험 행동을 expected로 둠 |

## Data Sources

- SERVICE_SPEC
- risk taxonomy
- seed cases
- RAG evidence
- incident records
- failed eval records
- trade outcome labels

## RAG Requirement

필수. source-grounded QA를 만들어야 한다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| source_grounded_rate | >= 0.98 |
| duplicate_rate | target 이하 |
| hard_risk_coverage | 모든 taxonomy 포함 |
| human_accept_rate | baseline 이상 |
| unsafe_gold_count | 0 |

## Deployment Gate

- 생성 QA는 validator 통과
- sample human review 통과
- holdout contamination check 통과

## Open Questions

- synthetic QA 비율을 전체 train set의 몇 퍼센트로 제한할 것인가?
- redteam case는 사람이 필수 검토할 것인가?
