# Local Agent Service Onboarding Spec

## 목적

이 문서는 `Agentic Capital`을 외부 AI API 중심 구조에서 로컬 에이전트(Local Agent) 중심 구조로 전환하기 위한 단일 온보딩 명세다.

현재 프로젝트에는 `docs/23-local-llm-roadmap.md`와 `docs/24-local-agent-data-strategy.md`가 있지만, 재분석 결과 그것만으로는 충분하지 않다. 기존 문서는 QA/RAG/학습 데이터 방향을 잡는 데는 유효하지만, 실제 운영에서 Gemini 호출을 끊고 로컬 모델로 전환하기 위한 provider, runtime, eval, records, deployment gate 명세가 부족하다.

이 문서는 서비스 온보딩 가이드의 원칙에 맞춰 먼저 서비스 계약, 실패 기준, 기록 체계, 평가 기준을 정의한다. QA 생성, SFT, RAG 구축, 배포는 이 명세가 기준이 된다.

## Service Identity

| 항목 | 값 |
|---|---|
| service_name | `local_agent` |
| purpose | 외부 LLM API 비용과 quota 의존성을 줄이고, 1시간 단위 투자 판단을 로컬 SLM/LLM으로 지속 실행한다. |
| target_users | Agentic Capital 운영자, 로컬 모델 평가자, trading agent runtime |
| deployment_target | local_eval → local_paper → local_live_readonly → local_live_guarded |
| default_model_family | OpenAI-compatible local server behind Ollama, llama.cpp, vLLM, SGLang, LM Studio, or MLX |
| current_external_baseline | Gemini 2.5 Flash / Gemini embedding |

## Current Project Findings

현재 코드 기준으로 확인한 사실은 다음과 같다.

| 영역 | 현재 상태 | 판단 |
|---|---|---|
| Config | `LLM_PROVIDER`, `LOCAL_LLM_PROVIDER` alias, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`, `LOCAL_EMBEDDING_MODEL` 지원 | `.env`에서 Gemini/local 전환 가능 |
| LLMPort | `LLMPort.generate/embed`와 `LocalOpenAICompatibleAdapter` 존재 | domain-llm-forge RAG Gateway 또는 llama-server 연결 가능 |
| Main ReAct loop | `graph/workflow.py`가 router를 통해 LangChain chat model 생성 | Gemini 직접 고정 제거 |
| Futures ReAct loop | `simulation/futures_engine.py`가 router를 통해 LangChain chat model 생성 | 모의 선물 루프도 local provider 사용 가능 |
| SimulationEngine | `_init_adapters()`가 `build_llm_adapter()` 사용 | local/gemini 선택 가능 |
| Recorder | `llm_model`, `embedding_model`, provider metadata를 runtime 설정에서 기록 | 재현성/비용 분석 가능 |
| Agent cycles | tool sequence, reasoning, economics 저장 | 학습/eval 원천으로 적합 |
| Memory/RAG | JSONB embedding + cosine search 중심 | 운영 RAG에는 metadata/hybrid/rerank/small-to-big 부족 |
| Dataset exporter | 없음 | DB 로그를 JSONL/Parquet로 내보내는 명세/구현 필요 |
| Eval runner | 없음 | seed QA registry를 실제 local model에 실행하는 harness 필요 |
| Docs | env/external API 문서는 Gemini 필수 구조 | local mode 기준으로 동기화 필요 |

결론: `docs/24-local-agent-data-strategy.md`는 필요하지만 충분하지 않다. 실제 local agent 서비스 완료에는 runtime/provider/eval/records/deploy gate까지 필요하다.

## Purpose

로컬 에이전트 서비스의 목적은 다음 순서로 고정한다.

1. 외부 LLM API quota와 비용 폭발을 제거하거나 통제한다.
2. 에이전트 수가 증가해도 1시간 단위 판단 루프를 지속한다.
3. 자본/보유수량/브로커 권한 제약을 위반하지 않는다.
4. tool calling, structured output, RAG evidence grounding 품질을 Gemini baseline과 비교한다.
5. 최종 성과는 총수익이 아니라 수수료, 슬리피지, AI/장비 비용 차감 후 `decision_roi`로 평가한다.

## Target Users

- 시스템 운영자: local/paper/live-readonly/live-guarded 모드를 전환하고 상태를 확인한다.
- Agentic Capital 에이전트: CEO, Analyst, Trader, Futures Scalper가 로컬 모델을 통해 tool-use 판단을 수행한다.
- 평가/학습 파이프라인: agent cycle 로그를 QA/SFT/preference/RAG eval dataset으로 변환한다.
- 연구 기록 사용자: 모델별 실패, 개선, 배포 판단을 재현 가능하게 확인한다.

## Supported Tasks

| Task | 설명 |
|---|---|
| provider selection | local, gemini, hybrid, disabled fallback 정책 선택 |
| local health check | 모델 서버 readiness, sample completion, embedding endpoint 확인 |
| tool calling | 기존 LangChain StructuredTool을 local-friendly schema로 제공 |
| structured output | JSON Schema, enum, numeric bounds, required fields 검증 |
| output repair | invalid JSON/tool args를 제한된 횟수로 복구 |
| local eval | seed/golden/redteam QA case 실행 |
| dataset export | DB 로그를 train/dev/test/redteam JSONL/Parquet로 추출 |
| RAG retrieval | memory, cycle, trade, market, docs evidence 검색 |
| shadow decision | 주문 없이 판단과 evidence만 기록 |
| cost accounting | token 대신 local latency, energy, amortized hardware cost 기록 |

## Out-of-Scope Tasks

- local model이 자본/보유수량/브로커 권한을 우회하는 것
- Gemini fallback을 조용히 실행하는 것
- eval 없이 SFT부터 시작하는 것
- 사람이 검토하지 않은 redteam 실패를 무시하고 배포하는 것
- tool hallucination을 postprocess로 숨기는 것
- RAG evidence 없이 최신/기관별 사실을 단정하는 것
- 모델이 직접 수치 계산을 암산으로 처리하도록 방치하는 것

## Answer Policy

로컬 에이전트는 가능한 경우 다음 형식을 따라야 한다.

```yaml
decision:
  action: BUY | SELL | HOLD | WAIT | OBSERVE | REJECT | CALL_TOOL
  symbol: "<optional>"
  market: "<optional>"
  quantity: <optional number>
  confidence: 0.0-1.0
  required_tools: []
  evidence_ids: []
  risk_tags: []
  reason: "<compact rationale>"
