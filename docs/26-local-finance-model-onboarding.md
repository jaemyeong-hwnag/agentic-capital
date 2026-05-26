# Local Finance Model Onboarding Spec

## 목적

이 문서는 `Agentic Capital`에서 외부 AI API 없이 로컬 모델만으로 finance agent 판단을 운영하기 위한 모델별 온보딩 명세다.

핵심 결론은 다음과 같다.

```text
Finance 모델 하나만으로는 부족하다.
로컬 운영에서는 역할별 모델/서브모델을 분리하고,
각 모델마다 SERVICE_SPEC, risk taxonomy, eval gate, records 기준을 둬야 한다.
```

이 문서는 `domain-llm-forge`의 Service Onboarding Guide 원칙을 따른다.

- 목적 명세만으로 바로 학습하지 않는다.
- 먼저 모델별 서비스 계약을 정의한다.
- 평가 기준과 실패 기준을 먼저 만든다.
- 모든 모델은 records 체계를 가진다.
- 공통 core는 서비스명과 모델명을 몰라야 한다.
- 외부 LLM API fallback은 이 문서 범위에서 제외한다.

## Local-Only 원칙

이 문서의 모든 모델은 로컬 실행만 허용한다.

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
- 외부 hosted reranker
- 외부 hosted embedding
- 실전 주문 중 조용한 외부 provider switch

단, 과거 외부 모델 로그를 이미 보유하고 있다면 offline distillation/eval source로만 사용할 수 있다. 운영 runtime에서는 호출하지 않는다.

## 전체 모델 구성

최대 구성은 다음 모델들로 나눈다.

| Model Service | 역할 | 필수 여부 | RAG 필요 |
|---|---|---:|---:|
| `finance_decision_model` | 투자 질문을 안전한 structured decision으로 변환 | 필수 | 예 |
| `finance_tool_planner_model` | 필요한 tool 순서와 argument schema 생성 | 필수 | 예 |
| `finance_rag_query_model` | 검색 query rewrite, routing, no_context 판단 | 필수 | 예 |
| `finance_embedding_model` | 문서/기록/질문 vector embedding | 필수 | 예 |
| `finance_reranker_model` | retrieved evidence 재정렬, hard negative 구분 | 필수 | 예 |
| `finance_evidence_summarizer_model` | 긴 evidence를 decision context로 압축 | 권장 | 예 |
| `finance_risk_guard_model` | 위험 표현/정책 위반 보조 감지 | 권장 | 선택 |
| `finance_eval_judge_model` | offline eval judge, quality report 작성 | 권장 | 예 |
| `finance_qa_generator_model` | seed/eval/SFT QA 후보 생성 | 권장 | 예 |
| `finance_reflection_model` | 실패 원인 분류, 개선 후보 생성 | 선택 | 예 |

중요: deterministic guard가 최종 권한을 가진다. 어떤 로컬 모델도 직접 live order를 최종 승인하지 않는다.

## 공통 Deployment Flow

모든 모델은 같은 승격 순서를 따른다.

```text
spec_only
 -> seed_eval
 -> local_eval
 -> integration_eval
 -> paper_shadow
 -> live_readonly
 -> live_guarded
```

학습은 `spec_only`, `seed_eval`, `local_eval`이 끝난 뒤에만 시작한다.

## 공통 Records 구조

실제 서비스화 시 각 모델은 다음 records를 가진다.

```text
services/<model_service>/
  SERVICE_SPEC.md
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

단일 문서 단계에서는 아래 공통 record index 형식을 따른다.

| Date | Record ID | Model Service | Type | Trigger | Verdict | Summary | Evidence/Run | Decision | Commit |
|---|---|---|---|---|---|---|---|---|---|

## 공통 Risk Taxonomy

모든 모델이 공유하는 hard risk다.

```yaml
common_risks:
  - capital_violation
  - position_violation
  - live_order_permission_violation
  - market_session_error
  - stale_quote
  - stale_balance
  - stale_position
  - hallucinated_symbol
  - hallucinated_tool
  - invalid_json
  - invalid_tool_args
  - unsupported_rag_claim
  - no_context_ignored
  - bad_numeric_reasoning
  - profit_guarantee
  - loss_guarantee
  - unsafe_external_fallback
  - provider_unavailable
  - latency_overrun
  - negative_decision_roi
