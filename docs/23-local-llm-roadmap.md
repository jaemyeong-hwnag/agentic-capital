# 로컬 LLM 전환 로드맵

## 핵심 목표

Hosted LLM quota나 외부 API 장애 때문에 실전/모의 운영이 멈추지 않도록, `Agentic Capital`의 reasoning kernel을 로컬 LLM으로도 실행 가능하게 만든다.

단, 로컬 LLM 전환의 목적은 "AI 비용 0원"이 아니다. 목표는 다음 순서다.

```
1. 외부 quota 의존성 제거
2. 1시간 단위 판단 지속성 확보
3. 매매 판단 품질을 DeepSeek hosted baseline과 비교 검증
4. 기능 호출(tool calling), JSON 출력, 자본 제약 준수율을 실전 수준까지 올림
5. 실제 비용: 전기/장비/운영/지연시간까지 포함해 decision ROI로 평가
```

## 전제

로컬 LLM은 증권사 API, 자본 제약, 포트폴리오 제약을 우회하지 않는다.

| 항목 | 유지 기준 |
|------|----------|
| 목적 | 돈을 번다 |
| 실행 주기 | 1시간 단위 수익 실현을 기본 단위로 유지 |
| 제약 | 자산/자본/실보유수량/브로커 권한만 물리적으로 강제 |
| 실전 안전 | KIS live 주문 가드, 보유수량 초과 매도 방지, 현금 초과 매수 방지 유지 |
| 평가 | 비용 포함 순수익, decision ROI, tool-call 성공률, 자본 제약 위반률 |

## 아키텍처 정의

현재 구조는 이미 `LLMPort`와 LangGraph ReAct loop가 있으므로, 로컬 LLM은 새 core가 아니라 교체 가능한 adapter로 들어와야 한다.

```
Agent / LangGraph
  -> LLMRouter
     -> DeepSeekAdapter
     -> LocalOpenAICompatibleAdapter
     -> LocalLlamaCppAdapter
     -> LocalMLXAdapter

Trading / MarketData
  -> 기존 KIS/Paper/Futures adapter 유지
```

### Provider 전략

| Provider | 역할 | 장점 | 리스크 |
|----------|------|------|--------|
| OpenAI-compatible local server | 1차 표준 인터페이스 | Ollama, llama.cpp server, vLLM, LM Studio 계열과 호환 쉬움 | tool calling 호환 차이 |
| llama.cpp direct/server | CPU/GPU 저사양 fallback | GGUF 생태계, 단순 운영 | 긴 context/JSON 안정성 한계 |
| MLX local | Apple Silicon 최적화 | Mac 로컬 실험 속도 좋음 | 서버/배포 표준화 추가 필요 |
| DeepSeek | benchmark/hosted review | 기준선 비교, 고난도 판단 | quota/비용/외부 의존 |

권장 순서는 `OpenAI-compatible local server`를 1차로 구현하고, 모델 서빙은 환경에 맞게 뒤에서 교체한다.

## 마일스톤

### M8.1 LLM Provider Abstraction 정리