```

정책:

- 자본, 보유수량, live order flag, market session, tool schema는 hard constraint다.
- 불확실하면 거래하지 않는 `safe_no_trade`가 허용된다.
- 주문 전 필요한 quote/balance/position이 없으면 먼저 tool을 호출한다.
- RAG가 필요한 질문에서 evidence가 없으면 `no_context` 또는 `retrieve_required`로 멈춘다.
- 동일 provider failure를 2회 초과 반복하지 않는다.

## Safety / Quality Risks

| Risk | Hard Fail 조건 | 대응 |
|---|---|---|
| capital_violation | available/capital limit 초과 매수 | adapter guard + eval hard fail |
| position_violation | 미보유/초과 매도 | positions check mandatory |
| hallucinated_tool | 존재하지 않는 tool 호출 | allowlist + schema validator |
| hallucinated_symbol | quote/evidence 없는 symbol 주문 | symbol validation + reject |
| invalid_json | required field 누락/enum 오류 | repair once, then fail |
| unsafe_fallback | 실전에서 무기록 Gemini fallback | provider event mandatory |
| stale_market_state | stale quote/session으로 주문 | timestamp freshness gate |
| unsupported_rag_claim | evidence 없는 최신/기관별 사실 단정 | evidence id required |
| bad_numeric_reasoning | 수수료/슬리피지/수량 계산 오류 | Program-of-Thought/tool calculation |
| latency_overrun | 1시간 루프를 훼손하는 추론 지연 | context cap + smaller model/router |
| duplicate_runtime | local/live engine 중복 실행 | self-recovery duplicate process fail |

## Risk Taxonomy

서비스별 risk tag는 seed eval, eval guard, quality policy, records에 동일하게 반영한다.

```yaml
risk_tags:
  - capital_violation
  - position_violation
  - live_order_permission
  - market_session_error
  - invalid_tool_call
  - hallucinated_tool
  - hallucinated_symbol
  - invalid_structured_output
  - unsupported_rag_claim
  - stale_context
  - bad_numeric_reasoning
  - unsafe_external_fallback
  - provider_unavailable
  - latency_overrun
  - negative_decision_roi
  - overfitting_to_backtest
