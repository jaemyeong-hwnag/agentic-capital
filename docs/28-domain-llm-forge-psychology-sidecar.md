# domain-llm-forge Psychology Sidecar 연동 런북

## 목적

이 문서는 `Agentic Capital`이 `/Users/tpirates/workspace-hjm/domain-llm-forge`를 psychology 로컬 모델/RAG sidecar로 붙일 때의 실제 실행 흐름을 정리한다.

원본 모델 목적 문서는 그대로 보존한다.

- 원본 목적 문서: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-psychology-models`
- 실제 실행 루트: `/Users/tpirates/workspace-hjm/domain-llm-forge`
- 실제 설정: `/Users/tpirates/workspace-hjm/domain-llm-forge/config`
- 실제 서비스 구현: `/Users/tpirates/workspace-hjm/domain-llm-forge/services`

psychology 모델은 투자 결정을 직접 실행하지 않는다. 성격, 감정, drift, 행동 편향, 사회적 맥락, 회고를 evidence-grounded 보조 신호로 제공한다.

## 현재 준비 상태

2026-05-26 기준 로컬 확인 결과:

| Service | GGUF | RAG index | eval report | 운영 권장 |
|---|---:|---:|---:|---|
| `psychology_profile_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_emotion_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_drift_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_behavior_bias_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_social_dynamics_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_memory_retriever_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_reflection_model` | 있음 | 있음 | 36-case 통과 | runtime sidecar |
| `psychology_qa_generator_model` | 미확인 | 있음 | 미확인 | offline QA only |
| `psychology_eval_judge_model` | 미확인 | 있음 | 미확인 | offline eval only |
| `psychology_model_suite` | 있음 | 있음 | 36-case 통과 | runtime orchestration |

확인된 runtime report의 `passed=true`, `n_test=36`, `quality_guard_failures=0`는 profile/emotion/drift/behavior_bias/social_dynamics/memory_retriever/reflection/model_suite 8개 모델에 적용된다.

현재 quality smoke에서 중점적으로 막아야 할 실패는 다음이다.

- JSON/schema 불안정
- runtime 답변에 `BERTScore`, `quality_guard_failures`, `passed=true` 같은 eval-only 용어가 섞이는 문제
- RAG 근거 chunk가 너무 얇아 schema/validator/integration 계약을 충분히 회수하지 못하는 문제
- psychology 모델이 BUY/SELL, 주문, 자본 변경, 의료/진단 결론을 내는 문제

## 환경변수 사용 규칙

필요한 env는 아래 파일에서 가져온다. 값은 문서, 로그, 커밋에 남기지 않는다.

- `/Users/tpirates/workspace-hjm/domain-llm-forge/.env`
- `/Users/tpirates/workspace-hjm/domain-model-forge/.env`

현재 두 파일에서 확인한 키 이름:

```text
DATA_GO_KR_API_KEY
GOOGLE_AI_API_KEY
HUGGINGFACE_TOKEN
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
QA_MODEL_PATH
```

실행 패턴:

```bash
set -a
source /Users/tpirates/workspace-hjm/domain-llm-forge/.env
source /Users/tpirates/workspace-hjm/domain-model-forge/.env
set +a
```

psychology 모델 결과는 agent state에 기록할 수 있지만, 주문/자본/권한을 직접 변경하는 env는 사용하지 않는다.

## 공통 실행 순서

권장 pipeline:

```text
semantic frame extraction
 -> frame 기반 faceted retrieval
 -> evidence coverage verifier
 -> deterministic postprocess 축소
 -> raw model failure 학습 루프
```

Agentic Capital 내부 사용 흐름:

```text
agent conversation / cycle trace
 -> psychology_memory_retriever_model 또는 RAG search
 -> profile/emotion/drift/bias/social model
 -> evidence coverage verifier
 -> validated psychology JSON
 -> finance risk/context layer
 -> recorder / eval loop
