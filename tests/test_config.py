"""Ce qu'`AppConfig` lit encore : FreshRSS, les catégories, le seuil, le SMTP.

Tout ce qui concerne les fournisseurs de LLM est passé dans `test_providers.py`.
"""

import os
import pathlib
import unittest
from unittest import mock

from rssresume.config import AppConfig
from rssresume.profil import DEFAULT_PROFIL, ENV_PROFIL

BASE_ENV = {
    "FRESHRSS_BASE_URL": "https://example.com",
    "FRESHRSS_USERNAME": "user",
    "FRESHRSS_API_PASSWORD": "password",
}


class AppConfigTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {**BASE_ENV, "RSSRESUME_OUTPUT_DIR": "   "}, clear=True)
    def test_from_env_defaults_the_output_dir(self):
        self.assertEqual(pathlib.Path("output"), AppConfig.from_env().output_dir)

    @mock.patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "RSSRESUME_CATEGORIES": " Tech , News ",
            "RSSRESUME_EXCLUDED_CATEGORIES": "Non classé",
        },
        clear=True,
    )
    def test_from_env_parses_category_lists(self):
        config = AppConfig.from_env()

        self.assertEqual(["Tech", "News"], config.categories)
        self.assertEqual(["Non classé"], config.excluded_categories)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_from_env_lists_missing_required_variables(self):
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn("FRESHRSS_BASE_URL", str(raised.exception))

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, "RSSRESUME_SCORE_THRESHOLD": "5", "RSSRESUME_MAX_DIGEST_ITEMS": "3"},
        clear=True,
    )
    def test_from_env_reads_the_selection_settings(self):
        config = AppConfig.from_env()

        self.assertEqual(5, config.score_threshold)
        self.assertEqual(3, config.max_digest_items)

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_defaults_the_fallback_settings(self):
        """Le repli est actif par défaut : cinq articles, en descendant jusqu'au score 5."""
        config = AppConfig.from_env()

        self.assertEqual(5, config.fallback_threshold)
        self.assertEqual(5, config.min_digest_items)
        self.assertEqual({}, config.category_thresholds)

    @mock.patch.dict(
        os.environ,
        {**BASE_ENV, "RSSRESUME_CATEGORY_THRESHOLDS": "6 - Tech generaliste=5, Veille = 6 "},
        clear=True,
    )
    def test_from_env_parses_the_per_category_thresholds(self):
        config = AppConfig.from_env()

        self.assertEqual(
            {"6 - tech generaliste": 5, "veille": 6}, config.category_thresholds
        )

    @mock.patch.dict(
        os.environ, {**BASE_ENV, "RSSRESUME_CATEGORY_THRESHOLDS": "Tech generaliste"}, clear=True
    )
    def test_a_malformed_category_threshold_fails_at_startup(self):
        """Un seuil qu'on croit posé et qui ne l'est pas ne se voit qu'après des digests vides."""
        with self.assertRaises(ValueError) as raised:
            AppConfig.from_env()

        self.assertIn("RSSRESUME_CATEGORY_THRESHOLDS", str(raised.exception))

    @mock.patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "RSSRESUME_SCORE_THRESHOLD": "7",
            "RSSRESUME_CATEGORY_THRESHOLDS": "6 - Tech generaliste=5",
            "RSSRESUME_FALLBACK_THRESHOLD": "5",
            "RSSRESUME_MIN_DIGEST_ITEMS": "4",
            "RSSRESUME_MAX_DIGEST_ITEMS": "9",
        },
        clear=True,
    )
    def test_the_selection_rule_of_a_category_carries_its_own_threshold(self):
        config = AppConfig.from_env()

        generaliste = config.selection_rule("6 - TECH GENERALISTE")
        cyber = config.selection_rule("2 - Cybersecurite")

        self.assertEqual(5, generaliste.seuil)
        self.assertEqual(7, cyber.seuil)
        # Repli et plafond, eux, répondent au volume d'une journée : ils sont communs.
        self.assertEqual((5, 4, 9), (cyber.seuil_repli, cyber.minimum, cyber.plafond))

    @mock.patch.dict(os.environ, BASE_ENV, clear=True)
    def test_from_env_falls_back_to_the_default_profile(self):
        self.assertEqual(DEFAULT_PROFIL, AppConfig.from_env().profil)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_PROFIL: "Vigneronne en Anjou."}, clear=True)
    def test_from_env_reads_an_injected_profile(self):
        """Le profil est résolu une fois au démarrage, pas à chaque prompt."""
        self.assertEqual("Vigneronne en Anjou.", AppConfig.from_env().profil)


if __name__ == "__main__":
    unittest.main()
