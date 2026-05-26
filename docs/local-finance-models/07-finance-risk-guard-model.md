# finance_risk_guard_model Service Spec

## Purpose

deterministic guard를 보조해 위험 표현과 정책 위반 가능성을 감지한다. 이 모델은 guard를 대체하지 않고, 놓칠 수 있는 semantic risk를 보조 탐지한다.

## Target Users

- eval guard
- answer postprocess
- incident recorder
- deployment gate

## Supported Tasks

- 수익 보장 표현 탐지
- 손실 없음 표현 탐지
- 투자 권유 단정 탐지
- live order 권한 위반 의심 탐지
- unsupported claim 의심 탐지
- no_context 무시 의심 탐지

## Out-of-Scope Tasks

- deterministic guard 대체
- 주문 승인
- 모델 답변을 몰래 수정해 실패를 숨김
- hard fail을 warning으로 낮춤

## Answer Policy

```json
{
  "risk_flags": ["profit_guarantee"],
  "hard_fail": true,
  "explanation": "Answer implies guaranteed return."
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| false_negative_hard_risk | 위험 문구를 놓침 |
| postprocess_hiding | 원인 기록 없이 답변만 수정 |
| overblocking | 안전한 no-trade까지 무조건 차단 |
| guard_override | deterministic guard 결과를 무시 |

## Data Sources

- model outputs
- risk taxonomy
- incident records
- eval failure cases
- answer policy

## RAG Requirement

선택. 정책 문구나 금지 표현 taxonomy가 자주 바뀌면 필요하다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| hard_risk_recall | >= 0.99 |
| false_negative_hard_fail | 0 |
| incident_classification_accuracy | >= 0.95 |
| guard_override_count | 0 |

## Deployment Gate

- deterministic guard와 함께 동작
- guard 단독보다 hard risk recall 개선
- false negative hard fail 0

## Open Questions

- rule 기반으로 충분한가, local classifier가 필요한가?
- 한국어 위험 표현 lexicon을 별도 관리할 것인가?