```

Agentic Capital은 psychology 결과를 `schema_status`와 함께 저장한다.

| 상태 | 의미 | downstream 사용 |
|---|---|---|
| `validated` | 필수 필드와 context-only 안전 가드를 통과 | recorder, memory, finance soft context |
| `invalid_json_to_context_only` | JSON parse 실패를 context-only failure signal로 축소 | recorder와 risk context에만 사용 |

모든 psychology soft context에는 `use_as=soft_risk_context_not_alpha`와
`forbidden_use=["trade_action","order_quantity","order_permission","capital_allocation"]`가 포함된다.
이 필드는 BUY/SELL, 주문 수량, 주문 권한, 자본 배분, risk limit override를 바꾸는 데 사용할 수 없다.

2026-05-26 기준 `domain-llm-forge`에서는 runtime psychology sidecar 7개와 `psychology_model_suite`에 대해 runtime schema, output validator, Agentic Capital integration, failure learning reference를 RAG corpus에 추가했다. search/gateway smoke에서 schema/validator/integration reference가 회수되고, suite는 QA/eval-only 모델을 runtime route로 쓰지 않도록 검증한다.

## 공통 파일 구조

| 항목 | 경로 |
|---|---|
| 설정 | `/Users/tpirates/workspace-hjm/domain-llm-forge/config/<service>.yaml` |
| 서비스 문서 | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/SERVICE_SPEC.md` |
| workflow | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/workflow.py` |
| 평가 가드 | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/eval_guards.py` |
| QA 생성기 | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/qa_generator.py` |
| 후처리 | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/answer_postprocess.py` |
| RAG 리소스 | `/Users/tpirates/workspace-hjm/domain-llm-forge/services/<service>/resources/` |
| 로컬 GGUF | `/Users/tpirates/workspace-hjm/domain-llm-forge/data/models/<service>/<service>.gguf` |
| RAG index | `/Users/tpirates/workspace-hjm/domain-llm-forge/data/rag/<service>/index/` |
| 평가 report | `/Users/tpirates/workspace-hjm/domain-llm-forge/data/eval/<service>/report.json` |

## 서비스별 계약

| Service | 목적 | 주요 출력 | 원본 문서 | sidecar 문서 | 모델 경로 |
|---|---|---|---|---|---|
| `psychology_profile_model` | 장기 심리 프로파일/선호/반복 패턴 요약 | profile facets, stable traits, uncertainty, evidence ids | `docs/local-psychology-models/01-psychology-profile-model.md` | `services/psychology_profile_model/SERVICE_SPEC.md` | `data/models/psychology_profile_model/psychology_profile_model.gguf` |
| `psychology_emotion_model` | 현재 감정 상태와 정서 강도 추정 | emotion labels, intensity, trigger evidence, uncertainty | `docs/local-psychology-models/02-psychology-emotion-model.md` | `services/psychology_emotion_model/SERVICE_SPEC.md` | `data/models/psychology_emotion_model/psychology_emotion_model.gguf` |
| `psychology_drift_model` | 시간에 따른 심리/관심사/행동 변화 감지 | drift direction, changed facets, evidence, confidence | `docs/local-psychology-models/03-psychology-drift-model.md` | `services/psychology_drift_model/SERVICE_SPEC.md` | `data/models/psychology_drift_model/psychology_drift_model.gguf` |
| `psychology_behavior_bias_model` | 반복 행동과 판단 편향 분석 | bias candidates, behavioral pattern, evidence, mitigation hint | `docs/local-psychology-models/04-psychology-behavior-bias-model.md` | `services/psychology_behavior_bias_model/SERVICE_SPEC.md` | `data/models/psychology_behavior_bias_model/psychology_behavior_bias_model.gguf` |
| `psychology_social_dynamics_model` | 관계 맥락과 상호작용 패턴 분석 | social facets, role/tension/support cues, evidence | `docs/local-psychology-models/05-psychology-social-dynamics-model.md` | `services/psychology_social_dynamics_model/SERVICE_SPEC.md` | `data/models/psychology_social_dynamics_model/psychology_social_dynamics_model.gguf` |
| `psychology_memory_retriever_model` | 심리 분석에 필요한 과거 기억 검색/요약 | relevant memories, evidence ids, retrieval rationale | `docs/local-psychology-models/06-psychology-memory-retriever-model.md` | `services/psychology_memory_retriever_model/SERVICE_SPEC.md` | `data/models/psychology_memory_retriever_model/psychology_memory_retriever_model.gguf` |
| `psychology_reflection_model` | 자기성찰형 응답과 관찰 요약 생성 | reflective response, gentle question, evidence-grounded summary | `docs/local-psychology-models/07-psychology-reflection-model.md` | `services/psychology_reflection_model/SERVICE_SPEC.md` | `data/models/psychology_reflection_model/psychology_reflection_model.gguf` |
| `psychology_qa_generator_model` | 학습/평가 QA와 회귀 테스트 질문 생성 | QA cases, regression candidates | `docs/local-psychology-models/08-psychology-qa-generator-model.md` | `services/psychology_qa_generator_model/SERVICE_SPEC.md` | `data/models/psychology_qa_generator_model/psychology_qa_generator_model.gguf` |
| `psychology_eval_judge_model` | 응답 목적/근거/안전성/형식 평가 | pass/fail, score axes, failure reason | `docs/local-psychology-models/09-psychology-eval-judge-model.md` | `services/psychology_eval_judge_model/SERVICE_SPEC.md` | `data/models/psychology_eval_judge_model/psychology_eval_judge_model.gguf` |
| `psychology_model_suite` | 9개 모델 조율 | profile, emotion, drift, bias, social, memory, reflection, eval summary | `docs/local-psychology-models/10-psychology-model-suite.md` | `services/psychology_model_suite/SERVICE_SPEC.md` | `data/models/psychology_model_suite/psychology_model_suite.gguf` |

