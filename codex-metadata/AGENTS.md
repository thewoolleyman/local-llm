# Local Codex model metadata

`model-catalog.json` is the Codex model catalog for the local llama.cpp
provider used by this repository. It prevents Codex from falling back to
generic metadata for `qwen3-coder-next` (the warning beginning “Model metadata
for ... not found”). The file contains no credentials or host-specific URLs.

## Install in a dedicated local profile

From the durable repository checkout, install the fleet profile:

```bash
python3 bin/install-codex-local-llm.py
codex --profile local-llm
```

The installer adds this setting only to `~/.codex/local-llm.config.toml`:

```toml
model_catalog_json = "/absolute/path/to/local-llm/codex-metadata/local-router-model-catalog.json"
```

Never set a local or combined static catalog in the normal base config:
`model_catalog_json` replaces live discovery instead of extending it, hiding
newly released OpenAI models. Catalog paths must be absolute. Start a new
Codex process after changes. Direct per-host connections using the unqualified
catalog also belong in their own explicit profiles.

## Repository wrapper

`bin/codex-local-llm` selects the installed `local-llm` profile in the usual
Codex home. It does not create an isolated `CODEX_HOME` or install the profile.

The direct-host catalog retains the unqualified `qwen3-coder-next` ID.
Both the wrapper and the standalone fleet profile use the
separate [`local-router-model-catalog.json`](./local-router-model-catalog.json)
with the qualified router IDs `macmini/qwen3-coder-next`,
`m4max/qwen3-coder-next`, and `gmktec/qwen3-coder-next`.

Verify the catalog parses before launching a session:

```bash
jq -e '.models[] | select(.slug == "qwen3-coder-next")' \
  codex-metadata/model-catalog.json >/dev/null
```

If Codex is upgraded and reports a catalog parse error, compare the enum
values in this file with that release's bundled catalog. In particular,
`visibility`, `shell_type`, `apply_patch_tool_type`, and
`web_search_tool_type` must use Codex protocol values.
