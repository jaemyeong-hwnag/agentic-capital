#!/usr/bin/env bash
# Start the domain-llm-forge finance RAG sidecar without copying secrets.

set -euo pipefail

FORGE_ROOT="${DOMAIN_LLM_FORGE_ROOT:-/Users/tpirates/workspace-hjm/domain-llm-forge}"
LLM_ENV="${DOMAIN_LLM_FORGE_ENV:-$FORGE_ROOT/.env}"
MODEL_ENV="${DOMAIN_MODEL_FORGE_ENV:-/Users/tpirates/workspace-hjm/domain-model-forge/.env}"
SERVICE="${RAG_SERVICE:-finance_decision_model}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"

load_env_file() {
  local env_file="$1"
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

load_env_file "$LLM_ENV"
load_env_file "$MODEL_ENV"

export DOMAIN_LLM_FORGE_ROOT="$FORGE_ROOT"
export RAG_SERVICE="$SERVICE"
export RAG_INDEX_DIR="${RAG_INDEX_DIR:-$FORGE_ROOT/data/rag/$SERVICE/index}"
export HOST
export PORT

exec "$FORGE_ROOT/run_rag.sh" "$SERVICE" serve
