#!/usr/bin/env bash
# Download local LLM GGUF files from Hugging Face when missing, then run the
# local paper-trading stack with separated agent, finance, and psychology models.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/opt/homebrew/bin/llama-server}"
HF_BIN="${HF_BIN:-hf}"
CURL_BIN="${CURL_BIN:-curl}"
SCREEN_BIN="${SCREEN_BIN:-screen}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"
LLAMA_CONTEXT_TOKENS="${LLAMA_CONTEXT_TOKENS:-4096}"
AGENTIC_CAPITAL_MODEL_CACHE="${AGENTIC_CAPITAL_MODEL_CACHE:-$HOME/.cache/agentic-capital/models}"
LOCAL_LLM_RUNTIME_MODE="${LOCAL_LLM_RUNTIME_MODE:-direct}"
FINANCE_DOMAIN_LLM_FORGE_ROOT="${FINANCE_DOMAIN_LLM_FORGE_ROOT:-/Users/tpirates/.codex/worktrees/dd25/domain-llm-forge}"
PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT="${PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT:-/Users/tpirates/workspace-hjm/domain-llm-forge}"
DOMAIN_MODEL_FORGE_ENV="${DOMAIN_MODEL_FORGE_ENV:-/Users/tpirates/workspace-hjm/domain-model-forge/.env}"
START_PAPER_LOOP="${START_PAPER_LOOP:-true}"
START_DOCKER_INFRA="${START_DOCKER_INFRA:-true}"
LOCAL_LLM_AUTO_UPDATE="${LOCAL_LLM_AUTO_UPDATE:-true}"
LOCAL_LLM_HF_REVISION="${LOCAL_LLM_HF_REVISION:-main}"
LOCAL_LLM_FORCE_DOWNLOAD="${LOCAL_LLM_FORCE_DOWNLOAD:-false}"
LOCAL_LLM_RESTART_ON_UPDATE="${LOCAL_LLM_RESTART_ON_UPDATE:-true}"
ACTION="${1:-start}"

AGENT_MODEL_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/agentic_capital_react_model"
AGENT_MODEL_FILE="Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
AGENT_MODEL_PATH="$AGENT_MODEL_DIR/$AGENT_MODEL_FILE"
FINANCE_RAG_QUERY_MODEL_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/finance_rag_query_model"
FINANCE_TOOL_PLANNER_MODEL_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/finance_tool_planner_model"
FINANCE_DECISION_MODEL_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/finance_decision_model"
FINANCE_RISK_GUARD_MODEL_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/finance_risk_guard_model"
PSYCHOLOGY_MODEL_SUITE_DIR="$AGENTIC_CAPITAL_MODEL_CACHE/psychology_model_suite"
FINANCE_RAG_QUERY_MODEL_PATH="$FINANCE_RAG_QUERY_MODEL_DIR/finance_rag_query_model.gguf"
FINANCE_TOOL_PLANNER_MODEL_PATH="$FINANCE_TOOL_PLANNER_MODEL_DIR/finance_tool_planner_model.gguf"
FINANCE_DECISION_MODEL_PATH="$FINANCE_DECISION_MODEL_DIR/finance_decision_model.gguf"
FINANCE_RISK_GUARD_MODEL_PATH="$FINANCE_RISK_GUARD_MODEL_DIR/finance_risk_guard_model.gguf"
PSYCHOLOGY_MODEL_SUITE_PATH="$PSYCHOLOGY_MODEL_SUITE_DIR/psychology_model_suite.gguf"
LOCAL_LLM_MODEL_REFRESHED=false
UPDATED_LLM_SESSIONS=""

log() {
  printf '[local-paper-stack] %s\n' "$*"
}

