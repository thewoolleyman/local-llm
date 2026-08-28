# SPECIFICATION.md

Concrete intents this repo realizes, the deployed implementation, and the
verified client workflow. See [AGENTS.md](./AGENTS.md) for host inventory and
resource policy, and [HANDOFF.md](./HANDOFF.md) for the latest resume snapshot.

## 1. Current deployment

The two Mac model servers, the fleet router, and the client workflows are
complete and were reverified from `chads-macbook-pro` on 2026-08-07. A third
host, `gmktec-xubuntu`, is being added to the pool (see its bring-up status
below).

| Host | Model quant | Server context/concurrency | Client key file | State |
|---|---|---|---|---|
| `macbook-m4-max` | Qwen3-Coder-Next Q6_K, four shards, about 61 GB | 65,536-token unified KV cache; four auto-selected slots | `~/.config/local-llm/api-key` | LaunchDaemon running; API, Codex, and Pi verified |
| `macmini` | Qwen3-Coder-Next Q4_K_M, four shards, 48,410,992,032 bytes | 32,768-token unified KV cache shared by two explicit slots | `~/.config/local-llm/api-key-macmini` | LaunchDaemon running; API, Codex, and Pi verified |
| `gmktec-xubuntu` | Qwen3-Coder-Next Q4_K_M, four shards, ~48 GB | 32,768-token unified KV cache shared by two explicit slots (target; may raise on this dedicated box) | `~/.config/local-llm/api-key-gmktec` | Server bring-up delegated to the `gmktec-xubuntu-info` repo/session; router wiring pending |

The deployed `llama-server` on both Macs reported llama.cpp version `10280`
(`61881b1f7`) during final verification. The fleet router is llama-swap `v247`.
The clients tested were Codex CLI `0.147.0` and Pi `0.83.0`.

