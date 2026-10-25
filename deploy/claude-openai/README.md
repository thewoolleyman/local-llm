# OpenAI Sol inside the full Claude Code harness

`bin/claude-openai` uses CLIProxyAPI's Anthropic Messages endpoint on
`127.0.0.1:8317`, with Codex ChatGPT authentication upstream. Claude Code owns
the agent loop, hooks, MCP, plugins, instructions, memory and messaging.
This is a separate path from the local Qwen fleet and does not change its
wrapper or the normal Claude/Codex defaults.

## Setup

Install the [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) binary
as `~/.local/bin/cli-proxy-api`. On this Linux amd64 host, the verified release
is **v8.0.42**, commit `bc064340`. Its release archive
`CLIProxyAPI_8.0.42_linux_amd64.tar.gz` has SHA256
`1e10566fe0042ed5a9b80306cf296bf86a83de590cd967a8b177988b896c8d31`,
verified against the publisher's `checksums.txt`.

With Codex already signed in using ChatGPT:

```bash
python3 /data/projects/local-llm/bin/configure-claude-openai.py
mkdir -p ~/.config/systemd/user
cp /data/projects/local-llm/deploy/claude-openai/claude-openai-gateway.service \
  ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claude-openai-gateway.service
```

On other platforms, run `cli-proxy-api -config
~/.config/local-llm/openai/gateway.json` under an appropriate supervisor.
The service template assumes the default config directory and binary path.

The configuration helper creates mode-0600 files under
`~/.config/local-llm/openai/`: `secrets.env` contains a random gateway client
key; `gateway.json` contains the generated CLIProxyAPI v8 configuration;
`auth/codex.json` holds a private copy of the Codex OAuth credential. The
listener is loopback-only and management is disabled. JSON is valid YAML
for CLIProxyAPI's configuration loader. Keep all these files outside Git.

The helper preserves existing gateway credentials on repeat runs, including
tokens refreshed by the proxy, and never writes Codex's original auth file.
Because both clients initially share an OAuth refresh token, independent
refresh or logout can require a new login. For a separate gateway login use:

```bash
cli-proxy-api -config ~/.config/local-llm/openai/gateway.json \
  -codex-device-login -no-browser
```

