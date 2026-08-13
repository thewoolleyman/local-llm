#!/bin/bash
# Shared configuration resolution + connectivity checks for the local fleet
# wrappers. Sourced, not executed directly.

: "${LOCAL_LLM_CONFIG_DIR:=$HOME/.config/local-llm}"
: "${LOCAL_LLM_ROUTER_HOST:=macmini}"
: "${LOCAL_LLM_ROUTER_PORT:=8081}"
: "${LOCAL_LLM_ROUTER_API_KEY_FILE:=$LOCAL_LLM_CONFIG_DIR/codex-router-key}"

local_llm_router_base_url() {
  echo "http://${LOCAL_LLM_ROUTER_HOST}:${LOCAL_LLM_ROUTER_PORT}/v1"
}

local_llm_require_router_key() {
  if [ -n "${LOCAL_LLM_ROUTER_API_KEY:-}" ]; then
    export LOCAL_LLM_ROUTER_API_KEY
    return 0
  fi
  if [ ! -f "$LOCAL_LLM_ROUTER_API_KEY_FILE" ]; then
    echo "error: no local LLM router key found at $LOCAL_LLM_ROUTER_API_KEY_FILE" >&2
    exit 1
  fi
  LOCAL_LLM_ROUTER_API_KEY="$(cat "$LOCAL_LLM_ROUTER_API_KEY_FILE")"
  export LOCAL_LLM_ROUTER_API_KEY
}

local_llm_check_router_reachable() {
  local router_url status
  router_url="$(local_llm_router_base_url)"
  status="$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
    -H "Authorization: Bearer ${LOCAL_LLM_ROUTER_API_KEY}" \
    "${router_url}/models" || true)"
  if [ "$status" != 200 ]; then
    echo "error: local LLM fleet router unreachable at ${router_url}" >&2
    echo "  check: is ${LOCAL_LLM_ROUTER_HOST} reachable over Tailscale?" >&2
    echo "  check: is its llama-swap LaunchDaemon running?" >&2
    exit 1
  fi
}
