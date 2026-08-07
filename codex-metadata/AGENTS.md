# Local Codex model metadata

`model-catalog.json` is the Codex model catalog for the local llama.cpp
provider used by this repository. It prevents Codex from falling back to
generic metadata for `qwen3-coder-next` (the warning beginning “Model metadata
for ... not found”). The file contains no credentials or host-specific URLs.

## Install for a normal local Codex installation

From the repository root, set the absolute catalog path in the Codex config:

```bash
catalog="$PWD/codex-metadata/model-catalog.json"
codex -c "model_catalog_json=\"$catalog\""
```

For a persistent installation, add this line to `~/.codex/config.toml`:

```toml
model_catalog_json = "/absolute/path/to/local-llm/codex-metadata/model-catalog.json"
```

The path must be absolute. Restart Codex after changing it; the catalog is
loaded only during startup. Keep the normal `model =` and provider settings
appropriate for the installation, for example `model = "qwen3-coder-next"`
and a provider whose `base_url` points at the local server's `/v1` endpoint.

## Repository wrapper

`bin/codex-local-llm` sets `model_catalog_json` automatically in its isolated
`CODEX_HOME`, so no edit to `~/.codex/config.toml` is needed. This keeps local
LLM state separate from the user's normal OpenAI Codex installation.

Verify the catalog parses before launching a session:

```bash
jq -e '.models[] | select(.slug == "qwen3-coder-next")' \
  codex-metadata/model-catalog.json >/dev/null
```

If Codex is upgraded and reports a catalog parse error, compare the enum
values in this file with that release's bundled catalog. In particular,
`visibility`, `shell_type`, `apply_patch_tool_type`, and
`web_search_tool_type` must use Codex protocol values.
