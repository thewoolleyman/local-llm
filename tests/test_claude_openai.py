"""Verify credential isolation and full-harness wrapper behavior without inference."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure", ROOT / "bin/configure-claude-openai.py")
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


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
            configure.configure(config, auth)
            self.assertEqual(json.loads(gateway_auth.read_text())["refresh_token"], "gateway-refreshed")
            self.assertEqual(auth.read_bytes(), original)
            for path in (gateway_auth, config / "secrets.env", config / "gateway.json"):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            settings = json.loads((config / "gateway.json").read_text())
            self.assertEqual(settings["server"]["host"], "127.0.0.1")

    def test_wrapper_keeps_harness_and_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            claude = root / "claude"
            claude.write_text('#!/usr/bin/env python3\nimport os,sys,json\nprint(json.dumps({"args":sys.argv[1:],"env":dict(os.environ)}))\n')
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
            self.assertEqual(data["args"], ["--model", "gpt-6.1-sol", *args])
            self.assertEqual(data["env"]["ANTHROPIC_MODEL"], "gpt-6.1-sol")
            self.assertEqual(data["env"]["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "500000")
            self.assertNotIn("CLAUDE_CODE_SIMPLE", data["env"])
            self.assertNotIn("CLAUDE_CODE_USE_VERTEX", data["env"])
            self.assertEqual(data["env"]["ANTHROPIC_API_KEY"], "test-key")
            self.assertEqual(data["env"]["XDG_RUNTIME_DIR"], env["XDG_RUNTIME_DIR"])
            self.assertEqual(data["env"]["TMPDIR"], env["TMPDIR"])


if __name__ == "__main__":
    unittest.main()
