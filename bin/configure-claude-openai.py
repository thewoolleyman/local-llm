#!/usr/bin/env python3
"""Create private CLIProxyAPI v8 config using an existing Codex ChatGPT login.

Install cli-proxy-api separately. This only writes under the user's config dir;
it never modifies Codex credentials. Existing gateway credentials are preserved.
"""
import argparse
import base64
import datetime
import fcntl
import json
import os
from pathlib import Path
import secrets


def private_json(path, value, *, in_place=False):
    # Replace atomically, with restrictive permissions from the first write.
    if in_place:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            json.dump(value, stream, indent=2)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        return
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def configure(config_dir, codex_auth):
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    auth_dir = config_dir / "auth"
    auth_dir.mkdir(exist_ok=True, mode=0o700)
    credential = auth_dir / "codex.json"
    if not credential.exists():
        auth = json.loads(codex_auth.read_text())
        if auth.get("auth_mode") != "chatgpt":
            raise ValueError("Codex must be signed in with ChatGPT")
        tokens = auth["tokens"]
        access = tokens["access_token"]
        payload = access.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        expiry = datetime.datetime.fromtimestamp(claims["exp"], datetime.timezone.utc)
        if expiry <= datetime.datetime.now(datetime.timezone.utc):
            raise ValueError("Codex access token expired; refresh the Codex login first")
        private_json(credential, {
            **tokens, "type": "codex", "expired": expiry.isoformat(),
            "last_refresh": auth.get("last_refresh", ""),
        })
    secret_file = config_dir / "secrets.env"
    if not secret_file.exists():
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("CLAUDE_OPENAI_GATEWAY_KEY=" + secrets.token_hex(32) + "\n")
    # Generated secrets.env deliberately has one plain hex assignment.
    assignment = secret_file.read_text().strip().split("=", 1)
    if len(assignment) != 2 or assignment[0] != "CLAUDE_OPENAI_GATEWAY_KEY":
        raise ValueError("Expected CLAUDE_OPENAI_GATEWAY_KEY in secrets.env")
    key = assignment[1]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("Gateway key must be 64 lowercase hex characters")
    config_file = config_dir / "gateway.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    config.update({"config-version": 8})
    config.setdefault("server", {}).update({"host": "127.0.0.1", "port": 8317})
    config.setdefault("access", {})["api-keys"] = [key]
    config.setdefault("oauth", {})["auth-dir"] = str(auth_dir.resolve())
    config.setdefault("management", {})["disable-control-panel"] = True
    # Preserve the live gateway's inode watch when reconfiguring it.
    private_json(config_file, config, in_place=True)
    print(f"Gateway config ready: {config_dir / 'gateway.json'} (credentials not printed)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path,
                        default=Path.home() / ".config/local-llm/openai")
    parser.add_argument("--codex-auth", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json")
    args = parser.parse_args()
    try:
        configure(args.config_dir, args.codex_auth)
    except (OSError, ValueError, KeyError, IndexError) as error:
        # Avoid including token-bearing input or JSON parse errors in output.
        parser.exit(1, f"error: gateway configuration failed ({type(error).__name__}); check private inputs\n")