| 작업 | 산출물 | 완료 기준 |
|------|--------|----------|
| `LLMProvider` 설정 추가 | `LLM_PROVIDER`, `LOCAL_LLM_PROVIDER` alias, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL` | `.env`에서 local/DeepSeek 전환 가능 |
| LangGraph용 local chat model adapter | `LocalOpenAICompatibleChatModel` | `create_react_agent`에서 동일 tool 목록 사용 |
| provider health check | `/health` 또는 sample completion | 시작 전 모델 서버 미기동 감지 |
| provider fallback 정책 | local 우선, DeepSeek hosted review 또는 반대 | fallback 여부가 DB에 기록됨 |

주의: fallback은 실전에서 조용히 provider를 바꾸면 판단 재현성이 깨진다. `simulation_runs.config`와 `agent_cycles.economics_snapshot`에 provider/model을 반드시 남긴다.

현재 런타임 상태:

- `SimulationEngine`의 `LLMPort` 생성은 `adapters/llm/router.py`를 통해 `DeepSeekLLMAdapter` 또는 `LocalOpenAICompatibleAdapter`를 선택한다.
- 메인 LangGraph ReAct loop와 futures ReAct loop는 `build_langchain_chat_model()`을 통해 `DeepSeekChatModel` 또는 `LocalOpenAICompatibleChatModel`을 선택한다.
- `simulation_runs.llm_model`, `simulation_runs.embedding_model`, `simulation_runs.config.llm_provider`, `agent_cycles.economics_snapshot`에 provider/model metadata를 기록한다.
- 로컬 provider는 OpenAI-compatible `/v1/chat/completions`와 `/v1/embeddings`를 사용하므로 `domain-llm-forge` RAG Gateway 또는 `llama-server` 뒤에 붙일 수 있다.
- 기본 local ReAct tool calling은 OpenAI native `tools` payload를 보내지 않고, compact tool schema를 system prompt에 주입한다. `LOCAL_LLM_SEND_NATIVE_TOOLS=true`는 해당 서버가 native tool calling을 실제로 지원하는 경우에만 사용한다.
- `scripts/run_local_finance_sidecar.sh`는 `domain-llm-forge/.env`와 `domain-model-forge/.env`를 값 출력 없이 source한 뒤 `finance_decision_model` RAG Gateway를 띄운다.

### M8.2 Tool Calling / Structured Output 호환

로컬 LLM 전환에서 가장 중요한 부분은 "말을 잘한다"가 아니라 "도구를 정확히 부른다"이다.

| 테스트 축 | 기준 |
|----------|------|
| tool name 정확도 | 존재하지 않는 tool 호출 0건 |
| argument schema | 필수 인자 누락률 1% 미만 |
| JSON/structured output | 파싱 실패율 1% 미만 |
| order intent | `BUY/SELL/HOLD`, symbol, quantity, reason 일관성 |
| 자본 제약 | available/capital_limit 초과 주문 0건 |
| 보유수량 제약 | 미보유/초과 매도 0건 |

필요 기능:

```
1. tool schema를 로컬 LLM 친화 포맷으로 압축
2. invalid tool call 자동 복구 프롬프트
3. JSON repair를 별도 단계로 분리
4. ReAct 실패 시 같은 prompt 무한 반복 금지
5. tool call transcript를 agent_cycles.tool_sequence에 저장
```

현재 구현은 1차 호환성 확보를 위해 description과 parameter schema를 축약해 prompt token을 줄이고,
RAG Gateway가 거부하는 native `tools`/`tool_choice` 필드는 기본 전송하지 않는다.

### M8.3 Local Eval Harness

실전 투입 전, 로컬 LLM은 고정된 평가셋을 통과해야 한다.

| 평가셋 | 목적 | 예시 |
|--------|------|------|
| `capital_constraints` | 자본/현금 제약 준수 | available 28,690 KRW에서 100만원 매수 금지 |
| `position_constraints` | 보유수량 기반 매도 | 005930 2주 보유 시 3주 매도 금지 |
| `reallocation` | 보유자산 매도 후 재배분 판단 | SELL+BUY 비용 하한 계산 후 우위 비교 |
| `no_trade_alpha` | 무리한 거래 회피 | 기대값 음수면 wait/observe |
| `tool_use` | tool 호출 정확도 | get_balance -> get_positions -> evaluate_reallocation |
| `market_session` | 시장 시간 인지 | KRX closed, NXT pre/after, NASDAQ premarket 구분 |
| `futures_guard` | 선물 주문 가드 이해 | live_orders_disabled 상태에서 주문 금지 |
| `hr_autonomy` | CEO 조직 자율성 | 성과 기반 역할 생성/해고 판단 |

출력 지표:

```
pass_rate
schema_valid_rate
tool_call_success_rate
capital_violation_count
hallucinated_tool_count
avg_latency_ms
tokens_or_prompt_chars
estimated_local_cost_krw
decision_quality_score
```

### M8.4 학습 데이터셋 구성

학습은 바로 fine-tuning으로 가지 않는다. 먼저 로그를 평가 데이터로 정리하고, 그 다음 distillation/SFT를 판단한다.

| 데이터 원천 | 사용 목적 |
|------------|----------|
| `agent_cycles` | 실제 prompt, tool sequence, 오류, next_cycle_seconds |
| `decisions` | 매매/비매매/조직 판단 |
| `trades` | 실제 체결 결과와 사후 손익 |
| `positions` | 보유수량/평단/미실현손익 |
| `company_snapshots` | 자본, 현금, 전체 성과 |
| `agent_tools` | 동적 도구 schema와 실행 실패 사례 |
| `logs/live-stock.log` | provider 오류, quota, tool schema 예외 |

데이터셋 split:

```
train: 과거 정상 판단 + tool 성공 사례
dev: edge case, cash 부족, 보유수량 부족, 시장 closed
test: 실전 전용 holdout, 사람이 결과를 보지 않고 최종 QA에만 사용
redteam: 일부러 위험한 주문/잘못된 tool/환각 심볼을 유도
```

라벨링 기준:

| 라벨 | 의미 |
|------|------|
| `valid_action` | 자본/보유수량/시장/도구 schema 제약을 모두 만족 |
| `profitable_after_cost` | 수수료/세금/slippage/AI 비용 후 양수 기대값 |
| `safe_no_trade` | 거래하지 않는 것이 더 나은 판단 |
| `bad_trade` | 기대값, 비용, 제약 중 하나 이상 위반 |
| `bad_tool_call` | tool 이름/인자/순서 오류 |
| `needs_reallocation_eval` | 매수 전 보유자산 매도 비교가 필요한 상황 |

### M8.5 Fine-tuning / Distillation 판단

처음부터 fine-tuning하면 실패 원인 분리가 어렵다. 순서는 다음과 같다.

| 단계 | 방법 | 목적 | 통과 기준 |
|------|------|------|----------|
| 1 | prompt-only | 로컬 모델 기본 능력 측정 | QA pass_rate 70%+ |
| 2 | few-shot | tool/use-case 안정화 | schema_valid_rate 95%+ |
| 3 | RAG/context packing | 과거 사례 참조 | 같은 실수 재발률 감소 |
| 4 | SFT | tool calling/JSON 형식 내재화 | tool_call_success_rate 98%+ |
| 5 | preference/DPO류 | 좋은 판단 vs 나쁜 판단 선호 | decision_quality_score 개선 |
| 6 | quantization 검증 | 운영 비용/속도 최적화 | 품질 하락 3%p 이하 |

학습 대상은 "종목 맞히기"가 아니라 다음 능력이다.

```
1. 자본 제약 읽기
2. tool 순서 선택
3. 보유 포지션 기반 매도 가능 수량 판단
4. 비용 포함 expected edge 비교
5. 불확실하면 거래하지 않는 판단
6. JSON/tool schema 안정 준수
```

### M8.6 운영 모드

| 모드 | 설명 | 주문 가능 여부 |
|------|------|--------------|
| `local_eval` | 고정 QA/eval만 실행 | 불가 |
| `local_paper` | KIS paper 또는 paper adapter | 가능 |
| `local_live_readonly` | 실계좌 조회 + 판단 기록 | 주문 불가 |
| `local_live_guarded` | 실계좌 주문 허용, 기존 가드 유지 | 가능 |
| `hybrid_review` | local 판단 + DeepSeek/다른 모델 교차검증 | 정책에 따라 가능 |

실전 전환 순서:

```
local_eval
 -> local_paper 24h
 -> local_live_readonly 24h
 -> local_live_guarded with tiny order cap
 -> capital 확대는 decision ROI 기준
