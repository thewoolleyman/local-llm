#!/usr/bin/env python3
"""Discover Codex/fleet models, refresh gateway routes, and launch Claude Code.

No OpenAI model IDs are maintained here. Codex model/list owns availability;
its refreshed model cache supplies context metadata absent from model/list.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data, *, in_place=False):
    """Atomically replace private state only if its contents changed."""
    content = json.dumps(data, indent=2) + "\n"
    if path.exists() and path.read_text() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if in_place:
        # CLIProxyAPI watches the config inode, rather than its parent folder.
        # An atomic rename drops its watch on Linux. Serialize full writes to
        # this private file; its watcher debounces before parsing.
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, "r+") as stream:
            os.chmod(path, 0o600)
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            stream.write(content)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        return
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".picker-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def codex_models(timeout=30):
    """Use a private app-server process, without touching the shared daemon."""
    process = subprocess.Popen(
        ["codex", "app-server", "-c", 'model_provider="openai"'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1, cwd=Path.home())
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read, daemon=True).start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(request_id):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
            if line is None:
                raise RuntimeError("Codex app-server exited during model discovery")
            message = json.loads(line)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError("Codex rejected model discovery")
                return message["result"]
        raise TimeoutError("Codex model discovery timed out")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "local_llm_picker", "version": "1"}}})
        receive(1)
        send({"method": "initialized"})
        result, cursor, request_id = [], None, 2
        while True:
            send({"id": request_id, "method": "model/list", "params": {
                "limit": 100, "includeHidden": False, "cursor": cursor}})
            page = receive(request_id)
            result.extend(page["data"])
            cursor = page.get("nextCursor")
            if not cursor:
                break
            request_id += 1
        return result
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def openai_entries(visible, cache):
    metadata = {m["slug"]: m for m in cache["models"]}
    entries = []
    for model in visible:
        if model.get("hidden"):
            continue
        model_id = model["model"]
        context = metadata.get(model_id, {}).get("context_window")
        if not isinstance(context, int) or context <= 0:
            raise ValueError(f"Codex context metadata missing for {model_id}; refresh Codex")
        entries.append({
            "id": model_id, "label": model.get("displayName", model_id),
            "description": model.get("description", ""), "provider": "openai",
            "context": context, "default": model.get("isDefault", False),
            "efforts": [r["reasoningEffort"] for r in model.get("supportedReasoningEfforts", [])],
            "modalities": model.get("inputModalities", ["text"]),
        })
    if not entries:
        raise ValueError("Codex returned no selectable models")
    return entries


def get_json(url, key):
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def local_entries(live, metadata):
    known = {m["slug"]: m for m in metadata["models"]}
    entries = []
    for model in live["data"]:
        model_id = model["id"]
        source = known.get(model_id, {})
        context = model.get("context_length") or source.get("context_window")
        if not isinstance(context, int) or context <= 0:
            raise ValueError(f"Fleet context metadata missing for {model_id}")
        entries.append({"id": model_id, "label": source.get("display_name", model.get("name", model_id)),
                        "description": source.get("description", "Local fleet model"),
                        "provider": "local", "context": context})
    return entries


def picker_settings(entries, used=None, current_limit=None):
    def row(model):
        overflow = max(0, (used or 0) - model["context"])
        usage = "current usage not measured yet" if used is None else f"current ≈{used:,} tokens"
        if used is not None and current_limit is not None:
            usage = f"current ≈{used:,}/{current_limit:,} tokens"
        warning = f"; ≈{overflow:,} tokens need summarizing/removing" if overflow else "; fits" if used is not None else ""
        provider = "OpenAI" if model["provider"] == "openai" else model["provider"].title()
        return {"model": model["id"],
                "label": ("⚠ " if overflow else "") + f'{provider}: {model["label"]}',
                "description": f'limit {model["context"]:,}; {usage}{warning}'}
    return {"modelPicker": {"replaceBuiltInOptions": True, "options": [
        row(m) for m in entries]}}


def overlay(base, extra):
    """Preserve user customization, appending wrapper hooks to existing hooks."""
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = overlay(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list) and key in ("UserPromptSubmit",):
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


def refresh_gateway(config_path, entries, router_url=None, router_key=None):
    config = json.loads(config_path.read_text())
    # CLIProxyAPI's own catalog is not the authority for Codex availability.
    # Generate its Codex registrations from the same live list as the picker.
    definitions = [{"id": m["id"], "object": "model", "owned_by": "openai", "type": "openai",
                    "display_name": m["label"], "description": m["description"],
                    "context_length": m["context"], "supported_parameters": ["tools"],
                    "supportedInputModalities": m.get("modalities", ["text"]),
                    "thinking": {"levels": m.get("efforts", [])}}
                   for m in entries if m["provider"] == "openai"]
    if definitions:
        catalog = {"codex-" + tier: definitions for tier in ("free", "team", "plus", "pro")}
        # A changed source path triggers immediate refresh on config reload;
        # overwriting one catalog path otherwise waits for the proxy's timer.
        digest = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()[:16]
        path = config_path.parent / "catalogs" / (digest + ".json")
        write_json(path, catalog)
        config.setdefault("models", {})["catalog"] = str(path)
    locals_ = [m for m in entries if m["provider"] == "local"]
    if locals_:
        groups = config.setdefault("api-keys", {}).setdefault("claude", [])
        group = {"name": "local-llm-fleet", "base-url": router_url,
                 "models": [{"name": m["id"], "alias": m["id"], "max-context-length": m["context"]}
                            for m in locals_], "keys": [{"api-key": router_key}]}
        groups[:] = [g for g in groups if g.get("name") != group["name"]] + [group]
        overrides = config.setdefault("requests", {}).setdefault("payload", {}).setdefault("override", [])
        local_ids = {m["id"] for m in locals_}
        overrides[:] = [r for r in overrides if not all(
            m.get("name") in local_ids for m in r.get("models", []))]
        overrides.append({"models": [{"name": m["id"], "protocol": "claude"} for m in locals_],
                          "params": {"max_tokens": 4096}})
    write_json(config_path, config, in_place=True)


def launch(args):
    config_dir = Path(os.environ.get("CLAUDE_OPENAI_CONFIG_DIR", Path.home() / ".config/local-llm/openai"))
    providers = os.environ.get("CLAUDE_PICKER_PROVIDERS", "openai,local").split(",")
    if not providers or any(p not in ("openai", "local") for p in providers):
        raise ValueError("CLAUDE_PICKER_PROVIDERS must be openai, local, or openai,local")
    entries = []
    if "openai" in providers:
        visible = codex_models()
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        entries.extend(openai_entries(visible, json.loads((codex_home / "models_cache.json").read_text())))
    router_url = router_key = None
    if "local" in providers:
        router_url = os.environ.get("LOCAL_LLM_ROUTER_BASE_URL", "http://" + os.environ.get(
            "LOCAL_LLM_ROUTER_HOST", "macmini") + ":" + os.environ.get("LOCAL_LLM_ROUTER_PORT", "8081"))
        router_key = os.environ.get("LOCAL_LLM_ROUTER_API_KEY")
        if not router_key:
            key_path = Path(os.environ.get("LOCAL_LLM_ROUTER_API_KEY_FILE", str(Path(os.environ.get(
                "LOCAL_LLM_CONFIG_DIR", Path.home() / ".config/local-llm")) / "codex-router-key")))
            router_key = key_path.read_text().strip()
        entries.extend(local_entries(get_json(router_url.rstrip("/") + "/v1/models", router_key),
                                     json.loads((ROOT / "codex-metadata/local-router-model-catalog.json").read_text())))
    if not entries:
        raise ValueError("No selectable models discovered")
    default = next((m for m in entries if m.get("default")), entries[0])["id"]
    model = os.environ.get("CLAUDE_OPENAI_MODEL", default)
    # --model must also participate in context and availability validation.
    for index, arg in enumerate(args):
        if arg == "--model" and index + 1 < len(args):
            model = args[index + 1]
        elif arg.startswith("--model="):
            model = arg.split("=", 1)[1]
    if model not in {m["id"] for m in entries}:
        raise ValueError(f"Selected model {model} is absent from the discovered picker")
    refresh_gateway(config_dir / "gateway.json", entries, router_url, router_key)
    # Do not shrink the whole session to the smallest offered model. Show its
    # limit and current overflow in live picker rows, with a guard before the
    # next prompt when the chosen model cannot fit the existing conversation.
    context = max(m["context"] for m in entries)
    override = os.environ.get("CLAUDE_OPENAI_CONTEXT_TOKENS")
    if override:
        context = min(context, int(override))
    if context <= 0:
        raise ValueError("Context cap must be positive")
    key = os.environ["CLAUDE_OPENAI_GATEWAY_KEY"]
    env = os.environ.copy()
    env.update(ANTHROPIC_MODEL=model, ANTHROPIC_SMALL_FAST_MODEL=model,
               ANTHROPIC_BASE_URL=env.get("CLAUDE_OPENAI_BASE_URL", "http://127.0.0.1:8317"),
               CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(context),
               CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(min(32000, context // 8)),
               CLAUDE_CODE_DISABLE_1M_CONTEXT="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_SAFE_MODE", "CLAUDE_CODE_USE_BEDROCK",
                 "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "CLAUDE_CODE_OAUTH_TOKEN",
                 "CLAUDE_CODE_USE_ANTHROPIC_AWS", "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD", "CLAUDE_CODE_USE_MANTLE",
                 "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
        env.pop(name, None)
    for tier in ("OPUS", "SONNET", "HAIKU", "FABLE"):
        env["ANTHROPIC_DEFAULT_" + tier + "_MODEL"] = model
    # One private live settings file per process lets the status-line callback
    # refresh /model warnings from actual usage without changing user settings.
    state_dir = Path(tempfile.mkdtemp(prefix="picker-", dir=config_dir))
    # --settings content is pinned at boot in Claude 2.1.310, so it cannot
    # refresh picker labels. A private user-settings overlay is watched live.
    # Share the original projects/plugins/memory/etc. through symlinks.
    source_dir = Path(os.environ.get("CLAUDE_PICKER_ORIGINAL_CONFIG_DIR", os.environ.get(
        "CLAUDE_CONFIG_DIR", Path.home() / ".claude"))).resolve()
    user_dir = state_dir / "claude"
    user_dir.mkdir(mode=0o700)
    if source_dir.exists():
        for child in source_dir.iterdir():
            if child.name != "settings.json":
                (user_dir / child.name).symlink_to(child.resolve())
    global_config = source_dir / ".claude.json"
    if not global_config.exists():
        global_config = Path.home() / ".claude.json"
    if global_config.exists():
        # Keep trust/MCP/preferences, but use separate locks for the private
        # config copy rather than concurrent locks on a shared symlink target.
        (user_dir / ".claude.json").unlink(missing_ok=True)
        write_json(user_dir / ".claude.json", json.loads(global_config.read_text()))
    settings_path = user_dir / "settings.json"
    state_path = state_dir / "state.json"
    original_settings = {}
    user_settings = source_dir / "settings.json"
    if user_settings.exists():
        original_settings = json.loads(user_settings.read_text())
    original_status = original_settings.get("statusLine", {})
    settings = picker_settings(entries)
    # apiKeyHelper avoids Claude's interactive "use this API key?" prompt;
    # the gateway bearer remains process-local and never enters settings.
    settings["apiKeyHelper"] = 'printf \'%s\' "$CLAUDE_OPENAI_GATEWAY_KEY"'
    import shlex
    callback = shlex.join([sys.executable, str(ROOT / "bin/claude-picker-status.py"), str(state_path)])
    settings["statusLine"] = {"type": "command", "command": callback}
    settings["hooks"] = {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": callback + " --guard"}]}]}
    settings["modelSettings"] = {m["id"]: {"autoCompactWindow": min(m["context"], context, 1000000)}
                                 for m in entries if min(m["context"], context) >= 100000}
    write_json(settings_path, overlay(original_settings, settings))
    write_json(state_path, {"entries": entries, "settings_path": str(settings_path),
                            "current_model": model, "used": None, "original_status": original_status})
    print(f'Claude picker: {len(entries)} discovered models ({",".join(providers)}); '
          'smaller models show live context warnings.', file=sys.stderr)
    env["CLAUDE_CONFIG_DIR"] = str(user_dir)
    env["CLAUDE_PICKER_ORIGINAL_CONFIG_DIR"] = str(source_dir)
    os.execvpe("claude", ["claude", "--model", model, *args], env)


if __name__ == "__main__":
    try:
        launch(sys.argv[1:])
    except (OSError, ValueError, RuntimeError, KeyError, queue.Empty) as error:
        # Never print HTTP bodies, auth/config content, or credential exceptions.
        print(f"error: Claude picker setup failed ({type(error).__name__}). "
              "Check Codex login, gateway config and fleet reachability. "
              "Use CLAUDE_PICKER_PROVIDERS=openai for an OpenAI-only picker.", file=sys.stderr)
        sys.exit(1)