The ChatGPT route was verified here; no OpenAI API key was needed. This is
third-party gateway integration, not a guarantee of continued account access.
[OpenAI authentication guidance](https://developers.openai.com/codex/auth)
distinguishes ChatGPT-backed Codex access from general API authentication.
If the subscription route becomes unavailable, a separately billed OpenAI
Platform API key with access to the requested Sol model is needed; that
upstream configuration is not implemented by this helper.

## Coordinator launch

From the existing coordinator pane, after exiting the old process:

```bash
cd /data/projects/livespec-dev-tooling
/data/projects/local-llm/bin/claude-openai --dangerously-skip-permissions \
  --resume gitops-fleet-capacity-monitoring
```

To start a fresh conversation instead, use `-n gitops-fleet-capacity-monitoring`
instead of `--resume gitops-fleet-capacity-monitoring`, and provide the plan
and coordinator instructions again. A display name does not resume history.
Starting a fresh conversation can also be useful if an old transcript's
model-specific thinking blocks cause a gateway error.

The default model now comes from Codex's live `model/list` response. Each
launch starts a separate short-lived app-server process (never restarts the
shared daemon), reads all pages of visible models, and pairs them with context
metadata in Codex's refreshed `models_cache.json`. No OpenAI model names,
default or context sizes are maintained in the wrapper. Missing metadata
causes an explicit setup failure rather than an invented context size. This
tracks the model list Codex currently presents to this account, rather than
every model on the public OpenAI API. New launches pick up catalog changes;
an already-running process retains its startup list, as Codex does.

The same native `/model` picker also includes live fleet-router models, with
the deployed context contract from `codex-metadata/local-router-model-catalog.json`.
The gateway's Codex registrations are generated from that same discovery
result; local entries get explicit Anthropic Messages routes to the fleet
router with its own upstream key. Gateway configuration reloads in place;
the coordinator and its conversation are not restarted. Local output requests
are capped at 4,096 tokens to leave useful headroom on the 32K servers.

Use `CLAUDE_OPENAI_MODEL` or `--model` to choose an initial discovered model.
`CLAUDE_PICKER_PROVIDERS=openai` restricts the picker to OpenAI;
`CLAUDE_PICKER_PROVIDERS=local` restricts it to local models. The default is
`openai,local`. Other overrides: `CLAUDE_OPENAI_BASE_URL`,
`CLAUDE_OPENAI_CONFIG_DIR`, `CLAUDE_OPENAI_SECRETS_FILE`,
`CLAUDE_OPENAI_GATEWAY_KEY`, and the existing `LOCAL_LLM_ROUTER_*` variables.
The original local-only `bin/claude-local-llm` wrapper remains supported.

Claude Code can emit an unrecognized-model warning; actual requests and replies
were verified below. Its displayed USD cost estimate and "API Usage Billing"
label do not establish API billing for this ChatGPT subscription route.

### Context when switching

Every model stays selectable. The session is **not** reduced to the smallest
offered context window. Picker descriptions show the target model's limit,
current measured token usage, and estimated overflow needing summarization
or removal. An overflowing entry also gets a warning marker. For example:

```text
⚠ Local: Qwen3-Coder-Next — Mac mini
limit 32,768; current ≈100,000 tokens; ≈67,232 tokens need summarizing/removing
```

The estimate sums the last request's input/cache tokens and response tokens.
Provider tokenizers differ, and new prompts/tool output add tokens; this is
not an exact target-provider token count or a measure of information lost.
Before usage is measured, the picker says so. Switching providers retains
history. Nothing in the wrapper silently clips it. A UserPromptSubmit hook
blocks a prompt when the last measured conversation already exceeds the
selected model's limit, explaining how to select a larger model and `/compact`
or start a fresh session. Native backend context errors remain the final check.
An initial count below the limit is not a guarantee that the next request fits.

Claude 2.1.310 has a process-wide custom-model context override, and its
per-model auto-compact settings have a 100K minimum. The wrapper uses the
largest discovered window as the process ceiling and installs per-model
auto-compact windows where supported. For the smaller local models, use the
warnings and guard; the native global context percentage can reflect the
larger ceiling. `CLAUDE_OPENAI_CONTEXT_TOKENS` can lower that ceiling.

`--settings` files are pinned at startup in this release, so live warnings use
a private, watched user-settings overlay under `openai/picker-*/claude/`.
It copies user settings and global trust/MCP preferences, shares the original
projects/plugins/memory directories through symlinks, appends the context
guard to existing user hooks, and continues running the original user status
line. Project settings and hooks still load normally. The original user
settings file is not changed. `XDG_RUNTIME_DIR` and `TMPDIR` are preserved.
Private state is per-session; finished sessions' picker directories can be
removed when no process uses them. Re-launching from an existing wrapped
session uses the original config directory rather than nesting overlays.

No `--bare`, `--safe-mode`, setting-source restriction, or MCP restriction is
added. Claude Code 2.1.310's `--bare` help explicitly says it skips configured
and plugin hooks, LSP, plugin sync, attribution, auto-memory, background
prefetch, keychain reads, and CLAUDE.md auto-discovery, and sets
`CLAUDE_CODE_SIMPLE=1`; skills remain explicitly callable. The existing local
wrapper uses that mode for its macOS keychain constraint, so use this sibling
for the coordinator. The gateway key is not an Anthropic credential.
The current launcher supplies it through `apiKeyHelper`
and clears competing API-key/bearer variables, avoiding the interactive custom
API-key approval prompt. Claude.ai hosted connectors require Claude OAuth and
are unavailable with this route; locally configured MCP still loads.

## Verification on vmi3006760, 2026-10-25

- Direct `/v1/messages` returned `SOL_GATEWAY_OK` with response model
  `gpt-6.1-sol`, and separately `gpt-6-sol`, using the imported ChatGPT login.
  The older reported 400 for `gpt-6-sol` was not reproduced today.
- Full Claude Code 2.1.310 session
  `a6107be0-4741-4e9b-8aa4-f1033005406b` used `gpt-6.1-sol`, reported a
  500,000-token context window and 32,000 max output tokens, and completed
  successfully in bypass-permissions mode. SessionStart and PreToolUse
  hooks returned success; Bash returned `SOL_HOOK_OK`. Livespec,
  orchestrator and overseer plugins loaded; `/loop`, ScheduleWakeup,
  ListAgents and SendMessage were present. Playwright MCP connected;
  existing honeycomb/brightdata authentication and agent-mail failures
  remain visible in the normal startup report.
- ListAgents found the coordinator and 19 peers. SendMessage returned
  success and the coordinator independently confirmed receiving it.
- Reverse-proof session `0434689c-3851-4be8-9e0d-19bc49feb86c`, named
  `sol-reverse-message-proof`, saw both `petri-factory-on-gmktec` and
  `caam-anthropic-loop-runner`. Its transcript records an incoming attachment
  containing `REVERSE_SOL_OK` from the coordinator at
  `uds:/tmp/cc-socks/1870958.sock`. The project's hook blocked a foreground
  standalone sleep, independently demonstrating active project policy.
- The wrapper does not change `XDG_RUNTIME_DIR` or `TMPDIR`. This Codex
  parent already had `XDG_RUNTIME_DIR=/run/user/1000`, so Claude used
  `/run/user/1000/cc-socks/1739208.sock`. Discovery and reverse delivery
  across that directory and `/tmp/cc-socks` both worked. A print session
  removes its socket when it exits; ENOENT after exit is expected.
- After moving the gateway under the enabled user systemd service,
  resuming the first smoke session through the wrapper returned
  `SOL_RESUME_OK`, again attributed to `gpt-6.1-sol` with 500K context.
  The reverse-test session completed successfully after the 150-second
  background wait and confirmed receiving `REVERSE_SOL_OK`.

Raw local evidence: `/tmp/local-llm-sol-smoke.jsonl`,
`/tmp/local-llm-sol-hooks.jsonl`, `/tmp/local-llm-sol-reverse.jsonl`, and
the reverse session's transcript under
`~/.claude/projects/-data-projects-livespec-dev-tooling/`. These contain
private session context and are not committed. The tests under `tests/`
also verify credential isolation and wrapper arguments without inference.

### Dynamic picker verification

The native interactive `/model` menu was opened in an isolated tmux test on
2026-10-25. It displayed the seven current Codex models and three fleet models.
Updating the status callback with **simulated** 100K usage updated that live
menu with 67,232-token warnings for 32K models and a 34,464-token warning for
the 65K model. This verifies the UI arithmetic and refresh mechanism; the
test conversation itself was not 100K tokens long. A real OpenAI print test
returned `DYNAMIC_PICKER_OK` with a reported 500K window, and a direct Messages
request to `gmktec/qwen3-coder-next` through the shared gateway returned
`LOCAL_PICKER_OK`. Tests cover new/removed Codex models, unknown context
metadata, warning updates, non-destructive overflow guards, route/key
separation, full startup, and socket environment preservation.

In that same interactive test conversation, OpenAI returned `TUI_OPENAI_OK`,
then switching through `/model` to GMKtec returned `TUI_LOCAL_OK` while retaining
the history. Measured usage updated from 16,163 to 18,425 tokens. The wrapper
status line shows the active model's true limit alongside that count; the
original user status-line command receives corrected context percentages too.
The native internal `/context` ceiling for custom models remains subject to
the Claude limitation described above.
The final overlay was also exercised from the coordinator project: seven
plugins loaded, Playwright and the configured Honeycomb MCP connected,
project PreToolUse hooks succeeded, and Bash returned `OVERLAY_HOOK_OK`.

Anthropic models require a separate authenticated gateway upstream. This
configuration supplies OpenAI and local routes; it does not turn a Claude.ai
subscription into an Anthropic API credential. Normal `claude` retains its
existing Anthropic route and configuration.
