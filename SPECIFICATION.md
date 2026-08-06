# SPECIFICATION.md

Concrete intents this repo is meant to realize, and how they were actually
implemented. See [AGENTS.md](./AGENTS.md) for background/goal and
per-host details, and [HANDOFF.md](./HANDOFF.md) for current
point-in-time status/next-steps.

## 1. Coder model server (implemented on `macbook-m4-max`, replicated on `macmini`)

- Runs under a **dedicated, non-admin "homelab" user** on `macbook-m4-max`,
  separate from the `cwoolley` account (which is a desktop / music
  production workstation and should not be touched by this).
  - The homelab user has its own clean `~/Library/LaunchAgents` (no
    Dropbox/Google Drive/Roland Cloud/Akai autostart, etc.) and its own
    SSH keys / tooling, isolated from `cwoolley`'s files, browser
    sessions, and DAW projects.
- The server itself runs as a **LaunchDaemon** (`/Library/LaunchDaemons`),
  not a per-user LaunchAgent — so it starts at boot and stays up
  regardless of whether anyone is logged into the GUI console (e.g. while
  `cwoolley` is doing music production), running as the homelab user via
  the plist's `UserName` key, with `RunAtLoad` + `KeepAlive`.
- **Server software**: `llama.cpp`'s `llama-server` (installed via a
  per-`homelab`-user Homebrew prefix at `~/.homebrew`, not
  `/opt/homebrew`), exposing an OpenAI-compatible API. It also exposes
  `/v1/responses` (added recently to llama.cpp — translated internally to
  chat completions), which is required for Codex (see §2).
