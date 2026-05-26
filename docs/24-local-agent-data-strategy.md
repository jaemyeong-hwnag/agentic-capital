# 로컬 에이전트 QA/RAG 데이터 전략

## 목적

외부 AI API 비용이 에이전트 수 증가와 함께 기하급수적으로 커지는 문제를 줄이기 위해, 로컬 SLM/LLM을 기본 reasoning kernel로 둔다. 단, 목표는 비용 0원이 아니라 `1시간 단위 수익`을 유지하면서 `cost per successful decision`을 낮추는 것이다.

## 최신 연구 반영 요약

최근 소형 모델 에이전트 연구는 schema-first prompting, strict JSON Schema, validator-first tool execution, SLM-default/LLM-fallback 라우팅을 권장한다. Hugging Face paper page의 2025년 SLM survey도 1-12B급 SLM이 schema/API 제약형 agentic workload에서 비용, latency, energy 측면의 강점이 있으며 BFCL, StableToolBench, guided decoding, LoRA/QLoRA를 핵심 축으로 제시한다.

금융 RAG 쪽은 단순 vector search만으로 부족하다. 2025년 금융 RAG 연구들은 metadata filtering, contextual chunk, hybrid retrieval, cross-encoder reranking, small-to-big retrieval이 성능을 좌우한다고 보고한다. 2026년 FinAgent-RAG 논문은 금융 QA에 대해 iterative retrieval-reasoning loop, hard negative mining, Program-of-Thought 계산, adaptive strategy router를 제안하며 비용을 줄이면서 정확도를 보존하는 방향을 제시한다.

QA 데이터 수집은 Self-Instruct류의 synthetic expansion을 쓰되, 프로젝트 특성상 반드시 deterministic validator를 먼저 통과시킨다. 학습 대상은 종목 추천 자체가 아니라 자본 제약, 보유수량, tool schema, 시장 시간, 수수료/AI 비용 반영, RAG evidence grounding이다.

## 구현 위치

- 코드 명세: `src/agentic_capital/core/local_ai/datasets.py`
- 테스트: `tests/unit/test_local_ai_datasets.py`
- 기존 로드맵: `docs/23-local-llm-roadmap.md`

## 테스트 케이스 범위

현재 `local_agent_qa_cases()`는 14개 category와 72개 이상의 deterministic case를 제공한다.

| Category | 목적 |
|---|---|
| `capital_constraint` | 현금, 수수료, 포지션 cap, settlement 제약 위반 방지 |
| `position_constraint` | 미보유/초과 매도, stale position, shorting 금지 |
| `reallocation` | 매수 전 보유자산 매도/교체의 비용 포함 우위 평가 |
| `no_trade_alpha` | 수수료, spread, AI 비용 후 음수 기대값이면 거래 회피 |
| `tool_use` | tool 순서, schema, unknown tool 방지 |
| `market_session` | KRX/NASDAQ/holiday/closing auction/crypto session 인지 |
| `futures_guard` | futures live disabled, leverage, daily loss, volatility guard |
| `hr_autonomy` | 성과 기반 agent 증감원과 역할 생성, 자율성 보존 |
| `rag_retrieval` | metadata filter, hard negative, small-to-big parent retrieval |
| `qa_generation` | cycle trace, trade outcome, counterfactual, dedupe 수집 |
| `cost_control` | agent 폭증, fallback 비용, cache, context 압축 |
| `provider_failure` | local server down, timeout, invalid JSON, fallback 기록 |
| `structured_output` | enum, numeric field, confidence bounds, memory refs |
| `hallucination_defense` | fake symbol/tool/evidence/price 방지 |

## LLM 학습용 QA 수집 방법

1. `agent_cycles`에서 prompt 대신 compact context, tool sequence, final reasoning, error count, provider/model metadata를 QA record로 변환한다.
2. `trades`, `positions`, `company_snapshots`를 join해 `profitable_after_cost`, `bad_trade`, `safe_no_trade`, `decision_roi` label을 붙인다.
3. seed QA case에서 Self-Instruct 방식으로 변형을 만들되, 자본/보유수량/tool schema validator를 먼저 통과시킨다.
4. RAG 문서와 memory에서 answerable, unanswerable, hard-negative, multi-turn 질문을 만들고 evidence id를 보존한다.
5. `train/dev/test/redteam` split을 분리한다. 특히 holdout/test는 학습에 쓰지 않고 로컬 모델 승격 기준으로만 사용한다.

## RAG에 필요한 데이터

`rag_data_requirements()`는 다음 source를 우선 인덱싱 대상으로 정의한다.

- `agent_cycles`: tool sequence, reasoning, errors, economics snapshot, provider/model
- `trades`, `positions`, `company_snapshots`: 체결, 보유, 비용, PnL, confidence
- guardrail/account snapshot: available cash, positions, risk cap, live order flag
- `market_ohlcv`, quote, market calendar: 가격 증거, session, spread, volume
- `memories`, `episodic_details`: semantic/episodic/procedural memory와 outcome
- `agent_tools`: tool schema, enabled flag, last error, schema history
- docs/research/filings/news: symbol, sector, source quality, published time, section metadata

## 승격 기준

로컬 모델은 최소 다음 metric을 통과해야 한다.

- `schema_valid_rate >= 0.99`
- `tool_call_success_rate >= 0.98`
- `capital_violation_count == 0`
- `hallucinated_tool_count == 0`
- `retrieval_recall_at_5`와 `rerank_mrr_at_5`가 기준선 이상
- `cost_per_successful_decision_krw`가 외부 API 대비 우위
- `decision_roi`가 no-trade/rule baseline보다 낮지 않음

## 참고 자료

- Small Language Models for Agentic Systems: A Survey of Architectures, Capabilities, and Deployment Trade offs, 2025: https://huggingface.co/papers/2510.03847
- Retrieval-Augmented Generation: A Comprehensive Survey of Architectures, Enhancements, and Robustness Frontiers, 2025: https://arxiv.org/abs/2506.00054
- Metadata-Driven Retrieval-Augmented Generation for Financial Question Answering, 2025: https://arxiv.org/abs/2510.24402
- Rethinking Retrieval: From Traditional RAG to Agentic and Non-Vector Reasoning Systems in Finance, 2025: https://arxiv.org/abs/2511.18177
- Optimizing Retrieval Strategies for Financial Question Answering Documents in RAG Systems, 2025: https://huggingface.co/papers/2503.15191
- Agentic Retrieval-Augmented Generation for Financial Document Question Answering, 2026: https://arxiv.org/abs/2605.05409
- Self-Instruct: Aligning Language Models with Self-Generated Instructions, 2022/2023: https://arxiv.org/abs/2212.10560
- Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection, 2023: https://arxiv.org/abs/2310.11511
