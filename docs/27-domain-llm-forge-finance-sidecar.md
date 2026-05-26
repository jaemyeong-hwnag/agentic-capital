# domain-llm-forge Finance Sidecar 연동 런북

## 목적

이 문서는 `Agentic Capital`이 `/Users/tpirates/workspace-hjm/domain-llm-forge`를 finance 로컬 모델/RAG sidecar로 붙일 때의 실제 실행 흐름을 정리한다.

원본 모델 목적 문서는 그대로 보존한다.

- 원본 목적 문서: `/Users/tpirates/workspace-hjm/agentic-capital/docs/local-finance-models`
- 실제 실행 루트: `/Users/tpirates/workspace-hjm/domain-llm-forge`
- 실제 설정: `/Users/tpirates/workspace-hjm/domain-llm-forge/config`
- 실제 서비스 구현: `/Users/tpirates/workspace-hjm/domain-llm-forge/services`

이 문서는 원본 문서를 대체하지 않는다. `Agentic Capital`에서 sidecar를 호출하는 운영 계약, 안전 모드, 모의투자 테스트 순서를 정의한다.

## 역할 경계

Finance 모델군은 매매 의사결정용 sidecar다. `Agentic Capital`이 질문, agent state, tool 결과, RAG evidence를 보내면 매매 판단에 필요한 구조화 결과를 돌려준다. 단, finance 모델도 주문 실행자가 아니다. 실제 주문 여부와 수량 집행은 `Agentic Capital`의 trading adapter, paper/live permission, deterministic risk guard가 최종 통제한다.

Psychology 모델군은 finance 판단을 대체하지 않는다. psychology 결과는 감정, drift, 행동 편향 같은 보조 signal로만 `finance_risk_guard_model` 또는 recorder에 전달할 수 있다.

## 현재 준비 상태

2026-05-26 기준 로컬 확인 결과:

| 항목 | 상태 | 의미 |
|---|---|---|
| finance service spec | 10개 서비스 디렉터리 존재 | 서비스 계약과 workflow 골격 사용 가능 |
| finance config | 10개 YAML 존재 | sidecar 서비스명별 실행 가능 |
| RAG raw/index | 10개 모두 `finance_service_reference.jsonl`, `chunks.jsonl`, `bm25.pkl` 존재 | RAG search 우선 연동 가능 |
| finance GGUF | 현재 main tree의 `data/models/finance_*/*.gguf` 없음 | 모델 추론은 GGUF 생성/다운로드 후 가능 |
| full eval report | current 30-case finance report 없음 또는 stale | production gate blocker |
| convert preflight | readiness gate가 `convert_free_gb`, `convert_disk_preflight_ok`를 기록 | preflight green일 때만 비용 큰 convert 허용 |
| 권장 운영 모드 | readonly, paper, shadow | live 주문 금지 |

따라서 지금 붙일 1차 방식은 **RAG search sidecar + deterministic guard + paper/shadow decision 기록**이다. GGUF 모델 서버는 파일 존재와 eval 통과 후 활성화한다.

다음 GGUF 확보 우선순위는 다음 3개다.

1. `finance_tool_planner_model`
2. `finance_decision_model`
3. `finance_risk_guard_model`

`finance_rag_query_model`은 runtime priority 모델이지만 현재는 RAG search 경로를 먼저 사용한다. 별도 GGUF가 준비되면 사용자/agent 질문을 `query`, `symbol`, `market`, `route`, `requires_fresh_data`로 구조화하는 전단 모델로 승격한다.

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

로컬 실행 시 sidecar 루트에서 `.env`가 자동 source된다. `Agentic Capital` 쪽에서 별도 실행 스크립트를 만들 때도 값 출력 없이 다음 패턴만 사용한다.

```bash
set -a
source /Users/tpirates/workspace-hjm/domain-llm-forge/.env
source /Users/tpirates/workspace-hjm/domain-model-forge/.env
set +a
```

모의투자 테스트는 `Agentic Capital` env에서 `KIS_IS_PAPER=true`, `FUTURES_LIVE_ORDERS_ENABLED=false`를 유지한다.

## Finance 모델 실행 흐름

권장 runtime chain:

```text
user_question
 -> finance_rag_query_model
 -> RAG / finance_embedding_model
 -> finance_reranker_model
 -> finance_evidence_summarizer_model
 -> finance_tool_planner_model
 -> finance_decision_model
 -> finance_risk_guard_model
 -> deterministic postprocess / 기록
```

핵심 runtime 모델:

| 모델 | runtime 역할 | 필수 출력/행동 |
|---|---|---|
| `finance_rag_query_model` | 질문을 검색 가능한 query, symbol, market, route로 변환 | `requires_fresh_data`, `facets`, `confidence`, `uncertainty` |
| `finance_tool_planner_model` | 매매 전 필요한 tool 호출 계획 생성 | `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`, `search_rag` |
| `finance_decision_model` | 최종 action 제안 | `BUY`, `SELL`, `HOLD`, `WAIT`, `OBSERVE`, `REJECT`, `CALL_TOOL`; 주문 실행 금지 |
| `finance_risk_guard_model` | decision/final answer 위험 검사 | profit guarantee, live 권한 없는 주문, 근거 없는 BUY/SELL 차단 |

RAG 품질 보조 모델:

| 모델 | 역할 |
|---|---|
| `finance_embedding_model` | 검색 embedding |
| `finance_reranker_model` | 검색 결과 재정렬 |
| `finance_evidence_summarizer_model` | evidence id와 숫자를 보존한 근거 압축 |

offline 전용 모델:

| 모델 | runtime 사용 여부 | 용도 |
|---|---:|---|
| `finance_qa_generator_model` | 아니오 | QA/eval/SFT 후보 생성 |
| `finance_eval_judge_model` | 아니오 | 배포 전후 regression 평가 |
| `finance_reflection_model` | 아니오 | 실패 분석, 재학습 후보 생성 |

## 서비스별 계약

| Service | Runtime 역할 | 원본 문서 | config | service dir | RAG index | GGUF 기대 경로 |
|---|---|---|---|---|---|---|
| `finance_rag_query_model` | 질문을 query/filter/route로 변환 | `docs/local-finance-models/03-finance-rag-query-model.md` | `config/finance_rag_query_model.yaml` | `services/finance_rag_query_model` | `data/rag/finance_rag_query_model/index` | `data/models/finance_rag_query_model/finance_rag_query_model.gguf` |
| `finance_embedding_model` | 문서, 질문, 기록 embedding | `docs/local-finance-models/04-finance-embedding-model.md` | `config/finance_embedding_model.yaml` | `services/finance_embedding_model` | `data/rag/finance_embedding_model/index` | `data/models/finance_embedding_model/finance_embedding_model.gguf` |
| `finance_reranker_model` | 후보 evidence 재정렬 | `docs/local-finance-models/05-finance-reranker-model.md` | `config/finance_reranker_model.yaml` | `services/finance_reranker_model` | `data/rag/finance_reranker_model/index` | `data/models/finance_reranker_model/finance_reranker_model.gguf` |
| `finance_evidence_summarizer_model` | evidence compact context 생성 | `docs/local-finance-models/06-finance-evidence-summarizer-model.md` | `config/finance_evidence_summarizer_model.yaml` | `services/finance_evidence_summarizer_model` | `data/rag/finance_evidence_summarizer_model/index` | `data/models/finance_evidence_summarizer_model/finance_evidence_summarizer_model.gguf` |
| `finance_tool_planner_model` | tool 호출 순서/args 생성 | `docs/local-finance-models/02-finance-tool-planner-model.md` | `config/finance_tool_planner_model.yaml` | `services/finance_tool_planner_model` | `data/rag/finance_tool_planner_model/index` | `data/models/finance_tool_planner_model/finance_tool_planner_model.gguf` |
| `finance_decision_model` | 최종 투자 행동 제안 | `docs/local-finance-models/01-finance-decision-model.md` | `config/finance_decision_model.yaml` | `services/finance_decision_model` | `data/rag/finance_decision_model/index` | `data/models/finance_decision_model/finance_decision_model.gguf` |
| `finance_risk_guard_model` | 위험 표현/권한 위반 감지 | `docs/local-finance-models/07-finance-risk-guard-model.md` | `config/finance_risk_guard_model.yaml` | `services/finance_risk_guard_model` | `data/rag/finance_risk_guard_model/index` | `data/models/finance_risk_guard_model/finance_risk_guard_model.gguf` |
| `finance_eval_judge_model` | offline 평가 judge | `docs/local-finance-models/08-finance-eval-judge-model.md` | `config/finance_eval_judge_model.yaml` | `services/finance_eval_judge_model` | `data/rag/finance_eval_judge_model/index` | `data/models/finance_eval_judge_model/finance_eval_judge_model.gguf` |
| `finance_qa_generator_model` | QA/eval/SFT 후보 생성 | `docs/local-finance-models/09-finance-qa-generator-model.md` | `config/finance_qa_generator_model.yaml` | `services/finance_qa_generator_model` | `data/rag/finance_qa_generator_model/index` | `data/models/finance_qa_generator_model/finance_qa_generator_model.gguf` |
| `finance_reflection_model` | 실패 원인 분류 | `docs/local-finance-models/10-finance-reflection-model.md` | `config/finance_reflection_model.yaml` | `services/finance_reflection_model` | `data/rag/finance_reflection_model/index` | `data/models/finance_reflection_model/finance_reflection_model.gguf` |

