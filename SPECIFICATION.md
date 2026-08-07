# SPECIFICATION.md

Concrete intents this repo realizes, the deployed implementation, and the
verified client workflow. See [AGENTS.md](./AGENTS.md) for host inventory and
resource policy, and [HANDOFF.md](./HANDOFF.md) for the latest resume snapshot.

## 1. Current deployment

Both model servers, the fleet router, and the client workflows are complete and
were reverified from `chads-macbook-pro` on 2026-08-07.

| Host | Model quant | Server context/concurrency | Client key file | State |
|---|---|---|---|---|
| `macbook-m4-max` | Qwen3-Coder-Next Q6_K, four shards, about 61 GB | 65,536-token unified KV cache; four auto-selected slots | `~/.config/local-llm/api-key` | LaunchDaemon running; API, Codex, and Pi verified |
| `macmini` | Qwen3-Coder-Next Q4_K_M, four shards, 48,410,992,032 bytes | 32,768-token unified KV cache shared by two explicit slots | `~/.config/local-llm/api-key-macmini` | LaunchDaemon running; API, Codex, and Pi verified |

The deployed `llama-server` on both hosts reported llama.cpp version `10280`
(`61881b1f7`) during final verification. The fleet router is llama-swap `v247`.
The clients tested were Codex CLI `0.147.0` and Pi `0.83.0`.

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
Both hosts use `--alias qwen3-coder-next`, so clients use one stable model ID
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

Downloads use `curl -C -` and are resumable. Exact commands are kept in Git
history; no download remains in progress.

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
  owned by `homelab`; it contains the router key and the two upstream
  llama-server keys. It is never committed.
- Launcher: `~/bin/run-llama-swap.sh`.
- Listener: `100.99.172.34:8081`, Tailscale-only; it is not bound to
  `0.0.0.0`.
- Boot service:
  `/Library/LaunchDaemons/local.homelab.llama-swap.plist`, root-owned,
  `UserName=homelab`, `RunAtLoad`, and `KeepAlive`.
- Logs: `~/Library/Logs/llama-swap.log` and
  `~/Library/Logs/llama-swap.error.log`.

The checked-in deployment templates are under
[`deploy/llama-swap/`](./deploy/llama-swap/). The config has two current peers:

| Router model ID | Upstream | Context |
|---|---|---:|
| `macmini/qwen3-coder-next` | `100.99.172.34:8080` / Q4_K_M | 32,768 |
| `m4max/qwen3-coder-next` | `100.125.10.110:8080` / Q6_K | 65,536 |

To add a future host, add a peer entry to the deployed config with its
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

- `bin/codex-local-llm`
- `bin/pi-local-llm`
- shared logic in `bin/lib/local-llm-common.sh`

Both wrappers:

- Default to `macbook-m4-max:8080` and model ID `qwen3-coder-next`.
- Select the matching default API-key file and advertised context window for
  the two known hosts.
- Accept environment overrides without editing the scripts.
- Probe `/v1/models` for readiness, then validate the bearer key with a
  deliberately invalid `{}` request to protected `/v1/chat/completions`. A
  correct key reaches payload validation (`400`) without running inference; a
  wrong key is rejected (`401`).
- Distinguish a key mismatch from an unreachable or unhealthy server and fail
  clearly instead of allowing an opaque downstream connection error.
- Generate isolated client configuration, then `exec` the real CLI with all
  user arguments unchanged.
- Do not mutate `~/.codex/config.toml`, `~/.pi/agent`, or the user's normal
  frontier-provider configuration.

### Codex model metadata

Codex's model name and provider settings are separate from its model metadata.
If a custom model is absent from the startup catalog, Codex emits
`Model metadata for ... not found. Defaulting to fallback metadata`, even when
the endpoint is reachable. The checked-in
[`codex-metadata/model-catalog.json`](./codex-metadata/model-catalog.json)
declares the stable `qwen3-coder-next` model ID with protocol-valid fields,
including the deployed 65,536-token context and local coding-tool capabilities.

`bin/codex-local-llm` writes an absolute `model_catalog_json` entry into its
isolated `CODEX_HOME/config.toml`, so the warning is fixed without touching a
normal Codex installation. A standalone installation can follow
[`codex-metadata/AGENTS.md`](./codex-metadata/AGENTS.md); Codex loads this file
only at startup, so restart after changing the path. The catalog intentionally
contains no API keys, hostnames, or other secrets.

Known-host defaults are:

| `LOCAL_LLM_HOST` | `LOCAL_LLM_API_KEY_FILE` default | `LOCAL_LLM_CONTEXT_WINDOW` default |
|---|---|---:|
| `macbook-m4-max` or any other host | `~/.config/local-llm/api-key` | 65,536 |
| `macmini`, its FQDN, or `100.99.172.34` | `~/.config/local-llm/api-key-macmini` | 32,768 |

Supported overrides:

| Variable | Purpose |
|---|---|
| `LOCAL_LLM_HOST` | Tailscale hostname or IP |
| `LOCAL_LLM_PORT` | llama-server port |
| `LOCAL_LLM_MODEL` | stable API model ID |
| `LOCAL_LLM_CONTEXT_WINDOW` | context size advertised to Codex and Pi; must match server capacity |
| `LOCAL_LLM_API_KEY` | bearer key supplied directly; takes precedence over a file |
| `LOCAL_LLM_API_KEY_FILE` | file containing the selected host's bearer key |
| `LOCAL_LLM_CONFIG_DIR` | parent of the generated isolated Codex/Pi state directories |

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

### Normal use

The M4 Max is the default, so it needs no host override:

```bash
./bin/codex-local-llm
./bin/pi-local-llm
```

Select the Mac mini with one environment variable; its key file and 32K client
context are selected automatically:

```bash
LOCAL_LLM_HOST=macmini ./bin/codex-local-llm
LOCAL_LLM_HOST=macmini ./bin/pi-local-llm
```

Noninteractive examples:

```bash
./bin/codex-local-llm exec 'Explain the current repository'
./bin/pi-local-llm --print 'Explain the current repository'

LOCAL_LLM_HOST=macmini \
  ./bin/codex-local-llm exec 'Run the relevant tests'
LOCAL_LLM_HOST=macmini \
  ./bin/pi-local-llm --print 'Inspect this repository'
```

## 7. Codex-specific configuration

`bin/codex-local-llm` regenerates
`~/.config/local-llm/codex-home/config.toml` on every run and exports that
directory as `CODEX_HOME`. `CODEX_HOME` relocates Codex configuration and state,
so the normal `~/.codex` setup remains untouched.

The generated configuration selects a custom provider with:

- `base_url = "http://<host>:8080/v1"`
- `env_key = "LOCAL_LLM_API_KEY"`
- `wire_api = "responses"`
- `model_context_window` matching the selected server

Current Codex supports only `wire_api = "responses"` for a custom provider.
`wire_api = "chat"` is removed in the installed CLI, not merely deprecated;
the binary emits `wire_api = "chat" is no longer supported.` This is why the
server's `/v1/responses` endpoint is a hard requirement.

The wrapper also sets `model_catalog_json` to the checked-in
`codex-metadata/model-catalog.json`. This supplies protocol-valid metadata for
`qwen3-coder-next`, including the context window and tool capabilities, so the
fallback-metadata warning is not emitted. This setting exists only in the
wrapper's isolated `CODEX_HOME`; the normal `~/.codex/config.toml` is not
changed and ordinary `codex` launches continue using their existing model and
provider settings.

The wrapper deliberately does not set `approval_policy` or `sandbox_mode`.
Interactive Codex therefore retains its own current safety defaults. In final
noninteractive verification, `codex exec` reported `approval: never` together
with `sandbox: read-only`; do not broaden a local model to unapproved host
access merely for convenience.

### Normal Codex fleet profile

The user's normal Codex installation now has a merged catalog at
`~/.codex/model-catalog-with-local.json`. It contains the current frontier
catalog from `~/.codex/models_cache.json` plus the two router-qualified local
entries. `~/.codex/config.toml` points `model_catalog_json` at that merged
file and defines the `local-llm-fleet` provider, so the normal model picker
shows both local router models alongside the frontier models.

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

## 8. Pi-specific configuration

`bin/pi-local-llm` regenerates
`~/.config/local-llm/pi-home/models.json`, exports that directory as
`PI_CODING_AGENT_DIR`, and starts:

```text
pi --model local-llm/qwen3-coder-next <all original arguments>
```

The generated model uses Pi's native `openai-completions` provider against
`/v1/chat/completions`, references `$LOCAL_LLM_API_KEY` instead of writing the
secret into JSON, advertises the selected host's real context window, and caps
individual model output at 8,192 tokens.

## 9. Final verification evidence

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
- Codex and Pi returned `pong` through the default M4 Max wrapper path.
- Codex and Pi returned `pong` through `LOCAL_LLM_HOST=macmini` using automatic
  Mini key/context selection.
- Codex and Pi each successfully used their shell tool to run
  `git rev-parse --short HEAD` and returned the then-current repository commit,
  proving an agent tool loop rather than text completion alone.

Useful repeatable smoke tests:

```bash
./bin/codex-local-llm exec 'Reply with exactly the word: pong'
./bin/pi-local-llm --print 'Reply with exactly the word: pong'

LOCAL_LLM_HOST=macmini \
  ./bin/codex-local-llm exec 'Reply with exactly the word: pong'
LOCAL_LLM_HOST=macmini \
  ./bin/pi-local-llm --print 'Reply with exactly the word: pong'
```

## 10. Resource and safety constraints

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

## 11. Out of scope

- CI runner setup on either `homelab` user.
- Automatic model updates, quant switching, or failover between hosts.
- MLX-based serving.
- Load balancing across the two hosts. Host selection is explicit through
  `LOCAL_LLM_HOST`.
