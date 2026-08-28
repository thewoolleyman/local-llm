# HANDOFF.md

Point-in-time resume snapshot. Read [AGENTS.md](./AGENTS.md) for host and
resource rules and [SPECIFICATION.md](./SPECIFICATION.md) for the complete
deployed design and verification evidence.

## Status at a glance

The two Mac hosts were complete as of 2026-08-06. A third host,
`gmktec-xubuntu`, is being added to the pool (see "Adding gmktec-xubuntu" below).

| Host | service user | llama.cpp | Model | Boot service | API | Codex | Pi |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `macbook-m4-max` | done | done | Q6_K complete | LaunchDaemon running | verified | verified | verified |
| `macmini` | done | done | Q4_K_M complete | LaunchDaemon running | verified | verified | verified |
| `gmktec-xubuntu` | in&nbsp;progress | in&nbsp;progress | Q4_K_M (target) | systemd (planned) | pending | pending | pending |

No download or setup process was left running on the Macs outside the two
intended `llama-server` LaunchDaemons. The `gmktec-xubuntu` bring-up is running
in its own repo/session. No CI runner work has been started.

## Adding gmktec-xubuntu

`gmktec-xubuntu` (AMD Ryzen AI MAX+ 395, Radeon 8060S iGPU, 64 GiB unified,
Ubuntu 26.04, Tailscale `100.79.195.82`) is being added as a third
`qwen3-coder-next` peer. Work is split:

- **This repo (done)**: the `gmktec` peer is checked into
  `deploy/llama-swap/config.yaml`; the client wrappers, the Codex router
  catalog, and the watchdog now include the `gmktec/qwen3-coder-next` model;
  the docs are updated. The Claude picker pins it to the Sonnet alias.
- **`gmktec-xubuntu-info` repo/session (delegated, in progress)**: installs
  llama.cpp (Vulkan backend for the iGPU), downloads Qwen3-Coder-Next Q4_K_M,
  serves it as a systemd service bound to the Tailscale IP on port `8080` with
  a per-host bearer key and the `qwen3-coder-next` alias, and documents the
  whole install there. It drops the bearer key at
  `~/.config/local-llm/api-key-gmktec` for pickup.
- **Live router wiring (remaining, needs `macmini` access)**: refresh the
  deployed router config on `macmini` from `deploy/llama-swap/config.yaml`, add
  `GMKTEC_LLAMA_KEY=<gmktec bearer key>` to
  `~/.config/llama-swap/secrets.env`, and reload
  `system/local.homelab.llama-swap`. Then the router `/v1/models` will list
  `gmktec/qwen3-coder-next` and the clients can select it.

## Normal client use

From this repo on `chads-macbook-pro`, the client wrappers use the fleet router:

```bash
./bin/claude-local-llm
./bin/codex-local-llm
./bin/pi-local-llm
```

`./bin/claude-local-llm` uses Claude Code's `--bare` startup plus an
`apiKeyHelper` to avoid login-Keychain credential prompts, and then explicitly
loads the user's MCP config so interactive local Claude sessions still have MCP.
This is deliberate: do not remove MCP as a workaround for keychain prompts.

Codex starts with `model_provider=local-llm-fleet`, so `/model` can select any
router-qualified model without changing the normal frontier setup. Pi exposes
the same models through its native model picker/cycling. Once the `gmktec` peer
is live in the router (see "Adding gmktec-xubuntu"), `gmktec/qwen3-coder-next`
joins `macmini/` and `m4max/qwen3-coder-next` in every client picker.

The watchdog plan is [tmp/watchdog-plan.md](./tmp/watchdog-plan.md). The
current one-shot observer/recovery command is:

```bash
./bin/local-llm-watchdog --host macmini --recover --interval 10 --samples 3
```

It samples slot progress and probes inference before restarting a host, and
now also targets `--host gmktec-xubuntu` (systemd restart) alongside the two
Macs (launchctl). The recurring per-host watchdog service is not yet deployed
on any host.

Repeatable noninteractive checks:

```bash
./bin/claude-local-llm -p --max-turns 1 'Reply with exactly: pong'
./bin/codex-local-llm exec 'Reply with exactly the word: pong'
./bin/pi-local-llm --print 'Reply with exactly the word: pong'
```

## Current deployed server details

Both Macs:

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

GMKtec EVO-X2 (`gmktec-xubuntu`, in progress):

- Q4_K_M four-shard model targeted under
  `~/models/Qwen3-Coder-Next-Q4_K_M/` on that host.
- Linux/systemd service (not a LaunchDaemon), llama.cpp Vulkan backend for the
  Radeon 8060S iGPU. Target flags mirror the Mac mini
  (`--ctx-size 32768 --parallel 2 --kv-unified`), possibly larger since the box
  is dedicated. Actual deployed values are recorded in the `gmktec-xubuntu-info`
  repo and reconciled into SPECIFICATION.md §1 once bring-up completes.
- Client key: `~/.config/local-llm/api-key-gmktec`.

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
  `~/.config/local-llm/api-key` (M4 Max),
  `~/.config/local-llm/api-key-macmini`,
  `~/.config/local-llm/api-key-gmktec`,
  `~/.config/local-llm/codex-router-key`, and
  `~/.config/local-llm/pi-home/`.
- `gmktec-xubuntu` machine-specific install/hardware/service docs live in the
  separate `gmktec-xubuntu-info` repo, not here.
- SSH aliases: `macbook-m4-max-homelab` and `macmini-homelab`.
- Per-host runtime: `~/.homebrew/`, `~/models/`,
  `~/bin/run-llama-server.sh`, `~/.llama-server-api-key`, and
  `~/Library/Logs/llama-server*.log` under `homelab`.
- Root-owned daemon:
  `/Library/LaunchDaemons/local.homelab.llama-server.plist`.

## Remaining work

`gmktec-xubuntu` server bring-up (delegated to its own repo/session) and the
live router wiring on `macmini` (add `GMKTEC_LLAMA_KEY`, refresh the config,
reload `local.homelab.llama-swap`) remain pending; see "Adding gmktec-xubuntu".
Claude live tool-loop verification and recurring per-host watchdog service
deployment also remain pending. Future CI runners, automatic failover, model
updates, and MLX serving remain explicitly out of scope.
