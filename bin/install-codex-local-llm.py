#!/usr/bin/env python3
"""Keep OpenAI discovery live and install the separate local fleet profile.

Requires Python 3.11+ and Codex 0.134+. Never reads or copies credential values.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import tomllib

KEYS = {"model", "model_provider", "model_catalog_json"}


def replace_top_level(source, updates):
    """Surgical edits; reject unsupported layouts rather than reserialize secrets."""
    original = tomllib.loads(source)
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("["):
            break
        match = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
        if match and match[1] in updates:
            lines[index] = ""
    prefix = "".join(f"{key} = {json.dumps(value)}\n"
                     for key, value in updates.items() if value is not None)
    result = prefix + "".join(lines)
    expected = dict(original)
    for key, value in updates.items():
        if value is None:
            expected.pop(key, None)
        else:
            expected[key] = value
    if tomllib.loads(result) != expected:
        raise ValueError("Unsupported TOML layout; refusing to alter unrelated settings")
    return result


def atomic_save(path, content):
    path = path.resolve()
    if path.exists() and path.read_text() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        fd, backup = tempfile.mkstemp(prefix=path.name + ".bak-", dir=path.parent)
        os.close(fd)
        shutil.copyfile(path, backup)  # mkstemp's 0600 protects any config secrets
        print(f"Backup: {backup}")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(codex_dir, catalog, key_file):
    catalog = catalog.resolve(strict=True)
    slugs = {m["slug"] for m in json.loads(catalog.read_text())["models"]}
    if "macmini/qwen3-coder-next" not in slugs:
        raise ValueError("Fleet catalog does not contain the default local model")
    config = codex_dir / "config.toml"
    profile = codex_dir / "local-llm.config.toml"
    base_text = config.read_text() if config.exists() else ""
    profile_text = profile.read_text() if profile.exists() else ""
    base = tomllib.loads(base_text)
    local = tomllib.loads(profile_text)
    if base.get("model_provider", "openai") not in {"openai", "local-llm-fleet"}:
        raise ValueError("Base uses another provider; refusing to change its routing")
    if "profile" in base or "profiles" in base:
        raise ValueError("Legacy profile configuration needs review before migration")
    updated_base = replace_top_level(base_text, {key: None for key in sorted(KEYS)})
    updates = {
        "model": local.get("model", "macmini/qwen3-coder-next"),
        "model_provider": "local-llm-fleet",
        "model_catalog_json": str(catalog),
        "model_reasoning_effort": local.get("model_reasoning_effort", "medium"),
    }
    if updates["model"] not in slugs:
        raise ValueError("Existing local default is absent from the fleet catalog")
    updated_profile = replace_top_level(profile_text, updates)
    provider = local.get("model_providers", {}).get("local-llm-fleet")
    provider = provider or base.get("model_providers", {}).get("local-llm-fleet")
    if not provider:
        key_file = key_file.resolve(strict=True)
        updated_profile += (
            '\n[model_providers.local-llm-fleet]\n'
            'name = "Local LLM fleet router on macmini"\n'
            'base_url = "http://macmini:8081/v1"\n'
            'wire_api = "responses"\n'
            '\n[model_providers.local-llm-fleet.auth]\n'
            'command = "cat"\n'
            f'args = [{json.dumps(str(key_file))}]\n'
            'timeout_ms = 1000\n'
        )
    elif provider.get("wire_api", "responses") != "responses":
        raise ValueError("Fleet provider must use the Responses API")
    # Validate both complete files before writing either. Install the profile first
    # so interruption cannot leave a newly unpinned base without a local profile.
    tomllib.loads(updated_profile)
    atomic_save(profile, updated_profile)
    atomic_save(config, updated_base)
    print(f"OK: OpenAI defaults unpinned; local fleet profile: {profile}")
    print("Start a new session: codex OR codex-local-llm (codex --profile local-llm)")
    print("A running shared app-server daemon can retain the old catalog even in new TUIs.")
    print("When its tasks are idle: codex app-server daemon restart; then verify /model.")
    print("For an isolated check without interrupting other tasks: codex --no-daemon")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--key-file", type=Path,
                        default=Path.home() / ".config/local-llm/codex-router-key")
    args = parser.parse_args()
    catalog = Path(__file__).resolve().parent.parent / "codex-metadata/local-router-model-catalog.json"
    try:
        install(args.codex_home, catalog, args.key_file)
    except (ValueError, OSError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
