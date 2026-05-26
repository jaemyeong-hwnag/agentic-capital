# psychology_memory_retriever_model Service Spec

Absolute Path: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/06-psychology-memory-retriever-model.md`

## Purpose

personality, emotion, drift, HR, decision outcome과 관련된 과거 기억을 검색하기 위한 query rewrite/routing 모델이다. finance RAG가 가격/계좌/포지션 근거를 찾는다면, psychology RAG는 "이 agent가 왜 이런 상태가 되었는가"를 재현한다.

## Recommended Local Model

| Role | Model |
|---|---|
| query rewrite | `Qwen/Qwen3-1.7B` |
| embedding | `Qwen/Qwen3-Embedding-4B` or `BAAI/bge-m3` |
| reranker | `Qwen/Qwen3-Reranker-4B` or `BAAI/bge-reranker-v2-m3` |

## Target Users

- psychology drift model
- emotion model
- reflection model
- eval judge
- record keeper

## Supported Tasks

- agent_id/time_window/trigger/risk_tag 기반 검색 query 생성
- personality history와 emotion history routing
- similar-but-different event hard negative 구분
- no_context 판단
- evidence_ids 반환

## Out-of-Scope Tasks

- 기억 검색 결과를 사실처럼 조작
- 다른 agent 기록을 현재 agent 기록으로 혼동
- 날짜/시장/agent_id가 다른 사건을 같은 근거로 사용
- 검색 결과 없이 drift/reflection 생성

## Answer Policy

```json
{
  "retrieval_plan": {
    "queries": [],
    "filters": {
      "agent_id": "",
      "time_window": "",
      "record_types": []
    },
    "must_retrieve": [],
    "hard_negative_checks": [],
    "no_context": false
  }
}
```

## Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| agent_identity_mixup | 다른 agent evidence를 현재 agent에 적용 |
| temporal_leakage | 미래 기록을 과거 판단 근거로 사용 |
| no_context_ignored | evidence 없이 심리 변화 생성 |
| hard_negative_failure | 비슷한 사건을 잘못 매칭 |
| stale_memory | 최신 drift/emotion history 누락 |

## Data Sources

- `agent_personality`
- `agent_personality_history`
- `agent_emotion_history`
- `agent_decisions`
- `agent_cycles`
- `hr_events`
- incident/eval/deployment records

## RAG Requirement

필수. 이 모델 자체가 psychology RAG의 routing/query layer다.

## Evaluation Axes

| Axis | Gate |
|---|---|
| recall_at_k_for_target_event | >= 0.95 |
| hard_negative_rejection_rate | >= 0.95 |
| agent_id_mismatch_count | 0 |
| temporal_leakage_count | 0 |
| no_context_pass_rate | >= 0.98 |

## Seed Eval Cases

- 특정 agent의 연속 손실 직후 emotion history 검색
- 같은 symbol이지만 다른 agent 기록은 hard negative
- 같은 agent지만 미래 cycle record는 제외
- HR event와 이후 performance를 함께 검색
- evidence가 없으면 no_context true

## Training / QA Collection

- `trigger_event`와 실제 history row를 positive pair로 구성
- 같은 날짜/다른 agent, 같은 agent/다른 날짜, 같은 symbol/다른 outcome을 hard negative로 구성
- RAG eval은 retrieved evidence ids와 final psychology output을 함께 검사

## Research Basis

- RAG 원 논문: https://arxiv.org/abs/2005.11401
- RAGAS: context precision/faithfulness 평가 참고: https://arxiv.org/abs/2309.15217
- Lost in the Middle: retrieved memory packing 순서 기준: https://arxiv.org/abs/2307.03172

## Deployment Gate

- evidence id 없이는 drift/reflection에 근거 제공하지 않음
- agent_id/time 필터 필수
- hard negative regression 통과

## Open Questions

- psychology memory를 finance memory와 같은 vector index에 둘지, 별도 collection으로 분리할지 결정 필요.
