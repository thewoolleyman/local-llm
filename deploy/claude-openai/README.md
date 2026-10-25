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

Defaults are `gpt-6.1-sol` and 500,000 context tokens. Use `CLAUDE_OPENAI_MODEL`
to select a different model; `gpt-6-sol` and `gpt-5.6-sol` select 272,000 tokens.
Other models require `CLAUDE_OPENAI_CONTEXT_TOKENS`. Use these environment
variables together rather than `--model`, which cannot update the wrapper's
context selection. Overrides: `CLAUDE_OPENAI_BASE_URL`,
`CLAUDE_OPENAI_SECRETS_FILE`, and `CLAUDE_OPENAI_GATEWAY_KEY`.

The wrapper sets all default model aliases to the selected Sol model so
small/fast tasks also use OpenAI. Claude Code can emit an unrecognized-model
warning; actual requests and replies were verified below. Its displayed USD
cost estimate does not establish API billing for this ChatGPT route.

No `--bare`, `--safe-mode`, setting-source restriction, or MCP restriction is
added. Claude Code 2.1.310's `--bare` help explicitly says it skips configured
and plugin hooks, LSP, plugin sync, attribution, auto-memory, background
prefetch, keychain reads, and CLAUDE.md auto-discovery, and sets
`CLAUDE_CODE_SIMPLE=1`; skills remain explicitly callable. The existing local
wrapper uses that mode for its macOS keychain constraint, so use this sibling
for the coordinator. `ANTHROPIC_API_KEY` here is the gateway key, not an
Anthropic credential. Claude.ai hosted connectors require Claude OAuth and
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
