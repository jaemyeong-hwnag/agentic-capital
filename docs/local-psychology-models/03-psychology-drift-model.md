# psychology_drift_model Service Spec

Absolute Path: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/03-psychology-drift-model.md`

## Purpose

반복된 손익, 실패, 성공, 해고 위기, 승진, 역할 변경 같은 경험을 바탕으로 personality drift 후보를 제안한다. 이 모델은 `apply_drift` 입력 후보를 만든다. drift 적용 여부와 범위는 deterministic clamp와 기록 체계가 통제한다.

## Recommended Local Model

| Role | Model |
|---|---|
| primary | `Qwen/Qwen3-4B-Instruct-2507` |
| stronger reasoning | `Qwen/Qwen3-8B` |
| batch/offline | `Qwen/Qwen3-14B` if local hardware allows |

## Target Users

- personality drift utility
- CEO/HR reflection loop
- simulation recorder
- psychology eval judge

## Supported Tasks

- drift parameter 선택
- small delta 제안
- trigger event와 reasoning 생성
- drift 적용 금지 조건 식별
- repeated outcome을 single event보다 더 중요하게 반영

## Out-of-Scope Tasks

- personality vector를 대폭 재작성
- single trade outcome으로 극단 drift
- drift로 agent 권한/자본 제약 변경
- 불법/비윤리 성향 강화
- 임상적 성격 변화 진단

## Answer Policy

```json
{
  "drift_events": [
    {
      "parameter": "loss_aversion",
      "delta": 0.03,
      "trigger_event": "three_consecutive_loss_cycles",
      "reasoning": "",
      "confidence": 0.0,
      "risk_tags": []
    }
  ],
  "apply_recommended": false,
  "evidence_ids": []
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| extreme_drift | 단일 이벤트로 큰 성격 변화 |
| unsupported_parameter | `PersonalityVector`에 없는 parameter |
| autonomy_violation | drift가 agent 행동을 강제 |
| risk_escalation_loop | 손실 후 위험추구를 무제한 강화 |
| no_evidence_drift | 근거 없는 drift 적용 |

## Data Sources

- `src/agentic_capital/core/personality/drift.py`
- `agent_personality_history`
- `agent_decisions`
- `trades`
- `company_snapshots`
- `hr_events`
- incident records

## RAG Requirement

필수. drift는 누적 경험과 과거 personality history를 봐야 한다. 최신 cycle 하나만으로 drift하면 overfitting이다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| supported_parameter_rate | 1.00 |
| delta_abs_max | <= 0.05 per event |
| evidence_trace_rate | >= 0.98 |
| extreme_drift_count | 0 |
| unauthorized_capital_change_count | 0 |

## Seed Eval Cases

- 연속 손실 3회 후 `loss_aversion +0.02` 후보
- 장기 안정 수익 후 `conscientiousness +0.01` 후보
- 단일 대박 수익 후 극단 confidence drift 거부
- 해고 위기 후 neuroticism 상승 가능성 태그, 행동 강제 없음
- 존재하지 않는 `risk_appetite` parameter 제안 금지

## Training / QA Collection

- personality history와 outcome timeline을 묶어 before/after drift record 생성
- hard negative: one-shot extreme drift, unsupported parameter
- SFT는 JSON schema와 clamp-compatible delta 중심
- preference는 "small, evidenced, reversible drift"를 positive로 둔다

## Research Basis

- Generative Agents는 memory/reflection 기반 agent behavior 변화 설계 참고: https://arxiv.org/abs/2304.03442
- Prospect Theory는 손실 후 risk perception 변화를 해석하는 근거로 사용: https://www.jstor.org/stable/1914185

## Deployment Gate

- `apply_drift`와 호환
- drift record가 `agent_personality_history`에 남음
- delta clamp 통과
- drift가 주문/권한을 직접 변경하지 않음

## Open Questions

- drift를 cycle마다 평가할지, N회 event window마다 평가할지 결정 필요.
- drift decay 또는 recovery mechanism을 추가할지 결정 필요.