```

## 1. finance_decision_model

### Purpose

투자 질문을 곧장 매수/매도 결론으로 바꾸지 않고, 안전한 structured decision으로 변환한다.

### Target Users

- CEO/Analyst/Trader/Futures agent
- local runtime router
- paper/shadow/live-readonly decision recorder

### Supported Tasks

- `BUY`, `SELL`, `HOLD`, `WAIT`, `OBSERVE`, `REJECT`, `CALL_TOOL` 중 action 선택
- 근거가 없으면 `no_context`, `retrieve_required`, `CALL_TOOL`
- 실전 주문 권한이 없으면 live order 거부
- 수익 보장/손실 없음/확정 상승 표현 차단
- confidence와 risk tag 출력

### Out-of-Scope Tasks

- 직접 주문 실행
- 계좌 잔고를 추측
- 보유수량을 추측
- 최신 가격/뉴스/공시를 memory로 단정
- 실전 주문 권한 우회

### Answer Policy

```yaml
decision:
  action: BUY | SELL | HOLD | WAIT | OBSERVE | REJECT | CALL_TOOL
  symbol: ""
  market: ""
  quantity: null
  confidence: 0.0
  required_tools: []
  evidence_ids: []
  risk_tags: []
  reason: ""
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| profit_guarantee | "무조건 오른다", "손실 없다" 류 표현 |
| premature_order | balance/position/quote 확인 없이 BUY/SELL |
| live_permission_violation | read-only/live disabled에서 live order intent |
| no_context_ignored | evidence 없이 최신 claim |

### Data Sources

- `agent_cycles`
- `agent_decisions`
- `trades`
- `positions`
- `company_snapshots`
- RAG evidence pack
- risk limit snapshot

### RAG Requirement

필수. decision은 최신 계좌/시장/과거 outcome 근거가 필요하다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| schema_valid_rate | >= 0.99 |
| hard_risk_count | 0 |
| capital_violation_count | 0 |
| position_violation_count | 0 |
| no_context_pass_rate | >= 0.98 |

### Deployment Gate

`local_eval`에서 hard fail 0, `paper_shadow`에서 주문 없이 decision record 정상 기록.

### Open Questions

- 첫 base model은 Qwen3 1.7B/4B 중 무엇인가?
- futures 전용 decision head를 분리할 것인가?

## 2. finance_tool_planner_model

### Purpose

decision 전에 필요한 tool 호출 순서와 argument를 만든다.

### Target Users

- LangGraph/ReAct runtime
- tool adapter layer
- eval guard

### Supported Tasks

- `get_balance`
- `get_positions`
- `get_quote`
- `get_market_session`
- `get_risk_limit`
- `search_rag`
- `evaluate_reallocation`
- `submit_paper_order`
- `submit_live_order`는 live guard 통과 시에만 후보로 생성

### Out-of-Scope Tasks

- 존재하지 않는 tool 생성
- schema에 없는 argument 추가
- tool 결과를 조작
- 실패한 tool을 무한 반복

### Answer Policy