## 최소 요청 구조

다른 서비스가 finance sidecar에 보내는 최소 payload:

```json
{
  "request_id": "uuid-or-cycle-id",
  "user_question": "005930 지금 매수해도 돼?",
  "agent_state": {
    "deployment_mode": "local_paper",
    "live_order_enabled": false,
    "account_id": "paper",
    "symbol": "005930",
    "market": "KRX"
  },
  "required_safety": {
    "no_profit_guarantee": true,
    "no_live_order_without_permission": true,
    "require_evidence_ids": true,
    "stop_on_missing_context": true
  }
}
```

BUY 또는 SELL은 다음 조건을 모두 만족할 때만 허용한다.

| 조건 | 실패 시 action |
|---|---|
| 최신 quote/session 확인 | `CALL_TOOL` 또는 `WAIT` |
| balance/position 확인 | `CALL_TOOL` |
| risk limit 확인 | `CALL_TOOL` 또는 `REJECT` |
| RAG evidence ids 존재 | `OBSERVE` 또는 `REJECT` |
| profit guarantee 없음 | `REJECT` |
| live order 권한 오해 없음 | `REJECT` |

최종 decision contract:

```json
{
  "action": "BUY|SELL|HOLD|WAIT|OBSERVE|REJECT|CALL_TOOL",
  "symbol": "005930",
  "market": "KRX",
  "quantity": null,
  "confidence": 0.0,
  "required_tools": [],
  "evidence_ids": [],
  "risk_tags": [],
  "reason": "compact evidence-grounded rationale"
}
```

## RAG 검색만 붙이는 방법

RAG search는 현재 가장 안전한 1차 연동이다.

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
./run_rag.sh finance_decision_model search "005930 보유 포지션과 리스크 한도 확인 후 매수 가능 여부"
```

Agentic Capital에서는 이 결과를 바로 매매 decision으로 쓰지 않는다. 반드시 다음 deterministic 조건을 확인한다.

| 필수 조건 | 없을 때 action |
|---|---|
| evidence ids | `no_context` 또는 `REJECT` |
| balance snapshot | `CALL_TOOL:get_balance` |
| position snapshot | `CALL_TOOL:get_positions` |
| quote/session snapshot | `CALL_TOOL:get_quote`, `CALL_TOOL:get_market_session` |
| risk limit | `CALL_TOOL:get_risk_limit` |

## RAG Gateway 실행

HTTP API로 붙일 때:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge

DOMAIN_LLM_FORGE_ROOT=/Users/tpirates/workspace-hjm/domain-llm-forge \
RAG_SERVICE=finance_decision_model \
RAG_INDEX_DIR=/Users/tpirates/workspace-hjm/domain-llm-forge/data/rag/finance_decision_model/index \
HOST=127.0.0.1 \
PORT=8080 \
./run_rag.sh finance_decision_model serve
```

사용 endpoint:

```text
GET  http://127.0.0.1:8080/healthz
POST http://127.0.0.1:8080/search
POST http://127.0.0.1:8080/v1/chat/completions
```

## GGUF 모델 서버 실행

GGUF 파일이 존재할 때만 모델 추론을 활성화한다.

```bash
llama-server \
  -m /Users/tpirates/workspace-hjm/domain-llm-forge/data/models/finance_decision_model/finance_decision_model.gguf \
  --host 127.0.0.1 \
  --port 8033 \
  -ngl 99
```

RAG gateway가 이 모델 서버를 쓰게 하는 실행:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge

LLAMA_SERVER_URL=http://127.0.0.1:8033 \
LLAMA_MODEL=finance_decision_model \
HOST=127.0.0.1 \
PORT=8080 \
./run_rag.sh finance_decision_model serve
```

OpenAI-compatible chat 호출:

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "finance_decision_model",
    "messages": [
      {"role": "user", "content": "005930 보유 포지션과 리스크 한도 확인 후 매수 가능 여부"}
    ],
    "temperature": 0.2
  }'
```