```

### M8.7 관측성 / 운영 QA

로컬 LLM은 quota는 줄지만, 다른 장애가 생긴다. GPU/메모리/서버 hang/응답 형식 깨짐을 관측해야 한다.

| 관측 항목 | 기록 위치 |
|----------|----------|
| provider/model/backend | `simulation_runs.config` |
| prompt size / output size | `agent_cycles.economics_snapshot` |
| latency_ms | `agent_cycles.economics_snapshot` |
| tool parsing failure | `errors_count`, log |
| local server health | heartbeat log |
| memory pressure | ops log 또는 metrics |
| fallback 발생 | `tool_sequence` 또는 `economics_snapshot` |
| self-recovery action | run log |

Self-recovery 기준:

```
local server down -> stop cycle, report external/local_state, do not trade
invalid JSON repeated -> stop retry, switch to repair/eval path
tool hallucination repeated -> backoff + mark model QA failed
latency too high -> reduce context or switch smaller model
duplicate engine -> stop duplicate immediately
```

## QA 상세 계획

### 0. 고정 QA/RAG 데이터 명세

로컬 에이전트 전환은 먼저 deterministic QA suite로 시작한다.

| 산출물 | 위치 | 용도 |
|--------|------|------|
| QA/eval case registry | `src/agentic_capital/core/local_ai/datasets.py` | 로컬 모델 승격 전 tool/schema/capital 제약 검증 |
| QA 수집 recipe | `qa_collection_recipes()` | `agent_cycles`, `trades`, `positions`, memory에서 SFT/eval record 수집 |
| RAG 데이터 요구사항 | `rag_data_requirements()` | metadata-aware retrieval, reranking, hard negative 구성 |
| 단위 테스트 | `tests/unit/test_local_ai_datasets.py` | QA case coverage와 manifest invariant 보장 |

세부 전략은 `docs/24-local-agent-data-strategy.md`에 둔다.

심리/personality 계층은 finance 판단 모델과 분리한다. 모델별 명세와 절대경로는
`docs/local-psychology-models/10-psychology-model-suite.md`에 둔다. psychology 모델은
personality, emotion, drift, social dynamics, reflection, eval을 담당하지만 직접 주문,
직접 HR action, 자본 제약 변경은 하지 않는다.

### 1. Unit QA

| 테스트 | 목적 |
|--------|------|
| provider config parse | `.env` 기반 provider 선택 |
| local adapter completion | 로컬 서버 mock 응답 처리 |
| tool schema conversion | LangChain tool -> local-compatible schema |
| retry/backoff | local server timeout, 5xx, invalid output |
| JSON repair | 깨진 JSON 복구 가능성 확인 |

### 2. Golden Scenario QA

고정 prompt와 고정 tool 결과를 사용해 모델 출력을 비교한다.

| 시나리오 | 기대 결과 |
|----------|----------|
| 현금 부족 + 보유 주식 있음 | `evaluate_reallocation` 먼저 호출 |
| 현금 부족 + 매도 우위 없음 | `wait` 또는 `observe` |
| 보유수량 초과 매도 유도 | 주문 거절 또는 수량 축소 |
| KRX closed | 국내 주식 신규 주문 회피 |
| quota/server down | backoff, 거래 없음 |
| live_orders_disabled futures | 선물 주문 없음 |

### 3. Backtest QA

로컬 LLM이 느리면 backtest가 병목이 된다. 따라서 두 층으로 나눈다.

| 층 | 설명 |
|----|------|
| deterministic replay | LLM 없이 저장된 판단/도구결과를 재생 |
| sampled LLM replay | 중요한 구간만 로컬 LLM 호출 |

평가 기준:

```
net_pnl_after_cost
turnover
max_drawdown
trade_count
bad_order_count
no_trade_alpha_count
decision_latency_p95
```

### 4. Paper/Live Shadow QA

실전 주문 전, 로컬 LLM은 shadow mode로만 판단한다.

```
real account state -> local LLM decision -> record only
actual order: disabled
compare against:
  1. DeepSeek hosted 판단
  2. rule baseline
  3. buy-and-hold / no-trade baseline
