#!/usr/bin/env python3
"""Regression tests for scripts/odoo_auto_upgrade.py (standard library only)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("odoo_auto_upgrade.py")


class AutoUpgradeScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self.run_git("init", "-b", "staging")
        self.run_git("config", "user.name", "Test User")
        self.run_git("config", "user.email", "test@example.invalid")
        self.add_module("module_one", "19.0.1.0.0")
        self.add_module("module_two", "19.0.2.0.0")
        self.write("README.md", "project documentation\n")
        self.commit("baseline")
        self.base = self.sha()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_git(self, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def run_script(self, *extra: str) -> str:
        return subprocess.check_output(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--base", self.base, "--head", "HEAD", *extra],
            text=True,
        )

    def write(self, relative: str, content: str) -> None:
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def add_module(self, name: str, version: str) -> None:
        self.write(name + "/__init__.py", "")
        self.write(name + "/__manifest__.py", "{'name': '" + name + "', 'version': '" + version + "'}\n")

    def commit(self, message: str) -> None:
        self.run_git("add", ".")
        self.run_git("commit", "-m", message)

    def sha(self) -> str:
        return self.run_git("rev-parse", "HEAD")

    def version(self, module: str) -> str:
        return (self.repo / module / "__manifest__.py").read_text(encoding="utf-8").split("'version': '")[1].split("'", 1)[0]

    def test_python_model_change_bumps_one_module(self) -> None:
        self.write("module_one/models/model.py", "from odoo import models\n")
        self.commit("model")
        self.run_script("--write")
        self.assertEqual(self.version("module_one"), "19.0.1.0.1")
        self.assertEqual(self.version("module_two"), "19.0.2.0.0")

    def test_xml_security_and_data_changes_bump_their_modules(self) -> None:
        self.write("module_one/views/view.xml", "<odoo/>\n")
        self.write("module_two/security/ir.model.access.csv", "id,name\n")
        self.write("module_two/data/defaults.xml", "<odoo/>\n")
        self.commit("views security data")
        self.run_script("--write")
        self.assertEqual(self.version("module_one"), "19.0.1.0.1")
        self.assertEqual(self.version("module_two"), "19.0.2.0.1")

    def test_documentation_only_change_does_not_bump(self) -> None:
        self.write("module_one/docs/README.md", "How to use this module\n")
        self.commit("docs")
        result = self.run_script("--write")
        self.assertIn("skipped: -", result)
        self.assertEqual(self.version("module_one"), "19.0.1.0.0")

    def test_version_only_manifest_change_is_not_bumped_again(self) -> None:
        self.write("module_one/__manifest__.py", "{'name': 'module_one', 'version': '19.0.1.0.9'}\n")
        self.commit("manual version")
        self.run_script("--write")
        self.assertEqual(self.version("module_one"), "19.0.1.0.9")

    def test_nested_addon_reference_is_not_a_deployable_module(self) -> None:
        self.write(
            "mobile_app/odoo_addon/copied_module/__manifest__.py",
            "{'name': 'copied_module', 'version': '19.0.9.0.0'}\n",
        )
        self.commit("mobile reference")
        result = self.run_script("--write")
        self.assertIn("no material repository-root", result)
        self.assertEqual(self.version("module_one"), "19.0.1.0.0")

    def test_new_and_removed_modules_are_safe(self) -> None:
        self.add_module("new_module", "19.0.3.0.0")
        for path in (self.repo / "module_two").rglob("*"):
            if path.is_file():
                path.unlink()
        (self.repo / "module_two").rmdir()
        self.commit("add and remove modules")
        result = self.run_script("--write")
        self.assertIn("new module", result)
        self.assertIn("module removed", result)
        self.assertEqual(self.version("new_module"), "19.0.3.0.0")

    def test_renamed_python_file_bumps_module_once(self) -> None:
        self.write("module_one/models/old.py", "VALUE = 1\n")
        self.commit("add model")
        self.base = self.sha()
        self.run_git("mv", "module_one/models/old.py", "module_one/models/new.py")
        self.commit("rename model")
        self.run_script("--write")
        self.assertEqual(self.version("module_one"), "19.0.1.0.1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
