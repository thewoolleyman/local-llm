#!/usr/bin/env python3
"""Refresh per-model context warnings from Claude's status-line usage payload."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location("picker", Path(__file__).with_name("claude-model-picker.py"))
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)


def update(state_path, payload):
    state = json.loads(state_path.read_text())
    usage = payload.get("context_window", {}).get("current_usage")
    if usage is not None:
        state["used"] = sum(usage.get(key, 0) or 0 for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    state["current_model"] = payload.get("model", {}).get("id", state["current_model"])
    current = next((m for m in state["entries"] if m["id"] == state["current_model"]), None)
    settings_path = Path(state["settings_path"])
    settings = json.loads(settings_path.read_text())
    settings.update(picker.picker_settings(state["entries"], state["used"], current["context"] if current else None))
    picker.write_json(settings_path, settings)
    picker.write_json(state_path, state)
    return state


def guard(state, payload):
    model = payload.get("model") or state["current_model"]
    entry = next((m for m in state["entries"] if m["id"] == model), None)
    if entry is not None and state["used"] is not None and state["used"] >= entry["context"]:
        overflow = state["used"] - entry["context"]
        return {"decision": "block", "reason": (
            f'{model} has a {entry["context"]:,}-token limit; this conversation currently uses '
            f'≈{state["used"]:,} tokens (≈{overflow:,} over the limit). Nothing was removed. '
            'Select the previous larger model and /compact, or start a fresh session for this model. '
            'Tokenization differs across providers; this is estimated overflow, not a measure of information lost.')}


def main():
    state_path = Path(sys.argv[1])
    raw = sys.stdin.read()
    payload = json.loads(raw)
    if "--guard" in sys.argv[2:]:
        result = guard(json.loads(state_path.read_text()), payload)
        if result:
            print(json.dumps(result))
        return
    state = update(state_path, payload)
    current = next((m for m in state["entries"] if m["id"] == state["current_model"]), None)
    if current and state["used"] is not None:
        # Give the existing user status line the active model's real limit.
        window = payload.setdefault("context_window", {})
        window["context_window_size"] = current["context"]
        window["used_percentage"] = min(100, round(state["used"] / current["context"] * 100))
        window["remaining_percentage"] = max(0, 100 - window["used_percentage"])
        raw = json.dumps(payload)
    original = state.get("original_status", {})
    if original.get("type") == "command" and original.get("command"):
        try:
            result = subprocess.run(original["command"], input=raw, shell=True,
                                    capture_output=True, text=True, timeout=5)
            if result.stdout:
                print(result.stdout.rstrip())
        except (OSError, subprocess.TimeoutExpired):
            pass
    if state["used"] is not None:
        limit = f'/{current["context"]:,}' if current else ""
        print(f'Picker context: ≈{state["used"]:,}{limit} tokens; /model shows target limits and overflow.')


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError):
        if "--guard" in sys.argv[2:]:
            print(json.dumps({"decision": "block", "reason": "Cannot verify picker context state; restart the wrapper to restore context warnings."}))
