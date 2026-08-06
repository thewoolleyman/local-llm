#!/bin/bash
# Shared config resolution + connectivity check for bin/codex-local-llm and
# bin/pi-local-llm. Sourced, not executed directly.

: "${LOCAL_LLM_HOST:=macbook-m4-max}"
: "${LOCAL_LLM_PORT:=8080}"
: "${LOCAL_LLM_MODEL:=qwen3-coder-next}"
: "${LOCAL_LLM_API_KEY_FILE:=$HOME/.config/local-llm/api-key}"
: "${LOCAL_LLM_CONFIG_DIR:=$HOME/.config/local-llm}"

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
    echo "  ssh macbook-m4-max-homelab 'cat ~/.llama-server-api-key' > \"$LOCAL_LLM_API_KEY_FILE\"" >&2
    exit 1
  fi
  LOCAL_LLM_API_KEY="$(cat "$LOCAL_LLM_API_KEY_FILE")"
  export LOCAL_LLM_API_KEY
}

local_llm_check_reachable() {
  local base_url
  base_url="$(local_llm_base_url)"
  if ! curl -sf -m 5 -H "Authorization: Bearer ${LOCAL_LLM_API_KEY}" "${base_url}/models" >/dev/null 2>&1; then
    echo "error: local LLM server unreachable at ${base_url}" >&2
    echo "  check: is macbook-m4-max on and reachable over Tailscale? (tailscale status)" >&2
    echo "  check: is the llama-server LaunchDaemon running there?" >&2
    echo "    ssh macbook-m4-max-homelab 'sudo launchctl print system/local.homelab.llama-server' (via cwoolley on that host)" >&2
    exit 1
  fi
}
