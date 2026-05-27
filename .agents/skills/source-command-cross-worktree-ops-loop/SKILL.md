---
name: "source-command-cross-worktree-ops-loop"
description: "Use automatically when operating, monitoring, improving, restarting, or debugging the local-only paper trading loop across agentic-capital, finance domain-llm-forge, and psychology domain-llm-forge worktrees. Keeps finance/agent/psychology responsibilities separated, reminds each worktree/model/service purpose, runs tests, restarts paper simulation safely, monitors trading plus AI requests/results, and routes fixes to the correct worktree."
---

# source-command-cross-worktree-ops-loop

Use this skill for broad ops loops that touch local paper trading, finance sidecars, psychology sidecars, agent orchestration, monitoring, recovery, or cross-worktree fixes.

## Mandatory Reminder

Before every action, restate this separation to yourself and preserve it in user-facing summaries:

| Area | Worktree | Branch | Definition / Purpose | Must Not Do |
|---|---|---|---|---|
| agentic-capital | `/Users/tpirates/workspace-hjm/agentic-capital` | current project branch | Role-playing investment company runtime: CEO/Analyst/Trader agents, orchestration, tools, recorder, simulation, safety, monitoring. | Do not train/serve domain LLMs here; do not use Gemini; do not bypass paper safety. |
| finance | `/Users/tpirates/.codex/worktrees/dd25/domain-llm-forge` | `codex/rebase-finance-runtime-payloads` | Local GGUF + RAG finance service suite for trading evidence, tool planning, decision payloads, and risk guard. | CEO/Analyst must not use finance decision model as a general LLM; finance must not own organization roleplay. |
| psychology | `/Users/tpirates/.codex/worktrees/3ab4/domain-llm-forge` | `codex/psychology-context-suite` | Local GGUF + RAG psychology service suite for agent state, emotion, drift, bias, conflict, and context-only risk signals. | Must never output or change BUY/SELL, order quantity, order permission, capital allocation, or risk-limit overrides. |

## Local Models / Services

Finance runtime services:

- `finance_rag_query_model`: evidence/RAG query shaping.
- `finance_tool_planner_model`: compact deterministic trading tool plan; fallback order is `search_rag -> get_market_session -> get_balance -> get_positions -> get_quote -> get_risk_limit`.
- `finance_decision_model`: Trader-only finance decision payload generation.
- `finance_risk_guard_model`: risk flags and guard review.
- Health endpoints: `18101`, `18102`, `8080`, `18104`.

Psychology runtime service:

- `psychology_model_suite`: orchestrates profile/emotion/drift/bias/social/memory/reflection signals.
- Runtime use is context-only risk support.
- Health endpoint: `19400`.

Agent runtime:

- `agentic_capital_react_model` on `http://127.0.0.1:19000/v1`.
- CEO/Analyst use this local agent model for strategy, analysis, communication, memory/tool use, and organization behavior.
- Trader alone goes through finance sidecar flow.

## Safe Operating Mode

Always preserve:

```text
LLM_PROVIDER=local
LOCAL_LLM_PROVIDER=local
LOCAL_AGENT_LLM_BASE_URL=http://127.0.0.1:19000/v1
KIS_IS_PAPER=true
FUTURES_LIVE_ORDERS_ENABLED=false
```

Never manually place, cancel, or recover orders. Never switch to Gemini or live futures. Treat duplicate paper engines as a failure.

## Repeating Loop

Run this loop until the user stops it or the automation is no longer useful:

1. Remind yourself of the three worktrees and responsibility boundaries.
2. Monitor the current paper loop broadly:
   - process/runtime: exactly one `agentic_capital.main` process under `screen agentic-capital-paper-local`, PID/etime/cpu/mem, log freshness, DB run status.
   - safety/mode: local provider, no Gemini/RESOURCE_EXHAUSTED, paper KIS, live futures disabled, no duplicate engines.
   - trading/portfolio: KIS balance, available cash, company snapshots, positions, reconciliation, orders/submits/cancels/fills/rejections.
   - AI requests/results: latest `agent_cycles`, `llm_reasoning`, request/response summaries, tool sequence, decisions/errors, next cycle, finance metrics, psychology context.
   - finance sidecars/RAG: health, stage status/status_code/latency/hash/body summary, evidence ids, risk flags, raw model failures.
   - psychology: health, `psychology_evaluation`, schema status, context-only enforcement, missing/unstable signals.
   - market/tooling: quotes, open markets, KIS/yfinance failures, dynamic tools.
   - guards/recovery: zero-decision streak, stop diagnostics, pacing clamp, cause classification, safe next action.
3. Classify each issue by first failing area:
   - `agentic_capital`: orchestration, DB recording, role routing, tool exposure, simulation safety, monitoring, KIS adapter, paper loop.
   - `finance`: RAG retrieval, finance tool planner, decision payload shape, risk guard, finance model/RAG service behavior.
   - `psychology`: schema instability, missing evidence ids, disallowed action leakage, context-only contract, psychology RAG/model behavior.
   - `external`: broker/API/network/rate limit.
   - `safety`: live mode, duplicate engines, unauthorized order path.
4. Apply fixes in the owning worktree only. Do not mix finance, psychology, and agentic-capital commits.
5. Test in the owning worktree. For agentic-capital use:
   `pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80`
6. Restart local-only paper simulation only after tests pass and only with paper/live-safety env intact.
7. Monitor again and compare before/after. If healthy, stay quiet unless a heartbeat asks for a report; if risky, notify with evidence.

## Routing Examples

- CEO/Analyst produce trade-like or hallucinated order text: fix in `agentic-capital` prompts/validators/tool exposure; optionally improve agent model later, but do not send them to finance decision model.
- Trader finance record lacks `sidecar_stage_metrics`, `first_failing_stage`, compact payload hashes, or `no_trade_reason`: fix in `agentic-capital` runtime/recorder unless the model/RAG response itself is malformed.
- Finance planner sends incomplete or malformed tool plans despite compact payload: fix in finance worktree service/model/RAG, then adapt agentic-capital only if the contract changed.
- Psychology returns non-JSON, missing evidence, action/quantity/capital leakage, or weak `schema_status`: fix psychology worktree service/model/RAG; keep agentic-capital repair/recording as a safety net.
- KIS/yfinance rate limits or broker failures: classify as external/local_state; do not manually trade to recover.

## Completion Evidence

Every report should include:

- worktree boundaries remembered,
- tests run and result,
- current run id and process evidence,
- trading/portfolio/order summary,
- AI request/result summary,
- finance and psychology sidecar health,
- first failing area and next safe action.