## RAG 인덱스 생성

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
./run_rag.sh psychology_profile_model all
```

직접 Python entrypoint를 쓸 때:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
python -m core.rag.prepare --service psychology_profile_model all
```

## RAG 검색 테스트

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
./run_rag.sh psychology_profile_model search "최근 대화에서 반복되는 위험 회피 패턴을 근거와 함께 요약"
```

직접 Python entrypoint:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
python -m core.rag.prepare --service psychology_profile_model search "최근 대화에서 반복되는 위험 회피 패턴을 근거와 함께 요약" --top-k 3
```

## 로컬 모델 서버 실행

GGUF 파일이 존재하는 서비스만 실행한다.

```bash
llama-server \
  -m /Users/tpirates/workspace-hjm/domain-llm-forge/data/models/psychology_profile_model/psychology_profile_model.gguf \
  --host 127.0.0.1 \
  --port 18080 \
  -c 2048
```

## RAG Gateway 실행

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge

RAG_SERVICE=psychology_profile_model \
RAG_INDEX_DIR=/Users/tpirates/workspace-hjm/domain-llm-forge/data/rag/psychology_profile_model/index \
RAG_CONFIG_PATH=/Users/tpirates/workspace-hjm/domain-llm-forge/config/psychology_profile_model.yaml \
RAG_LEXICON_PATH=/Users/tpirates/workspace-hjm/domain-llm-forge/services/psychology_profile_model/resources/lexicon.yaml \
LLAMA_SERVER_URL=http://127.0.0.1:18080 \
LLAMA_MODEL=psychology_profile_model \
RAG_WARMUP=0 \
python -m uvicorn apps.rag_gateway.server:app --host 127.0.0.1 --port 18000
```

OpenAI-compatible 호출:

```bash
curl -s http://127.0.0.1:18000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "psychology_profile_model",
    "messages": [
      {"role": "user", "content": "최근 의사결정 로그에서 반복되는 심리 패턴을 evidence id와 함께 요약"}
    ],
    "temperature": 0.2
  }'