## 모델 다운로드와 생성 파이프라인

HF에서 모델을 받아 GGUF를 만들 때는 `HUGGINGFACE_TOKEN`을 env에서만 읽는다.

전체 파이프라인:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge

./run.sh finance_decision_model data
./run.sh finance_decision_model qa
./run.sh finance_decision_model train
./run.sh finance_decision_model convert
./run.sh finance_decision_model eval
```

오프라인 QA 생성:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge

FINANCE_QA_OFFLINE=1 \
QA_MODEL_PATH=/tmp/not-used-qwen.gguf \
./run.sh finance_decision_model qa
```

RAG 인덱스 재생성:

```bash
cd /Users/tpirates/workspace-hjm/domain-llm-forge
./run_rag.sh finance_decision_model all
```

## Agentic Capital 연동 순서

1. `local_eval`에서 `src/agentic_capital/core/local_ai/datasets.py`의 deterministic QA suite를 통과시킨다.
2. `finance_rag_query_model` RAG search로 symbol, market, route, freshness 요구사항을 얻는다.
3. `Agentic Capital` tool layer에서 `get_balance`, `get_positions`, `get_quote`, `get_market_session`, `get_risk_limit`을 모의투자로 호출한다.
4. RAG evidence와 tool 결과가 모두 있을 때만 `finance_decision_model` chat을 호출한다.
5. decision 직후 `finance_risk_guard_model`과 deterministic guard를 모두 실행한다.
6. `KIS_IS_PAPER=true`에서 paper order 또는 shadow decision만 기록한다.
7. `simulation_runs.config`, `agent_cycles.economics_snapshot`, `tool_sequence`에 provider, model, evidence ids, latency, fallback 여부를 기록한다.

## 다음 검증 루프

1. disk preflight가 green인지 확인한 뒤 convert/train 재실행 여부를 결정한다.
2. `finance_tool_planner_model`, `finance_decision_model`, `finance_risk_guard_model` 순서로 GGUF를 확보한다.
3. 각 모델에 대해 gateway health/search/chat smoke를 실행한다.
4. paper trading shadow에서 decision record가 남는지 확인한다.
5. decision 0 반복, BUY/SELL 근거 누락, risk limit 초과, profit guarantee 표현을 회귀 테스트로 고정한다.
6. trade가 생성되더라도 risk limit을 넘지 않는지 `tests/unit/test_trading_paper.py` 계층에서 확인한다.

## 모의투자 테스트 기준

모의투자 테스트는 주문 가능성이 있어도 live 권한을 절대 켜지 않는다.

| Stage | 조건 | 통과 기준 |
|---|---|---|
| `rag_smoke` | RAG search 1회 이상 | evidence ids 반환 또는 명시적 `no_context` |
| `gateway_smoke` | `/healthz`, `/search` 호출 | HTTP 200 |
| `local_eval` | deterministic QA suite | hard fail 0 |
| `local_paper_shadow` | `KIS_IS_PAPER=true`, 주문 기록 shadow | balance/position/quote 없으면 `BUY/SELL` 없음 |
| `paper_order_guarded` | paper adapter만 주문 허용 | capital/position/live permission violation 0 |

최소 hard rule:

```text
근거, balance, position, quote, risk limit 중 하나라도 없으면 BUY/SELL 금지.
허용 action은 CALL_TOOL, WAIT, REJECT, no_context뿐이다.
```

## Self-Recovery 기준

| 실패 | 분류 | 조치 |
|---|---|---|
| gateway down | `local_state` 또는 `local_config` | health 확인, 단일 프로세스로 재시작 |
| GGUF 없음 | `local_config` | RAG-only/paper-shadow로 degrade |
| 같은 invalid JSON 2회 | `local_code` 또는 `model_schema_error` | retry 중단, repair/eval failure 기록 |
| evidence 없음 | `data_gap` 또는 `retrieval_miss` | `no_context`, RAG case 추가 |
| duplicate simulation/runtime | `safety` | 중복 프로세스 중단, 주문 금지 |
| live 권한 불명확 | `safety` | 주문 금지, readonly 보고 |

## Production Gate Blockers

현재 finance sidecar를 live 주문 판단에 쓰기 전 필요한 blocker:

- finance GGUF 파일 존재 확인
- 각 finance service의 최신 full eval report
- RAG chat smoke 통과 기록
- stale validation summary
- paper/shadow 24h에서 duplicate runtime 0
- capital/position/live permission hard fail 0

blocker 해소 전 기본값은 `readonly`, `paper`, `shadow`다.
