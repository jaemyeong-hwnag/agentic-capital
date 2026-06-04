---
name: "source-command-local-paper-stack"
description: "Use automatically when starting, restarting, downloading, validating, documenting, or debugging the independent local LLM + Agentic Capital paper trading stack from this project. Covers HF GGUF download, llama-server direct mode, optional domain-llm-forge RAG gateway mode, safe local env, DB/Redis, screen sessions, runtime health, and paper/mock trading verification."
---

# source-command-local-paper-stack

Use this skill when the user asks to run this project with local LLMs, download models from Hugging Face, start or restart paper trading, make the project independently runnable, or explain the local runtime setup.

## Boundary

Default to independent `agentic-capital` execution. Do not require local `domain-llm-forge` worktrees unless the user explicitly chooses `LOCAL_LLM_RUNTIME_MODE=rag_gateway`.

Always preserve:

```text
LLM_PROVIDER=local
LOCAL_LLM_PROVIDER=local
KIS_IS_PAPER=true
FUTURES_LIVE_ORDERS_ENABLED=false
```

Never place manual orders to prove execution. Paper orders must come from the running local paper loop.

## Main Command

From `/Users/tpirates/workspace-hjm/agentic-capital`:

```bash
./scripts/run_local_paper_stack.sh start
```

Actions:

```bash
./scripts/run_local_paper_stack.sh download
./scripts/run_local_paper_stack.sh health
./scripts/run_local_paper_stack.sh status
./scripts/run_local_paper_stack.sh restart
./scripts/run_local_paper_stack.sh stop
```

## Runtime Modes

Default:

```bash
LOCAL_LLM_RUNTIME_MODE=direct ./scripts/run_local_paper_stack.sh start
```

`direct` mode downloads GGUF files into `~/.cache/agentic-capital/models`, starts each model with `llama-server`, and points Agentic Capital directly at `/v1/chat/completions`.

By default, `start` and `download` also check Hugging Face for the latest configured GGUF revision before runtime startup:

```bash
LOCAL_LLM_AUTO_UPDATE=true
LOCAL_LLM_HF_REVISION=main
LOCAL_LLM_RESTART_ON_UPDATE=true
```

If a model file changes while local sessions are already running, allow the runner to recycle the affected `llama-server` session and `agentic-capital-paper-local` so the new GGUF is actually loaded. Use `LOCAL_LLM_AUTO_UPDATE=false` only for intentional offline/cache-only operation.

Optional compatibility mode:

```bash
LOCAL_LLM_RUNTIME_MODE=rag_gateway ./scripts/run_local_paper_stack.sh start
```

Use this only when local `domain-llm-forge` roots exist and RAG gateway `/healthz` plus `/search` behavior is required.

## HF Token

The script reads env files in this order:

1. finance domain-llm-forge `.env` if present
2. psychology domain-llm-forge `.env` if present
3. domain-model-forge `.env` if present
4. current project `.env`

Current project `.env` wins. `HF_TOKEN` is preferred; if empty, `HUGGINGFACE_TOKEN` is mapped to `HF_TOKEN` at runtime. Never print or commit token values.

## Required Checks

After start/restart:

1. Run `./scripts/run_local_paper_stack.sh health`.
2. Confirm exactly one `agentic_capital.main` process under `agentic-capital-paper-local`.
3. Check DB evidence: latest `simulation_runs`, `agent_cycles`, `agent_decisions`, `trades`, `positions`, `company_snapshots`.
4. Classify paper execution as `AI_DIRECT_PAPER_TRADE`, `PAPER_RECOVERY_OR_SCOUT_TRADE`, or `NO_PAPER_TRADE`.

## Docs

Primary runbook:

```text
docs/30-local-paper-stack-runbook.md
```

Env reference:

```text
docs/15-env-variables.md
```
