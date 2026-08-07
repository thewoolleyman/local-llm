#!/bin/bash
set -euo pipefail

CONFIG_DIR="/Users/homelab/.config/llama-swap"
SECRETS_FILE="$CONFIG_DIR/secrets.env"

if [[ ! -r "$SECRETS_FILE" ]]; then
  echo "llama-swap secrets file is missing or unreadable: $SECRETS_FILE" >&2
  exit 1
fi

# The secrets file is root-readable only by homelab and is never committed.
set -a
# shellcheck disable=SC1090
source "$SECRETS_FILE"
set +a

exec /Users/homelab/.homebrew/bin/llama-swap \
  --config "$CONFIG_DIR/config.yaml" \
  --listen "100.99.172.34:8081"
