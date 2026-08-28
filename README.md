# local-llm

Hosting local LLM models via llama.cpp on a Tailscale fleet — `macbook-m4-max`,
`macmini`, and `gmktec-xubuntu` — behind a llama-swap router, exposed to other
machines and agents (e.g. Claude Code, Codex, and Pi on `chads-macbook-pro`)
over Tailscale.

See [AGENTS.md](./AGENTS.md) for the host inventory and resource policy,
[SPECIFICATION.md](./SPECIFICATION.md) for the full design, and
[HANDOFF.md](./HANDOFF.md) for the current status.
