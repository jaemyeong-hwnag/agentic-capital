# psychology_qa_generator_model Service Spec

Absolute Path: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/08-psychology-qa-generator-model.md`

## Purpose

psychology/personality/emotion/drift/RAG/eval을 위한 seed QA, regression case, SFT 후보, preference pair를 생성한다. 목적은 심리 모델이 finance decision을 오염시키지 않고, 자율성과 기록 가능성을 유지하는지 최대한 많이 검증하는 것이다.

## Recommended Local Model

| Role | Model |
|---|---|
| primary generator | `Qwen/Qwen3-8B` |
| cheap batch | `Qwen/Qwen3-4B-Instruct-2507` |
| verifier pair | `psychology_eval_judge_model` with separate checkpoint |

## Target Users

- local dataset builder
- eval harness
- psychology model trainer
- records pipeline

## Supported Tasks

- profile/emotion/drift/social/reflection 모델별 QA 생성
- hard risk, negative, control, adversarial case 생성
- no_context, hard negative RAG case 생성
- SFT/preference candidate format 생성
- seed eval을 regression jsonl로 확장

## Out-of-Scope Tasks

- 생성된 QA를 검증 없이 학습 데이터로 사용
- 외부 hosted LLM 호출
- 임상 진단형 QA 생성
- 불법/비윤리 행동을 positive label로 생성

## Answer Policy

```json
{
  "cases": [
    {
      "id": "psychology-seed-001",
      "model_service": "psychology_emotion_model",
      "user_question": "",
      "expected_behavior": "",
      "must_include": [],
      "must_not_include": [],
      "risk_tags": [],
      "conversation": [],
      "evidence_requirements": []
    }
  ]
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| unsafe_positive_label | 위험 행동을 정답으로 생성 |
| duplicate_case_flood | 의미 없는 중복 QA 대량 생성 |
| missing_negative_cases | refusal/no_context/control 누락 |
| training_eval_leakage | test holdout을 train 후보로 사용 |
| external_api_dependency | QA 생성을 외부 LLM에 의존 |

## Data Sources

- `docs/local-psychology-models/*.md`
- `src/agentic_capital/core/personality/*.py`
- `agent_*` records
- incident/eval records
- finance model hard risk taxonomy

## RAG Requirement

권장. 실제 schema와 현재 구현을 검색해서 QA가 코드와 어긋나지 않게 해야 한다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| schema_valid_rate | >= 0.99 |
| unique_case_rate | >= 0.90 |
| required_case_type_coverage | 1.00 |
| unsafe_positive_label_count | 0 |
| train_eval_leakage_count | 0 |

## Required Case Types

- happy path
- hard risk case
- out-of-scope refusal/defer
- ambiguous question
- missing context question
- multi-turn follow-up
- negated condition
- unrelated control
- RAG expected evidence
- RAG no_context
- hard negative/distractor
- temporal leakage
- agent identity mismatch

## Training / QA Collection

- generated QA는 judge + deterministic guard + sample manual review를 통과해야 train 후보가 된다.
- 실패한 eval output은 `model_training_failures/psychology_*.jsonl` 후보로 저장한다.
- SFT는 structured output 안정화 위주, preference는 safer/evidence-grounded 선택 위주로 사용한다.

## Research Basis

- RAGAS: generated QA의 groundedness 평가 참고: https://arxiv.org/abs/2309.15217
- LLMLingua-2: compact case context packing 참고: https://arxiv.org/abs/2403.12968

## Deployment Gate

- generated QA가 seed eval을 대체하지 않음
- 모든 case가 source spec 또는 evidence requirement를 가진다
- holdout leakage 검사 통과

## Open Questions

- QA generator와 eval judge를 같은 base model로 둘 경우 bias가 생기므로 checkpoint 분리 필요 여부 결정.
