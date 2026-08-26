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
    def test_from_env_falls_back_to_the_default_profile(self):
        self.assertEqual(DEFAULT_PROFIL, AppConfig.from_env().profil)

    @mock.patch.dict(os.environ, {**BASE_ENV, ENV_PROFIL: "Vigneronne en Anjou."}, clear=True)
    def test_from_env_reads_an_injected_profile(self):
        """Le profil est résolu une fois au démarrage, pas à chaque prompt."""
        self.assertEqual("Vigneronne en Anjou.", AppConfig.from_env().profil)


if __name__ == "__main__":
    unittest.main()
