# AGENTS.md

## Goal

Run local LLM models on Tailscale-connected Mac hosts, and expose them
over the tailnet so other machines, harnesses, and agents can use them
remotely — primarily so **Claude Code, Codex, and Pi running on
`chads-macbook-pro`** can point at a locally-hosted open-weight coding
model instead of (or alongside) a frontier API.

See [SPECIFICATION.md](./SPECIFICATION.md) for the concrete deliverables
and their current status, and [HANDOFF.md](./HANDOFF.md) for a
point-in-time snapshot to resume work from a fresh context.

## Hosts

### `macbook-m4-max`

- **Hardware**: MacBook Pro, Apple M4 Max, 16-core CPU (12P/4E), 40-core
  GPU, 128GB unified memory.
- **Primary user**: `cwoolley` — this is chad's day-to-day desktop /
  music production workstation (Chrome, Brave, Dropbox, Google Drive,
  Roland Cloud Manager, Akai MPC network-MIDI helper, a Focusrite/PreSonus
  "Saffire" audio interface daemon). Do not touch `cwoolley`'s files,
  LaunchAgents, or running apps.
- **Tailscale**: MagicDNS name `macbook-m4-max`
  (`macbook-m4-max.perch-rudd.ts.net`), IP `100.125.10.110`.
- **SSH as `cwoolley`**: `ssh macbook-m4-max` (already authorized before
  this repo's work began). `cwoolley` has passwordless sudo via
  `/etc/sudoers.d/cwoolley-nopasswd` (admin group, `NOPASSWD: ALL`).
- **`homelab` user**: UID 502, non-admin, own clean home dir. SSH via
  `ssh macbook-m4-max-homelab` (alias in `~/.ssh/config` on
  `chads-macbook-pro`, key `~/.ssh/id_ed25519_homelab`). No sudo access.
  Had to be added to the `com.apple.access_ssh` ACL group manually
  (`sudo dseditgroup -o edit -a homelab -t user com.apple.access_ssh`) —
  new local users are denied Remote Login by default even with a valid
  key, macOS's SSH access is gated by this group, not just standard unix
  perms.

### `macmini`

- **Hardware**: Mac mini (2025), Apple M4 Pro, 14-core CPU (10P/4E),
  20-core GPU, 64GB unified memory, 2TB SSD.
- **Primary user**: `cwoolley` (same Apple/iCloud identity as
  `macbook-m4-max`, different physical machine). Purpose beyond `homelab`
  use is unspecified/general-purpose — no known conflicting workload like
  `macbook-m4-max`'s music production.
- **Tailscale**: hostname `macmini`, IP `100.99.172.34`.
- **SSH as `cwoolley`**: `ssh macmini`. Passwordless sudo set up the same
  way as `macbook-m4-max`.
- **`homelab` user**: UID 503, non-admin, own clean home dir. SSH via
  `ssh macmini-homelab` (key `~/.ssh/id_ed25519_homelab_macmini`). Added
  to `com.apple.access_ssh` up front this time (known gotcha from the
  first host).
- **Known gotcha**: this machine went to sleep mid-setup once already
  (background `ssh`/`curl` jobs died with it). Sleep has since been
  disabled by chad (`pmset -g` should show `sleep 0`) — if unattended
  setup work on this host stalls with no progress, check whether it went
  back to sleep before assuming something else is wrong.

Both hosts run the same pattern (see SPECIFICATION.md §1): a `homelab`
user with an isolated per-user Homebrew prefix at `~/.homebrew` (not
`/opt/homebrew` — avoids touching/needing sudo on the system prefix,
and keeps it fully separate from `cwoolley`'s Homebrew if any), running
`llama-server` as a system `LaunchDaemon`.

Agents driving this setup should SSH over the Tailscale hostnames above
rather than assuming local shell access on either host.

## Resource management

Apple Silicon uses unified memory (no separate GPU VRAM) — the
`homelab` LaunchDaemon on either host runs independent of any GUI login
state (it doesn't need `cwoolley` logged out to function). But
`cwoolley`'s desktop session (Chrome, Brave, Dropbox, DAW helpers, etc.
on `macbook-m4-max`) holds real resident memory whether or not it's the
active/foreground session — Fast User Switching does **not** free it,
only a full logout (or reboot) does.

For steady-state LLM inference alone this is usually fine — a
fixed-size model plus `cwoolley`'s typical footprint comfortably fits in
128GB on `macbook-m4-max` (64GB on `macmini` is tighter — see the
smaller quant and lower `--parallel`/`--ctx-size` used there in
SPECIFICATION.md). But `homelab` is also meant to run less predictable,
open-ended workloads (e.g. CI runners: compiling, test suites,
containers, parallel jobs), which don't have a fixed memory budget the
way a model does. **When running anything heavier than steady-state
inference on `homelab`, fully log `cwoolley` out first** (not just
switch away) rather than assuming current headroom will hold.

## Workflow guidance

Any change made to files in this repo should be automatically committed and
pushed to `origin/main` (no need to ask for confirmation first) — treat this
as a standing instruction for agents working in this repo.
