#!/bin/bash
# Shared config resolution + connectivity check for bin/codex-local-llm and
# bin/pi-local-llm. Sourced, not executed directly.

: "${LOCAL_LLM_HOST:=macbook-m4-max}"
: "${LOCAL_LLM_PORT:=8080}"
: "${LOCAL_LLM_MODEL:=qwen3-coder-next}"
: "${LOCAL_LLM_CONFIG_DIR:=$HOME/.config/local-llm}"

if [ -z "${LOCAL_LLM_API_KEY_FILE:-}" ]; then
  case "$LOCAL_LLM_HOST" in
    macmini|macmini.*|100.99.172.34)
      LOCAL_LLM_API_KEY_FILE="$HOME/.config/local-llm/api-key-macmini"
      ;;
    *)
      LOCAL_LLM_API_KEY_FILE="$HOME/.config/local-llm/api-key"
      ;;
  esac
fi

if [ -z "${LOCAL_LLM_CONTEXT_WINDOW:-}" ]; then
  case "$LOCAL_LLM_HOST" in
    macmini|macmini.*|100.99.172.34)
      LOCAL_LLM_CONTEXT_WINDOW=32768
      ;;
    *)
      LOCAL_LLM_CONTEXT_WINDOW=65536
      ;;
  esac
fi

case "$LOCAL_LLM_PORT" in
  *[!0-9]*)
    echo "error: LOCAL_LLM_PORT must be numeric (got: $LOCAL_LLM_PORT)" >&2
    exit 1
    ;;
esac

case "$LOCAL_LLM_CONTEXT_WINDOW" in
  *[!0-9]*)
    echo "error: LOCAL_LLM_CONTEXT_WINDOW must be numeric (got: $LOCAL_LLM_CONTEXT_WINDOW)" >&2
    exit 1
    ;;
esac

local_llm_base_url() {
  echo "http://${LOCAL_LLM_HOST}:${LOCAL_LLM_PORT}/v1"
}

local_llm_require_api_key() {
  if [ -n "${LOCAL_LLM_API_KEY:-}" ]; then
    return 0
  fi
  if [ ! -f "$LOCAL_LLM_API_KEY_FILE" ]; then
    echo "error: no local-llm API key found at $LOCAL_LLM_API_KEY_FILE" >&2
    echo "  set LOCAL_LLM_API_KEY, or copy the key from the server:" >&2
    echo "  ssh ${LOCAL_LLM_HOST}-homelab 'cat ~/.llama-server-api-key' > \"$LOCAL_LLM_API_KEY_FILE\"" >&2
    exit 1
  fi
  LOCAL_LLM_API_KEY="$(cat "$LOCAL_LLM_API_KEY_FILE")"
  export LOCAL_LLM_API_KEY
}

local_llm_check_reachable() {
  local auth_status base_url models_status
  base_url="$(local_llm_base_url)"

  models_status="$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
    -H "Authorization: Bearer ${LOCAL_LLM_API_KEY}" \
    "${base_url}/models" || true)"
  if [ "$models_status" != 200 ]; then
    echo "error: local LLM server unreachable at ${base_url}" >&2
    echo "  check: is ${LOCAL_LLM_HOST} reachable over Tailscale? (tailscale status)" >&2
    echo "  check: is its llama-server LaunchDaemon running?" >&2
    echo "    ssh ${LOCAL_LLM_HOST} 'sudo launchctl print system/local.homelab.llama-server'" >&2
    exit 1
  fi

  # llama.cpp intentionally leaves /v1/models readable without a valid key.
  # An empty request to a protected endpoint validates auth without inference:
  # a valid key reaches payload validation (HTTP 400), while a bad key gets 401.
  auth_status="$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
    -H "Authorization: Bearer ${LOCAL_LLM_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{}' "${base_url}/chat/completions" || true)"
  case "$auth_status" in
    400)
      return 0
      ;;
    401|403)
      echo "error: local LLM server at ${base_url} rejected the API key" >&2
      echo "  check that $LOCAL_LLM_API_KEY_FILE contains the key for ${LOCAL_LLM_HOST}" >&2
      ;;
    *)
      echo "error: local LLM server at ${base_url} failed its authentication probe (HTTP ${auth_status})" >&2
      ;;
  esac
  exit 1
}
