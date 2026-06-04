# 로컬 LLM 포함 프로젝트 실행 런북

## 목적

이 런북은 `agentic-capital` 프로젝트 루트에서 Hugging Face 모델 다운로드, 로컬 LLM 실행, DB/Redis 시작, 모의투자 paper loop 시작까지 재현하는 운영 절차다.

기본값은 `LOCAL_LLM_RUNTIME_MODE=direct`다. 이 모드는 `domain-llm-forge` worktree가 없어도 이 프로젝트만으로 실행된다. 각 모델은 `llama-server`의 OpenAI-compatible `/v1/chat/completions` endpoint에 직접 연결된다.

기본 안전 모드는 고정한다.

```text
LLM_PROVIDER=local
LOCAL_LLM_PROVIDER=local
KIS_IS_PAPER=true
FUTURES_LIVE_ORDERS_ENABLED=false
```

실전 주문 전환, live futures 주문, 수동 주문 제출은 이 런북 범위가 아니다.

## 실행 명령

프로젝트 루트에서 실행한다.

```bash
./scripts/run_local_paper_stack.sh start
```

명시적으로 독립 실행 모드를 지정하려면 다음처럼 실행한다.

```bash
LOCAL_LLM_RUNTIME_MODE=direct ./scripts/run_local_paper_stack.sh start
```

기존 `domain-llm-forge` RAG gateway를 사용하려면 호환 모드를 켠다.

```bash
LOCAL_LLM_RUNTIME_MODE=rag_gateway ./scripts/run_local_paper_stack.sh start
```

전체 재시작은 기존 screen session을 정리한 뒤 다시 시작한다.

```bash
./scripts/run_local_paper_stack.sh restart
```

상태 확인:

```bash
./scripts/run_local_paper_stack.sh status
```

중지:

```bash
./scripts/run_local_paper_stack.sh stop
```

모델 다운로드만 확인/수행:

```bash
./scripts/run_local_paper_stack.sh download
```

기본값은 실행할 때마다 Hugging Face의 `main` revision을 확인하고 바뀐 GGUF만 적용한다. 이미 실행 중인 로컬 LLM 세션이 있는데 모델 파일이 갱신되면 관련 `llama-server` 세션과 paper loop를 재기동해 새 파일을 실제 런타임에 반영한다.

```bash
LOCAL_LLM_AUTO_UPDATE=true ./scripts/run_local_paper_stack.sh start
```

## HF 토큰 규칙

스크립트는 다음 env 파일을 읽는다.

1. finance domain-llm-forge `.env`
2. psychology domain-llm-forge `.env`
3. domain-model-forge `.env`
4. 현재 프로젝트 `.env`

현재 프로젝트 `.env`를 마지막에 읽기 때문에 같은 키가 있으면 `agentic-capital/.env` 값이 우선한다.

허용 키:

```env
HF_TOKEN=
HUGGINGFACE_TOKEN=
```

`HF_TOKEN`이 비어 있고 `HUGGINGFACE_TOKEN`이 있으면 스크립트가 런타임에서만 다음처럼 매핑한다.

```bash
export HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
```

토큰 값은 문서, 로그, git commit에 넣지 않는다.

## 모델 소스

| 역할 | HF repo | 로컬 경로 |
|---|---|---|
| 일반 agent LLM | `unsloth/Qwen3-4B-Instruct-2507-GGUF` | `~/.cache/agentic-capital/models/agentic_capital_react_model/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` |
| finance RAG query | `raiss123/finance_rag_query_model-qwen3-1.7b` | `~/.cache/agentic-capital/models/finance_rag_query_model/finance_rag_query_model.gguf` |
| finance tool planner | `raiss123/finance_tool_planner_model-qwen3-1.7b` | `~/.cache/agentic-capital/models/finance_tool_planner_model/finance_tool_planner_model.gguf` |
| finance decision | `raiss123/finance_decision_model-qwen3-4b-instruct-2507` | `~/.cache/agentic-capital/models/finance_decision_model/finance_decision_model.gguf` |
| finance risk guard | `raiss123/finance_risk_guard_model-qwen3-1.7b` | `~/.cache/agentic-capital/models/finance_risk_guard_model/finance_risk_guard_model.gguf` |
| psychology suite | `raiss123/psychology_model_suite-qwen3-4b` | `~/.cache/agentic-capital/models/psychology_model_suite/psychology_model_suite.gguf` |