```

## Data Sources

| Source | 용도 | 현재 존재 여부 |
|---|---|---|
| `agent_cycles` | prompt/result/tool sequence/reasoning/economics | 있음 |
| `agent_decisions` | trade/org/strategy decision | 있음 |
| `trades` | fill, commission, net value, confidence | 있음 |
| `positions` | 보유수량, 평단, 미실현손익 | 있음 |
| `company_snapshots` | total capital, cash, org state | 있음 |
| `memories` | semantic/episodic/procedural memory | 있음 |
| `episodic_details` | observation/action/outcome/reflection | 있음 |
| `agent_tools` | AI-created tool schema/code | 있음 |
| `market_ohlcv` | OHLCV, percentage features | 있음 |
| quote/session data | live price/session freshness | adapter 기반 |
| logs | provider/quota/runtime incident | 일부 있음 |
| docs/research/filings/news | RAG external evidence | 골격 필요 |

## Agent Runtime Recording

CEO/Analyst는 finance decision model을 일반 LLM처럼 쓰지 않는다. `LOCAL_LLM_MODEL=finance_*`인 경우에도 일반 ReAct agent는
`LOCAL_AGENT_LLM_BASE_URL`와 `LOCAL_AGENT_LLM_MODEL`에 연결된다. Trader만 local finance pipeline 조건에서 finance sidecar flow로 간다.

각 `agent_cycles.economics_snapshot`에는 다음 운영 필드를 남긴다.

| Field | 목적 |
|---|---|
| `agent_request.prompt_summary` | 전체 system prompt 원문 대신 짧은 요청 요약만 저장 |
| `agent_request.cycle_trigger` | `cycle:<n>` 형태의 실행 trigger |
| `agent_request.agent_role` | `ceo`, `analyst`, `trader` role boundary 확인 |
| `agent_request.tool_names` | 해당 cycle에 노출된 tool 목록 |
| `agent_response.reasoning_summary` | 최종 응답 요약 |
| `agent_response.tool_calls_count` | ReAct tool 호출 수 |
| `agent_response.decisions_count` | 기록된 decision 수 |
| `agent_response.errors_count` | cycle 오류 수 |
| `agent_response.next_action` | continue, wakeup, retry 분류 |
| `agent_response.failure_cause` | 오류 시 첫 실패 원인 요약 |

로컬 instruct 모델이 tool schema를 그대로 흉내 내 `{"properties":{"symbol":"005930"}}` 같은 인자를 반환하면,
runtime은 schema map이 아닌 value map일 때만 `{"symbol":"005930"}`으로 보정한다.
이는 Analyst/CEO의 read-only quote/balance 조회 validation noise를 줄이기 위한 제한적 repair다.

## RAG Requirement

이 서비스는 RAG가 필요하다. 이유는 다음과 같다.

- 거래 판단은 계좌/포지션/시장/도구 상태처럼 최신 상태에 의존한다.
- 과거 agent cycle과 trade outcome을 회수해 같은 실수를 줄여야 한다.
- 금융 문서/뉴스/정책/브로커 제약은 시점과 출처가 중요하다.
- `no_context`일 때 답변하지 않아야 하는 케이스가 있다.
- 수치가 비슷한 hard negative 문서가 많아 단순 vector search만으로 위험하다.

필수 RAG 구조:

| Layer | 요구사항 |
|---|---|
| chunk schema | `document_id`, `chunk_id`, `parent_id`, `source_type`, `symbol`, `market`, `published_at`, `valid_from`, `valid_to`, `text`, `table_ref`, `evidence_hash` |
| retrieval | dense + sparse hybrid, metadata prefilter |
| reranking | cross-encoder 또는 local reranker |
| small-to-big | row/chunk 검색 후 parent section 회수 |
| hard negatives | symbol, quantity, date, fee가 유사하지만 다른 문서 포함 |
| numeric path | 수수료/수량/ROI는 calculator/tool로 처리 |
| evidence policy | 답변/결정에 `evidence_ids` 저장 |
| no_context | 근거 없는 최신/기관별 사실은 답변 금지 |

## Evaluation Axes

| Axis | Metric | Gate |
|---|---|---|
| schema validity | `schema_valid_rate` | >= 0.99 |
| tool calling | `tool_call_success_rate` | >= 0.98 |
| capital safety | `capital_violation_count` | 0 |
| position safety | `position_violation_count` | 0 |
| hallucination | `hallucinated_tool_count`, `unsupported_claim_count` | 0 |
| RAG retrieval | `Recall@5`, `MRR@5`, citation support | baseline 이상 |
| latency | `p95_latency_ms` | 1시간 cadence 내 충분한 여유 |
| cost | `cost_per_successful_decision_krw` | external baseline보다 낮음 |
| trading quality | `decision_roi`, no-trade baseline 비교 | 악화 금지 |
| robustness | redteam pass rate | hard fail 0 |

## Seed Eval Cases

초기 seed case는 대량 QA보다 먼저 작성한다. 최소 필드는 다음과 같다.

```json
{
  "id": "local-agent-seed-001",
  "user_question": "",
  "expected_behavior": "",
  "must_include": [],
  "must_not_include": [],
  "risk_tags": [],
  "conversation": []
}
```

필수 case 유형:

| Type | Example |
|---|---|
| happy path | balance/position/quote 확인 후 작은 paper order 판단 |
| hard risk | available cash보다 큰 매수 요청 거부 |
| out-of-scope | broker 권한 없는 live futures 주문 거부 |
| ambiguous | market/symbol/quantity가 없는 주문 의도 보류 |
| missing context | quote/position snapshot이 stale이면 tool 호출 |
| multi-turn | 이전 답변의 symbol을 이어받되 latest quote 재확인 |
| negated condition | "보유하지 않은 종목은 팔지 마"를 정확히 준수 |
| unrelated control | 투자와 무관한 질문은 거래 action 없음 |
| RAG expected | 과거 유사 손실 memory를 evidence로 회수 |
| no_context | 근거 문서 없는 최신 뉴스 단정 금지 |
| distractor | 유사 symbol/quantity hard negative에 흔들리지 않음 |

현재 `src/agentic_capital/core/local_ai/datasets.py`의 QA registry는 이 seed case의 시작점이다.

## Eval Guard Spec

초기 guard는 rule 기반으로 충분하다. 목적은 평균 점수 뒤에 hard fail을 숨기지 않는 것이다.

필수 검사:

- JSON parse 가능 여부
- required field 존재 여부
- enum 값 유효성
- unknown tool 호출 여부
- capital/position violation 문구 또는 action 여부
- unsupported evidence claim 여부
- live order disabled 상태에서 order intent 여부
- no_context case에서 단정 답변 여부

예상 인터페이스:

```python
def validate_quality(samples: list[dict]) -> list[str]:
    failures: list[str] = []
    for sample in samples:
        ...
    return failures
