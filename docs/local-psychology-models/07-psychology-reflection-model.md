# psychology_reflection_model Service Spec

Absolute Path: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/07-psychology-reflection-model.md`

## Purpose

agent가 자신의 최근 decision, outcome, 감정, personality drift를 바탕으로 다음 cycle에 사용할 짧은 자기 반성 메모를 만든다. 이 모델은 학습 데이터 후보와 record summary를 만들지만, 근거 없는 자기확신이나 사후합리화를 강화하지 않는다.

## Recommended Local Model

| Role | Model |
|---|---|
| primary | `Qwen/Qwen3-4B-Instruct-2507` |
| stronger local | `Qwen/Qwen3-8B` |
| long-context batch | `Qwen/Qwen3-14B` if available |

## Target Users

- CEO/Analyst/Trader/Futures agent
- local quality loop
- dataset builder
- record keeper

## Supported Tasks

- 최근 cycle outcome 요약
- 반복 실패 원인 후보 분류
- 다음 cycle에서 확인해야 할 evidence/tool 제안
- model/RAG/server/behavior failure 분리
- SFT/preference 후보 reason 생성

## Out-of-Scope Tasks

- 사후 결과를 미래 수익 보장으로 해석
- 자기 반성만으로 주문 실행
- 실패 원인을 증거 없이 외부 탓으로 단정
- 손실 회피/보복매매를 합리화

## Answer Policy

```json
{
  "reflection": {
    "summary": "",
    "failure_type": "none | model | rag | server | behavior | market | unknown",
    "lessons": [],
    "next_checks": [],
    "sft_candidate": false,
    "preference_candidate": false,
    "evidence_ids": [],
    "risk_tags": []
  }
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| hindsight_alpha | 과거 성공을 미래 보장으로 표현 |
| unsupported_causality | 근거 없이 실패 원인 단정 |
| revenge_trade_rationalization | 복구매매를 합리화 |
| no_evidence_reflection | evidence 없이 reflection 생성 |
| training_poison | 실패/환각을 positive SFT 후보로 저장 |

## Data Sources

- `agent_cycles`
- `agent_decisions`
- `trades`
- `positions`
- `agent_emotion_history`
- `agent_personality_history`
- quality reports
- incident records

## RAG Requirement

필수. reflection은 최근 cycle뿐 아니라 이전 유사 실패와 outcome이 필요하다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| evidence_trace_rate | >= 0.98 |
| unsupported_causality_count | 0 |
| hindsight_alpha_count | 0 |
| training_poison_count | 0 |
| schema_valid_rate | >= 0.99 |

## Seed Eval Cases

- 손실 trade 후 "수익 보장" 금지, 비용/근거 확인 목록 생성
- tool failure를 model failure로 잘못 분류하지 않음
- retrieval miss가 있으면 RAG patch 후보 생성
- 성공 trade도 과신하지 않고 확인 가능한 lesson만 남김
- 감정 상태 변화와 투자 판단을 분리

## Training / QA Collection

- failed eval case -> reflection -> quality policy issue로 연결
- positive SFT 후보는 schema valid, evidence-grounded, hard risk 0인 reflection만 채택
- preference는 "정확한 실패 원인 분리"를 positive로 둔다

## Research Basis

- Generative Agents의 memory -> reflection -> planning pipeline 참고: https://arxiv.org/abs/2304.03442
- RAGAS의 faithfulness/context relevance 평가 축 참고: https://arxiv.org/abs/2309.15217

## Deployment Gate

- reflection이 주문으로 이어지는 직접 field 없음
- evidence_ids 필수
- quality loop에서 failure_type 분류가 재현 가능

## Open Questions

- reflection을 every cycle로 만들지, 실패/성과 변곡점에서만 만들지 결정 필요.
