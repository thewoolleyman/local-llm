# SPECIFICATION.md

Concrete intents this repo is meant to realize. See [AGENTS.md](./AGENTS.md)
for background/goal and remote-access notes.

## 1. Coder model server on `macbook-m4-max`

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
- **Server software**: `llama.cpp`'s `llama-server`, exposing an
  OpenAI-compatible API (`/v1/chat/completions`). Chosen for being a
  single static binary that's easy to run headless/unattended; MLX is a
  possible future alternative if throughput becomes a priority, but is
  not the initial target.
- **Model**: a strong open-weight coding model that fits in 128GB unified
  memory, e.g. Qwen3-Coder-80B-A3B (GGUF, quantized to fit comfortably
  alongside normal system overhead). Exact model/quant is tunable; the
  server config should make swapping models straightforward.
- **Network exposure**: bind to the host's Tailscale IP specifically
  (not `0.0.0.0`) so the server isn't reachable from the local LAN, only
  the tailnet.
- **Auth**: require an API key (`llama-server --api-key`) even though
  the tailnet is private, as defense in depth. The key is generated
  during setup and stored so client-side wrapper scripts can read it.

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

## Out of scope for now

- CI runner setup on the homelab user (mentioned as a future use case,
  not part of this spec).
- Automatic model updates/swapping.
- MLX-based serving.