- **Model**: [Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF)
  (80B total / ~3B active MoE, 256K native context), verified real and
  actively maintained — not to be confused with unverifiable/hallucinated
  model claims (a "GLM-5.2-Air" was researched and debunked during
  planning; the real GLM-5.2 needs 256GB+ and doesn't fit either host).
  Quant is sized per host's unified memory:
  - `macbook-m4-max` (128GB): **Q6_K**, 4-part GGUF, ~61GB on disk.
  - `macmini` (64GB): **Q4_K_M**, 4-part GGUF, ~48.5GB on disk (lighter
    quant needed to leave headroom in the smaller memory budget).
  - Downloaded directly from Hugging Face via `curl -C -` (resumable —
    safe to re-run the same command after any interruption; see
    HANDOFF.md for exact per-host commands).
  - Server started with `--alias qwen3-coder-next` so the model ID is
    stable across hosts/quants — this is the ID the client wrapper
    scripts default to.
- **`--ctx-size` / `--parallel`**: `-np/--parallel` defaults to `-1`
  (auto) and `llama-server` picks a slot count itself; with
  `kv_unified=true` each slot got the *full* `--ctx-size`, not a divided
  share, which was more generous than expected. Given `macmini`'s
  tighter memory budget, its config sets `--parallel 2` explicitly rather
  than relying on auto-selection. See HANDOFF.md for the exact flags
  used per host and real observed throughput (~31 tok/s single-stream on
  `macbook-m4-max`).
- **Network exposure**: bind to the host's Tailscale IP specifically
  (not `0.0.0.0`), resolved at every startup via the Tailscale CLI
  (`/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4`) so it
  survives IP changes — not hardcoded. Port `8080` on both hosts (no
  conflict since they're different hosts).
- **Auth**: `llama-server --api-key`, a random key generated during setup
  (`openssl rand -hex 32`) and stored at `~/.llama-server-api-key`
  (chmod 600) on each host's `homelab` user. Client machines need a copy
  at `~/.config/local-llm/api-key` (outside this repo, never committed —
  see §2).
- **Startup**: a small wrapper script (`~/bin/run-llama-server.sh` on
  each host's `homelab` user) resolves the Tailscale IP and reads the API
  key at every launch, then `exec`s `llama-server` with the flags above.
  A `LaunchDaemon` (`/Library/LaunchDaemons/local.homelab.llama-server.plist`,
  `RunAtLoad`+`KeepAlive`, `UserName homelab`) runs that script — this is
  what makes it start at boot and survive independent of any GUI login
  state. Load with `sudo launchctl bootstrap system <plist path>`;
  logs go to `~/Library/Logs/llama-server.log` / `.error.log` under the
  `homelab` user (only readable as that user or via `sudo`).

## 2. Client-side wrapper scripts

Two scripts, checked into this repo under `bin/`, meant to be run from
any machine on the tailnet (e.g. `chads-macbook-pro`) that has `codex`
or `pi` installed:

- **`bin/codex-local-llm`**
- **`bin/pi-local-llm`**

Behavior common to both:

- Default to pointing at the model server on `macbook-m4-max` over
  Tailscale (host defaults to the Tailscale MagicDNS name; port and
  model name have sane defaults) — no manual config editing required to
  just run them.
- All of host/port/model/API key are overridable via environment
  variables, so the same scripts work if the model moves to a different
  host or port.
- Inject whatever provider config the wrapped CLI needs to talk to an
  OpenAI-compatible endpoint (base URL, auth token, model name/remap,
  wire format) **without mutating the user's normal global config** for
  that CLI — e.g. via a dedicated config directory/profile the script
  generates or updates, pointed to by an env var the CLI supports
  (such as `CODEX_HOME` for Codex), rather than editing
  `~/.codex/config.toml` or Pi's default config in place. This keeps a
  normal `codex`/`pi` invocation (pointed at a real frontier model)
  unaffected.
- After preparing config, `exec` the real `codex`/`pi` binary, passing
  through all script arguments untouched, so the wrapper is otherwise
  transparent to the user.
- Fail with a clear error (not a silent fallback) if the model server is
  unreachable, rather than letting the underlying CLI fail with an
  opaque connection error.

Both scripts share config resolution + the reachability check via
`bin/lib/local-llm-common.sh`. Defaults: `LOCAL_LLM_HOST=macbook-m4-max`,
`LOCAL_LLM_PORT=8080`, `LOCAL_LLM_MODEL=qwen3-coder-next`, API key read
from `LOCAL_LLM_API_KEY` env var or `~/.config/local-llm/api-key` file.
**To point at `macmini` instead, override `LOCAL_LLM_HOST=macmini`** (and
copy that host's API key to the key file, or pass `LOCAL_LLM_API_KEY`) —
no code changes needed, this was already supported by the env-var design,
just not exercised yet for a second host.

Implementation specifics discovered while building this (verified against
the actual installed CLI binaries, not just docs):

- **Codex**: `wire_api = "chat"` was confirmed **removed** (not just
  deprecated) in the currently-installed Codex CLI (v0.146.0) — the
  string `"wire_api = \"chat\"" is no longer supported.` is literally in
  the binary. Must use `wire_api = "responses"`, which works because
  `llama.cpp`'s server added `/v1/responses` support. Config is written
  to an isolated `CODEX_HOME` (`~/.config/local-llm/codex-home/config.toml`,
  regenerated on every run) — confirmed via `codex doctor` that
  `CODEX_HOME` fully relocates Codex's config/state dir. The wrapper
  deliberately does **not** set `approval_policy`/`sandbox_mode` — it
  leaves Codex's normal safe interactive-approval defaults in place,
  since a local, less-trustworthy model running with
  `danger-full-access`/`never`-approval and weak tool-call discipline is
  a real risk, not just a convenience tradeoff.
- **Pi**: uses its native `openai-completions` provider type directly
  against `/v1/chat/completions` — no translation needed at all. Config
  is a generated `models.json` under an isolated `PI_CODING_AGENT_DIR`
  (`~/.config/local-llm/pi-home`, default is `~/.pi/agent`). Model
  selection is via `pi --model local-llm/qwen3-coder-next`.
- Both wrappers were smoke-tested end-to-end against the live
  `macbook-m4-max` server (`codex exec "..."` and `pi --print "..."`,
  both correctly round-tripped through the real model).

## Out of scope for now

- CI runner setup on the homelab user (mentioned as a future use case,
  not part of this spec).
- Automatic model updates/swapping.
- MLX-based serving.
