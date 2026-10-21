#!/usr/bin/env python3
"""Stdlib-only tests for ensure_plugins. Run: python3 -m unittest -v."""

from __future__ import annotations

import json
import unittest

import ensure_plugins as hook

_FLEET_SHAPE = {
    "extraKnownMarketplaces": {
        "livespec": {
            "source": {
                "source": "github",
                "repo": "thewoolleyman/livespec",
                "ref": "release",
            }
        },
        "livespec-overseer": {
            "source": {
                "source": "github",
                "repo": "thewoolleyman/livespec-overseer",
                "ref": "release",
            }
        },
    },
    "enabledPlugins": {
        "livespec@livespec": True,
        "livespec-overseer@livespec-overseer": True,
    },
}


def _commands(settings: object) -> list[tuple[str, ...]]:
    return list(hook.planned_commands(settings_text=json.dumps(settings)))


class PlannedCommandTests(unittest.TestCase):
    def test_a_newly_enabled_plugin_is_added_and_installed_not_only_updated(
        self,
    ) -> None:
        """The defect this hook exists to fix.

        A loop that only runs `plugin update` can never provision a plugin
        that was never installed: `update` on an absent plugin does nothing.
        Both `marketplace add` and `plugin install` must be planned.
        """
        planned = _commands(_FLEET_SHAPE)
        self.assertIn(
            (
                "claude",
                "plugin",
                "marketplace",
                "add",
                "thewoolleyman/livespec-overseer@release",
            ),
            planned,
        )
        self.assertIn(
            (
                "claude",
                "plugin",
                "install",
                "livespec-overseer@livespec-overseer",
                "-s",
                "project",
            ),
            planned,
        )

    def test_every_enabled_plugin_is_derived_from_settings_not_a_literal_list(
        self,
    ) -> None:
        """No plugin name is hard-coded.

        A hard-coded list silently omits whatever was added to settings.json
        without a paired hook edit, which is the currency bug this replaces.
        Adding a fifth marketplace must need no change to this hook.
        """
        settings = json.loads(json.dumps(_FLEET_SHAPE))
        settings["extraKnownMarketplaces"]["brand-new"] = {
            "source": {
                "source": "github",
                "repo": "thewoolleyman/brand-new",
                "ref": "v1.2.3",
            }
        }
        settings["enabledPlugins"]["brand-new@brand-new"] = True
        planned = _commands(settings)
        self.assertIn(
            ("claude", "plugin", "marketplace", "add", "thewoolleyman/brand-new@v1.2.3"),
            planned,
        )
        self.assertIn(
            ("claude", "plugin", "install", "brand-new@brand-new", "-s", "project"),
            planned,
        )

    def test_currency_is_preserved_marketplace_update_runs_first(self) -> None:
        """The mechanism this replaces guaranteed currency, and must keep it.

        `marketplace update` refreshes the catalogs before anything resolves
        against them, so it has to be the FIRST command, not merely present.
        """
        planned = _commands(_FLEET_SHAPE)
        self.assertEqual(planned[0], ("claude", "plugin", "marketplace", "update"))

    def test_each_enabled_plugin_is_also_updated_after_install(self) -> None:
        planned = _commands(_FLEET_SHAPE)
        install = planned.index(
            ("claude", "plugin", "install", "livespec@livespec", "-s", "project")
        )
        update = planned.index(
            ("claude", "plugin", "update", "livespec@livespec", "-s", "project")
        )
        self.assertLess(install, update)

    def test_a_disabled_plugin_is_not_installed(self) -> None:
        settings = json.loads(json.dumps(_FLEET_SHAPE))
        settings["enabledPlugins"]["livespec-overseer@livespec-overseer"] = False
        planned = _commands(settings)
        self.assertNotIn(
            (
                "claude",
                "plugin",
                "install",
                "livespec-overseer@livespec-overseer",
                "-s",
                "project",
            ),
            planned,
        )

    def test_a_non_github_or_refless_marketplace_is_skipped(self) -> None:
        """`ref` lives under the record's `source` object, not at top level.

        A shallow read of a top-level `ref` returns None for every fleet peer,
        which would look like "no marketplace pins a ref" — the exact opposite
        of the truth. An entry genuinely missing repo/ref is skipped rather
        than turned into a malformed command.
        """
        settings = {
            "extraKnownMarketplaces": {
                "local": {"source": {"source": "directory", "path": "/tmp/x"}},
                "refless": {"source": {"source": "github", "repo": "o/r"}},
                "toplevel-ref": {"source": {"source": "github", "repo": "o/r2"}, "ref": "release"},
            },
            "enabledPlugins": {},
        }
        planned = _commands(settings)
        self.assertEqual(planned, [("claude", "plugin", "marketplace", "update")])

    def test_vacuous_settings_plan_nothing_beyond_the_catalog_refresh(self) -> None:
        self.assertEqual(
            _commands({}), [("claude", "plugin", "marketplace", "update")]
        )

    def test_malformed_settings_are_fail_open(self) -> None:
        """SessionStart must never be wedged by an unparsable settings file."""
        self.assertEqual(hook.planned_commands(settings_text="not json"), ())
        self.assertEqual(hook.planned_commands(settings_text="[1, 2]"), ())


class ProjectScopeTests(unittest.TestCase):
    def test_every_command_runs_with_the_project_directory_as_cwd(self) -> None:
        """`-s project` resolves the project from the PROCESS CWD.

        Measured against the real CLI: `claude plugin install … -s project`
        installs into whatever directory the process is in, and ignores
        `CLAUDE_PROJECT_DIR` entirely. Run from elsewhere it silently succeeds
        while recording nothing for this repository — an exit 0 that provisions
        nothing. The cwd must therefore be passed explicitly rather than
        inherited, so the hook cannot be defeated by its caller's cwd.
        """
        seen: list[str | None] = []

        def runner(*, args: tuple[str, ...], cwd: str | None = None) -> int:
            _ = args
            seen.append(cwd)
            return 0

        _ = hook.provision(
            settings_text=json.dumps(_FLEET_SHAPE),
            runner=runner,
            project_dir="/data/projects/homelab",
        )
        self.assertTrue(seen, "no command was attempted")
        self.assertEqual(set(seen), {"/data/projects/homelab"})


class MainContractTests(unittest.TestCase):
    def test_main_returns_zero_even_when_every_command_fails(self) -> None:
        """Fail-open: a broken `claude` CLI must not block session start."""
        attempted: list[tuple[str, ...]] = []

        def runner(*, args: tuple[str, ...], cwd: str | None = None) -> int:
            _ = cwd
            attempted.append(args)
            return 1

        code = hook.provision(
            settings_text=json.dumps(_FLEET_SHAPE), runner=runner, project_dir="/x"
        )
        self.assertEqual(code, 0)
        self.assertGreater(len(attempted), 1, "a failure must not abort the rest")

    def test_main_returns_zero_when_the_settings_file_is_absent(self) -> None:
        self.assertEqual(
            hook.provision(
                settings_text=None,
                runner=lambda *, args, cwd=None: 0,
                project_dir="/x",
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
