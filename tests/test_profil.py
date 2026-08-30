"""Chargement du profil de pertinence et effets de son injection."""

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from rssresume.llm.prompts import article_system, scoring_system
from tests.support import empreinte
from rssresume.profil import DEFAULT_PROFIL, ENV_PROFIL, ENV_PROFIL_FILE, load_profil

AUTRE_PROFIL = "Vigneronne en Anjou, bio depuis 2019. Veille : météo, phytosanitaire, export."


class LoadProfilTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_without_configuration_the_default_profile_applies(self):
        self.assertEqual(DEFAULT_PROFIL, load_profil())

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_an_explicit_profile_wins(self):
        self.assertEqual(AUTRE_PROFIL, load_profil(AUTRE_PROFIL))

    @mock.patch.dict(os.environ, {ENV_PROFIL: f"  {AUTRE_PROFIL}  "}, clear=True)
    def test_the_inline_variable_is_read_and_trimmed(self):
        self.assertEqual(AUTRE_PROFIL, load_profil())

    @mock.patch.dict(os.environ, {ENV_PROFIL: "profil de l'environnement"}, clear=True)
    def test_an_explicit_profile_beats_the_environment(self):
        self.assertEqual(AUTRE_PROFIL, load_profil(AUTRE_PROFIL))

    def test_a_profile_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "profil.txt"
            fichier.write_text(AUTRE_PROFIL, encoding="utf-8")

            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                self.assertEqual(AUTRE_PROFIL, load_profil())

    def test_the_inline_variable_beats_the_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "profil.txt"
            fichier.write_text("profil du fichier", encoding="utf-8")
            env = {ENV_PROFIL: AUTRE_PROFIL, ENV_PROFIL_FILE: str(fichier)}

            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(AUTRE_PROFIL, load_profil())

    @mock.patch.dict(os.environ, {ENV_PROFIL_FILE: "/introuvable/profil.txt"}, clear=True)
    def test_an_unreadable_profile_file_raises(self):
        """Noter toute une journée contre le mauvais critère, sans rien dire, serait pire."""
        with self.assertRaises(ValueError):
            load_profil()

    def test_an_empty_profile_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fichier = pathlib.Path(tmpdir) / "vide.txt"
            fichier.write_text("   \n", encoding="utf-8")

            with mock.patch.dict(os.environ, {ENV_PROFIL_FILE: str(fichier)}, clear=True):
                with self.assertRaises(ValueError):
                    load_profil()


class InjectedProfileTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {}, clear=True)
    def test_both_prompts_carry_the_injected_profile(self):
        self.assertIn(AUTRE_PROFIL, scoring_system(AUTRE_PROFIL))
        self.assertIn(AUTRE_PROFIL, article_system(AUTRE_PROFIL))
        self.assertNotIn(DEFAULT_PROFIL, scoring_system(AUTRE_PROFIL))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_the_scoring_prompt_keeps_its_json_braces(self):
        """Le prompt est concaténé, pas formaté : ses accolades ne sont pas des champs."""
        self.assertIn('{"resultats": [{"id": "...", "score": 0', scoring_system(AUTRE_PROFIL))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_a_profile_containing_braces_is_accepted(self):
        profil = 'Développeur : je suis {"json"} et les accolades {} de près.'

        self.assertIn(profil, scoring_system(profil))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_changing_the_profile_invalidates_the_scoring_cache(self):
        """Sinon des scores calculés contre l'ancien profil survivraient au changement."""
        self.assertNotEqual(empreinte(), empreinte(AUTRE_PROFIL))
        # Même profil, même empreinte : relancer la journée ne repaie rien.
        self.assertEqual(empreinte(AUTRE_PROFIL), empreinte(AUTRE_PROFIL))


if __name__ == "__main__":
    unittest.main()