`LOCAL_LLM_AUTO_UPDATE=true`가 기본값이므로 GGUF 파일이 이미 있어도 `hf download --revision main`으로 최신 여부를 확인한다. HF CLI가 캐시와 원격 metadata를 비교해 동일 파일이면 다운로드 없이 넘어가고, 파일이 달라졌으면 로컬 GGUF를 갱신한다.

오프라인 재사용이 필요하면 다음처럼 자동 확인을 끈다.

```bash
LOCAL_LLM_AUTO_UPDATE=false ./scripts/run_local_paper_stack.sh start
```

`HF_HUB_OFFLINE=true` 또는 `TRANSFORMERS_OFFLINE=true`이면 기존 GGUF가 있을 때 최신 확인을 건너뛴다. 해당 파일이 없으면 시작을 실패시킨다. private HF repo 접근이 필요한 모델은 `HF_TOKEN` 또는 `HUGGINGFACE_TOKEN`이 필요하다.

## 실행 포트

| 서비스 | direct llama-server | `rag_gateway` 선택 모드 |
|---|---:|---:|
| agentic_capital_react_model | `19000` | 없음 |
| finance_rag_query_model | `18181` | `18101` |
| finance_tool_planner_model | `18182` | `18102` |
| finance_decision_model | `18183` | `8080` |
| finance_risk_guard_model | `18184` | `18104` |
| psychology_model_suite | `18080` | `19400` |

direct 모드에서 프로젝트 paper loop는 다음 URL을 사용한다.

```text
LOCAL_AGENT_LLM_BASE_URL=http://127.0.0.1:19000/v1
LOCAL_FINANCE_RAG_QUERY_BASE_URL=http://127.0.0.1:18181/v1
LOCAL_FINANCE_TOOL_PLANNER_BASE_URL=http://127.0.0.1:18182/v1
LOCAL_FINANCE_DECISION_BASE_URL=http://127.0.0.1:18183/v1
LOCAL_FINANCE_RISK_GUARD_BASE_URL=http://127.0.0.1:18184/v1
LOCAL_PSYCHOLOGY_BASE_URL=http://127.0.0.1:18080/v1
```

## screen 세션

| 세션 | 역할 |
|---|---|
| `local-agent-llm` | CEO/Analyst 일반 ReAct agent LLM |
| `local-finance-rag-query-llama` | finance RAG query GGUF |
| `local-finance-tool-planner-llama` | finance tool planner GGUF |
| `local-finance-decision-llama` | finance decision GGUF |
| `local-finance-risk-guard-llama` | finance risk guard GGUF |
| `local-psych-suite-llama` | psychology suite GGUF |
| `local-finance-rag-query-rag` | `rag_gateway` 모드에서만 finance RAG query gateway |
| `local-finance-tool-planner-rag` | `rag_gateway` 모드에서만 finance tool planner gateway |
| `local-finance-decision-rag` | `rag_gateway` 모드에서만 finance decision gateway |
| `local-finance-risk-guard-rag` | `rag_gateway` 모드에서만 finance risk guard gateway |
| `local-psych-suite-rag` | `rag_gateway` 모드에서만 psychology suite gateway |
| `agentic-capital-paper-local` | 모의투자 paper loop |

스크립트는 이미 같은 포트의 health endpoint가 살아 있으면 새 llama/gateway를 중복 시작하지 않는다.

## 검증 기준

health action은 다음 endpoint를 확인한다.

```bash
./scripts/run_local_paper_stack.sh health
```

