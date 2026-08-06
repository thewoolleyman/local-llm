# AGENTS.md

## Goal

Set up the Tailscale host `macbook-m4-max` to run local LLM models via
llama.cpp (or a compatible runner), and expose them over the Tailscale
network so other machines, harnesses, and agents can use them remotely.

The primary consumer is Claude Code running on `chads-macbook-pro`, which
will connect to the model server over Tailscale instead of running models
locally.

## Components

- **Host**: `macbook-m4-max` — runs the LLM inference server (llama.cpp or
  similar), taking advantage of Apple Silicon (M4 Max) for local inference.
- **Network**: Tailscale — provides secure, private connectivity between
  `macbook-m4-max` and client machines without exposing the server to the
  public internet.
- **Clients**: Other machines/agents on the tailnet, e.g. `chads-macbook-pro`
  running Claude Code, that call into the hosted model over the network.

## Remote access

`macbook-m4-max` is reachable over Tailscale via MagicDNS at
`macbook-m4-max` (resolves to `macbook-m4-max.perch-rudd.ts.net`, currently
`100.125.10.110`). SSH as `cwoolley` works directly:

```
ssh macbook-m4-max
```

Agents driving this setup should use SSH over the Tailscale hostname to run
commands on `macbook-m4-max` remotely rather than assuming local shell
access on that host.

## Workflow guidance

Any change made to files in this repo should be automatically committed and
pushed to `origin/main` (no need to ask for confirmation first) — treat this
as a standing instruction for agents working in this repo.

## Status

Early setup. Nothing is implemented yet.