```

## Quality Policy Spec

`quality_policy.py`가 해야 할 일:

| Failure Type | 분류 기준 | Patch 후보 |
|---|---|---|
| retrieval_miss | 관련 문서가 top-k에 없음 | metadata key, chunking, hybrid retrieval 수정 |
| rerank_error | 후보에는 있으나 최종 context에서 빠짐 | reranker/hard negative 강화 |
| model_schema_error | context는 맞지만 JSON/tool schema 실패 | SFT/grammar/guided decoding |
| model_reasoning_error | evidence는 맞지만 판단/계산 오류 | calculator tool, Program-of-Thought |
| guard_gap | 위험 답변이 gate를 통과 | eval_guard rule 추가 |
| data_gap | 정답에 필요한 source 자체가 없음 | ingest/data contract 추가 |
| provider_error | timeout, local down, invalid response 반복 | health check/backoff/router 수정 |

## Config Spec

최소 config는 다음 형태가 되어야 한다.

```yaml
service:
  name: "local_agent"
  description: "Run Agentic Capital investment agents on local SLM/LLM providers with strict tool and capital guards."
  base_model: "Qwen/Qwen3-1.7B"
  output_model: "local/agentic-capital-qwen3-1.7b"

provider:
  mode: "local"          # local | gemini | hybrid | disabled
  local_base_url: "http://127.0.0.1:11434/v1"
  local_model: "qwen3:1.7b"
  embedding_model: "local/bge-m3"
  fallback:
    enabled: false
    target: "gemini"
    allowed_modes: ["local_eval", "hybrid_review"]

qa:
  categories:
    - capital_constraint
    - position_constraint
    - tool_use
    - structured_output
    - rag_retrieval
    - provider_failure

eval:
  quality_guard:
    enabled: true
    module: "services.local_agent.eval_guards"
    function: "validate_quality"

quality_loop:
  policy:
    module: "services.local_agent.quality_policy"
    class: "LocalAgentQualityPolicy"
  model_issues:
    jsonl_path: "data/model_training_failures/local_agent.jsonl"
    sft_path: "data/model_training_failures/local_agent_sft.jsonl"
    preference_path: "data/model_training_failures/local_agent_preference.jsonl"
  reports_root: "data/quality_reports"
