# Local Psychology Model Suite

Absolute Path: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/10-psychology-model-suite.md`

## 목적

이 문서는 `Agentic Capital`의 심리/personality 계층을 외부 AI API 없이 로컬 모델만으로 운영하기 위한 모델별 최대 구성 목록이다.

핵심 결론:

```text
finance model suite만으로는 부족하다.
이 프로젝트에는 personality, emotion, drift, social dynamics가 이미 있으므로
psychology model suite도 별도로 필요하다.
단, psychology 모델은 투자 행동을 직접 실행하지 않고 finance/risk 계층에 보조 근거를 제공한다.
```

## Current Code Anchors

| Anchor | Absolute Path |
|---|---|
| personality schema | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/core/personality/models.py` |
| drift utility | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/core/personality/drift.py` |
| emotion utility | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/core/personality/emotion.py` |
| random personality factory | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/core/agents/factory.py` |
| compact prompt encoder | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/formats/compact.py` |
| simulation recorder | `/Users/tpirates/workspace-hjm/agentic-capital/src/agentic_capital/simulation/recorder.py` |

## Model Files

| Model Service | Absolute Path | Recommended Model |
|---|---|---|
| `psychology_profile_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/01-psychology-profile-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_emotion_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/02-psychology-emotion-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_drift_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/03-psychology-drift-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_behavior_bias_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/04-psychology-behavior-bias-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_social_dynamics_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/05-psychology-social-dynamics-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_memory_retriever_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/06-psychology-memory-retriever-model.md` | `Qwen/Qwen3-1.7B` + `Qwen/Qwen3-Embedding-4B` + `Qwen/Qwen3-Reranker-4B` |
| `psychology_reflection_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/07-psychology-reflection-model.md` | `Qwen/Qwen3-4B-Instruct-2507` |
| `psychology_qa_generator_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/08-psychology-qa-generator-model.md` | `Qwen/Qwen3-8B` |
| `psychology_eval_judge_model` | `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models/09-psychology-eval-judge-model.md` | `Qwen/Qwen3-8B` |

## Local-Only Runtime Rule

허용:

- Ollama
- llama.cpp server
- vLLM local
- SGLang local
- LM Studio local server
- MLX local
- local embedding server
- local reranker
- local fine-tuned checkpoint

금지:

- Gemini runtime fallback
- OpenAI runtime fallback
- Claude runtime fallback
- external hosted judge
- external hosted embedding/reranker
- 실전 cycle 중 조용한 provider switch

## 공통 Risk Taxonomy

```yaml
psychology_common_risks:
  - schema_mismatch
  - unsupported_parameter
  - range_error
  - forced_behavior
  - emotion_as_order_signal
  - bias_as_alpha
  - autonomy_violation
  - clinical_claim
  - revenge_trade_risk
  - no_evidence_drift
  - no_context_ignored
  - temporal_leakage
  - agent_identity_mixup
  - unsupported_causality
  - training_poison
  - judge_overreach
```

## 공통 Records 구조

실제 서비스화 시 각 모델은 다음 구조를 가진다.

```text
services/<psychology_model_service>/
  SERVICE_SPEC.md
  eval_cases/
    regression.jsonl
    rag_regression.jsonl
  records/
    RECORDKEEPING_PLAN.md
    RECORD_INDEX.md
    templates/
      model_card.md
      dataset_datasheet.md
      eval_record.md
      deployment_record.md
      incident_record.md
      research_note.md
```

## Deployment Order

```text
spec_only
 -> seed_eval
 -> local_eval
 -> RAG_regression
 -> integration_eval_with_finance
 -> paper_shadow
 -> live_readonly
 -> live_guarded_observer
```

psychology 모델은 `live_guarded`에서도 observer/helper다. 직접 주문, 직접 HR action, 직접 자본 배분을 실행하지 않는다.

## Integration Boundary

| From | To | Allowed Payload |
|---|---|---|
| psychology_profile_model | agent factory | validated personality JSON |
| psychology_emotion_model | prompt/recorder | VAD+ emotion JSON |
| psychology_drift_model | drift utility | small delta candidate |
| psychology_behavior_bias_model | finance risk guard | bias risk tags |
| psychology_social_dynamics_model | CEO HR context | evidence checklist |
| psychology_memory_retriever_model | psychology models | evidence ids/context |
| psychology_reflection_model | quality loop | failure type, lessons, dataset candidates |
| psychology_eval_judge_model | deployment gate | local verdict only |

## Important Gap

현재 구현의 `PersonalityVector` docstring은 15D라고 쓰지만 실제 필드는 10D다. 문서와 코드가 충돌한다.

운영 전 결정:

```text
Option A: 10D를 표준으로 확정하고 docstring/docs를 수정한다.
Option B: MBTI/Enneagram/Dark Triad 등 5D를 추가해 15D로 확장한다.
```

권장: 먼저 10D를 표준으로 확정한다. MBTI/Dark Triad는 학술적 엄밀성과 안전 리스크 때문에 prompt annotation 또는 offline analysis로 두는 것이 더 안전하다.

## Research Basis

- Generative Agents: https://arxiv.org/abs/2304.03442
- Retrieval-Augmented Generation: https://arxiv.org/abs/2005.11401
- RAGAS: https://arxiv.org/abs/2309.15217
- Lost in the Middle: https://arxiv.org/abs/2307.03172
- LLMLingua-2: https://arxiv.org/abs/2403.12968
- Prospect Theory: https://www.jstor.org/stable/1914185
- Qwen3 local checkpoints: https://huggingface.co/Qwen
- BGE-M3 embedding: https://huggingface.co/BAAI/bge-m3
- BGE reranker v2 m3: https://huggingface.co/BAAI/bge-reranker-v2-m3

## Completion Definition

- 모델별 Service Spec 존재
- 절대경로와 추천 모델명 명시
- current code anchor와 통합 boundary 명시
- finance model suite와 역할 충돌 없음
- psychology 모델이 직접 주문/권한/자본 제약을 우회하지 않음
- RAG/eval/records/QA 수집 기준 존재
