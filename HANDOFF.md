# HANDOFF.md

Point-in-time status snapshot for resuming this work in a fresh context.
Read [AGENTS.md](./AGENTS.md) (host inventory) and
[SPECIFICATION.md](./SPECIFICATION.md) (what's being built and how)
first — this file is just "what's done, what's not, what to run next."

## Status at a glance

| Host              | homelab user | llama.cpp | Model downloaded | LaunchDaemon | Verified reachable |
|-------------------|:---:|:---:|:---:|:---:|:---:|
| `macbook-m4-max`  | done | done | done (Q6_K) | **running** | **yes** |
| `macmini`         | done | done | **partial, stopped** | staged, not loaded | no |

Client-side (`bin/codex-local-llm`, `bin/pi-local-llm`) is fully done and
tested against `macbook-m4-max`. Not yet tested against `macmini`.

## `macbook-m4-max`: fully done

Nothing to do here. Confirmed working end to end:

```
curl -sf -H "Authorization: Bearer $(cat ~/.config/local-llm/api-key)" http://macbook-m4-max:8080/v1/models
codex-local-llm exec "Reply with exactly the word: pong"   # from repo bin/, tested, works
pi-local-llm --print "Reply with exactly the word: pong"   # from repo bin/, tested, works
```

If it's ever unreachable, check the daemon first:

```
ssh macbook-m4-max 'sudo launchctl print system/local.homelab.llama-server' | grep state
ssh macbook-m4-max-homelab 'tail -50 ~/Library/Logs/llama-server.error.log'
```

## `macmini`: stopped mid-download, needs resuming

**Why it's stopped**: this was deliberately halted (not crashed) to leave
a clean state for a fresh-context handoff, per explicit instruction — the
in-progress background download was killed both locally and on the
remote host so nothing is running unsupervised.

**Exact state when stopped** (all 4 parts of Q4_K_M, `curl -C -` used
throughout so every part resumes safely — just re-run the same loop):

```
ssh macmini-homelab 'ls -la ~/models/Qwen3-Coder-Next-Q4_K_M'
# part 1: 15,524,827,040 bytes — check if this equals the full remote size (may already be complete)
# part 2: 14,872,168,352 bytes — check if this equals the full remote size (may already be complete)
# part 3: 4,126,478,336 bytes  — definitely partial, was actively downloading
# part 4: not started
```

**To resume the download** (safe to just run this — `curl -C -` will
skip/verify already-complete parts and resume the partial one):

```bash
ssh macmini-homelab '
caffeinate -i -w $$ &
cd ~/models/Qwen3-Coder-Next-Q4_K_M
for i in 00001 00002 00003 00004; do
  f="Qwen3-Coder-Next-Q4_K_M-${i}-of-00004.gguf"
  echo "=== downloading $f ==="
  curl -C - -L -o "$f" "https://huggingface.co/Qwen/Qwen3-Coder-Next-GGUF/resolve/main/Qwen3-Coder-Next-Q4_K_M/$f"
done
ls -la ~/models/Qwen3-Coder-Next-Q4_K_M
'
```

Run this via `Bash` with `run_in_background: true` (it'll exceed the
2-minute default timeout) — total remaining is roughly 30GB, so expect
this to take a while. **`macmini` went to sleep mid-setup once already**
(that's why `caffeinate -i -w $$` is in the command) — if progress
stalls with no output, check `ssh macmini 'pmset -g | grep sleep'` before
assuming something else broke.

**After the download completes**, everything else is already staged and
just needs activating:

```bash
# 1. Bootstrap the LaunchDaemon (plist already written and validated at
#    /Library/LaunchDaemons/local.homelab.llama-server.plist on macmini)
ssh macmini 'sudo launchctl bootstrap system /Library/LaunchDaemons/local.homelab.llama-server.plist'

# 2. Confirm it loaded the model and is listening
ssh macmini-homelab 'tail -30 ~/Library/Logs/llama-server.error.log'
# expect a line like: llama_server: listening on http://100.99.172.34:8080

# 3. Copy its API key down for client use (separate from macbook-m4-max's key)
ssh macmini-homelab 'cat ~/.llama-server-api-key'
# store wherever convenient — e.g. ~/.config/local-llm/api-key-macmini,
# then pass LOCAL_LLM_API_KEY_FILE=~/.config/local-llm/api-key-macmini
# (or LOCAL_LLM_API_KEY=<value>) when testing against this host

# 4. Verify reachability + test the wrapper scripts against it
LOCAL_LLM_HOST=macmini LOCAL_LLM_API_KEY=<key-from-step-3> \
  curl -sf -H "Authorization: Bearer <key>" http://macmini:8080/v1/models

LOCAL_LLM_HOST=macmini LOCAL_LLM_API_KEY=<key-from-step-3> \
  ./bin/codex-local-llm exec "Reply with exactly the word: pong"

LOCAL_LLM_HOST=macmini LOCAL_LLM_API_KEY=<key-from-step-3> \
  ./bin/pi-local-llm --print "Reply with exactly the word: pong"
```

Then mark tasks #8 and #9 (see below) complete.

## Task list state (as of handoff)

1. Create dedicated homelab user on macbook-m4-max — **completed**
2. Install llama.cpp under homelab user on macbook-m4-max — **completed**
3. Download and configure a coding model (GGUF) — **completed**
4. Set up llama-server as a LaunchDaemon bound to Tailscale IP — **completed**
5. Verify model server reachable over Tailscale from chads-macbook-pro — **completed**
6. Write bin/codex-local-llm and bin/pi-local-llm wrapper scripts — **completed**
7. Create dedicated homelab user on macmini — **completed**
8. Install llama.cpp + download coding model on macmini — **in progress** (llama.cpp done, model download stopped partway, resume per above)
9. Set up llama-server LaunchDaemon on macmini — **in progress** (plist staged, not yet bootstrapped — waiting on #8)

Not yet started / not requested:

- Verifying `macmini` end to end (bootstrap daemon, test wrapper scripts against it) — blocked on #8.
- Any CI runner work on either `homelab` user (explicitly out of scope per SPECIFICATION.md — mentioned as a future use case only).
- Multi-host selection UX beyond the existing `LOCAL_LLM_HOST` env var override (works today, just not polished — e.g. no shortcut flag to pick a host by name).

## Gotchas hit during setup (don't re-discover these)

- **New local macOS users are denied Remote Login by default even with a
  valid authorized_keys entry.** SSH access is gated by the
  `com.apple.access_ssh` ACL group, separate from normal unix file perms.
  Fix: `sudo dseditgroup -o edit -a <user> -t user com.apple.access_ssh`.
  Symptom if missed: SSH accepts the key (`Accepted publickey` in the
  client log) but the connection closes immediately after — check
  `sudo log show --predicate 'process == "sshd-session"' --last 30s` on
  the host for `pam_sacl: denying '<user>'` to confirm this is the cause.
- **`macmini` sleeps unattended**, killing any in-flight SSH-driven
  background work. User has since disabled sleep on it, but verify with
  `pmset -g` before assuming a stalled job is broken for some other
  reason.
- **Codex's `wire_api = "chat"` is removed**, not just deprecated —
  confirmed by grepping strings in the installed binary. Must use
  `wire_api = "responses"`; this works because `llama.cpp`'s server added
  `/v1/responses` support (translates internally to chat completions).
  Verify with a direct curl to `/v1/responses` if Codex ever fails to
  connect after a `llama.cpp` upgrade, in case that support regresses.
- **A "GLM-5.2-Air" model does not exist** — it was cited by another
  AI's research with a `[Verified]` tag and a specific throughput number,
  but checking Z.ai's own Hugging Face page turned up a thread literally
  titled "Air or Flash model coming?" (i.e. requested, not released), and
  a direct HF search for the name returns nothing. Treat specific
  model/benchmark claims from any AI-generated research as unverified
  until checked against a primary source (model card, HF repo listing),
  regardless of confidence tags.
- **Background SSH-driven jobs can outlive the local SSH client being
  killed.** Killing the local `ssh ... &` process does not reliably
  SIGHUP-terminate the remote command (observed: remote `curl`/`caffeinate`
  kept running after the local wrapper was killed). If you need a remote
  job fully stopped, kill it explicitly on the remote side too — don't
  assume killing the local side was sufficient.

## Where things live

- This repo (`chads-macbook-pro`): `AGENTS.md`, `SPECIFICATION.md`,
  `HANDOFF.md`, `.gitignore`, `bin/codex-local-llm`, `bin/pi-local-llm`,
  `bin/lib/local-llm-common.sh`.
- Client-side secrets (NOT in repo, gitignored by location not name):
  `~/.config/local-llm/api-key` (macbook-m4-max's key),
  `~/.config/local-llm/codex-home/` (generated per-run),
  `~/.config/local-llm/pi-home/` (generated per-run).
- SSH config additions on `chads-macbook-pro` (`~/.ssh/config`):
  `macbook-m4-max-homelab`, `macmini-homelab` host aliases.
- SSH keys (`chads-macbook-pro`, not in repo): `~/.ssh/id_ed25519_homelab`,
  `~/.ssh/id_ed25519_homelab_macmini`.
- Per-host (`homelab` user home dir on each Mac): `~/.homebrew/`
  (isolated Homebrew prefix), `~/models/`, `~/bin/run-llama-server.sh`,
  `~/.llama-server-api-key`, `~/Library/Logs/llama-server*.log`.
- Per-host (root-owned): `/Library/LaunchDaemons/local.homelab.llama-server.plist`.
