"""Verify credential isolation and full-harness wrapper behavior without inference."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure", ROOT / "bin/configure-claude-openai.py")
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)
spec = importlib.util.spec_from_file_location("picker", ROOT / "bin/claude-model-picker.py")
picker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(picker)
spec = importlib.util.spec_from_file_location("status", ROOT / "bin/claude-picker-status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class ClaudeOpenAITest(unittest.TestCase):
    def test_private_config_preserves_both_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            auth = root / "codex.json"
            payload = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + 3600}).encode()).decode().rstrip("=")
            auth.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {
                "access_token": "header." + payload + ".signature", "refresh_token": "private"}}))
            original = auth.read_bytes()
            config = root / "gateway"
            configure.configure(config, auth)
            gateway_auth = config / "auth/codex.json"
            stored = json.loads(gateway_auth.read_text())
            self.assertEqual(stored["type"], "codex")
            stored["refresh_token"] = "gateway-refreshed"
            gateway_auth.write_text(json.dumps(stored))
            gateway_config = config / "gateway.json"
            value = json.loads(gateway_config.read_text())
            value["models"] = {"catalog": "/private/discovered-catalog.json"}
            gateway_config.write_text(json.dumps(value))
            inode = gateway_config.stat().st_ino
            configure.configure(config, auth)
            self.assertEqual(json.loads(gateway_auth.read_text())["refresh_token"], "gateway-refreshed")
            self.assertEqual(auth.read_bytes(), original)
            for path in (gateway_auth, config / "secrets.env", config / "gateway.json"):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            settings = json.loads((config / "gateway.json").read_text())
            self.assertEqual(settings["server"]["host"], "127.0.0.1")
            self.assertEqual(settings["models"], value["models"])
            self.assertEqual(gateway_config.stat().st_ino, inode)

    def test_wrapper_keeps_harness_and_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            claude = root / "python3"
            claude.write_text('#!' + sys.executable + '\nimport os,sys,json\nprint(json.dumps({"args":sys.argv[1:],"env":dict(os.environ)}))\n')
            claude.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"],
                       CLAUDE_OPENAI_SECRETS_FILE=str(root / "absent"),
                       CLAUDE_OPENAI_GATEWAY_KEY="test-key", CLAUDE_CODE_SIMPLE="1",
                       CLAUDE_CODE_USE_VERTEX="1", ANTHROPIC_MODEL="local-model",
                       XDG_RUNTIME_DIR="/run/user/test", TMPDIR="/tmp/test-runtime")
            env.pop("CLAUDE_OPENAI_MODEL", None)
            env.pop("CLAUDE_OPENAI_CONTEXT_TOKENS", None)
            args = ["--dangerously-skip-permissions", "-n", "coordinator"]
            result = subprocess.run([str(ROOT / "bin/claude-openai"), *args],
                                    env=env, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            self.assertEqual(data["args"], [str(ROOT / "bin/claude-model-picker.py"), *args])
            self.assertEqual(data["env"]["CLAUDE_OPENAI_GATEWAY_KEY"], "test-key")
            self.assertEqual(data["env"]["XDG_RUNTIME_DIR"], env["XDG_RUNTIME_DIR"])
            self.assertEqual(data["env"]["TMPDIR"], env["TMPDIR"])

    def test_new_codex_models_and_removals_follow_discovery(self):
        cache = {"models": [{"slug": "future-model", "context_window": 640000},
                            {"slug": "retired-model", "context_window": 900000}]}
        entries = picker.openai_entries([
            {"model": "future-model", "displayName": "Future", "isDefault": True}], cache)
        self.assertEqual([m["id"] for m in entries], ["future-model"])
        self.assertEqual(entries[0]["context"], 640000)
        with self.assertRaises(ValueError):
            picker.openai_entries([{"model": "unknown-context"}], cache)

    def test_mixed_picker_preserves_large_context_and_correct_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "gateway.json").write_text(json.dumps({"server": {"host": "127.0.0.1"}}))
            (root / "models_cache.json").write_text(json.dumps({"models": [
                {"slug": "future-model", "context_window": 640000}]}))
            source = root / "original-claude"
            source.mkdir()
            (source / "projects").mkdir()
            original = {"model": "opus", "hooks": {"UserPromptSubmit": [{"hooks": [
                {"type": "command", "command": "existing-user-hook"}]}]}}
            (source / "settings.json").write_text(json.dumps(original))
            env = dict(os.environ, CLAUDE_OPENAI_CONFIG_DIR=str(root), CODEX_HOME=str(root),
                       CLAUDE_CONFIG_DIR=str(source), CLAUDE_PICKER_ORIGINAL_CONFIG_DIR=str(source),
                       CLAUDE_OPENAI_GATEWAY_KEY="gateway-only", LOCAL_LLM_ROUTER_API_KEY="fleet-only",
                       CLAUDE_PICKER_PROVIDERS="openai,local", CLAUDE_CODE_SIMPLE="1",
                       CLAUDE_CODE_USE_VERTEX="1", XDG_RUNTIME_DIR="/run/user/test", TMPDIR="/tmp/test")
            env.pop("CLAUDE_OPENAI_MODEL", None)
            env.pop("CLAUDE_OPENAI_CONTEXT_TOKENS", None)
            visible = [{"model": "future-model", "displayName": "Future", "isDefault": True}]
            local = {"data": [{"id": "macmini/qwen3-coder-next"}]}
            with patch.dict(os.environ, env, clear=True), patch.object(picker, "codex_models", return_value=visible), \
                 patch.object(picker, "get_json", return_value=local), patch.object(picker.os, "execvpe") as execute:
                picker.launch(["--dangerously-skip-permissions", "-n", "proof"])
            _, args, launched = execute.call_args.args
            self.assertEqual(args[1:3], ["--model", "future-model"])
            settings = json.loads((Path(launched["CLAUDE_CONFIG_DIR"]) / "settings.json").read_text())
            self.assertEqual([m["model"] for m in settings["modelPicker"]["options"]],
                             ["future-model", "macmini/qwen3-coder-next"])
            self.assertEqual(launched["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "640000")
            self.assertEqual(launched["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], "32000")
            self.assertNotIn("CLAUDE_CODE_SIMPLE", launched)
            self.assertNotIn("CLAUDE_CODE_USE_VERTEX", launched)
            self.assertEqual(launched["XDG_RUNTIME_DIR"], env["XDG_RUNTIME_DIR"])
            self.assertEqual(json.loads((source / "settings.json").read_text()), original)
            self.assertEqual(len(settings["hooks"]["UserPromptSubmit"]), 2)
            self.assertEqual((Path(launched["CLAUDE_CONFIG_DIR"]) / "projects").resolve(), source / "projects")
            self.assertNotIn("--bare", args)
            config = json.loads((root / "gateway.json").read_text())
            group = config["api-keys"]["claude"][0]
            self.assertEqual(group["models"][0]["name"], "macmini/qwen3-coder-next")
            self.assertEqual(group["keys"][0]["api-key"], "fleet-only")
            self.assertIn("CLAUDE_OPENAI_GATEWAY_KEY", settings["apiKeyHelper"])
            self.assertEqual(launched["CLAUDE_OPENAI_GATEWAY_KEY"], "gateway-only")
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", launched)
            self.assertNotIn("ANTHROPIC_API_KEY", launched)
            catalog = json.loads(Path(config["models"]["catalog"]).read_text())
            self.assertEqual(catalog["codex-pro"][0]["id"], "future-model")
            self.assertEqual((root / "gateway.json").stat().st_mode & 0o777, 0o600)

    def test_usage_warnings_refresh_and_guard_without_removing_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = [{"id": "large", "label": "Large", "provider": "openai", "context": 500000},
                       {"id": "small", "label": "Small", "provider": "local", "context": 32768}]
            picker.write_json(root / "settings.json", {**picker.picker_settings(entries),
                                                      "statusLine": {"command": "preserve-me"}})
            picker.write_json(root / "state.json", {"entries": entries,
                "settings_path": str(root / "settings.json"), "current_model": "large", "used": None})
            state = status.update(root / "state.json", {"model": {"id": "small"}, "context_window": {
                "current_usage": {"input_tokens": 18000, "cache_read_input_tokens": 80000, "output_tokens": 2000}}})
            settings = json.loads((root / "settings.json").read_text())
            rows = settings["modelPicker"]["options"]
            self.assertEqual([r["model"] for r in rows], ["large", "small"])
            self.assertIn("100,000", rows[1]["description"])
            self.assertIn("67,232", rows[1]["description"])
            self.assertTrue(rows[1]["label"].startswith("⚠"))
            self.assertFalse(rows[0]["label"].startswith("⚠"))
            self.assertEqual(settings["statusLine"]["command"], "preserve-me")
            block = status.guard(state, {})
            self.assertEqual(block["decision"], "block")
            self.assertIn("Nothing was removed", block["reason"])
            self.assertIsNone(status.guard(state, {"model": "large"}))
            state = status.update(root / "state.json", {"context_window": {
                "current_usage": {"input_tokens": 8000, "output_tokens": 1000}}})
            self.assertIsNone(status.guard(state, {}))


if __name__ == "__main__":
    unittest.main()