`gmktec-xubuntu` is a Linux/amdgpu host, so its install differs from the Macs
(systemd instead of LaunchDaemon, llama.cpp Vulkan/ROCm instead of Metal). Its
machine-specific install, hardware notes, and service definition live in the
separate [`gmktec-xubuntu-info`](https://github.com/thewoolleyman/gmktec-xubuntu-info)
repo, which is edited directly on that machine and auto-committed there. This
repo owns only the fleet router entry, client wrappers, catalogs, and the model
contract for that peer.

## 2. Server architecture

Each host uses the same isolation pattern:

- A dedicated, non-admin `homelab` user owns the model, runtime, API key,
  wrapper, and logs. It does not use or modify `cwoolley`'s files, login items,
  applications, or per-user Homebrew installation.
- llama.cpp is installed in the `homelab` user's isolated Homebrew prefix at
  `~/.homebrew`, not the system `/opt/homebrew` prefix.
- `~/bin/run-llama-server.sh` resolves the host's current Tailscale IPv4 address
  at every start with
  `/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4`. The server binds
  only that address on port `8080`, not `0.0.0.0`.
- `/Library/LaunchDaemons/local.homelab.llama-server.plist` is a root-owned
  system LaunchDaemon with `UserName=homelab`, `RunAtLoad`, and `KeepAlive`.
  It therefore starts at boot and does not depend on a GUI login session.
- Standard output and error go to
  `~/Library/Logs/llama-server.log` and
  `~/Library/Logs/llama-server.error.log` in the `homelab` home.
- Each host has a different random `--api-key`, stored as
  `~/.llama-server-api-key` with mode `0600`. Keys are copied to the client
  outside this repo and must never be committed.

The tailnet transport is Tailscale-encrypted. The llama.cpp endpoint itself is
plain HTTP inside the tailnet. Generation endpoints additionally require the
per-host bearer key; `/v1/models` metadata is intentionally public to the
tailnet process endpoint.

## 3. Model and per-host server flags

The model is
[Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF),
an 80B-total/~3B-active MoE coding model with 256K native context. The deployed
context is deliberately smaller to fit useful concurrency and memory headroom.
All hosts use `--alias qwen3-coder-next`, so clients use one stable model ID
regardless of the host-specific quant.

Qwen3-Coder-Next was confirmed against its primary Hugging Face repository. An
earlier research artifact claimed a smaller model named `GLM-5.2-Air` existed;
during original selection, primary-source checks did not find such a release,
while the real full GLM-5.2 did not fit these hosts. That unverified alternative
is deliberately excluded.

### `macbook-m4-max`

- Model path:
  `~/models/Qwen3-Coder-Next-Q6_K/Qwen3-Coder-Next-Q6_K-00001-of-00004.gguf`
- Quant: Q6_K, four GGUF shards, about 61 GB on disk.
- Important flags:

  ```text
  --ctx-size 65536
  --n-gpu-layers 999
  --flash-attn on
  --alias qwen3-coder-next
  ```

- `--parallel` remains auto (`-1`). The verified startup log reported four
  slots, `n_ctx_slot = 65536`, and `kv_unified = true`.
- Earlier single-stream testing observed about 31 generated tokens/second;
  throughput varies with prompt size, concurrency, and workload.

### `macmini`

- Model path:
  `~/models/Qwen3-Coder-Next-Q4_K_M/Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf`
- Quant: Q4_K_M, four GGUF shards. Final shard sizes were verified against the
  remote HTTP sizes and then accepted by llama.cpp:

  ```text
  15,524,827,040  Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf
  14,872,168,352  Qwen3-Coder-Next-Q4_K_M-00002-of-00004.gguf
  14,503,294,496  Qwen3-Coder-Next-Q4_K_M-00003-of-00004.gguf
   3,510,702,144  Qwen3-Coder-Next-Q4_K_M-00004-of-00004.gguf
  ```

- Important flags:

  ```text
  --ctx-size 32768
  --parallel 2
  --kv-unified
  --n-gpu-layers 999
  --flash-attn on
  --alias qwen3-coder-next
  ```

- `--kv-unified` must be explicit here. llama.cpp enables it automatically when
  slot count is auto, but not when `--parallel 2` is explicit. Without this
  flag, the first startup divided the 32K budget into two 16K slot contexts.
  After correction, the verified log reported two slots,
  `n_ctx_slot = 32768`, and `kv_unified = true`. The two sequences share the
  unified 32K KV capacity.
- The first uncached model load took about 52 seconds. A wrapper should treat
  startup as complete only after `/v1/models` answers, not merely when
  `launchctl` says the process is running.

### `gmktec-xubuntu`

This host is Linux (Ubuntu 26.04 / Xubuntu) on an AMD Ryzen AI MAX+ 395 with a
Radeon 8060S iGPU (RDNA3.5, `gfx1151`) and 64 GiB of unified LPDDR5 shared with
the iGPU — memory-comparable to the Mac mini, so it uses the same quant.

- Model path (target):
  `~/models/Qwen3-Coder-Next-Q4_K_M/Qwen3-Coder-Next-Q4_K_M-00001-of-00004.gguf`
- Quant: Q4_K_M, four GGUF shards, ~48 GB.
- Backend: llama.cpp built with Vulkan (`-DGGML_VULKAN=ON`) for the 8060S iGPU;
  ROCm is an acceptable alternative only if `gfx1151` support is confirmed
  working. The whole model is offloaded (`--n-gpu-layers 999`) against the
  unified memory pool.
- Target flags (mirror the Mac mini; may be raised on this dedicated box):

  ```text
  --ctx-size 32768
  --parallel 2
  --kv-unified
  --n-gpu-layers 999
  --flash-attn on
  --alias qwen3-coder-next
  ```

- `--kv-unified` must be explicit here for the same reason as the Mac mini:
  an explicit `--parallel` disables llama.cpp's automatic unified KV cache.
- Because this is a dedicated headless-style host with no competing desktop
  user (unlike the M4 Max's music workstation), more of the 64 GiB is free, so
  the shipped `--ctx-size`/`--parallel` may be larger than the Mac mini's. The
  actual deployed values are recorded in the `gmktec-xubuntu-info` repo and
  reconciled into §1 once bring-up completes.
- The server binds only the Tailscale IPv4 (resolved via `tailscale ip -4` at
  every start), port `8080`, and requires the per-host bearer key stored
  `0600` at `~/.llama-server-api-key`. It is managed by a systemd unit (the
  Linux equivalent of the Macs' root LaunchDaemon) that restarts on failure
  and starts at boot after `tailscaled`.

Downloads use `curl -C -` and are resumable. Exact commands for the Macs are
kept in this repo's Git history; the `gmktec-xubuntu` download/build/service
commands are kept in the `gmktec-xubuntu-info` repo. No download remains in
progress here.

## 4. API behavior and lifecycle

llama.cpp exposes the OpenAI-compatible endpoints needed by the clients:

- `/v1/models` for reachability and model discovery. llama.cpp intentionally
  serves this metadata even when the bearer key is wrong; it is not an
  authentication test.
- `/v1/chat/completions` for Pi's `openai-completions` provider.
- `/v1/responses` for current Codex CLI. llama.cpp translates Responses API
  requests internally to its chat-completion machinery.

The service is managed as a system daemon:

```bash
ssh macbook-m4-max \
  'sudo launchctl print system/local.homelab.llama-server'
ssh macmini \
  'sudo launchctl print system/local.homelab.llama-server'
```

Logs must be read as `homelab` or through `sudo`:

```bash
ssh macbook-m4-max-homelab \
  'tail -50 ~/Library/Logs/llama-server.error.log'
ssh macmini-homelab \
  'tail -50 ~/Library/Logs/llama-server.error.log'
```

A healthy startup ends with `model loaded` and a Tailscale-only listening URL.
`launchctl` process state alone is insufficient while the model is loading.

## 5. Tailscale fleet router

The Mac mini also runs a `llama-swap` fleet router as the `homelab` user. It
does not replace or duplicate either existing `llama-server`; it proxies their
already-running OpenAI-compatible endpoints and selects the peer from the
requested model ID.

### Deployment

- Binary: `~/.homebrew/bin/llama-swap`, installed from the
  `mostlygeek/llama-swap` Homebrew tap in the `homelab`-owned Homebrew prefix.
- Config: `~/.config/llama-swap/config.yaml`.
- Secret environment file: `~/.config/llama-swap/secrets.env`, mode `0600`,
  owned by `homelab`; it contains the router key and each upstream
  llama-server key (`MACMINI_LLAMA_KEY`, `M4MAX_LLAMA_KEY`, and
  `GMKTEC_LLAMA_KEY`). It is never committed.
- Launcher: `~/bin/run-llama-swap.sh`.
- Listener: `100.99.172.34:8081`, Tailscale-only; it is not bound to
  `0.0.0.0`.
- Boot service:
  `/Library/LaunchDaemons/local.homelab.llama-swap.plist`, root-owned,
  `UserName=homelab`, `RunAtLoad`, and `KeepAlive`.
- Logs: `~/Library/Logs/llama-swap.log` and
  `~/Library/Logs/llama-swap.error.log`.

The checked-in deployment templates are under
[`deploy/llama-swap/`](./deploy/llama-swap/). The config declares three peers:

| Router model ID | Upstream | Context |
|---|---|---:|
| `macmini/qwen3-coder-next` | `100.99.172.34:8080` / Q4_K_M | 32,768 |
| `m4max/qwen3-coder-next` | `100.125.10.110:8080` / Q6_K | 65,536 |
| `gmktec/qwen3-coder-next` | `100.79.195.82:8080` / Q4_K_M | 32,768 |

The `gmktec` peer is checked into the template. It becomes live once the
deployed router config on `macmini` is refreshed from this template **and**
`GMKTEC_LLAMA_KEY` is added to `macmini`'s `~/.config/llama-swap/secrets.env`
(the `gmktec-xubuntu` bearer key, installed out of band). See §6's client-key
steps for retrieving that key; do not commit it.

To add a further host, add a peer entry to the deployed config with its
Tailscale address, an environment-variable reference for its bearer key, and
the model IDs it serves. Keep the corresponding secret only in
`secrets.env`; do not add keys to YAML, plist, Git, or Codex metadata.

### Router checks

Run these from a tailnet client:

```bash
ssh macmini 'sudo launchctl print system/local.homelab.llama-swap'
curl -H "Authorization: Bearer $CODEX_LOCAL_ROUTER_KEY" \
  http://macmini:8081/v1/models
```

`/v1/models` reports the qualified peer IDs. Inference endpoints require the
router bearer key; llama-swap injects the matching upstream key when forwarding
to each peer. The first request to a cold server may take roughly a minute
while its model loads.

## 6. Client wrapper contract

The supported entry points are:

- `bin/claude-local-llm`
- `bin/codex-local-llm`
- `bin/pi-local-llm`
- `bin/local-llm-watchdog`
- shared logic in `bin/lib/local-llm-common.sh`

All wrappers:

- Use the Mac mini fleet router at `macmini:8081` and check its readiness
  before starting the client.
- Expose every router-qualified model (`macmini/`, `m4max/`, and
  `gmktec/qwen3-coder-next`) to the client's native model picker.
- Leave model selection and session state to Codex/Pi instead of forcing a
  model in the wrapper.
- Keep the normal frontier-provider default unchanged.
- Export `LIVESPEC_LOCAL_LLM_WRAPPER` with the wrapper's own resolved
  absolute path. Every wrapper ends in `exec`, which replaces the process
  image, so the wrapper leaves no trace in the launched client's parent
  chain; a supervisor that wants to relaunch the session through the same
  wrapper cannot discover it by walking parents. The environment survives
  `exec`, so this variable is the durable record. It is read by
  livespec-overseer's launch-profile capture and is inert for anything
  that does not look at it. This is a one-directional read of this repo:
  nothing here depends on livespec-overseer.

`bin/claude-local-llm` additionally selects Claude Code's Anthropic Messages
transport against the fleet router, sets a valid local initial model, and
clears competing Anthropic, Bedrock, and Vertex credentials for that process. It
starts Claude Code with `--bare` and an `apiKeyHelper` so the local wrapper never
reads Claude Code's login-Keychain OAuth credentials, then explicitly passes the
user MCP config back with `--mcp-config`.

### Codex model metadata

Codex's model name and provider settings are separate from its model metadata.
If a custom model is absent from the startup catalog, Codex emits
`Model metadata for ... not found. Defaulting to fallback metadata`, even when
the endpoint is reachable. The checked-in
[`codex-metadata/model-catalog.json`](./codex-metadata/model-catalog.json)
declares the stable `qwen3-coder-next` model ID with protocol-valid fields,
including the deployed 65,536-token context and local coding-tool capabilities.

The normal Codex installation supplies the merged model catalog and fleet
provider. The wrapper selects that provider only for its process, so the
normal frontier-provider default remains unchanged.

Supported overrides:

| Variable | Purpose |
|---|---|
| `LOCAL_LLM_ROUTER_HOST` | Tailscale hostname of the fleet router; defaults to `macmini` |
| `LOCAL_LLM_ROUTER_PORT` | Fleet router port; defaults to `8081` |
| `LOCAL_LLM_ROUTER_API_KEY` | Router bearer key supplied directly |
| `LOCAL_LLM_ROUTER_API_KEY_FILE` | File containing the router bearer key |
| `LOCAL_LLM_CONFIG_DIR` | Parent of the generated isolated Pi state directory |

### Client key installation

These files already exist on `chads-macbook-pro`. To rebuild them on another
tailnet client:

```bash
install -d -m 700 ~/.config/local-llm
umask 077
ssh macbook-m4-max-homelab 'cat ~/.llama-server-api-key' \
  > ~/.config/local-llm/api-key
ssh macmini-homelab 'cat ~/.llama-server-api-key' \
  > ~/.config/local-llm/api-key-macmini
chmod 600 ~/.config/local-llm/api-key \
  ~/.config/local-llm/api-key-macmini
```

The `gmktec-xubuntu` server writes its own bearer key to
`~/.config/local-llm/api-key-gmktec` during bring-up (see the
`gmktec-xubuntu-info` repo for the exact source path on that host). This is the
key that must also be installed as `GMKTEC_LLAMA_KEY` in the `macmini` router's
`secrets.env` before the `gmktec` peer can serve traffic.

### Normal use

The wrappers use the fleet router and expose all local models to the native
client picker:

```bash
./bin/claude-local-llm
./bin/codex-local-llm
./bin/pi-local-llm
```

Noninteractive examples:

```bash
./bin/claude-local-llm -p 'Explain the current repository'
./bin/codex-local-llm exec 'Explain the current repository'
./bin/pi-local-llm --print 'Explain the current repository'

./bin/claude-local-llm -p 'Run the relevant tests'
./bin/codex-local-llm exec 'Run the relevant tests'
./bin/pi-local-llm --print 'Inspect this repository'
```

The wrappers are also installed on this Mac as symlinks under
`/usr/local/bin/claude-local-llm`, `/usr/local/bin/codex-local-llm`, and
`/usr/local/bin/pi-local-llm`.

## 7. Codex-specific configuration

`bin/codex-local-llm` selects the already-configured fleet provider with the
process-only equivalent of:

```bash
codex -c model_provider=local-llm-fleet
```

This leaves Codex's normal model catalog, `/model` picker, and session model
state in charge. It does not change the normal `~/.codex/config.toml`.

Current Codex supports only `wire_api = "responses"` for a custom provider.
`wire_api = "chat"` is removed in the installed CLI, not merely deprecated;
the binary emits `wire_api = "chat" is no longer supported.` This is why the
server's `/v1/responses` endpoint is a hard requirement.

The wrapper deliberately does not set `approval_policy` or `sandbox_mode`.
Interactive Codex therefore retains its own current safety defaults. In final
noninteractive verification, `codex exec` reported `approval: never` together
with `sandbox: read-only`; do not broaden a local model to unapproved host
access merely for convenience.

### Normal Codex fleet profile

The user's normal Codex installation now has a merged catalog at
`~/.codex/model-catalog-with-local.json`. It contains the current frontier
catalog from `~/.codex/models_cache.json` plus the router-qualified local
entries (`macmini/`, `m4max/`, and `gmktec/qwen3-coder-next`).
`~/.codex/config.toml` points `model_catalog_json` at that merged
file and defines the `local-llm-fleet` provider, so the normal model picker
shows all local router models alongside the frontier models.

The merged catalog is a local generated artifact rather than a repository
file. When Codex refreshes `models_cache.json` after a client update, rebuild it
with:

```bash
jq --slurpfile local \
  /Users/cwoolley/workspace/local-llm/codex-metadata/local-router-model-catalog.json \
  '.models += $local[0].models' \
  ~/.codex/models_cache.json > ~/.codex/model-catalog-with-local.json
chmod 600 ~/.codex/model-catalog-with-local.json
```

### Provider selection and portable standalone clients

Codex's `model_provider` is a process-level routing setting, separate from the
model catalog. The normal OpenAI/ChatGPT-backed provider must remain the
default for ordinary frontier sessions; setting `model_provider =
"local-llm-fleet"` globally would send an OpenAI model to the local router.
Start a new Codex process to change providers. An already-running interactive
session should not be expected to change its transport/provider mid-session.

The preferred paths are the repository wrapper (`bin/codex-local-llm`) or the
standalone `local-llm` profile above. For a client that already has the
provider definition and catalog, a temporary provider override can be used
without editing the normal config:

```bash
# Force the local provider, then use the model picker.
codex -c model_provider=local-llm-fleet

# Force the normal OpenAI provider, then use the frontier-model picker.
codex -c model_provider=openai
```

`-m` is optional when launching the picker. Use it when a deterministic model
is wanted, for example:

```bash
codex -c model_provider=local-llm-fleet -m m4max/qwen3-coder-next
codex -c model_provider=openai -m gpt-5.6-terra
```

The picker may display catalog entries that are not servable by the selected
provider. Choose a model belonging to the provider forced for that process.
The `--oss` option is for Codex's built-in Ollama/LM Studio paths; it is not
the switch for this Tailscale fleet router.

The `-c model_provider=...` override only selects a named provider; it does
not create that provider. Every standalone client must have a matching
provider definition before the override can work. A client without it fails
early with `Model provider local-llm-fleet not found`. The minimum definition
for a client reaching the Mac mini router is:

```toml
[model_providers.local-llm-fleet]
name = "Local LLM fleet router"
base_url = "http://macmini:8081/v1"
wire_api = "responses"

[model_providers.local-llm-fleet.auth]
command = "cat"
args = ["/home/<client-user>/.config/local-llm/codex-router-key"]
timeout_ms = 1000
```

Replace `<client-user>` with the actual account on that client. Install the
router bearer key out of band with mode `0600`; never commit it. Before
debugging Codex, verify the client can reach the router:

```bash
curl http://macmini:8081/v1/models
```

The model catalog is also client-local. A standalone client may use `-m`
explicitly after defining the provider, but the picker requires the merged
catalog or the checked-in local router catalog to be installed and referenced
in that client's `CODEX_HOME`/config. The repository wrapper handles this
isolation automatically.

Codex's `model_provider` setting is global. It is intentionally not set to
`local-llm-fleet` in the normal config, because that would send the existing
frontier default to the local router. To actually run a local model while
keeping the normal frontier default safe, use the separate profile at
`~/.codex/local-llm.config.toml`:

Start an interactive fleet session with:

```bash
codex --profile local-llm
```

Inside that session, `/models` lists:

```text
macmini/qwen3-coder-next
m4max/qwen3-coder-next
```

The noninteractive smoke test is:

```bash
codex --profile local-llm --ask-for-approval never \
  --sandbox read-only exec 'Reply with exactly the word: pong'
```

The checked-in router catalog is
[`codex-metadata/local-router-model-catalog.json`](./codex-metadata/local-router-model-catalog.json).
Codex loads model catalogs at startup, so restart the session after changing
the catalog or profile.

## 8. Claude Code-specific configuration

`bin/claude-local-llm` starts Claude Code against the fleet router by setting,
for that process only:

```text
ANTHROPIC_BASE_URL=http://macmini:8081
ANTHROPIC_AUTH_TOKEN=<contents of ~/.config/local-llm/codex-router-key>
ANTHROPIC_MODEL=macmini/qwen3-coder-next
ANTHROPIC_SMALL_FAST_MODEL=macmini/qwen3-coder-next
```

The base URL intentionally omits `/v1`; Claude Code appends `/v1/messages`.
This is different from the shared OpenAI-compatible helper used by Codex and
Pi, which returns a `/v1` base. The Claude wrapper must not reuse that full
URL or requests become `/v1/v1/messages` and fail with HTTP 404.
The router exposes the Anthropic Messages endpoint natively, so no translation
proxy is required. Claude Code's session model remains in charge after
startup. The wrapper's initial local model is selectable with
`CLAUDE_LOCAL_MODEL` or `--model`. Claude Code's gateway discovery only keeps
model IDs containing `claude`/`anthropic` (case-insensitive substring), so the
fleet's `qwen3-coder-next` IDs are filtered out of auto-discovery. The wrapper
therefore pins each peer to a built-in alias so all three appear in the native
picker with local display names: the Opus alias to the M4 Max peer, the Sonnet
alias to the GMKtec peer, and the main model plus the one custom entry to the
Mac mini. To choose a specific peer deterministically, use
`--model macmini/qwen3-coder-next`, `--model m4max/qwen3-coder-next`, or
`--model gmktec/qwen3-coder-next` when starting a new session. The wrapper also sets
`CLAUDE_CODE_DISABLE_1M_CONTEXT=1`; the mini has a 32,768-token context and
cannot accept Claude Code's 51,200-token extended-context request. It also
sets `CLAUDE_CODE_MAX_CONTEXT_TOKENS=32768`, because Claude Code otherwise
assumes a larger window for this unrecognized gateway model ID.
Override the initial models with `CLAUDE_LOCAL_MODEL` and
`CLAUDE_LOCAL_SMALL_FAST_MODEL` when needed.

The wrapper unsets `ANTHROPIC_API_KEY`, Bedrock, and Vertex routing variables so
a normal Claude.ai or cloud-provider credential cannot bypass the local router.
It also defaults `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` while using the
local endpoint. Interactive invocations use Claude Code's `--bare` mode to skip
normal keychain reads, but MCP remains enabled by explicitly loading
`~/.claude.json` with `--mcp-config`. Auth in bare mode comes from
`bin/claude-local-llm-api-key-helper`, which reads the local router key file and
prints it for Claude Code's `apiKeyHelper` setting.

Print-mode invocations automatically use
`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`, preventing short smoke
tests from starting long-lived MCP descendants. Set
`CLAUDE_LOCAL_LLM_DISABLE_MCP=0` only when a print-mode session intentionally
needs the normal MCP configuration.

Do not pipe a normal MCP-enabled Claude process into `head`: if the consumer
exits early, MCP descendants can be orphaned and a Keychain helper can leave a
macOS security dialog open. For smoke tests use print mode, which is isolated by
the wrapper. Live Claude tool-loop verification is pending until the model
servers are stable.

## 9. Pi-specific configuration

`bin/pi-local-llm` regenerates
`~/.config/local-llm/pi-home/models.json`, exports that directory as
`PI_CODING_AGENT_DIR`, and starts Pi with the local provider selected:

```text
pi --provider local-llm <all original arguments>
```

The generated provider exposes `macmini/qwen3-coder-next`,
`m4max/qwen3-coder-next`, and `gmktec/qwen3-coder-next`, uses Pi's native
`openai-completions` provider against
the fleet router's `/v1/chat/completions`, resolves the exported
`LOCAL_LLM_ROUTER_API_KEY` through Pi's command-backed `apiKey` configuration
instead of writing the secret into JSON or process arguments, and caps
individual model output at 8,192 tokens. Pi's normal model picker/cycling and
session state remain in charge.

## 10. Watchdog design and current implementation

The full watchdog plan is tracked in
[`tmp/watchdog-plan.md`](./tmp/watchdog-plan.md). It is a planned design for
deployment on `macbook-m4-max`, `macmini`, and `gmktec-xubuntu`; the recurring
per-host watchdog service is not yet installed on any host.

The runnable first implementation is `bin/local-llm-watchdog`. It runs from
the client over SSH and supports:

```bash
./bin/local-llm-watchdog --host macbook-m4-max --once
./bin/local-llm-watchdog --host macmini --recover --interval 10 --samples 3
```

It reads authenticated `/slots` snapshots, compares
`n_prompt_tokens_processed` and nested decoded-token counters between samples,
and runs a one-token authenticated probe. Active counter motion is `busy`; a
restart is only proposed or performed after repeated no-progress samples plus
a failed probe. `--recover` kickstarts only the selected host's
`local.homelab.llama-server`; without it, the script is observation/dry-run.
It does not restart a peer merely because its slots are full.

Dogfooding on 2026-08-12 showed:

- `macbook-m4-max`: no active slots; probe passed; no restart.
- `macmini`: prompt counters advanced and the active slot cleared; probe
  passed; classified as busy/degraded; no restart.

This validates the busy-vs-stuck guard against the current failure mode, where
the process can be running while requests are slow or KV capacity is under
pressure. Remaining work is the plan's dry-run deployment, peer drain,
per-host supervisor installation on every host (root LaunchDaemon on the Macs,
systemd unit on `gmktec-xubuntu`), circuit breaking, and controlled failure
testing.

### Planned watchdog contract for every host

The eventual deployment is one root-owned per-host supervisor (a
`/Library/LaunchDaemons/local.homelab.llama-watchdog.plist` on the Macs, a
systemd unit on `gmktec-xubuntu`). The existing per-host `llama-server` boot
service remains the process supervisor; the watchdog handles
live-but-unhealthy inference. The host targets are `macbook-m4-max:8080` with
four auto-selected 65,536-token slots, `macmini:8080` with two 32,768-token
slots, and `gmktec-xubuntu:8080` with its shipped slot count. The Mac mini's
`local.homelab.llama-swap` router is monitored separately and must not be
restarted merely because one model peer is unhealthy.

The planned state machine is `ready`, `busy`, `degraded`, `stuck`,
`recovering`, and `failed`. `busy` means active slot counters continue moving;
full slots alone are not failure. `stuck` requires an adaptive request-age
budget to be exceeded, no prompt/decode progress for the no-progress window,
an unsuccessful authenticated one-token probe or repeated KV/context/5xx
errors, and the condition recurring for the consecutive sample count. Initial
defaults are a 10-second sample, 60-second no-progress window, three failed
observations, and exponential backoff; these remain configurable until
production timings validate them.

The probe ladder is process/LaunchDaemon state, `/v1/models` readiness,
authenticated one-token generation, then slot/progress and log inspection.
Probes are rate-limited and use the actual host bearer key without logging it.
For confirmed `stuck`, the planned recovery is: drain the peer in llama-swap,
record redacted evidence, cancel/clear work through a supported endpoint when
available, kickstart only that host's `llama-server`, wait for `/v1/models` and
the generation probe, then re-enable the peer. Router recovery is independent.
Repeated failures trip a circuit breaker and leave the peer drained rather than
looping restarts.

The watchdog must never restart solely because a request is long or slots are
occupied; must serialize recovery, use backoff, preserve rotated logs, retain
Tailscale-only binding and secret isolation, and avoid `cwoolley`'s files or
processes. Acceptance requires proving that progressing long prompts remain
busy, wedged servers recover, healthy peers are not restarted, router failures
recover independently, and boot/reboot starts protection on every host.

## 11. Final verification evidence

On 2026-08-07, from `chads-macbook-pro`:

- Both LaunchDaemons were `running` with no crash exit.
- `local.homelab.llama-swap` was `running` as a boot-time LaunchDaemon on
  `macmini`.
- The router `/v1/models` endpoint returned both
  `m4max/qwen3-coder-next` and `macmini/qwen3-coder-next`.
- Both `/v1/models` endpoints returned model ID `qwen3-coder-next`; protected
  generation endpoints separately accepted each host's bearer key.
- `codex --profile local-llm --ask-for-approval never --sandbox read-only exec`
  returned `pong` through the Mac mini router.
- A direct Mac mini `/v1/responses` request returned `pong`.
- Codex and Pi returned `pong` through the fleet router using the router key.
- Codex and Pi each successfully used their shell tool to run
  `git rev-parse --short HEAD` and returned the then-current repository commit,
  proving an agent tool loop rather than text completion alone.

Useful repeatable smoke tests:

```bash
./bin/codex-local-llm exec 'Reply with exactly the word: pong'
./bin/pi-local-llm --print 'Reply with exactly the word: pong'
```

## 12. Resource and safety constraints

Apple Silicon uses unified memory. Fast User Switching does not release the
resident memory held by `cwoolley`'s desktop session. Steady-state inference is
the intended concurrent workload and has been verified. Before running
open-ended heavy jobs such as CI builds, containers, or parallel compilation as
`homelab`, fully log `cwoolley` out as required by [AGENTS.md](./AGENTS.md).

The local open-weight model should be treated as less reliable at tool-policy
discipline than a frontier service. Keep agent approval and sandbox boundaries
in place, review destructive commands, and never expose the server on
`0.0.0.0` or commit either API key.

Operational gotchas already encountered:

- A new macOS local user can accept an SSH public key and still be denied after
  authentication until added to `com.apple.access_ssh`. Both `homelab` users
  are already added.
- `macmini` previously slept during an unattended download. Its system sleep is
  now `0`; recheck `pmset -g` if a future remote job stalls.
- Killing the local side of an SSH session does not prove a remote `curl` or
  `caffeinate` child stopped. Inspect the remote process table explicitly.
- llama.cpp currently warns that its future default port will become `9931`.
  This deployment is unaffected because both wrappers and daemons explicitly
  set port `8080`.

## 13. Out of scope

- CI runner setup on either `homelab` user.
- Automatic model updates, quant switching, or failover between hosts.
- MLX-based serving.
- Automatic load balancing across fleet hosts. Model selection remains
  explicit through each client's native model picker.
