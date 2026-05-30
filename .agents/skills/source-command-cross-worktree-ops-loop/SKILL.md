---
name: "source-command-cross-worktree-ops-loop"
description: "Use automatically when operating, monitoring, improving, restarting, testing, or debugging the local-only paper trading loop, paper/mock trading, AI trading decisions, sidecar health, agent cycles, order/fill recording, or cross-worktree fixes across agentic-capital, finance domain-llm-forge, and psychology domain-llm-forge. Reminds each worktree/model/service purpose every check, preserves finance/agent/psychology separation, monitors trading plus AI requests/results broadly, runs tests, restarts only safe local paper services, and routes fixes to the owning worktree."
---

# source-command-cross-worktree-ops-loop

Use this skill for broad ops loops that touch local paper trading, mock/paper execution, finance sidecars, psychology sidecars, agent orchestration, AI decision quality, monitoring, recovery, or cross-worktree fixes. The loop is proactive: observe broadly, classify first failing area, fix in the owning worktree, test, restart only affected local paper services, then observe again.

## Mandatory Reminder

Before every action, restate this separation to yourself and preserve it in user-facing summaries:

| Area | Worktree | Branch | Definition / Purpose | Must Not Do |
|---|---|---|---|---|
| agentic-capital | `/Users/tpirates/workspace-hjm/agentic-capital` | current project branch | Role-playing investment company runtime: CEO/Analyst/Trader agents, orchestration, tools, recorder, simulation, safety, monitoring. | Do not train/serve domain LLMs here; do not use Gemini; do not bypass paper safety. |
| finance | `/Users/tpirates/.codex/worktrees/dd25/domain-llm-forge` | `codex/rebase-finance-runtime-payloads` | Local GGUF + RAG finance service suite for trading evidence, tool planning, decision payloads, and risk guard. | CEO/Analyst must not use finance decision model as a general LLM; finance must not own organization roleplay. |
| psychology | `/Users/tpirates/.codex/worktrees/3ab4/domain-llm-forge` | `codex/psychology-context-suite` | Local GGUF + RAG psychology service suite for agent state, emotion, drift, bias, conflict, and context-only risk signals. | Must never output or change BUY/SELL, order quantity, order permission, capital allocation, or risk-limit overrides. |

Carry this reminder into every check. Do not silently move code across boundaries: if a defect belongs to finance, edit only the finance worktree; if it belongs to psychology, edit only the psychology worktree; if it belongs to runtime/orchestration/recording/safety, edit only agentic-capital.

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

Operational boundaries:

- AI-driven orders may only come from the running local paper loop under paper safety env.
- KRX stock orders route to KIS paper. Overseas spot orders route through local `PAPER-OVS` recording. Explicit call-only KR options route through local `PAPER-CALL`; puts, ambiguous options, and sell-open options must be rejected or held unless a future defined-risk adapter explicitly supports them.
- Recovery/scout orders must not bypass finance decision quality. If the finance decision is missing, looping, low-confidence, or lacks a clear edge, the safe result is `HOLD`/`WAIT` with `would_submit_order=false`.

## Repeating Loop

Run this loop until the user stops it or the automation is no longer useful:

1. Remind yourself of the three worktrees and responsibility boundaries.
2. Monitor the current paper loop broadly; do not reduce monitoring to liveness:
   - process/runtime: exactly one `agentic_capital.main` process under `screen agentic-capital-paper-local`, PID/etime/cpu/mem, log freshness, DB run status.
   - safety/mode: local provider, no Gemini/RESOURCE_EXHAUSTED, paper KIS, live futures disabled, no duplicate engines.
   - trading/portfolio: KIS balance, available cash, company snapshots, positions by market/product, reconciliation, orders/submits/cancels/fills/rejections, latest BUY/SELL/HOLD decisions, realized/unrealized PnL.
   - AI requests/results: latest `agent_cycles`, `llm_reasoning`, request/response summaries, tool sequence, tool calls count, decisions/errors, next cycle, economics snapshot metadata, finance record type, `sidecar_latency_ms`, `first_failing_stage`, and model output repair status.
   - finance sidecars/RAG: ports `18101`, `18102`, `8080`, `18104`; health/process evidence; stage status/status_code/latency/hash/body summary; evidence ids/count; risk flags; raw model failures; prompt/postprocess/RAG regressions.
   - psychology: health, `psychology_evaluation`, schema status, context-only enforcement, missing/unstable signals.
   - market/tooling: quotes, open markets, KIS/yfinance failures, dynamic tools.
   - guards/recovery: zero-decision streak, stop diagnostics, pacing clamp, duplicate engines, stale DB-running simulations, cause classification, safe next action.
   - schedules/automations: identify obsolete or noisy Codex automations, but delete/update them only when the user asked or the heartbeat task is done.