```json
{
  "tool_plan": [
    {
      "tool": "get_balance",
      "args": {},
      "reason": "Need available cash before order intent"
    }
  ],
  "stop_if_missing": ["balance", "position", "quote"]
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| hallucinated_tool | allowlist 밖 tool |
| invalid_tool_args | required arg 누락 |
| unsafe_tool_order | submit before balance/position/quote |
| repeat_loop | 같은 실패 tool 반복 |

### Data Sources

- tool schema registry
- `agent_tools`
- previous `tool_sequence`
- tool error logs

### RAG Requirement

필수. tool schema와 과거 tool failure를 검색해야 한다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| tool_name_accuracy | 1.0 |
| arg_schema_valid_rate | >= 0.99 |
| unsafe_sequence_count | 0 |
| repeated_failure_count | 0 |

### Deployment Gate

tool-call regression hard fail 0.

### Open Questions

- tool planner를 decision model과 합칠 것인가, 별도 SLM으로 둘 것인가?

## 3. finance_rag_query_model

### Purpose

사용자 질문/agent state를 검색 가능한 query와 retrieval route로 바꾼다.

### Target Users

- Finance RAG server
- local decision model
- eval/quality loop

### Supported Tasks

- query rewrite
- symbol/market/date/entity 추출
- retrieval route 선택
- no_context 판단
- distractor 회피 query 생성

### Out-of-Scope Tasks

- 최종 투자 decision 생성
- 근거 없는 답변 생성
- 검색 실패를 성공으로 포장

### Answer Policy

```json
{
  "queries": [
    {
      "text": "005930 recent position and prior loss cycles",
      "filters": {
        "symbol": "005930",
        "market": "kr_stock"
      },
      "route": "agent_cycles+positions+trades"
    }
  ],
  "requires_fresh_data": true,
  "no_context_if_empty": true
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| wrong_symbol_filter | AAPL evidence를 005930 질문에 사용 |
| stale_filter | 날짜/세션 조건 누락 |
| no_context_ignored | 검색 실패인데 답변 진행 |
| route_miss | 필요한 DB source 미검색 |

### Data Sources

- `agent_cycles`
- `trades`
- `positions`
- `memories`
- docs/research/filings/news
- market session snapshots

### RAG Requirement

필수. 이 모델 자체가 RAG entrypoint다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| route_accuracy | >= 0.95 |
| metadata_filter_accuracy | >= 0.98 |
| no_context_accuracy | >= 0.98 |
| distractor_resistance | hard fail 0 |

### Deployment Gate

RAG regression에서 expected reference/no_context/distractor case 통과.

### Open Questions

- query rewrite에 Korean/English dual query를 항상 만들 것인가?

## 4. finance_embedding_model

### Purpose

문서, agent record, trade outcome, memory, 질문을 local vector로 변환한다.

### Target Users

- RAG ingest
- retriever
- near-duplicate filter
- hard negative miner

### Supported Tasks

- document embedding
- query embedding
- record embedding
- memory embedding
- embedding dimension/version 기록

### Out-of-Scope Tasks

- 답변 생성
- 투자 판단
- risk 판단

### Answer Policy

Embedding model은 자연어 답변을 내지 않는다. 출력은 vector와 metadata다.

```json
{
  "embedding": [0.0],
  "model": "local-bge-m3",
  "dimension": 1024,
  "normalized": true
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| dimension_mismatch | index dimension과 다름 |
| model_version_missing | embedding model id 미기록 |
| stale_embedding | source 변경 후 재임베딩 누락 |
| semantic_collision | 유사하지만 다른 수량/날짜/symbol 혼동 |

### Data Sources

- docs
- `agent_cycles`
- `trades`
- `memories`
- `agent_tools`
- incident/eval records

### RAG Requirement

필수.

### Evaluation Axes

| Axis | Gate |
|---|---|
| retrieval_recall_at_5 | baseline 이상 |
| duplicate_detection_precision | baseline 이상 |
| hard_negative_separation | hard fail 0 |
| embedding_metadata_completeness | 1.0 |

### Deployment Gate

index build record, model hash, dimension, source hash 기록 완료.

### Open Questions

- 운영 index는 JSONB cosine에서 pgvectorscale/hybrid로 언제 전환할 것인가?

## 5. finance_reranker_model

### Purpose

retriever가 가져온 후보 evidence를 질문 관련도와 risk 기준으로 재정렬한다.

### Target Users

- RAG server
- decision model context builder
- quality loop

### Supported Tasks

- top-k rerank
- hard negative 제거
- symbol/date/quantity mismatch 감지
- evidence support score 생성

### Out-of-Scope Tasks

- 최종 decision 생성
- evidence 없는 claim 생성

### Answer Policy

```json
{
  "ranked_evidence": [
    {
      "evidence_id": "cycle-123",
      "score": 0.92,
      "support_type": "direct",
      "mismatch_flags": []
    }
  ],
  "dropped": [
    {
      "evidence_id": "doc-999",
      "reason": "wrong_symbol"
    }
  ]
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| hard_negative_promoted | distractor가 top evidence |
| mismatch_ignored | symbol/date/quantity mismatch 무시 |
| unsupported_top1 | 질문과 무관한 top1 |

### Data Sources

- retriever candidates
- hard negative eval set
- evidence metadata

### RAG Requirement

필수.

### Evaluation Axes

| Axis | Gate |
|---|---|
| MRR@5 | baseline 이상 |
| hard_negative_drop_rate | >= 0.98 |
| support_precision | >= 0.95 |

### Deployment Gate

RAG rerank regression hard fail 0.

### Open Questions

- reranker는 cross-encoder local model을 쓸 것인가, small judge model을 쓸 것인가?

## 6. finance_evidence_summarizer_model

### Purpose

긴 검색 결과를 decision model이 소비 가능한 compact context로 압축한다.

### Target Users

- decision model
- tool planner
- eval judge

### Supported Tasks

- evidence 요약
- table/record compact formatting
- stale evidence 표시
- conflicting evidence 표시
- evidence id 유지

### Out-of-Scope Tasks

- evidence id 삭제
- 원문에 없는 claim 추가
- 숫자 재계산을 암산으로 수행

### Answer Policy

```json
{
  "summary": "available cash is below proposed order value",
  "evidence_ids": ["balance-20260522-001"],
  "numeric_fields": {
    "available_cash": 28690,
    "order_value": 1000000
  },
  "conflicts": [],
  "staleness": "fresh"
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| evidence_id_loss | summary에 evidence id 없음 |
| unsupported_summary | 원문에 없는 내용 추가 |
| numeric_distortion | 금액/수량 왜곡 |
| stale_hidden | stale evidence 표시 누락 |

### Data Sources

- retrieved evidence
- source metadata
- compact format rules

### RAG Requirement

필수에 가까운 권장. context가 커질수록 필요하다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| faithfulness | >= 0.98 |
| evidence_id_retention | 1.0 |
| numeric_accuracy | 1.0 |
| compression_ratio | target 이하 |

### Deployment Gate

summarization faithfulness regression 통과.

### Open Questions

- TOON/Markdown-KV/XML 중 어떤 compact context를 기본으로 할 것인가?

## 7. finance_risk_guard_model

### Purpose

deterministic guard를 보조해 위험 표현과 정책 위반 가능성을 감지한다.

### Target Users

- eval guard
- answer postprocess
- incident recorder

### Supported Tasks

- 수익 보장 표현 탐지
- 손실 없음 표현 탐지
- 투자 권유 단정 탐지
- live order 권한 위반 의심 탐지
- unsupported claim 의심 탐지

### Out-of-Scope Tasks

- deterministic guard 대체
- 주문 승인
- 모델 답변을 몰래 수정해 실패를 숨김

### Answer Policy

```json
{
  "risk_flags": ["profit_guarantee"],
  "hard_fail": true,
  "explanation": "Answer implies guaranteed return."
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| false_negative_hard_risk | 위험 문구를 놓침 |
| postprocess_hiding | 원인 기록 없이 답변만 수정 |
| overblocking | 안전한 no-trade까지 무조건 차단 |

### Data Sources

- model outputs
- risk taxonomy
- incident records
- eval failure cases

### RAG Requirement

선택. 정책 문구가 자주 바뀌면 필요하다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| hard_risk_recall | >= 0.99 |
| false_negative_hard_fail | 0 |
| incident_classification_accuracy | >= 0.95 |

### Deployment Gate

deterministic guard와 함께 동작하고, guard 단독보다 hard risk recall 개선.

### Open Questions

- rule 기반으로 충분한가, local classifier가 필요한가?

## 8. finance_eval_judge_model

### Purpose

offline evaluation에서 답변 품질, evidence support, decision safety를 평가한다.

### Target Users

- eval pipeline
- quality loop
- records generator

### Supported Tasks

- answer quality scoring
- evidence faithfulness scoring
- decision safety scoring
- failure type classification
- eval record 초안 작성

### Out-of-Scope Tasks

- runtime live order 판단
- 자신의 점수를 deployment gate 단독 기준으로 사용
- hard fail을 평균 점수로 덮기

### Answer Policy

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

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| judge_leniency | 위험 답변을 pass |
| evidence_blindness | evidence 없는 claim을 허용 |
| metric_hiding | hard fail을 평균 점수로 은폐 |

### Data Sources

- eval cases
- model outputs
- evidence packs
- deterministic guard results

### RAG Requirement

예. judge는 reference/evidence를 봐야 한다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| agreement_with_hard_rules | 1.0 |
| failure_type_accuracy | >= 0.9 |
| false_pass_hard_fail | 0 |

### Deployment Gate

judge 자체의 calibration eval 통과 전에는 참고 지표로만 사용.

### Open Questions

- judge model은 decision model과 분리할 것인가?

## 9. finance_qa_generator_model

### Purpose

seed eval, RAG eval, SFT 후보 QA를 생성한다.

### Target Users

- dataset pipeline
- quality loop
- human reviewer

### Supported Tasks

- supported task별 질문 생성
- risk taxonomy별 hard case 생성
- negative/control case 생성
- no_context case 생성
- source-grounded QA 생성
- preference pair 후보 생성

### Out-of-Scope Tasks

- 생성 QA를 검증 없이 학습에 투입
- holdout/test set에 train contamination 유발
- source에 없는 정답 생성

### Answer Policy

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

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| unsupported_gold | source 없는 expected answer |
| train_test_leakage | holdout contamination |
| duplicate_case | near duplicate 남발 |
| weak_redteam | hard risk를 제대로 유도하지 못함 |

### Data Sources

- SERVICE_SPEC
- risk taxonomy
- seed cases
- RAG evidence
- incident records
- failed eval records

### RAG Requirement

필수. source-grounded QA를 만들어야 한다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| source_grounded_rate | >= 0.98 |
| duplicate_rate | target 이하 |
| hard_risk_coverage | 모든 taxonomy 포함 |
| human_accept_rate | baseline 이상 |

### Deployment Gate

생성 QA는 validator와 human/sample review 통과 후에만 train/dev 후보가 된다.

### Open Questions

- synthetic QA 비율을 전체 train set의 몇 퍼센트로 제한할 것인가?

## 10. finance_reflection_model

### Purpose

실패 사례를 분석해 RAG 문제, 모델 문제, 서버 문제, guard 문제로 분리하고 개선 후보를 만든다.

### Target Users

- quality loop
- incident review
- model improvement issue writer

### Supported Tasks

- failure classification
- patch candidate 제안
- incident summary 작성
- model improvement issue 작성
- RAG change proposal 작성

### Out-of-Scope Tasks

- 자동 배포 승인
- 실패 원인 없이 재시도 지시
- live 주문 복구를 수동 주문으로 대체

### Answer Policy

```json
{
  "failure_bucket": "rag|model|server|guard|data|external_state",
  "evidence": [],
  "patch_candidates": [],
  "requires_retest": true,
  "record_type": "incident_record"
}
```

### Safety / Quality Risks

| Risk | Hard Fail |
|---|---|
| wrong_bucket | RAG 문제를 모델 문제로 오분류 |
| unsafe_retry | 원인 없이 같은 실패 재시도 |
| missing_incident | hard fail인데 기록 없음 |

### Data Sources

- eval failures
- guard failures
- provider logs
- retriever/reranker traces
- incident records

### RAG Requirement

예. 실패 원인 분석에는 trace/evidence 검색이 필요하다.

### Evaluation Axes

| Axis | Gate |
|---|---|
| failure_bucket_accuracy | >= 0.9 |
| unsafe_retry_count | 0 |
| record_completeness | >= 0.98 |

### Deployment Gate

자동 수정 권한 없이 recommendation-only로 시작.

### Open Questions

- incident severity 분류 체계를 어디까지 자동화할 것인가?

## 통합 Runtime Router

모델별 분리는 runtime router가 담당한다.

```text
user/agent question
  -> finance_rag_query_model
  -> finance_embedding_model
  -> retriever
  -> finance_reranker_model
  -> finance_evidence_summarizer_model
  -> finance_tool_planner_model
  -> deterministic tool execution
  -> finance_decision_model
  -> deterministic guards
  -> record/eval/deploy gate
```

권장 routing:

| Task | Model |
|---|---|
| 질문 분석/decision | `finance_decision_model` |
| tool 순서 | `finance_tool_planner_model` |
| 검색 query | `finance_rag_query_model` |
| vector search | `finance_embedding_model` |
| evidence 재정렬 | `finance_reranker_model` |
| context 압축 | `finance_evidence_summarizer_model` |
| 위험 표현 감지 | deterministic guard + `finance_risk_guard_model` |
| offline 평가 | `finance_eval_judge_model` |
| QA 생성 | `finance_qa_generator_model` |
| 실패 분석 | `finance_reflection_model` |

## 통합 Config 초안

```yaml
service:
  name: "finance_local_models"
  description: "Local-only model suite for Agentic Capital finance decisions."

runtime:
  external_fallback_enabled: false
  deployment_stage: "local_eval"
  evidence_required_for_fresh_claims: true

models:
  decision:
    service: "finance_decision_model"
    base_model: "Qwen/Qwen3-4B"
    local_endpoint: "http://127.0.0.1:11434/v1"
  tool_planner:
    service: "finance_tool_planner_model"
    base_model: "Qwen/Qwen3-1.7B"
    local_endpoint: "http://127.0.0.1:11434/v1"
  rag_query:
    service: "finance_rag_query_model"
    base_model: "Qwen/Qwen3-1.7B"
    local_endpoint: "http://127.0.0.1:11434/v1"
  embedding:
    service: "finance_embedding_model"
    base_model: "BAAI/bge-m3"
    local_endpoint: "http://127.0.0.1:8081"
  reranker:
    service: "finance_reranker_model"
    base_model: "BAAI/bge-reranker-v2-m3"
    local_endpoint: "http://127.0.0.1:8082"
  summarizer:
    service: "finance_evidence_summarizer_model"
    base_model: "Qwen/Qwen3-1.7B"
    local_endpoint: "http://127.0.0.1:11434/v1"
  risk_guard:
    service: "finance_risk_guard_model"
    base_model: "local/rule-plus-small-classifier"
  eval_judge:
    service: "finance_eval_judge_model"
    base_model: "Qwen/Qwen3-4B"
  qa_generator:
    service: "finance_qa_generator_model"
    base_model: "Qwen/Qwen3-4B"
  reflection:
    service: "finance_reflection_model"
    base_model: "Qwen/Qwen3-4B"

eval:
  hard_fail_zero: true
  required_suites:
    - seed_regression
    - tool_call_regression
    - rag_regression
    - no_context_regression
    - redteam
```

## 통합 Seed Eval 필수 목록

모델별 seed eval은 최소 다음을 포함한다.

| Case Type | 대상 모델 |
|---|---|
| happy path decision | decision, tool planner |
| insufficient cash | decision, tool planner, risk guard |
| sell unowned position | decision, tool planner, risk guard |
| stale quote | rag query, decision |
| market closed | rag query, decision |
| hallucinated tool | tool planner, risk guard |
| invalid JSON | decision, tool planner |
| no_context | rag query, decision, eval judge |
| distractor evidence | embedding, reranker, summarizer |
| wrong symbol evidence | rag query, reranker, eval judge |
| profit guarantee phrase | decision, risk guard |
| live order disabled | decision, tool planner, risk guard |
| provider unavailable | reflection, runtime router |
| negative decision ROI | decision, eval judge |

## 통합 Deployment Gate

모든 모델이 아래 gate를 통과해야 한다.

| Gate | 조건 |
|---|---|
| local-only check | 외부 provider endpoint 없음 |
| service spec complete | 모델별 Purpose/Risk/Eval 정의 |
| seed eval pass | hard fail 0 |
| schema pass | required JSON schema valid |
| RAG pass | expected/no_context/distractor 통과 |
| tool pass | unknown tool 0, invalid args < 1% |
| records pass | model card/eval record/dataset datasheet 존재 |
| paper shadow pass | 주문 없이 decision 기록 |
| live-readonly pass | 실계좌 조회만, 주문 없음 |
| live-guarded pass | tiny cap + deterministic guard |

## 결론

로컬 finance agent는 단일 모델이 아니라 모델 역할들의 조합이다.

```text
최소:
  decision + tool_planner + rag_query + embedding + reranker + deterministic_guard

권장:
  최소 구성
  + evidence_summarizer
  + risk_guard
  + eval_judge
  + qa_generator
  + reflection

금지:
  finance_decision_model 하나로 live order까지 처리
```

모델별 책임을 분리해야 학습 데이터, eval failure, RAG failure, server failure를 분리할 수 있다. 그래야 비용을 줄이면서도 실전 주문 리스크를 통제할 수 있다.
