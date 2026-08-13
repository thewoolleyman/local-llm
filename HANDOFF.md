# HANDOFF.md

Point-in-time resume snapshot. Read [AGENTS.md](./AGENTS.md) for host and
resource rules and [SPECIFICATION.md](./SPECIFICATION.md) for the complete
deployed design and verification evidence.

## Status at a glance

All requested setup is complete as of 2026-08-06.

| Host | `homelab` user | llama.cpp | Model | LaunchDaemon | API | Codex | Pi |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `macbook-m4-max` | done | done | Q6_K complete | running | verified | verified | verified |
| `macmini` | done | done | Q4_K_M complete | running | verified | verified | verified |

No download or setup process was left running outside the two intended
`llama-server` LaunchDaemons. No CI runner work has been started.

## Normal client use

From this repo on `chads-macbook-pro`, the client wrappers use the fleet router:

```bash
./bin/claude-local-llm
./bin/codex-local-llm
./bin/pi-local-llm
```

Codex starts with `model_provider=local-llm-fleet`, so `/model` can select
either router-qualified model without changing the normal frontier setup. Pi
exposes the same two models through its native model picker/cycling.

The watchdog plan is [tmp/watchdog-plan.md](./tmp/watchdog-plan.md). The
current one-shot observer/recovery command is:

```bash
./bin/local-llm-watchdog --host macmini --recover --interval 10 --samples 3
```

It samples slot progress and probes inference before restarting a host. The
recurring watchdog LaunchDaemon on both hosts is not yet deployed.

Repeatable noninteractive checks:

```bash
./bin/claude-local-llm -p --max-turns 1 'Reply with exactly: pong'
./bin/codex-local-llm exec 'Reply with exactly the word: pong'
./bin/pi-local-llm --print 'Reply with exactly the word: pong'
```

## Current deployed server details

Both hosts:

- llama.cpp `llama-server` version `10280` (`61881b1f7`).
- Port `8080`, bound only to the Tailscale IPv4 address resolved at startup.
- Stable API model ID `qwen3-coder-next`.
- Per-host bearer key at `/Users/homelab/.llama-server-api-key`.
- System service label `local.homelab.llama-server`.

M4 Max:

- Q6_K four-shard model under
  `/Users/homelab/models/Qwen3-Coder-Next-Q6_K/`.
- 65,536-token context; auto-selected four slots; unified KV cache.
- Client key: `~/.config/local-llm/api-key`.

Mac mini:

- Q4_K_M four-shard model under
  `/Users/homelab/models/Qwen3-Coder-Next-Q4_K_M/`.
- All four shards complete; total 48,410,992,032 bytes.
- Wrapper flags include `--ctx-size 32768 --parallel 2 --kv-unified`.
  Explicit `--kv-unified` is necessary because explicit parallel count disables
  llama.cpp's auto-unified behavior. Final log showed two 32K-capable slots
  sharing the unified cache.
- Client key: `~/.config/local-llm/api-key-macmini`.

## If a server is unavailable

Check the actual daemon, then its model-load log:

```bash
ssh macbook-m4-max \
  'sudo launchctl print system/local.homelab.llama-server'
ssh macbook-m4-max-homelab \
  'tail -50 ~/Library/Logs/llama-server.error.log'

ssh macmini \
  'sudo launchctl print system/local.homelab.llama-server'
ssh macmini-homelab \
  'tail -50 ~/Library/Logs/llama-server.error.log'
```

Wait for `model loaded` and `listening on http://<tailscale-ip>:8080` before
testing `/v1/models`. A process can be `running` for roughly a minute while an
uncached model load is still in progress.

If the wrapper reports 401/403, the server is reachable but the selected key is
wrong. Confirm the per-host client key file rather than restarting the daemon.

## Important gotchas

- macOS Remote Login is gated by `com.apple.access_ssh`; a valid key alone is
  insufficient for a newly-created local user. Both `homelab` users are already
  members.
- `macmini` previously slept during setup. Sleep is now disabled (`sleep 0`),
  but recheck `ssh macmini 'pmset -g'` if future unattended work stalls.
- Current Codex custom providers require the Responses API wire format.
  `wire_api = "chat"` is removed. llama.cpp's `/v1/responses` endpoint is
  therefore required.
- Killing a local SSH process does not guarantee a remote child stopped. Check
  and terminate the remote process explicitly when stopping future downloads.
- Fast User Switching does not free `cwoolley`'s memory. Fully log that user out
  before any `homelab` workload heavier or less predictable than steady-state
  inference.

## Locations

- Repo: `AGENTS.md`, `SPECIFICATION.md`, `HANDOFF.md`, `codex-metadata/`, and
  `bin/` wrappers.
- Client secrets/state:
  `~/.config/local-llm/api-key`,
  `~/.config/local-llm/codex-router-key`, and
  `~/.config/local-llm/pi-home/`.
- SSH aliases: `macbook-m4-max-homelab` and `macmini-homelab`.
- Per-host runtime: `~/.homebrew/`, `~/models/`,
  `~/bin/run-llama-server.sh`, `~/.llama-server-api-key`, and
  `~/Library/Logs/llama-server*.log` under `homelab`.
- Root-owned daemon:
  `/Library/LaunchDaemons/local.homelab.llama-server.plist`.

## Remaining work

Claude live tool-loop verification and recurring watchdog LaunchDaemon
deployment remain pending. Future CI runners, automatic failover, model
updates, and MLX serving remain explicitly out of scope.