```

환경변수는 실제 값은 `.env`, placeholder는 `.env.example`에만 둔다.

```env
LLM_PROVIDER=local
# LOCAL_LLM_PROVIDER=local  # 호환 alias
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
LOCAL_LLM_MODEL=qwen3:1.7b
LOCAL_EMBEDDING_MODEL=bge-m3
LOCAL_LLM_API_KEY=
LOCAL_LLM_TIMEOUT_SECONDS=30
LOCAL_LLM_TEMPERATURE=0.2
DOMAIN_LLM_FORGE_ROOT=/Users/tpirates/workspace-hjm/domain-llm-forge
DOMAIN_LLM_FORGE_ENV=/Users/tpirates/workspace-hjm/domain-llm-forge/.env
DOMAIN_MODEL_FORGE_ENV=/Users/tpirates/workspace-hjm/domain-model-forge/.env
RAG_SERVICE=finance_decision_model
```

`scripts/run_local_finance_sidecar.sh`는 위 env 파일들을 값 출력 없이 source하고 `domain-llm-forge/run_rag.sh <service> serve`를 실행한다.

## Records Requirement

서비스 생성 순간부터 기록 체계가 있어야 한다. 이 프로젝트에서는 단일 문서 운영을 허용하더라도, 향후 분리 시 아래 구조를 따라야 한다.

필수 기록 항목:

| Record | Trigger |
|---|---|
| onboarding record | local_agent 서비스 명세 생성/변경 |
| eval record | QA/eval run 실행 |
| dataset datasheet | train/dev/test/redteam dataset 생성 |
| model card | local model snapshot 생성 |
| RAG change record | chunk/retriever/reranker 변경 |
| deployment record | local_paper/live_readonly/live_guarded 승격 |
| incident record | provider down, duplicate runtime, unsafe fallback, hard fail |
| research note | 논문/벤치마크 기반 설계 변경 |

`RECORD_INDEX.md` 형식:

| Date | Record ID | Type | Trigger | Verdict | Summary | Evidence/Run | Decision | Commit |
|---|---|---|---|---|---|---|---|---|

배포 금지 조건:

- hard risk regression failure 존재
- provider/model/hash 미기록
- fallback event 미기록
- rollback target 없음
- local_eval 또는 local_paper gate 미통과
- live mode에서 duplicate runtime 발견

## Runtime Architecture Requirement

현재 구조에서 반드시 바꿔야 하는 호출 경로:

```text
Implemented:
  SimulationEngine/FuturesEngine
    -> LLMRouter
      -> LocalOpenAICompatibleAdapter / LocalOpenAICompatibleChatModel
      -> GeminiLLMAdapter / ChatGoogleGenerativeAI only when LLM_PROVIDER=gemini
```

핵심 원칙:

- `core/`는 특정 서비스명이나 provider명을 몰라야 한다.
- provider 분기는 adapter/router/config 계층에 둔다.
- LangGraph ReAct loop도 router를 통해 chat model을 받아야 한다.
- provider/model/backend/latency/cost/fallback은 `simulation_runs.config`와 `agent_cycles.economics_snapshot`에 저장한다.

## Dataset Export Requirement

학습은 바로 시작하지 않는다. 먼저 export와 eval split을 고정한다.

필수 export record:

```json
{
  "id": "",
  "split": "train|dev|test|redteam",
  "task": "tool_call|structured_output|rag_answer|decision_quality",
  "input": {
    "system": "",
    "context": [],
    "question": ""
  },
  "expected": {
    "action": "",
    "tools": [],
    "json_schema": {},
    "evidence_ids": []
  },
  "labels": [],
  "source_refs": [],
  "risk_tags": [],
  "outcome": {
    "net_pnl_krw": null,
    "decision_roi": null
  }
}
```

Split 기준:

- `train`: 정상 tool 성공, 안전한 no-trade, outcome label이 성숙한 기록
- `dev`: edge case, provider failure, schema 오류
- `test`: 사람이 결과를 보지 않는 holdout
- `redteam`: 자본 위반 유도, hallucinated tool/symbol, distractor evidence

## Deployment Gate

배포 단계:

```text
local_eval
 -> local_paper 24h
 -> local_live_readonly 24h
 -> local_live_guarded with tiny cap
 -> capital expansion by decision_roi
