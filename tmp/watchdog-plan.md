# Local LLM watchdog plan

Status: planned; not deployed as of 2026-08-12.

## Objective

Run an independent watchdog on both `macbook-m4-max` and `macmini` so a
`llama-server` that is alive but unhealthy is detected and recovered. The
watchdog must not confuse legitimate long prompt evaluation or concurrent
inference with a stuck server.

## Deployment model

Install one root-owned macOS LaunchDaemon per host:

```text
/Library/LaunchDaemons/local.homelab.llama-watchdog.plist
```

The daemon runs a repo-owned or homelab-owned watchdog executable as `root`
only when required to inspect/restart the root-owned model service. It should
use the existing `homelab` SSH/user boundary for logs and configuration where
possible. The existing `local.homelab.llama-server` LaunchDaemon remains the
process supervisor and keeps `RunAtLoad`/`KeepAlive` behavior.

The watchdog configuration must be host-specific and checked in as templates,
with no secrets in Git:

| Host | Server endpoint | Slots | Context |
|---|---|---:|---:|
| `macbook-m4-max` | `100.125.10.110:8080` | auto, currently four | 65,536 |
| `macmini` | `100.99.172.34:8080` | two | 32,768 |

The Mac mini router watchdog is a separate concern. It should monitor
`local.homelab.llama-swap` on `macmini`, but a peer recovery must happen before
restarting the router. The router should drain or mark a peer unavailable while
that peer is being restarted.

## Health state and busy-vs-stuck decision

The watchdog keeps a small local state file containing observation timestamps,
request IDs if available, slot progress, failure counts, and the current
state. It samples each server at a fixed interval, initially 10 seconds.

States:

- `ready`: authenticated readiness and a recent probe succeed.
- `busy`: one or more requests are active and progress is observable.
- `degraded`: a probe failed or a request is slow, but active work is still
  making progress; do not restart.
- `stuck`: active work has stopped progressing and independent probes fail for
  the configured consecutive window.
- `recovering`: the peer is drained and its model daemon is being restarted.
- `failed`: recovery did not restore health; leave the peer drained and alert.

Busy is not failure. The watchdog compares successive observations of llama.cpp
slot/status data and logs. A request counts as progressing when prompt tokens,
decoded tokens, slot activity, or an equivalent monotonic server counter moves.
Prompt evaluation is allowed a generous adaptive interval based on observed
prompt size and recent throughput. A full slot or a long first model load is
therefore not sufficient evidence for restart.

The watchdog declares `stuck` only when all of the following hold:

1. At least one request has exceeded its adaptive age budget.
2. No active slot has shown token/progress movement for the no-progress window.
3. A small authenticated health probe cannot complete, or the server returns
   repeated context/KV/5xx failures.
4. The condition occurs for the configured consecutive sample count.

The default starting policy should be conservative and configurable, for
example a 10-second sample interval, 60-second no-progress window, three
consecutive failed observations, and exponential recovery backoff. Thresholds
must be validated against real prompt-evaluation timings before deployment.

## Probe ladder

Use progressively more expensive checks:

1. Process and LaunchDaemon state (`launchctl print`/process existence).
2. Unauthenticated or authenticated `/v1/models` readiness check as
   appropriate; model metadata alone is not an inference health signal.
3. Authenticated one-token generation probe to the selected local endpoint,
   with a strict probe timeout and no tools.
4. Slot/progress inspection and recent log classification.

The generation probe must use the server's actual bearer key, never expose that
key in logs, and be serialized or rate-limited so health checking cannot itself
consume the KV cache. A probe failure during known heavy activity enters
`degraded` first; it does not immediately restart the daemon.

## Recovery procedure

For a confirmed `stuck` peer:

1. Tell llama-swap to drain or stop selecting the peer, if supported by its
   configuration/API; otherwise use a watchdog-side lock and bounded restart
   window so new requests are not intentionally accepted.
2. Record the reason, peer, active request summary, and relevant redacted log
   evidence.
3. Cancel/clear the stuck server workload through the supported llama.cpp
   endpoint if available.
4. Kickstart only the affected `local.homelab.llama-server` LaunchDaemon.
5. Wait for `/v1/models`, then run the authenticated one-token probe.
6. Re-enable the peer only after the probe succeeds.
7. Back off repeated recoveries and leave the peer drained after the maximum
   recovery attempts; never restart both model servers in response to one peer
   failure.

If the router itself fails its process/readiness probe, restart
`local.homelab.llama-swap` separately. Router recovery must not restart healthy
model servers.

## Safety and operational requirements

- Never use `kill -9` as the first recovery action.
- Never restart a peer merely because all slots are busy.
- Bound request generation and context budgets so clients cannot consume the
  entire cache indefinitely.
- Use a lock to prevent simultaneous watchdog recoveries.
- Apply exponential backoff and a circuit breaker after repeated failures.
- Preserve logs across restarts with rotation and include recovery reason,
  duration, and outcome.
- Keep Tailscale-only binding and all bearer keys outside Git.
- Do not alter `cwoolley`'s processes or files; the watchdog manages only the
  homelab services.

## Implementation sequence

1. Capture current `/slots`, `/v1/models`, authenticated probe behavior, and
   log formats on both hosts.
2. Implement a read-only observer with state transitions and dry-run recovery
   logging.
3. Add unit tests for busy, progressing, cold-start, KV-exhausted,
   context-exceeded, deadlocked, and router-unavailable fixtures.
4. Deploy dry-run LaunchDaemons on both hosts and compare decisions with real
   traffic.
5. Enable peer drain and single-peer restart recovery.
6. Exercise controlled failures and verify recovery, backoff, and alerting.
7. Document the deployed thresholds and evidence in `SPECIFICATION.md` and
   update `HANDOFF.md`.

## Acceptance tests

- A long but progressing prompt remains `busy`/`degraded` and is not restarted.
- A deliberately wedged server reaches `stuck`, is drained, restarts, passes
  the probe, and returns to service.
- KV/context failures are classified and recovered without restarting the
  healthy peer.
- Router failures recover independently.
- Repeated failures trigger backoff/circuit-breaker behavior.
- Both hosts boot with the watchdog and remain protected after sleep/reboot.
- Logs and state contain enough redacted evidence to explain every restart.