필수 endpoint:

```text
http://127.0.0.1:19000/health
http://127.0.0.1:18181/health
http://127.0.0.1:18182/health
http://127.0.0.1:18183/health
http://127.0.0.1:18184/health
http://127.0.0.1:18080/health
```

앱 내부 finance/psychology health checker는 direct mode에서 `/healthz` 실패 시 `/health`와 `/v1/models`를 확인해 모델 alias가 기대값과 맞는지 검증한다.

모의투자 체결 확인은 DB의 `simulation_runs`, `agent_cycles`, `agent_decisions`, `trades`, `positions`, `company_snapshots`로 한다. 수동 주문으로 성공을 만들지 않는다.

Trader finance cycle은 `LOCAL_FINANCE_DEFAULT_SYMBOLS`의 열린 시장 후보를 read-only quote/OHLCV로 먼저 스캔한다. 15m runtime signal이 BUY인 후보가 있으면 cycle 순번의 primary symbol보다 우선하며, 기본 유니버스에는 상승장 후보와 하락장 대응 KR ETF 후보(`252670`, `251340`, `114800`)가 함께 들어 있다. `NXT_AFTER` 같은 `NXT_*`/`KRX_*` 세션 값은 한국 주식 후보의 열린 경로와 paper-only scout 주문 게이트로 처리한다. KIS paper API가 `NXT` after-session scout 주문을 거절하면 실전 주문으로 전환하지 않고 paper safety 안에서 `PAPER-KR-*` 로컬 체결과 포지션으로 기록한다. KR 후보 가격이 500원 미만이면 조정가/저가 왜곡 가능성이 있어 BUY signal ranking에서 제외한다.

## 환경 오버라이드

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LOCAL_LLM_RUNTIME_MODE` | `direct` | `direct`는 독립 실행, `rag_gateway`는 domain-llm-forge gateway 사용 |
| `FINANCE_DOMAIN_LLM_FORGE_ROOT` | `/Users/tpirates/.codex/worktrees/dd25/domain-llm-forge` | `rag_gateway` 모드에서만 필요한 finance RAG worktree |
| `PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT` | `/Users/tpirates/workspace-hjm/domain-llm-forge` | `rag_gateway` 모드에서만 필요한 psychology RAG worktree |
| `DOMAIN_MODEL_FORGE_ENV` | `/Users/tpirates/workspace-hjm/domain-model-forge/.env` | 공통 모델/HF env |
| `AGENTIC_CAPITAL_MODEL_CACHE` | `~/.cache/agentic-capital/models` | agent/finance/psychology GGUF 저장 위치 |
| `LOCAL_LLM_AUTO_UPDATE` | `true` | `start`/`download`에서 HF 최신 GGUF를 확인하고 적용 |
| `LOCAL_LLM_HF_REVISION` | `main` | 확인할 HF branch/tag/commit. 기본은 `main` 최신 |
| `LOCAL_LLM_FORCE_DOWNLOAD` | `false` | `true`면 HF cache를 통해 강제 재다운로드 |
| `LOCAL_LLM_RESTART_ON_UPDATE` | `true` | 모델 파일이 갱신되면 관련 local LLM screen과 paper loop를 재기동 |
| `LLAMA_SERVER_BIN` | `/opt/homebrew/bin/llama-server` | llama.cpp server binary |
| `HF_BIN` | `hf` | Hugging Face CLI |
| `START_DOCKER_INFRA` | `true` | `docker compose up -d` 실행 여부 |
| `START_PAPER_LOOP` | `true` | paper loop screen 시작 여부 |
| `N_GPU_LAYERS` | `99` | llama-server GPU layer 수 |
| `LLAMA_CONTEXT_TOKENS` | `4096` | llama-server context size |

예: LLM/gateway만 시작하고 paper loop는 직접 시작하려면 다음처럼 실행한다.

```bash
START_PAPER_LOOP=false ./scripts/run_local_paper_stack.sh start
```
