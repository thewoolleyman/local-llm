# HANDOFF.md

Point-in-time resume snapshot. Read [AGENTS.md](./AGENTS.md) for host and
resource rules and [SPECIFICATION.md](./SPECIFICATION.md) for the complete
deployed design and verification evidence.

## Status at a glance

The two Mac hosts were complete as of 2026-08-06. A third host,
`gmktec-xubuntu`, was added to the pool on 2026-08-29 and verified end-to-end
through the router (see "Adding gmktec-xubuntu" below).

| Host | service user | llama.cpp | Model | Boot service | Router | Gen probe |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `macbook-m4-max` | done | done | Q6_K complete | LaunchDaemon running | live | verified |
| `macmini` | done | done | Q4_K_M complete | LaunchDaemon running | live | verified |
| `gmktec-xubuntu` | done | Vulkan build | Q4_K_M complete | systemd running | live | verified |

No download or setup process was left running on the Macs outside the two
intended `llama-server` LaunchDaemons. The `gmktec-xubuntu` install and its
machine docs live in the `gmktec-xubuntu-info` repo. No CI runner work has been
started.

## Adding gmktec-xubuntu

`gmktec-xubuntu` (AMD Ryzen AI MAX+ 395, Radeon 8060S iGPU, 64 GiB unified,
Ubuntu 26.04, Tailscale `100.79.195.82`) was added as a third
`qwen3-coder-next` peer on 2026-08-29. All three parts are done:

- **This repo (done)**: the `gmktec` peer is in
  `deploy/llama-swap/config.yaml`; the client wrappers, the Codex router
  catalog, and the watchdog include the `gmktec/qwen3-coder-next` model; the
  docs are updated. The Claude picker pins it to the Sonnet alias.
- **`gmktec-xubuntu-info` repo/session (done)**: installed llama.cpp with the
  Vulkan backend (build `b1-d7bd3bf`; RADV exposed ~97 GiB, no GTT/IOMMU tuning
  needed; `spirv-headers` is a hard build dep), Qwen3-Coder-Next Q4_K_M under
  `/home/homelab/models/`, served by a systemd service bound to the Tailscale
  IP on port `8080` (`n_ctx=32768`, two slots, alias `qwen3-coder-next`). The
  bearer key was dropped at `~/.config/local-llm/api-key-gmktec` for pickup.
  The full install is documented in that repo.
- **Live router wiring on `macmini` (done)**: `GMKTEC_LLAMA_KEY` was added to
  `~homelab/.config/llama-swap/secrets.env`, the deployed `config.yaml` was
  refreshed with the `gmktec` peer, and `system/local.homelab.llama-swap` was
  reloaded (over `ssh cwoolley@macmini` + `sudo`). Verified: the router
  `/v1/models` lists all three qualified IDs and a generation request to
  `gmktec/qwen3-coder-next` returned `pong` through the router.

Note: normal client use needs no per-host key — the wrappers reach every peer
through the router with the router key. `~/.config/local-llm/api-key-gmktec` is
only needed to run the watchdog's *direct* probe against `gmktec-xubuntu`;
install it on a client (e.g. `chads-macbook-pro`) if that direct probe is
wanted there.

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

GMKtec EVO-X2 (`gmktec-xubuntu`, live):

- Q4_K_M four-shard model under
  `/home/homelab/models/Qwen3-Coder-Next-Q4_K_M/`.
- Linux/systemd service (not a LaunchDaemon), llama.cpp Vulkan backend
  (build `b1-d7bd3bf`) for the Radeon 8060S iGPU. Deployed at the Mac mini's
  `--ctx-size 32768 --parallel 2 --kv-unified` (verified `n_ctx=32768`, two
  slots). Full install detail lives in the `gmktec-xubuntu-info` repo.
- Requires the bearer key even for `/v1/models` (the Macs leave it public);
  harmless via the router, which injects the peer key.
- Client key: `~/.config/local-llm/api-key-gmktec` (only for direct watchdog
  probes; normal use goes through the router).

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

For `gmktec-xubuntu` (Linux/systemd; unit `local-homelab-llama-server.service`,
service user `homelab`):

```bash
ssh gmktec-xubuntu \
  'sudo systemctl status local-homelab-llama-server.service'
ssh gmktec-xubuntu \
  'sudo journalctl -u local-homelab-llama-server.service -n 50 --no-pager'
```

The exact unit, launcher, and log paths are documented in the
`gmktec-xubuntu-info` repo (`llm-server.md`). As with the Macs, these `ssh`
examples assume the client's `~/.ssh/config` resolves the host to the right
remote user (from `chads-macbook-pro`, `100.79.195.82` requires the key even on
`/v1/models`, so include the bearer key on direct probes).

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

`gmktec-xubuntu` is fully added and verified (server, router wiring, and
generation probe — see "Adding gmktec-xubuntu"). Optional follow-ups: install
`~/.config/local-llm/api-key-gmktec` on `chads-macbook-pro` if direct watchdog
probing of that host is wanted, and consider raising its `--ctx-size`/
`--parallel` since the dedicated box has headroom. Still pending fleet-wide:
Claude live tool-loop verification and recurring per-host watchdog service
deployment. Future CI runners, automatic failover, model updates, and MLX
serving remain explicitly out of scope.