usage() {
  cat <<'EOF'
usage: scripts/run_local_paper_stack.sh <start|restart|download|health|status|stop>

Actions:
  start     download missing models, start DB/Redis, LLMs, optional gateways, paper loop
  restart   stop known screen sessions, then start
  download  check/apply latest GGUF files from Hugging Face
  health    check local HTTP health endpoints
  status    show screen session presence and health endpoints
  stop      stop known screen sessions only

Safety defaults:
  LLM_PROVIDER=local
  LOCAL_LLM_PROVIDER=local
  KIS_IS_PAPER=true
  FUTURES_LIVE_ORDERS_ENABLED=false

Runtime modes:
  LOCAL_LLM_RUNTIME_MODE=direct      default; independent agentic-capital-only mode
  LOCAL_LLM_RUNTIME_MODE=rag_gateway optional; requires domain-llm-forge run_rag.sh

Model refresh:
  LOCAL_LLM_AUTO_UPDATE=true         check HF latest on start/download
  LOCAL_LLM_HF_REVISION=main         HF branch/tag/commit to resolve
  LOCAL_LLM_FORCE_DOWNLOAD=false     force re-download through HF cache
  LOCAL_LLM_RESTART_ON_UPDATE=true   recycle running local LLM sessions if files changed
EOF
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

hf_offline() {
  truthy "${HF_HUB_OFFLINE:-false}" || truthy "${TRANSFORMERS_OFFLINE:-false}"
}

file_signature() {
  local path="$1"
  if [ ! -s "$path" ]; then
    printf 'missing'
    return 0
  fi
  if stat -f '%z:%m' "$path" >/dev/null 2>&1; then
    stat -f '%z:%m' "$path"
  else
    stat -c '%s:%Y' "$path"
  fi
}

mark_model_refreshed() {
  local session="${1:-}"
  LOCAL_LLM_MODEL_REFRESHED=true
  if [ -n "$session" ]; then
    case " $UPDATED_LLM_SESSIONS " in
      *" $session "*) ;;
      *) UPDATED_LLM_SESSIONS="${UPDATED_LLM_SESSIONS:+$UPDATED_LLM_SESSIONS }$session" ;;
    esac
  fi
}