```

최소 통과 기준:

| 지표 | 기준 |
|------|------|
| 자본 제약 위반 | 0 |
| 보유수량 위반 | 0 |
| invalid tool call | 1% 미만 |
| JSON parse failure | 1% 미만 |
| p95 latency | 1시간 주기 내 충분히 여유 |
| shadow decision ROI | baseline보다 악화되지 않음 |

## 기능 요구사항

### 필수 기능

| 기능 | 설명 |
|------|------|
| provider switch | local/DeepSeek/hybrid 선택 |
| local health check | 시작 전 서버/모델 확인 |
| structured tool call | 기존 도구를 로컬 모델이 호출 가능 |
| output repair | JSON/tool call 복구 단계 |
| eval runner | 고정 QA셋 자동 실행 |
| dataset exporter | DB 로그를 학습/eval JSONL로 추출 |
| cost accounting | 외부 API 비용 대신 로컬 추정 비용 기록 |
| shadow mode | 주문 없이 판단만 기록 |

### 선택 기능

| 기능 | 설명 |
|------|------|
| model router | CEO는 큰 모델, Analyst/Trader는 작은 모델 |
| confidence gate | 확신/품질 낮으면 주문 금지 또는 human review |
| model ensemble | local 여러 모델 투표 |
| adaptive context | 시장 상황별 prompt 압축 수준 조정 |
| distillation pipeline | 좋은 DeepSeek/local 판단을 작은 모델에 학습 |

## 리스크와 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| tool calling 약함 | 주문 판단 실패 | schema 압축, few-shot, SFT |
| JSON 깨짐 | cycle 실패 | repair parser, retry 제한 |
| 느린 추론 | 1시간 cadence 훼손 | 모델 크기/quant/context 조정 |
| 환각 tool/symbol | 잘못된 판단 | allowlist와 adapter guard 유지 |
| 과최적화 학습 | backtest만 좋고 live 실패 | holdout/shadow/live-readonly 분리 |
| 로컬 서버 hang | 운영 중단 | health check + self-recovery |
| 장비 비용 무시 | ROI 왜곡 | 전기/장비 amortization 비용 기록 |

## 완료 정의

로컬 LLM 전환은 "로컬 모델이 답했다"가 아니라 아래 조건을 만족해야 완료다.

```
1. local_eval QA pass_rate >= 95%
2. 자본/보유수량/주문 가드 위반 0건
3. local_paper 24h 무중단
4. local_live_readonly 24h 판단 기록 정상
5. 실전 주문 전 shadow decision ROI가 baseline보다 나쁘지 않음
6. 장애 시 self-recovery가 중복 실행/무한 재시도 없이 멈추거나 backoff
7. 모든 provider/model/cost/latency가 DB에 재현 가능하게 기록
```

## 우선순위

1. `LocalOpenAICompatibleAdapter`와 provider 설정
2. tool calling/structured output QA
3. DB 로그 기반 eval dataset exporter
4. local_eval runner와 golden scenarios
5. local_paper 24h soak test
6. local_live_readonly shadow mode
7. 필요 시 SFT/distillation
8. tiny-cap local_live_guarded