```

## Agentic Capital 연동 방식

로컬 실행 보조 스크립트:

```bash
cd /Users/tpirates/workspace-hjm/agentic-capital
DOMAIN_LLM_FORGE_ROOT=/Users/tpirates/workspace-hjm/domain-llm-forge \
RAG_SERVICE=psychology_model_suite \
PORT=19400 \
./scripts/run_local_psychology_sidecar.sh
```

Agentic Capital smoke:

```bash
cd /Users/tpirates/workspace-hjm/agentic-capital
LOCAL_PSYCHOLOGY_READINESS_REQUIRED=true \
LOCAL_PSYCHOLOGY_BASE_URL=http://127.0.0.1:19400/v1 \
LOCAL_PSYCHOLOGY_MODEL=psychology_model_suite \
agentic-capital-psychology-smoke
```

권장 payload:

```json
{
  "request_id": "cycle-id-or-uuid",
  "service": "psychology_profile_model",
  "agent_context": {
    "agent_id": "CEO-Alpha",
    "deployment_mode": "local_paper",
    "live_order_enabled": false,
    "cycle_window": "recent"
  },
  "input_text": "recent conversation, memory summary, or cycle trace",
  "required_safety": {
    "require_evidence_ids": true,
    "allow_observation_only": true,
    "no_clinical_diagnosis": true,
    "no_direct_order": true
  }
}
```

권장 response:

```json
{
  "signals": [],
  "agent_state_patch": {},
  "evidence_ids": [],
  "confidence": 0.0,
  "uncertainty": [],
  "risk_tags": [],
  "allowed_downstream_use": "context_only"
}
```

runtime validator는 최소한 다음을 hard failure로 처리한다.

| Failure | 의미 |
|---|---|
| `schema_unstable` | structured JSON이 필요한데 JSON으로 parse되지 않음 |
| `schema_missing_required` | `evidence_ids`, `confidence`, `uncertainty` 누락 |
| `trade_action_leak` | `action: BUY`, `action: SELL`, 매수/매도/주문 실행 권고 |
| `eval_artifact_leak` | eval-only 용어가 runtime 응답에 섞임 |
| `clinical_claim` | 임상 진단, 치료, therapy plan 표현 |

finance 계층으로 넘길 때는 다음으로 축소한다.

```json
{
  "psychology_context": {
    "risk_tags": ["overconfidence_risk"],
    "evidence_ids": ["memory-123"],
    "confidence": 0.72,
    "uncertainty": ["requires finance tools before any trade"],
    "agent_state_patch": {"attention": "risk_review"},
    "use_as": "soft_risk_context_not_alpha",
    "forbidden_use": ["trade_action", "order_quantity", "order_permission", "capital_allocation"]
  }
}
```

Agentic Capital runtime은 각 agent cycle 전후에 `psychology_model_suite`를 관찰자로 호출한다.

| Phase | 입력 | 권한 |
|---|---|---|
| `pre_agent_cycle` | agent id/name/role, cycle number, emotion snapshot, 직전 trace 요약 | 상태 관찰만 가능 |
| `post_agent_cycle` | LLM reasoning, tool sequence, decisions, errors | 상태 관찰과 risk tag 기록만 가능 |

Trader가 finance 전용 flow를 탈 때도 같은 pre/post 관찰을 실행한다. 단, finance pipeline에는 pre psychology 결과를 `build_finance_soft_context`로 축소한 soft context만 전달한다. 이 soft context는 `risk_tags`, `evidence_ids`, `confidence`, `uncertainty`, `agent_state_patch`, `use_as`, `forbidden_use`만 포함하며, alpha signal이나 주문 권한으로 승격되지 않는다.

Agentic Capital 쪽 recorder 경로는 세 곳에 남긴다.

| 저장 위치 | 내용 | 목적 |
|---|---|---|
| `agent_cycles.economics_snapshot.psychology_context` | soft context 축소본 | cycle audit와 비용/행동 추적 |
| `memories` + `episodic_details` | psychology context memory | 이후 drift/bias/RAG 회수 |
| `agent_decisions.decision_type=psychology_evaluation` | `action=context_only` evaluation record | eval/회귀/실패 학습 기록 |

`record_cycle`은 `psychology`, `psychology_context`, `psychology_evaluation` 타입을 trade/general decision route로 보내지 않고 `record_psychology_context`로만 보낸다. finance decision payload에 psychology가 섞여도 runtime validator가 `build_finance_soft_context`로 축소하고, BUY/SELL, 수량, 주문 권한, 자본 배분 필드는 deterministic hard failure로 차단한다.

테스트/e2e에서는 psychology와 finance sidecar 호출을 mock하거나 `LOCAL_FINANCE_PIPELINE_ENABLED=false`로 고정한다. sidecar 실호출은 smoke, paper loop, runtime monitor에서 검증하며, unit/e2e 테스트가 로컬 모델 latency나 현재 운영 env에 의존하지 않게 유지한다.

## 안전 경계

| 금지 | 이유 | 대체 |
|---|---|---|
| psychology 결과로 직접 BUY/SELL | psychology는 alpha 모델이 아님 | finance decision model과 risk guard로 전달 |
| 감정 상태를 수익 신호로 단정 | `bias_as_alpha` 위험 | risk tag 또는 confidence adjustment 후보 |
| 임상 진단/치료 결론 | 고위험 의료 claim | 관찰/정리/회고 문구 |
| evidence 없는 drift 단정 | temporal leakage 위험 | `no_context` 또는 memory retrieval |
| 직접 HR action 실행 | 조직 자율성 침해 가능 | CEO context/evidence checklist 제공 |

## 모의투자 테스트 기준

psychology sidecar는 paper trading 중에도 observer/helper로만 동작한다.

| Stage | 조건 | 통과 기준 |
|---|---|---|
| `rag_smoke` | RAG search 1회 이상 | evidence ids 또는 `no_context` |
| `gateway_smoke` | `/healthz`, `/search`, `/v1/chat/completions` | HTTP 200, schema parse 가능 |
| `integration_eval` | Agentic Capital cycle trace 입력 | finance action 없이 context만 반환 |
| `paper_shadow` | `KIS_IS_PAPER=true` cycle | psychology 결과가 주문 수량/권한을 직접 바꾸지 않음 |
| `quality_loop` | 실패 case 기록 | `failure_bucket`, `requires_retest`, `record_type` 생성 |

모의투자 중에도 live 관련 기본값은 유지한다.

```text
KIS_IS_PAPER=true
FUTURES_LIVE_ORDERS_ENABLED=false
psychology_direct_order=false
```

## Self-Recovery 기준

| 실패 | 분류 | 조치 |
|---|---|---|
| GGUF 없는 서비스 호출 | `local_config` | shadow/test로 degrade |
| RAG index 없음 | `data_gap` | RAG build 또는 `no_context` |
| evidence ids 없음 | `retrieval_miss` | downstream 사용 금지 |
| clinical claim 출력 | `guard_gap` | hard fail, eval case 추가 |
| finance action 직접 출력 | `safety` | 결과 폐기, guard failure 기록 |
| gateway hang/down | `local_state` | 단일 프로세스로 재시작, health 재확인 |

## Production Gate Blockers

runtime psychology sidecar 7개와 `psychology_model_suite`는 로컬 readiness 기준을 통과했다. 남은 blocker는 runtime 사용 권한이 아니라 통합 운영 검증이다.

- `agentic-capital` cycle trace 기반 integration smoke 반복
- paper trading shadow에서 psychology 결과가 주문 수량/권한/BUY/SELL을 직접 바꾸지 않는지 확인
- 실패 case를 `domain-llm-forge` eval regression에 계속 추가

`psychology_qa_generator_model`과 `psychology_eval_judge_model`은 offline QA/eval 도구로 유지한다. 별도 GGUF 산출물을 만들 수는 있지만, runtime agent-state route나 trading route로 승격하지 않는다.

psychology 모델은 gate 통과 후에도 직접 주문, 직접 자본 배분, 직접 HR 실행 권한을 갖지 않는다.