load_env_file() {
  local env_file="$1"
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

bootstrap_env() {
  load_env_file "$FINANCE_DOMAIN_LLM_FORGE_ROOT/.env"
  load_env_file "$PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT/.env"
  load_env_file "$DOMAIN_MODEL_FORGE_ENV"
  load_env_file "$PROJECT_ROOT/.env"
  export HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "$command_name" >&2
    exit 2
  fi
}

require_file() {
  local path="$1"
  local label="$2"
  if [ ! -f "$path" ]; then
    printf 'error: missing %s: %s\n' "$label" "$path" >&2
    exit 2
  fi
}

download_gguf() {
  local repo_id="$1"
  local include_pattern="$2"
  local output_dir="$3"
  local expected_file="$4"
  local runtime_session="${5:-}"
  local expected_path="$output_dir/$expected_file"

  if [ -s "$expected_path" ] && ! truthy "$LOCAL_LLM_AUTO_UPDATE"; then
    log "model exists; HF latest check disabled: $expected_path"
    return 0
  fi

  if [ -s "$expected_path" ] && hf_offline; then
    log "model exists; HF offline mode skips latest check: $expected_path"
    return 0
  fi

  if [ ! -s "$expected_path" ] && hf_offline; then
    printf 'error: HF offline mode is enabled and local GGUF is missing: %s\n' "$expected_path" >&2
    exit 1
  fi

  require_command "$HF_BIN"
  mkdir -p "$output_dir"
  local before_signature
  before_signature="$(file_signature "$expected_path")"
  local force_download_args=()
  if truthy "$LOCAL_LLM_FORCE_DOWNLOAD"; then
    force_download_args+=(--force-download)
  fi

  log "checking HF latest: $repo_id ($include_pattern) revision=$LOCAL_LLM_HF_REVISION"
  if ! "$HF_BIN" download "$repo_id" --revision "$LOCAL_LLM_HF_REVISION" --include "$include_pattern" --local-dir "$output_dir" --quiet "${force_download_args[@]}"; then
    if [ -s "$expected_path" ]; then
      log "warning: HF latest check failed; using existing GGUF: $expected_path"
      return 0
    fi
    printf 'error: HF download failed and no local GGUF exists: %s\n' "$expected_path" >&2
    exit 1
  fi

  if [ ! -s "$expected_path" ]; then
    printf 'error: HF download finished but expected GGUF is missing: %s\n' "$expected_path" >&2
    exit 1
  fi

  local after_signature
  after_signature="$(file_signature "$expected_path")"
  if [ "$before_signature" != "$after_signature" ]; then
    if [ "$before_signature" = "missing" ]; then
      log "model downloaded: $expected_path"
    else
      log "model updated from HF: $expected_path"
    fi
    mark_model_refreshed "$runtime_session"
  else
    log "model current: $expected_path"
  fi
}

download_models() {
  bootstrap_env

  download_gguf \
    "unsloth/Qwen3-4B-Instruct-2507-GGUF" \
    "$AGENT_MODEL_FILE" \
    "$AGENT_MODEL_DIR" \
    "$AGENT_MODEL_FILE" \
    "local-agent-llm"

  download_gguf "raiss123/finance_rag_query_model-qwen3-1.7b" \
    "finance_rag_query_model.gguf" \
    "$FINANCE_RAG_QUERY_MODEL_DIR" \
    "finance_rag_query_model.gguf" \
    "local-finance-rag-query-llama"

  download_gguf "raiss123/finance_tool_planner_model-qwen3-1.7b" \
    "finance_tool_planner_model.gguf" \
    "$FINANCE_TOOL_PLANNER_MODEL_DIR" \
    "finance_tool_planner_model.gguf" \
    "local-finance-tool-planner-llama"

  download_gguf "raiss123/finance_decision_model-qwen3-4b-instruct-2507" \
    "finance_decision_model.gguf" \
    "$FINANCE_DECISION_MODEL_DIR" \
    "finance_decision_model.gguf" \
    "local-finance-decision-llama"

  download_gguf "raiss123/finance_risk_guard_model-qwen3-1.7b" \
    "finance_risk_guard_model.gguf" \
    "$FINANCE_RISK_GUARD_MODEL_DIR" \
    "finance_risk_guard_model.gguf" \
    "local-finance-risk-guard-llama"

  download_gguf "raiss123/psychology_model_suite-qwen3-4b" \
    "psychology_model_suite.gguf" \
    "$PSYCHOLOGY_MODEL_SUITE_DIR" \
    "psychology_model_suite.gguf" \
    "local-psych-suite-llama"
}

session_exists() {
  local session="$1"
  "$SCREEN_BIN" -ls 2>/dev/null | grep -E "[.]${session}[[:space:]]" >/dev/null 2>&1
}

stop_session() {
  local session="$1"
  if session_exists "$session"; then
    log "stopping screen: $session"
    "$SCREEN_BIN" -S "$session" -X quit
  fi
}

restart_updated_runtime_after_model_refresh() {
  if [ "$LOCAL_LLM_MODEL_REFRESHED" != "true" ]; then
    return 0
  fi
  if ! truthy "$LOCAL_LLM_RESTART_ON_UPDATE"; then
    log "model refresh detected; runtime restart disabled"
    return 0
  fi

  log "model refresh detected; recycling dependent local runtime sessions"
  stop_session "agentic-capital-paper-local"
  if [ "$LOCAL_LLM_RUNTIME_MODE" = "rag_gateway" ]; then
    stop_session "local-finance-rag-query-rag"
    stop_session "local-finance-tool-planner-rag"
    stop_session "local-finance-decision-rag"
    stop_session "local-finance-risk-guard-rag"
    stop_session "local-psych-suite-rag"
  fi
  local session
  for session in $UPDATED_LLM_SESSIONS; do
    stop_session "$session"
  done
}

endpoint_ready() {
  local url="$1"
  "$CURL_BIN" -fsS -m 5 "$url" >/dev/null 2>&1
}

start_llama() {
  local session="$1"
  local model_path="$2"
  local port="$3"
  local alias="$4"

  require_file "$model_path" "GGUF model for $alias"
  if session_exists "$session"; then
    log "screen already running: $session"
    return 0
  fi
  if endpoint_ready "http://$HOST:$port/health"; then
    log "llama endpoint already healthy on port $port for $alias"
    return 0
  fi

  log "starting llama-server: $session port=$port alias=$alias"
  "$SCREEN_BIN" -dmS "$session" "$LLAMA_SERVER_BIN" \
    -m "$model_path" \
    --host "$HOST" \
    --port "$port" \
    -ngl "$N_GPU_LAYERS" \
    -c "$LLAMA_CONTEXT_TOKENS" \
    --alias "$alias"
}

start_gateway() {
  local session="$1"
  local forge_root="$2"
  local service="$3"
  local llama_port="$4"
  local gateway_port="$5"

  require_file "$forge_root/run_rag.sh" "run_rag.sh for $service"
  require_file "$forge_root/config/$service.yaml" "config for $service"
  if session_exists "$session"; then
    log "screen already running: $session"
    return 0
  fi
  if endpoint_ready "http://$HOST:$gateway_port/healthz"; then
    log "RAG gateway already healthy on port $gateway_port for $service"
    return 0
  fi

  log "starting RAG gateway: $session service=$service port=$gateway_port"
  "$SCREEN_BIN" -dmS "$session" env \
    HOST="$HOST" \
    PORT="$gateway_port" \
    LLAMA_SERVER_URL="http://$HOST:$llama_port" \
    LLAMA_MODEL="$service" \
    RAG_SERVICE="$service" \
    DOMAIN_LLM_FORGE_ROOT="$forge_root" \
    RAG_INDEX_DIR="$forge_root/data/rag/$service/index" \
    "$forge_root/run_rag.sh" "$service" serve
}

wait_http() {
  local url="$1"
  local label="$2"
  local timeout_seconds="${3:-90}"
  local started_at
  local now
  local elapsed
  started_at="$(date +%s)"
  while :; do
    if "$CURL_BIN" -fsS -m 5 "$url" >/dev/null 2>&1; then
      log "healthy: $label $url"
      return 0
    fi
    now="$(date +%s)"
    elapsed=$((now - started_at))
    if [ "$elapsed" -ge "$timeout_seconds" ]; then
      printf 'error: health timeout after %ss: %s %s\n' "$timeout_seconds" "$label" "$url" >&2
      return 1
    fi
    if [ "$elapsed" -lt 15 ]; then
      sleep 2
    else
      sleep 5
    fi
  done
}

start_docker_infra() {
  if [ "$START_DOCKER_INFRA" != "true" ]; then
    log "docker infra start skipped"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    log "docker not found; DB/Redis start skipped"
    return 0
  fi
  log "starting DB/Redis with docker compose"
  (cd "$PROJECT_ROOT" && docker compose up -d)
}

start_paper_loop() {
  if [ "$START_PAPER_LOOP" != "true" ]; then
    log "paper loop start skipped"
    return 0
  fi
  if session_exists "agentic-capital-paper-local"; then
    log "screen already running: agentic-capital-paper-local"
    return 0
  fi

  local finance_rag_query_base_url
  local finance_tool_planner_base_url
  local finance_decision_base_url
  local finance_risk_guard_base_url
  local psychology_base_url
  if [ "$LOCAL_LLM_RUNTIME_MODE" = "rag_gateway" ]; then
    finance_rag_query_base_url="http://$HOST:18101/v1"
    finance_tool_planner_base_url="http://$HOST:18102/v1"
    finance_decision_base_url="http://$HOST:8080/v1"
    finance_risk_guard_base_url="http://$HOST:18104/v1"
    psychology_base_url="http://$HOST:19400/v1"
  else
    finance_rag_query_base_url="http://$HOST:18181/v1"
    finance_tool_planner_base_url="http://$HOST:18182/v1"
    finance_decision_base_url="http://$HOST:18183/v1"
    finance_risk_guard_base_url="http://$HOST:18184/v1"
    psychology_base_url="http://$HOST:18080/v1"
  fi

  log "starting Agentic Capital paper loop"
  cd "$PROJECT_ROOT"
  "$SCREEN_BIN" -dmS agentic-capital-paper-local env \
    LLM_PROVIDER=local \
    LOCAL_LLM_PROVIDER=local \
    LOCAL_LLM_BASE_URL="$finance_decision_base_url" \
    LOCAL_LLM_MODEL=finance_decision_model \
    LOCAL_LLM_EXPECTED_HEALTH_MODEL=finance_decision_model \
    LOCAL_AGENT_LLM_BASE_URL="http://$HOST:19000/v1" \
    LOCAL_AGENT_LLM_MODEL=agentic_capital_react_model \
    LOCAL_LLM_TIMEOUT_SECONDS=60 \
    LOCAL_AGENT_LLM_TIMEOUT_SECONDS=90 \
    LOCAL_FINANCE_RAG_QUERY_BASE_URL="$finance_rag_query_base_url" \
    LOCAL_FINANCE_TOOL_PLANNER_BASE_URL="$finance_tool_planner_base_url" \
    LOCAL_FINANCE_DECISION_BASE_URL="$finance_decision_base_url" \
    LOCAL_FINANCE_RISK_GUARD_BASE_URL="$finance_risk_guard_base_url" \
    LOCAL_PSYCHOLOGY_BASE_URL="$psychology_base_url" \
    LOCAL_PSYCHOLOGY_EXPECTED_HEALTH_MODEL=psychology_model_suite \
    KIS_IS_PAPER=true \
    FUTURES_LIVE_ORDERS_ENABLED=false \
    PYTHONPATH=src \
    "$PYTHON_BIN" -m agentic_capital.main
}

start_stack() {
  bootstrap_env
  require_command "$LLAMA_SERVER_BIN"
  require_command "$SCREEN_BIN"
  require_command "$CURL_BIN"
  if [ "$LOCAL_LLM_RUNTIME_MODE" = "rag_gateway" ]; then
    require_file "$FINANCE_DOMAIN_LLM_FORGE_ROOT/run_rag.sh" "finance domain-llm-forge run_rag.sh"
    require_file "$PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT/run_rag.sh" "psychology domain-llm-forge run_rag.sh"
  elif [ "$LOCAL_LLM_RUNTIME_MODE" != "direct" ]; then
    printf 'error: unsupported LOCAL_LLM_RUNTIME_MODE=%s\n' "$LOCAL_LLM_RUNTIME_MODE" >&2
    exit 2
  fi

  download_models
  restart_updated_runtime_after_model_refresh

  start_llama "local-agent-llm" "$AGENT_MODEL_PATH" "19000" "agentic_capital_react_model"
  start_llama "local-finance-rag-query-llama" "$FINANCE_RAG_QUERY_MODEL_PATH" "18181" "finance_rag_query_model"
  start_llama "local-finance-tool-planner-llama" "$FINANCE_TOOL_PLANNER_MODEL_PATH" "18182" "finance_tool_planner_model"
  start_llama "local-finance-decision-llama" "$FINANCE_DECISION_MODEL_PATH" "18183" "finance_decision_model"
  start_llama "local-finance-risk-guard-llama" "$FINANCE_RISK_GUARD_MODEL_PATH" "18184" "finance_risk_guard_model"
  start_llama "local-psych-suite-llama" "$PSYCHOLOGY_MODEL_SUITE_PATH" "18080" "psychology_model_suite"

  wait_http "http://$HOST:19000/health" "agent llama"
  wait_http "http://$HOST:18181/health" "finance rag-query llama"
  wait_http "http://$HOST:18182/health" "finance tool-planner llama"
  wait_http "http://$HOST:18183/health" "finance decision llama"
  wait_http "http://$HOST:18184/health" "finance risk-guard llama"
  wait_http "http://$HOST:18080/health" "psychology suite llama"

  if [ "$LOCAL_LLM_RUNTIME_MODE" = "rag_gateway" ]; then
    start_gateway "local-finance-rag-query-rag" "$FINANCE_DOMAIN_LLM_FORGE_ROOT" "finance_rag_query_model" "18181" "18101"
    start_gateway "local-finance-tool-planner-rag" "$FINANCE_DOMAIN_LLM_FORGE_ROOT" "finance_tool_planner_model" "18182" "18102"
    start_gateway "local-finance-decision-rag" "$FINANCE_DOMAIN_LLM_FORGE_ROOT" "finance_decision_model" "18183" "8080"
    start_gateway "local-finance-risk-guard-rag" "$FINANCE_DOMAIN_LLM_FORGE_ROOT" "finance_risk_guard_model" "18184" "18104"
    start_gateway "local-psych-suite-rag" "$PSYCHOLOGY_DOMAIN_LLM_FORGE_ROOT" "psychology_model_suite" "18080" "19400"

    wait_http "http://$HOST:18101/healthz" "finance rag-query gateway"
    wait_http "http://$HOST:18102/healthz" "finance tool-planner gateway"
    wait_http "http://$HOST:8080/healthz" "finance decision gateway"
    wait_http "http://$HOST:18104/healthz" "finance risk-guard gateway"
    wait_http "http://$HOST:19400/healthz" "psychology suite gateway"
  fi

  start_docker_infra
  start_paper_loop
  log "started local paper stack"
}

stop_stack() {
  stop_session "agentic-capital-paper-local"
  stop_session "local-finance-rag-query-rag"
  stop_session "local-finance-tool-planner-rag"
  stop_session "local-finance-decision-rag"
  stop_session "local-finance-risk-guard-rag"
  stop_session "local-psych-suite-rag"
  stop_session "local-agent-llm"
  stop_session "local-finance-rag-query-llama"
  stop_session "local-finance-tool-planner-llama"
  stop_session "local-finance-decision-llama"
  stop_session "local-finance-risk-guard-llama"
  stop_session "local-psych-suite-llama"
  stop_session "local-agent-llm-recover"
  stop_session "local-psych-suite-llama-recover"
}

health_stack() {
  wait_http "http://$HOST:19000/health" "agent llama" 10
  if [ "$LOCAL_LLM_RUNTIME_MODE" = "rag_gateway" ]; then
    wait_http "http://$HOST:18101/healthz" "finance rag-query gateway" 10
    wait_http "http://$HOST:18102/healthz" "finance tool-planner gateway" 10
    wait_http "http://$HOST:8080/healthz" "finance decision gateway" 10
    wait_http "http://$HOST:18104/healthz" "finance risk-guard gateway" 10
    wait_http "http://$HOST:19400/healthz" "psychology suite gateway" 10
  else
    wait_http "http://$HOST:18181/health" "finance rag-query llama" 10
    wait_http "http://$HOST:18182/health" "finance tool-planner llama" 10
    wait_http "http://$HOST:18183/health" "finance decision llama" 10
    wait_http "http://$HOST:18184/health" "finance risk-guard llama" 10
    wait_http "http://$HOST:18080/health" "psychology suite llama" 10
  fi
}

status_stack() {
  "$SCREEN_BIN" -ls || true
  health_stack || true
}

case "$ACTION" in
  start)
    start_stack
    ;;
  restart)
    stop_stack
    start_stack
    ;;
  download)
    download_models
    ;;
  health)
    health_stack
    ;;
  status)
    status_stack
    ;;
  stop)
    stop_stack
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