3. Classify each issue by first failing area:
   - `agentic_capital`: orchestration, DB recording, role routing, tool exposure, simulation safety, monitoring, KIS adapter, paper loop.
   - `finance`: RAG retrieval, finance tool planner, decision payload shape, risk guard, finance model/RAG service behavior.
   - `psychology`: schema instability, missing evidence ids, disallowed action leakage, context-only contract, psychology RAG/model behavior.
   - `external`: broker/API/network/rate limit.
   - `safety`: live mode, duplicate engines, unauthorized order path.
4. Apply fixes in the owning worktree only. Do not mix finance, psychology, and agentic-capital commits.
5. Test in the owning worktree. Use focused tests first when diagnosing, then broader tests before finalizing. For agentic-capital use:
   `pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80`
6. Restart only the affected local service after tests pass:
   - finance model/RAG/service fix: restart only the affected finance sidecar or GGUF service.
   - psychology model/RAG/service fix: restart only the affected psychology sidecar or GGUF service.
   - agentic-capital runtime/safety/recorder fix: restart the paper loop only with paper/live-safety env intact.
7. Run or continue the local paper simulation and monitor actual DB/log evidence. Confirm whether new decisions produced orders, fills, rejections, or no-trade outcomes. Never place manual orders to prove execution.
8. Monitor again and compare before/after. If healthy, stay quiet unless a heartbeat asks for a report; if risky, notify with concise evidence and the safe action taken or next action.

## Routing Examples

- CEO/Analyst produce trade-like or hallucinated order text: fix in `agentic-capital` prompts/validators/tool exposure; optionally improve agent model later, but do not send them to finance decision model.
- Trader finance record lacks `sidecar_stage_metrics`, `first_failing_stage`, compact payload hashes, or `no_trade_reason`: fix in `agentic-capital` runtime/recorder unless the model/RAG response itself is malformed.
- Finance planner sends incomplete or malformed tool plans despite compact payload: fix in finance worktree service/model/RAG, then adapt agentic-capital only if the contract changed.
- Psychology returns non-JSON, missing evidence, action/quantity/capital leakage, or weak `schema_status`: fix psychology worktree service/model/RAG; keep agentic-capital repair/recording as a safety net.
- KIS/yfinance rate limits or broker failures: classify as external/local_state; do not manually trade to recover.

## Decision Quality Guardrails

- A trade is AI-direct only when the latest finance decision has explicit `BUY`/`SELL`, supporting evidence/tool ids, risk guard approval, `would_submit_order=true`, and a recorded paper-only order/fill or rejection.
- `WAIT`, `HOLD`, `CALL_TOOL`, `NO_CONTEXT`, raw model failure, or repaired low-confidence output must not be treated as a trading edge.
- If complete runtime tools exist but the finance model asks for more tools repeatedly, fix finance postprocess/prompt/RAG and convert the runtime result to no-trade, not a scout order.
- For call options, require at least one premium-overcoming edge: fast delta move, IV expansion, or structural cost reduction. If unclear, hold.

## Completion Evidence

Every report should include:

- worktree boundaries remembered,
- tests run and result,
- current run id and process evidence,
- trading/portfolio/order summary,
- AI request/result summary,
- finance and psychology sidecar health,
- first failing area and next safe action.

Auto activation validation after updates:

- description trigger must mention monitoring, paper/mock trading, AI requests/results, sidecars, and cross-worktree fixes.
- command-free selection should work when the user asks to monitor, run paper trading, fix decision model, check AI buy/sell, restart sidecars, or separate finance/psychology/agentic-capital work.
- dependency availability is satisfied by local shell, pytest, screen, DB access, and the three worktree paths above.
