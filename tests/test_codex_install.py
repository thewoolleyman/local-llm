import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "bin/install-codex-local-llm.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MigrationTest(unittest.TestCase):
    def test_preserves_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            untouched = ('model_reasoning_effort = "max"\n'
                         '# Keep comments and machine settings\n'
                         '[model_providers.local-llm-fleet]\n'
                         'base_url = "http://macmini:8081/v1"\n'
                         'wire_api = "responses"\n'
                         '[model_providers.local-llm-fleet.auth]\n'
                         'command = "cat"\nargs = ["/private/existing-key"]\n'
                         '[projects."/some/project"]\ntrust_level = "trusted"\n')
            original = 'model = "old-model"\nmodel_catalog_json = "/old.json"\n' + untouched
            config.write_text(original)
            profile = root / "local-llm.config.toml"
            profile.write_text('model = "m4max/qwen3-coder-next"\n[features]\nshell_tool = true\n')
            catalog = ROOT / "codex-metadata/local-router-model-catalog.json"
            installer.install(root, catalog, root / "missing-key")
            self.assertEqual(config.read_text(), untouched)
            self.assertEqual(tomllib.loads(profile.read_text())["model"], "m4max/qwen3-coder-next")
            self.assertTrue(tomllib.loads(profile.read_text())["features"]["shell_tool"])
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            installer.install(root, catalog, root / "missing-key")
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            backups = list(root.glob("config.toml.bak-*"))
            self.assertEqual(backups[0].read_text(), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_new_provider_references_key_without_copying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "router-key"
            key.write_text("test-secret")
            installer.install(root, ROOT / "codex-metadata/local-router-model-catalog.json", key)
            text = (root / "local-llm.config.toml").read_text()
            self.assertNotIn("test-secret", text)
            self.assertEqual(tomllib.loads(text)["model_providers"]["local-llm-fleet"]["auth"]["args"], [str(key.resolve())])

    def test_unrelated_provider_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            config.write_text('model_provider = "enterprise"\n')
            with self.assertRaises(ValueError):
                installer.install(root, ROOT / "codex-metadata/local-router-model-catalog.json", root / "key")
            self.assertEqual(list(root.iterdir()), [config])
            self.assertEqual(config.read_text(), 'model_provider = "enterprise"\n')

    def test_unsupported_layout_does_not_silently_drop_content(self):
        with self.assertRaises((ValueError, tomllib.TOMLDecodeError)):
            installer.replace_top_level('"model" = "old"\n', {"model": None})
        with self.assertRaises((ValueError, tomllib.TOMLDecodeError)):
            installer.replace_top_level('model = """\nold\n"""\n', {"model": None})


if __name__ == "__main__":
    unittest.main()