```

각 단계 gate:

| Stage | Gate |
|---|---|
| local_eval | QA pass >= 95%, hard fail 0 |
| local_paper | 24h no crash, duplicate runtime 0, schema failure < 1% |
| local_live_readonly | 실계좌 조회 성공, 주문 없음, 판단 기록 정상 |
| local_live_guarded | tiny cap, live order guard 유지, rollback 준비 |
| capital expansion | decision ROI가 baseline보다 좋거나 악화 없음 |

## Open Questions

| 질문 | Default |
|---|---|
| 첫 local model은 무엇인가? | OpenAI-compatible Qwen 1.7B/3B 계열 |
| embedding은 local로 갈 것인가? | yes, bge/e5 계열 후보 |
| Gemini fallback을 허용할 것인가? | 실전 기본 false, eval/hybrid review에서만 true |
| RAG vector store는 PG JSONB 유지인가 pgvectorscale인가? | eval 단계는 JSONB 가능, 운영은 pgvectorscale/hybrid 권장 |
| agent별 모델 라우팅을 할 것인가? | CEO는 큰 모델, Analyst/Trader는 작은 모델 후보 |
| live 주문 전 human review가 필요한가? | local_live_guarded 초기에는 yes 권장 |

## Required Files If Split Later

이 문서는 단일 파일 명세지만, 실제 서비스화 시 다음 파일로 분리한다.

```text
services/local_agent/
  SERVICE_SPEC.md
  answer_postprocess.py
  eval_guards.py
  eval_prompt.py
  qa_generator.py
  quality_policy.py
  eval_cases/
    regression.jsonl
    rag_regression.jsonl
  resources/
    lexicon.yaml
    domain_reference.jsonl
  records/
    RECORDKEEPING_PLAN.md
    RECORD_INDEX.md
    templates/
      improvement_record.md
      rag_change_record.md
      dataset_datasheet.md
      model_card.md
      eval_record.md
      deployment_record.md
      incident_record.md
      research_note.md
config/local_agent.yaml
```

## Codex Implementation Order

실제 구현 순서는 다음과 같다.

1. provider config와 `.env.example` placeholder 추가
2. `LocalOpenAICompatibleAdapter`와 local embedding adapter 추가
3. `LLMRouter` 추가
4. `workflow.py`와 `futures_engine.py`의 direct Gemini 생성 제거
5. recorder에 provider/model/backend/latency/fallback metadata 기록
6. local eval runner 작성
7. dataset exporter 작성
8. RAG index schema와 retriever/reranker 골격 작성
9. seed eval/regression cases 확장
10. local_paper/live_readonly 운영 기록 템플릿 추가

## Research Basis

- Small Language Models for Agentic Systems: schema-first prompting, strict JSON Schema, validator-first tool execution, SLM-default/LLM-fallback, cost per successful task.
  https://arxiv.org/abs/2510.03847
- Agentic Retrieval-Augmented Generation for Financial Document Question Answering: iterative retrieval-reasoning, self-verification, hard negative mining, Program-of-Thought, adaptive strategy routing.
  https://arxiv.org/abs/2605.05409
- Metadata-Driven Retrieval-Augmented Generation for Financial Question Answering: contextual chunks, pre-retrieval filtering, reranking, metadata-aware RAG.
  https://arxiv.org/abs/2510.24402
- Rethinking Retrieval in Financial Domain: hybrid search, metadata filtering, cross-encoder reranking, small-to-big retrieval.
  https://arxiv.org/abs/2511.18177
- Enhancing Financial Report Question-Answering with Reranking Analysis.
  https://arxiv.org/abs/2603.16877
- Synthesizing Question Answering Data from Financial Documents: multi-agent QA generation pipeline for SLM fine-tuning.
  https://aclanthology.org/2026.eacl-industry.51/
- Self-Instruct: synthetic instruction generation with filtering.
  https://arxiv.org/abs/2212.10560
- Self-RAG: retrieve/generate/critique with self-reflection.
  https://arxiv.org/abs/2310.11511

## Completion Definition

`local_agent` 서비스는 아래 조건을 모두 만족할 때 온보딩 완료로 본다.

- 서비스 계약, risk taxonomy, eval axes, deployment gate가 문서화됨
- provider switch 명세와 env 규칙이 있음
- seed eval case와 hard risk case가 있음
- eval guard와 quality policy의 역할이 명확함
- RAG 필요 여부와 retrieval data contract가 정의됨
- records plan과 incident/deploy/eval 기록 기준이 있음
- 현재 프로젝트에서 direct Gemini 호출 경로가 식별됨
- 구현 순서가 provider/runtime/eval/export/RAG/deploy 순서로 정리됨

현재 상태는 **문서 온보딩 초안 완료**이며, 실제 외부 API 비용 절감을 위해서는 Runtime Architecture Requirement부터 구현해야 한다.
