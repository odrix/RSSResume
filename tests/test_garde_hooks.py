"""Ce que le garde-fou des hooks Claude Code refuse, et surtout ce qu'il laisse passer.

Un garde trop large bloque le travail ordinaire (`2>&1`, `os.environ`, `.env.example`) et
finit désactivé ; un garde trop étroit laisse repasser le `sed -i` qui a réécrit le dépôt.
Les deux bords sont donc testés.
"""

import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest
from unittest import mock

CHEMIN = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "garde.py"
_spec = importlib.util.spec_from_file_location("garde", CHEMIN)
garde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(garde)


def bash(commande):
    return garde.motif_de_refus("Bash", {"command": commande})


class SecretsTests(unittest.TestCase):
    def test_reading_or_writing_the_user_env_files_is_refused(self):
        for chemin in (".env", ".env.local", r"D:\Projets\RSSResume\.env.local", "/x/.env"):
            with self.subTest(chemin=chemin):
                self.assertIsNotNone(garde.motif_de_refus("Read", {"file_path": chemin}))
                self.assertIsNotNone(garde.motif_de_refus("Edit", {"file_path": chemin}))

    def test_the_example_file_stays_editable(self):
        self.assertIsNone(garde.motif_de_refus("Edit", {"file_path": ".env.example"}))

    def test_searching_the_code_for_env_is_not_reading_it(self):
        self.assertIsNone(garde.motif_de_refus("Grep", {"pattern": r"\.env", "path": "rssresume"}))

    def test_the_shell_cannot_reach_the_env_files_either(self):
        self.assertIsNotNone(bash("cat .env.local"))
        self.assertIsNotNone(garde.motif_de_refus("PowerShell", {"command": "Get-Content .env"}))

    def test_lookalikes_are_not_secrets(self):
        for commande in ("python -c 'import os; os.environ'", "cat .env.example", "ls .envrc"):
            with self.subTest(commande=commande):
                self.assertIsNone(bash(commande))


class EditionAuShellTests(unittest.TestCase):
    def test_in_place_sed_is_refused(self):
        for commande in ("sed -i 's/a/b/' f.py", "sed -ri 's/a/b/' f.py", "sed --in-place 's/a/b/' f"):
            with self.subTest(commande=commande):
                self.assertIn("sed -i", bash(commande))

    def test_reading_sed_and_a_case_insensitive_grep_downstream_pass(self):
        self.assertIsNone(bash("sed -n '1,5p' f.py"))
        self.assertIsNone(bash("sed -n '1,5p' f.py | grep -i erreur"))

    def test_heredoc_is_refused(self):
        self.assertIn("heredoc", bash("cat <<'EOF'\nx\nEOF"))

    def test_redirection_into_a_repo_file_is_refused(self):
        for commande in ("echo x > f.py", "echo x >> notes.md", 'git diff > "sortie.txt"'):
            with self.subTest(commande=commande):
                self.assertIn("redirection", bash(commande))

    def test_descriptors_sinks_and_temp_dirs_are_allowed(self):
        for commande in (
            "git log 2>&1 | head",
            "ls x 2>/dev/null",
            "cmd > /dev/null",
            "cmd > C:/Users/x/AppData/Local/Temp/claude/scratchpad/sortie.txt",
            "python -c 'print(1 >= 0)'",
            "python -c 'f = lambda: a -> b'",
        ):
            with self.subTest(commande=commande):
                self.assertIsNone(bash(commande))

    def test_a_chevron_inside_quotes_is_not_a_redirection(self):
        self.assertIsNone(bash('git commit -m "Co-Authored-By: X <x@y.com>" -m "suite"'))
        self.assertIsNone(bash("python -c 'print(2 > 1)'"))
        self.assertIn("redirection", bash('echo "a > b" > f.txt'))

    def test_powershell_writers_are_refused(self):
        for commande in ("Set-Content f.py 'x'", "'x' | Out-File f.py", "x 2>$null; Add-Content f 'y'"):
            with self.subTest(commande=commande):
                self.assertIsNotNone(garde.motif_de_refus("PowerShell", {"command": commande}))

    def test_powershell_null_sink_is_allowed(self):
        self.assertIsNone(garde.motif_de_refus("PowerShell", {"command": "git fetch 2>$null"}))

    def test_other_tools_are_not_inspected(self):
        self.assertIsNone(garde.motif_de_refus("WebSearch", {"query": "sed -i > .env"}))


class SuiteTests(unittest.TestCase):
    def test_the_project_root_is_found_from_a_nested_file(self):
        racine = CHEMIN.parents[2]
        self.assertEqual(racine, garde.racine_du_projet(racine / "rssresume" / "llm"))

    def test_outside_a_project_there_is_no_root(self):
        with tempfile.TemporaryDirectory() as dossier:
            self.assertIsNone(garde.racine_du_projet(pathlib.Path(dossier)))

    def test_editing_a_non_python_file_does_not_run_the_suite(self):
        with mock.patch.object(garde, "lancer_la_suite") as lancer:
            self.assertEqual(0, garde.post({"tool_input": {"file_path": "README.md"}}))
        lancer.assert_not_called()

    def test_a_red_suite_after_an_edit_is_reported_to_the_model(self):
        fichier = str(CHEMIN.parents[2] / "rssresume" / "cli.py")
        with mock.patch.object(garde, "lancer_la_suite", return_value=(False, "FAILED (failures=1)")):
            with contextlib.redirect_stderr(io.StringIO()) as erreurs:
                self.assertEqual(2, garde.post({"tool_input": {"file_path": fichier}}))
        self.assertIn("FAILED (failures=1)", erreurs.getvalue())

    def test_stop_does_not_loop_once_already_relaunched(self):
        with mock.patch.object(garde, "lancer_la_suite") as lancer:
            self.assertEqual(0, garde.stop({"stop_hook_active": True}))
        lancer.assert_not_called()

    def test_stop_skips_the_suite_when_no_python_changed(self):
        with mock.patch.object(garde, "python_modifie", return_value=False), mock.patch.object(
            garde, "lancer_la_suite"
        ) as lancer:
            self.assertEqual(0, garde.stop({"cwd": str(CHEMIN.parents[2])}))
        lancer.assert_not_called()

    def test_stop_refuses_to_conclude_on_a_red_suite(self):
        with mock.patch.object(garde, "python_modifie", return_value=True), mock.patch.object(
            garde, "lancer_la_suite", return_value=(False, "FAILED")
        ), contextlib.redirect_stderr(io.StringIO()) as erreurs:
            self.assertEqual(2, garde.stop({"cwd": str(CHEMIN.parents[2])}))
        self.assertIn("suite est rouge", erreurs.getvalue())


if __name__ == "__main__":
    unittest.main()
